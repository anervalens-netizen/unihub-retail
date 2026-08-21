"""Campaigns runtime orchestration for one immutable database snapshot.

Database lifecycle primitives are supplied by the public facade because
``services.campaigns`` is the existing architecture-boundary exception.
"""

from __future__ import annotations

import asyncio
import time
from contextvars import ContextVar
from datetime import date
from typing import Any, Awaitable, Callable

from domain.filter_scope import FilterInput
from repositories.campaigns import CampaignsRepository
from services.campaigns.metrics import (
    CAMPAIGN_COMPUTE_SECONDS,
    CAMPAIGN_DB_LOAD_SECONDS,
    CampaignMetric,
)
from services.campaigns.request import build_campaign_request
from services.campaigns.snapshot import load_campaign_snapshot


DEFAULT_CAMPAIGN_REQUEST_DEADLINE_SECONDS = 5.0
_CAMPAIGN_DEADLINE_PHASE: ContextVar[CampaignMetric] = ContextVar(
    "campaign_deadline_phase",
    default="compute",
)


async def run_promotions_incentives_snapshot(
    repo: CampaignsRepository,
    *,
    acquire_connection: Callable[[], Awaitable[tuple[Any, bool]]],
    transaction: Callable[..., Any],
    release_connection: Callable[[Any], Awaitable[None]],
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
    response_builder: Callable[[Any], dict[str, Any]],
    config_loader: Callable[[], tuple[Any, str | None]],
    definitions_loader: Callable[[Any, str], tuple[list[Any], str | None]],
    definition_loader: Callable[
        [Any, str, str | None], tuple[Any, str | None]
    ],
    compute_promotion_result: Callable[..., Any],
    fetch_promo_incentive_summary: Callable[..., Any],
    get_store_incentive_multipliers: Callable[..., Any],
    get_incentive_campaign: Callable[..., Any],
) -> dict[str, Any]:
    """Build the canonical response using facade-supplied DB lifecycle callbacks."""
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
    conn, owns_connection = await acquire_connection()
    db_started = time.perf_counter()
    observed = False
    _CAMPAIGN_DEADLINE_PHASE.set("db_load")
    try:
        async with transaction(conn, owned=owns_connection):
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
            await release_connection(conn)
            conn = None
        compute_started = time.perf_counter()
        _CAMPAIGN_DEADLINE_PHASE.set("compute")
        try:
            return await asyncio.to_thread(response_builder, snapshot)
        finally:
            CAMPAIGN_COMPUTE_SECONDS.observe(
                time.perf_counter() - compute_started
            )
    finally:
        if owns_connection and conn is not None:
            try:
                await release_connection(conn)
            finally:
                if not observed:
                    CAMPAIGN_DB_LOAD_SECONDS.observe(
                        time.perf_counter() - db_started
                    )


__all__ = [
    "DEFAULT_CAMPAIGN_REQUEST_DEADLINE_SECONDS",
    "run_promotions_incentives_snapshot",
]
