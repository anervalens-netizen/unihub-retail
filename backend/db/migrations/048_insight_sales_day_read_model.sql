-- Daily, versioned Sales contract for UniHub Insight calendar and day-grain queries.
--
-- The view remains additive and exposes only Retail reporting aggregates.  A
-- missing date stays missing; an observed zero remains a row with value zero.
-- Return quantity keeps the canonical negative sign used by Retail.

CREATE OR REPLACE VIEW reporting_sales_day_v1 (
    period,
    sale_date,
    site_code,
    locatie,
    firma,
    regional,
    asm,
    agent,
    net_sales,
    net_quantity,
    positive_quantity,
    return_quantity,
    receipt_count,
    receipt_2plus_count,
    coverage_state,
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
WITH item_day AS (
    SELECT
        item.import_month,
        item.sale_date,
        item.site_code,
        item.agent,
        SUM(item.positive_quantity)::bigint AS positive_quantity,
        SUM(item.return_quantity)::bigint AS return_quantity
    FROM reporting_item_day AS item
    WHERE item.locatie NOT ILIKE 'TR %'
      AND item.locatie NOT ILIKE '%cartel%'
    GROUP BY
        item.import_month,
        item.sale_date,
        item.site_code,
        item.agent
)
SELECT
    daily.import_month,
    daily.sale_date,
    daily.site_code,
    daily.locatie,
    daily.firma,
    daily.regional,
    daily.asm,
    daily.agent,
    daily.total_sales,
    daily.total_quantity::bigint,
    COALESCE(item_day.positive_quantity, 0),
    COALESCE(item_day.return_quantity, 0),
    daily.receipt_count::bigint,
    daily.receipt_2plus_count::bigint,
    'observed'::text,
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
FROM reporting_agent_day AS daily
LEFT JOIN item_day
  ON item_day.import_month = daily.import_month
 AND item_day.sale_date = daily.sale_date
 AND item_day.site_code = daily.site_code
 AND item_day.agent = daily.agent
JOIN reporting_source_snapshot_v1 AS snapshot
  ON snapshot.domain = 'sales'
 AND snapshot.period = daily.import_month
WHERE daily.locatie NOT ILIKE 'TR %'
  AND daily.locatie NOT ILIKE '%cartel%';

COMMENT ON VIEW reporting_sales_day_v1 IS
    'Observed day-grain Sales aggregates for Insight; coverage_state never claims completeness, missing dates are not converted to zero and return quantity stays negative.';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_insight_reader') THEN
        EXECUTE 'GRANT SELECT ON TABLE reporting_sales_day_v1 TO unihub_insight_reader';
    END IF;
END
$$;
