CREATE TABLE IF NOT EXISTS grile_store_projection_generations (
    run_month TEXT NOT NULL CHECK (run_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE CASCADE,
    next_generation BIGINT NOT NULL DEFAULT 0 CHECK (next_generation >= 0),
    PRIMARY KEY (run_month, site_code)
);

CREATE TABLE IF NOT EXISTS grile_run_store_generations (
    run_id INTEGER NOT NULL REFERENCES grile_runs(id) ON DELETE CASCADE,
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE RESTRICT,
    generation BIGINT NOT NULL CHECK (generation > 0),
    PRIMARY KEY (run_id, site_code)
);

CREATE TABLE IF NOT EXISTS grile_store_refreshes (
    id BIGSERIAL PRIMARY KEY,
    run_month TEXT NOT NULL CHECK (run_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE RESTRICT,
    generation BIGINT NOT NULL CHECK (generation > 0),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    requested_by_sub TEXT NOT NULL
        CHECK (char_length(btrim(requested_by_sub)) BETWEEN 1 AND 256),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_grile_store_refresh_active
    ON grile_store_refreshes (run_month, site_code)
    WHERE status IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS idx_grile_store_refresh_month_created
    ON grile_store_refreshes (run_month, created_at DESC);

CREATE TABLE IF NOT EXISTS grile_store_observations (
    id BIGSERIAL PRIMARY KEY,
    run_month TEXT NOT NULL CHECK (run_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE RESTRICT,
    source TEXT NOT NULL CHECK (source IN ('full', 'store')),
    source_run_id INTEGER REFERENCES grile_runs(id) ON DELETE CASCADE,
    store_refresh_id BIGINT REFERENCES grile_store_refreshes(id) ON DELETE CASCADE,
    generation BIGINT NOT NULL CHECK (generation > 0),
    completion_pct NUMERIC(5,1),
    last_edit TIMESTAMPTZ,
    grila_target NUMERIC(12,2),
    grila_sales NUMERIC(12,2),
    db_target NUMERIC(12,2),
    db_sales_mtd NUMERIC(12,2),
    db_max_sale_date DATE,
    fill_status TEXT,
    target_status TEXT,
    sales_status TEXT,
    tolerance NUMERIC(12,2),
    error_code TEXT,
    error_message TEXT,
    raw_summary JSONB,
    content_sha256 TEXT CHECK (content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'),
    checked_by_sub TEXT,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (source = 'full' AND source_run_id IS NOT NULL AND store_refresh_id IS NULL)
        OR (source = 'store' AND source_run_id IS NULL AND store_refresh_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_grile_store_observation_full_owner
    ON grile_store_observations (source_run_id, site_code)
    WHERE source = 'full';
CREATE UNIQUE INDEX IF NOT EXISTS uq_grile_store_observation_refresh_owner
    ON grile_store_observations (store_refresh_id)
    WHERE source = 'store';
CREATE INDEX IF NOT EXISTS idx_grile_store_observations_month_site_checked
    ON grile_store_observations (run_month, site_code, checked_at DESC);

ALTER TABLE grile_store_current_status
    ADD COLUMN IF NOT EXISTS generation BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS current_observation_id BIGINT REFERENCES grile_store_observations(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS last_success_observation_id BIGINT REFERENCES grile_store_observations(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS last_success_checked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_error_observation_id BIGINT REFERENCES grile_store_observations(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS last_error_generation BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_error_checked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_error_code TEXT,
    ADD COLUMN IF NOT EXISTS last_error_message TEXT;

UPDATE grile_store_current_status
SET last_success_checked_at = CASE
        WHEN error_code IS NULL THEN COALESCE(last_success_checked_at, checked_at)
        ELSE last_success_checked_at
    END,
    last_error_checked_at = CASE
        WHEN error_code IS NOT NULL AND last_error_checked_at IS NULL THEN checked_at
        ELSE last_error_checked_at
    END,
    last_error_code = COALESCE(last_error_code, error_code),
    last_error_message = COALESCE(last_error_message, error_message);

CREATE INDEX IF NOT EXISTS idx_grile_store_current_success_age
    ON grile_store_current_status (run_month, last_success_checked_at);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON TABLE grile_store_projection_generations,
                     grile_run_store_generations,
                     grile_store_refreshes
            TO unihub_runtime;
        GRANT SELECT, INSERT
            ON TABLE grile_store_observations
            TO unihub_runtime;
        GRANT USAGE, SELECT, UPDATE
            ON SEQUENCE grile_store_refreshes_id_seq,
                        grile_store_observations_id_seq
            TO unihub_runtime;
    END IF;
END
$$;

COMMENT ON TABLE grile_store_observations IS
    'Append-only Google/DB observations. Runtime has SELECT/INSERT only; no observation update or delete privilege.';
COMMENT ON TABLE grile_store_projection_generations IS
    'Monotonic per month/store fencing generation allocated before a full run or store refresh reads Google.';
COMMENT ON TABLE grile_store_current_status IS
    'Current projection of latest successful Grile observation; latest error metadata is intentionally separate.';
