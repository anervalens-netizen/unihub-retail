from __future__ import annotations

from typing import Any

import asyncpg

from retail_filters import distribution_location_clause


class ExportsRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def fetch_report_rows(
        self,
        *,
        dataset: str,
        months: list[str],
        filters: dict[str, list[str]],
        include_closed_stores: bool,
        period: str | None = None,
    ) -> list[asyncpg.Record]:
        dataset_fields = {
            "agents": [
                ("agent", "agg.agent"),
                ("site_code", "agg.site_code"),
                ("locatie", "s.locatie"),
                ("firma", "s.firma"),
                ("regional", "s.regional"),
                ("asm", "s.asm"),
            ],
            "stores": [
                ("site_code", "agg.site_code"),
                ("locatie", "s.locatie"),
                ("firma", "s.firma"),
                ("regional", "s.regional"),
                ("asm", "s.asm"),
            ],
            "regionals": [
                ("regional", "s.regional"),
            ],
            "asms": [
                ("regional", "s.regional"),
                ("asm", "s.asm"),
            ],
        }
        if dataset not in dataset_fields:
            raise ValueError(f"Unsupported export dataset: {dataset}")
        if period not in (None, "month", "day"):
            raise ValueError(f"Unsupported export period: {period}")

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

        fields = dataset_fields[dataset]
        field_select = ",\n                ".join(f"{expr} AS {alias}" for alias, expr in fields)
        field_group = ", ".join(expr for _, expr in fields)
        field_aliases = ", ".join(alias for alias, _ in fields)
        field_alias_select = ",\n            ".join(alias for alias, _ in fields)
        field_alias_select_from_agg = ",\n                        ".join(
            f"agg.{alias} AS {alias}" for alias, _ in fields
        )
        join_conditions = " AND ".join(f"t.{alias} IS NOT DISTINCT FROM b.{alias}" for alias, _ in fields)
        target_group = ", ".join([*(f"agg.{alias}" for alias, _ in fields), "agg.period_key"])
        period_expr = {
            None: "NULL::TEXT",
            "month": "agg.import_month",
            "day": "agg.sale_date::TEXT",
        }[period]
        period_select = ", agg.import_month AS target_month" if period == "month" else ""
        period_group = ", agg.import_month" if period == "month" else ""

        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH filtered AS MATERIALIZED (
                    SELECT
                        {field_select},
                        {period_expr} AS period_key,
                        agg.import_month,
                        agg.sale_date,
                        agg.site_code AS raw_site_code,
                        agg.agent AS raw_agent,
                        agg.total_sales,
                        agg.total_quantity,
                        agg.receipt_count,
                        agg.receipt_2plus_count,
                        agg.focus_quantity
                    FROM reporting_agent_day agg
                    JOIN stores s ON s.site_code = agg.site_code
                    WHERE {" AND ".join(clauses)}
                ),
                base AS (
                    SELECT
                        {field_alias_select},
                        period_key,
                        COALESCE(SUM(total_sales), 0) AS total_sales,
                        COALESCE(SUM(total_quantity), 0)::INT AS total_quantity,
                        COALESCE(SUM(receipt_count), 0)::INT AS total_receipts,
                        COALESCE(SUM(receipt_2plus_count), 0)::INT AS receipt_2plus_count,
                        COALESCE(SUM(focus_quantity), 0)::INT AS focus_quantity,
                        COUNT(DISTINCT raw_site_code)::INT AS store_count,
                        COUNT(DISTINCT raw_agent)::INT AS agent_count,
                        COUNT(DISTINCT sale_date)::INT AS working_days
                    FROM filtered
                    GROUP BY {field_aliases}, period_key
                ),
                store_agent_counts AS (
                    SELECT import_month, site_code, COUNT(DISTINCT agent)::NUMERIC AS active_agents
                    FROM reporting_agent_month
                    WHERE import_month = ANY($1::TEXT[])
                    GROUP BY import_month, site_code
                ),
                effective_agent_targets AS (
                    SELECT
                        {field_alias_select_from_agg},
                        agg.period_key AS period_key,
                        COALESCE(SUM(COALESCE(atg.target_value, stg.target_value / NULLIF(sac.active_agents, 0))), 0) AS target
                    FROM (
                        SELECT DISTINCT
                            {field_select},
                            agg.import_month,
                            agg.site_code AS raw_site_code,
                            agg.agent AS raw_agent,
                            {period_expr} AS period_key
                        FROM reporting_agent_day agg
                        JOIN stores s ON s.site_code = agg.site_code
                        WHERE {" AND ".join(clauses)}
                    ) agg
                    LEFT JOIN store_targets stg
                        ON stg.import_month = agg.import_month
                        AND stg.site_code = agg.raw_site_code
                    LEFT JOIN store_agent_counts sac
                        ON sac.import_month = agg.import_month
                        AND sac.site_code = agg.raw_site_code
                    LEFT JOIN agent_targets atg
                        ON atg.import_month = agg.import_month
                        AND atg.site_code = agg.raw_site_code
                        AND atg.agent = agg.raw_agent
                    GROUP BY {target_group}
                ),
                store_targets_scoped AS (
                    SELECT
                        {field_alias_select_from_agg},
                        agg.period_key AS period_key,
                        COALESCE(SUM(stg.target_value), 0) AS target
                    FROM (
                        SELECT DISTINCT
                            {field_select},
                            agg.import_month,
                            agg.site_code AS raw_site_code,
                            {period_expr} AS period_key
                        FROM reporting_agent_day agg
                        JOIN stores s ON s.site_code = agg.site_code
                        WHERE {" AND ".join(clauses)}
                    ) agg
                    LEFT JOIN store_targets stg
                        ON stg.import_month = agg.import_month
                        AND stg.site_code = agg.raw_site_code
                    GROUP BY {target_group}
                ),
                targets AS (
                    SELECT *
                    FROM {"effective_agent_targets" if dataset == "agents" else "store_targets_scoped"}
                )
                SELECT
                    b.*,
                    COALESCE(t.target, 0) AS target
                FROM base b
                LEFT JOIN targets t
                    ON {join_conditions}
                    AND t.period_key IS NOT DISTINCT FROM b.period_key
                ORDER BY {", ".join("b." + alias for alias, _ in fields)}, b.period_key NULLS FIRST
                """,
                *params,
            )

    async def fetch_daily_evolution_rows(
        self,
        *,
        months: list[str],
        filters: dict[str, list[str]],
        include_closed_stores: bool,
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

        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
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
                ORDER BY day_of_month ASC, agg.import_month ASC
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
    ) -> list[asyncpg.Record]:
        level_fields = {
            "general": [],
            "asms": [
                ("asm", "s.asm"),
            ],
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
        if level not in level_fields:
            raise ValueError(f"Unsupported comparison level: {level}")

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

        fields = level_fields[level]
        field_select = ",\n                    ".join(f"{expr} AS {alias}" for alias, expr in fields)
        field_group = ", ".join(expr for _, expr in fields)
        select_prefix = f"{field_select}," if field_select else ""
        group_prefix = f"{field_group}, " if field_group else ""
        order_prefix = ", ".join(alias for alias, _ in fields)
        order_clause = f"{order_prefix}, day_of_month, import_month" if order_prefix else "day_of_month, import_month"

        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT
                    {select_prefix}
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
                GROUP BY {group_prefix}agg.import_month, day_of_month
                ORDER BY {order_clause}
                """,
                *params,
            )
