ALTER TABLE import_snapshots
    ADD COLUMN IF NOT EXISTS source_artifact_required BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS source_artifact_state TEXT,
    ADD COLUMN IF NOT EXISTS source_artifact_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS source_artifact_bytes BIGINT,
    ADD COLUMN IF NOT EXISTS source_artifact_retained_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS source_artifact_retained_path TEXT;

ALTER TABLE import_snapshots
    DROP CONSTRAINT IF EXISTS ck_import_snapshots_source_artifact_state,
    DROP CONSTRAINT IF EXISTS ck_import_snapshots_source_artifact_sha256,
    DROP CONSTRAINT IF EXISTS ck_import_snapshots_source_artifact_bytes;

ALTER TABLE import_snapshots
    ADD CONSTRAINT ck_import_snapshots_source_artifact_state CHECK (
        source_artifact_state IS NULL
        OR source_artifact_state IN ('artifact_retaining', 'artifact_retained', 'recovery_required')
    ),
    ADD CONSTRAINT ck_import_snapshots_source_artifact_sha256 CHECK (
        source_artifact_sha256 IS NULL OR source_artifact_sha256 ~ '^[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT ck_import_snapshots_source_artifact_bytes CHECK (
        source_artifact_bytes IS NULL OR source_artifact_bytes >= 0
    );

CREATE INDEX IF NOT EXISTS idx_import_snapshots_source_artifact_state
    ON import_snapshots (source_artifact_state, heartbeat_at);

CREATE OR REPLACE FUNCTION guard_sales_source_artifact_lifecycle()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.source_artifact_required
       AND NEW.status = 'completed'
       AND (
           NEW.source_artifact_state IS DISTINCT FROM 'artifact_retained'
           OR NEW.source_artifact_sha256 IS DISTINCT FROM NEW.source_sha256
           OR NEW.source_artifact_bytes IS NULL
           OR NEW.source_artifact_retained_at IS NULL
           OR NEW.source_artifact_retained_path IS NULL
       ) THEN
        RAISE EXCEPTION 'completed sales generation requires an exact retained source artifact';
    END IF;

    IF TG_OP = 'UPDATE'
       AND OLD.source_artifact_required
       AND NOT NEW.source_artifact_required THEN
        RAISE EXCEPTION 'required sales source artifact fence is immutable';
    END IF;

    IF TG_OP = 'UPDATE'
       AND OLD.source_artifact_state = 'artifact_retained'
       AND NOT (
           NEW.source_artifact_state = 'recovery_required'
           AND NEW.status = 'failed'
       )
       AND (
           NEW.source_artifact_state IS DISTINCT FROM OLD.source_artifact_state
           OR NEW.source_artifact_sha256 IS DISTINCT FROM OLD.source_artifact_sha256
           OR NEW.source_artifact_bytes IS DISTINCT FROM OLD.source_artifact_bytes
           OR NEW.source_artifact_retained_at IS DISTINCT FROM OLD.source_artifact_retained_at
           OR NEW.source_artifact_retained_path IS DISTINCT FROM OLD.source_artifact_retained_path
       ) THEN
        RAISE EXCEPTION 'retained sales source artifact metadata is immutable';
    END IF;

    IF NEW.source_artifact_state = 'artifact_retained'
       AND (
           NEW.source_artifact_sha256 IS DISTINCT FROM NEW.source_sha256
           OR NEW.source_artifact_bytes IS NULL
           OR NEW.source_artifact_retained_at IS NULL
           OR NEW.source_artifact_retained_path IS NULL
       ) THEN
        RAISE EXCEPTION 'retained sales source artifact metadata is incomplete';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_sales_source_artifact_lifecycle ON import_snapshots;
CREATE TRIGGER trg_sales_source_artifact_lifecycle
BEFORE INSERT OR UPDATE ON import_snapshots
FOR EACH ROW EXECUTE FUNCTION guard_sales_source_artifact_lifecycle();

CREATE OR REPLACE FUNCTION guard_sales_generation_head_source_artifact()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    artifact RECORD;
BEGIN
    SELECT source_artifact_required, source_sha256, source_artifact_state,
           source_artifact_sha256, source_artifact_bytes,
           source_artifact_retained_at, source_artifact_retained_path
    INTO artifact
    FROM import_snapshots
    WHERE id = NEW.snapshot_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'sales generation head references a missing snapshot';
    END IF;
    IF artifact.source_artifact_required
       AND (
           artifact.source_artifact_state IS DISTINCT FROM 'artifact_retained'
           OR artifact.source_artifact_sha256 IS DISTINCT FROM artifact.source_sha256
           OR artifact.source_artifact_bytes IS NULL
           OR artifact.source_artifact_retained_at IS NULL
           OR artifact.source_artifact_retained_path IS NULL
       ) THEN
        RAISE EXCEPTION 'sales generation head requires an exact retained source artifact';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_sales_generation_head_source_artifact
ON sales_generation_heads;
CREATE TRIGGER trg_sales_generation_head_source_artifact
BEFORE INSERT OR UPDATE OF snapshot_id ON sales_generation_heads
FOR EACH ROW EXECUTE FUNCTION guard_sales_generation_head_source_artifact();

GRANT SELECT, UPDATE ON TABLE import_snapshots TO unihub_sales_import;
