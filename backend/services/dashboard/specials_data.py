"""Special cards data assembly (promotion + incentive) for /api/dashboard/special-cards."""
from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from db.connection import get_pool
from domain.filter_scope import FilterInput
from schemas.dashboard import DashboardSpecialCard
from schemas.campaigns import PromoIncentiveSummary
from services.campaigns import (
    CampaignContext,
    fetch_promo_incentive_summary,
    load_campaign_context,
)
from services.dashboard.queries import (
    _scope_clauses,
    _scope_join,
)
from services.dashboard_specials import (
    build_incentive_card,
    build_promotion_card,
)
from services.filters import build_scoped_params


def _effective_promotion_error(context: CampaignContext) -> str | None:
    if context.promotion_error is not None:
        return context.promotion_error
    if context.promotion_status.value == "complete":
        return None
    return (
        context.promotion_warnings[0]
        if context.promotion_warnings
        else "Calculul promo este incomplet."
    )


def _promotion_stats(context: CampaignContext) -> dict[str, Any] | None:
    result = context.selected_promotion_result
    if result is None:
        return None
    return {
        "qualifying_bons": result.qualifying_bons,
        "discounted_units": result.discounted_units,
        "discount_value": result.discount_value,
        "active_stores": result.active_stores,
        "active_agents": result.active_agents,
    }


async def _fetch_incentive_rows(
    pool: Any,
    *,
    month: str,
    incentive_codes: list[str],
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool,
    include_closed_stores: bool,
) -> tuple[list[Any], Any | None]:
    params, positions = build_scoped_params(
        [month, incentive_codes],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses = [
        "agg.import_month = $1",
        "agg.item_code = ANY($2::TEXT[])",
        *_scope_clauses(
            positions,
            current_scope=current_scope,
            include_closed_stores=include_closed_stores,
        ),
    ]
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            WITH filtered AS MATERIALIZED (
                SELECT agg.site_code, agg.agent, agg.item_code,
                       agg.net_quantity, agg.positive_quantity, agg.return_quantity
                FROM reporting_item_month agg
                {_scope_join(current_scope)}
                WHERE {" AND ".join(clauses)}
            ),
            item_totals AS (
                SELECT false AS is_meta, site_code, item_code,
                       COALESCE(SUM(net_quantity), 0)::INT AS net_quantity,
                       COALESCE(SUM(positive_quantity), 0)::INT AS positive_quantity,
                       COALESCE(SUM(return_quantity), 0)::INT AS return_quantity,
                       0::BIGINT AS active_stores, 0::BIGINT AS active_agents,
                       0::BIGINT AS active_codes
                FROM filtered GROUP BY site_code, item_code
            ),
            meta AS (
                SELECT true AS is_meta, NULL::TEXT AS site_code,
                       NULL::TEXT AS item_code, 0::INT AS net_quantity,
                       0::INT AS positive_quantity, 0::INT AS return_quantity,
                       COUNT(DISTINCT site_code) FILTER (WHERE positive_quantity > 0) AS active_stores,
                       COUNT(DISTINCT agent) FILTER (WHERE positive_quantity > 0) AS active_agents,
                       COUNT(DISTINCT item_code) FILTER (WHERE positive_quantity > 0) AS active_codes
                FROM filtered
            )
            SELECT * FROM item_totals UNION ALL SELECT * FROM meta
            """,
            *params,
        )
    return [row for row in rows if not row["is_meta"]], next(
        (row for row in rows if row["is_meta"]), None
    )


async def _load_incentive_stats(
    pool: Any,
    context: CampaignContext,
    summary_awaitable: Awaitable[PromoIncentiveSummary] | None,
    *,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool,
    include_closed_stores: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    campaign = context.incentive_campaign
    if campaign is None:
        return None, None
    codes = list(campaign.get("item_codes") or campaign.get("reward_map", {}).keys())
    if not codes:
        return None, None
    item_rows, meta = await _fetch_incentive_rows(
        pool,
        month=month,
        incentive_codes=codes,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
    if summary_awaitable is not None:
        summary = await summary_awaitable
    else:
        async with pool.acquire() as conn:
            summary = await fetch_promo_incentive_summary(
                conn,
                month,
                firma,
                regional,
                asm,
                site_code,
                agent,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
                campaign_context=context,
            )
    if summary.calculation_status == "invalid":
        return None, (
            summary.calculation_warnings[0]
            if summary.calculation_warnings
            else "Calculul Incentive este indisponibil."
        )
    return {
        "net_quantity": summary.incentive_qty,
        "positive_quantity": summary.incentive_qty,
        "return_quantity": sum(int(row["return_quantity"]) for row in item_rows),
        "incentive_value": float(summary.incentive_value or 0),
        "active_stores": int(meta["active_stores"]) if meta else 0,
        "active_agents": int(meta["active_agents"]) if meta else 0,
        "active_codes": int(meta["active_codes"]) if meta else 0,
    }, None


def _build_special_cards(
    month: str,
    context: CampaignContext,
    promotion_stats: dict[str, Any] | None,
    incentive_stats: dict[str, Any] | None,
    incentive_error: str | None,
) -> list[DashboardSpecialCard]:
    cards: list[DashboardSpecialCard] = []
    if context.promotion_definition is not None or context.config_error:
        cards.append(
            build_promotion_card(
                month,
                context.promotion_definition,
                promotion_stats,
                config_error=context.config_error,
                definition_error=_effective_promotion_error(context),
            )
        )
    if context.incentive_campaign is not None or context.config_error:
        campaign = context.incentive_campaign
        definition = (
            {
                "title": campaign["title"],
                "subtitle": campaign["subtitle"],
                "description": campaign["description"],
                "month": campaign["month"],
                "reward_per_unit": None,
            }
            if campaign is not None
            else None
        )
        cards.append(
            build_incentive_card(
                month,
                definition,
                incentive_stats,
                config_error=context.config_error,
                definition_error=incentive_error,
                codes_error=None,
            )
        )
    return cards


async def _get_special_cards_data(
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    *,
    current_scope: bool = False,
    include_closed_stores: bool = False,
    campaign_context: CampaignContext | None = None,
    promo_incentive_summary: Awaitable[PromoIncentiveSummary] | None = None,
    pool: Any | None = None,
) -> list[DashboardSpecialCard]:
    """Internal helper to build special cards data without HTTP dependencies."""
    active_pool = pool or await get_pool()
    if campaign_context is None:
        async with active_pool.acquire() as conn:
            campaign_context = await load_campaign_context(
                conn,
                month,
                firma,
                regional,
                asm,
                site_code,
                agent,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
            )
    incentive_stats, incentive_error = await _load_incentive_stats(
        active_pool,
        campaign_context,
        promo_incentive_summary,
        month=month,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
    return _build_special_cards(
        month,
        campaign_context,
        _promotion_stats(campaign_context),
        incentive_stats,
        incentive_error,
    )
