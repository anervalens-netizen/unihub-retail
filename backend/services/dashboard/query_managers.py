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

def _regional_base_query(
    return_receipt_identity: str,
    current_scope: bool,
    return_clauses_sql: str,
    clauses: list[str],
) -> str:
    return f"""
        WITH regional_base AS (
            SELECT
                agg.import_month,
                {_store_field("regional", current_scope)} AS regional,
                COALESCE(SUM(agg.total_sales), 0) AS total_vanzari,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS qty_total,
                COALESCE(SUM(agg.receipt_count), 0)::INT AS nr_bonuri,
                COUNT(DISTINCT agg.agent)::INT AS nr_agenti,
                COALESCE(SUM(agg.working_days), 0)::INT AS zile_active,
                COALESCE(SUM(agg.receipt_2plus_count), 0)::INT AS receipt_2plus_count,
                COALESCE(SUM(agg.focus_quantity), 0)::INT AS focus_quantity
            FROM reporting_agent_month agg
            {_scope_join(current_scope)}
            WHERE {" AND ".join(clauses)}
            GROUP BY agg.import_month, {_store_field("regional", current_scope)}
        ),
        regional_stores AS (
            SELECT DISTINCT {_store_field("regional", current_scope)} AS regional, agg.site_code
            FROM reporting_agent_month agg
            {_scope_join(current_scope)}
            WHERE {" AND ".join(clauses)}
        ),
        regional_targets AS (
            SELECT
                rs.regional,
                COALESCE(SUM(stg.target_value), 0) AS target
            FROM regional_stores rs
            LEFT JOIN store_targets stg
                ON stg.import_month = $1
                AND stg.site_code = rs.site_code
            GROUP BY rs.regional
        ),
        {business_forecast_factor_ctes()},
        return_summary AS (
            SELECT
                s.regional,
                COUNT(DISTINCT {return_receipt_identity})
                    FILTER (
                        WHERE st.quantity < 0
                          AND st.bon_nr IS NOT NULL
                    ) AS return_receipt_count
            FROM sales_transactions st
            JOIN stores s ON s.site_code = st.site_code
            WHERE st.import_month = $1
              AND NOT st.is_cartela
              AND {return_clauses_sql}
            GROUP BY s.regional
        )
        SELECT
            rb.import_month,
            rb.regional,
            rb.total_vanzari,
            rb.qty_total,
            rb.nr_bonuri,
            rb.nr_agenti,
            rb.zile_active,
            COALESCE(rt.target, 0) AS target,
            CASE
                WHEN COALESCE(rt.target, 0) > 0
                THEN ROUND(rb.total_vanzari * 100.0 / rt.target, 2)
                ELSE NULL
            END AS proc_realizare_target,
            CASE
                WHEN COALESCE(rt.target, 0) > 0
                THEN ROUND(rb.total_vanzari * fm.forecast_factor * 100.0 / rt.target, 2)
                ELSE NULL
            END AS forecast_target_pct,
            CASE
                WHEN rb.zile_active > 0
                THEN ROUND(rb.total_vanzari / rb.zile_active, 2)
                ELSE NULL
            END AS medie_zilnica,
            CASE
                WHEN rb.qty_total > 0
                THEN ROUND(rb.total_vanzari / rb.qty_total, 2)
                ELSE NULL
            END AS medie_produs,
            CASE
                WHEN rb.nr_bonuri > 0
                THEN ROUND(rb.receipt_2plus_count * 100.0 / rb.nr_bonuri, 2)
                ELSE NULL
            END AS proc_bon2acc,
            CASE
                WHEN rb.qty_total > 0
                THEN ROUND(rb.focus_quantity * 100.0 / rb.qty_total, 2)
                ELSE NULL
            END AS prc_focus_acc_qty,
            COALESCE(rs.return_receipt_count, 0)::INT AS return_receipt_count
        FROM regional_base rb
        CROSS JOIN forecast_meta fm
        LEFT JOIN regional_targets rt ON rt.regional = rb.regional
        LEFT JOIN return_summary rs ON rs.regional = rb.regional
        ORDER BY rb.total_vanzari DESC, rb.regional ASC
        """


async def _fetch_regional_base_rows(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> list[dict[str, Any]]:
    return_receipt_identity = canonical_receipt_identity_sql("st")
    params, positions = build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    query_clauses = _scope_clauses(
        positions,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
        month_alias="agg.import_month",
        month_position=1,
    )
    clauses = query_clauses or ["true"]
    return_clauses = _scope_clauses(
        positions,
        current_scope=True,
        include_closed_stores=include_closed_stores or not current_scope,
        source_alias="st",
        month_alias="st.import_month",
        month_position=1,
    )
    return_clauses_sql = " AND ".join(return_clauses)
    rows = await conn.fetch(
        _regional_base_query(
            return_receipt_identity, current_scope, return_clauses_sql, clauses
        ),
        *params,
    )

    base_rows = [dict(row) for row in rows]
    if not base_rows:
        return base_rows

    return base_rows


async def _enrich_regional_campaign(
    conn: Any,
    base_rows: list[dict[str, Any]],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> list[dict[str, Any]]:
    return_receipt_identity = canonical_receipt_identity_sql("st")
    config, _ = load_special_cards_config()
    promotion_definition, _ = parse_promotion_definition(config, month)
    incentive_campaign = await get_incentive_campaign(conn, month)
    incentive_codes = list(incentive_campaign.get("item_codes") or incentive_campaign.get("reward_map", {}).keys()) if incentive_campaign else None
    promotion_codes = (
        promotion_definition["item_codes"] if promotion_definition is not None else []
    )
    if not promotion_codes and not incentive_codes:
        for row in base_rows:
            row["promo_qty"] = 0
            row["incentive_qty"] = 0
        return base_rows

    metric_params, metric_positions = build_scoped_params(
        [month, promotion_codes or [], incentive_codes or []],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )

    metric_query_clauses = _scope_clauses(
        metric_positions,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
        month_alias="agg.import_month",
        month_position=1,
    )
    metric_clauses = ["agg.import_month = $1", *metric_query_clauses]
    metric_rows = await conn.fetch(
        f"""
        SELECT
            agg.import_month,
            {_store_field("regional", current_scope)} AS regional,
            COALESCE(
                SUM(
                    CASE
                        WHEN cardinality($2::TEXT[]) > 0
                             AND agg.item_code = ANY($2::TEXT[])
                        THEN agg.positive_quantity
                        ELSE 0
                    END
                ),
                0
            ) AS promo_qty,
            COALESCE(
                SUM(
                    CASE
                        WHEN cardinality($3::TEXT[]) > 0
                             AND agg.item_code = ANY($3::TEXT[])
                        THEN agg.positive_quantity
                        ELSE 0
                    END
                ),
                0
            ) AS incentive_qty
        FROM reporting_item_month agg
        {_scope_join(current_scope)}
        WHERE {" AND ".join(metric_clauses)}
        GROUP BY agg.import_month, {_store_field("regional", current_scope)}
        """,
        *metric_params,
    )
    campaign_metrics = {
        (str(row["import_month"]), str(row["regional"])): dict(row)
        for row in metric_rows
    }
    for row in base_rows:
        metrics = campaign_metrics.get((str(row["import_month"]), str(row["regional"])))
        row["promo_qty"] = int(metrics["promo_qty"]) if metrics else 0
        row["incentive_qty"] = int(metrics["incentive_qty"]) if metrics else 0
    return base_rows



async def _fetch_regional_stats(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> list[dict[str, Any]]:
    return_receipt_identity = canonical_receipt_identity_sql("st")
    base_rows = await _fetch_regional_base_rows(
        conn, month, firma, regional, asm, site_code, agent,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
    if not base_rows:
        return base_rows
    return await _enrich_regional_campaign(
        conn, base_rows, month, firma, regional, asm, site_code, agent,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
async def _fetch_asm_base_rows(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> list[dict[str, Any]]:
    params, positions = build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    query_clauses = _scope_clauses(
        positions,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
        month_alias="agg.import_month",
        month_position=1,
    )
    clauses = query_clauses or ["true"]
    rows = await conn.fetch(
        f"""
        WITH asm_base AS (
            SELECT
                agg.import_month,
                {_store_field("regional", current_scope)} AS regional,
                {_store_field("asm", current_scope)} AS asm,
                COALESCE(SUM(agg.total_sales), 0) AS total_vanzari,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS qty_total,
                COALESCE(SUM(agg.receipt_count), 0)::INT AS nr_bonuri,
                COUNT(DISTINCT agg.agent)::INT AS nr_agenti,
                COALESCE(SUM(agg.working_days), 0)::INT AS zile_active,
                COALESCE(SUM(agg.receipt_2plus_count), 0)::INT AS receipt_2plus_count,
                COALESCE(SUM(agg.focus_quantity), 0)::INT AS focus_quantity
            FROM reporting_agent_month agg
            {_scope_join(current_scope)}
            WHERE {" AND ".join(clauses)}
            GROUP BY agg.import_month, {_store_field("regional", current_scope)}, {_store_field("asm", current_scope)}
        ),
        asm_stores AS (
            SELECT DISTINCT
                {_store_field("regional", current_scope)} AS regional,
                {_store_field("asm", current_scope)} AS asm,
                agg.site_code
            FROM reporting_agent_month agg
            {_scope_join(current_scope)}
            WHERE {" AND ".join(clauses)}
        ),
        asm_targets AS (
            SELECT
                ast.regional,
                ast.asm,
                COALESCE(SUM(stg.target_value), 0) AS target
            FROM asm_stores ast
            LEFT JOIN store_targets stg
                ON stg.import_month = $1
                AND stg.site_code = ast.site_code
            GROUP BY ast.regional, ast.asm
        )
        SELECT
            ab.import_month,
            ab.regional,
            ab.asm,
            ab.total_vanzari,
            ab.qty_total,
            ab.nr_bonuri,
            ab.nr_agenti,
            ab.zile_active,
            COALESCE(at.target, 0) AS target,
            CASE
                WHEN COALESCE(at.target, 0) > 0
                THEN ROUND(ab.total_vanzari * 100.0 / at.target, 2)
                ELSE NULL
            END AS proc_realizare_target,
            CASE
                WHEN ab.zile_active > 0
                THEN ROUND(ab.total_vanzari / ab.zile_active, 2)
                ELSE NULL
            END AS medie_zilnica,
            CASE
                WHEN ab.qty_total > 0
                THEN ROUND(ab.total_vanzari / ab.qty_total, 2)
                ELSE NULL
            END AS medie_produs,
            CASE
                WHEN ab.nr_bonuri > 0
                THEN ROUND(ab.receipt_2plus_count * 100.0 / ab.nr_bonuri, 2)
                ELSE NULL
            END AS proc_bon2acc,
            CASE
                WHEN ab.qty_total > 0
                THEN ROUND(ab.focus_quantity * 100.0 / ab.qty_total, 2)
                ELSE NULL
            END AS prc_focus_acc_qty
        FROM asm_base ab
        LEFT JOIN asm_targets at ON at.regional = ab.regional AND at.asm = ab.asm
        ORDER BY ab.total_vanzari DESC, ab.regional ASC, ab.asm ASC
        """,
        *params,
    )

    base_rows = [dict(row) for row in rows]
    if not base_rows:
        return base_rows

    return base_rows


async def _enrich_asm_campaign(
    conn: Any,
    base_rows: list[dict[str, Any]],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> list[dict[str, Any]]:
    config, _ = load_special_cards_config()
    promotion_definition, _ = parse_promotion_definition(config, month)
    incentive_campaign = await get_incentive_campaign(conn, month)
    incentive_codes = list(incentive_campaign.get("item_codes") or incentive_campaign.get("reward_map", {}).keys()) if incentive_campaign else None
    promotion_codes = (
        promotion_definition["item_codes"] if promotion_definition is not None else []
    )
    if not promotion_codes and not incentive_codes:
        for row in base_rows:
            row["promo_qty"] = 0
            row["incentive_qty"] = 0
        return base_rows

    metric_params, metric_positions = build_scoped_params(
        [month, promotion_codes or [], incentive_codes or []],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )

    metric_query_clauses = _scope_clauses(
        metric_positions,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
        month_alias="agg.import_month",
        month_position=1,
    )
    metric_clauses = ["agg.import_month = $1", *metric_query_clauses]
    metric_rows = await conn.fetch(
        f"""
        SELECT
            agg.import_month,
            {_store_field("regional", current_scope)} AS regional,
            {_store_field("asm", current_scope)} AS asm,
            COALESCE(
                SUM(
                    CASE
                        WHEN cardinality($2::TEXT[]) > 0
                             AND agg.item_code = ANY($2::TEXT[])
                        THEN agg.positive_quantity
                        ELSE 0
                    END
                ),
                0
            ) AS promo_qty,
            COALESCE(
                SUM(
                    CASE
                        WHEN cardinality($3::TEXT[]) > 0
                             AND agg.item_code = ANY($3::TEXT[])
                        THEN agg.positive_quantity
                        ELSE 0
                    END
                ),
                0
            ) AS incentive_qty
        FROM reporting_item_month agg
        {_scope_join(current_scope)}
        WHERE {" AND ".join(metric_clauses)}
        GROUP BY agg.import_month, {_store_field("regional", current_scope)}, {_store_field("asm", current_scope)}
        """,
        *metric_params,
    )
    campaign_metrics = {
        (str(row["import_month"]), str(row["regional"]), str(row["asm"])): dict(row)
        for row in metric_rows
    }
    for row in base_rows:
        metrics = campaign_metrics.get(
            (str(row["import_month"]), str(row["regional"]), str(row["asm"]))
        )
        row["promo_qty"] = int(metrics["promo_qty"]) if metrics else 0
        row["incentive_qty"] = int(metrics["incentive_qty"]) if metrics else 0
    return base_rows

async def _fetch_asm_stats(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> list[dict[str, Any]]:
    base_rows = await _fetch_asm_base_rows(
        conn, month, firma, regional, asm, site_code, agent,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
    if not base_rows:
        return base_rows
    return await _enrich_asm_campaign(
        conn, base_rows, month, firma, regional, asm, site_code, agent,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
