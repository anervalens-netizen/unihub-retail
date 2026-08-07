-- Preserve Finance v2 semantics while making period predicates index/pushdown
-- eligible.  The preferred-kind decision is a single window pass and all row
-- metadata uses period windows; neither view materializes unrelated months.

CREATE OR REPLACE VIEW reporting_finance_preferred_rows_v1 (
    source_row_id, period, company_name, source_site_code,
    source_location_name, site_code, locatie, firma, regional, asm,
    is_unallocated, is_unmapped, category_code, category_name, amount,
    data_kind, source_file, source_sha256, imported_at, period_date
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
), ranked AS (
    SELECT
        row.*,
        bool_or(row.data_kind = 'actual') OVER (
            PARTITION BY row.company_name, row.period, row.canonical_site_code
        ) AS has_actual
    FROM normalized AS row
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
    row.imported_at,
    row.period
FROM ranked AS row
WHERE row.data_kind = CASE WHEN row.has_actual THEN 'actual' ELSE 'estimated' END;

CREATE OR REPLACE VIEW reporting_finance_month_v2 (
    period, company_name, source_site_code, source_location_name, site_code,
    locatie, firma, regional, asm, is_unallocated, is_unmapped, category_code,
    category_name, amount, data_kind, source_file, source_sha256, source_row_id,
    source, source_generation, authority, authority_head, contract_version,
    rule_version, status, as_of, cutoff, is_final, coverage_numerator,
    coverage_denominator, produced_at, warnings, period_date
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
    'store_pnl_monthly'::text,
    format(
        'finance-direct:%s:%s:%s',
        finance.period,
        MAX(finance.source_row_id) OVER (PARTITION BY finance.period_date),
        COUNT(*) OVER (PARTITION BY finance.period_date)
    ),
    'retail_store_pnl_direct'::text,
    NULL::text,
    2::integer,
    'store-pnl-prefer-actual-v2'::text,
    'official'::text,
    NULL::date,
    NULL::date,
    NOT bool_or(finance.data_kind = 'estimated') OVER (
        PARTITION BY finance.period_date
    ),
    COUNT(*) OVER (PARTITION BY finance.period_date)::bigint,
    COUNT(*) OVER (PARTITION BY finance.period_date)::bigint,
    MAX(finance.imported_at) OVER (PARTITION BY finance.period_date),
    ARRAY_REMOVE(ARRAY[
        CASE WHEN bool_or(finance.data_kind = 'estimated') OVER (
            PARTITION BY finance.period_date
        ) THEN 'estimated_rows_visible' END,
        CASE WHEN bool_or(finance.is_unallocated) OVER (
            PARTITION BY finance.period_date
        ) THEN 'finance_unallocated_rows_visible' END,
        CASE WHEN bool_or(finance.is_unmapped) OVER (
            PARTITION BY finance.period_date
        ) THEN 'finance_unmapped_rows_visible' END
    ], NULL),
    finance.period_date
FROM reporting_finance_preferred_rows_v1 AS finance;

COMMENT ON VIEW reporting_finance_preferred_rows_v1 IS
    'Internal Retail-equivalent Finance preference with an explicit date key for bounded period pushdown; not granted to the Insight reader.';
COMMENT ON VIEW reporting_finance_month_v2 IS
    'Complete Retail P&L v2 with actual/estimated precedence and bounded period-local window metadata.';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_insight_reader') THEN
        GRANT SELECT ON TABLE reporting_finance_month_v2 TO unihub_insight_reader;
    END IF;
END
$$;
