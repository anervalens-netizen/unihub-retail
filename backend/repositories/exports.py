from __future__ import annotations

from typing import Any

import asyncpg

from repositories.export_report_query import build_report_rows_query
from repositories.export_daily_comparison_query import (
    build_daily_comparison_rows_query,
)
from retail_filters import distribution_location_clause


class ExportsRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def fetch_incentive_product_rows(
        self,
        *,
        month: str,
        filters: dict[str, list[str]],
        include_closed_stores: bool,
        selected_days: list[int] | None = None,
        limit: int | None = None,
        include_total_count: bool = False,
    ) -> list[asyncpg.Record]:
        """Return incentive sales at the store-product grain used by Focus."""
        params: list[Any] = [month]
        clauses = [
            "agg.import_month = $1",
            distribution_location_clause("s"),
        ]
        if not include_closed_stores:
            clauses.append("s.is_active = TRUE")

        filter_columns = {
            "firma": "s.firma",
            "regional": "s.regional",
            "asm": "s.asm",
            "site_code": "agg.site_code",
            "agent": "agg.agent",
        }
        for key, column in filter_columns.items():
            values = [value for value in filters.get(key, []) if value]
            if values:
                params.append(values)
                clauses.append(f"{column} = ANY(${len(params)}::TEXT[])")
        if selected_days:
            params.append(selected_days)
            clauses.append(f"EXTRACT(DAY FROM agg.sale_date)::INT = ANY(${len(params)}::INT[])")

        item_source = "reporting_item_day"
        if limit is not None and limit < 1:
            raise ValueError("Export row limit must be positive")
        if limit is not None:
            params.append(limit)
            limit_clause = f" LIMIT ${len(params)}"
        else:
            limit_clause = ""

        report_count_cte = """
                , report_count AS (
                    SELECT COUNT(*)::INT AS total_count
                    FROM (
                        SELECT
                            import_month,
                            category,
                            subcategory,
                            item_code,
                            item_name,
                            reward_value
                        FROM product_rows
                        GROUP BY import_month, category, subcategory, item_code, item_name, reward_value
                    ) grouped_rows
                )
        """ if include_total_count else ""
        report_count_select = ", report_count.total_count AS total_count" if include_total_count else ""
        report_count_join = "CROSS JOIN report_count" if include_total_count else ""

        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH item_categories AS (
                    SELECT
                        import_month,
                        item_code,
                        COALESCE(NULLIF(TRIM(MAX(category)), ''), 'Necategorizat') AS category,
                        COALESCE(
                            NULLIF(TRIM(MAX(subcategory)), ''),
                            NULLIF(TRIM(MAX(category)), ''),
                            'Necategorizat'
                        ) AS subcategory
                    FROM sales_transactions
                    WHERE import_month = $1
                    GROUP BY import_month, item_code
                ),
                product_rows AS (
                    SELECT
                        agg.import_month,
                        agg.site_code,
                        agg.item_code,
                        COALESCE(MAX(ip.item_name), MAX(agg.item_name), agg.item_code) AS item_name,
                        COALESCE(MAX(categories.category), 'Necategorizat') AS category,
                        COALESCE(MAX(categories.subcategory), 'Necategorizat') AS subcategory,
                        MAX(ip.reward_value) AS reward_value,
                        ip.valid_from,
                        ip.valid_to,
                        COALESCE(SUM(agg.net_quantity), 0)::INT AS net_quantity,
                        COALESCE(SUM(agg.positive_quantity), 0)::INT AS positive_quantity,
                        COALESCE(SUM(agg.return_quantity), 0)::INT AS return_quantity
                    FROM {item_source} agg
                    JOIN stores s ON s.site_code = agg.site_code
                    JOIN incentive_campaigns campaign ON campaign.month = agg.import_month
                    JOIN incentive_products ip
                        ON ip.campaign_id = campaign.id
                        AND ip.item_code = agg.item_code
                        AND agg.sale_date BETWEEN ip.valid_from AND ip.valid_to
                    LEFT JOIN item_categories categories
                        ON categories.import_month = agg.import_month
                        AND categories.item_code = agg.item_code
                    WHERE {" AND ".join(clauses)}
                    GROUP BY agg.import_month, agg.site_code, agg.item_code, ip.valid_from, ip.valid_to
                )
                {report_count_cte}
                SELECT product_rows.*{report_count_select}
                FROM product_rows
                {report_count_join}
                ORDER BY category, subcategory, item_code, site_code{limit_clause}
                """,
                *params,
            )

    async def fetch_report_rows(
        self,
        *,
        dataset: str,
        months: list[str],
        filters: dict[str, list[str]],
        include_closed_stores: bool,
        campaign_codes_by_month: dict[str, list[str]] | None = None,
        campaign_exclusions_by_month: dict[str, dict[tuple[str, str, str], int]] | None = None,
        selected_days: list[int] | None = None,
        period: str | None = None,
        include_campaign_metrics: bool = True,
        limit: int | None = None,
        include_total_count: bool = False,
    ) -> list[asyncpg.Record]:
        query, params = build_report_rows_query(
            dataset=dataset, months=months, filters=filters,
            include_closed_stores=include_closed_stores,
            campaign_codes_by_month=campaign_codes_by_month,
            campaign_exclusions_by_month=campaign_exclusions_by_month,
            selected_days=selected_days, period=period,
            include_campaign_metrics=include_campaign_metrics,
            limit=limit, include_total_count=include_total_count,
        )
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *params)

    async def fetch_daily_evolution_rows(
        self,
        *,
        months: list[str],
        filters: dict[str, list[str]],
        include_closed_stores: bool,
        campaign_codes_by_month: dict[str, list[str]] | None = None,
        campaign_exclusions_by_month: dict[str, dict[tuple[str, str, str], int]] | None = None,
        selected_days: list[int] | None = None,
        include_campaign_metrics: bool = False,
        limit: int | None = None,
    ) -> list[asyncpg.Record]:
        params: list[Any] = [months]
        clauses = [
            "agg.import_month = ANY($1::TEXT[])",
            distribution_location_clause("s"),
        ]
        if not include_closed_stores:
            clauses.append("s.is_active = TRUE")

        filter_columns = {
            "firma": "s.firma",
            "regional": "s.regional",
            "asm": "s.asm",
            "site_code": "agg.site_code",
            "agent": "agg.agent",
        }
        for key, column in filter_columns.items():
            values = [value for value in filters.get(key, []) if value]
            if values:
                params.append(values)
                clauses.append(f"{column} = ANY(${len(params)}::TEXT[])")
        if selected_days:
            params.append(selected_days)
            clauses.append(f"EXTRACT(DAY FROM agg.sale_date)::INT = ANY(${len(params)}::INT[])")

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
        if limit is not None:
            params.append(limit)
            limit_clause = f" LIMIT ${len(params)}"
        else:
            limit_clause = ""

        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH base AS (
                    SELECT
                        agg.import_month,
                        agg.sale_date,
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
                    GROUP BY agg.import_month, agg.sale_date
                ),
                promo_codes AS (
                    SELECT import_month, item_code
                    FROM UNNEST(${promo_months_param}::TEXT[], ${promo_codes_param}::TEXT[]) AS t(import_month, item_code)
                ),
                campaign AS (
                    SELECT
                        agg.import_month,
                        agg.sale_date,
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
                    GROUP BY agg.import_month, agg.sale_date
                )
                SELECT
                    base.*,
                    COALESCE(campaign.incentive_sales, 0) AS incentive_sales,
                    COALESCE(campaign.incentive_quantity, 0)::INT AS incentive_quantity,
                    COALESCE(campaign.incentive_bonus, 0) AS incentive_bonus,
                    COALESCE(campaign.promo_sales, 0) AS promo_sales,
                    COALESCE(campaign.promo_quantity, 0)::INT AS promo_quantity
                FROM base
                LEFT JOIN campaign
                    ON campaign.import_month = base.import_month
                    AND campaign.sale_date = base.sale_date
                ORDER BY day_of_month ASC, import_month ASC{limit_clause}
                """,
                *params,
            )

    async def fetch_daily_comparison_rows(
        self,
        *,
        level: str,
        months: list[str],
        filters: dict[str, list[str]],
        include_closed_stores: bool,
        campaign_codes_by_month: dict[str, list[str]] | None = None,
        selected_days: list[int] | None = None,
        include_campaign_metrics: bool = False,
        limit: int | None = None,
    ) -> list[asyncpg.Record]:
        query, params = build_daily_comparison_rows_query(
            level=level,
            months=months,
            filters=filters,
            include_closed_stores=include_closed_stores,
            campaign_codes_by_month=campaign_codes_by_month,
            selected_days=selected_days,
            include_campaign_metrics=include_campaign_metrics,
            limit=limit,
        )
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *params)
