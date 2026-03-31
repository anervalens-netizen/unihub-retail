from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from db.connection import get_pool
from dependencies import get_current_user
from models import (
    CampaignOverview,
    CampaignProductStat,
    CampaignSnapshot,
    CampaignStoreStat,
    CampaignsPromotionsResponse,
    FocusHistoryPoint,
    FocusHistoryResponse,
    IncentiveTopAgent,
    PromoTopStore,
    PromotionsIncentivesResponse,
    PromoData,
    PromoStoreStat,
    IncentiveData,
    IncentiveAgentStat,
)
from routers.dashboard_filters import scoped_clauses
from routers.shared import build_scope_filter, normalize_filter
from services.dashboard_specials import (
    load_special_cards_config,
    parse_promotion_definition,
    parse_incentive_definition,
    load_incentive_codes,
)
from decimal import Decimal
from services.dashboard_specials import (
    load_special_cards_config,
    parse_promotion_definition,
    parse_incentive_definition,
    load_incentive_codes,
)
from decimal import Decimal
from services.dashboard_specials import (
    load_special_cards_config,
    parse_promotion_definition,
    parse_incentive_definition,
    load_incentive_codes,
)
from decimal import Decimal

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


def _campaign_clauses(
    user: dict[str, Any],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    *,
    alias: str,
) -> tuple[list[str], list[Any]]:
    clauses = [f"{alias}.import_month = $1"]
    params: list[Any] = [month]
    for column, value in [
        (f"{alias}.firma", normalize_filter(firma)),
        (f"{alias}.regional", normalize_filter(regional)),
        (f"{alias}.asm", normalize_filter(asm)),
        (f"{alias}.site_code", normalize_filter(site_code)),
        (f"{alias}.agent", normalize_filter(agent)),
    ]:
        if value:
            params.append(value)
            clauses.append(f"{column} = ${len(params)}")
    scope_sql, scope_params = build_scope_filter(
        user,
        base_alias=alias,
        param_start=len(params) + 1,
    )
    if scope_sql:
        clauses.append(scope_sql)
        params.extend(scope_params)
    return clauses, params


@router.get("/overview", response_model=CampaignSnapshot)
async def get_campaign_overview(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> CampaignSnapshot:
    focus_clauses, focus_params = _campaign_clauses(
        user, month, firma, regional, asm, site_code, agent, alias="agg"
    )
    totals_clauses, totals_params = _campaign_clauses(
        user, month, firma, regional, asm, site_code, agent, alias="tot"
    )
    focus_where_sql = " AND ".join(focus_clauses)
    totals_where_sql = " AND ".join(totals_clauses)
    pool = await get_pool()
    async with pool.acquire() as conn:
        overview_row = await conn.fetchrow(
            f"""
            WITH focus_totals AS (
                SELECT
                    COALESCE(SUM(agg.total_sales), 0) AS total_focus_sales,
                    COALESCE(SUM(agg.total_quantity), 0)::INT AS total_focus_qty,
                    COUNT(DISTINCT agg.item_code) FILTER (WHERE agg.total_quantity > 0)::INT AS active_focus_products,
                    COUNT(DISTINCT agg.site_code) FILTER (WHERE agg.total_quantity > 0)::INT AS active_focus_stores
                FROM reporting_focus_item_month agg
                WHERE {focus_where_sql}
            ),
            overall_totals AS (
                SELECT
                    COALESCE(SUM(tot.total_quantity), 0)::INT AS total_quantity
                FROM reporting_agent_month tot
                WHERE {totals_where_sql}
            )
            SELECT
                $1::TEXT AS month,
                ft.total_focus_sales,
                ft.total_focus_qty,
                ROUND(ft.total_focus_qty * 100.0 / NULLIF(ot.total_quantity, 0), 2) AS focus_share_pct,
                ft.active_focus_products,
                ft.active_focus_stores
            FROM focus_totals ft
            CROSS JOIN overall_totals ot
            """,
            *focus_params,
        )
        product_rows = await conn.fetch(
            f"""
            SELECT
                agg.item_code,
                MAX(agg.item_name) AS item_name,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS qty_total,
                COALESCE(SUM(agg.total_sales), 0) AS sales_total,
                COUNT(DISTINCT agg.site_code)::INT AS store_count
            FROM reporting_focus_item_month agg
            WHERE {focus_where_sql}
            GROUP BY agg.item_code
            ORDER BY sales_total DESC, qty_total DESC, agg.item_code ASC
            LIMIT 8
            """,
            *focus_params,
        )
        store_rows = await conn.fetch(
            f"""
            SELECT
                agg.site_code,
                MAX(agg.locatie) AS locatie,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS qty_total,
                COALESCE(SUM(agg.total_sales), 0) AS sales_total,
                COUNT(DISTINCT agg.item_code) FILTER (WHERE agg.total_quantity > 0)::INT AS active_products
            FROM reporting_focus_item_month agg
            WHERE {focus_where_sql}
            GROUP BY agg.site_code
            ORDER BY sales_total DESC, qty_total DESC, locatie ASC
            LIMIT 8
            """,
            *focus_params,
        )

    overview = (
        CampaignOverview(**dict(overview_row))
        if overview_row
        else CampaignOverview(
            month=month,
            total_focus_sales=0,
            total_focus_qty=0,
            focus_share_pct=None,
            active_focus_products=0,
            active_focus_stores=0,
        )
    )
    return CampaignSnapshot(
        overview=overview,
        products=[CampaignProductStat(**dict(row)) for row in product_rows],
        stores=[CampaignStoreStat(**dict(row)) for row in store_rows],
    )


@router.get("/history", response_model=FocusHistoryResponse)
async def get_focus_history(
    month: str = Query(...),
    months_back: int = Query(12, ge=2, le=24),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> FocusHistoryResponse:
    params: list[Any] = [month, months_back]
    positions: dict[str, int] = {}
    for key, value in [
        ("firma", normalize_filter(firma)),
        ("regional", normalize_filter(regional)),
        ("asm", normalize_filter(asm)),
        ("site_code", normalize_filter(site_code)),
        ("agent", normalize_filter(agent)),
    ]:
        if value is not None:
            params.append(value)
            positions[key] = len(params)

    focus_clauses = ["agg.import_month IN (SELECT import_month FROM recent_months)"]
    totals_clauses = ["tot.import_month IN (SELECT import_month FROM recent_months)"]
    for key, focus_column, totals_column in [
        ("firma", "agg.firma", "tot.firma"),
        ("regional", "agg.regional", "tot.regional"),
        ("asm", "agg.asm", "tot.asm"),
        ("site_code", "agg.site_code", "tot.site_code"),
        ("agent", "agg.agent", "tot.agent"),
    ]:
        if key in positions:
            focus_clauses.append(f"{focus_column} = ${positions[key]}")
            totals_clauses.append(f"{totals_column} = ${positions[key]}")

    focus_scope_sql, scope_params = build_scope_filter(
        user,
        base_alias="agg",
        param_start=max([2, *positions.values()], default=2) + 1,
    )
    totals_scope_sql, _totals_scope_params = build_scope_filter(
        user,
        base_alias="tot",
        param_start=max([2, *positions.values()], default=2) + 1,
    )
    if focus_scope_sql:
        focus_clauses.append(focus_scope_sql)
    if totals_scope_sql:
        totals_clauses.append(totals_scope_sql)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            WITH recent_months AS (
                SELECT import_month
                FROM (
                    SELECT DISTINCT import_month
                    FROM import_snapshots
                    WHERE import_month <= $1
                      AND status = 'completed'
                    ORDER BY import_month DESC
                    LIMIT $2
                ) months
            ),
            focus_summary AS (
                SELECT
                    agg.import_month AS month,
                    COALESCE(SUM(agg.total_sales), 0) AS total_focus_sales,
                    COALESCE(SUM(agg.total_quantity), 0)::INT AS total_focus_qty,
                    COUNT(DISTINCT agg.item_code) FILTER (WHERE agg.total_quantity > 0)::INT AS active_focus_products,
                    COUNT(DISTINCT agg.site_code) FILTER (WHERE agg.total_quantity > 0)::INT AS active_focus_stores
                FROM reporting_focus_item_month agg
                WHERE {" AND ".join(focus_clauses)}
                GROUP BY agg.import_month
            ),
            total_summary AS (
                SELECT
                    tot.import_month AS month,
                    COALESCE(SUM(tot.total_quantity), 0)::INT AS total_quantity
                FROM reporting_agent_month tot
                WHERE {" AND ".join(totals_clauses)}
                GROUP BY tot.import_month
            )
            SELECT
                fs.month,
                fs.total_focus_sales,
                fs.total_focus_qty,
                ROUND(
                    fs.total_focus_qty * 100.0
                    / NULLIF(ts.total_quantity, 0),
                    2
                ) AS focus_share_pct,
                fs.active_focus_products,
                fs.active_focus_stores
            FROM focus_summary fs
            LEFT JOIN total_summary ts ON ts.month = fs.month
            ORDER BY fs.month ASC
            """,
            *params,
            *scope_params,
        )

    return FocusHistoryResponse(
        history=[FocusHistoryPoint(**dict(row)) for row in rows]
    )


@router.get("/promotions-incentives", response_model=CampaignsPromotionsResponse)
async def get_promotions_incentives(
    start_date: str = Query(...),
    end_date: str = Query(...),
    zone: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> CampaignsPromotionsResponse:
    # Parse date strings to date objects for asyncpg
    from datetime import date as date_cls

    start = date_cls.fromisoformat(start_date)
    end = date_cls.fromisoformat(end_date)

    config, _ = load_special_cards_config()
    promotion_definition, promotion_error = parse_promotion_definition(config)
    incentive_definition, incentive_error = parse_incentive_definition(config)

    pool = await get_pool()
    async with pool.acquire() as conn:
        promo_qty = 0
        promo_total_qty = 0
        promo_category_qty: int | None = None
        promo_impact: float = 0.0
        promo_title = ""
        promo_description = ""
        incentive_qty = 0
        incentive_value: float = 0.0
        incentive_title = ""
        incentive_description = ""
        top_stores: list[PromoTopStore] = []
        top_agents: list[IncentiveTopAgent] = []

        if promotion_definition is not None and promotion_error is None:
            promo_title = promotion_definition.get("title", "Promotie")
            promo_description = promotion_definition.get("description", "")

            promo_params: list[Any] = [
                start,
                end,
                promotion_definition["item_codes"],
            ]
            positions: dict[str, int] = {}
            for key, value in [
                ("firma", normalize_filter(zone)),
                ("regional", normalize_filter(zone)),
                ("asm", normalize_filter(zone)),
            ]:
                if value is not None:
                    promo_params.append(value)
                    positions[key] = len(promo_params)

            promo_clauses = [
                "agg.sale_date BETWEEN $1 AND $2",
                "agg.item_code = ANY($3::TEXT[])",
            ]
            promo_query_clauses, promo_scope_params = scoped_clauses(
                user,
                positions,
                site_alias="agg",
                store_alias="agg",
                agent_alias="agg",
                month_alias=None,
                month_position=None,
                scope_base_alias="agg",
                param_floor=len(promo_params),
            )
            promo_clauses.extend(promo_query_clauses)

            promo_row = await conn.fetchrow(
                f"""
                SELECT
                    COALESCE(SUM(agg.positive_quantity), 0) AS promo_qty,
                    COALESCE(SUM(agg.net_quantity), 0) AS total_qty,
                    COALESCE(SUM(agg.total_sales), 0) AS total_sales
                FROM reporting_item_day agg
                WHERE {" AND ".join(promo_clauses)}
                """,
                *promo_params,
                *promo_scope_params,
            )
            if promo_row:
                promo_qty = int(promo_row["promo_qty"] or 0)
                promo_total_qty = int(promo_row["total_qty"] or 0)
                promo_sales = float(promo_row["total_sales"] or 0)
                promo_impact = round(promo_sales * 0.20, 2)

            store_rows = await conn.fetch(
                f"""
                SELECT
                    agg.site_code,
                    MAX(agg.locatie) AS locatie,
                    COALESCE(SUM(agg.positive_quantity), 0)::INT AS qty,
                    COALESCE(SUM(agg.net_quantity), 0)::INT AS total_qty
                FROM reporting_item_day agg
                WHERE {" AND ".join(promo_clauses)}
                GROUP BY agg.site_code
                ORDER BY qty DESC
                LIMIT 10
                """,
                *promo_params,
                *promo_scope_params,
            )
            for row in store_rows:
                top_stores.append(
                    PromoTopStore(
                        store_name=f"{row['site_code']} - {row['locatie']}",
                        qty=row["qty"],
                        total_qty=row["total_qty"],
                        category_qty=0,
                    )
                )

        if incentive_definition is not None and incentive_error is None:
            incentive_title = incentive_definition.get("title", "Incentive")
            incentive_description = incentive_definition.get("description", "")

            incentive_codes, incentive_codes_error = load_incentive_codes(
                incentive_definition
            )
            if incentive_codes is not None and incentive_codes_error is None:
                incentive_params: list[Any] = [incentive_codes]
                incentive_positions: dict[str, int] = {}
                for key, value in [
                    ("firma", normalize_filter(zone)),
                    ("regional", normalize_filter(zone)),
                    ("asm", normalize_filter(zone)),
                ]:
                    if value is not None:
                        incentive_params.append(value)
                        incentive_positions[key] = len(incentive_params)

                incentive_clauses = [
                    "agg.item_code = ANY($1::TEXT[])",
                ]
                incentive_query_clauses, incentive_scope_params = scoped_clauses(
                    user,
                    incentive_positions,
                    site_alias="agg",
                    store_alias="agg",
                    agent_alias="agg",
                    month_alias=None,
                    month_position=None,
                    scope_base_alias="agg",
                    param_floor=len(incentive_params),
                )
                incentive_clauses.extend(incentive_query_clauses)

                agent_rows = await conn.fetch(
                    f"""
                    SELECT
                        agg.agent,
                        COALESCE(SUM(agg.positive_quantity), 0)::INT AS qty
                    FROM reporting_item_month agg
                    WHERE {" AND ".join(incentive_clauses)}
                    GROUP BY agg.agent
                    ORDER BY qty DESC
                    LIMIT 10
                    """,
                    *incentive_params,
                    *incentive_scope_params,
                )
                incentive_qty = sum(int(row["qty"] or 0) for row in agent_rows)
                reward_per_unit = incentive_definition.get("reward_per_unit", 5)
                incentive_value = round(incentive_qty * reward_per_unit, 2)
                top_agents = [
                    IncentiveTopAgent(agent_name=row["agent"], qty=row["qty"])
                    for row in agent_rows
                ]

    return CampaignsPromotionsResponse(
        promo_title=promo_title,
        promo_description=promo_description,
        promo_qty=promo_qty,
        promo_total_qty=promo_total_qty,
        promo_category_qty=promo_category_qty,
        promo_impact=promo_impact,
        incentive_title=incentive_title,
        incentive_description=incentive_description,
        incentive_qty=incentive_qty,
        incentive_value=incentive_value,
        top_stores=top_stores,
        top_agents=top_agents,
    )
