"""Heavy lifting for dashboard: stats + mix + period comparison + promo/incentive summary."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

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
from services.filters import build_scoped_params, scoped_clauses
from services.forecast import business_forecast_factor_ctes
from services.incentive_db import get_incentive_campaign
from services.receipt_identity import canonical_receipt_identity_sql


def apply_current_promo_metrics(
    rows: list[dict[str, Any]],
    campaign_context: CampaignContext,
    *,
    level: Literal["agent", "store", "regional"],
    site_regionals: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Attach official promo units and discount value to dashboard rows."""
    qty_by_key: dict[Any, int] = {}
    value_by_key: dict[Any, Decimal] = {}

    for (site, agent_name, item), units in campaign_context.promo_excluded_units.items():
        if level == "agent":
            key: Any = (site, agent_name)
        elif level == "store":
            key = site
        else:
            key = (site_regionals or {}).get(site)
            if key is None:
                continue
        qty_by_key[key] = qty_by_key.get(key, 0) + units
        value_key = (site, agent_name, item)
        value_by_key[key] = (
            value_by_key.get(key, Decimal("0"))
            + campaign_context.promo_discount_values.get(value_key, Decimal("0"))
        )

    for row in rows:
        if level == "agent":
            row_key: Any = (str(row["site_code"]), str(row["agent"]))
        elif level == "store":
            row_key = str(row["site_code"])
        else:
            row_key = str(row["regional"])
        row["promo_qty"] = qty_by_key.get(row_key, 0)
        row["promo_discount_value"] = value_by_key.get(row_key, Decimal("0"))
    return rows


def _scope_join(current_scope: bool, source_alias: str = "agg") -> str:
    return f"JOIN stores s ON s.site_code = {source_alias}.site_code" if current_scope else ""


def _scope_clauses(
    positions: dict[str, int],
    *,
    current_scope: bool,
    include_closed_stores: bool,
    source_alias: str = "agg",
    month_alias: str | None = None,
    month_position: int | None = None,
) -> list[str]:
    clauses = scoped_clauses(
        positions,
        site_alias=source_alias,
        store_alias="s" if current_scope else source_alias,
        agent_alias=source_alias,
        month_alias=month_alias,
        month_position=month_position,
    )
    if current_scope:
        clauses = _expand_current_manager_scope(clauses, positions)
    if current_scope and not include_closed_stores:
        clauses.append("s.is_active = true")
    return clauses


def _store_field(field: str, current_scope: bool, source_alias: str = "agg") -> str:
    return f"s.{field}" if current_scope else f"{source_alias}.{field}"


async def _fetch_store_stats_rows(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
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
        f"""
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
        """,
        *params,
    )


async def _enrich_store_stats_with_campaign(
    conn: Any,
    base_rows: list[dict[str, Any]],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
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


async def _fetch_agent_stats_rows(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
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
        f"""
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
        """,
        *params,
    )

    base_rows = [dict(row) for row in rows]
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


async def _fetch_regional_stats(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
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
        f"""
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
        """,
        *params,
    )

    base_rows = [dict(row) for row in rows]
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
            row.pop("import_month", None)
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
        row.pop("import_month", None)
    return base_rows


async def _fetch_asm_stats(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
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
            row.pop("import_month", None)
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
        row.pop("import_month", None)
    return base_rows


async def _fetch_period_comparison(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    cutoff_day: int | None = None,
    target_metric: str = "sales",
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> PeriodComparisonPayload:
    if cutoff_day is None:
        cutoff_day = await _fetch_period_comparison_cutoff_day(conn, month)

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

    previous_month = _shift_month(month, -1)
    year_over_year_month = _shift_month(month, -12)
    periods = [
        ("Curenta", month),
        ("Luna trecuta", previous_month),
        ("Anul trecut", year_over_year_month),
    ]
    rows: list[PeriodComparisonPoint] = []

    for label, period_month in periods:
        start_date, end_date, day_range = _month_day_range(period_month, cutoff_day)
        is_current_period = period_month == month
        params, positions = build_scoped_params(
            [period_month, start_date, end_date],
            # Historical columns follow the current-store cohort. Applying
            # historical ownership again would drop stores moved between RMs.
            firma=firma if is_current_period else None,
            regional=regional if is_current_period else None,
            asm=asm if is_current_period else None,
            site_code=site_code if is_current_period else None,
            agent=agent,
        )

        query_clauses = _scope_clauses(
            positions,
            current_scope=current_scope and is_current_period,
            include_closed_stores=include_closed_stores,
        )
        cartela_query_clauses = scoped_clauses(
            positions,
            site_alias="c",
            store_alias="cs",
            agent_alias="c",
        )
        if current_scope and is_current_period and not include_closed_stores:
            cartela_query_clauses.append("cs.is_active = true")
        if not is_current_period:
            store_pos = len(params) + 1
            params.append(active_store_codes)
            query_clauses.append(f"agg.site_code = ANY(${store_pos}::TEXT[])")
            cartela_query_clauses.append(f"c.site_code = ANY(${store_pos}::TEXT[])")
        clauses = [
            "agg.import_month = $1",
            "agg.sale_date BETWEEN $2 AND $3",
            *query_clauses,
        ]
        cartela_clauses = [
            "c.import_month = $1",
            "c.sale_date BETWEEN $2 AND $3",
            *cartela_query_clauses,
        ]
        row = await conn.fetchrow(
            f"""
            WITH filtered_days AS (
                SELECT *
                FROM reporting_agent_day agg
                {_scope_join(current_scope and is_current_period)}
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
                ROUND(
                    COALESCE(SUM(fd.receipt_2plus_count), 0) * 100.0
                    / NULLIF(COALESCE(SUM(fd.receipt_count), 0), 0),
                    2
                ) AS proc_bon2acc,
                ROUND(
                    COALESCE(SUM(fd.focus_quantity), 0) * 100.0
                    / NULLIF(COALESCE(SUM(fd.total_quantity), 0), 0),
                    2
                ) AS prc_focus_acc_qty
            FROM cartele_summary cs
            LEFT JOIN filtered_days fd ON true
            """,
            *params,
        )
        rows.append(
            PeriodComparisonPoint(
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
        )

    return PeriodComparisonPayload(
        current=rows[0],
        previous=rows[1],
        year_over_year=rows[2],
    )


async def _fetch_daily_last_year_for_current_cohort(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
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


async def _fetch_period_comparison_cutoff_day(conn: Any, month: str) -> int:
    row = await conn.fetchrow(
        """
        WITH month_meta AS (
            SELECT BOOL_OR(is_month_final) AS is_final
            FROM import_snapshots
            WHERE import_month = $1
              AND status = 'completed'
        ),
        last_sale AS (
            SELECT EXTRACT(DAY FROM MAX(sale_date))::INT AS last_sale_day
            FROM reporting_agent_day
            WHERE import_month = $1
        )
        SELECT
            COALESCE(mm.is_final, true) AS is_final,
            ls.last_sale_day,
            EXTRACT(DAY FROM (
                date_trunc('month', to_date($1 || '-01', 'YYYY-MM-DD'))
                + INTERVAL '1 month - 1 day'
            ))::INT AS days_in_month
        FROM last_sale ls
        LEFT JOIN month_meta mm ON true
        """,
        month,
    )
    if not row:
        return 31

    days_in_month = int(row["days_in_month"] or 31)
    if row["is_final"]:
        return days_in_month

    last_sale_day = row["last_sale_day"]
    if last_sale_day:
        return max(1, min(int(last_sale_day), days_in_month))
    return days_in_month


async def _fetch_receipt_bucket_mix(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> list[ReceiptBucketItem]:
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
        f"""
        WITH filtered_month AS (
            SELECT *
            FROM reporting_agent_month agg
            {_scope_join(current_scope)}
            WHERE {" AND ".join(clauses)}
        )
        SELECT
            bucket,
            receipt_count,
            ROUND(receipt_count * 100.0 / NULLIF(SUM(receipt_count) OVER (), 0), 2) AS share_pct
        FROM (
            SELECT '1' AS bucket, COALESCE(SUM(receipt_1_count), 0)::INT AS receipt_count FROM filtered_month
            UNION ALL
            SELECT '2' AS bucket, COALESCE(SUM(receipt_2_count), 0)::INT AS receipt_count FROM filtered_month
            UNION ALL
            SELECT '3' AS bucket, COALESCE(SUM(receipt_3_count), 0)::INT AS receipt_count FROM filtered_month
            UNION ALL
            SELECT '>3' AS bucket, COALESCE(SUM(receipt_4plus_count), 0)::INT AS receipt_count FROM filtered_month
        ) buckets
        WHERE receipt_count > 0
        ORDER BY
            CASE bucket
                WHEN '1' THEN 1
                WHEN '2' THEN 2
                WHEN '3' THEN 3
                ELSE 4
            END
        """,
        *params,
    )
    return [ReceiptBucketItem(**dict(row)) for row in rows]


async def _fetch_focus_subcategory_mix(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> list[CategoryMixItem]:
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
        f"""
        WITH focus_sales AS (
            SELECT
                agg.focus_subcategory AS category,
                COALESCE(SUM(agg.total_sales), 0) AS sales_total,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS quantity_total
            FROM reporting_focus_item_month agg
            {_scope_join(current_scope)}
            WHERE {" AND ".join(clauses)}
            GROUP BY agg.focus_subcategory
        ),
        ranked AS (
            SELECT
                category,
                sales_total,
                quantity_total,
                ROW_NUMBER() OVER (ORDER BY quantity_total DESC, sales_total DESC, category ASC) AS rank_no
            FROM focus_sales
            WHERE quantity_total > 0
        ),
        grouped AS (
            SELECT
                CASE WHEN rank_no <= 5 THEN category ELSE 'Altele' END AS category,
                SUM(sales_total) AS sales_total,
                SUM(quantity_total) AS quantity_total
            FROM ranked
            GROUP BY CASE WHEN rank_no <= 5 THEN category ELSE 'Altele' END
        )
        SELECT
            category,
            sales_total,
            quantity_total,
            ROUND(quantity_total * 100.0 / NULLIF(SUM(quantity_total) OVER (), 0), 2) AS share_pct
        FROM grouped
        ORDER BY quantity_total DESC, sales_total DESC, category ASC
        """,
        *params,
    )
    return [CategoryMixItem(**dict(row)) for row in rows]


async def _fetch_brand_mix(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> list[BrandMixItem]:
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
        f"""
        WITH brand_sales AS (
            SELECT
                agg.brand_group AS brand,
                COALESCE(SUM(agg.total_sales), 0) AS sales_total,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS quantity_total
            FROM reporting_category_month agg
            {_scope_join(current_scope)}
            WHERE {" AND ".join(clauses)}
              AND LOWER(TRIM(agg.category)) IN ('stil si protectie', 'folii sticla')
            GROUP BY agg.brand_group
        )
        SELECT
            brand,
            sales_total,
            quantity_total,
            ROUND(sales_total * 100.0 / NULLIF(SUM(sales_total) OVER (), 0), 2) AS share_pct
        FROM brand_sales
        WHERE sales_total > 0 OR quantity_total > 0
        ORDER BY sales_total DESC, quantity_total DESC, brand ASC
        """,
        *params,
    )
    return [BrandMixItem(**dict(row)) for row in rows]


async def _fetch_category_mix(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> list[CategoryMixItem]:
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
        f"""
        WITH category_sales AS (
            SELECT
                agg.category,
                COALESCE(SUM(agg.total_sales), 0) AS sales_total,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS quantity_total
            FROM reporting_category_month agg
            {_scope_join(current_scope)}
            WHERE {" AND ".join(clauses)}
            GROUP BY agg.category
        ),
        ranked AS (
            SELECT
                category,
                sales_total,
                quantity_total,
                ROW_NUMBER() OVER (ORDER BY sales_total DESC, category ASC) AS rank_no
            FROM category_sales
        ),
        grouped AS (
            SELECT
                CASE WHEN rank_no <= 5 THEN category ELSE 'Altele' END AS category,
                SUM(sales_total) AS sales_total,
                SUM(quantity_total) AS quantity_total
            FROM ranked
            GROUP BY CASE WHEN rank_no <= 5 THEN category ELSE 'Altele' END
        )
        SELECT
            category,
            sales_total,
            quantity_total,
            ROUND(sales_total * 100.0 / NULLIF(SUM(sales_total) OVER (), 0), 2) AS share_pct
        FROM grouped
        ORDER BY sales_total DESC, category ASC
        """,
        *params,
    )
    return [CategoryMixItem(**dict(row)) for row in rows]
