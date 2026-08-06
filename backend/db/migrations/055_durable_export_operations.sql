-- Durable lifecycle for charted/complex XLSX exports.
--
-- The web process reserves an owner-bound operation before publishing ARQ.
-- The operations worker claims it with an epoch/lease fence and may publish a
-- private artifact only through the matching running generation.

CREATE TABLE export_operations (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('daily_metrics', 'daily_comparison')),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'expired')),
    job_id TEXT NOT NULL UNIQUE
        CHECK (job_id ~ '^export-complex:[1-9][0-9]*$'),
    request_payload JSONB NOT NULL CHECK (jsonb_typeof(request_payload) = 'object'),
    request_sha256 TEXT NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    requested_by_sub TEXT NOT NULL CHECK (btrim(requested_by_sub) <> ''),
    execution_owner TEXT,
    execution_epoch BIGINT NOT NULL DEFAULT 0 CHECK (execution_epoch >= 0),
    execution_lease_until TIMESTAMPTZ,
    artifact_key TEXT UNIQUE
        CHECK (artifact_key IS NULL OR artifact_key ~ '^[0-9a-f]{32}\.xlsx$'),
    artifact_sha256 TEXT
        CHECK (artifact_sha256 IS NULL OR artifact_sha256 ~ '^[0-9a-f]{64}$'),
    artifact_size BIGINT CHECK (artifact_size IS NULL OR artifact_size > 0),
    peak_rss_bytes BIGINT CHECK (peak_rss_bytes IS NULL OR peak_rss_bytes > 0),
    build_seconds DOUBLE PRECISION CHECK (build_seconds IS NULL OR build_seconds >= 0),
    cell_count BIGINT CHECK (cell_count IS NULL OR cell_count >= 0),
    download_filename TEXT
        CHECK (download_filename IS NULL OR (btrim(download_filename) <> '' AND length(download_filename) <= 140)),
    error_code TEXT
        CHECK (error_code IS NULL OR error_code ~ '^[a-z0-9_]{1,80}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    download_claimed_at TIMESTAMPTZ,
    CHECK (
        (status = 'queued'
            AND execution_owner IS NULL
            AND execution_lease_until IS NULL
            AND started_at IS NULL
            AND finished_at IS NULL)
        OR (status = 'running'
            AND NULLIF(btrim(execution_owner), '') IS NOT NULL
            AND execution_epoch > 0
            AND execution_lease_until IS NOT NULL
            AND started_at IS NOT NULL
            AND finished_at IS NULL)
        OR (status IN ('completed', 'failed', 'cancelled', 'expired')
            AND finished_at IS NOT NULL
            AND execution_lease_until IS NULL)
    ),
    CHECK (
        (status = 'completed'
            AND artifact_key IS NOT NULL
            AND artifact_sha256 IS NOT NULL
            AND artifact_size IS NOT NULL
            AND peak_rss_bytes IS NOT NULL
            AND build_seconds IS NOT NULL
            AND cell_count IS NOT NULL
            AND download_filename IS NOT NULL
            AND expires_at IS NOT NULL
            AND expires_at > finished_at
            AND error_code IS NULL)
        OR (status <> 'completed' AND artifact_key IS NULL)
    )
);

CREATE INDEX idx_export_operations_owner_created
    ON export_operations (requested_by_sub, created_at DESC);
CREATE INDEX idx_export_operations_active
    ON export_operations (status, created_at)
    WHERE status IN ('queued', 'running');
CREATE UNIQUE INDEX uq_export_operations_owner_active
    ON export_operations (requested_by_sub)
    WHERE status IN ('queued', 'running');
CREATE INDEX idx_export_operations_expiry
    ON export_operations (expires_at)
    WHERE status = 'completed';

CREATE OR REPLACE FUNCTION public.guard_export_operation_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'export operation evidence cannot be deleted';
    END IF;
    IF OLD.id IS DISTINCT FROM NEW.id
       OR OLD.kind IS DISTINCT FROM NEW.kind
       OR OLD.job_id IS DISTINCT FROM NEW.job_id
       OR OLD.request_payload IS DISTINCT FROM NEW.request_payload
       OR OLD.request_sha256 IS DISTINCT FROM NEW.request_sha256
       OR OLD.requested_by_sub IS DISTINCT FROM NEW.requested_by_sub
       OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
        RAISE EXCEPTION 'export operation identity and request are immutable';
    END IF;

    IF OLD.status IN ('failed', 'cancelled', 'expired') THEN
        RAISE EXCEPTION 'terminal export operation is immutable';
    END IF;
    IF OLD.status = 'completed' THEN
        IF NEW.status = 'completed' THEN
            IF OLD.download_claimed_at IS NOT NULL
               OR NEW.download_claimed_at IS NULL
               OR OLD.execution_owner IS DISTINCT FROM NEW.execution_owner
               OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
               OR OLD.execution_lease_until IS DISTINCT FROM NEW.execution_lease_until
               OR OLD.artifact_key IS DISTINCT FROM NEW.artifact_key
               OR OLD.artifact_sha256 IS DISTINCT FROM NEW.artifact_sha256
               OR OLD.artifact_size IS DISTINCT FROM NEW.artifact_size
               OR OLD.peak_rss_bytes IS DISTINCT FROM NEW.peak_rss_bytes
               OR OLD.build_seconds IS DISTINCT FROM NEW.build_seconds
               OR OLD.cell_count IS DISTINCT FROM NEW.cell_count
               OR OLD.download_filename IS DISTINCT FROM NEW.download_filename
               OR OLD.error_code IS DISTINCT FROM NEW.error_code
               OR OLD.started_at IS DISTINCT FROM NEW.started_at
               OR OLD.finished_at IS DISTINCT FROM NEW.finished_at
               OR OLD.expires_at IS DISTINCT FROM NEW.expires_at THEN
                RAISE EXCEPTION 'completed export operation accepts one download claim only';
            END IF;
        ELSIF NEW.status NOT IN ('expired', 'failed')
           OR NEW.artifact_key IS NOT NULL
           OR OLD.artifact_sha256 IS DISTINCT FROM NEW.artifact_sha256
           OR OLD.artifact_size IS DISTINCT FROM NEW.artifact_size
           OR OLD.peak_rss_bytes IS DISTINCT FROM NEW.peak_rss_bytes
           OR OLD.build_seconds IS DISTINCT FROM NEW.build_seconds
           OR OLD.cell_count IS DISTINCT FROM NEW.cell_count
           OR OLD.download_filename IS DISTINCT FROM NEW.download_filename
           OR OLD.finished_at IS DISTINCT FROM NEW.finished_at
           OR OLD.expires_at IS DISTINCT FROM NEW.expires_at
           OR OLD.download_claimed_at IS DISTINCT FROM NEW.download_claimed_at
           OR (NEW.status = 'failed' AND NEW.error_code IS DISTINCT FROM 'artifact_integrity_failed')
           OR (NEW.status = 'expired' AND NEW.error_code IS NOT NULL) THEN
            RAISE EXCEPTION 'completed export operation accepts only expiry or attested integrity failure';
        END IF;
    END IF;
    IF OLD.status = 'queued' AND NEW.status NOT IN ('queued', 'running', 'failed', 'cancelled') THEN
        RAISE EXCEPTION 'invalid queued export transition';
    END IF;
    IF OLD.status = 'running' AND NEW.status NOT IN ('running', 'completed', 'failed', 'cancelled') THEN
        RAISE EXCEPTION 'invalid running export transition';
    END IF;
    IF OLD.status = 'running' AND NEW.status = 'running'
       AND (OLD.execution_owner IS DISTINCT FROM NEW.execution_owner
            OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch) THEN
        RAISE EXCEPTION 'running export fence is immutable';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_export_operations_transition
BEFORE UPDATE OR DELETE ON export_operations
FOR EACH ROW EXECUTE FUNCTION public.guard_export_operation_transition();

REVOKE ALL ON TABLE export_operations FROM PUBLIC;
REVOKE ALL ON SEQUENCE export_operations_id_seq FROM PUBLIC;

GRANT SELECT ON TABLE export_operations TO unihub_web_read, unihub_operations;
GRANT INSERT ON TABLE export_operations TO unihub_business_write;
GRANT UPDATE (status, artifact_key, error_code, updated_at, finished_at, execution_lease_until, download_claimed_at)
    ON TABLE export_operations TO unihub_business_write;
GRANT SELECT, UPDATE ON TABLE export_operations TO unihub_operations;
GRANT USAGE, SELECT ON SEQUENCE export_operations_id_seq
    TO unihub_business_write, unihub_operations;
