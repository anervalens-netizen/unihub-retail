from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from domain.filter_scope import FilterInput
from schemas.dashboard import (
    DashboardSpecialCard,
    DashboardSpecialCardMetric,
)
from schemas.premium_glass import (
    PremiumGlassAgentStat,
    PremiumGlassAnalysis,
    PremiumGlassManagerStat,
    PremiumGlassModelStat,
    PremiumGlassProductStat,
    PremiumGlassStoreStat,
    PremiumGlassSummary,
    PremiumGlassSurfaceStat,
)
from services.dashboard.utils import _expand_current_manager_scope
from services.filters import build_scoped_params, scoped_clauses
from services import premium_glass_aggregation as premium_aggregation


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
    site_code: FilterInput,
    agent: FilterInput,
    surface: Literal["all", "screen", "camera"],
    *,
    current_scope: bool,
    include_closed_stores: bool,
) -> tuple[list[str], list[Any]]:
    params, positions = build_scoped_params(
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
    if surface == "camera":
        clauses.append("st.item_name ILIKE '%CAMERA%'")
    elif surface == "screen":
        clauses.append("st.item_name NOT ILIKE '%CAMERA%'")
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


def _zero_split_bucket() -> dict[str, Any]:
    return {
        "premium_qty": 0,
        "regular_qty": 0,
        "total_qty": 0,
        "premium_sales": Decimal(0),
        "regular_sales": Decimal(0),
        "total_sales": Decimal(0),
    }


def _add_split(bucket: dict[str, Any], qty: int, sales: Decimal, is_premium: bool) -> None:
    bucket["total_qty"] += qty
    bucket["total_sales"] += sales
    if is_premium:
        bucket["premium_qty"] += qty
        bucket["premium_sales"] += sales
    else:
        bucket["regular_qty"] += qty
        bucket["regular_sales"] += sales


def _share_pct(part: int | Decimal, total: int | Decimal) -> Decimal | None:
    if total == 0:
        return None
    return (Decimal(part) * Decimal(100) / Decimal(total)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _surface_for_item(item_name: str) -> tuple[str, str]:
    if "CAMERA" in item_name.upper():
        return "camera", "Camera"
    return "screen", "Ecran"


def _deduplicate_eligible_rows(rows: list[Any]) -> list[Any]:
    return list({
        (
            row["id"],
            row["item_code"],
            row["item_name"],
            row["site_code"],
            row["locatie"],
            row["firma"],
            row["manager"],
            row["agent"],
            row["is_premium"],
            row["qty"],
            row["sales"],
        ): row
        for row in rows
    }.values())


async def get_premium_glass_analysis(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    surface: Literal["all", "screen", "camera"] = "all",
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
        surface,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
    cte = _premium_base_cte(" AND ".join(clauses))

    matched_rows = await conn.fetch(
        f"""
        {cte}
        SELECT
            id, item_code, item_name, site_code, locatie, firma, manager, agent,
            is_premium, model_key, model_label, qty, sales
        FROM matched_lines
        """,
        *params,
    )
    target_model_count = int(
        await conn.fetchval(
            "SELECT COUNT(DISTINCT model_key)::INT FROM premium_glass_item_models"
        )
        or 0
    )
    return premium_aggregation.build_analysis(
        matched_rows,
        _deduplicate_eligible_rows(matched_rows),
        month=month,
        target_model_count=target_model_count,
        zero_bucket=_zero_split_bucket,
        add_split=_add_split,
        share_pct=_share_pct,
        surface_for_item=_surface_for_item,
    )


def build_premium_glass_card(analysis: PremiumGlassAnalysis) -> DashboardSpecialCard:
    summary = analysis.summary
    has_data = summary.total_qty > 0
    return DashboardSpecialCard(
        key="premium_glass",
        title="Folii Premium",
        subtitle="SAPPHIRE, CERAMIC si CORNING pentru ecran + camera premium din lista operationala",
        status="ready" if has_data else "no_data",
        status_label="Activ" if has_data else "Fara date",
        highlight_value=_format_int(summary.premium_qty),
        description="Compara foliile premium cu restul foliilor de sticla pentru aceleasi modele tinta.",
        coverage_note=(
            "Modele: iPhone 15/16/17 si Samsung S26, cu variantele eligibile din lista operationala."
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
