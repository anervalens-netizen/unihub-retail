ALTER TABLE import_snapshots
    ADD COLUMN IF NOT EXISTS source_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS cutoff_date DATE,
    ADD COLUMN IF NOT EXISTS manifest JSONB,
    ADD COLUMN IF NOT EXISTS manifest_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS generation_token UUID,
    ADD COLUMN IF NOT EXISTS owner_id UUID,
    ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS expected_head_revision BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS previous_snapshot_id INTEGER REFERENCES import_snapshots(id),
    ADD COLUMN IF NOT EXISTS promoted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS approved_by_sub TEXT,
    ADD COLUMN IF NOT EXISTS override_reason TEXT,
    ADD COLUMN IF NOT EXISTS source_spool_path TEXT;

ALTER TABLE import_snapshots
    DROP CONSTRAINT IF EXISTS ck_import_snapshots_source_sha256,
    DROP CONSTRAINT IF EXISTS ck_import_snapshots_manifest_sha256,
    DROP CONSTRAINT IF EXISTS ck_import_snapshots_approval;

ALTER TABLE import_snapshots
    ADD CONSTRAINT ck_import_snapshots_source_sha256 CHECK (
        source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT ck_import_snapshots_manifest_sha256 CHECK (
        manifest_sha256 IS NULL OR manifest_sha256 ~ '^[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT ck_import_snapshots_approval CHECK (
        approved_by_sub IS NULL
        OR char_length(btrim(approved_by_sub)) BETWEEN 1 AND 256
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_import_snapshots_generation_token
    ON import_snapshots (generation_token)
    WHERE generation_token IS NOT NULL;

CREATE TABLE IF NOT EXISTS sales_import_stage_rows (
    snapshot_id INTEGER NOT NULL REFERENCES import_snapshots(id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL CHECK (row_number > 0),
    import_month TEXT NOT NULL CHECK (import_month ~ '^[0-9]{4}-[0-9]{2}$'),
    sale_date DATE NOT NULL,
    site_code TEXT NOT NULL,
    locatie TEXT NOT NULL,
    firma TEXT NOT NULL,
    regional TEXT NOT NULL,
    asm TEXT NOT NULL,
    bon_nr TEXT NOT NULL,
    item_code TEXT NOT NULL,
    item_name TEXT NOT NULL,
    brand TEXT,
    category TEXT,
    subcategory TEXT,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    total_value NUMERIC(10, 2) NOT NULL,
    agent TEXT NOT NULL,
    is_cartela BOOLEAN NOT NULL,
    is_return BOOLEAN NOT NULL,
    PRIMARY KEY (snapshot_id, row_number)
);

CREATE INDEX IF NOT EXISTS idx_sales_import_stage_month_site_day
    ON sales_import_stage_rows (import_month, site_code, sale_date);

CREATE TABLE IF NOT EXISTS sales_generation_heads (
    import_month TEXT PRIMARY KEY CHECK (import_month ~ '^[0-9]{4}-[0-9]{2}$'),
    snapshot_id INTEGER NOT NULL REFERENCES import_snapshots(id),
    revision BIGINT NOT NULL CHECK (revision > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sales_generation_promotions (
    id BIGSERIAL PRIMARY KEY,
    import_month TEXT NOT NULL CHECK (import_month ~ '^[0-9]{4}-[0-9]{2}$'),
    from_snapshot_id INTEGER REFERENCES import_snapshots(id),
    to_snapshot_id INTEGER NOT NULL REFERENCES import_snapshots(id),
    head_revision BIGINT NOT NULL CHECK (head_revision > 0),
    action TEXT NOT NULL CHECK (action IN ('promote', 'rollback')),
    requested_by_sub TEXT NOT NULL
        CHECK (char_length(btrim(requested_by_sub)) BETWEEN 1 AND 256),
    override_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sales_generation_promotions_month_created
    ON sales_generation_promotions (import_month, created_at DESC);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON TABLE sales_import_stage_rows,
                     sales_generation_heads,
                     sales_generation_promotions
            TO unihub_runtime;
        GRANT USAGE, SELECT, UPDATE
            ON SEQUENCE sales_generation_promotions_id_seq
            TO unihub_runtime;
    END IF;
END
$$;

COMMENT ON TABLE sales_import_stage_rows IS
    'Validated immutable sales facts for the current and previous rollback generation.';
COMMENT ON TABLE sales_generation_heads IS
    'CAS-fenced pointer to the generation materialized in sales_transactions.';
COMMENT ON TABLE sales_generation_promotions IS
    'Immutable audit ledger for promote and rollback decisions.';
