"""Campaigns snapshot data assembly: load promotion/incentive/summary rows from one DB snapshot."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

import asyncpg

from domain.filter_scope import FilterInput
from repositories.campaigns import CampaignsRepository
from services.campaigns.contracts import CampaignContext, CampaignResponseSnapshot
from services.campaigns.context import (
    build_campaign_context,
    materialize_period_evaluations,
)
from services.campaigns.incentives import (
    incentive_item_codes,
    normalized_incentive_periods,
)
from services.campaigns.loader import load_incentive_campaign
from services.campaigns.request import CampaignRequest


async def load_campaign_summary(
    conn: asyncpg.Connection,
    request: CampaignRequest,
    context: CampaignContext,
    repo: CampaignsRepository,
    fetch_promo_incentive_summary: Callable[..., Any],
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


async def materialize_campaign_periods(
    conn: asyncpg.Connection,
    request: CampaignRequest,
    context: CampaignContext,
    periods: list[dict[str, Any]],
    evaluator: Callable[..., Any],
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
        evaluator=evaluator,
    )


async def load_store_multipliers(
    conn: asyncpg.Connection,
    request: CampaignRequest,
    incentive_campaign: dict[str, Any] | None,
    get_store_incentive_multipliers: Callable[..., Any],
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


async def load_promotion_rows(
    conn: asyncpg.Connection,
    request: CampaignRequest,
    campaign_context: CampaignContext,
    repo: CampaignsRepository,
) -> tuple[Any | None, list[Any]]:
    evaluation = campaign_context.selected_promotion_evaluation
    item_codes = evaluation.item_codes if evaluation is not None else []
    has_active = (
        request.promotion_definition is not None
        and request.promotion_error is None
    )
    if not has_active or not item_codes:
        return None, []
    total_row = await repo.fetch_promo_total(
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
    store_rows = await repo.fetch_promo_store_rows(
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


async def load_incentive_rows(
    conn: asyncpg.Connection,
    request: CampaignRequest,
    incentive_campaign: dict[str, Any] | None,
    repo: CampaignsRepository,
) -> tuple[list[Any], list[Any]]:
    item_codes = incentive_item_codes(incentive_campaign)
    if incentive_campaign is None or not item_codes:
        return [], []
    store_rows = await repo.fetch_incentive_store_rows(
        conn,
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
    agent_rows = await repo.fetch_incentive_agent_rows(
        conn,
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
    return store_rows, agent_rows


async def load_campaign_snapshot(
    conn: asyncpg.Connection,
    request: CampaignRequest,
    repo: CampaignsRepository,
    *,
    compute_promotion_result: Callable[..., Any],
    fetch_promo_incentive_summary: Callable[..., Any],
    get_store_incentive_multipliers: Callable[..., Any],
    get_incentive_campaign: Callable[..., Any],
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
    summary = await load_campaign_summary(
        conn,
        request,
        context,
        repo,
        fetch_promo_incentive_summary,
    )
    periods = normalized_incentive_periods(
        campaign,
        start=request.start,
        end=request.end,
    )
    await materialize_campaign_periods(
        conn,
        request,
        context,
        periods,
        compute_promotion_result,
    )
    multipliers, achievements = await load_store_multipliers(
        conn,
        request,
        campaign,
        get_store_incentive_multipliers,
    )
    promo_total, promo_stores = await load_promotion_rows(
        conn,
        request,
        context,
        repo,
    )
    incentive_stores, incentive_agents = await load_incentive_rows(
        conn,
        request,
        campaign,
        repo,
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


__all__ = [
    "load_campaign_snapshot",
    "load_campaign_summary",
    "load_incentive_rows",
    "load_promotion_rows",
    "load_store_multipliers",
    "materialize_campaign_periods",
]
