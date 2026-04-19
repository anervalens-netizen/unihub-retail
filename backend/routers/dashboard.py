from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query

from db.connection import get_pool
from models import (
    AgentStats,
    AsmStats,
    BrandMixItem,
    CategoryMixItem,
    DailySalesPoint,
    DashboardAllResponse,
    DashboardHistoryResponse,
    DashboardSpecialCardsResponse,
    DashboardSummary,
    MonthlyHistoryPoint,
    PeriodComparisonPayload,
    PromoIncentiveSummary,
    ReceiptBucketItem,
    RegionalStats,
    StoreStats,
    YearHistoryPoint,
    YearHistoryResponse,
)
from services.dashboard.queries import (
    _enrich_store_stats_with_campaign,
    _fetch_agent_stats_rows,
    _fetch_asm_stats,
    _fetch_brand_mix,
    _fetch_category_mix,
    _fetch_focus_subcategory_mix,
    _fetch_period_comparison,
    _fetch_promo_incentive_summary,
    _fetch_receipt_bucket_mix,
    _fetch_regional_stats,
    _fetch_store_stats_rows,
)
from services.dashboard.specials_data import _get_special_cards_data
from services.dashboard.utils import _build_scoped_params
from services.filters import normalize_filter, scoped_clauses

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
) -> DashboardSummary:
    params, positions = _build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses = scoped_clauses(
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
    )
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            WITH filtered_days AS (
                SELECT *
                FROM reporting_agent_day agg
                WHERE {" AND ".join(clauses)}
            ),
            sales_summary AS (
                SELECT
                    fd.import_month AS month,
                    COALESCE(SUM(fd.total_sales), 0) AS total_sales,
                    COALESCE(SUM(fd.total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(fd.receipt_count), 0)::INT AS total_receipts,
                    ROUND(COALESCE(SUM(fd.receipt_2plus_count), 0) * 100.0 / NULLIF(COALESCE(SUM(fd.receipt_count), 0), 0), 2) AS proc_bon2acc,
                    ROUND(COALESCE(SUM(fd.focus_quantity), 0) * 100.0 / NULLIF(COALESCE(SUM(fd.total_quantity), 0), 0), 2) AS prc_focus_acc_qty,
                    COUNT(DISTINCT fd.site_code)::INT AS total_stores,
                    COUNT(DISTINCT fd.agent)::INT AS total_agents,
                    COUNT(DISTINCT fd.sale_date)::INT AS working_days,
                    ROUND(
                        COALESCE(SUM(fd.total_sales), 0) / NULLIF(COUNT(DISTINCT fd.sale_date), 0),
                        2
                    ) AS daily_average
                FROM filtered_days fd
                GROUP BY fd.import_month
            ),
            last_sale AS (
                SELECT MAX(sale_date) AS last_sale_date
                FROM filtered_days
            ),
            target_summary AS (
                SELECT
                    stg.import_month AS month,
                    COALESCE(SUM(stg.target_value), 0) AS total_target
                FROM store_targets stg
                WHERE stg.import_month = $1
                  AND EXISTS (
                      SELECT 1
                      FROM filtered_days fd
                      WHERE fd.site_code = stg.site_code
                  )
                GROUP BY stg.import_month
            ),
            month_meta AS (
                SELECT
                    snap.import_month,
                    COALESCE(snap.is_month_final, true) AS is_month_final,
                    EXTRACT(DAY FROM (
                        date_trunc('month', to_date(snap.import_month || '-01', 'YYYY-MM-DD'))
                        + INTERVAL '1 month - 1 day'
                    ))::INT AS days_in_month
                FROM import_snapshots snap
                WHERE snap.import_month = $1 AND snap.status = 'completed'
                ORDER BY snap.created_at DESC
                LIMIT 1
            ),

            cartele_summary AS (
                SELECT
                    COALESCE(SUM(c.qty_total), 0)::INT AS cartele_qty
                FROM v_cartele_monthly c
                WHERE c.import_month = $1
                  AND EXISTS (
                      SELECT 1
                      FROM filtered_days fd
                      WHERE fd.site_code = c.site_code
                        AND fd.agent = c.agent
                        AND fd.import_month = c.import_month
                  )
            )
            SELECT
                ss.month,
                ss.total_sales,
                COALESCE(ts.total_target, 0) AS total_target,
                CASE
                    WHEN COALESCE(ts.total_target, 0) > 0
                    THEN ROUND(ss.total_sales * 100.0 / ts.total_target, 2)
                    ELSE NULL
                END AS target_progress_pct,
                CASE
                    WHEN COALESCE(mm.is_month_final, true) = false
                         AND ls.last_sale_date IS NOT NULL
                         AND EXTRACT(DAY FROM ls.last_sale_date) > 0
                    THEN ROUND(ss.total_sales / EXTRACT(DAY FROM ls.last_sale_date) * mm.days_in_month, 2)
                    ELSE ss.total_sales
                END AS forecast_sales,
                CASE
                    WHEN COALESCE(ts.total_target, 0) > 0
                         AND COALESCE(mm.is_month_final, true) = false
                         AND ls.last_sale_date IS NOT NULL
                         AND EXTRACT(DAY FROM ls.last_sale_date) > 0
                    THEN ROUND((ss.total_sales / EXTRACT(DAY FROM ls.last_sale_date) * mm.days_in_month) * 100.0 / ts.total_target, 2)
                    WHEN COALESCE(ts.total_target, 0) > 0
                    THEN ROUND(ss.total_sales * 100.0 / ts.total_target, 2)
                    ELSE NULL
                END AS forecast_target_progress_pct,
                ss.total_quantity,
                ss.total_receipts,
                ss.proc_bon2acc,
                ss.prc_focus_acc_qty,
                ss.total_stores,
                ss.total_agents,
                ss.working_days,
                ss.daily_average,
                COALESCE(mm.is_month_final, true) AS is_month_final,
                ls.last_sale_date,
                CASE
                    WHEN ls.last_sale_date IS NOT NULL THEN EXTRACT(DAY FROM ls.last_sale_date)::INT
                    ELSE NULL
                END AS imported_day_of_month,
                mm.days_in_month,
                cs.cartele_qty
            FROM sales_summary ss
            LEFT JOIN target_summary ts ON ts.month = ss.month
            LEFT JOIN month_meta mm ON mm.import_month = ss.month
            LEFT JOIN last_sale ls ON true
            LEFT JOIN cartele_summary cs ON true
            """,
            *params,
        )
    if row is None:
        return DashboardSummary(
            month=month,
            total_sales=0,
            total_target=0,
            target_progress_pct=None,
            forecast_sales=None,
            forecast_target_progress_pct=None,
            total_quantity=0,
            total_receipts=0,
            proc_bon2acc=None,
            prc_focus_acc_qty=None,
            total_stores=0,
            total_agents=0,
            working_days=0,
            daily_average=None,
            is_month_final=True,
            last_sale_date=None,
            imported_day_of_month=None,
            days_in_month=None,
            cartele_qty=0,
        )
    return DashboardSummary(**dict(row))


@router.get("/all", response_model=DashboardAllResponse)
async def get_dashboard_all(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
) -> DashboardAllResponse:
    """Returns all dashboard data except history in a single response.

    Runs agents, stores, and daily queries in parallel for speed.
    Calls get_summary directly for complete summary data (including targets).
    """
    pool = await get_pool()

    async def get_agents_data() -> list[AgentStats]:
        async with pool.acquire() as conn:
            rows = await _fetch_agent_stats_rows(
                conn,
                month,
                firma,
                regional,
                asm,
                site_code,
                agent,
            )
        return [AgentStats(**row) for row in rows]

    async def get_stores_data() -> list[StoreStats]:
        async with pool.acquire() as conn:
            rows = await _fetch_store_stats_rows(
                conn,
                month,
                firma,
                regional,
                asm,
                site_code,
                agent,
            )
            enriched = await _enrich_store_stats_with_campaign(
                conn,
                [dict(r) for r in rows],
                month,
                firma,
                regional,
                asm,
                site_code,
                agent,
            )
        return [StoreStats(**row) for row in enriched]

    async def get_daily_data() -> list[DailySalesPoint]:
        params, positions = _build_scoped_params(
            [month],
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
        clauses = scoped_clauses(
            positions,
            site_alias="agg",
            store_alias="agg",
            agent_alias="agg",
            month_alias="agg.import_month",
            month_position=1,
        )
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT
                    agg.sale_date,
                    COALESCE(SUM(agg.total_sales), 0) AS total_sales,
                    COALESCE(SUM(agg.total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(agg.receipt_count), 0)::INT AS receipt_count
                FROM reporting_agent_day agg
                WHERE {" AND ".join(clauses)}
                GROUP BY agg.sale_date
                ORDER BY agg.sale_date ASC
                """,
                *params,
            )
        return [DailySalesPoint(**dict(row)) for row in rows]

    async def get_period_comparison_data(
        cutoff_day: int,
    ) -> PeriodComparisonPayload:
        async with pool.acquire() as conn:
            return await _fetch_period_comparison(
                conn,
                month,
                cutoff_day,
                firma,
                regional,
                asm,
                site_code,
                agent,
            )

    async def get_category_mix_data() -> list[CategoryMixItem]:
        async with pool.acquire() as conn:
            return await _fetch_category_mix(
                conn, month, firma, regional, asm, site_code, agent
            )

    async def get_receipt_bucket_mix_data() -> list[ReceiptBucketItem]:
        async with pool.acquire() as conn:
            return await _fetch_receipt_bucket_mix(
                conn, month, firma, regional, asm, site_code, agent
            )

    async def get_focus_subcategory_mix_data() -> list[CategoryMixItem]:
        async with pool.acquire() as conn:
            return await _fetch_focus_subcategory_mix(
                conn, month, firma, regional, asm, site_code, agent
            )

    async def get_brand_mix_data() -> list[BrandMixItem]:
        async with pool.acquire() as conn:
            return await _fetch_brand_mix(
                conn, month, firma, regional, asm, site_code, agent
            )

    async def get_promo_incentive_data() -> PromoIncentiveSummary:
        async with pool.acquire() as conn:
            return await _fetch_promo_incentive_summary(
                conn, month, firma, regional, asm, site_code, agent
            )

    async def get_regional_data() -> list[RegionalStats]:
        async with pool.acquire() as conn:
            rows = await _fetch_regional_stats(
                conn, month, firma, regional, asm, site_code, agent
            )
        return [RegionalStats(**row) for row in rows]

    async def get_asm_data() -> list[AsmStats]:
        async with pool.acquire() as conn:
            rows = await _fetch_asm_stats(
                conn, month, firma, regional, asm, site_code, agent
            )
        return [AsmStats(**row) for row in rows]

    (
        agents,
        stores,
        daily,
        category_mix,
        receipt_bucket_mix,
        focus_subcategory_mix,
        brand_mix,
        promo_incentive,
        regionals,
        asms,
    ) = await asyncio.gather(
        get_agents_data(),
        get_stores_data(),
        get_daily_data(),
        get_category_mix_data(),
        get_receipt_bucket_mix_data(),
        get_focus_subcategory_mix_data(),
        get_brand_mix_data(),
        get_promo_incentive_data(),
        get_regional_data(),
        get_asm_data(),
    )
    summary = await get_summary(
        month=month,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    special_cards_response = await get_special_cards(
        month=month,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    cutoff_day = summary.imported_day_of_month or summary.days_in_month or 1
    period_comparison = await get_period_comparison_data(cutoff_day)

    return DashboardAllResponse(
        summary=summary,
        agents=agents,
        stores=stores,
        daily=daily,
        special_cards=special_cards_response.cards,
        period_comparison=period_comparison,
        category_mix=category_mix,
        receipt_bucket_mix=receipt_bucket_mix,
        focus_subcategory_mix=focus_subcategory_mix,
        brand_mix=brand_mix,
        promo_incentive=promo_incentive,
        regionals=regionals,
        asms=asms,
    )


@router.get("/daily", response_model=list[DailySalesPoint])
async def get_daily_sales(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
) -> list[DailySalesPoint]:
    params, positions = _build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses = scoped_clauses(
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
    )
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                agg.sale_date,
                COALESCE(SUM(agg.total_sales), 0) AS total_sales,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS total_quantity,
                COALESCE(SUM(agg.receipt_count), 0)::INT AS receipt_count
            FROM reporting_agent_day agg
            WHERE {" AND ".join(clauses)}
            GROUP BY agg.sale_date
            ORDER BY agg.sale_date ASC
            """,
            *params,
        )
    return [DailySalesPoint(**dict(row)) for row in rows]


@router.get("/special-cards", response_model=DashboardSpecialCardsResponse)
async def get_special_cards(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
) -> DashboardSpecialCardsResponse:
    cards = await _get_special_cards_data(
        month, firma, regional, asm, site_code, agent
    )
    return DashboardSpecialCardsResponse(cards=cards)


@router.get("/history", response_model=DashboardHistoryResponse)
async def get_monthly_history(
    month: str = Query(...),
    months_back: int = Query(12, ge=2, le=24),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
) -> DashboardHistoryResponse:
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

    sales_clauses = scoped_clauses(
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
    )
    sales_clauses.insert(
        0, "agg.import_month IN (SELECT import_month FROM recent_months)"
    )

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            WITH recent_months AS MATERIALIZED (
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
            filtered_days AS MATERIALIZED (
                SELECT *
                FROM reporting_agent_day agg
                WHERE {" AND ".join(sales_clauses)}
            ),
            sales_summary AS (
                SELECT
                    fd.import_month AS month,
                    COALESCE(SUM(fd.total_sales), 0) AS total_sales,
                    COALESCE(SUM(fd.total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(fd.receipt_count), 0)::INT AS total_receipts,
                    ROUND(
                        COALESCE(SUM(fd.receipt_2plus_count), 0) * 100.0
                        / NULLIF(COALESCE(SUM(fd.receipt_count), 0), 0),
                        2
                    ) AS proc_bon2acc,
                    ROUND(
                        COALESCE(SUM(fd.focus_quantity), 0) * 100.0
                        / NULLIF(COALESCE(SUM(fd.total_quantity), 0), 0),
                        2
                    ) AS prc_focus_acc_qty,
                    COUNT(DISTINCT fd.site_code)::INT AS total_stores,
                    COUNT(DISTINCT fd.agent)::INT AS total_agents,
                    COUNT(DISTINCT fd.sale_date)::INT AS working_days,
                    ROUND(COALESCE(SUM(fd.total_sales), 0) / NULLIF(COUNT(DISTINCT fd.sale_date), 0), 2) AS daily_average
                FROM filtered_days fd
                GROUP BY fd.import_month
            ),
            target_summary AS (
                SELECT
                    stg.import_month AS month,
                    COALESCE(SUM(stg.target_value), 0) AS total_target
                FROM store_targets stg
                WHERE stg.import_month IN (SELECT import_month FROM recent_months)
                  AND EXISTS (
                      SELECT 1
                      FROM filtered_days fd
                      WHERE fd.import_month = stg.import_month
                        AND fd.site_code = stg.site_code
                  )
                GROUP BY stg.import_month
            )
            SELECT
                ss.month,
                ss.total_sales,
                COALESCE(ts.total_target, 0) AS total_target,
                CASE
                    WHEN COALESCE(ts.total_target, 0) > 0
                    THEN ROUND(ss.total_sales * 100.0 / ts.total_target, 2)
                    ELSE NULL
                END AS target_progress_pct,
                ss.total_quantity,
                ss.total_receipts,
                ss.proc_bon2acc,
                ss.prc_focus_acc_qty,
                ss.total_stores,
                ss.total_agents,
                ss.working_days,
                ss.daily_average
            FROM sales_summary ss
            LEFT JOIN target_summary ts ON ts.month = ss.month
            ORDER BY ss.month ASC
            """,
            *params,
        )
    return DashboardHistoryResponse(
        history=[MonthlyHistoryPoint(**dict(row)) for row in rows]
    )


_RO_MONTHS = {
    1: "Ian", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mai", 6: "Iun",
    7: "Iul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


@router.get("/history-year", response_model=YearHistoryResponse)
async def get_history_by_year(
    year: int = Query(..., ge=2022, le=2030),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
) -> YearHistoryResponse:
    _firma = normalize_filter(firma)
    _regional = normalize_filter(regional)
    _asm = normalize_filter(asm)
    _site_code = normalize_filter(site_code)
    _agent = normalize_filter(agent)

    pool = await get_pool()
    async with pool.acquire() as conn:
        points: list[YearHistoryPoint] = []

        if year <= 2023 and _agent is None:
            hist_params: list[Any] = [year]
            hist_clauses: list[str] = []
            if year == 2023:
                hist_clauses.append("has.is_partial_year = TRUE")
            p = 2
            for val, col in [
                (_firma, "has.firma"),
                (_regional, "s.regional"),
                (_asm, "s.asm"),
                (_site_code, "has.site_code"),
            ]:
                if val is not None:
                    hist_clauses.append(f"{col} = ${p}")
                    hist_params.append(val)
                    p += 1

            where_hist = f"AND {' AND '.join(hist_clauses)}" if hist_clauses else ""
            row = await conn.fetchrow(
                f"""
                SELECT COALESCE(SUM(has.total_value), 0) AS total_sales,
                       COALESCE(SUM(has.total_qty), 0)::INT AS total_quantity
                FROM historical_annual_sales has
                JOIN stores s ON s.site_code = has.site_code
                WHERE has.year = $1 {where_hist}
                """,
                *hist_params,
            )
            if row and row["total_sales"] > 0:
                points.append(
                    YearHistoryPoint(
                        label="Ian–Aug" if year == 2023 else "2022",
                        sort_key=f"{year}-00",
                        total_sales=row["total_sales"],
                        total_target=Decimal(0),
                        total_quantity=row["total_quantity"],
                        is_aggregate=True,
                    )
                )

        start_month = f"{year}-09" if year == 2023 else f"{year}-01"
        end_month = f"{year}-12"

        rep_params: list[Any] = [start_month, end_month]
        rep_clauses: list[str] = []
        p = 3
        for val, col in [
            (_firma, "agg.firma"),
            (_regional, "agg.regional"),
            (_asm, "agg.asm"),
            (_site_code, "agg.site_code"),
            (_agent, "agg.agent"),
        ]:
            if val is not None:
                rep_clauses.append(f"{col} = ${p}")
                rep_params.append(val)
                p += 1

        where_rep = f"AND {' AND '.join(rep_clauses)}" if rep_clauses else ""

        rows = await conn.fetch(
            f"""
            WITH sales_agg AS (
                SELECT agg.import_month, agg.site_code,
                       SUM(agg.total_sales)    AS total_sales,
                       SUM(agg.total_quantity) AS total_quantity
                FROM reporting_agent_month agg
                JOIN stores s ON s.site_code = agg.site_code
                WHERE agg.import_month >= $1 AND agg.import_month <= $2
                  {where_rep}
                GROUP BY agg.import_month, agg.site_code
            ),
            month_sales AS (
                SELECT import_month,
                       SUM(total_sales)          AS total_sales,
                       SUM(total_quantity)::INT  AS total_quantity
                FROM sales_agg
                GROUP BY import_month
            ),
            month_targets AS (
                SELECT st.import_month, SUM(st.target_value) AS total_target
                FROM store_targets st
                WHERE st.import_month >= $1 AND st.import_month <= $2
                  AND EXISTS (
                      SELECT 1 FROM sales_agg sa
                      WHERE sa.import_month = st.import_month
                        AND sa.site_code = st.site_code
                  )
                GROUP BY st.import_month
            )
            SELECT ms.import_month,
                   ms.total_sales,
                   COALESCE(mt.total_target, 0) AS total_target,
                   ms.total_quantity
            FROM month_sales ms
            LEFT JOIN month_targets mt ON mt.import_month = ms.import_month
            ORDER BY ms.import_month
            """,
            *rep_params,
        )

        for r in rows:
            month_num = int(r["import_month"][5:7])
            points.append(
                YearHistoryPoint(
                    label=_RO_MONTHS[month_num],
                    sort_key=r["import_month"],
                    total_sales=r["total_sales"],
                    total_target=r["total_target"],
                    total_quantity=r["total_quantity"],
                    is_aggregate=False,
                )
            )

    return YearHistoryResponse(points=points)
