CREATE TABLE IF NOT EXISTS historical_monthly_sales (
    site_code TEXT NOT NULL REFERENCES stores(site_code),
    import_month TEXT NOT NULL,
    firma TEXT NOT NULL,
    total_value NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total_qty INTEGER NOT NULL DEFAULT 0,
    source_file TEXT NOT NULL,
    source_store_name TEXT NOT NULL,
    source_manager TEXT,
    had_inchis_prefix BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (site_code, import_month, firma)
);

CREATE INDEX IF NOT EXISTS idx_historical_monthly_sales_month
    ON historical_monthly_sales (import_month);

CREATE INDEX IF NOT EXISTS idx_historical_monthly_sales_site_month
    ON historical_monthly_sales (site_code, import_month);
