"""Heavy lifting for dashboard: stats + mix + period comparison + promo/incentive summary."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from repositories.dashboard_cutoffs import (
    fetch_period_comparison_cutoff_day as _fetch_period_comparison_cutoff_day,
    resolve_period_comparison_cutoff_day,
)
from schemas.dashboard import (
    BrandMixItem,
    CategoryMixItem,
    PeriodComparisonPayload,
    PeriodComparisonPoint,
    ReceiptBucketItem,
)
from services.campaigns import CampaignContext
from services.dashboard.utils import (
    _expand_current_manager_scope,
    _month_day_range,
    _shift_month,
)
from services.dashboard_specials import load_special_cards_config, parse_promotion_definition
from services.filters import FilterInput, build_scoped_params, scoped_clauses
from services.forecast import business_forecast_factor_ctes
from services.incentive_db import get_incentive_campaign
from services.receipt_identity import canonical_receipt_identity_sql


from services.dashboard.query_common import (
    _scope_clauses,
    _scope_join,
    _store_field,
)

async def _active_store_codes(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    *,
    current_scope: bool,
    include_closed_stores: bool,
) -> list[str]:
    params, positions = build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses = _scope_clauses(
        positions,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
        month_alias="agg.import_month",
        month_position=1,
    )
    rows = await conn.fetch(
        f"""SELECT DISTINCT agg.site_code
            FROM reporting_agent_day agg
            {_scope_join(current_scope)}
            WHERE {" AND ".join(clauses)}""",
        *params,
    )
    return [str(row["site_code"]) for row in rows]


def _comparison_scope(
    period_month: str,
    month: str,
    cutoff_day: int,
    active_store_codes: list[str],
    *,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool,
    include_closed_stores: bool,
) -> tuple[list[Any], list[str], list[str], str, bool]:
    start_date, end_date, day_range = _month_day_range(period_month, cutoff_day)
    is_current = period_month == month
    params, positions = build_scoped_params(
        [period_month, start_date, end_date],
        firma=firma if is_current else None,
        regional=regional if is_current else None,
        asm=asm if is_current else None,
        site_code=site_code if is_current else None,
        agent=agent,
    )
    clauses = _scope_clauses(
        positions,
        current_scope=current_scope and is_current,
        include_closed_stores=include_closed_stores,
    )
    cartela_clauses = scoped_clauses(
        positions, site_alias="c", store_alias="cs", agent_alias="c"
    )
    if current_scope and is_current and not include_closed_stores:
        cartela_clauses.append("cs.is_active = true")
    if not is_current:
        store_pos = len(params) + 1
        params.append(active_store_codes)
        clauses.append(f"agg.site_code = ANY(${store_pos}::TEXT[])")
        cartela_clauses.append(f"c.site_code = ANY(${store_pos}::TEXT[])")
    return params, clauses, cartela_clauses, day_range, is_current


def _comparison_point(
    label: str, period_month: str, day_range: str, row: Any
) -> PeriodComparisonPoint:
    return PeriodComparisonPoint(
        label=label,
        month=period_month,
        day_range=day_range,
        total_sales=Decimal(row["total_sales"]) if row else Decimal(0),
        total_quantity=row["total_quantity"] if row else 0,
        total_receipts=row["total_receipts"] if row else 0,
        cartele_qty=row["cartele_qty"] if row else 0,
        working_days=row["working_days"] if row else 0,
        daily_average=row["daily_average"] if row else None,
        avg_receipt_value=row["avg_receipt_value"] if row else None,
        medie_produs=row["medie_produs"] if row else None,
        proc_bon2acc=row["proc_bon2acc"] if row else None,
        prc_focus_acc_qty=row["prc_focus_acc_qty"] if row else None,
    )


async def _fetch_comparison_point(
    conn: Any,
    *,
    label: str,
    period_month: str,
    month: str,
    cutoff_day: int,
    active_store_codes: list[str],
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool,
    include_closed_stores: bool,
) -> PeriodComparisonPoint:
    params, query_scope, cartela_scope, day_range, is_current = _comparison_scope(
        period_month,
        month,
        cutoff_day,
        active_store_codes,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
    clauses = ["agg.import_month = $1", "agg.sale_date BETWEEN $2 AND $3", *query_scope]
    cartela_clauses = [
        "c.import_month = $1",
        "c.sale_date BETWEEN $2 AND $3",
        *cartela_scope,
    ]
    row = await conn.fetchrow(
        f"""
        WITH filtered_days AS (
            SELECT * FROM reporting_agent_day agg
            {_scope_join(current_scope and is_current)}
            WHERE {" AND ".join(clauses)}
        ),
        cartele_summary AS (
            SELECT COALESCE(SUM(c.total_quantity), 0)::INT AS cartele_qty
            FROM reporting_cartela_day c
            JOIN stores cs ON cs.site_code = c.site_code
            WHERE {" AND ".join(cartela_clauses)}
        )
        SELECT
            COALESCE(SUM(fd.total_sales), 0) AS total_sales,
            COALESCE(SUM(fd.total_quantity), 0)::INT AS total_quantity,
            COALESCE(SUM(fd.receipt_count), 0)::INT AS total_receipts,
            COALESCE(MAX(cs.cartele_qty), 0)::INT AS cartele_qty,
            COUNT(DISTINCT fd.sale_date)::INT AS working_days,
            ROUND(COALESCE(SUM(fd.total_sales), 0) / NULLIF(COUNT(DISTINCT fd.sale_date), 0), 2) AS daily_average,
            ROUND(COALESCE(SUM(fd.total_sales), 0) / NULLIF(COALESCE(SUM(fd.receipt_count), 0), 0), 2) AS avg_receipt_value,
            ROUND(COALESCE(SUM(fd.total_sales), 0) / NULLIF(COALESCE(SUM(fd.total_quantity), 0), 0), 2) AS medie_produs,
            ROUND(COALESCE(SUM(fd.receipt_2plus_count), 0) * 100.0 / NULLIF(COALESCE(SUM(fd.receipt_count), 0), 0), 2) AS proc_bon2acc,
            ROUND(COALESCE(SUM(fd.focus_quantity), 0) * 100.0 / NULLIF(COALESCE(SUM(fd.total_quantity), 0), 0), 2) AS prc_focus_acc_qty
        FROM cartele_summary cs LEFT JOIN filtered_days fd ON true
        """,
        *params,
    )
    return _comparison_point(label, period_month, day_range, row)


async def _fetch_period_comparison(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    cutoff_day: int | None = None,
    target_metric: str = "sales",
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> PeriodComparisonPayload:
    del target_metric
    cutoff = await resolve_period_comparison_cutoff_day(conn, month, cutoff_day)
    active_stores = await _active_store_codes(
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
    periods = [
        ("Curenta", month),
        ("Luna trecuta", _shift_month(month, -1)),
        ("Anul trecut", _shift_month(month, -12)),
    ]
    rows = [
        await _fetch_comparison_point(
            conn,
            label=label,
            period_month=period_month,
            month=month,
            cutoff_day=cutoff,
            active_store_codes=active_stores,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
            current_scope=current_scope,
            include_closed_stores=include_closed_stores,
        )
        for label, period_month in periods
    ]
    return PeriodComparisonPayload(
        current=rows[0], previous=rows[1], year_over_year=rows[2]
    )

async def _fetch_daily_last_year_for_current_cohort(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> list[Any]:
    year, mon = month.split("-")
    last_year_month = f"{int(year) - 1}-{mon}"

    baseline_params, baseline_positions = build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    baseline_clauses = _scope_clauses(
        baseline_positions,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
        month_alias="agg.import_month",
        month_position=1,
    )
    active_rows = await conn.fetch(
        f"""
        SELECT DISTINCT agg.site_code
        FROM reporting_agent_day agg
        {_scope_join(current_scope)}
        WHERE {" AND ".join(baseline_clauses)}
        """,
        *baseline_params,
    )
    active_store_codes = [r["site_code"] for r in active_rows]
    if not active_store_codes:
        return []

    params, positions = build_scoped_params(
        [last_year_month],
        # Historical daily comparison follows the current-store cohort. Applying
        # historical ownership again would drop stores moved between RMs.
        firma=None,
        regional=None,
        asm=None,
        site_code=None,
        agent=agent,
    )
    query_clauses = _scope_clauses(
        positions,
        current_scope=False,
        include_closed_stores=include_closed_stores,
    )
    store_pos = len(params) + 1
    params.append(active_store_codes)
    query_clauses.append(f"agg.site_code = ANY(${store_pos}::TEXT[])")
    clauses = [
        "agg.import_month = $1",
        *query_clauses,
    ]

    return await conn.fetch(
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
