ALTER TABLE grile_runs
    ADD COLUMN IF NOT EXISTS triggered_by_sub TEXT;

CREATE TABLE IF NOT EXISTS grile_agent_target_sync_runs (
    id BIGSERIAL PRIMARY KEY,
    run_month TEXT NOT NULL CHECK (run_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    mode TEXT NOT NULL CHECK (mode IN ('dry_run', 'sync')),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    job_id TEXT,
    requested_by_sub TEXT NOT NULL
        CHECK (char_length(btrim(requested_by_sub)) BETWEEN 1 AND 256),
    before_sha256 TEXT,
    after_sha256 TEXT,
    before_count INTEGER,
    after_count INTEGER,
    diff JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP INDEX IF EXISTS uq_grile_agent_target_sync_month_active;

CREATE UNIQUE INDEX uq_grile_agent_target_sync_month_active
    ON grile_agent_target_sync_runs (run_month, mode)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS idx_grile_agent_target_sync_month_created
    ON grile_agent_target_sync_runs (run_month, created_at DESC);

-- Migrations run as the owner while API and worker connections use the
-- least-privilege runtime role. Keep the new audit lifecycle usable without
-- broadening privileges on unrelated objects.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON TABLE grile_agent_target_sync_runs TO unihub_runtime;
        GRANT USAGE, SELECT, UPDATE
            ON SEQUENCE grile_agent_target_sync_runs_id_seq TO unihub_runtime;
    END IF;
END
$$;
