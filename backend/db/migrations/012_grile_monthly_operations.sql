CREATE TABLE IF NOT EXISTS grile_monthly_operations (
    id                 SERIAL PRIMARY KEY,
    op                 TEXT NOT NULL CHECK (op IN ('finalize', 'archive', 'reset')),
    closing_month      TEXT NOT NULL,
    only_filter        TEXT,
    dry_run            BOOLEAN NOT NULL DEFAULT true,
    status             TEXT NOT NULL DEFAULT 'queued'
                         CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    job_id             TEXT,
    triggered_by_email TEXT,
    result             JSONB,
    error_message      TEXT,
    started_at         TIMESTAMPTZ,
    heartbeat_at       TIMESTAMPTZ,
    finished_at        TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_grile_monthly_operations_month_active
    ON grile_monthly_operations (closing_month)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS idx_grile_monthly_operations_month_created
    ON grile_monthly_operations (closing_month, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_grile_monthly_reset_live_completed
    ON grile_monthly_operations (closing_month, COALESCE(only_filter, ''))
    WHERE op = 'reset' AND dry_run = false AND status = 'completed';

CREATE TABLE IF NOT EXISTS grile_monthly_reset_items (
    id              SERIAL PRIMARY KEY,
    operation_id    INT NOT NULL REFERENCES grile_monthly_operations(id) ON DELETE CASCADE,
    closing_month   TEXT NOT NULL,
    next_month      TEXT NOT NULL,
    site_code       TEXT NOT NULL,
    sheet_id        TEXT NOT NULL,
    company         TEXT NOT NULL,
    store           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'error', 'uncertain', 'skipped')),
    ranges          JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (operation_id, site_code)
);

CREATE INDEX IF NOT EXISTS idx_grile_monthly_reset_items_month_site
    ON grile_monthly_reset_items (closing_month, site_code);

CREATE INDEX IF NOT EXISTS idx_grile_monthly_reset_items_status
    ON grile_monthly_reset_items (closing_month, status);
