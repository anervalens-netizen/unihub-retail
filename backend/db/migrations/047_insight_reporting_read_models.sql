-- Versioned, read-only Retail reporting contracts for UniHub Insight.
--
-- These views are additive: callers must choose an explicit *_v1 contract.
-- They intentionally expose only eligible authoritative sources and carry the
-- source/finality contract with every domain result.  No browser principal is
-- granted access to the underlying business tables by this migration.

CREATE OR REPLACE VIEW reporting_source_snapshot_v1 (
    domain,
    period,
    source,
    source_generation,
    authority,
    authority_head,
    contract_version,
    rule_version,
    status,
    as_of,
    cutoff,
    is_final,
    coverage_numerator,
    coverage_denominator,
    produced_at,
    warnings
)
WITH (security_barrier = true)
AS
WITH selected_sales_snapshot AS (
    SELECT
        snapshot.*,
        head.snapshot_id AS head_snapshot_id,
        head.revision AS head_revision,
        head.updated_at AS head_updated_at,
        ROW_NUMBER() OVER (
            PARTITION BY snapshot.import_month
            ORDER BY
                (head.snapshot_id IS NOT NULL) DESC,
                snapshot.promoted_at DESC NULLS LAST,
                snapshot.finished_at DESC NULLS LAST,
                snapshot.id DESC
        ) AS selection_rank
    FROM import_snapshots AS snapshot
    LEFT JOIN sales_generation_heads AS head
      ON head.import_month = snapshot.import_month
     AND head.snapshot_id = snapshot.id
    WHERE snapshot.status = 'completed'
),
sales_source AS (
    SELECT
        'sales'::text AS domain,
        snapshot.import_month AS period,
        'import_snapshots'::text AS source,
        COALESCE(
            'sales:' || snapshot.generation_token::text,
            'snapshot:' || snapshot.id::text
        ) AS source_generation,
        CASE
            WHEN snapshot.head_snapshot_id IS NOT NULL THEN 'sales_generation_head'
            ELSE 'legacy_completed_snapshot'
        END AS authority,
        COALESCE(snapshot.head_revision::text, snapshot.id::text) AS authority_head,
        1::integer AS contract_version,
        'sales-reporting-v1'::text AS rule_version,
        CASE
            WHEN snapshot.head_snapshot_id IS NOT NULL THEN 'official'
            ELSE 'partial'
        END AS status,
        snapshot.cutoff_date AS as_of,
        snapshot.cutoff_date AS cutoff,
        snapshot.is_month_final AS is_final,
        COALESCE(snapshot.rows_imported, 0)::bigint AS coverage_numerator,
        COALESCE(snapshot.rows_in_file, snapshot.rows_imported, 0)::bigint AS coverage_denominator,
        COALESCE(
            snapshot.promoted_at,
            snapshot.finished_at,
            snapshot.head_updated_at,
            snapshot.created_at
        ) AS produced_at,
        CASE
            WHEN snapshot.head_snapshot_id IS NOT NULL THEN ARRAY[]::text[]
            ELSE ARRAY['legacy_completed_snapshot_without_sales_head']::text[]
        END AS warnings
    FROM selected_sales_snapshot AS snapshot
    WHERE snapshot.selection_rank = 1
),
eligible_compensation_person_month AS (
    SELECT
        salary.year,
        salary.month,
        salary.company_name,
        salary.person_id,
        SUM(salary.total_salary) AS total_salary
    FROM salary_records AS salary
    JOIN salary_import_batches AS batch
      ON batch.batch_id = salary.import_batch_id
     AND batch.status = 'applied'
     AND batch.approval_artifact_sha256 IS NOT NULL
    WHERE salary.person_id IS NOT NULL
    GROUP BY salary.year, salary.month, salary.company_name, salary.person_id
),
eligible_compensation_all_person_month AS (
    SELECT
        person_month.year,
        person_month.month,
        person_month.person_id,
        SUM(person_month.total_salary) AS total_salary
    FROM eligible_compensation_person_month AS person_month
    GROUP BY person_month.year, person_month.month, person_month.person_id
),
eligible_compensation_month AS (
    SELECT
        person_month.year,
        person_month.month
    FROM eligible_compensation_all_person_month AS person_month
    GROUP BY person_month.year, person_month.month
    HAVING COUNT(*) >= 3
),
eligible_compensation_source AS (
    SELECT
        compensation.year,
        compensation.month,
        (
            SELECT string_agg(
                DISTINCT salary.import_batch_id::text,
                ',' ORDER BY salary.import_batch_id::text
            )
            FROM salary_records AS salary
            JOIN salary_import_batches AS batch
              ON batch.batch_id = salary.import_batch_id
             AND batch.status = 'applied'
             AND batch.approval_artifact_sha256 IS NOT NULL
            WHERE salary.year = compensation.year
              AND salary.month = compensation.month
              AND salary.person_id IS NOT NULL
        ) AS approved_batch_ids,
        (
            SELECT MAX(batch.created_at)
            FROM salary_records AS salary
            JOIN salary_import_batches AS batch
              ON batch.batch_id = salary.import_batch_id
             AND batch.status = 'applied'
             AND batch.approval_artifact_sha256 IS NOT NULL
            WHERE salary.year = compensation.year
              AND salary.month = compensation.month
              AND salary.person_id IS NOT NULL
        ) AS produced_at
    FROM eligible_compensation_month AS compensation
),
finance_scope AS (
    SELECT
        head.company_name,
        head.period,
        head.revision,
        head.updated_at,
        generation.id AS generation_id,
        generation.promoted_at,
        scope.cutoff,
        scope.candidate_row_count
    FROM store_pnl_generation_heads AS head
    JOIN store_pnl_generations AS generation
      ON generation.id = head.active_generation_id
     AND generation.state = 'promoted'
    JOIN store_pnl_generation_scopes AS scope
      ON scope.generation_id = head.active_generation_id
     AND scope.company_name = head.company_name
     AND scope.period = head.period
),
completed_forecast_candidates AS (
    SELECT
        forecast.id,
        forecast.forecast_month,
        forecast.model_name,
        forecast.model_mode,
        forecast.variant,
        forecast.generated_at,
        COUNT(store_forecast.site_code)::bigint AS coverage,
        ROW_NUMBER() OVER (
            PARTITION BY forecast.forecast_month
            ORDER BY forecast.generated_at DESC, forecast.id DESC
        ) AS selection_rank
    FROM ai_forecast_runs AS forecast
    LEFT JOIN ai_forecast_store_month AS store_forecast
      ON store_forecast.run_id = forecast.id
    WHERE forecast.status = 'completed'
    GROUP BY
        forecast.id,
        forecast.forecast_month,
        forecast.model_name,
        forecast.model_mode,
        forecast.variant,
        forecast.generated_at
),
latest_completed_forecast AS (
    SELECT *
    FROM completed_forecast_candidates
    WHERE selection_rank = 1
),
finalized_target_candidates AS (
    SELECT
        scenario.id,
        scenario.target_month,
        scenario.revision,
        scenario.rule_set_hash,
        scenario.rule_set_snapshot,
        COALESCE(scenario.finalized_at, scenario.updated_at) AS produced_at,
        COUNT(target.site_code)::bigint AS coverage,
        BOOL_AND(target.final_target IS NOT NULL) AS has_final_values,
        ROW_NUMBER() OVER (
            PARTITION BY scenario.target_month
            ORDER BY scenario.revision DESC, scenario.finalized_at DESC NULLS LAST, scenario.id DESC
        ) AS selection_rank
    FROM target_scenarios AS scenario
    JOIN target_scenario_rows AS target
      ON target.scenario_id = scenario.id
    WHERE scenario.status = 'finalized'
    GROUP BY
        scenario.id,
        scenario.target_month,
        scenario.revision,
        scenario.rule_set_hash,
        scenario.rule_set_snapshot,
        scenario.finalized_at,
        scenario.updated_at
),
latest_finalized_target AS (
    SELECT *
    FROM finalized_target_candidates
    WHERE selection_rank = 1
),
planning_source AS (
    SELECT
        COALESCE(forecast.forecast_month, target.target_month) AS period,
        forecast.id AS forecast_id,
        forecast.model_name,
        forecast.model_mode,
        forecast.variant,
        forecast.generated_at AS forecast_produced_at,
        forecast.coverage AS forecast_coverage,
        target.id AS target_id,
        target.revision AS target_revision,
        target.rule_set_hash,
        target.rule_set_snapshot,
        target.produced_at AS target_produced_at,
        target.coverage AS target_coverage,
        target.has_final_values
    FROM latest_completed_forecast AS forecast
    FULL OUTER JOIN latest_finalized_target AS target
      ON target.target_month = forecast.forecast_month
)
SELECT
    sales.domain,
    sales.period,
    sales.source,
    sales.source_generation,
    sales.authority,
    sales.authority_head,
    sales.contract_version,
    sales.rule_version,
    sales.status,
    sales.as_of,
    sales.cutoff,
    sales.is_final,
    sales.coverage_numerator,
    sales.coverage_denominator,
    sales.produced_at,
    sales.warnings
FROM sales_source AS sales

UNION ALL

SELECT
    'campaigns'::text,
    sales.period,
    'reporting_focus_item_month'::text,
    sales.source_generation,
    sales.authority,
    sales.authority_head,
    1::integer,
    'focus-only-campaign-v1'::text,
    'partial'::text,
    sales.as_of,
    sales.cutoff,
    sales.is_final,
    sales.coverage_numerator,
    sales.coverage_denominator,
    sales.produced_at,
    sales.warnings || ARRAY['focus_only_promo_incentive_contest_and_folii_unavailable']::text[]
FROM sales_source AS sales

UNION ALL

SELECT
    'workforce'::text,
    sales.period,
    'reporting_agent_month'::text,
    sales.source_generation,
    sales.authority,
    sales.authority_head,
    1::integer,
    'sales-derived-workforce-v1'::text,
    'partial'::text,
    sales.as_of,
    sales.cutoff,
    sales.is_final,
    sales.coverage_numerator,
    sales.coverage_denominator,
    sales.produced_at,
    sales.warnings || ARRAY['sales_activity_is_not_an_official_workforce_roster']::text[]
FROM sales_source AS sales

UNION ALL

SELECT
    'compensation'::text,
    format('%s-%s', compensation.year, lpad(compensation.month::text, 2, '0')),
    'salary_import_batches'::text,
    'approved-salary-batches:' || compensation.approved_batch_ids,
    'salary_import_batch_approval'::text,
    'aggregate:' || compensation.approved_batch_ids,
    1::integer,
    'compensation-aggregate-v1'::text,
    'official'::text,
    NULL::date,
    NULL::date,
    true,
    NULL::bigint,
    NULL::bigint,
    compensation.produced_at,
    ARRAY[]::text[]
FROM eligible_compensation_source AS compensation

UNION ALL

SELECT
    'visits'::text,
    visit.month,
    'visits_snapshot'::text,
    'visits_snapshot:' || visit.month || ':' || MAX(visit.synced_at)::text,
    'legacy_asm_snapshot'::text,
    'legacy_asm'::text,
    1::integer,
    'visit-team-leader-v1'::text,
    'partial'::text,
    NULL::date,
    NULL::date,
    false,
    COALESCE(SUM(visit.total_visits), 0)::bigint,
    COALESCE(SUM(visit.total_visits), 0)::bigint,
    MAX(visit.synced_at),
    ARRAY['legacy_asm_snapshot_not_team_leader']::text[]
FROM visits_snapshot AS visit
GROUP BY visit.month

UNION ALL

SELECT
    'finance'::text,
    to_char(finance.period, 'YYYY-MM'),
    'store_pnl_generations'::text,
    string_agg(DISTINCT finance.generation_id::text, ',' ORDER BY finance.generation_id::text),
    'store_pnl_generation_heads'::text,
    string_agg(
        finance.company_name || ':' || finance.revision::text,
        ',' ORDER BY finance.company_name
    ),
    1::integer,
    'store-pnl-generation-v1'::text,
    'official'::text,
    MIN(finance.cutoff),
    MIN(finance.cutoff),
    true,
    SUM(finance.candidate_row_count)::bigint,
    SUM(finance.candidate_row_count)::bigint,
    MAX(COALESCE(finance.promoted_at, finance.updated_at)),
    ARRAY['actual_only_estimates_unavailable']::text[]
FROM finance_scope AS finance
GROUP BY finance.period

UNION ALL

SELECT
    'planning'::text,
    planning.period,
    'planning_authorities'::text,
    concat_ws(
        '|',
        CASE
            WHEN planning.forecast_id IS NOT NULL
                THEN 'forecast-run:' || planning.forecast_id::text
        END,
        CASE
            WHEN planning.target_id IS NOT NULL
                THEN 'target-scenario:' || planning.target_id::text
        END
    ),
    concat_ws(
        '|',
        CASE
            WHEN planning.forecast_id IS NOT NULL THEN 'completed_forecast_run'
        END,
        CASE
            WHEN planning.target_id IS NOT NULL THEN 'finalized_target_scenario'
        END
    ),
    concat_ws(
        '|',
        CASE
            WHEN planning.forecast_id IS NOT NULL
                THEN 'forecast:' || planning.forecast_id::text
        END,
        CASE
            WHEN planning.target_id IS NOT NULL
                THEN 'target:' || planning.target_id::text || ':revision:' || planning.target_revision::text
        END
    ),
    1::integer,
    COALESCE(
        concat_ws(
            '|',
            CASE
                WHEN planning.forecast_id IS NOT NULL
                    THEN planning.model_name || ':' || planning.model_mode || ':' || planning.variant
            END,
            planning.rule_set_hash
        ),
        'planning-v1'
    ),
    CASE
        WHEN planning.forecast_id IS NULL
         AND planning.target_id IS NOT NULL
         AND planning.rule_set_snapshot IS NOT NULL
         AND planning.has_final_values THEN 'official'
        ELSE 'partial'
    END,
    NULL::date,
    NULL::date,
    (
        planning.forecast_id IS NULL
        AND planning.target_id IS NOT NULL
        AND planning.rule_set_snapshot IS NOT NULL
        AND planning.has_final_values
    ),
    COALESCE(planning.forecast_coverage, 0) + COALESCE(planning.target_coverage, 0),
    COALESCE(planning.forecast_coverage, 0) + COALESCE(planning.target_coverage, 0),
    GREATEST(
        COALESCE(planning.forecast_produced_at, '-infinity'::timestamptz),
        COALESCE(planning.target_produced_at, '-infinity'::timestamptz)
    ),
    ARRAY[]::text[]
    || CASE
        WHEN planning.forecast_id IS NULL THEN ARRAY['completed_forecast_unavailable']::text[]
        ELSE ARRAY['forecast_run_not_promoted']::text[]
    END
    || CASE
        WHEN planning.target_id IS NULL THEN ARRAY['finalized_target_unavailable']::text[]
        WHEN planning.rule_set_snapshot IS NOT NULL AND planning.has_final_values THEN ARRAY[]::text[]
        ELSE ARRAY['finalized_target_lacks_a_versioned_rule_snapshot_or_values']::text[]
    END
FROM planning_source AS planning;

CREATE OR REPLACE VIEW reporting_campaign_month_v1 (
    period,
    mechanism,
    site_code,
    locatie,
    firma,
    regional,
    asm,
    actual_sales,
    actual_quantity,
    active_product_count,
    source,
    source_generation,
    authority,
    authority_head,
    contract_version,
    rule_version,
    status,
    as_of,
    cutoff,
    is_final,
    coverage_numerator,
    coverage_denominator,
    produced_at,
    warnings
)
WITH (security_barrier = true)
AS
SELECT
    focus.import_month,
    'focus'::text,
    focus.site_code,
    MAX(focus.locatie),
    MAX(focus.firma),
    MAX(focus.regional),
    MAX(focus.asm),
    SUM(focus.total_sales),
    SUM(focus.total_quantity)::bigint,
    COUNT(DISTINCT focus.item_code)::bigint,
    snapshot.source,
    snapshot.source_generation,
    snapshot.authority,
    snapshot.authority_head,
    snapshot.contract_version,
    snapshot.rule_version,
    snapshot.status,
    snapshot.as_of,
    snapshot.cutoff,
    snapshot.is_final,
    snapshot.coverage_numerator,
    snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings
FROM reporting_focus_item_month AS focus
JOIN reporting_source_snapshot_v1 AS snapshot
  ON snapshot.domain = 'campaigns'
 AND snapshot.period = focus.import_month
WHERE focus.locatie NOT ILIKE 'TR%'
  AND focus.locatie NOT ILIKE '%cartel%'
GROUP BY
    focus.import_month,
    focus.site_code,
    snapshot.source,
    snapshot.source_generation,
    snapshot.authority,
    snapshot.authority_head,
    snapshot.contract_version,
    snapshot.rule_version,
    snapshot.status,
    snapshot.as_of,
    snapshot.cutoff,
    snapshot.is_final,
    snapshot.coverage_numerator,
    snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings;

CREATE OR REPLACE VIEW reporting_workforce_month_v1 (
    period,
    site_code,
    locatie,
    firma,
    regional,
    asm,
    active_agent_count,
    total_sales,
    total_quantity,
    working_days,
    new_agent_count,
    reactivated_agent_count,
    source,
    source_generation,
    authority,
    authority_head,
    contract_version,
    rule_version,
    status,
    as_of,
    cutoff,
    is_final,
    coverage_numerator,
    coverage_denominator,
    produced_at,
    warnings
)
WITH (security_barrier = true)
AS
SELECT
    monthly.import_month,
    monthly.site_code,
    MAX(monthly.locatie),
    MAX(monthly.firma),
    MAX(monthly.regional),
    MAX(monthly.asm),
    COUNT(DISTINCT monthly.agent)::bigint,
    SUM(monthly.total_sales),
    SUM(monthly.total_quantity)::bigint,
    SUM(monthly.working_days)::bigint,
    COUNT(DISTINCT monthly.agent) FILTER (WHERE lifecycle.is_new)::bigint,
    COUNT(DISTINCT monthly.agent) FILTER (WHERE lifecycle.is_reactivated)::bigint,
    snapshot.source,
    snapshot.source_generation,
    snapshot.authority,
    snapshot.authority_head,
    snapshot.contract_version,
    snapshot.rule_version,
    snapshot.status,
    snapshot.as_of,
    snapshot.cutoff,
    snapshot.is_final,
    snapshot.coverage_numerator,
    snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings
FROM reporting_agent_month AS monthly
JOIN reporting_source_snapshot_v1 AS snapshot
  ON snapshot.domain = 'workforce'
 AND snapshot.period = monthly.import_month
LEFT JOIN reporting_agent_lifecycle_month AS lifecycle
  ON lifecycle.import_month = monthly.import_month
 AND lifecycle.agent = monthly.agent
WHERE monthly.locatie NOT ILIKE 'TR%'
  AND monthly.locatie NOT ILIKE '%cartel%'
GROUP BY
    monthly.import_month,
    monthly.site_code,
    snapshot.source,
    snapshot.source_generation,
    snapshot.authority,
    snapshot.authority_head,
    snapshot.contract_version,
    snapshot.rule_version,
    snapshot.status,
    snapshot.as_of,
    snapshot.cutoff,
    snapshot.is_final,
    snapshot.coverage_numerator,
    snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings;

CREATE OR REPLACE VIEW reporting_compensation_month_v1 (
    period,
    company_name,
    eligible_person_count,
    payroll_total,
    average_salary_eligible,
    median_salary,
    source,
    source_generation,
    authority,
    authority_head,
    contract_version,
    rule_version,
    status,
    as_of,
    cutoff,
    is_final,
    coverage_numerator,
    coverage_denominator,
    produced_at,
    warnings
)
WITH (security_barrier = true)
AS
WITH protected_person_month AS (
    SELECT
        salary.year,
        salary.month,
        salary.company_name,
        salary.person_id,
        SUM(salary.total_salary) AS total_salary
    FROM salary_records AS salary
    JOIN salary_import_batches AS batch
      ON batch.batch_id = salary.import_batch_id
     AND batch.status = 'applied'
     AND batch.approval_artifact_sha256 IS NOT NULL
    WHERE salary.person_id IS NOT NULL
    GROUP BY salary.year, salary.month, salary.company_name, salary.person_id
),
protected_company_month AS (
    SELECT
        person_month.year,
        person_month.month,
        person_month.company_name,
        COUNT(*)::bigint AS eligible_person_count,
        SUM(person_month.total_salary) AS payroll_total,
        AVG(person_month.total_salary) FILTER (WHERE person_month.total_salary >= 2000)
            AS average_salary_eligible,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY person_month.total_salary)
            AS median_salary
    FROM protected_person_month AS person_month
    GROUP BY person_month.year, person_month.month, person_month.company_name
    HAVING COUNT(*) >= 3
),
protected_all_person_month AS (
    SELECT
        person_month.year,
        person_month.month,
        person_month.person_id,
        SUM(person_month.total_salary) AS total_salary
    FROM protected_person_month AS person_month
    GROUP BY person_month.year, person_month.month, person_month.person_id
),
protected_all_month AS (
    SELECT
        person_month.year,
        person_month.month,
        '__ALL__'::text AS company_name,
        COUNT(*)::bigint AS eligible_person_count,
        SUM(person_month.total_salary) AS payroll_total,
        AVG(person_month.total_salary) FILTER (WHERE person_month.total_salary >= 2000)
            AS average_salary_eligible,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY person_month.total_salary)
            AS median_salary
    FROM protected_all_person_month AS person_month
    GROUP BY person_month.year, person_month.month
    HAVING COUNT(*) >= 3
),
protected_compensation_month AS (
    SELECT
        year,
        month,
        company_name,
        eligible_person_count,
        payroll_total,
        average_salary_eligible,
        median_salary
    FROM protected_company_month

    UNION ALL

    SELECT
        year,
        month,
        company_name,
        eligible_person_count,
        payroll_total,
        average_salary_eligible,
        median_salary
    FROM protected_all_month
)
SELECT
    format('%s-%s', compensation.year, lpad(compensation.month::text, 2, '0')),
    compensation.company_name,
    compensation.eligible_person_count,
    compensation.payroll_total,
    compensation.average_salary_eligible,
    compensation.median_salary,
    snapshot.source,
    snapshot.source_generation,
    snapshot.authority,
    snapshot.authority_head,
    snapshot.contract_version,
    snapshot.rule_version,
    snapshot.status,
    snapshot.as_of,
    snapshot.cutoff,
    snapshot.is_final,
    snapshot.coverage_numerator,
    snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings
FROM protected_compensation_month AS compensation
JOIN reporting_source_snapshot_v1 AS snapshot
  ON snapshot.domain = 'compensation'
 AND snapshot.period = format('%s-%s', compensation.year, lpad(compensation.month::text, 2, '0'));

CREATE OR REPLACE VIEW reporting_visit_month_v1 (
    period,
    manager_dimension,
    manager_key,
    total_visits,
    avg_completion,
    avg_duration,
    distinct_stores,
    checklist_score,
    approved_pct,
    source,
    source_generation,
    authority,
    authority_head,
    contract_version,
    rule_version,
    status,
    as_of,
    cutoff,
    is_final,
    coverage_numerator,
    coverage_denominator,
    produced_at,
    warnings
)
WITH (security_barrier = true)
AS
SELECT
    visit.month,
    'legacy_asm'::text,
    visit.asm,
    visit.total_visits::bigint,
    visit.avg_completion,
    visit.avg_duration,
    visit.distinct_stores::bigint,
    visit.checklist_score,
    visit.approved_pct,
    snapshot.source,
    snapshot.source_generation,
    snapshot.authority,
    snapshot.authority_head,
    snapshot.contract_version,
    snapshot.rule_version,
    snapshot.status,
    snapshot.as_of,
    snapshot.cutoff,
    snapshot.is_final,
    snapshot.coverage_numerator,
    snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings
FROM visits_snapshot AS visit
JOIN reporting_source_snapshot_v1 AS snapshot
  ON snapshot.domain = 'visits'
 AND snapshot.period = visit.month;

CREATE OR REPLACE VIEW reporting_finance_month_v1 (
    period,
    company_name,
    source_site_code,
    source_location_name,
    site_code,
    locatie,
    firma,
    regional,
    asm,
    is_unallocated,
    category_code,
    category_name,
    amount,
    data_kind,
    source,
    source_generation,
    authority,
    authority_head,
    contract_version,
    rule_version,
    status,
    as_of,
    cutoff,
    is_final,
    coverage_numerator,
    coverage_denominator,
    produced_at,
    warnings
)
WITH (security_barrier = true)
AS
SELECT
    to_char(row.period, 'YYYY-MM'),
    row.company_name,
    row.source_site_code,
    row.source_location_name,
    COALESCE(link.site_code, '__FINANCE_UNALLOCATED__')::text,
    store.locatie,
    store.firma,
    store.regional,
    store.asm,
    (link.site_code IS NULL),
    row.category_code,
    row.category_name,
    row.amount,
    'actual'::text,
    snapshot.source,
    snapshot.source_generation,
    snapshot.authority,
    snapshot.authority_head,
    snapshot.contract_version,
    snapshot.rule_version,
    snapshot.status,
    snapshot.as_of,
    snapshot.cutoff,
    snapshot.is_final,
    snapshot.coverage_numerator,
    snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings
FROM store_pnl_generation_heads AS head
JOIN store_pnl_generations AS generation
  ON generation.id = head.active_generation_id
 AND generation.state = 'promoted'
JOIN store_pnl_generation_scopes AS scope
  ON scope.generation_id = head.active_generation_id
 AND scope.company_name = head.company_name
 AND scope.period = head.period
JOIN store_pnl_generation_rows AS row
  ON row.generation_id = scope.generation_id
 AND row.company_name = scope.company_name
 AND row.period = scope.period
 AND row.row_set = 'candidate'
LEFT JOIN store_pnl_site_links AS link
  ON link.company_name = row.company_name
 AND link.source_site_code = row.source_site_code
LEFT JOIN stores AS store
  ON store.site_code = link.site_code
JOIN reporting_source_snapshot_v1 AS snapshot
  ON snapshot.domain = 'finance'
 AND snapshot.period = to_char(row.period, 'YYYY-MM');

CREATE OR REPLACE VIEW reporting_planning_scenario_v1 (
    authority_kind,
    period,
    site_code,
    locatie,
    firma,
    regional,
    asm,
    forecast_run_id,
    target_scenario_id,
    target_scenario_revision,
    metric,
    horizon,
    model_name,
    model_mode,
    variant,
    source_month,
    rule_set_hash,
    forecast_value,
    target_value,
    source,
    source_generation,
    authority,
    authority_head,
    contract_version,
    rule_version,
    status,
    as_of,
    cutoff,
    is_final,
    coverage_numerator,
    coverage_denominator,
    produced_at,
    warnings
)
WITH (security_barrier = true)
AS
SELECT
    'forecast'::text,
    forecast.forecast_month,
    store_forecast.site_code,
    store.locatie,
    store.firma,
    store.regional,
    store.asm,
    forecast.id,
    NULL::integer,
    NULL::integer,
    forecast.metric,
    forecast.horizon,
    forecast.model_name,
    forecast.model_mode,
    forecast.variant,
    forecast.source_month,
    NULL::text,
    store_forecast.forecast_sales,
    NULL::numeric,
    snapshot.source,
    snapshot.source_generation,
    snapshot.authority,
    snapshot.authority_head,
    snapshot.contract_version,
    snapshot.rule_version,
    snapshot.status,
    snapshot.as_of,
    snapshot.cutoff,
    snapshot.is_final,
    snapshot.coverage_numerator,
    snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings
FROM ai_forecast_runs AS forecast
JOIN ai_forecast_store_month AS store_forecast
  ON store_forecast.run_id = forecast.id
JOIN stores AS store
  ON store.site_code = store_forecast.site_code
JOIN reporting_source_snapshot_v1 AS snapshot
  ON snapshot.domain = 'planning'
 AND snapshot.period = forecast.forecast_month
 AND position('forecast-run:' || forecast.id::text IN snapshot.source_generation) > 0
WHERE forecast.status = 'completed'

UNION ALL

SELECT
    'target'::text,
    scenario.target_month,
    target.site_code,
    target.locatie,
    target.firma,
    target.regional,
    target.asm,
    NULL::bigint,
    scenario.id,
    scenario.revision,
    NULL::text,
    NULL::text,
    NULL::text,
    NULL::text,
    NULL::text,
    scenario.cohort_month,
    scenario.rule_set_hash,
    NULL::numeric,
    target.final_target,
    snapshot.source,
    snapshot.source_generation,
    snapshot.authority,
    snapshot.authority_head,
    snapshot.contract_version,
    snapshot.rule_version,
    snapshot.status,
    snapshot.as_of,
    snapshot.cutoff,
    snapshot.is_final,
    snapshot.coverage_numerator,
    snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings
FROM target_scenarios AS scenario
JOIN target_scenario_rows AS target
  ON target.scenario_id = scenario.id
JOIN reporting_source_snapshot_v1 AS snapshot
  ON snapshot.domain = 'planning'
 AND snapshot.period = scenario.target_month
 AND position('target-scenario:' || scenario.id::text IN snapshot.source_generation) > 0
WHERE scenario.status = 'finalized';

COMMENT ON VIEW reporting_source_snapshot_v1 IS
    'Versioned source/finality metadata for all UniHub Insight analytical read models.';
COMMENT ON VIEW reporting_compensation_month_v1 IS
    'Fail-closed compensation aggregate: approved batches only, company/month and __ALL__ scopes, with fewer than three people omitted.';
COMMENT ON VIEW reporting_finance_month_v1 IS
    'P&L actuals only from the current promoted immutable generation head; estimated rows are deliberately absent.';
COMMENT ON VIEW reporting_visit_month_v1 IS
    'Legacy ASM visit snapshot only; this is explicitly not a Team Leader visit contract.';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_insight_reader') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA public TO unihub_insight_reader';
        EXECUTE 'GRANT SELECT ON TABLE '
            || 'reporting_source_snapshot_v1, '
            || 'reporting_campaign_month_v1, '
            || 'reporting_workforce_month_v1, '
            || 'reporting_compensation_month_v1, '
            || 'reporting_visit_month_v1, '
            || 'reporting_finance_month_v1, '
            || 'reporting_planning_scenario_v1 '
            || 'TO unihub_insight_reader';
    END IF;
END
$$;

-- Raw grants are intentionally preserved for one publisher release so the
-- currently deployed N-1 Insight consumer remains rollback-compatible.  A
-- follow-up migration revokes them only after two view-based Insight releases
-- are deployed and the rollback drill has selected the view-based predecessor.
