-- Lot 23: materialize canonical return-receipt counts in the reporting read
-- model. Dashboard return summaries stop rescanning raw sales_transactions and
-- read the additive value that the monthly reporting refresh already produces.
--
-- Eligibility mirrors the reporting refresh exactly: non-TR location,
-- non-cartela, negative quantity and a non-null receipt number. A receipt is
-- counted once per canonical reporting grain, so duplicate item rows on the
-- same receipt contribute exactly "1". The monthly column is summed from the
-- backfilled day model instead of rescanning raw transactions a second time.

ALTER TABLE reporting_agent_day
    ADD COLUMN IF NOT EXISTS return_receipt_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE reporting_agent_month
    ADD COLUMN IF NOT EXISTS return_receipt_count INTEGER NOT NULL DEFAULT 0;

WITH return_day AS (
    SELECT
        st.import_month,
        st.sale_date,
        st.site_code,
        st.agent,
        COUNT(DISTINCT st.bon_nr)::INT AS return_receipt_count
    FROM sales_transactions st
    JOIN stores s ON s.site_code = st.site_code
    WHERE s.locatie NOT ILIKE 'TR %'
      AND NOT st.is_cartela
      AND st.quantity < 0
      AND st.bon_nr IS NOT NULL
    GROUP BY
        st.import_month,
        st.sale_date,
        st.site_code,
        st.agent
)
UPDATE reporting_agent_day rad
SET return_receipt_count = return_day.return_receipt_count
FROM return_day
WHERE rad.import_month = return_day.import_month
  AND rad.sale_date = return_day.sale_date
  AND rad.site_code = return_day.site_code
  AND rad.agent = return_day.agent;

WITH return_month AS (
    SELECT
        import_month,
        site_code,
        agent,
        COALESCE(SUM(return_receipt_count), 0)::INT AS return_receipt_count
    FROM reporting_agent_day
    GROUP BY import_month, site_code, agent
)
UPDATE reporting_agent_month ram
SET return_receipt_count = return_month.return_receipt_count
FROM return_month
WHERE ram.import_month = return_month.import_month
  AND ram.site_code = return_month.site_code
  AND ram.agent = return_month.agent;

ANALYZE reporting_agent_day;
ANALYZE reporting_agent_month;
