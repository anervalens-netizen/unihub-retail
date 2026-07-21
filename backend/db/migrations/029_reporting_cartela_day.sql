CREATE TABLE IF NOT EXISTS reporting_cartela_day (
    import_month TEXT NOT NULL
        CHECK (import_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    sale_date DATE NOT NULL,
    site_code TEXT NOT NULL,
    agent TEXT NOT NULL,
    total_quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (import_month, sale_date, site_code, agent)
);

CREATE INDEX IF NOT EXISTS idx_reporting_cartela_day_month_site
    ON reporting_cartela_day (import_month, site_code);

CREATE INDEX IF NOT EXISTS idx_reporting_cartela_day_month_agent
    ON reporting_cartela_day (import_month, agent);

INSERT INTO reporting_cartela_day (
    import_month,
    sale_date,
    site_code,
    agent,
    total_quantity
)
SELECT
    st.import_month,
    st.sale_date,
    st.site_code,
    st.agent,
    COALESCE(SUM(st.quantity), 0)::INT
FROM sales_transactions st
JOIN stores s ON s.site_code = st.site_code
WHERE st.is_cartela = true
  AND s.locatie NOT ILIKE 'TR %'
GROUP BY st.import_month, st.sale_date, st.site_code, st.agent
ON CONFLICT (import_month, sale_date, site_code, agent) DO UPDATE
SET total_quantity = EXCLUDED.total_quantity;

ANALYZE reporting_cartela_day;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON TABLE reporting_cartela_day TO unihub_runtime;
    END IF;
END
$$;
