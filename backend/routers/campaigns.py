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
    IncentiveCategory,
    IncentiveTopAgent,
    PromoTopStore,
)
from services.dashboard.queries import _fetch_promo_incentive_summary, _get_store_incentive_multipliers
from services.filters import build_scope_filter, normalize_filter, scoped_clauses
from services.dashboard_specials import (
    load_special_cards_config,
    parse_promotion_definition,
)
from services.incentive_db import get_incentive_campaign

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
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> CampaignsPromotionsResponse:
    from datetime import date as date_cls

    start = date_cls.fromisoformat(start_date)
    end = date_cls.fromisoformat(end_date)
    month = start_date[:7]

    config, _ = load_special_cards_config()
    promotion_definition, promotion_error = parse_promotion_definition(config, month)

    pool = await get_pool()
    async with pool.acquire() as conn:
        promo_title = (
            promotion_definition.get("title", "Promotie")
            if promotion_definition
            else ""
        )
        promo_description = (
            promotion_definition.get("description", "") if promotion_definition else ""
        )

        # Load incentive campaign from DB (single source of truth)
        incentive_campaign = await get_incentive_campaign(conn, month)
        incentive_title = incentive_campaign["title"] if incentive_campaign else ""
        incentive_description = incentive_campaign["description"] if incentive_campaign else ""

        summary = await _fetch_promo_incentive_summary(
            conn=conn,
            user=user,
            month=month,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )

        promo_qty = summary.promo_qty
        promo_impact = float(summary.promo_impact)
        incentive_qty = summary.incentive_qty
        incentive_value = float(summary.incentive_value)

        promo_total_qty = 0
        # Build store multipliers (used for both top_stores incentive and top_agents)
        store_multipliers: dict[str, float] = {}
        store_achievements: dict[str, float | None] = {}
        if incentive_campaign is not None:
            store_multipliers, store_achievements = await _get_store_incentive_multipliers(
                conn, user, month, firma, regional, asm, site_code
            )

        has_active_promotion = promotion_definition is not None and promotion_error is None

        if has_active_promotion:
            promo_month = start_date[:7]
            promo_params: list[Any] = [
                start,
                end,
                promotion_definition["item_codes"],
                promo_month,
            ]
            positions: dict[str, int] = {}
            for key, value in [
                ("firma", normalize_filter(firma)),
                ("regional", normalize_filter(regional)),
                ("asm", normalize_filter(asm)),
                ("site_code", normalize_filter(site_code)),
                ("agent", normalize_filter(agent)),
            ]:
                if value is not None:
                    promo_params.append(value)
                    positions[key] = len(promo_params)

            promo_clauses = [
                "agg.import_month = $4",
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

            total_row = await conn.fetchrow(
                f"""
                SELECT COALESCE(SUM(agg.net_quantity), 0) AS total_qty
                FROM reporting_item_day agg
                WHERE {" AND ".join(promo_clauses)}
                """,
                *promo_params,
                *promo_scope_params,
            )
            if total_row:
                promo_total_qty = int(total_row["total_qty"] or 0)

            store_rows = await conn.fetch(
                f"""
                SELECT
                    agg.site_code,
                    MAX(agg.locatie) AS locatie,
                    MAX(agg.firma) AS firma,
                    COALESCE(SUM(agg.positive_quantity), 0)::INT AS qty,
                    COALESCE(SUM(agg.net_quantity), 0)::INT AS total_qty
                FROM reporting_item_day agg
                WHERE {" AND ".join(promo_clauses)}
                GROUP BY agg.site_code
                ORDER BY qty DESC
                """,
                *promo_params,
                *promo_scope_params,
            )
            top_stores = [
                PromoTopStore(
                    store_name=f"{row['site_code']} - {row['locatie']}",
                    qty=row["qty"],
                    total_qty=row["total_qty"],
                    category_qty=0,
                    incentive_value=0.0,
                    achievement=store_achievements.get(row["site_code"]),
                    firma=row["firma"] or "",
                )
                for row in store_rows
            ]
        else:
            top_stores = []

        # Add incentive_value per store (promo stores or incentive-based list)
        if incentive_campaign is not None:
            reward_map_for_stores: dict[str, float] | None = incentive_campaign["reward_map"] or None
            if reward_map_for_stores:
                inc_store_params: list[Any] = [list(reward_map_for_stores.keys()), month]
                inc_store_positions: dict[str, int] = {}
                for key, value in [
                    ("firma", normalize_filter(firma)),
                    ("regional", normalize_filter(regional)),
                    ("asm", normalize_filter(asm)),
                    ("site_code", normalize_filter(site_code)),
                ]:
                    if value is not None:
                        inc_store_params.append(value)
                        inc_store_positions[key] = len(inc_store_params)
                inc_store_clauses = [
                    "agg.item_code = ANY($1::TEXT[])",
                    "agg.import_month = $2",
                ]
                inc_store_query_clauses, inc_store_scope_params = scoped_clauses(
                    user, inc_store_positions,
                    site_alias="agg", store_alias="agg", agent_alias="agg",
                    month_alias=None, month_position=None,
                    scope_base_alias="agg", param_floor=len(inc_store_params),
                )
                inc_store_clauses.extend(inc_store_query_clauses)
                store_item_rows = await conn.fetch(
                    f"""
                    SELECT agg.site_code, MAX(agg.locatie) AS locatie,
                           MAX(agg.firma) AS firma,
                           agg.item_code,
                           COALESCE(SUM(agg.net_quantity), 0)::INT AS qty
                    FROM reporting_item_month agg
                    WHERE {" AND ".join(inc_store_clauses)}
                    GROUP BY agg.site_code, agg.item_code
                    """,
                    *inc_store_params,
                    *inc_store_scope_params,
                )
                # Build {site_code: [locatie, incentive_value, firma]}
                store_inc: dict[str, list] = {}
                for row in store_item_rows:
                    sc = row["site_code"]
                    loc = row["locatie"]
                    firma_val = row["firma"] or ""
                    val = max(0, int(row["qty"])) * reward_map_for_stores.get(row["item_code"], 0) * store_multipliers.get(sc, 0)
                    if sc not in store_inc:
                        store_inc[sc] = [loc, 0.0, firma_val]
                    store_inc[sc][1] += val

                if has_active_promotion:
                    # Patch incentive_value into existing top_stores list
                    top_stores = [
                        PromoTopStore(
                            store_name=s.store_name,
                            qty=s.qty,
                            total_qty=s.total_qty,
                            category_qty=s.category_qty,
                            incentive_value=round(store_inc.get(s.store_name.split(" - ")[0], [None, 0.0, ""])[1], 2),
                            achievement=s.achievement,
                            firma=s.firma,
                        )
                        for s in top_stores
                    ]
                else:
                    # No promo: build top_stores from incentive data, sorted by incentive_value
                    top_stores = [
                        PromoTopStore(
                            store_name=f"{sc} - {data[0]}",
                            qty=0,
                            total_qty=0,
                            category_qty=0,
                            incentive_value=round(data[1], 2),
                            achievement=store_achievements.get(sc),
                            firma=data[2],
                        )
                        for sc, data in sorted(store_inc.items(), key=lambda x: -x[1][1])
                        if data[1] > 0
                    ]
                    # Fara [:10] — toate magazinele

        if incentive_campaign is not None:
            reward_map: dict[str, float] | None = incentive_campaign["reward_map"] or None
            if reward_map:
                incentive_month = start_date[:7]
                incentive_codes = list(reward_map.keys())
                incentive_params: list[Any] = [incentive_codes, incentive_month]
                incentive_positions: dict[str, int] = {}
                for key, value in [
                    ("firma", normalize_filter(firma)),
                    ("regional", normalize_filter(regional)),
                    ("asm", normalize_filter(asm)),
                    ("site_code", normalize_filter(site_code)),
                    ("agent", normalize_filter(agent)),
                ]:
                    if value is not None:
                        incentive_params.append(value)
                        incentive_positions[key] = len(incentive_params)

                incentive_clauses = [
                    "agg.item_code = ANY($1::TEXT[])",
                    "agg.import_month = $2",
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

                agent_item_rows = await conn.fetch(
                    f"""
                    SELECT
                        agg.agent,
                        agg.site_code,
                        agg.item_code,
                        COALESCE(SUM(agg.net_quantity), 0)::INT AS qty
                    FROM reporting_item_month agg
                    WHERE {" AND ".join(incentive_clauses)}
                    GROUP BY agg.agent, agg.site_code, agg.item_code
                    """,
                    *incentive_params,
                    *incentive_scope_params,
                )
                # Aggregate per agent and per reward-tier category
                agent_bonus: dict[str, float] = {}
                agent_qty: dict[str, int] = {}       # bucati incentive per agent
                agent_site: dict[str, str] = {}      # site_code per agent (pentru achievement lookup)
                tier_qty: dict[float, int] = {}
                tier_value: dict[float, float] = {}
                for row in agent_item_rows:
                    agent_name = row["agent"]
                    site = row["site_code"]
                    multiplier = store_multipliers.get(site, 0)
                    qty = max(0, int(row["qty"]))
                    reward = reward_map.get(row["item_code"], 0)
                    bonus = qty * reward * multiplier
                    agent_bonus[agent_name] = agent_bonus.get(agent_name, 0) + bonus
                    agent_qty[agent_name] = agent_qty.get(agent_name, 0) + qty
                    agent_site[agent_name] = site
                    # Category = reward tier (regardless of store multiplier for grouping)
                    tier_qty[reward] = tier_qty.get(reward, 0) + qty
                    tier_value[reward] = tier_value.get(reward, 0) + qty * reward
                top_agents = [
                    IncentiveTopAgent(
                        agent_name=agent,
                        qty_sold=agent_qty.get(agent, 0),
                        val_incentive=round(bonus, 2),
                        achievement=store_achievements.get(agent_site.get(agent, "")),
                    )
                    for agent, bonus in sorted(agent_bonus.items(), key=lambda x: -x[1])
                ]
                # Fara [:10] — toti agentii
                incentive_categories = [
                    IncentiveCategory(
                        label=f"{int(rv) if rv == int(rv) else rv} RON/buc",
                        qty=tier_qty[rv],
                        value=round(tier_value[rv], 2),
                    )
                    for rv in sorted(tier_qty, key=lambda r: -tier_qty[r])
                    if tier_qty[rv] > 0
                ]
                incentive_product_count = len(reward_map)
            else:
                top_agents = []
                incentive_categories = []
                incentive_product_count = 0
        else:
            top_agents = []
            incentive_categories = []
            incentive_product_count = 0

    return CampaignsPromotionsResponse(
        promo_title=promo_title,
        promo_description=promo_description,
        promo_qty=promo_qty,
        promo_total_qty=promo_total_qty,
        promo_category_qty=None,
        promo_impact=promo_impact,
        incentive_title=incentive_title,
        incentive_description=incentive_description,
        incentive_qty=incentive_qty,
        incentive_value=incentive_value,
        incentive_product_count=incentive_product_count,
        incentive_categories=incentive_categories,
        has_active_promotion=has_active_promotion,
        top_stores=top_stores,
        top_agents=top_agents,
    )
