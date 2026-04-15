-- Composite partial index for cartela receipt count query
-- Replaces the BitmapAnd of idx_sales_transactions_month_cartela + idx_sales_date
-- with a single index scan, eliminating 872 heap block re-checks (~40ms → ~10ms).
--
-- Query target: specials_data.py COUNT(DISTINCT bon_nr) WHERE import_month + sale_date + is_cartela=false
CREATE INDEX IF NOT EXISTS idx_sales_month_date_cartela
    ON sales_transactions (import_month, sale_date)
    WHERE is_cartela = false;
