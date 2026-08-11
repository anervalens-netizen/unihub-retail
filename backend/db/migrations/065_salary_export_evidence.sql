-- Authoritative evidence for sensitive salary exports.
--
-- Salary workbooks use the existing owner-bound durable export lifecycle. The
-- browser may select filters, but only the dedicated salary-export authority
-- can attest the artifact digest and its actual rendered row count.

ALTER TABLE export_operations
    DROP CONSTRAINT export_operations_kind_check,
    DROP CONSTRAINT export_operations_job_id_check,
    DROP CONSTRAINT export_operations_artifact_key_check;

ALTER TABLE export_operations
    ADD CONSTRAINT export_operations_kind_check CHECK (
        kind IN (
            'daily_metrics',
            'daily_comparison',
            'salary_store_summary',
            'salary_monthly_trend',
            'salary_agents'
        )
    ),
    ADD CONSTRAINT export_operations_job_id_check CHECK (
        (kind IN ('daily_metrics', 'daily_comparison')
            AND job_id ~ '^export-complex:[1-9][0-9]*$')
        OR (kind IN ('salary_store_summary', 'salary_monthly_trend', 'salary_agents')
            AND job_id ~ '^salary-export:[1-9][0-9]*$')
    ),
    ADD CONSTRAINT export_operations_artifact_key_check CHECK (
        artifact_key IS NULL
        OR (kind IN ('daily_metrics', 'daily_comparison')
            AND artifact_key ~ '^[0-9a-f]{32}\.xlsx$')
        OR (kind IN ('salary_store_summary', 'salary_monthly_trend', 'salary_agents')
            AND artifact_key ~ '^salary/[0-9a-f]{32}\.xlsx$')
    ),
    ADD COLUMN row_count BIGINT
        CHECK (row_count IS NULL OR row_count >= 0),
    ADD CONSTRAINT export_operations_salary_request_check CHECK (
        kind NOT IN ('salary_store_summary', 'salary_monthly_trend', 'salary_agents')
        OR (
            NOT (request_payload ? 'row_count')
            AND jsonb_typeof(request_payload -> 'site_code') = 'array'
            AND (
                (kind = 'salary_store_summary'
                    AND request_payload ->> 'export_kind' = 'store_summary')
                OR (kind = 'salary_monthly_trend'
                    AND request_payload ->> 'export_kind' = 'monthly_trend')
                OR (kind = 'salary_agents'
                    AND request_payload ->> 'export_kind' = 'agents')
            )
        )
    ),
    ADD CONSTRAINT export_operations_salary_row_count_check CHECK (
        row_count IS NULL
        OR (
            kind IN ('salary_store_summary', 'salary_monthly_trend', 'salary_agents')
            AND status IN ('completed', 'failed', 'expired')
            AND finished_at IS NOT NULL
        )
    ),
    ADD CONSTRAINT export_operations_completed_salary_row_count_check CHECK (
        kind NOT IN ('salary_store_summary', 'salary_monthly_trend', 'salary_agents')
        OR status <> 'completed'
        OR row_count IS NOT NULL
    );

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
               OR OLD.row_count IS DISTINCT FROM NEW.row_count
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
           OR OLD.row_count IS DISTINCT FROM NEW.row_count
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
