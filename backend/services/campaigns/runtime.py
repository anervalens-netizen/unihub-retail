"""Campaigns runtime: connection lifecycle, repeatable-read snapshot transaction, deadline phase metrics."""

from __future__ import annotations

import asyncio
import time
from contextvars import ContextVar
from contextlib import asynccontextmanager
from datetime import date
from typing import Any, Callable

import asyncpg

from domain.filter_scope import FilterInput
from repositories.campaigns import CampaignsRepository
from services.campaigns.metrics import (
    CAMPAIGN_COMPUTE_SECONDS,
    CAMPAIGN_DB_LOAD_SECONDS,
    CAMPAIGN_POOL_WAIT_SECONDS,
    CampaignMetric,
)
from services.campaigns.request import build_campaign_request
from services.campaigns.snapshot import load_campaign_snapshot


DEFAULT_CAMPAIGN_REQUEST_DEADLINE_SECONDS = 5.0
_CAMPAIGN_DEADLINE_PHASE: ContextVar[CampaignMetric] = ContextVar(
    "campaign_deadline_phase",
    default="compute",
)


async def release_campaign_connection(pool: Any, conn: Any) -> None:
    """Finish pool release even when the request task is being cancelled."""
    release_task = asyncio.create_task(pool.release(conn))
    try:
        await asyncio.shield(release_task)
    except asyncio.CancelledError:
        await release_task
        raise


@asynccontextmanager
async def campaign_snapshot_transaction(conn: Any, *, owned: bool):
    if not owned:
        yield conn
        return
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        yield conn


async def acquire_snapshot_connection(
    pool: asyncpg.Pool | None,
    *,
    caller_conn: asyncpg.Connection | None,
) -> tuple[asyncpg.Connection, bool]:
    """Resolve the DB connection used for the snapshot transaction.

    If the caller supplied a connection, return it without acquiring from the pool.
    Otherwise acquire from ``pool`` while observing the pool_wait phase metric.
    Raises RuntimeError when no connection is supplied and the pool is unavailable.
    """
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


async def run_promotions_incentives_snapshot(
    repo: CampaignsRepository,
    pool: asyncpg.Pool | None,
    *,
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
    response_builder: Callable[[Any], dict[str, Any]] | None = None,
    config_loader: Callable[[], tuple[Any, str | None]] | None = None,
    definitions_loader: Callable[[Any, str], tuple[list[Any], str | None]] | None = None,
    definition_loader: Callable[
        [Any, str, str | None], tuple[Any, str | None]
    ] | None = None,
    compute_promotion_result: Callable[..., Any] | None = None,
    fetch_promo_incentive_summary: Callable[..., Any] | None = None,
    get_store_incentive_multipliers: Callable[..., Any] | None = None,
    get_incentive_campaign: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical response while preserving repeatable-read + cancellation-safe release."""
    assert config_loader is not None, (
        "config_loader must be supplied by the facade"
    )
    assert definitions_loader is not None, (
        "definitions_loader must be supplied by the facade"
    )
    assert definition_loader is not None, (
        "definition_loader must be supplied by the facade"
    )
    assert compute_promotion_result is not None, (
        "compute_promotion_result must be supplied by the facade"
    )
    assert fetch_promo_incentive_summary is not None, (
        "fetch_promo_incentive_summary must be supplied by the facade"
    )
    assert get_store_incentive_multipliers is not None, (
        "get_store_incentive_multipliers must be supplied by the facade"
    )
    assert get_incentive_campaign is not None, (
        "get_incentive_campaign must be supplied by the facade"
    )
    request = build_campaign_request(
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
        config_loader=config_loader,
        definitions_loader=definitions_loader,
        definition_loader=definition_loader,
    )
    conn, owns_connection = await acquire_snapshot_connection(
        pool,
        caller_conn=connection,
    )
    db_started = time.perf_counter()
    observed = False
    _CAMPAIGN_DEADLINE_PHASE.set("db_load")
    try:
        async with campaign_snapshot_transaction(
            conn,
            owned=owns_connection,
        ):
            snapshot = await load_campaign_snapshot(
                conn,
                request,
                repo,
                compute_promotion_result=compute_promotion_result,
                fetch_promo_incentive_summary=fetch_promo_incentive_summary,
                get_store_incentive_multipliers=get_store_incentive_multipliers,
                get_incentive_campaign=get_incentive_campaign,
            )
        CAMPAIGN_DB_LOAD_SECONDS.observe(time.perf_counter() - db_started)
        observed = True
        if owns_connection:
            await release_campaign_connection(pool, conn)
            conn = None
        compute_started = time.perf_counter()
        _CAMPAIGN_DEADLINE_PHASE.set("compute")
        try:
            builder = response_builder
            assert builder is not None, (
                "response_builder must be supplied by the facade"
            )
            return await asyncio.to_thread(
                builder,
                snapshot,
            )
        finally:
            CAMPAIGN_COMPUTE_SECONDS.observe(
                time.perf_counter() - compute_started
            )
    finally:
        if owns_connection and conn is not None:
            try:
                await release_campaign_connection(pool, conn)
            finally:
                if not observed:
                    CAMPAIGN_DB_LOAD_SECONDS.observe(
                        time.perf_counter() - db_started
                    )


__all__ = [
    "DEFAULT_CAMPAIGN_REQUEST_DEADLINE_SECONDS",
    "acquire_snapshot_connection",
    "campaign_snapshot_transaction",
    "release_campaign_connection",
    "run_promotions_incentives_snapshot",
]
