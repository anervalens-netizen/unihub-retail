-- Complete, additive Compensation and Finance read models for UniHub Insight.
--
-- The v1 contracts remain available as N-1 rollback anchors.  v2 publishes
-- every Retail salary row (without CNP) and the same actual/estimated P&L rows
-- selected by Retail.  Import provenance enriches the result; it never gates
-- an existing business row.

CREATE OR REPLACE VIEW reporting_finance_preferred_rows_v1 (
    source_row_id, period, company_name, source_site_code,
    source_location_name, site_code, locatie, firma, regional, asm,
    is_unallocated, is_unmapped, category_code, category_name, amount,
    data_kind, source_file, source_sha256, imported_at
) WITH (security_barrier = true) AS
WITH normalized AS (
    SELECT
        pnl.id AS source_row_id,
        pnl.period,
        pnl.company_name,
        pnl.source_site_code,
        pnl.source_location_name,
        CASE
            WHEN pnl.source_site_code = '__FINANCE_UNALLOCATED__'
                THEN '__FINANCE_UNALLOCATED__'
            ELSE COALESCE(link.site_code, pnl.source_site_code)
        END AS canonical_site_code,
        link.site_code AS linked_site_code,
        store.locatie,
        store.firma,
        store.regional,
        store.asm,
        pnl.category_code,
        pnl.category_name,
        pnl.amount,
        pnl.data_kind,
        pnl.source_file,
        pnl.source_sha256,
        pnl.imported_at
    FROM store_pnl_monthly AS pnl
    LEFT JOIN store_pnl_site_links AS link
      ON link.company_name = pnl.company_name
     AND link.source_site_code = pnl.source_site_code
     AND pnl.source_site_code <> '__FINANCE_UNALLOCATED__'
    LEFT JOIN stores AS store ON store.site_code = link.site_code
), preferred_kind AS (
    SELECT
        company_name,
        period,
        canonical_site_code,
        CASE WHEN bool_or(data_kind = 'actual') THEN 'actual' ELSE 'estimated' END
            AS data_kind
    FROM normalized
    GROUP BY company_name, period, canonical_site_code
)
SELECT
    row.source_row_id,
    to_char(row.period, 'YYYY-MM'),
    row.company_name,
    row.source_site_code,
    row.source_location_name,
    row.canonical_site_code,
    COALESCE(row.locatie, row.source_location_name),
    COALESCE(row.firma, row.company_name),
    row.regional,
    row.asm,
    row.source_site_code = '__FINANCE_UNALLOCATED__',
    row.source_site_code <> '__FINANCE_UNALLOCATED__'
        AND row.linked_site_code IS NULL,
    row.category_code,
    row.category_name,
    row.amount,
    row.data_kind,
    row.source_file,
    row.source_sha256,
    row.imported_at
FROM normalized AS row
JOIN preferred_kind AS preferred
  ON preferred.company_name = row.company_name
 AND preferred.period = row.period
 AND preferred.canonical_site_code = row.canonical_site_code
 AND preferred.data_kind = row.data_kind;

CREATE OR REPLACE VIEW reporting_source_snapshot_v7 (
    domain, period, source, source_generation, authority, authority_head,
    contract_version, rule_version, status, as_of, cutoff, is_final,
    coverage_numerator, coverage_denominator, produced_at, warnings
) WITH (security_barrier = true) AS
SELECT
    snapshot.domain,
    snapshot.period,
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
FROM reporting_source_snapshot_v6 AS snapshot
WHERE snapshot.domain NOT IN ('compensation', 'finance')

UNION ALL

SELECT
    'compensation'::text,
    format('%s-%s', salary.year, lpad(salary.month::text, 2, '0')),
    'salary_records'::text,
    format(
        'salary-direct:%s-%s:%s:%s',
        salary.year,
        lpad(salary.month::text, 2, '0'),
        MAX(salary.id),
        COUNT(*)
    ),
    'retail_salary_records'::text,
    NULL::text,
    2::integer,
    'compensation-person-v2'::text,
    'official'::text,
    NULL::date,
    NULL::date,
    false,
    COUNT(*)::bigint,
    COUNT(*)::bigint,
    MAX(salary.created_at),
    ARRAY_REMOVE(ARRAY[
        'compensation_finality_not_published'::text,
        CASE WHEN bool_or(salary.import_batch_id IS NULL)
            THEN 'legacy_salary_rows_visible' END,
        CASE WHEN bool_or(salary.site_code IS NULL)
            THEN 'salary_rows_without_store_visible' END
    ], NULL)
FROM salary_records AS salary
GROUP BY salary.year, salary.month

UNION ALL

SELECT
    'finance'::text,
    finance.period,
    'store_pnl_monthly'::text,
    format(
        'finance-direct:%s:%s:%s',
        finance.period,
        MAX(finance.source_row_id),
        COUNT(*)
    ),
    'retail_store_pnl_direct'::text,
    NULL::text,
    2::integer,
    'store-pnl-prefer-actual-v2'::text,
    'official'::text,
    NULL::date,
    NULL::date,
    NOT bool_or(finance.data_kind = 'estimated'),
    COUNT(DISTINCT (finance.company_name, finance.site_code))::bigint,
    COUNT(DISTINCT (finance.company_name, finance.site_code))::bigint,
    MAX(finance.imported_at),
    ARRAY_REMOVE(ARRAY[
        CASE WHEN bool_or(finance.data_kind = 'estimated')
            THEN 'estimated_rows_visible' END,
        CASE WHEN bool_or(finance.is_unallocated)
            THEN 'finance_unallocated_rows_visible' END,
        CASE WHEN bool_or(finance.is_unmapped)
            THEN 'finance_unmapped_rows_visible' END
    ], NULL)
FROM reporting_finance_preferred_rows_v1 AS finance
GROUP BY finance.period;

CREATE OR REPLACE VIEW reporting_compensation_person_month_v2 (
    salary_row_id, period, year, month, person_id, full_name, total_salary,
    company_name, site_code, salary_location, store_location, firma, regional,
    asm, linked_agent_codes, agent_link_count, record_source_state,
    import_batch_id, source_file, source_sheet, source_row, source_sha256,
    source, source_generation, authority, authority_head, contract_version,
    rule_version, status, as_of, cutoff, is_final, coverage_numerator,
    coverage_denominator, produced_at, warnings
) WITH (security_barrier = true) AS
SELECT
    salary.id,
    format('%s-%s', salary.year, lpad(salary.month::text, 2, '0')),
    salary.year,
    salary.month,
    salary.person_id,
    salary.full_name,
    salary.total_salary,
    salary.company_name,
    salary.site_code,
    salary.locatie,
    store.locatie,
    COALESCE(store.firma, salary.company_name),
    store.regional,
    store.asm,
    COALESCE(agent_links.agent_codes, ARRAY[]::text[]),
    COALESCE(agent_links.agent_count, 0::bigint),
    CASE
        WHEN salary.import_batch_id IS NULL THEN 'legacy'
        ELSE COALESCE(batch.status, 'batch-missing')
    END,
    salary.import_batch_id,
    salary.source_file,
    salary.source_sheet,
    salary.source_row,
    salary.source_sha256,
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
FROM salary_records AS salary
LEFT JOIN salary_import_batches AS batch ON batch.batch_id = salary.import_batch_id
LEFT JOIN stores AS store ON store.site_code = salary.site_code
LEFT JOIN LATERAL (
    SELECT
        array_agg(DISTINCT link.agent_code ORDER BY link.agent_code) AS agent_codes,
        COUNT(DISTINCT link.agent_code)::bigint AS agent_count
    FROM agent_salary_links AS link
    WHERE link.match_status = 'confirmed'
      AND link.person_id = salary.person_id
      AND link.site_code = salary.site_code
      AND (
          link.effective_from_month IS NULL
          OR link.effective_from_month <= format(
              '%s-%s', salary.year, lpad(salary.month::text, 2, '0')
          )
      )
) AS agent_links ON true
JOIN reporting_source_snapshot_v7 AS snapshot
  ON snapshot.domain = 'compensation'
 AND snapshot.period = format('%s-%s', salary.year, lpad(salary.month::text, 2, '0'));

CREATE OR REPLACE VIEW reporting_compensation_month_v2 (
    period, company_name, person_count, salary_row_count, payroll_total,
    average_salary, median_salary, minimum_salary, maximum_salary,
    source, source_generation, authority, authority_head, contract_version,
    rule_version, status, as_of, cutoff, is_final, coverage_numerator,
    coverage_denominator, produced_at, warnings
) WITH (security_barrier = true) AS
WITH company_person AS (
    SELECT
        row.period,
        row.company_name,
        row.person_id,
        SUM(row.total_salary) AS total_salary,
        COUNT(*)::bigint AS salary_row_count
    FROM reporting_compensation_person_month_v2 AS row
    GROUP BY row.period, row.company_name, row.person_id
), company_month AS (
    SELECT
        period,
        company_name,
        COUNT(*)::bigint AS person_count,
        SUM(salary_row_count)::bigint AS salary_row_count,
        SUM(total_salary) AS payroll_total,
        AVG(total_salary) AS average_salary,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY total_salary) AS median_salary,
        MIN(total_salary) AS minimum_salary,
        MAX(total_salary) AS maximum_salary
    FROM company_person
    GROUP BY period, company_name
), all_person AS (
    SELECT
        period,
        person_id,
        SUM(total_salary) AS total_salary,
        SUM(salary_row_count)::bigint AS salary_row_count
    FROM company_person
    GROUP BY period, person_id
), all_month AS (
    SELECT
        period,
        '__ALL__'::text AS company_name,
        COUNT(*)::bigint AS person_count,
        SUM(salary_row_count)::bigint AS salary_row_count,
        SUM(total_salary) AS payroll_total,
        AVG(total_salary) AS average_salary,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY total_salary) AS median_salary,
        MIN(total_salary) AS minimum_salary,
        MAX(total_salary) AS maximum_salary
    FROM all_person
    GROUP BY period
), combined AS (
    SELECT * FROM company_month
    UNION ALL
    SELECT * FROM all_month
)
SELECT
    compensation.period,
    compensation.company_name,
    compensation.person_count,
    compensation.salary_row_count,
    compensation.payroll_total,
    compensation.average_salary,
    compensation.median_salary,
    compensation.minimum_salary,
    compensation.maximum_salary,
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
FROM combined AS compensation
JOIN reporting_source_snapshot_v7 AS snapshot
  ON snapshot.domain = 'compensation'
 AND snapshot.period = compensation.period;

CREATE OR REPLACE VIEW reporting_finance_month_v2 (
    period, company_name, source_site_code, source_location_name, site_code,
    locatie, firma, regional, asm, is_unallocated, is_unmapped, category_code,
    category_name, amount, data_kind, source_file, source_sha256, source_row_id,
    source, source_generation, authority, authority_head, contract_version,
    rule_version, status, as_of, cutoff, is_final, coverage_numerator,
    coverage_denominator, produced_at, warnings
) WITH (security_barrier = true) AS
SELECT
    finance.period,
    finance.company_name,
    finance.source_site_code,
    finance.source_location_name,
    finance.site_code,
    finance.locatie,
    finance.firma,
    finance.regional,
    finance.asm,
    finance.is_unallocated,
    finance.is_unmapped,
    finance.category_code,
    finance.category_name,
    finance.amount,
    finance.data_kind,
    finance.source_file,
    finance.source_sha256,
    finance.source_row_id,
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
FROM reporting_finance_preferred_rows_v1 AS finance
JOIN reporting_source_snapshot_v7 AS snapshot
  ON snapshot.domain = 'finance'
 AND snapshot.period = finance.period;

COMMENT ON VIEW reporting_source_snapshot_v7 IS
    'Snapshot v7 keeps v6 domains and publishes every Retail salary row plus preferred actual/estimated Retail P&L rows without technical provenance gates.';
COMMENT ON VIEW reporting_compensation_person_month_v2 IS
    'One row per Retail salary record, including person and organizational detail but never CNP; no batch, value or cohort suppression.';
COMMENT ON VIEW reporting_compensation_month_v2 IS
    'Company and network Compensation aggregates over all person-month values; no minimum-person or salary-value threshold.';
COMMENT ON VIEW reporting_finance_month_v2 IS
    'Complete Retail P&L selection with actual preferred per company/period/site and estimated, unmapped and unallocated rows kept visible.';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_insight_reader') THEN
        GRANT USAGE ON SCHEMA public TO unihub_insight_reader;
        GRANT SELECT ON TABLE
            reporting_source_snapshot_v7,
            reporting_compensation_person_month_v2,
            reporting_compensation_month_v2,
            reporting_finance_month_v2
        TO unihub_insight_reader;
    END IF;
END
$$;
