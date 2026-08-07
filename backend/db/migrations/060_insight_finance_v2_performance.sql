-- Keep the 059 Finance v2 contract and avoid re-expanding the full cross-domain
-- snapshot while reading its rows. Metadata is derived once from the exact
-- materialized Finance row set for each period.

CREATE OR REPLACE VIEW reporting_finance_month_v2 (
    period, company_name, source_site_code, source_location_name, site_code,
    locatie, firma, regional, asm, is_unallocated, is_unmapped, category_code,
    category_name, amount, data_kind, source_file, source_sha256, source_row_id,
    source, source_generation, authority, authority_head, contract_version,
    rule_version, status, as_of, cutoff, is_final, coverage_numerator,
    coverage_denominator, produced_at, warnings
) WITH (security_barrier = true) AS
WITH finance_rows AS MATERIALIZED (
    SELECT * FROM reporting_finance_preferred_rows_v1
), finance_metadata AS (
    SELECT
        row.period,
        format(
            'finance-direct:%s:%s:%s',
            row.period,
            MAX(row.source_row_id),
            COUNT(*)
        ) AS source_generation,
        NOT bool_or(row.data_kind = 'estimated') AS is_final,
        COUNT(DISTINCT (row.company_name, row.site_code))::bigint AS coverage,
        MAX(row.imported_at) AS produced_at,
        ARRAY_REMOVE(ARRAY[
            CASE WHEN bool_or(row.data_kind = 'estimated')
                THEN 'estimated_rows_visible' END,
            CASE WHEN bool_or(row.is_unallocated)
                THEN 'finance_unallocated_rows_visible' END,
            CASE WHEN bool_or(row.is_unmapped)
                THEN 'finance_unmapped_rows_visible' END
        ], NULL) AS warnings
    FROM finance_rows AS row
    GROUP BY row.period
)
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
    metadata.source_generation,
    'retail_store_pnl_direct'::text,
    NULL::text,
    2::integer,
    'store-pnl-prefer-actual-v2'::text,
    'official'::text,
    NULL::date,
    NULL::date,
    metadata.is_final,
    metadata.coverage,
    metadata.coverage,
    metadata.produced_at,
    metadata.warnings
FROM finance_rows AS finance
JOIN finance_metadata AS metadata ON metadata.period = finance.period;

COMMENT ON VIEW reporting_finance_month_v2 IS
    'Complete Retail P&L v2 with period-local metadata materialized once; actual/estimated, unmapped and unallocated rows remain visible.';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_insight_reader') THEN
        GRANT SELECT ON TABLE reporting_finance_month_v2 TO unihub_insight_reader;
    END IF;
END
$$;
