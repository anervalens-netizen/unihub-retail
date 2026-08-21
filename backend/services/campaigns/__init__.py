"""Campaigns service facade with one immutable repeatable-read DB snapshot.

This module is a thin facade. Substantial orchestration lives in:
- :mod:`services.campaigns.request` — date/config assembly
- :mod:`services.campaigns.runtime` — connection lifecycle and deadline phases
- :mod:`services.campaigns.snapshot` — DB row assembly
"""

from __future__ import annotations

import asyncio
import time
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
from services.campaigns.contracts import CampaignContext
from services.campaigns.context import build_campaign_context, load_campaign_context
from services.campaigns.dates import (
    CampaignDateRangeError,
    validate_campaign_date_range,
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
from services.campaigns.request import CampaignRequest
from services.campaigns.response import (
    build_promotions_incentives_response,
    map_campaign_overview,
    map_focus_history,
)
from services.campaigns.runtime import (
    DEFAULT_CAMPAIGN_REQUEST_DEADLINE_SECONDS,
    _CAMPAIGN_DEADLINE_PHASE,
    run_promotions_incentives_snapshot,
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


async def _acquire_snapshot_connection(
    pool: asyncpg.Pool | None,
    *,
    caller_conn: asyncpg.Connection | None,
) -> tuple[asyncpg.Connection, bool]:
    """Resolve the DB connection used for the snapshot transaction."""
    owns_connection = caller_conn is None
    if not owns_connection:
        assert caller_conn is not None
        return caller_conn, False
    if pool is None:
        raise RuntimeError("Campaigns pool is unavailable")
    _CAMPAIGN_DEADLINE_PHASE.set("pool_wait")
    started = time.perf_counter()
    try:
        return await pool.acquire(), True
    finally:
        CAMPAIGN_POOL_WAIT_SECONDS.observe(time.perf_counter() - started)


async def _caller_owned_connection(
    conn: asyncpg.Connection,
) -> tuple[asyncpg.Connection, bool]:
    return conn, False


async def _caller_owned_release(_conn: Any) -> None:
    return None


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
                run_promotions_incentives_snapshot(
                    self.repo,
                    acquire_connection=lambda: _acquire_snapshot_connection(
                        self.pool,
                        caller_conn=None,
                    ),
                    transaction=_campaign_snapshot_transaction,
                    release_connection=lambda conn: _release_campaign_connection(
                        self.pool,
                        conn,
                    ),
                    start_date=start_date,
                    end_date=end_date,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    promotion_key=promotion_key,
                    view=view,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                    response_builder=build_promotions_incentives_response,
                    config_loader=load_special_cards_config,
                    definitions_loader=parse_promotion_definitions,
                    definition_loader=parse_promotion_definition,
                    compute_promotion_result=compute_promotion_result,
                    fetch_promo_incentive_summary=fetch_promo_incentive_summary,
                    get_store_incentive_multipliers=get_store_incentive_multipliers,
                    get_incentive_campaign=get_incentive_campaign,
                )
            )
        except RequestDeadlineExceeded:
            record_campaign_deadline_exceeded(_CAMPAIGN_DEADLINE_PHASE.get())
            raise
        finally:
            _CAMPAIGN_DEADLINE_PHASE.reset(token)


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
    return await run_promotions_incentives_snapshot(
        repo,
        acquire_connection=lambda: _caller_owned_connection(conn),
        transaction=_campaign_snapshot_transaction,
        release_connection=_caller_owned_release,
        start_date=start_date,
        end_date=end_date,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
        promotion_key=promotion_key,
        view=view,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
        response_builder=build_promotions_incentives_response,
        config_loader=load_special_cards_config,
        definitions_loader=parse_promotion_definitions,
        definition_loader=parse_promotion_definition,
        compute_promotion_result=compute_promotion_result,
        fetch_promo_incentive_summary=fetch_promo_incentive_summary,
        get_store_incentive_multipliers=get_store_incentive_multipliers,
        get_incentive_campaign=get_incentive_campaign,
    )


__all__ = [
    "CampaignsService",
    "CampaignContext",
    "CampaignDateRangeError",
    "CampaignMetric",
    "CampaignRequest",
    "CAMPAIGN_COMPUTE_SECONDS",
    "CAMPAIGN_DB_LOAD_SECONDS",
    "CAMPAIGN_POOL_WAIT_SECONDS",
    "DEFAULT_CAMPAIGN_REQUEST_DEADLINE_SECONDS",
    "build_campaign_context",
    "build_promotions_incentives_on_snapshot",
    "build_promotions_incentives_response",
    "compute_promotion_result",
    "fetch_promo_incentive_summary",
    "get_incentive_campaign",
    "get_store_incentive_multipliers",
    "load_campaign_configuration",
    "load_campaign_context",
    "load_incentive_campaign",
    "load_special_cards_config",
    "map_campaign_overview",
    "map_focus_history",
    "parse_promotion_definition",
    "parse_promotion_definitions",
    "record_campaign_deadline_exceeded",
    "record_campaign_request_rejected",
    "validate_campaign_date_range",
]
