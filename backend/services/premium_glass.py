from __future__ import annotations

from decimal import Decimal
from typing import Any

from models import (
    DashboardSpecialCard,
    DashboardSpecialCardMetric,
    PremiumGlassAgentStat,
    PremiumGlassAnalysis,
    PremiumGlassManagerStat,
    PremiumGlassModelStat,
    PremiumGlassProductStat,
    PremiumGlassStoreStat,
    PremiumGlassSummary,
)
from services.dashboard.utils import _build_scoped_params, _expand_current_manager_scope
from services.filters import scoped_clauses


def _format_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _format_pct(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.1f}%"


def _premium_scope(
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    *,
    current_scope: bool,
    include_closed_stores: bool,
) -> tuple[list[str], list[Any]]:
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
        site_alias="st",
        store_alias="s",
        agent_alias="st",
        month_alias="st.import_month",
        month_position=1,
        include_cartela_filter=True,
    )
    if current_scope:
        clauses = _expand_current_manager_scope(clauses, positions)
    if current_scope and not include_closed_stores:
        clauses.append("s.is_active = true")
    clauses.extend(
        [
            "LOWER(TRIM(COALESCE(st.category, ''))) = 'folii sticla'",
            "st.quantity > 0",
            "st.agent NOT ILIKE 'TR%'",
        ]
    )
    return clauses, params


def _premium_base_cte(where_sql: str) -> str:
    return f"""
        WITH base_lines AS (
            SELECT
                st.id,
                st.item_code,
                st.item_name,
                st.site_code,
                s.locatie,
                s.firma,
                COALESCE(NULLIF(TRIM(s.regional), ''), NULLIF(TRIM(s.asm), ''), 'Fara manager') AS manager,
                st.agent,
                pgm.is_premium_glass AS is_premium,
                pgm.model_key,
                pgm.model_label,
                st.quantity::INT AS qty,
                st.total_value AS sales
            FROM sales_transactions st
            JOIN stores s ON s.site_code = st.site_code
            JOIN premium_glass_item_models pgm ON pgm.item_code = st.item_code
            WHERE {where_sql}
        ),
        matched_lines AS (
            SELECT *
            FROM base_lines
        ),
        eligible_lines AS (
            SELECT DISTINCT
                id,
                item_code,
                item_name,
                site_code,
                locatie,
                firma,
                manager,
                agent,
                is_premium,
                qty,
                sales
            FROM matched_lines
        )
    """


async def get_premium_glass_analysis(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    *,
    current_scope: bool = True,
    include_closed_stores: bool = False,
) -> PremiumGlassAnalysis:
    clauses, params = _premium_scope(
        month,
        firma,
        regional,
        asm,
        site_code,
        agent,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
    cte = _premium_base_cte(" AND ".join(clauses))

    summary_row = await conn.fetchrow(
        f"""
        {cte}
        SELECT
            $1::TEXT AS month,
            COALESCE(SUM(qty), 0)::INT AS total_qty,
            COALESCE(SUM(sales), 0) AS total_sales,
            COALESCE(SUM(qty) FILTER (WHERE is_premium), 0)::INT AS premium_qty,
            COALESCE(SUM(sales) FILTER (WHERE is_premium), 0) AS premium_sales,
            COALESCE(SUM(qty) FILTER (WHERE NOT is_premium), 0)::INT AS regular_qty,
            COALESCE(SUM(sales) FILTER (WHERE NOT is_premium), 0) AS regular_sales,
            ROUND(
                COALESCE(SUM(qty) FILTER (WHERE is_premium), 0) * 100.0
                / NULLIF(COALESCE(SUM(qty), 0), 0),
                2
            ) AS premium_qty_share_pct,
            ROUND(
                COALESCE(SUM(sales) FILTER (WHERE is_premium), 0) * 100.0
                / NULLIF(COALESCE(SUM(sales), 0), 0),
                2
            ) AS premium_sales_share_pct,
            COUNT(DISTINCT site_code)::INT AS active_stores,
            COUNT(DISTINCT agent)::INT AS active_agents,
            COUNT(DISTINCT site_code) FILTER (WHERE is_premium)::INT AS premium_active_stores,
            COUNT(DISTINCT agent) FILTER (WHERE is_premium)::INT AS premium_active_agents,
            (SELECT COUNT(DISTINCT model_key)::INT FROM premium_glass_item_models) AS target_model_count
        FROM eligible_lines
        """,
        *params,
    )

    model_rows = await conn.fetch(
        f"""
        {cte}
        SELECT
            model_key,
            model_label,
            COALESCE(SUM(qty) FILTER (WHERE is_premium), 0)::INT AS premium_qty,
            COALESCE(SUM(qty) FILTER (WHERE NOT is_premium), 0)::INT AS regular_qty,
            COALESCE(SUM(qty), 0)::INT AS total_qty,
            COALESCE(SUM(sales) FILTER (WHERE is_premium), 0) AS premium_sales,
            COALESCE(SUM(sales) FILTER (WHERE NOT is_premium), 0) AS regular_sales,
            COALESCE(SUM(sales), 0) AS total_sales,
            ROUND(
                COALESCE(SUM(qty) FILTER (WHERE is_premium), 0) * 100.0
                / NULLIF(COALESCE(SUM(qty), 0), 0),
                2
            ) AS premium_qty_share_pct,
            COUNT(DISTINCT item_code) FILTER (WHERE is_premium)::INT AS premium_item_count,
            COUNT(DISTINCT item_code) FILTER (WHERE NOT is_premium)::INT AS regular_item_count
        FROM matched_lines
        GROUP BY model_key, model_label
        ORDER BY total_qty DESC, model_label ASC
        """,
        *params,
    )

    store_rows = await conn.fetch(
        f"""
        {cte}
        SELECT
            site_code,
            MAX(locatie) AS locatie,
            MAX(firma) AS firma,
            COALESCE(SUM(qty) FILTER (WHERE is_premium), 0)::INT AS premium_qty,
            COALESCE(SUM(qty) FILTER (WHERE NOT is_premium), 0)::INT AS regular_qty,
            COALESCE(SUM(qty), 0)::INT AS total_qty,
            COALESCE(SUM(sales) FILTER (WHERE is_premium), 0) AS premium_sales,
            COALESCE(SUM(sales) FILTER (WHERE NOT is_premium), 0) AS regular_sales,
            COALESCE(SUM(sales), 0) AS total_sales,
            ROUND(
                COALESCE(SUM(qty) FILTER (WHERE is_premium), 0) * 100.0
                / NULLIF(COALESCE(SUM(qty), 0), 0),
                2
            ) AS premium_qty_share_pct
        FROM eligible_lines
        GROUP BY site_code
        ORDER BY premium_qty DESC, total_qty DESC, locatie ASC
        """,
        *params,
    )

    manager_rows = await conn.fetch(
        f"""
        {cte}
        SELECT
            manager,
            COALESCE(SUM(qty) FILTER (WHERE is_premium), 0)::INT AS premium_qty,
            COALESCE(SUM(qty) FILTER (WHERE NOT is_premium), 0)::INT AS regular_qty,
            COALESCE(SUM(qty), 0)::INT AS total_qty,
            COALESCE(SUM(sales) FILTER (WHERE is_premium), 0) AS premium_sales,
            COALESCE(SUM(sales) FILTER (WHERE NOT is_premium), 0) AS regular_sales,
            COALESCE(SUM(sales), 0) AS total_sales,
            ROUND(
                COALESCE(SUM(qty) FILTER (WHERE is_premium), 0) * 100.0
                / NULLIF(COALESCE(SUM(qty), 0), 0),
                2
            ) AS premium_qty_share_pct,
            COUNT(DISTINCT site_code)::INT AS store_count,
            COUNT(DISTINCT agent)::INT AS agent_count
        FROM eligible_lines
        GROUP BY manager
        ORDER BY premium_qty DESC, total_qty DESC, manager ASC
        """,
        *params,
    )

    agent_rows = await conn.fetch(
        f"""
        {cte}
        SELECT
            agent,
            site_code,
            MAX(locatie) AS locatie,
            COALESCE(SUM(qty) FILTER (WHERE is_premium), 0)::INT AS premium_qty,
            COALESCE(SUM(qty) FILTER (WHERE NOT is_premium), 0)::INT AS regular_qty,
            COALESCE(SUM(qty), 0)::INT AS total_qty,
            COALESCE(SUM(sales) FILTER (WHERE is_premium), 0) AS premium_sales,
            COALESCE(SUM(sales) FILTER (WHERE NOT is_premium), 0) AS regular_sales,
            COALESCE(SUM(sales), 0) AS total_sales,
            ROUND(
                COALESCE(SUM(qty) FILTER (WHERE is_premium), 0) * 100.0
                / NULLIF(COALESCE(SUM(qty), 0), 0),
                2
            ) AS premium_qty_share_pct
        FROM eligible_lines
        GROUP BY agent, site_code
        ORDER BY premium_qty DESC, total_qty DESC, agent ASC
        """,
        *params,
    )

    product_rows = await conn.fetch(
        f"""
        {cte},
        product_models AS (
            SELECT
                item_code,
                ARRAY_AGG(DISTINCT model_label ORDER BY model_label) AS model_labels
            FROM matched_lines
            GROUP BY item_code
        )
        SELECT
            el.item_code,
            MAX(el.item_name) AS item_name,
            bool_or(el.is_premium) AS is_premium,
            COALESCE(pm.model_labels, ARRAY[]::TEXT[]) AS model_labels,
            COALESCE(SUM(el.qty), 0)::INT AS qty,
            COALESCE(SUM(el.sales), 0) AS sales,
            COUNT(DISTINCT el.site_code)::INT AS store_count
        FROM eligible_lines el
        LEFT JOIN product_models pm ON pm.item_code = el.item_code
        GROUP BY el.item_code, pm.model_labels
        ORDER BY qty DESC, sales DESC, item_name ASC
        LIMIT 12
        """,
        *params,
    )

    summary = (
        PremiumGlassSummary(**dict(summary_row))
        if summary_row
        else PremiumGlassSummary(month=month)
    )
    return PremiumGlassAnalysis(
        summary=summary,
        models=[PremiumGlassModelStat(**dict(row)) for row in model_rows],
        managers=[PremiumGlassManagerStat(**dict(row)) for row in manager_rows],
        stores=[PremiumGlassStoreStat(**dict(row)) for row in store_rows],
        agents=[PremiumGlassAgentStat(**dict(row)) for row in agent_rows],
        products=[PremiumGlassProductStat(**dict(row)) for row in product_rows],
    )


def build_premium_glass_card(analysis: PremiumGlassAnalysis) -> DashboardSpecialCard:
    summary = analysis.summary
    has_data = summary.total_qty > 0
    return DashboardSpecialCard(
        key="premium_glass",
        title="Folii Premium",
        subtitle="SAPPHIRE, CERAMIC si CORNING in categoria Folii Sticla",
        status="ready" if has_data else "no_data",
        status_label="Activ" if has_data else "Fara date",
        highlight_value=_format_int(summary.premium_qty),
        description="Compara foliile premium cu restul foliilor de sticla pentru aceleasi modele tinta.",
        coverage_note=(
            "Modele: iPhone 15/16/17 normal, Pro, Pro Max si Samsung S26 Ultra."
        ),
        metrics=[
            DashboardSpecialCardMetric(label="Premium", value=_format_int(summary.premium_qty)),
            DashboardSpecialCardMetric(label="Rest", value=_format_int(summary.regular_qty)),
            DashboardSpecialCardMetric(
                label="Share cant.",
                value=_format_pct(summary.premium_qty_share_pct),
            ),
            DashboardSpecialCardMetric(
                label="Magazine premium",
                value=_format_int(summary.premium_active_stores),
            ),
        ],
    )
