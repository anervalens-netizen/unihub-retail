CREATE TABLE IF NOT EXISTS store_pnl_monthly (
    id BIGSERIAL PRIMARY KEY,
    company_name TEXT NOT NULL CHECK (company_name IN ('Mobicell', 'Mobiup')),
    period DATE NOT NULL CHECK (period = date_trunc('month', period)::date),
    source_site_code TEXT NOT NULL,
    source_location_name TEXT NOT NULL,
    category_code TEXT NOT NULL CHECK (
        category_code IN ('v1', 'v11', 'v2', 'v3', 'c1', 'c11', 'c2', 'c3', 'c4', 'c5', 'c6', 'a1')
    ),
    category_name TEXT NOT NULL,
    amount NUMERIC(16, 2) NOT NULL,
    data_kind TEXT NOT NULL DEFAULT 'actual' CHECK (data_kind IN ('actual', 'estimated')),
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_name, period, source_site_code, category_code, data_kind)
);

CREATE INDEX IF NOT EXISTS idx_store_pnl_monthly_period
    ON store_pnl_monthly (period);
CREATE INDEX IF NOT EXISTS idx_store_pnl_monthly_company_period
    ON store_pnl_monthly (company_name, period);
CREATE INDEX IF NOT EXISTS idx_store_pnl_monthly_source_site
    ON store_pnl_monthly (source_site_code, period);

COMMENT ON TABLE store_pnl_monthly IS
    'P&L lunar pe magazin. Randurile actual sunt importate din fisierele Finance; estimarile trebuie marcate separat.';
COMMENT ON COLUMN store_pnl_monthly.source_site_code IS
    'Codul istoric exact din fisierul P&L; nu presupune corespondenta cu stores.site_code.';
