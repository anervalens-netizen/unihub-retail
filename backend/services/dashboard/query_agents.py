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

def _agent_base_query(
    return_receipt_identity: str,
    current_scope: bool,
    return_clauses_sql: str,
    agent_clauses: list[str],
) -> str:
    return f"""
        WITH store_agent_counts AS (
            SELECT
                import_month,
                site_code,
                COUNT(*)::INT AS active_agents
            FROM reporting_agent_month
            WHERE import_month = $1
            GROUP BY import_month, site_code
        ),
        return_summary AS (
            SELECT
                st.import_month,
                st.site_code,
                st.agent,
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
            GROUP BY st.import_month, st.site_code, st.agent
        ),
        agent_base AS (
            SELECT
                agg.import_month,
                agg.site_code,
                {_store_field("locatie", current_scope)} AS locatie,
                {_store_field("firma", current_scope)} AS firma,
                {_store_field("regional", current_scope)} AS regional,
                {_store_field("asm", current_scope)} AS asm,
                {"s.is_active" if current_scope else "true"} AS is_active,
                agg.agent,
                agg.total_sales,
                agg.total_quantity,
                agg.focus_quantity,
                agg.receipt_count,
                agg.receipt_2plus_count,
                agg.working_days,
                COALESCE(
                    atg.target_value,
                    CASE
                        WHEN sac.active_agents > 0 THEN ROUND(stg.target_value / sac.active_agents, 2)
                        ELSE NULL
                    END
                ) AS effective_target
            FROM reporting_agent_month agg
            {_scope_join(current_scope)}
            LEFT JOIN store_targets stg
                ON stg.import_month = agg.import_month
                AND stg.site_code = agg.site_code
            LEFT JOIN store_agent_counts sac
                ON sac.import_month = agg.import_month
                AND sac.site_code = agg.site_code
            LEFT JOIN agent_targets atg
                ON atg.import_month = agg.import_month
                AND atg.site_code = agg.site_code
                AND atg.agent = agg.agent
        )
        SELECT
            agg.import_month,
            agg.agent,
            agg.site_code,
            agg.locatie,
            agg.firma,
            agg.regional,
            agg.asm,
            agg.total_quantity AS acc_qty_realizat,
            agg.receipt_count AS nr_bonuri,
            agg.receipt_2plus_count AS nr_bon2acc,
            CASE
                WHEN agg.receipt_count > 0
                THEN ROUND(agg.receipt_2plus_count * 100.0 / agg.receipt_count, 2)
                ELSE NULL
            END AS proc_bon2acc,
            agg.total_sales AS total_vanzari,
            agg.working_days AS zile_lucrate,
            CASE
                WHEN agg.working_days > 0
                THEN ROUND(agg.total_sales / agg.working_days, 2)
                ELSE NULL
            END AS medie_zilnica,
            CASE
                WHEN agg.total_quantity > 0
                THEN ROUND(agg.total_sales / agg.total_quantity, 2)
                ELSE NULL
            END AS medie_produs,
            agg.focus_quantity AS acc_focus_qty,
            CASE
                WHEN agg.total_quantity > 0
                THEN ROUND(agg.focus_quantity * 100.0 / agg.total_quantity, 2)
                ELSE NULL
            END AS prc_focus_acc_qty,
            agg.effective_target AS target,
            CASE
                WHEN agg.effective_target > 0
                THEN ROUND(agg.total_sales * 100.0 / agg.effective_target, 2)
                ELSE NULL
            END AS proc_realizare_target,
            COALESCE(rs.return_receipt_count, 0)::INT AS return_receipt_count
        FROM agent_base agg
        LEFT JOIN return_summary rs
            ON rs.import_month = agg.import_month
            AND rs.site_code = agg.site_code
            AND rs.agent = agg.agent
        WHERE {" AND ".join(agent_clauses)}
        ORDER BY agg.total_sales DESC, agg.agent ASC
        """


async def _fetch_agent_base_rows(
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
    agent_clauses = _scope_clauses(
        positions,
        current_scope=False,
        include_closed_stores=include_closed_stores,
        month_alias="agg.import_month",
        month_position=1,
    )
    if current_scope and not include_closed_stores:
        agent_clauses.append("agg.is_active = true")
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
        _agent_base_query(
            return_receipt_identity, current_scope, return_clauses_sql, agent_clauses
        ),
        *params,
    )

    base_rows = [dict(row) for row in rows]
    if not base_rows:
        return base_rows
    return base_rows


async def _enrich_agent_campaign(
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
            agg.agent,
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
        GROUP BY agg.import_month, agg.site_code, agg.agent
        """,
        *metric_params,
    )
    campaign_metrics = {
        (str(row["import_month"]), str(row["site_code"]), str(row["agent"])): dict(row)
        for row in metric_rows
    }
    for row in base_rows:
        metrics = campaign_metrics.get(
            (str(row["import_month"]), str(row["site_code"]), str(row["agent"]))
        )
        row["promo_qty"] = int(metrics["promo_qty"]) if metrics else 0
        row["incentive_qty"] = int(metrics["incentive_qty"]) if metrics else 0
    return base_rows

async def _fetch_agent_stats_rows(
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
    base_rows = await _fetch_agent_base_rows(
        conn, month, firma, regional, asm, site_code, agent,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
    if not base_rows:
        return base_rows
    return await _enrich_agent_campaign(
        conn, base_rows, month, firma, regional, asm, site_code, agent,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
