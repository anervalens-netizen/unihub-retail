CREATE OR REPLACE VIEW reporting_sales_cutoff_v1 (
    import_month, cutoff_date
) WITH (security_barrier = true) AS
SELECT
    head.import_month,
    COALESCE(snapshot.cutoff_date, MAX(transaction.sale_date)) AS cutoff_date
FROM sales_generation_heads AS head
JOIN import_snapshots AS snapshot
  ON snapshot.id = head.snapshot_id
 AND snapshot.status = 'completed'
LEFT JOIN sales_transactions AS transaction
  ON transaction.snapshot_id = snapshot.id
GROUP BY head.import_month, snapshot.cutoff_date;

COMMENT ON VIEW reporting_sales_cutoff_v1 IS
    'Official cutoff of the currently promoted sales generation, without exposing generation evidence to the web process.';

REVOKE ALL ON TABLE reporting_sales_cutoff_v1 FROM PUBLIC;
GRANT SELECT ON TABLE reporting_sales_cutoff_v1 TO unihub_web_read;
