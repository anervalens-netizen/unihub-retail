"""Campaigns service facade with one immutable repeatable-read DB snapshot."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
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


@dataclass(slots=True)
class _CampaignRequest:
    start: date
    end: date
    month: str
    firma: str | None
    regional: str | None
    asm: str | None
    site_code: FilterInput
    agent: FilterInput
    config_error: str | None
    promotion_definitions: list[dict[str, Any]]
    promotion_list_error: str | None
    promotion_definition: dict[str, Any] | None
    promotion_error: str | None
    include_incentive: bool
    current_scope: bool
    include_closed_stores: bool


def _campaign_request(
    start_date: date,
    end_date: date,
    *,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    promotion_key: str | None,
    view: str,
    current_scope: bool,
    include_closed_stores: bool,
) -> _CampaignRequest:
    start, end = _parse_campaign_dates(start_date, end_date)
    month = validate_campaign_date_range(start, end)
    (
        _config,
        config_error,
        definitions,
        list_error,
        definition,
        definition_error,
    ) = load_campaign_configuration(
        month,
        promotion_key=promotion_key,
        config_loader=load_special_cards_config,
        definitions_loader=parse_promotion_definitions,
        definition_loader=parse_promotion_definition,
    )
    return _CampaignRequest(
        start=start,
        end=end,
        month=month,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
        config_error=config_error,
        promotion_definitions=definitions,
        promotion_list_error=list_error,
        promotion_definition=definition,
        promotion_error=definition_error or list_error,
        include_incentive=view != "promo",
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )


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

    async def _acquire_snapshot_connection(
        self,
        connection: asyncpg.Connection | None,
    ) -> tuple[asyncpg.Connection, bool]:
        owns_connection = connection is None
        if not owns_connection:
            assert connection is not None
            return connection, False
        if self.pool is None:
            raise RuntimeError("Campaigns pool is unavailable")
        _CAMPAIGN_DEADLINE_PHASE.set("pool_wait")
        started = time.perf_counter()
        try:
            return await self.pool.acquire(), True
        finally:
            CAMPAIGN_POOL_WAIT_SECONDS.observe(time.perf_counter() - started)

    async def _load_promotion_rows(
        self,
        conn: asyncpg.Connection,
        request: _CampaignRequest,
        campaign_context: CampaignContext,
    ) -> tuple[Any | None, list[Any]]:
        evaluation = campaign_context.selected_promotion_evaluation
        item_codes = evaluation.item_codes if evaluation is not None else []
        has_active = (
            request.promotion_definition is not None
            and request.promotion_error is None
        )
        if not has_active or not item_codes:
            return None, []
        total_row = await self.repo.fetch_promo_total(
            conn,
            request.start,
            request.end,
            item_codes,
            request.month,
            firma=request.firma,
            regional=request.regional,
            asm=request.asm,
            site_code=request.site_code,
            agent=request.agent,
            current_scope=request.current_scope,
            include_closed_stores=request.include_closed_stores,
        )
        store_rows = await self.repo.fetch_promo_store_rows(
            conn,
            request.start,
            request.end,
            item_codes,
            request.month,
            firma=request.firma,
            regional=request.regional,
            asm=request.asm,
            site_code=request.site_code,
            agent=request.agent,
            current_scope=request.current_scope,
            include_closed_stores=request.include_closed_stores,
        )
        return total_row, store_rows

    async def _load_incentive_rows(
        self,
        conn: asyncpg.Connection,
        request: _CampaignRequest,
        incentive_campaign: dict[str, Any] | None,
    ) -> tuple[list[Any], list[Any]]:
        item_codes = incentive_item_codes(incentive_campaign)
        if incentive_campaign is None or not item_codes:
            return [], []
        kwargs = {
            "firma": request.firma,
            "regional": request.regional,
            "asm": request.asm,
            "site_code": request.site_code,
            "agent": request.agent,
            "current_scope": request.current_scope,
            "include_closed_stores": request.include_closed_stores,
        }
        store_rows = await self.repo.fetch_incentive_store_rows(
            conn,
            item_codes,
            request.month,
            **kwargs,
        )
        agent_rows = await self.repo.fetch_incentive_agent_rows(
            conn,
            item_codes,
            request.month,
            **kwargs,
        )
        return store_rows, agent_rows

    async def _load_campaign_snapshot(
        self,
        conn: asyncpg.Connection,
        request: _CampaignRequest,
    ) -> CampaignResponseSnapshot:
        campaign = (
            await load_incentive_campaign(
                conn,
                request.month,
                loader=get_incentive_campaign,
            )
            if request.include_incentive
            else None
        )
        context = await build_campaign_context(
            conn,
            config_error=request.config_error,
            promotion_definitions=request.promotion_definitions,
            promotion_definition=request.promotion_definition,
            promotion_error=request.promotion_error,
            incentive_campaign=campaign,
            month=request.month,
            firma=request.firma,
            regional=request.regional,
            asm=request.asm,
            site_code=request.site_code,
            agent=request.agent,
            include_incentive=request.include_incentive,
            current_scope=request.current_scope,
            include_closed_stores=request.include_closed_stores,
            evaluator=compute_promotion_result,
        )
        summary = await self._load_campaign_summary(conn, request, context)
        periods = normalized_incentive_periods(
            campaign,
            start=request.start,
            end=request.end,
        )
        await self._materialize_campaign_periods(conn, request, context, periods)
        multipliers, achievements = await self._load_store_multipliers(
            conn,
            request,
            campaign,
        )
        promo_total, promo_stores = await self._load_promotion_rows(
            conn,
            request,
            context,
        )
        incentive_stores, incentive_agents = await self._load_incentive_rows(
            conn,
            request,
            campaign,
        )
        return CampaignResponseSnapshot(
            start=request.start,
            end=request.end,
            month=request.month,
            promotion_definitions=request.promotion_definitions,
            promotion_list_error=request.promotion_list_error,
            promotion_definition=request.promotion_definition,
            promotion_error=request.promotion_error,
            include_incentive=request.include_incentive,
            incentive_campaign=campaign,
            incentive_periods=periods,
            campaign_context=context,
            summary=summary,
            store_multipliers=multipliers,
            store_achievements=achievements,
            promo_total_row=promo_total,
            promo_store_rows=promo_stores,
            incentive_store_rows=incentive_stores,
            incentive_agent_rows=incentive_agents,
        )

    async def _load_campaign_summary(
        self,
        conn: asyncpg.Connection,
        request: _CampaignRequest,
        context: CampaignContext,
    ) -> Any | None:
        if not request.include_incentive:
            return None
        return await fetch_promo_incentive_summary(
            conn=conn,
            month=request.month,
            firma=request.firma,
            regional=request.regional,
            asm=request.asm,
            site_code=request.site_code,
            agent=request.agent,
            current_scope=request.current_scope,
            include_closed_stores=request.include_closed_stores,
            campaign_context=context,
        )

    async def _materialize_campaign_periods(
        self,
        conn: asyncpg.Connection,
        request: _CampaignRequest,
        context: CampaignContext,
        periods: list[dict[str, Any]],
    ) -> None:
        await materialize_period_evaluations(
            conn,
            campaign_context=context,
            periods=periods,
            promotion_definitions=request.promotion_definitions,
            month=request.month,
            firma=request.firma,
            regional=request.regional,
            asm=request.asm,
            site_code=request.site_code,
            agent=request.agent,
            current_scope=request.current_scope,
            include_closed_stores=request.include_closed_stores,
            evaluator=compute_promotion_result,
        )

    async def _load_store_multipliers(
        self,
        conn: asyncpg.Connection,
        request: _CampaignRequest,
        incentive_campaign: dict[str, Any] | None,
    ) -> tuple[dict[str, float], dict[str, float | None]]:
        if incentive_campaign is None:
            return {}, {}
        return await get_store_incentive_multipliers(
            conn,
            request.month,
            request.firma,
            request.regional,
            request.asm,
            request.site_code,
            current_scope=request.current_scope,
            include_closed_stores=request.include_closed_stores,
        )

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
        request = _campaign_request(
            start_date,
            end_date,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
            promotion_key=promotion_key,
            view=view,
            current_scope=current_scope,
            include_closed_stores=include_closed_stores,
        )
        conn, owns_connection = await self._acquire_snapshot_connection(connection)
        db_started = time.perf_counter()
        observed = False
        _CAMPAIGN_DEADLINE_PHASE.set("db_load")
        try:
            async with _campaign_snapshot_transaction(
                conn,
                owned=owns_connection,
            ):
                snapshot = await self._load_campaign_snapshot(conn, request)
            CAMPAIGN_DB_LOAD_SECONDS.observe(time.perf_counter() - db_started)
            observed = True
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
                CAMPAIGN_COMPUTE_SECONDS.observe(
                    time.perf_counter() - compute_started
                )
        finally:
            if owns_connection and conn is not None:
                try:
                    await _release_campaign_connection(self.pool, conn)
                finally:
                    if not observed:
                        CAMPAIGN_DB_LOAD_SECONDS.observe(
                            time.perf_counter() - db_started
                        )

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
