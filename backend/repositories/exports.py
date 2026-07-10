from __future__ import annotations

from typing import Any

import asyncpg

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
                )
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
                ORDER BY category, subcategory, agg.item_code, agg.site_code
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
        historical_clauses = [
            "hms.import_month = ANY($1::TEXT[])",
            "COALESCE(s.locatie, hms.source_store_name, '') NOT ILIKE 'TR %'",
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
        historical_filter_columns = {
            "firma": "COALESCE(s.firma, hms.firma)",
            "regional": "COALESCE(s.regional, hms.source_manager)",
            "asm": "COALESCE(s.asm, hms.source_manager)",
            "site_code": "hms.site_code",
        }
        for key, column in filter_columns.items():
            values = [value for value in filters.get(key, []) if value]
            if values:
                params.append(values)
                clauses.append(f"{column} = ANY(${len(params)}::TEXT[])")
                historical_column = historical_filter_columns.get(key)
                if historical_column is not None:
                    historical_clauses.append(f"{historical_column} = ANY(${len(params)}::TEXT[])")
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
        excluded_months: list[str] = []
        excluded_sites: list[str] = []
        excluded_agents: list[str] = []
        excluded_codes: list[str] = []
        excluded_units: list[int] = []
        for month, month_exclusions in sorted((campaign_exclusions_by_month or {}).items()):
            for (site_code, agent, item_code), units in sorted(month_exclusions.items()):
                if units <= 0:
                    continue
                excluded_months.append(month)
                excluded_sites.append(site_code)
                excluded_agents.append(agent)
                excluded_codes.append(item_code)
                excluded_units.append(units)
        params.extend([excluded_months, excluded_sites, excluded_agents, excluded_codes, excluded_units])
        excluded_months_param = len(params) - 4
        excluded_sites_param = len(params) - 3
        excluded_agents_param = len(params) - 2
        excluded_codes_param = len(params) - 1
        excluded_units_param = len(params)

        fields = dataset_fields[dataset]
        field_select = ",\n                ".join(f"{expr} AS {alias}" for alias, expr in fields)
        historical_exprs = {
            "agent": "NULL::TEXT",
            "site_code": "hms.site_code",
            "locatie": "COALESCE(s.locatie, hms.source_store_name, hms.site_code)",
            "firma": "COALESCE(s.firma, hms.firma, '')",
            "regional": "COALESCE(s.regional, hms.source_manager, '')",
            "asm": "COALESCE(s.asm, hms.source_manager, '')",
        }
        historical_field_select = ",\n                        ".join(
            f"{historical_exprs[alias]} AS {alias}" for alias, _ in fields
        )
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
        historical_period_expr = {
            None: "NULL::TEXT",
            "month": "hms.import_month",
            "day": "NULL::TEXT",
        }[period]
        historical_union = ""
        if dataset != "agents" and period != "day" and not selected_days:
            historical_union = f"""
                    UNION ALL
                    SELECT
                        {historical_field_select},
                        {historical_period_expr} AS period_key,
                        hms.import_month,
                        NULL::DATE AS sale_date,
                        hms.site_code AS raw_site_code,
                        NULL::TEXT AS raw_agent,
                        hms.total_value AS total_sales,
                        hms.total_qty AS total_quantity,
                        0::INT AS receipt_count,
                        0::INT AS receipt_2plus_count,
                        0::INT AS focus_quantity
                    FROM historical_monthly_sales hms
                    LEFT JOIN stores s ON s.site_code = hms.site_code
                    WHERE {" AND ".join(historical_clauses)}
                      AND NOT EXISTS (
                          SELECT 1
                          FROM reporting_agent_day rad
                          WHERE rad.import_month = hms.import_month
                            AND rad.site_code = hms.site_code
                      )
            """
        period_select = ", agg.import_month AS target_month" if period == "month" else ""
        period_group = ", agg.import_month" if period == "month" else ""
        campaign_has_agent_detail = dataset == "agents" or bool(filters.get("agent")) or period == "day"
        campaign_source = "reporting_item_day agg"
        campaign_product_agent_select = "raw_agent" if campaign_has_agent_detail else "NULL::TEXT"
        campaign_product_agent_group = ", raw_agent" if campaign_has_agent_detail else ""
        if period == "day":
            campaign_excluded_expr = "0"
            campaign_reported_expr = "0"
            campaign_excluded_join = ""
            promo_sales_expr = "SUM(total_sales) FILTER (WHERE is_promo)"
            promo_quantity_expr = "SUM(net_quantity) FILTER (WHERE is_promo)"
        elif campaign_has_agent_detail:
            campaign_excluded_expr = """
                LEAST(
                    GREATEST(agg.net_quantity, 0),
                    GREATEST(
                        0,
                        COALESCE(eai.units, 0) - COALESCE(
                            SUM(GREATEST(agg.net_quantity, 0)) OVER (
                                PARTITION BY agg.import_month, agg.site_code, agg.agent, agg.item_code
                                ORDER BY agg.sale_date
                                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                            ),
                            0
                        )
                    )
                )
            """
            campaign_reported_expr = """
                CASE WHEN ROW_NUMBER() OVER (
                    PARTITION BY agg.import_month, agg.site_code, agg.agent, agg.item_code
                    ORDER BY agg.sale_date
                ) = 1 THEN COALESCE(eai.units, 0) ELSE 0 END
            """
            campaign_excluded_join = """
                LEFT JOIN excluded_agent_item eai
                        ON eai.import_month = agg.import_month
                        AND eai.site_code = agg.site_code
                        AND eai.agent = agg.agent
                        AND eai.item_code = agg.item_code
            """
        else:
            campaign_excluded_expr = """
                LEAST(
                    GREATEST(agg.net_quantity, 0),
                    GREATEST(
                        0,
                        COALESCE(esi.units, 0) - COALESCE(
                            SUM(GREATEST(agg.net_quantity, 0)) OVER (
                                PARTITION BY agg.import_month, agg.site_code, agg.item_code
                                ORDER BY agg.sale_date, agg.agent
                                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                            ),
                            0
                        )
                    )
                )
            """
            campaign_reported_expr = """
                CASE WHEN ROW_NUMBER() OVER (
                    PARTITION BY agg.import_month, agg.site_code, agg.item_code
                    ORDER BY agg.sale_date, agg.agent
                ) = 1 THEN COALESCE(esi.units, 0) ELSE 0 END
            """
            campaign_excluded_join = """
                LEFT JOIN excluded_site_item esi
                    ON esi.import_month = agg.import_month
                    AND esi.site_code = agg.site_code
                    AND esi.item_code = agg.item_code
            """

        if period != "day":
            promo_sales_expr = """
                SUM(
                    CASE
                        WHEN is_promo AND net_quantity > 0
                            THEN promo_excluded_quantity::NUMERIC * total_sales / net_quantity
                        ELSE 0
                    END
                )
            """
            promo_quantity_expr = "SUM(promo_reported_quantity)"

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
                    {historical_union}
                ),
                promo_codes AS (
                    SELECT import_month, item_code
                    FROM UNNEST(${promo_months_param}::TEXT[], ${promo_codes_param}::TEXT[]) AS t(import_month, item_code)
                ),
                excluded_units AS (
                    SELECT import_month, site_code, agent, item_code, units
                    FROM UNNEST(
                        ${excluded_months_param}::TEXT[],
                        ${excluded_sites_param}::TEXT[],
                        ${excluded_agents_param}::TEXT[],
                        ${excluded_codes_param}::TEXT[],
                        ${excluded_units_param}::INT[]
                    ) AS t(import_month, site_code, agent, item_code, units)
                ),
                excluded_site_item AS (
                    SELECT import_month, site_code, item_code, SUM(units)::INT AS units
                    FROM excluded_units
                    GROUP BY import_month, site_code, item_code
                ),
                excluded_agent_item AS (
                    SELECT import_month, site_code, agent, item_code, SUM(units)::INT AS units
                    FROM excluded_units
                    GROUP BY import_month, site_code, agent, item_code
                ),
                campaign_filtered AS MATERIALIZED (
                    SELECT
                        {field_select},
                        {period_expr} AS period_key,
                        agg.import_month,
                        agg.site_code AS raw_site_code,
                        agg.agent AS raw_agent,
                        agg.item_code,
                        agg.total_sales,
                        agg.net_quantity,
                        ip.reward_value,
                        pc.item_code IS NOT NULL AS is_promo,
                        {campaign_reported_expr} AS promo_reported_quantity,
                        {campaign_excluded_expr} AS promo_excluded_quantity
                    FROM {campaign_source}
                    JOIN stores s ON s.site_code = agg.site_code
                    LEFT JOIN incentive_campaigns ic
                        ON ic.month = agg.import_month
                    LEFT JOIN incentive_products ip
                        ON ip.campaign_id = ic.id
                        AND ip.item_code = agg.item_code
                        AND agg.sale_date BETWEEN ip.valid_from AND ip.valid_to
                    LEFT JOIN promo_codes pc
                        ON pc.import_month = agg.import_month
                        AND pc.item_code = agg.item_code
                    {campaign_excluded_join}
                    WHERE {" AND ".join(clauses)}
                      AND (ip.item_code IS NOT NULL OR pc.item_code IS NOT NULL)
                ),
                campaign_product AS (
                    SELECT
                        {field_alias_select},
                        period_key,
                        raw_site_code,
                        {campaign_product_agent_select} AS raw_agent,
                        item_code,
                        reward_value,
                        is_promo,
                        COALESCE(SUM(total_sales), 0) AS total_sales,
                        COALESCE(SUM(net_quantity), 0)::INT AS net_quantity,
                        COALESCE(SUM(promo_reported_quantity), 0)::INT AS promo_reported_quantity,
                        COALESCE(SUM(promo_excluded_quantity), 0)::INT AS promo_excluded_quantity
                    FROM campaign_filtered
                    GROUP BY
                        {field_aliases}, period_key, raw_site_code{campaign_product_agent_group},
                        item_code, reward_value, is_promo
                ),
                campaign_base AS (
                    SELECT
                        {field_alias_select},
                        period_key,
                        COALESCE(SUM(
                            CASE
                                WHEN reward_value IS NOT NULL AND net_quantity > 0 THEN
                                    GREATEST(0, net_quantity - promo_excluded_quantity)::NUMERIC
                                    * total_sales / net_quantity
                                ELSE 0
                            END
                        ), 0) AS incentive_sales,
                        COALESCE(SUM(
                            GREATEST(0, net_quantity - promo_excluded_quantity)
                        ) FILTER (WHERE reward_value IS NOT NULL), 0)::INT AS incentive_quantity,
                        COALESCE(SUM(
                            GREATEST(0, net_quantity - promo_excluded_quantity) * reward_value
                        ) FILTER (WHERE reward_value IS NOT NULL), 0) AS incentive_bonus,
                        COALESCE({promo_sales_expr}, 0) AS promo_sales,
                        COALESCE({promo_quantity_expr}, 0)::INT AS promo_quantity
                    FROM campaign_product
                    GROUP BY {field_aliases}, period_key
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
                    COALESCE(t.target, 0) AS target,
                    COALESCE(c.incentive_sales, 0) AS incentive_sales,
                    COALESCE(c.incentive_quantity, 0)::INT AS incentive_quantity,
                    COALESCE(c.incentive_bonus, 0) AS incentive_bonus,
                    COALESCE(c.promo_sales, 0) AS promo_sales,
                    COALESCE(c.promo_quantity, 0)::INT AS promo_quantity
                FROM base b
                LEFT JOIN targets t
                    ON {join_conditions}
                    AND t.period_key IS NOT DISTINCT FROM b.period_key
                LEFT JOIN campaign_base c
                    ON {" AND ".join(f"c.{alias} IS NOT DISTINCT FROM b.{alias}" for alias, _ in fields)}
                    AND c.period_key IS NOT DISTINCT FROM b.period_key
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
        campaign_codes_by_month: dict[str, list[str]] | None = None,
        campaign_exclusions_by_month: dict[str, dict[tuple[str, str, str], int]] | None = None,
        selected_days: list[int] | None = None,
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
                ORDER BY day_of_month ASC, import_month ASC
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

        fields = level_fields[level]
        field_select = ",\n                    ".join(f"{expr} AS {alias}" for alias, expr in fields)
        field_group = ", ".join(expr for _, expr in fields)
        select_prefix = f"{field_select}," if field_select else ""
        group_prefix = f"{field_group}, " if field_group else ""
        order_prefix = ", ".join(alias for alias, _ in fields)
        order_clause = f"{order_prefix}, day_of_month, import_month" if order_prefix else "day_of_month, import_month"
        campaign_field_select = f"{field_select}," if field_select else ""
        campaign_group_prefix = f"{field_group}, " if field_group else ""
        campaign_join = (
            " AND ".join(f"campaign.{alias} IS NOT DISTINCT FROM base.{alias}" for alias, _ in fields)
            or "true"
        )

        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH base AS (
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
                ),
                promo_codes AS (
                    SELECT import_month, item_code
                    FROM UNNEST(${promo_months_param}::TEXT[], ${promo_codes_param}::TEXT[]) AS t(import_month, item_code)
                ),
                campaign AS (
                    SELECT
                        {campaign_field_select}
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
                      AND (ip.item_code IS NOT NULL OR pc.item_code IS NOT NULL)
                    GROUP BY {campaign_group_prefix}agg.import_month, day_of_month
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
                    ON {campaign_join}
                    AND campaign.import_month = base.import_month
                    AND campaign.day_of_month = base.day_of_month
                ORDER BY {order_clause}
                """,
                *params,
            )
