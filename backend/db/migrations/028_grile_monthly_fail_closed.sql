ALTER TABLE grile_monthly_operations
    ADD COLUMN IF NOT EXISTS requested_by_sub TEXT,
    ADD COLUMN IF NOT EXISTS approved_manifest_id BIGINT;

ALTER TABLE grile_monthly_operations
    ADD CONSTRAINT ck_grile_monthly_requested_by_sub
    CHECK (
        requested_by_sub IS NULL
        OR char_length(btrim(requested_by_sub)) BETWEEN 1 AND 256
    ) NOT VALID;

CREATE TABLE IF NOT EXISTS grile_monthly_manifests (
    id BIGSERIAL PRIMARY KEY,
    operation_id INTEGER NOT NULL UNIQUE
        REFERENCES grile_monthly_operations(id) ON DELETE CASCADE,
    closing_month TEXT NOT NULL
        CHECK (closing_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    operation TEXT NOT NULL
        CHECK (operation IN ('finalize', 'archive', 'reset')),
    status TEXT NOT NULL DEFAULT 'building'
        CHECK (status IN (
            'building', 'failed', 'verified', 'approved', 'consumed',
            'rolled_back', 'uncertain'
        )),
    expected_store_count INTEGER NOT NULL DEFAULT 0
        CHECK (expected_store_count >= 0),
    processed_store_count INTEGER NOT NULL DEFAULT 0
        CHECK (processed_store_count >= 0),
    expected_agent_count INTEGER NOT NULL DEFAULT 0
        CHECK (expected_agent_count >= 0),
    processed_agent_count INTEGER NOT NULL DEFAULT 0
        CHECK (processed_agent_count >= 0),
    error_count INTEGER NOT NULL DEFAULT 0
        CHECK (error_count >= 0),
    control_totals JSONB NOT NULL DEFAULT '{}'::jsonb,
    artifacts JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_backups JSONB NOT NULL DEFAULT '[]'::jsonb,
    manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    manifest_sha256 TEXT,
    requested_by_sub TEXT NOT NULL
        CHECK (char_length(btrim(requested_by_sub)) BETWEEN 1 AND 256),
    approved_by_sub TEXT,
    approved_at TIMESTAMPTZ,
    error_code TEXT,
    verified_at TIMESTAMPTZ,
    consumed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (approved_by_sub IS NULL AND approved_at IS NULL)
        OR (
            char_length(btrim(approved_by_sub)) BETWEEN 1 AND 256
            AND approved_at IS NOT NULL
        )
    ),
    CHECK (manifest_sha256 IS NULL OR manifest_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS idx_grile_monthly_manifests_month_created
    ON grile_monthly_manifests (closing_month, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_grile_monthly_manifests_status
    ON grile_monthly_manifests (closing_month, operation, status);

ALTER TABLE grile_monthly_operations
    ADD CONSTRAINT fk_grile_monthly_approved_manifest
    FOREIGN KEY (approved_manifest_id)
    REFERENCES grile_monthly_manifests(id);

ALTER TABLE grile_monthly_reset_items
    ADD COLUMN IF NOT EXISTS backup_path TEXT,
    ADD COLUMN IF NOT EXISTS backup_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS rollback_status TEXT,
    ADD COLUMN IF NOT EXISTS restored_at TIMESTAMPTZ;

ALTER TABLE grile_monthly_reset_items
    ADD CONSTRAINT ck_grile_reset_backup_sha256
    CHECK (backup_sha256 IS NULL OR backup_sha256 ~ '^[0-9a-f]{64}$') NOT VALID,
    ADD CONSTRAINT ck_grile_reset_rollback_status
    CHECK (rollback_status IS NULL OR rollback_status IN ('restored', 'failed')) NOT VALID;

-- The migration owner creates the manifest objects, while backend and worker
-- connections use the established least-privilege runtime role.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON TABLE grile_monthly_manifests TO unihub_runtime;
        GRANT USAGE, SELECT, UPDATE
            ON SEQUENCE grile_monthly_manifests_id_seq TO unihub_runtime;
    END IF;
END
$$;
