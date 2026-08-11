"""Campaigns service facade with one immutable repeatable-read DB snapshot."""

from __future__ import annotations

import asyncio
import time
from contextvars import ContextVar
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

import asyncpg

from domain.filter_scope import FilterInput
from repositories.campaigns import CampaignsRepository
from schemas.campaigns import (
    CampaignSnapshot,
    FocusHistoryResponse,
)
from services.campaigns.contracts import CampaignContext, CampaignResponseSnapshot
from services.campaigns.context import (
    build_campaign_context,
    load_campaign_context,
    materialize_period_evaluations,
)
from services.campaigns.incentives import (
    incentive_item_codes,
    normalized_incentive_periods,
)
from services.campaigns.loader import (
    load_campaign_configuration,
    load_incentive_campaign,
)
from services.campaigns.metrics import (
    CAMPAIGN_COMPUTE_SECONDS,
    CAMPAIGN_DB_LOAD_SECONDS,
    CAMPAIGN_POOL_WAIT_SECONDS,
    CampaignMetric,
    record_campaign_deadline_exceeded,
    record_campaign_request_rejected,
)
from services.campaigns.promotions import compute_promotion_result
from services.campaigns.dates import (
    CampaignDateRangeError,
    validate_campaign_date_range,
)
from services.campaigns.response import (
    build_promotions_incentives_response,
    map_campaign_overview,
    map_focus_history,
)
from services.campaigns.summary import (
    fetch_promo_incentive_summary,
    get_store_incentive_multipliers,
)
from services.dashboard_specials import (
    load_special_cards_config,
    parse_promotion_definition,
    parse_promotion_definitions,
)
from services.incentive_db import get_incentive_campaign
from services.request_deadline import RequestDeadline, RequestDeadlineExceeded


DEFAULT_CAMPAIGN_REQUEST_DEADLINE_SECONDS = 5.0
_CAMPAIGN_DEADLINE_PHASE: ContextVar[CampaignMetric] = ContextVar(
    "campaign_deadline_phase",
    default="compute",
)


async def _release_campaign_connection(pool: Any, conn: Any) -> None:
    """Finish pool release even when the request task is being cancelled."""
    release_task = asyncio.create_task(pool.release(conn))
    try:
        await asyncio.shield(release_task)
    except asyncio.CancelledError:
        await release_task
        raise


@asynccontextmanager
async def _campaign_snapshot_transaction(conn: Any, *, owned: bool):
    if not owned:
        yield conn
        return
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        yield conn


def _parse_campaign_dates(
    start_date: date | str,
    end_date: date | str,
) -> tuple[date, date]:
    try:
        start = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
        end = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date
    except ValueError as exc:
        record_campaign_request_rejected("invalid_iso_date")
        raise CampaignDateRangeError("invalid_iso_date") from exc
    return start, end


class CampaignsService:
    def __init__(self, repo: CampaignsRepository, pool: asyncpg.Pool | None):
        self.repo = repo
        self.pool = pool

    async def get_campaign_overview(
        self,
        month: str,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: FilterInput,
        agent: FilterInput,
    ) -> CampaignSnapshot:
        data = await self.repo.fetch_overview(
            month,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
        return map_campaign_overview(month, data)

    async def get_focus_history(
        self,
        month: str,
        months_back: int,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: FilterInput,
        agent: FilterInput,
    ) -> FocusHistoryResponse:
        rows = await self.repo.fetch_history(
            month,
            months_back,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
        return map_focus_history(rows)

    async def get_promotions_incentives(
        self,
        start_date: date,
        end_date: date,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: FilterInput,
        agent: FilterInput,
        promotion_key: str | None = None,
        view: str = "all",
        current_scope: bool = False,
        include_closed_stores: bool = False,
        deadline: RequestDeadline | None = None,
    ) -> dict[str, Any]:
        request_deadline = deadline or RequestDeadline(
            DEFAULT_CAMPAIGN_REQUEST_DEADLINE_SECONDS
        )
        token = _CAMPAIGN_DEADLINE_PHASE.set("compute")
        try:
            return await request_deadline.run(
                self._get_promotions_incentives_snapshot(
                    start_date,
                    end_date,
                    firma,
                    regional,
                    asm,
                    site_code,
                    agent,
                    promotion_key,
                    view,
                    current_scope,
                    include_closed_stores,
                )
            )
        except RequestDeadlineExceeded:
            record_campaign_deadline_exceeded(_CAMPAIGN_DEADLINE_PHASE.get())
            raise
        finally:
            _CAMPAIGN_DEADLINE_PHASE.reset(token)

    async def _get_promotions_incentives_snapshot(
        self,
        start_date: date,
        end_date: date,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: FilterInput,
        agent: FilterInput,
        promotion_key: str | None,
        view: str,
        current_scope: bool,
        include_closed_stores: bool,
        connection: asyncpg.Connection | None = None,
    ) -> dict[str, Any]:
        start, end = _parse_campaign_dates(start_date, end_date)
        month = validate_campaign_date_range(start, end)

        (
            _config,
            config_error,
            promotion_definitions,
            promotion_list_error,
            promotion_definition,
            promotion_error,
        ) = load_campaign_configuration(
            month,
            promotion_key=promotion_key,
            config_loader=load_special_cards_config,
            definitions_loader=parse_promotion_definitions,
            definition_loader=parse_promotion_definition,
        )
        if promotion_error is None:
            promotion_error = promotion_list_error
        include_incentive = view != "promo"

        # Every query and evaluator sees this exact immutable snapshot.  The
        # connection is released before pure aggregation and response mapping.
        owns_connection = connection is None
        _CAMPAIGN_DEADLINE_PHASE.set("pool_wait")
        pool_wait_started = time.perf_counter()
        if owns_connection:
            if self.pool is None:
                raise RuntimeError("Campaigns pool is unavailable")
            try:
                conn = await self.pool.acquire()
            finally:
                CAMPAIGN_POOL_WAIT_SECONDS.observe(
                    time.perf_counter() - pool_wait_started
                )
        else:
            conn = connection
        db_load_started = time.perf_counter()
        db_load_observed = False
        _CAMPAIGN_DEADLINE_PHASE.set("db_load")
        try:
            async with _campaign_snapshot_transaction(
                conn,
                owned=owns_connection,
            ):
                incentive_campaign = (
                    await load_incentive_campaign(
                        conn,
                        month,
                        loader=get_incentive_campaign,
                    )
                    if include_incentive
                    else None
                )
                campaign_context = await build_campaign_context(
                    conn,
                    config_error=config_error,
                    promotion_definitions=promotion_definitions,
                    promotion_definition=promotion_definition,
                    promotion_error=promotion_error,
                    incentive_campaign=incentive_campaign,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    include_incentive=include_incentive,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                    evaluator=compute_promotion_result,
                )
                summary = (
                    await fetch_promo_incentive_summary(
                        conn=conn,
                        month=month,
                        firma=firma,
                        regional=regional,
                        asm=asm,
                        site_code=site_code,
                        agent=agent,
                        current_scope=current_scope,
                        include_closed_stores=include_closed_stores,
                        campaign_context=campaign_context,
                    )
                    if include_incentive
                    else None
                )
                periods = normalized_incentive_periods(
                    incentive_campaign,
                    start=start,
                    end=end,
                )
                await materialize_period_evaluations(
                    conn,
                    campaign_context=campaign_context,
                    periods=periods,
                    promotion_definitions=promotion_definitions,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                    evaluator=compute_promotion_result,
                )
                store_multipliers, store_achievements = (
                    await get_store_incentive_multipliers(
                        conn,
                        month,
                        firma,
                        regional,
                        asm,
                        site_code,
                        current_scope=current_scope,
                        include_closed_stores=include_closed_stores,
                    )
                    if incentive_campaign is not None
                    else ({}, {})
                )

                has_active_promotion = (
                    promotion_definition is not None
                    and promotion_error is None
                )
                selected_evaluation = (
                    campaign_context.selected_promotion_evaluation
                )
                promotion_item_codes = (
                    selected_evaluation.item_codes
                    if selected_evaluation is not None
                    else []
                )
                promo_total_row = None
                promo_store_rows: list[Any] = []
                if has_active_promotion and promotion_item_codes:
                    promo_total_row = await self.repo.fetch_promo_total(
                        conn,
                        start,
                        end,
                        promotion_item_codes,
                        month,
                        firma=firma,
                        regional=regional,
                        asm=asm,
                        site_code=site_code,
                        agent=agent,
                        current_scope=current_scope,
                        include_closed_stores=include_closed_stores,
                    )
                    promo_store_rows = (
                        await self.repo.fetch_promo_store_rows(
                            conn,
                            start,
                            end,
                            promotion_item_codes,
                            month,
                            firma=firma,
                            regional=regional,
                            asm=asm,
                            site_code=site_code,
                            agent=agent,
                            current_scope=current_scope,
                            include_closed_stores=include_closed_stores,
                        )
                    )

                incentive_codes = incentive_item_codes(incentive_campaign)
                incentive_store_rows: list[Any] = []
                incentive_agent_rows: list[Any] = []
                if incentive_campaign is not None and incentive_codes:
                    incentive_store_rows = (
                        await self.repo.fetch_incentive_store_rows(
                            conn,
                            incentive_codes,
                            month,
                            firma=firma,
                            regional=regional,
                            asm=asm,
                            site_code=site_code,
                            agent=agent,
                            current_scope=current_scope,
                            include_closed_stores=include_closed_stores,
                        )
                    )
                    incentive_agent_rows = (
                        await self.repo.fetch_incentive_agent_rows(
                            conn,
                            incentive_codes,
                            month,
                            firma=firma,
                            regional=regional,
                            asm=asm,
                            site_code=site_code,
                            agent=agent,
                            current_scope=current_scope,
                            include_closed_stores=include_closed_stores,
                        )
                    )

                snapshot = CampaignResponseSnapshot(
                    start=start,
                    end=end,
                    month=month,
                    promotion_definitions=promotion_definitions,
                    promotion_list_error=promotion_list_error,
                    promotion_definition=promotion_definition,
                    promotion_error=promotion_error,
                    include_incentive=include_incentive,
                    incentive_campaign=incentive_campaign,
                    incentive_periods=periods,
                    campaign_context=campaign_context,
                    summary=summary,
                    store_multipliers=store_multipliers,
                    store_achievements=store_achievements,
                    promo_total_row=promo_total_row,
                    promo_store_rows=promo_store_rows,
                    incentive_store_rows=incentive_store_rows,
                    incentive_agent_rows=incentive_agent_rows,
                )

            CAMPAIGN_DB_LOAD_SECONDS.observe(time.perf_counter() - db_load_started)
            db_load_observed = True
            if owns_connection:
                await _release_campaign_connection(self.pool, conn)
                conn = None
            compute_started = time.perf_counter()
            _CAMPAIGN_DEADLINE_PHASE.set("compute")
            try:
                return await asyncio.to_thread(
                    build_promotions_incentives_response,
                    snapshot,
                )
            finally:
                CAMPAIGN_COMPUTE_SECONDS.observe(time.perf_counter() - compute_started)
        finally:
            if owns_connection and conn is not None:
                try:
                    await _release_campaign_connection(self.pool, conn)
                finally:
                    if not db_load_observed:
                        CAMPAIGN_DB_LOAD_SECONDS.observe(time.perf_counter() - db_load_started)


async def build_promotions_incentives_on_snapshot(
    repo: CampaignsRepository,
    conn: asyncpg.Connection,
    start_date: date,
    end_date: date,
    *,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    promotion_key: str | None = None,
    view: str = "all",
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> dict[str, Any]:
    """Build the canonical response on a caller-owned immutable DB snapshot."""
    service = CampaignsService(repo, None)
    return await service._get_promotions_incentives_snapshot(
        start_date,
        end_date,
        firma,
        regional,
        asm,
        site_code,
        agent,
        promotion_key,
        view,
        current_scope,
        include_closed_stores,
        connection=conn,
    )
