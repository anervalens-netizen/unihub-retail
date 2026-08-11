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
                    WHERE {clauses_sql}
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
                    WHERE {clauses_sql}
                      AND ${campaign_metrics_param}::BOOLEAN
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
                        WHERE {clauses_sql}
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
                        WHERE {clauses_sql}
                    ) agg
                    LEFT JOIN store_targets stg
                        ON stg.import_month = agg.import_month
                        AND stg.site_code = agg.raw_site_code
                    GROUP BY {target_group}
                ),
                targets AS (
                    SELECT *
                    FROM {targets_source}
                )
                SELECT
                    b.*,
                    COALESCE(t.target, 0) AS target,
                    COALESCE(c.incentive_sales, 0) AS incentive_sales,
                    COALESCE(c.incentive_quantity, 0)::INT AS incentive_quantity,
                    COALESCE(c.incentive_bonus, 0) AS incentive_bonus,
                    COALESCE(c.promo_sales, 0) AS promo_sales,
                    COALESCE(c.promo_quantity, 0)::INT AS promo_quantity
                    {total_count_select}
                FROM base b
                LEFT JOIN targets t
                    ON {join_conditions}
                    AND t.period_key IS NOT DISTINCT FROM b.period_key
                LEFT JOIN campaign_base c
                    ON {campaign_join_conditions}
                    AND c.period_key IS NOT DISTINCT FROM b.period_key
                ORDER BY {order_fields}, b.period_key NULLS FIRST{limit_clause}
