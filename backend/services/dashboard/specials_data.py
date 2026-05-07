"""Special cards data assembly (promotion + incentive) for /api/dashboard/special-cards."""
from __future__ import annotations

from typing import Any

from db.connection import get_pool
from models import DashboardSpecialCard
from services.dashboard.queries import _get_store_incentive_multipliers
from services.dashboard.utils import _build_scoped_params
from services.dashboard_specials import (
    build_incentive_card,
    build_promotion_card,
    load_special_cards_config,
    parse_promotion_definition,
)
from services.filters import scoped_clauses
from services.incentive_db import get_incentive_campaign


async def _get_special_cards_data(
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> list[DashboardSpecialCard]:
    """Internal helper to build special cards data without HTTP dependencies."""
    config, config_error = load_special_cards_config()
    promotion_definition, promotion_error = parse_promotion_definition(config, month)
    promotion_stats: dict[str, Any] | None = None
    incentive_stats: dict[str, Any] | None = None

    pool = await get_pool()
    async with pool.acquire() as _conn_ic:
        incentive_campaign = await get_incentive_campaign(_conn_ic, month)

    if promotion_definition is not None and promotion_error is None:
        params, positions = _build_scoped_params(
            [
                month,
                promotion_definition["start_date"],
                promotion_definition["end_date"],
                promotion_definition["item_codes"],
            ],
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )

        clauses = [
            "agg.import_month = $1",
            "agg.sale_date BETWEEN $2 AND $3",
            "agg.item_code = ANY($4::TEXT[])",
        ]
        query_clauses = scoped_clauses(
            positions,
            site_alias="agg",
            store_alias="agg",
            agent_alias="agg",
        )
        clauses.extend(query_clauses)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT
                    COALESCE(SUM(agg.total_sales), 0) AS total_sales,
                    COALESCE(SUM(agg.positive_quantity), 0) AS total_quantity,
                    COUNT(DISTINCT agg.site_code) FILTER (WHERE agg.positive_quantity > 0) AS active_stores,
                    COUNT(DISTINCT agg.agent) FILTER (WHERE agg.positive_quantity > 0) AS active_agents
                FROM reporting_item_day agg
                WHERE {" AND ".join(clauses)}
                """,
                *params,
            )
            receipt_query_clauses = scoped_clauses(
                positions,
                site_alias="st",
                store_alias="s",
                agent_alias="st",
                include_cartela_filter=True,
            )
            receipt_row = await conn.fetchrow(
                f"""
                SELECT
                    COUNT(DISTINCT st.bon_nr) AS total_receipts
                FROM sales_transactions st
                JOIN stores s ON s.site_code = st.site_code
                WHERE st.import_month = $1
                  AND st.sale_date BETWEEN $2 AND $3
                  AND st.item_code = ANY($4::TEXT[])
                  {" ".join(f"AND {clause}" for clause in receipt_query_clauses)}
                """,
                *params,
            )
        promotion_stats = dict(row) if row else None
        if promotion_stats is not None:
            promotion_stats["total_receipts"] = int(
                (receipt_row["total_receipts"] if receipt_row else 0) or 0
            )

    if incentive_campaign is not None:
        reward_map = incentive_campaign["reward_map"]
        if reward_map:
            incentive_codes = list(reward_map.keys())
            params, positions = _build_scoped_params(
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
            query_clauses = scoped_clauses(
                positions,
                site_alias="agg",
                store_alias="agg",
                agent_alias="agg",
            )
            clauses.extend(query_clauses)
            async with pool.acquire() as conn:
                item_rows = await conn.fetch(
                    f"""
                    SELECT
                        agg.site_code,
                        agg.item_code,
                        COALESCE(SUM(agg.net_quantity), 0)::INT AS net_quantity,
                        COALESCE(SUM(agg.positive_quantity), 0)::INT AS positive_quantity,
                        COALESCE(SUM(agg.return_quantity), 0)::INT AS return_quantity
                    FROM reporting_item_month agg
                    WHERE {" AND ".join(clauses)}
                    GROUP BY agg.site_code, agg.item_code
                    """,
                    *params,
                )
                meta_row = await conn.fetchrow(
                    f"""
                    SELECT
                        COUNT(DISTINCT agg.site_code) FILTER (WHERE agg.positive_quantity > 0) AS active_stores,
                        COUNT(DISTINCT agg.agent) FILTER (WHERE agg.positive_quantity > 0) AS active_agents,
                        COUNT(DISTINCT agg.item_code) FILTER (WHERE agg.positive_quantity > 0) AS active_codes
                    FROM reporting_item_month agg
                    WHERE {" AND ".join(clauses)}
                    """,
                    *params,
                )
                store_multipliers, _ = await _get_store_incentive_multipliers(
                    conn, month, firma, regional, asm, site_code
                )
            net_qty = sum(int(r["net_quantity"]) for r in item_rows)
            pos_qty = sum(int(r["positive_quantity"]) for r in item_rows)
            ret_qty = sum(int(r["return_quantity"]) for r in item_rows)
            incentive_value = sum(
                max(0, int(r["net_quantity"]))
                * reward_map.get(r["item_code"], 0)
                * store_multipliers.get(r["site_code"], 0)
                for r in item_rows
            )
            incentive_stats = {
                "net_quantity": net_qty,
                "positive_quantity": pos_qty,
                "return_quantity": ret_qty,
                "incentive_value": incentive_value,
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
