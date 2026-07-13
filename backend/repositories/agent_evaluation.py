from __future__ import annotations

from business_rules import AGENT_LIFECYCLE_BASELINE_MONTH

AGENT_EVALUATION_V2_QUERY = f"""
WITH current_month AS (
    SELECT MAX(import_month) AS month
    FROM reporting_agent_month
),
current_agents AS (
    SELECT DISTINCT ON (ram.agent)
        ram.agent,
        ram.firma,
        ram.site_code,
        ram.locatie,
        ram.regional,
        ram.asm
    FROM reporting_agent_month ram
    JOIN current_month cm ON cm.month = ram.import_month
    WHERE ram.agent IS NOT NULL
      AND TRIM(ram.agent) != ''
      AND ram.agent != '-'
      AND ram.agent NOT ILIKE 'TR%'
    ORDER BY ram.agent, ram.working_days DESC, ram.total_sales DESC, ram.site_code
),
selected_months AS (
    SELECT DISTINCT ram.import_month
    FROM reporting_agent_month ram
    JOIN current_agents ca ON ca.agent = ram.agent
    WHERE ram.import_month >= '{AGENT_LIFECYCLE_BASELINE_MONTH}'
      AND ($1::TEXT IS NULL OR ram.import_month = ANY(string_to_array($1::TEXT, ',')))
      AND ($2::TEXT IS NULL OR LOWER(ca.firma) = LOWER($2))
      AND ($3::TEXT IS NULL OR ca.asm = $3 OR ca.regional = $3)
      AND ($4::TEXT IS NULL OR ca.site_code = ANY(string_to_array($4::TEXT, ',')))
),
selected_context AS (
    SELECT
        MIN(import_month) AS min_month,
        MAX(import_month) AS max_month,
        COUNT(*)::INT AS period_month_count,
        MIN(CAST(SUBSTRING(import_month, 1, 4) AS INTEGER) * 12 + CAST(SUBSTRING(import_month, 6, 2) AS INTEGER)) AS min_month_idx,
        MAX(CAST(SUBSTRING(import_month, 1, 4) AS INTEGER) * 12 + CAST(SUBSTRING(import_month, 6, 2) AS INTEGER)) AS max_month_idx
    FROM selected_months
),
sale_month_days AS (
    SELECT import_month, EXTRACT(DAY FROM MAX(sale_date))::INT AS last_sale_day
    FROM reporting_item_day
    WHERE import_month IN (SELECT import_month FROM selected_months)
    GROUP BY import_month
),
month_meta AS (
    SELECT
        sm.import_month,
        COALESCE(BOOL_AND(snap.is_month_final), true) AS is_final,
        COALESCE(smd.last_sale_day, 0) AS last_sale_day,
        EXTRACT(DAY FROM (
            date_trunc('month', to_date(sm.import_month || '-01', 'YYYY-MM-DD'))
            + INTERVAL '1 month - 1 day'
        ))::INT AS days_in_month,
        CASE
            WHEN COALESCE(BOOL_AND(snap.is_month_final), true) = false
                 AND COALESCE(smd.last_sale_day, 0) > 0
            THEN
                EXTRACT(DAY FROM (
                    date_trunc('month', to_date(sm.import_month || '-01', 'YYYY-MM-DD'))
                    + INTERVAL '1 month - 1 day'
                ))::NUMERIC
                / COALESCE(smd.last_sale_day, 1)::NUMERIC
            ELSE 1::NUMERIC
        END AS forecast_factor,
        CASE
            WHEN COALESCE(BOOL_AND(snap.is_month_final), true) = false
                 AND COALESCE(smd.last_sale_day, 0) > 0
            THEN smd.last_sale_day
            ELSE EXTRACT(DAY FROM (
                date_trunc('month', to_date(sm.import_month || '-01', 'YYYY-MM-DD'))
                + INTERVAL '1 month - 1 day'
            ))::INT
        END AS available_days
    FROM selected_months sm
    LEFT JOIN import_snapshots snap ON snap.import_month = sm.import_month
    LEFT JOIN sale_month_days smd ON smd.import_month = sm.import_month
    GROUP BY sm.import_month, smd.last_sale_day
),
location_working_days AS (
    SELECT
        rad.import_month,
        rad.site_code,
        COUNT(DISTINCT rad.sale_date)::INT AS working_days
    FROM reporting_agent_day rad
    WHERE rad.import_month IN (SELECT import_month FROM selected_months)
    GROUP BY rad.import_month, rad.site_code
),
monthly_base AS (
    SELECT
        ram.import_month AS raw_month,
        CASE
            WHEN $1::TEXT IS NULL THEN '{AGENT_LIFECYCLE_BASELINE_MONTH}..curent'
            WHEN POSITION(',' IN $1::TEXT) > 0 THEN 'custom'
            ELSE ram.import_month
        END AS month,
        ca.firma,
        ca.site_code,
        ca.locatie,
        ca.regional,
        ca.asm,
        ram.agent,
        ram.total_sales,
        ram.total_quantity,
        ram.focus_quantity,
        ram.receipt_count,
        ram.receipt_2plus_count,
        ram.working_days,
        COALESCE(st.target_value, 0) AS store_target,
        mm.forecast_factor,
        (mm.is_final = false) AS is_partial,
        mm.available_days,
        mm.days_in_month,
        COALESCE(lwd.working_days, 0) AS location_working_days
    FROM reporting_agent_month ram
    JOIN current_agents ca ON ca.agent = ram.agent
    JOIN month_meta mm ON mm.import_month = ram.import_month
    LEFT JOIN location_working_days lwd
      ON lwd.import_month = ram.import_month
     AND lwd.site_code = ram.site_code
    LEFT JOIN store_targets st
      ON st.import_month = ram.import_month
     AND st.site_code = ram.site_code
    WHERE ram.import_month >= '{AGENT_LIFECYCLE_BASELINE_MONTH}'
      AND ($1::TEXT IS NULL OR ram.import_month = ANY(string_to_array($1::TEXT, ',')))
      AND ($2::TEXT IS NULL OR LOWER(ca.firma) = LOWER($2))
      AND ($3::TEXT IS NULL OR ca.asm = $3 OR ca.regional = $3)
      AND ($4::TEXT IS NULL OR ca.site_code = ANY(string_to_array($4::TEXT, ',')))
      AND ram.agent IS NOT NULL
      AND TRIM(ram.agent) != ''
      AND ram.agent != '-'
      AND ram.agent NOT ILIKE 'TR%'
),
monthly_targets AS (
    SELECT
        *,
        CASE
            WHEN location_working_days > 0
            THEN ROUND(store_target * working_days / location_working_days, 2)
            ELSE 0
        END AS effective_target
    FROM monthly_base
),
monthly_scored AS (
    SELECT
        *,
        CASE
            WHEN effective_target > 0 THEN ROUND(total_sales * 100.0 / effective_target, 2)
        END AS month_target_pct,
        CASE
            WHEN effective_target <= 0 THEN NULL
            WHEN total_sales * 100.0 / effective_target >= 100 THEN 1::NUMERIC
            WHEN total_sales * 100.0 / effective_target >= 90 THEN 0.6667::NUMERIC
            WHEN total_sales * 100.0 / effective_target >= 80 THEN 0.3333::NUMERIC
            ELSE 0::NUMERIC
        END AS target_month_score_ratio,
        CASE
            WHEN effective_target <= 0 THEN 0::NUMERIC
            WHEN is_partial AND days_in_month > 0
            THEN LEAST(1::NUMERIC, GREATEST(0::NUMERIC, available_days::NUMERIC / days_in_month::NUMERIC))
            ELSE 1::NUMERIC
        END AS target_month_score_weight
    FROM monthly_targets
),
agent_period AS (
    SELECT
        month,
        firma,
        site_code,
        locatie,
        regional,
        asm,
        agent,
        COALESCE(SUM(total_sales), 0) AS total_sales,
        COALESCE(SUM(total_sales * forecast_factor), 0) AS forecast_sales,
        COALESCE(SUM(total_quantity), 0)::INT AS total_quantity,
        COALESCE(SUM(focus_quantity), 0)::INT AS focus_quantity,
        COALESCE(SUM(receipt_count), 0)::INT AS receipt_count,
        COALESCE(SUM(receipt_2plus_count), 0)::INT AS receipt_2plus_count,
        COALESCE(SUM(working_days), 0)::INT AS working_days,
        COALESCE(SUM(effective_target), 0) AS target_value,
        COALESCE(MAX(forecast_factor), 1) AS forecast_factor,
        BOOL_OR(is_partial) AS is_partial,
        COALESCE(SUM(available_days), 0)::INT AS available_days,
        COUNT(*)::INT AS period_month_count,
        COUNT(*) FILTER (WHERE is_partial)::INT AS partial_month_count,
        COUNT(*) FILTER (WHERE NOT is_partial)::INT AS final_month_count,
        COALESCE(SUM(
            CASE
                WHEN is_partial THEN CEIL(available_days * 0.4)::INT
                ELSE 0
            END
        ), 0)::INT AS partial_min_working_days,
        COALESCE(SUM(target_month_score_weight), 0) AS target_score_month_weight,
        CASE
            WHEN COALESCE(SUM(target_month_score_weight), 0) > 0
            THEN ROUND(
                SUM(target_month_score_ratio * target_month_score_weight)
                / SUM(target_month_score_weight),
                4
            )
        END AS target_score_ratio
    FROM monthly_scored
    GROUP BY month, firma, site_code, locatie, regional, asm, agent
),
agent_metrics AS (
    SELECT
        *,
        'allocated_store_target'::TEXT AS target_source,
        CASE WHEN target_value > 0 THEN ROUND(total_sales * 100.0 / target_value, 2) END AS target_pct,
        CASE WHEN target_value > 0 THEN ROUND(forecast_sales * 100.0 / target_value, 2) END AS target_forecast_pct,
        CASE WHEN working_days > 0 THEN ROUND(total_sales / working_days, 2) END AS daily_average,
        CASE WHEN total_quantity > 0 THEN ROUND(total_sales / total_quantity, 2) END AS value_reper,
        CASE WHEN receipt_count > 0 THEN ROUND(receipt_2plus_count * 100.0 / receipt_count, 2) END AS bonuri_pct,
        CASE WHEN total_quantity > 0 THEN ROUND(focus_quantity * 100.0 / total_quantity, 2) END AS focus_pct
    FROM agent_period
),
peer_refs AS (
    SELECT
        am.*,
        (
            SELECT ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY other.daily_average)::NUMERIC, 2)
            FROM agent_metrics other
            WHERE other.month = am.month
              AND other.site_code = am.site_code
              AND other.agent <> am.agent
              AND other.daily_average IS NOT NULL
        ) AS peer_daily_median
    FROM agent_metrics am
),
location_history AS (
    SELECT
        ram.site_code,
        ROUND(SUM(ram.total_sales) / NULLIF(SUM(ram.working_days), 0), 2) AS daily_average
    FROM reporting_agent_month ram
    CROSS JOIN selected_context sc
    WHERE sc.max_month_idx IS NOT NULL
      AND (CAST(SUBSTRING(ram.import_month, 1, 4) AS INTEGER) * 12 + CAST(SUBSTRING(ram.import_month, 6, 2) AS INTEGER))
          BETWEEN sc.max_month_idx - 3 AND sc.max_month_idx - 1
    GROUP BY ram.site_code
),
manager_history AS (
    SELECT
        c.asm,
        ROUND(SUM(ram.total_sales) / NULLIF(SUM(ram.working_days), 0), 2) AS daily_average
    FROM reporting_agent_month ram
    JOIN v_retail_current_store_org c ON c.site_code = ram.site_code
    CROSS JOIN selected_context sc
    WHERE sc.max_month_idx IS NOT NULL
      AND (CAST(SUBSTRING(ram.import_month, 1, 4) AS INTEGER) * 12 + CAST(SUBSTRING(ram.import_month, 6, 2) AS INTEGER))
          BETWEEN sc.max_month_idx - 3 AND sc.max_month_idx - 1
    GROUP BY c.asm
),
agent_history AS (
    SELECT
        ram.agent,
        ROUND(SUM(ram.total_sales) / NULLIF(SUM(ram.working_days), 0), 2) AS daily_average
    FROM reporting_agent_month ram
    CROSS JOIN selected_context sc
    WHERE sc.max_month_idx IS NOT NULL
      AND (CAST(SUBSTRING(ram.import_month, 1, 4) AS INTEGER) * 12 + CAST(SUBSTRING(ram.import_month, 6, 2) AS INTEGER))
          BETWEEN sc.max_month_idx - 3 AND sc.max_month_idx - 1
    GROUP BY ram.agent
),
premium_lines AS (
    SELECT DISTINCT
        st.id,
        CASE
            WHEN $1::TEXT IS NULL THEN '{AGENT_LIFECYCLE_BASELINE_MONTH}..curent'
            WHEN POSITION(',' IN $1::TEXT) > 0 THEN 'custom'
            ELSE st.import_month
        END AS month,
        st.agent,
        pgm.is_premium_glass AS is_premium,
        st.quantity::INT AS qty
    FROM sales_transactions st
    JOIN current_agents ca ON ca.agent = st.agent
    JOIN premium_glass_item_models pgm ON pgm.item_code = st.item_code
    WHERE st.import_month >= '{AGENT_LIFECYCLE_BASELINE_MONTH}'
      AND ($1::TEXT IS NULL OR st.import_month = ANY(string_to_array($1::TEXT, ',')))
      AND ($2::TEXT IS NULL OR LOWER(ca.firma) = LOWER($2))
      AND ($3::TEXT IS NULL OR ca.asm = $3 OR ca.regional = $3)
      AND ($4::TEXT IS NULL OR ca.site_code = ANY(string_to_array($4::TEXT, ',')))
      AND LOWER(TRIM(COALESCE(st.category, ''))) = 'folii sticla'
      AND st.quantity > 0
      AND st.agent IS NOT NULL
      AND TRIM(st.agent) != ''
      AND st.agent != '-'
      AND st.agent NOT ILIKE 'TR%'
),
premium_by_agent AS (
    SELECT
        month,
        agent,
        COALESCE(SUM(qty), 0)::INT AS glass_qty,
        COALESCE(SUM(qty) FILTER (WHERE is_premium), 0)::INT AS premium_glass_qty
    FROM premium_lines
    GROUP BY month, agent
)
SELECT
    pr.*,
    CASE
        WHEN pr.peer_daily_median IS NOT NULL THEN pr.peer_daily_median
        WHEN lh.daily_average IS NOT NULL THEN lh.daily_average
        ELSE mh.daily_average
    END AS daily_reference,
    CASE
        WHEN pr.peer_daily_median IS NOT NULL THEN 'colegi'
        WHEN lh.daily_average IS NOT NULL THEN 'istoric_locatie'
        WHEN mh.daily_average IS NOT NULL THEN 'media_manager'
        ELSE 'none'
    END AS daily_reference_type,
    CASE
        WHEN COALESCE(
            pr.peer_daily_median,
            lh.daily_average,
            mh.daily_average
        ) > 0
        THEN ROUND(
            pr.daily_average * 100.0 / COALESCE(
                pr.peer_daily_median,
                lh.daily_average,
                mh.daily_average
            ),
            2
        )
    END AS daily_vs_reference_pct,
    COALESCE(pba.glass_qty, 0)::INT AS glass_qty,
    COALESCE(pba.premium_glass_qty, 0)::INT AS premium_glass_qty,
    CASE
        WHEN COALESCE(pba.glass_qty, 0) > 0
        THEN ROUND(COALESCE(pba.premium_glass_qty, 0) * 100.0 / pba.glass_qty, 2)
    END AS premium_glass_pct,
    CASE
        WHEN ah.daily_average > 0 AND pr.daily_average IS NOT NULL
        THEN ROUND((pr.daily_average - ah.daily_average) * 100.0 / ah.daily_average, 2)
    END AS trend_daily_pct
FROM peer_refs pr
LEFT JOIN location_history lh ON lh.site_code = pr.site_code
LEFT JOIN manager_history mh ON mh.asm = pr.asm
LEFT JOIN agent_history ah ON ah.agent = pr.agent
LEFT JOIN premium_by_agent pba
  ON pba.month = pr.month
 AND pba.agent = pr.agent
ORDER BY pr.is_partial DESC, pr.asm, pr.locatie, pr.total_sales DESC, pr.agent
"""


AGENT_EVALUATION_OPTIONS_QUERY = f"""
WITH current_month AS (
    SELECT MAX(import_month) AS month
    FROM reporting_agent_month
),
current_agents AS (
    SELECT DISTINCT ON (ram.agent)
        ram.agent,
        ram.firma,
        ram.regional,
        ram.asm,
        ram.site_code,
        ram.locatie
    FROM reporting_agent_month ram
    JOIN current_month cm ON cm.month = ram.import_month
    WHERE ram.agent IS NOT NULL
      AND TRIM(ram.agent) != ''
      AND ram.agent != '-'
      AND ram.agent NOT ILIKE 'TR%'
    ORDER BY ram.agent, ram.working_days DESC, ram.total_sales DESC, ram.site_code
),
scoped AS (
    SELECT DISTINCT ram.import_month AS month, ca.firma, ca.regional, ca.asm, ca.site_code, ca.locatie
    FROM reporting_agent_month ram
    JOIN current_agents ca ON ca.agent = ram.agent
    WHERE ram.import_month >= '{AGENT_LIFECYCLE_BASELINE_MONTH}'
)
SELECT 'month' AS type, month AS value, month AS label FROM scoped
UNION
SELECT 'firma' AS type, firma AS value, firma AS label FROM scoped WHERE firma IS NOT NULL AND TRIM(firma) != ''
UNION
SELECT 'asm' AS type, asm AS value, asm AS label FROM scoped WHERE asm IS NOT NULL AND TRIM(asm) != ''
UNION
SELECT 'store' AS type, site_code AS value, locatie || ' (' || site_code || ')' AS label
FROM scoped
WHERE ($1::TEXT IS NULL OR LOWER(firma) = LOWER($1))
  AND ($2::TEXT IS NULL OR asm = $2 OR regional = $2)
ORDER BY type, label
"""
