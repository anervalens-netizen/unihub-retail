"""Special cards data assembly (promotion + incentive) for /api/dashboard/special-cards."""
from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from db.connection import get_pool
from schemas.dashboard import DashboardSpecialCard
from schemas.campaigns import PromoIncentiveSummary
from services.dashboard.queries import (
    DashboardCampaignContext,
    _fetch_promo_incentive_summary,
    _load_dashboard_campaign_context,
    _scope_clauses,
    _scope_join,
)
from services.dashboard_specials import (
    build_incentive_card,
    build_promotion_card,
)
from services.filters import build_scoped_params

async def _get_special_cards_data(
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    *,
    current_scope: bool = False,
    include_closed_stores: bool = False,
    campaign_context: DashboardCampaignContext | None = None,
    promo_incentive_summary: Awaitable[PromoIncentiveSummary] | None = None,
    pool: Any | None = None,
) -> list[DashboardSpecialCard]:
    """Internal helper to build special cards data without HTTP dependencies."""
    active_pool = pool or await get_pool()
    if campaign_context is None:
        async with active_pool.acquire() as conn:
            campaign_context = await _load_dashboard_campaign_context(
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
    config_error = campaign_context.config_error
    promotion_definition = campaign_context.promotion_definition
    promotion_error = campaign_context.promotion_error
    if (
        promotion_error is None
        and campaign_context.promotion_status.value != "complete"
    ):
        promotion_error = (
            campaign_context.promotion_warnings[0]
            if campaign_context.promotion_warnings
            else "Calculul promo este incomplet."
        )
    incentive_campaign = campaign_context.incentive_campaign
    promotion_stats: dict[str, Any] | None = None
    incentive_stats: dict[str, Any] | None = None
    incentive_definition_error: str | None = None

    selected_promotion_result = campaign_context.selected_promotion_result
    if selected_promotion_result is not None:
        promotion_stats = {
            "qualifying_bons": selected_promotion_result.qualifying_bons,
            "discounted_units": selected_promotion_result.discounted_units,
            "discount_value": selected_promotion_result.discount_value,
            "active_stores": selected_promotion_result.active_stores,
            "active_agents": selected_promotion_result.active_agents,
        }
    if incentive_campaign is not None:
        incentive_codes = list(
            incentive_campaign.get("item_codes")
            or incentive_campaign.get("reward_map", {}).keys()
        )
        if incentive_codes:
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
            ]
            query_clauses = _scope_clauses(
                positions,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
            )
            clauses.extend(query_clauses)
            summary: PromoIncentiveSummary | None = None
            async with active_pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    WITH filtered AS MATERIALIZED (
                        SELECT
                            agg.site_code,
                            agg.agent,
                            agg.item_code,
                            agg.net_quantity,
                            agg.positive_quantity,
                            agg.return_quantity
                        FROM reporting_item_month agg
                        {_scope_join(current_scope)}
                        WHERE {" AND ".join(clauses)}
                    ),
                    item_totals AS (
                        SELECT
                            false AS is_meta,
                            site_code,
                            item_code,
                            COALESCE(SUM(net_quantity), 0)::INT AS net_quantity,
                            COALESCE(SUM(positive_quantity), 0)::INT AS positive_quantity,
                            COALESCE(SUM(return_quantity), 0)::INT AS return_quantity,
                            0::BIGINT AS active_stores,
                            0::BIGINT AS active_agents,
                            0::BIGINT AS active_codes
                        FROM filtered
                        GROUP BY site_code, item_code
                    ),
                    meta AS (
                        SELECT
                            true AS is_meta,
                            NULL::TEXT AS site_code,
                            NULL::TEXT AS item_code,
                            0::INT AS net_quantity,
                            0::INT AS positive_quantity,
                            0::INT AS return_quantity,
                            COUNT(DISTINCT site_code) FILTER (WHERE positive_quantity > 0) AS active_stores,
                            COUNT(DISTINCT agent) FILTER (WHERE positive_quantity > 0) AS active_agents,
                            COUNT(DISTINCT item_code) FILTER (WHERE positive_quantity > 0) AS active_codes
                        FROM filtered
                    )
                    SELECT * FROM item_totals
                    UNION ALL
                    SELECT * FROM meta
                    """,
                    *params,
                )
                item_rows = [row for row in rows if not row["is_meta"]]
                meta_row = next((row for row in rows if row["is_meta"]), None)
                if promo_incentive_summary is None:
                    summary = await _fetch_promo_incentive_summary(
                        conn,
                        month,
                        firma,
                        regional,
                        asm,
                        site_code,
                        agent,
                        current_scope=current_scope,
                        include_closed_stores=include_closed_stores,
                        campaign_context=campaign_context,
                    )
            if promo_incentive_summary is not None:
                summary = await promo_incentive_summary
            assert summary is not None
            if summary.calculation_status == "invalid":
                incentive_definition_error = (
                    summary.calculation_warnings[0]
                    if summary.calculation_warnings
                    else "Calculul Incentive este indisponibil."
                )
            else:
                ret_qty = sum(int(row["return_quantity"]) for row in item_rows)
                incentive_stats = {
                    "net_quantity": summary.incentive_qty,
                    "positive_quantity": summary.incentive_qty,
                    "return_quantity": ret_qty,
                    "incentive_value": float(summary.incentive_value or 0),
                    "active_stores": int(meta_row["active_stores"]) if meta_row else 0,
                    "active_agents": int(meta_row["active_agents"]) if meta_row else 0,
                    "active_codes": int(meta_row["active_codes"]) if meta_row else 0,
                }

    cards: list[DashboardSpecialCard] = []
    if promotion_definition is not None or config_error:
        cards.append(
            build_promotion_card(
                month,
                promotion_definition,
                promotion_stats,
                config_error=config_error,
                definition_error=promotion_error,
            )
        )
    if incentive_campaign is not None or config_error:
        incentive_definition = (
            {
                "title": incentive_campaign["title"],
                "subtitle": incentive_campaign["subtitle"],
                "description": incentive_campaign["description"],
                "month": incentive_campaign["month"],
                "reward_per_unit": None,
            }
            if incentive_campaign is not None
            else None
        )
        cards.append(
            build_incentive_card(
                month,
                incentive_definition,
                incentive_stats,
                config_error=config_error,
                definition_error=incentive_definition_error,
                codes_error=None,
            )
        )
    return cards
