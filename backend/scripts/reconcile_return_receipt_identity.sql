-- Read-only reconciliation for audit finding H-03.
-- Compares the legacy COUNT(DISTINCT bon_nr) with the canonical receipt identity.
-- Run against production only with a read-only database role.

\set ON_ERROR_STOP on

WITH returned_receipts AS MATERIALIZED (
    SELECT DISTINCT
        st.import_month,
        st.sale_date,
        st.site_code,
        COALESCE(NULLIF(BTRIM(st.agent), ''), '<unknown>') AS normalized_agent,
        st.bon_nr
    FROM sales_transactions st
    WHERE st.quantity < 0
      AND NOT st.is_cartela
      AND st.bon_nr IS NOT NULL
),
legacy_counts AS (
    SELECT
        import_month,
        COUNT(DISTINCT bon_nr)::BIGINT AS legacy_return_receipts
    FROM returned_receipts
    GROUP BY import_month
),
canonical_counts AS (
    SELECT
        import_month,
        COUNT(*)::BIGINT AS canonical_return_receipts
    FROM returned_receipts
    GROUP BY import_month
),
collisions AS (
    SELECT
        import_month,
        COUNT(*)::BIGINT AS colliding_receipt_numbers,
        COALESCE(SUM(canonical_receipts - 1), 0)::BIGINT AS receipts_lost_by_legacy_key
    FROM (
        SELECT
            import_month,
            bon_nr,
            COUNT(*)::BIGINT AS canonical_receipts
        FROM returned_receipts
        GROUP BY import_month, bon_nr
        HAVING COUNT(*) > 1
    ) grouped
    GROUP BY import_month
)
SELECT
    cc.import_month,
    COALESCE(lc.legacy_return_receipts, 0) AS legacy_return_receipts,
    cc.canonical_return_receipts,
    cc.canonical_return_receipts - COALESCE(lc.legacy_return_receipts, 0) AS absolute_delta,
    CASE
        WHEN COALESCE(lc.legacy_return_receipts, 0) > 0
        THEN ROUND(
            (cc.canonical_return_receipts - lc.legacy_return_receipts) * 100.0
            / lc.legacy_return_receipts,
            2
        )
        ELSE NULL
    END AS relative_delta_pct,
    COALESCE(c.colliding_receipt_numbers, 0) AS colliding_receipt_numbers,
    COALESCE(c.receipts_lost_by_legacy_key, 0) AS receipts_lost_by_legacy_key
FROM canonical_counts cc
LEFT JOIN legacy_counts lc USING (import_month)
LEFT JOIN collisions c USING (import_month)
ORDER BY cc.import_month DESC;
