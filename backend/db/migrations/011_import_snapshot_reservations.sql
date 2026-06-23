ALTER TABLE import_snapshots
    ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS uq_import_snapshots_month_processing
    ON import_snapshots (import_month)
    WHERE status = 'processing';
