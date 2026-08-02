CREATE TABLE IF NOT EXISTS store_pnl_shadow_generations (
    id UUID PRIMARY KEY,
    scope JSONB NOT NULL,
    scope_sha256 TEXT NOT NULL CHECK (scope_sha256 ~ '^[0-9a-f]{64}$'),
    input_cutoff DATE NOT NULL CHECK (EXTRACT(DAY FROM input_cutoff) = 1),
    source_sha256 TEXT NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    input_sha256 TEXT NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    legacy_ruleset_sha256 TEXT NOT NULL CHECK (legacy_ruleset_sha256 ~ '^[0-9a-f]{64}$'),
    effective_ruleset_sha256 TEXT NOT NULL CHECK (effective_ruleset_sha256 ~ '^[0-9a-f]{64}$'),
    legacy_model_sha256 TEXT NOT NULL CHECK (legacy_model_sha256 ~ '^[0-9a-f]{64}$'),
    effective_model_sha256 TEXT NOT NULL CHECK (effective_model_sha256 ~ '^[0-9a-f]{64}$'),
    legacy_output_sha256 TEXT NOT NULL CHECK (legacy_output_sha256 ~ '^[0-9a-f]{64}$'),
    effective_output_sha256 TEXT NOT NULL CHECK (effective_output_sha256 ~ '^[0-9a-f]{64}$'),
    fiscal_delta JSONB NOT NULL,
    input_or_model_delta JSONB NOT NULL,
    baseline_generation_id UUID REFERENCES store_pnl_shadow_generations(id) ON DELETE RESTRICT,
    state TEXT NOT NULL DEFAULT 'staged'
        CHECK (state IN ('staged', 'promoted', 'superseded', 'rolled_back')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_at TIMESTAMPTZ,
    rolled_back_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_store_pnl_shadow_generations_scope
    ON store_pnl_shadow_generations (scope_sha256, created_at DESC);

CREATE TABLE IF NOT EXISTS store_pnl_shadow_rows (
    generation_id UUID NOT NULL REFERENCES store_pnl_shadow_generations(id) ON DELETE CASCADE,
    variant TEXT NOT NULL CHECK (variant IN ('legacy_v2', 'effective_v3')),
    company_name TEXT NOT NULL,
    period DATE NOT NULL,
    site_code TEXT NOT NULL,
    source_site_code TEXT NOT NULL,
    source_location_name TEXT NOT NULL,
    category_code TEXT NOT NULL,
    category_name TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    PRIMARY KEY (generation_id, variant, company_name, period, site_code, category_code)
);

CREATE INDEX IF NOT EXISTS idx_store_pnl_shadow_rows_scope
    ON store_pnl_shadow_rows (generation_id, variant, company_name, period);

CREATE TABLE IF NOT EXISTS store_pnl_shadow_preimage_rows (
    generation_id UUID NOT NULL REFERENCES store_pnl_shadow_generations(id) ON DELETE CASCADE,
    company_name TEXT NOT NULL,
    period DATE NOT NULL,
    source_site_code TEXT NOT NULL,
    source_location_name TEXT NOT NULL,
    category_code TEXT NOT NULL,
    category_name TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    data_kind TEXT NOT NULL CHECK (data_kind IN ('actual', 'estimated')),
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        generation_id, company_name, period, source_site_code,
        category_code, data_kind
    )
);

CREATE TABLE IF NOT EXISTS store_pnl_shadow_pointer (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    active_generation_id UUID REFERENCES store_pnl_shadow_generations(id) ON DELETE RESTRICT,
    previous_generation_id UUID REFERENCES store_pnl_shadow_generations(id) ON DELETE RESTRICT,
    revision BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO store_pnl_shadow_pointer (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON TABLE store_pnl_shadow_generations,
                     store_pnl_shadow_rows,
                     store_pnl_shadow_preimage_rows,
                     store_pnl_shadow_pointer
            TO unihub_runtime;
    END IF;
END
$$;

COMMENT ON TABLE store_pnl_shadow_generations IS
    'Immutable P&L shadow captures. Staging never mutates store_pnl_monthly.';
COMMENT ON TABLE store_pnl_shadow_preimage_rows IS
    'Exact P&L scope pre-image captured before any future separately approved promotion.';
COMMENT ON TABLE store_pnl_shadow_pointer IS
    'CAS-protected review pointer only; runtime P&L reads do not consume this table.';
