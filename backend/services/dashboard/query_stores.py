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

def _store_stats_query(
    return_receipt_identity: str,
    current_scope: bool,
    return_clauses_sql: str,
    clauses: list[str],
) -> str:
    return f"""
        WITH filtered_days AS (
            SELECT
                agg.import_month,
                agg.sale_date,
                agg.site_code,
                {_store_field("locatie", current_scope)} AS locatie,
                {_store_field("firma", current_scope)} AS firma,
                {_store_field("regional", current_scope)} AS regional,
                {_store_field("asm", current_scope)} AS asm,
                agg.agent,
                agg.total_sales,
                agg.total_quantity,
                agg.receipt_count,
                agg.receipt_2plus_count,
                agg.focus_quantity
            FROM reporting_agent_day agg
            {_scope_join(current_scope)}
            WHERE {" AND ".join(clauses)}
        ),
        {business_forecast_factor_ctes()},
        return_summary AS (
            SELECT
                st.import_month,
                st.site_code,
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
            GROUP BY st.import_month, st.site_code
        )
        SELECT
            fd.import_month,
            fd.site_code,
            fd.locatie,
            fd.firma,
            fd.regional,
            fd.asm,
            COALESCE(SUM(fd.total_sales), 0) AS total_vanzari,
            COALESCE(SUM(fd.total_quantity), 0)::INT AS qty_total,
            COALESCE(SUM(fd.receipt_count), 0)::INT AS nr_bonuri,
            COUNT(DISTINCT fd.agent)::INT AS nr_agenti,
            COUNT(DISTINCT fd.sale_date)::INT AS zile_active,
            COALESCE(MAX(stg.target_value), 0) AS target,
            CASE
                WHEN COALESCE(MAX(stg.target_value), 0) > 0
                THEN ROUND(COALESCE(SUM(fd.total_sales), 0) * 100.0 / MAX(stg.target_value), 2)
                ELSE NULL
            END AS proc_realizare_target,
            CASE
                WHEN COALESCE(MAX(stg.target_value), 0) > 0
                THEN ROUND(COALESCE(SUM(fd.total_sales), 0) * MAX(fm.forecast_factor) * 100.0 / MAX(stg.target_value), 2)
                ELSE NULL
            END AS forecast_target_pct,
            CASE
                WHEN COALESCE(SUM(fd.total_quantity), 0) > 0
                THEN ROUND(COALESCE(SUM(fd.total_sales), 0) / SUM(fd.total_quantity), 2)
                ELSE NULL
            END AS medie_produs,
            CASE
                WHEN COALESCE(SUM(fd.receipt_count), 0) > 0
                THEN ROUND(
                    COALESCE(SUM(fd.receipt_2plus_count), 0) * 100.0
                    / SUM(fd.receipt_count),
                    2
                )
                ELSE NULL
            END AS proc_bon2acc,
            CASE
                WHEN COALESCE(SUM(fd.total_quantity), 0) > 0
                THEN ROUND(
                    COALESCE(SUM(fd.focus_quantity), 0) * 100.0
                    / SUM(fd.total_quantity),
                    2
                )
                ELSE NULL
            END AS prc_focus_acc_qty,
            COALESCE(rs.return_receipt_count, 0)::INT AS return_receipt_count
        FROM filtered_days fd
        CROSS JOIN forecast_meta fm
        LEFT JOIN store_targets stg
            ON stg.import_month = fd.import_month
            AND stg.site_code = fd.site_code
        LEFT JOIN return_summary rs
            ON rs.import_month = fd.import_month
            AND rs.site_code = fd.site_code
        GROUP BY
            fd.import_month,
            fd.site_code,
            fd.locatie,
            fd.firma,
            fd.regional,
            fd.asm,
            rs.return_receipt_count
        ORDER BY proc_realizare_target DESC NULLS LAST, total_vanzari DESC, fd.locatie ASC
        """


async def _fetch_store_stats_rows(
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
    return await conn.fetch(
        _store_stats_query(
            return_receipt_identity, current_scope, return_clauses_sql, clauses
        ),
        *params,
    )


async def _enrich_store_stats_with_campaign(
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
    """Attach promo_qty and incentive_qty to each store stats row."""
    if not base_rows:
        return base_rows

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
            agg.site_code,
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
        GROUP BY agg.import_month, agg.site_code
        """,
        *metric_params,
    )
    campaign_metrics = {
        (str(row["import_month"]), str(row["site_code"])): dict(row)
        for row in metric_rows
    }
    for row in base_rows:
        metrics = campaign_metrics.get((str(row["import_month"]), str(row["site_code"])))
        row["promo_qty"] = int(metrics["promo_qty"]) if metrics else 0
        row["incentive_qty"] = int(metrics["incentive_qty"]) if metrics else 0
    return base_rows
