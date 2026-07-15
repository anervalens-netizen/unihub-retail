ALTER TABLE import_snapshots
    ADD COLUMN IF NOT EXISTS coverage_report JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS store_activity_events (
    id BIGSERIAL PRIMARY KEY,
    site_code TEXT NOT NULL REFERENCES stores(site_code),
    previous_is_active BOOLEAN NOT NULL,
    new_is_active BOOLEAN NOT NULL,
    reason TEXT NOT NULL CHECK (char_length(btrim(reason)) BETWEEN 10 AND 500),
    requested_by_sub TEXT NOT NULL CHECK (char_length(btrim(requested_by_sub)) BETWEEN 1 AND 256),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (previous_is_active IS DISTINCT FROM new_is_active)
);

CREATE INDEX IF NOT EXISTS idx_store_activity_events_site_created
    ON store_activity_events (site_code, created_at DESC);

-- Production migrations run as the owner while web/worker use the established
-- least-privilege role.  Grant the new objects in the same migration so the
-- explicit activity endpoint is usable immediately after rollout.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON TABLE store_activity_events TO unihub_runtime;
        GRANT USAGE, SELECT, UPDATE
            ON SEQUENCE store_activity_events_id_seq TO unihub_runtime;
    END IF;
END
$$;
