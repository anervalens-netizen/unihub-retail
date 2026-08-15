from __future__ import annotations

from typing import Any

from retail_filters import distribution_location_clause


LEVEL_FIELDS: dict[str, list[tuple[str, str]]] = {
    "general": [],
    "asms": [("asm", "s.asm")],
    "stores": [
        ("site_code", "agg.site_code"),
        ("locatie", "s.locatie"),
        ("asm", "s.asm"),
    ],
    "agents": [
        ("agent", "agg.agent"),
        ("site_code", "agg.site_code"),
        ("locatie", "s.locatie"),
        ("asm", "s.asm"),
    ],
}

FILTER_COLUMNS = {
    "firma": "s.firma",
    "regional": "s.regional",
    "asm": "s.asm",
    "site_code": "agg.site_code",
    "agent": "agg.agent",
}


def _comparison_scope(
    months: list[str],
    filters: dict[str, list[str]],
    *,
    include_closed_stores: bool,
    selected_days: list[int] | None,
) -> tuple[list[Any], list[str]]:
    params: list[Any] = [months]
    clauses = [
        "agg.import_month = ANY($1::TEXT[])",
        distribution_location_clause("s"),
    ]
    if not include_closed_stores:
        clauses.append("s.is_active = TRUE")
    for key, column in FILTER_COLUMNS.items():
        values = [value for value in filters.get(key, []) if value]
        if values:
            params.append(values)
            clauses.append(f"{column} = ANY(${len(params)}::TEXT[])")
    if selected_days:
        params.append(selected_days)
        clauses.append(
            f"EXTRACT(DAY FROM agg.sale_date)::INT = ANY(${len(params)}::INT[])"
        )
    return params, clauses


def _comparison_campaign_params(
    params: list[Any],
    campaign_codes_by_month: dict[str, list[str]] | None,
    *,
    include_campaign_metrics: bool,
    limit: int | None,
) -> tuple[int, int, int, str]:
    promo_months: list[str] = []
    promo_codes: list[str] = []
    for month, codes in sorted((campaign_codes_by_month or {}).items()):
        for code in codes:
            promo_months.append(month)
            promo_codes.append(code)
    params.extend([promo_months, promo_codes])
    promo_months_param = len(params) - 1
    promo_codes_param = len(params)
    params.append(include_campaign_metrics)
    campaign_metrics_param = len(params)
    if limit is not None and limit < 1:
        raise ValueError("Export row limit must be positive")
    if limit is None:
        return promo_months_param, promo_codes_param, campaign_metrics_param, ""
    params.append(limit)
    return (
        promo_months_param,
        promo_codes_param,
        campaign_metrics_param,
        f" LIMIT ${len(params)}",
    )


def _comparison_field_sql(fields: list[tuple[str, str]]) -> dict[str, str]:
    field_select = ",\n                    ".join(
        f"{expr} AS {alias}" for alias, expr in fields
    )
    field_group = ", ".join(expr for _, expr in fields)
    order_prefix = ", ".join(alias for alias, _ in fields)
    return {
        "select_prefix": f"{field_select}," if field_select else "",
        "group_prefix": f"{field_group}, " if field_group else "",
        "order_clause": (
            f"{order_prefix}, day_of_month, import_month"
            if order_prefix
            else "day_of_month, import_month"
        ),
        "campaign_join": (
            " AND ".join(
                f"campaign.{alias} IS NOT DISTINCT FROM base.{alias}"
                for alias, _ in fields
            )
            or "true"
        ),
        "dimension_count_select": (
            ", ".join(alias for alias, _ in fields) or "1"
        ),
    }


def _comparison_query_sql(
    *,
    clauses: list[str],
    field_sql: dict[str, str],
    promo_months_param: int,
    promo_codes_param: int,
    campaign_metrics_param: int,
    limit_clause: str,
) -> str:
    return f"""
                WITH base AS (
                    SELECT
                        {field_sql['select_prefix']}
                        agg.import_month,
                        EXTRACT(DAY FROM agg.sale_date)::INT AS day_of_month,
                        COALESCE(SUM(agg.total_sales), 0) AS total_sales,
                        COALESCE(SUM(agg.total_quantity), 0)::INT AS total_quantity,
                        COALESCE(SUM(agg.receipt_count), 0)::INT AS total_receipts,
                        COALESCE(SUM(agg.receipt_2plus_count), 0)::INT AS receipt_2plus_count,
                        COALESCE(SUM(agg.focus_quantity), 0)::INT AS focus_quantity,
                        COUNT(DISTINCT agg.site_code)::INT AS store_count,
                        COUNT(DISTINCT agg.agent)::INT AS agent_count,
                        COUNT(DISTINCT agg.sale_date)::INT AS working_days,
                        0::NUMERIC AS target
                    FROM reporting_agent_day agg
                    JOIN stores s ON s.site_code = agg.site_code
                    WHERE {" AND ".join(clauses)}
                    GROUP BY {field_sql['group_prefix']}agg.import_month, day_of_month
                ),
                dimension_count AS (
                    SELECT COUNT(*)::INT AS total_dimensions
                    FROM (
                        SELECT DISTINCT {field_sql['dimension_count_select']}
                        FROM base
                    ) dimensions
                ),
                promo_codes AS (
                    SELECT import_month, item_code
                    FROM UNNEST(${promo_months_param}::TEXT[], ${promo_codes_param}::TEXT[]) AS t(import_month, item_code)
                ),
                campaign AS (
                    SELECT
                        {field_sql['select_prefix']}
                        agg.import_month,
                        EXTRACT(DAY FROM agg.sale_date)::INT AS day_of_month,
                        COALESCE(SUM(agg.total_sales) FILTER (WHERE ip.item_code IS NOT NULL), 0) AS incentive_sales,
                        COALESCE(SUM(agg.net_quantity) FILTER (WHERE ip.item_code IS NOT NULL), 0)::INT AS incentive_quantity,
                        COALESCE(SUM(agg.net_quantity * ip.reward_value) FILTER (WHERE ip.item_code IS NOT NULL), 0) AS incentive_bonus,
                        COALESCE(SUM(agg.total_sales) FILTER (WHERE pc.item_code IS NOT NULL), 0) AS promo_sales,
                        COALESCE(SUM(agg.net_quantity) FILTER (WHERE pc.item_code IS NOT NULL), 0)::INT AS promo_quantity
                    FROM reporting_item_day agg
                    JOIN stores s ON s.site_code = agg.site_code
                    LEFT JOIN incentive_campaigns ic ON ic.month = agg.import_month
                    LEFT JOIN incentive_products ip
                      ON ip.campaign_id = ic.id
                     AND ip.item_code = agg.item_code
                     AND agg.sale_date BETWEEN ip.valid_from AND ip.valid_to
                    LEFT JOIN promo_codes pc ON pc.import_month = agg.import_month AND pc.item_code = agg.item_code
                    WHERE {" AND ".join(clauses)}
                      AND ${campaign_metrics_param}::BOOLEAN
                      AND (ip.item_code IS NOT NULL OR pc.item_code IS NOT NULL)
                    GROUP BY {field_sql['group_prefix']}agg.import_month, day_of_month
                )
                SELECT
                    base.*,
                    COALESCE(campaign.incentive_sales, 0) AS incentive_sales,
                    COALESCE(campaign.incentive_quantity, 0)::INT AS incentive_quantity,
                    COALESCE(campaign.incentive_bonus, 0) AS incentive_bonus,
                    COALESCE(campaign.promo_sales, 0) AS promo_sales,
                    COALESCE(campaign.promo_quantity, 0)::INT AS promo_quantity,
                    dimension_count.total_dimensions AS total_dimensions
                FROM base
                CROSS JOIN dimension_count
                LEFT JOIN campaign
                    ON {field_sql['campaign_join']}
                    AND campaign.import_month = base.import_month
                    AND campaign.day_of_month = base.day_of_month
                ORDER BY {field_sql['order_clause']}{limit_clause}
                """


def build_daily_comparison_rows_query(
    *,
    level: str,
    months: list[str],
    filters: dict[str, list[str]],
    include_closed_stores: bool,
    campaign_codes_by_month: dict[str, list[str]] | None = None,
    selected_days: list[int] | None = None,
    include_campaign_metrics: bool = False,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    if level not in LEVEL_FIELDS:
        raise ValueError(f"Unsupported comparison level: {level}")
    params, clauses = _comparison_scope(
        months,
        filters,
        include_closed_stores=include_closed_stores,
        selected_days=selected_days,
    )
    month_param, code_param, metrics_param, limit_clause = (
        _comparison_campaign_params(
            params,
            campaign_codes_by_month,
            include_campaign_metrics=include_campaign_metrics,
            limit=limit,
        )
    )
    query = _comparison_query_sql(
        clauses=clauses,
        field_sql=_comparison_field_sql(LEVEL_FIELDS[level]),
        promo_months_param=month_param,
        promo_codes_param=code_param,
        campaign_metrics_param=metrics_param,
        limit_clause=limit_clause,
    )
    return query, params
