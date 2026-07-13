"""Special cards data assembly (promotion + incentive) for /api/dashboard/special-cards."""
from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from db.connection import get_pool
from models import DashboardSpecialCard
from schemas.campaigns import PromoIncentiveSummary
from services.dashboard.queries import (
    DashboardCampaignContext,
    _fetch_promo_incentive_summary,
    _get_store_incentive_multipliers,
    _load_dashboard_campaign_context,
    _scope_clauses,
    _scope_join,
)
from services.dashboard_specials import (
    build_incentive_card,
    build_promotion_card,
)
from services.filters import build_scoped_params


def _excluded_by_site_item(
    excluded_units: dict[tuple[str, str, str], int],
) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    for (site_code, _agent, item_code), units in excluded_units.items():
        out[(site_code, item_code)] = out.get((site_code, item_code), 0) + units
    return out


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
) -> list[DashboardSpecialCard]:
    """Internal helper to build special cards data without HTTP dependencies."""
    pool = await get_pool()
    if campaign_context is None:
        async with pool.acquire() as conn:
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
    incentive_campaign = campaign_context.incentive_campaign
    promotion_stats: dict[str, Any] | None = None
    incentive_stats: dict[str, Any] | None = None

    selected_promotion_result = campaign_context.selected_promotion_result
    if selected_promotion_result is not None:
        promotion_stats = {
            "qualifying_bons": selected_promotion_result.qualifying_bons,
            "discounted_units": selected_promotion_result.discounted_units,
            "active_stores": selected_promotion_result.active_stores,
            "active_agents": selected_promotion_result.active_agents,
        }
    promo_excluded = _excluded_by_site_item(
        campaign_context.promo_excluded_units
    )

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
            async with pool.acquire() as conn:
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
                store_multipliers, _ = await _get_store_incentive_multipliers(
                    conn,
                    month,
                    firma,
                    regional,
                    asm,
                    site_code,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )
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
            net_qty = 0
            pos_qty = 0
            ret_qty = 0
            incentive_value = 0.0
            for r in item_rows:
                site = r["site_code"]
                code = r["item_code"]
                # Unitatile vandute in promo (cu reducere co-purchase) nu se incentiveaza.
                excluded = promo_excluded.get((site, code), 0)
                adj_net = int(r["net_quantity"]) - excluded
                adj_pos = max(0, int(r["positive_quantity"]) - excluded)
                net_qty += max(0, adj_net)
                pos_qty += adj_pos
                ret_qty += int(r["return_quantity"])
                incentive_value += (
                    max(0, adj_net)
                    * incentive_campaign.get("reward_map", {}).get(code, 0)
                    * store_multipliers.get(site, 0)
                )
            incentive_stats = {
                "net_quantity": summary.incentive_qty,
                "positive_quantity": summary.incentive_qty,
                "return_quantity": ret_qty,
                "incentive_value": float(summary.incentive_value),
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
                definition_error=None,
                codes_error=None,
            )
        )
    return cards
