ALTER TABLE grile_runs
    ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS uq_grile_runs_month_active
    ON grile_runs (run_month)
    WHERE status IN ('queued', 'running');
