"""Query object for the multi-dimensional Retail export report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from retail_filters import distribution_location_clause


DATASET_FIELDS = {
    "agents": [
        ("agent", "agg.agent"), ("site_code", "agg.site_code"),
        ("locatie", "s.locatie"), ("firma", "s.firma"),
        ("regional", "s.regional"), ("asm", "s.asm"),
    ],
    "stores": [
        ("site_code", "agg.site_code"), ("locatie", "s.locatie"),
        ("firma", "s.firma"), ("regional", "s.regional"), ("asm", "s.asm"),
    ],
    "regionals": [("regional", "s.regional")],
    "asms": [("regional", "s.regional"), ("asm", "s.asm")],
}
QUERY_TEMPLATE = Path(__file__).with_name("sql").joinpath("export_report_rows.sql").read_text(encoding="utf-8")


def _scope_parameters(
    *,
    months: list[str],
    filters: dict[str, list[str]],
    include_closed_stores: bool,
    selected_days: list[int] | None,
    campaign_codes_by_month: dict[str, list[str]] | None,
    campaign_exclusions_by_month: dict[str, dict[tuple[str, str, str], int]] | None,
    include_campaign_metrics: bool,
    limit: int | None,
) -> tuple[list[Any], list[str], list[str], dict[str, Any]]:
    params: list[Any] = [months]
    clauses = ["agg.import_month = ANY($1::TEXT[])", distribution_location_clause("s")]
    historical = [
        "hms.import_month = ANY($1::TEXT[])",
        "COALESCE(s.locatie, hms.source_store_name, '') NOT ILIKE 'TR %'",
    ]
    if not include_closed_stores:
        clauses.append("s.is_active = TRUE")
    columns = {
        "firma": "s.firma", "regional": "s.regional", "asm": "s.asm",
        "site_code": "agg.site_code", "agent": "agg.agent",
    }
    historical_columns = {
        "firma": "COALESCE(s.firma, hms.firma)",
        "regional": "COALESCE(s.regional, hms.source_manager)",
        "asm": "COALESCE(s.asm, hms.source_manager)", "site_code": "hms.site_code",
    }
    for key, column in columns.items():
        values = [value for value in filters.get(key, []) if value]
        if values:
            params.append(values)
            clauses.append(f"{column} = ANY(${len(params)}::TEXT[])")
            if key in historical_columns:
                historical.append(f"{historical_columns[key]} = ANY(${len(params)}::TEXT[])")
    if selected_days:
        params.append(selected_days)
        clauses.append(f"EXTRACT(DAY FROM agg.sale_date)::INT = ANY(${len(params)}::INT[])")
    promo_pairs = [
        (month, code)
        for month, codes in sorted((campaign_codes_by_month or {}).items())
        for code in codes
    ]
    params.extend([[month for month, _ in promo_pairs], [code for _, code in promo_pairs]])
    markers: dict[str, Any] = {
        "promo_months_param": len(params) - 1, "promo_codes_param": len(params),
    }
    exclusions = [
        (month, site, agent, code, units)
        for month, month_rows in sorted((campaign_exclusions_by_month or {}).items())
        for (site, agent, code), units in sorted(month_rows.items()) if units > 0
    ]
    for index in range(5):
        params.append([row[index] for row in exclusions])
    markers.update({
        "excluded_months_param": len(params) - 4, "excluded_sites_param": len(params) - 3,
        "excluded_agents_param": len(params) - 2, "excluded_codes_param": len(params) - 1,
        "excluded_units_param": len(params),
    })
    params.append(include_campaign_metrics)
    markers["campaign_metrics_param"] = len(params)
    if limit is not None and limit < 1:
        raise ValueError("Export row limit must be positive")
    if limit is not None:
        params.append(limit)
        markers["limit_clause"] = f" LIMIT ${len(params)}"
    else:
        markers["limit_clause"] = ""
    return params, clauses, historical, markers


def _dimension_fragments(
    dataset: str,
    period: str | None,
    filters: dict[str, list[str]],
    selected_days: list[int] | None,
    clauses: list[str],
    historical_clauses: list[str],
) -> dict[str, Any]:
    if dataset not in DATASET_FIELDS:
        raise ValueError(f"Unsupported export dataset: {dataset}")
    if period not in (None, "month", "day"):
        raise ValueError(f"Unsupported export period: {period}")
    fields = DATASET_FIELDS[dataset]
    aliases = [alias for alias, _ in fields]
    historical_exprs = {
        "agent": "NULL::TEXT", "site_code": "hms.site_code",
        "locatie": "COALESCE(s.locatie, hms.source_store_name, hms.site_code)",
        "firma": "COALESCE(s.firma, hms.firma, '')",
        "regional": "COALESCE(s.regional, hms.source_manager, '')",
        "asm": "COALESCE(s.asm, hms.source_manager, '')",
    }
    period_expr = {None: "NULL::TEXT", "month": "agg.import_month", "day": "agg.sale_date::TEXT"}[period]
    historical_period = {None: "NULL::TEXT", "month": "hms.import_month", "day": "NULL::TEXT"}[period]
    historical_union = ""
    if dataset != "agents" and period != "day" and not selected_days and not filters.get("agent"):
        historical_fields = ",\n                        ".join(
            f"{historical_exprs[alias]} AS {alias}" for alias in aliases
        )
        historical_union = f"""
                    UNION ALL
                    SELECT {historical_fields}, {historical_period} AS period_key,
                        hms.import_month, NULL::DATE AS sale_date, hms.site_code AS raw_site_code,
                        NULL::TEXT AS raw_agent, hms.total_value AS total_sales,
                        hms.total_qty AS total_quantity, 0::INT AS receipt_count,
                        0::INT AS receipt_2plus_count, 0::INT AS focus_quantity
                    FROM historical_monthly_sales hms
                    LEFT JOIN stores s ON s.site_code = hms.site_code
                    WHERE {" AND ".join(historical_clauses)}
                      AND NOT EXISTS (
                          SELECT 1 FROM reporting_agent_day rad
                          WHERE rad.import_month = hms.import_month AND rad.site_code = hms.site_code
                      )
        """
    return {
        "fields": fields,
        "field_select": ",\n                ".join(f"{expr} AS {alias}" for alias, expr in fields),
        "field_aliases": ", ".join(aliases),
        "field_alias_select": ",\n            ".join(aliases),
        "field_alias_select_from_agg": ",\n                        ".join(f"agg.{alias} AS {alias}" for alias in aliases),
        "period_expr": period_expr, "historical_union": historical_union,
        "join_conditions": " AND ".join(f"t.{alias} IS NOT DISTINCT FROM b.{alias}" for alias in aliases),
        "target_group": ", ".join([*(f"agg.{alias}" for alias in aliases), "agg.period_key"]),
        "period_select": ", agg.import_month AS target_month" if period == "month" else "",
        "period_group": ", agg.import_month" if period == "month" else "",
        "clauses_sql": " AND ".join(clauses),
        "targets_source": "effective_agent_targets" if dataset == "agents" else "store_targets_scoped",
        "campaign_join_conditions": " AND ".join(
            f"c.{alias} IS NOT DISTINCT FROM b.{alias}" for alias in aliases
        ),
        "order_fields": ", ".join(f"b.{alias}" for alias in aliases),
    }


def _campaign_fragments(
    dataset: str, period: str | None, filters: dict[str, list[str]],
) -> dict[str, str]:
    has_agent = dataset == "agents" or bool(filters.get("agent")) or period == "day"
    fragments = {
        "campaign_source": "reporting_item_day agg",
        "campaign_product_agent_select": "raw_agent" if has_agent else "NULL::TEXT",
        "campaign_product_agent_group": ", raw_agent" if has_agent else "",
    }
    if period == "day":
        fragments.update({
            "campaign_excluded_expr": "0", "campaign_reported_expr": "0",
            "campaign_excluded_join": "",
            "promo_sales_expr": "SUM(total_sales) FILTER (WHERE is_promo)",
            "promo_quantity_expr": "SUM(net_quantity) FILTER (WHERE is_promo)",
        })
        return fragments
    partition = (
        "agg.import_month, agg.site_code, agg.agent, agg.item_code"
        if has_agent else "agg.import_month, agg.site_code, agg.item_code"
    )
    order = "agg.sale_date" if has_agent else "agg.sale_date, agg.agent"
    exclusion_alias = "eai" if has_agent else "esi"
    fragments.update({
        "campaign_excluded_expr": f"""
                LEAST(GREATEST(agg.net_quantity, 0), GREATEST(0,
                    COALESCE({exclusion_alias}.units, 0) - COALESCE(
                        SUM(GREATEST(agg.net_quantity, 0)) OVER (
                            PARTITION BY {partition} ORDER BY {order}
                            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                        ), 0)))
        """,
        "campaign_reported_expr": f"""
                CASE WHEN ROW_NUMBER() OVER (PARTITION BY {partition} ORDER BY {order}) = 1
                    THEN COALESCE({exclusion_alias}.units, 0) ELSE 0 END
        """,
        "campaign_excluded_join": (
            "LEFT JOIN excluded_agent_item eai ON eai.import_month = agg.import_month "
            "AND eai.site_code = agg.site_code AND eai.agent = agg.agent AND eai.item_code = agg.item_code"
            if has_agent else
            "LEFT JOIN excluded_site_item esi ON esi.import_month = agg.import_month "
            "AND esi.site_code = agg.site_code AND esi.item_code = agg.item_code"
        ),
        "promo_sales_expr": """
                SUM(CASE WHEN is_promo AND net_quantity > 0
                    THEN promo_excluded_quantity::NUMERIC * total_sales / net_quantity ELSE 0 END)
        """,
        "promo_quantity_expr": "SUM(promo_reported_quantity)",
    })
    return fragments


def build_report_rows_query(
    *, dataset: str, months: list[str], filters: dict[str, list[str]],
    include_closed_stores: bool,
    campaign_codes_by_month: dict[str, list[str]] | None,
    campaign_exclusions_by_month: dict[str, dict[tuple[str, str, str], int]] | None,
    selected_days: list[int] | None, period: str | None,
    include_campaign_metrics: bool, limit: int | None, include_total_count: bool,
) -> tuple[str, list[Any]]:
    params, clauses, historical, markers = _scope_parameters(
        months=months, filters=filters, include_closed_stores=include_closed_stores,
        selected_days=selected_days, campaign_codes_by_month=campaign_codes_by_month,
        campaign_exclusions_by_month=campaign_exclusions_by_month,
        include_campaign_metrics=include_campaign_metrics, limit=limit,
    )
    fragments = _dimension_fragments(dataset, period, filters, selected_days, clauses, historical)
    fragments.update(_campaign_fragments(dataset, period, filters))
    fragments.update(markers)
    fragments["total_count_select"] = ", COUNT(*) OVER() AS total_count" if include_total_count else ""
    return QUERY_TEMPLATE.format_map(fragments), params
