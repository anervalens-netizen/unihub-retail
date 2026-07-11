CREATE TABLE IF NOT EXISTS store_pnl_site_links (
    company_name TEXT NOT NULL CHECK (company_name IN ('Mobicell', 'Mobiup')),
    source_site_code TEXT NOT NULL,
    source_location_name TEXT NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE RESTRICT,
    match_method TEXT NOT NULL CHECK (match_method IN ('exact_code', 'exact_name', 'manual_alias', 'fuzzy_name')),
    confidence NUMERIC(5, 4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    reviewed BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (company_name, source_site_code)
);

CREATE INDEX IF NOT EXISTS idx_store_pnl_site_links_site_code
    ON store_pnl_site_links (site_code);

COMMENT ON TABLE store_pnl_site_links IS
    'Legatura auditabila dintre codurile istorice Finance P&L si stores.site_code.';
