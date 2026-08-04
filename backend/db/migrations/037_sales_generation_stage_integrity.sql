ALTER TABLE import_snapshots
    ADD COLUMN IF NOT EXISTS stage_rows_sha256 TEXT;

ALTER TABLE import_snapshots
    DROP CONSTRAINT IF EXISTS ck_import_snapshots_stage_rows_sha256;

ALTER TABLE import_snapshots
    ADD CONSTRAINT ck_import_snapshots_stage_rows_sha256 CHECK (
        stage_rows_sha256 IS NULL
        OR stage_rows_sha256 ~ '^[0-9a-f]{64}$'
    );

CREATE OR REPLACE FUNCTION sales_stage_digest_scalar(p_value TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT CASE
        WHEN p_value IS NULL THEN 'N'
        ELSE 'V' || octet_length(p_value)::TEXT || ':' || p_value
    END
$$;

CREATE OR REPLACE FUNCTION sales_stage_rows_sha256(p_snapshot_id INTEGER)
RETURNS TEXT
LANGUAGE SQL
STABLE
STRICT
AS $$
    SELECT encode(
        digest(
            convert_to(
                COALESCE(
                    string_agg(
                        concat_ws(
                            E'\x1f',
                            sales_stage_digest_scalar(row_number::TEXT),
                            sales_stage_digest_scalar(import_month),
                            sales_stage_digest_scalar(sale_date::TEXT),
                            sales_stage_digest_scalar(site_code),
                            sales_stage_digest_scalar(locatie),
                            sales_stage_digest_scalar(firma),
                            sales_stage_digest_scalar(regional),
                            sales_stage_digest_scalar(asm),
                            sales_stage_digest_scalar(bon_nr),
                            sales_stage_digest_scalar(item_code),
                            sales_stage_digest_scalar(item_name),
                            sales_stage_digest_scalar(brand),
                            sales_stage_digest_scalar(category),
                            sales_stage_digest_scalar(subcategory),
                            sales_stage_digest_scalar(quantity::TEXT),
                            sales_stage_digest_scalar(unit_price::TEXT),
                            sales_stage_digest_scalar(total_value::TEXT),
                            sales_stage_digest_scalar(agent),
                            sales_stage_digest_scalar(is_cartela::TEXT),
                            sales_stage_digest_scalar(is_return::TEXT)
                        ),
                        E'\x1e'
                        ORDER BY row_number
                    ),
                    ''
                ),
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    )
    FROM sales_import_stage_rows
    WHERE snapshot_id = p_snapshot_id
$$;

DO $$
DECLARE
    legacy_snapshot RECORD;
    stage_count BIGINT;
    stage_store_count BIGINT;
    stage_total_quantity BIGINT;
    stage_total_value NUMERIC;
    stage_max_sale_date DATE;
BEGIN
    -- 036 manifests did not carry a full-stage digest.  Verify the controls
    -- they did persist before retaining a post-upgrade digest; a mismatch is a
    -- migration failure, never an implicit certification of old staging.
    FOR legacy_snapshot IN
        SELECT snapshot.id, snapshot.manifest
        FROM import_snapshots snapshot
        WHERE snapshot.manifest_sha256 IS NOT NULL
          AND snapshot.stage_rows_sha256 IS NULL
          AND EXISTS (
              SELECT 1
              FROM sales_import_stage_rows staged
              WHERE staged.snapshot_id = snapshot.id
          )
    LOOP
        SELECT COUNT(*),
               COUNT(DISTINCT site_code),
               COALESCE(SUM(quantity), 0),
               COALESCE(SUM(total_value), 0),
               MAX(sale_date)
        INTO stage_count,
             stage_store_count,
             stage_total_quantity,
             stage_total_value,
             stage_max_sale_date
        FROM sales_import_stage_rows
        WHERE snapshot_id = legacy_snapshot.id;

        IF legacy_snapshot.manifest IS NULL
           OR legacy_snapshot.manifest->>'rows_imported' IS NULL
           OR legacy_snapshot.manifest->>'store_count' IS NULL
           OR legacy_snapshot.manifest->>'total_quantity' IS NULL
           OR legacy_snapshot.manifest->>'total_value' IS NULL
           OR legacy_snapshot.manifest->>'max_sale_date' IS NULL
           OR stage_count <> (legacy_snapshot.manifest->>'rows_imported')::BIGINT
           OR stage_store_count <> (legacy_snapshot.manifest->>'store_count')::BIGINT
           OR stage_total_quantity <> (legacy_snapshot.manifest->>'total_quantity')::BIGINT
           OR stage_total_value <> (legacy_snapshot.manifest->>'total_value')::NUMERIC
           OR stage_max_sale_date::TEXT IS DISTINCT FROM legacy_snapshot.manifest->>'max_sale_date'
        THEN
            RAISE EXCEPTION
                'migration 037 cannot certify legacy sales staging for snapshot % against its manifest controls',
                legacy_snapshot.id;
        END IF;
    END LOOP;
END
$$;

UPDATE import_snapshots snapshot
SET stage_rows_sha256 = sales_stage_rows_sha256(snapshot.id)
WHERE snapshot.manifest_sha256 IS NOT NULL
  AND snapshot.stage_rows_sha256 IS NULL
  AND EXISTS (
      SELECT 1
      FROM sales_import_stage_rows staged
      WHERE staged.snapshot_id = snapshot.id
  );

CREATE OR REPLACE FUNCTION guard_import_snapshot_sales_provenance()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    actual_digest TEXT;
    manifest_digest TEXT;
    source_digest TEXT;
    rollback_source_id INTEGER;
    stage_count BIGINT;
BEGIN
    IF OLD.manifest_sha256 IS NULL AND NEW.manifest_sha256 IS NOT NULL THEN
        SELECT COUNT(*), sales_stage_rows_sha256(NEW.id)
        INTO stage_count, actual_digest
        FROM sales_import_stage_rows
        WHERE snapshot_id = NEW.id;

        IF stage_count <= 0 THEN
            RAISE EXCEPTION
                'validated sales generation % has no staged rows',
                NEW.id;
        END IF;
        manifest_digest := NEW.manifest->>'stage_rows_sha256';
        IF manifest_digest IS NULL
           OR manifest_digest !~ '^[0-9a-f]{64}$'
           OR manifest_digest IS DISTINCT FROM actual_digest THEN
            RAISE EXCEPTION
                'validated sales manifest for snapshot % does not match staged rows',
                NEW.id;
        END IF;
        NEW.stage_rows_sha256 := actual_digest;
    ELSIF OLD.manifest_sha256 IS NOT NULL THEN
        IF NEW.import_month IS DISTINCT FROM OLD.import_month
           OR NEW.source_sha256 IS DISTINCT FROM OLD.source_sha256
           OR NEW.cutoff_date IS DISTINCT FROM OLD.cutoff_date
           OR NEW.manifest_sha256 IS DISTINCT FROM OLD.manifest_sha256
           OR NEW.generation_token IS DISTINCT FROM OLD.generation_token
           OR (NEW.manifest - 'generation_state')
                IS DISTINCT FROM (OLD.manifest - 'generation_state') THEN
            RAISE EXCEPTION
                'validated sales provenance for snapshot % is immutable',
                OLD.id;
        END IF;

        IF NEW.stage_rows_sha256 IS DISTINCT FROM OLD.stage_rows_sha256 THEN
            IF OLD.stage_rows_sha256 IS NOT NULL THEN
                RAISE EXCEPTION
                    'stage digest for snapshot % is immutable',
                    OLD.id;
            END IF;

            BEGIN
                rollback_source_id :=
                    NULLIF(NEW.manifest->>'rollback_source_snapshot_id', '')::INTEGER;
            EXCEPTION
                WHEN invalid_text_representation THEN
                    RAISE EXCEPTION
                        'rollback source for snapshot % is invalid',
                        OLD.id;
            END;

            IF rollback_source_id IS NULL THEN
                RAISE EXCEPTION
                    'stage digest for snapshot % cannot be assigned manually',
                    OLD.id;
            END IF;

            SELECT stage_rows_sha256
            INTO source_digest
            FROM import_snapshots
            WHERE id = rollback_source_id;

            SELECT COUNT(*), sales_stage_rows_sha256(NEW.id)
            INTO stage_count, actual_digest
            FROM sales_import_stage_rows
            WHERE snapshot_id = NEW.id;

            IF stage_count <= 0
               OR source_digest IS NULL
               OR NEW.stage_rows_sha256 IS DISTINCT FROM source_digest
               OR actual_digest IS DISTINCT FROM source_digest THEN
                RAISE EXCEPTION
                    'rollback staging for snapshot % does not match source %',
                    OLD.id,
                    rollback_source_id;
            END IF;
        END IF;

        IF NEW.manifest->>'generation_state'
           NOT IN ('validated', 'promoting', 'promoted') THEN
            RAISE EXCEPTION
                'sales generation state for snapshot % is invalid',
                OLD.id;
        END IF;
    END IF;

    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_import_snapshot_sales_provenance
    ON import_snapshots;

CREATE TRIGGER trg_import_snapshot_sales_provenance
    BEFORE UPDATE ON import_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION guard_import_snapshot_sales_provenance();

CREATE OR REPLACE FUNCTION sales_snapshot_is_retained(p_snapshot_id INTEGER)
RETURNS BOOLEAN
LANGUAGE SQL
STABLE
STRICT
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM sales_generation_heads head
        WHERE head.snapshot_id = p_snapshot_id

        UNION ALL

        SELECT 1
        FROM sales_generation_heads head
        JOIN import_snapshots current_snapshot
          ON current_snapshot.id = head.snapshot_id
        WHERE current_snapshot.previous_snapshot_id = p_snapshot_id
    )
$$;

CREATE OR REPLACE FUNCTION guard_sales_stage_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target_snapshot_id INTEGER;
    stored_digest TEXT;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'sales staging rows are append-only';
    END IF;

    target_snapshot_id := CASE
        WHEN TG_OP = 'DELETE' THEN OLD.snapshot_id
        ELSE NEW.snapshot_id
    END;

    SELECT stage_rows_sha256
    INTO stored_digest
    FROM import_snapshots
    WHERE id = target_snapshot_id;

    IF TG_OP = 'INSERT' AND stored_digest IS NOT NULL THEN
        RAISE EXCEPTION
            'validated sales staging for snapshot % is immutable',
            target_snapshot_id;
    END IF;

    IF TG_OP = 'DELETE'
       AND sales_snapshot_is_retained(target_snapshot_id) THEN
        RAISE EXCEPTION
            'retained sales staging for snapshot % is immutable',
            target_snapshot_id;
    END IF;

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END
$$;

DROP TRIGGER IF EXISTS trg_sales_stage_mutation
    ON sales_import_stage_rows;

CREATE TRIGGER trg_sales_stage_mutation
    BEFORE INSERT OR UPDATE OR DELETE ON sales_import_stage_rows
    FOR EACH ROW
    EXECUTE FUNCTION guard_sales_stage_mutation();

CREATE OR REPLACE FUNCTION verify_sales_generation_head_target()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    actual_digest TEXT;
    stored_digest TEXT;
    manifest_digest TEXT;
    source_digest TEXT;
    manifest_payload JSONB;
    rollback_source_id INTEGER;
    stage_count BIGINT;
BEGIN
    IF TG_OP = 'UPDATE'
       AND NEW.snapshot_id IS NOT DISTINCT FROM OLD.snapshot_id THEN
        RETURN NEW;
    END IF;

    SELECT manifest, stage_rows_sha256
    INTO manifest_payload, stored_digest
    FROM import_snapshots
    WHERE id = NEW.snapshot_id
    FOR UPDATE;

    IF NOT FOUND OR manifest_payload IS NULL THEN
        RAISE EXCEPTION
            'sales head target snapshot % is not validated',
            NEW.snapshot_id;
    END IF;
    manifest_digest := manifest_payload->>'stage_rows_sha256';

    SELECT COUNT(*), sales_stage_rows_sha256(NEW.snapshot_id)
    INTO stage_count, actual_digest
    FROM sales_import_stage_rows
    WHERE snapshot_id = NEW.snapshot_id;

    IF stored_digest IS NULL THEN
        BEGIN
            rollback_source_id :=
                NULLIF(manifest_payload->>'rollback_source_snapshot_id', '')::INTEGER;
        EXCEPTION
            WHEN invalid_text_representation THEN
                RAISE EXCEPTION
                    'sales head target snapshot % has invalid rollback source',
                    NEW.snapshot_id;
        END;

        IF rollback_source_id IS NULL THEN
            RAISE EXCEPTION
                'sales head target snapshot % has no validated stage digest',
                NEW.snapshot_id;
        END IF;

        SELECT stage_rows_sha256
        INTO source_digest
        FROM import_snapshots
        WHERE id = rollback_source_id;

        IF stage_count <= 0
           OR source_digest IS NULL
           OR manifest_digest IS DISTINCT FROM source_digest
           OR actual_digest IS DISTINCT FROM source_digest THEN
            RAISE EXCEPTION
                'rollback snapshot % differs from retained source %',
                NEW.snapshot_id,
                rollback_source_id;
        END IF;

        UPDATE import_snapshots
        SET stage_rows_sha256 = actual_digest
        WHERE id = NEW.snapshot_id
          AND stage_rows_sha256 IS NULL;

        stored_digest := actual_digest;
    END IF;

    IF stage_count <= 0
       OR (manifest_digest IS NOT NULL AND manifest_digest IS DISTINCT FROM stored_digest)
       OR actual_digest IS DISTINCT FROM stored_digest THEN
        RAISE EXCEPTION
            'sales head target snapshot % staging digest mismatch',
            NEW.snapshot_id;
    END IF;

    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_verify_sales_generation_head_target
    ON sales_generation_heads;

CREATE TRIGGER trg_verify_sales_generation_head_target
    BEFORE INSERT OR UPDATE OF snapshot_id ON sales_generation_heads
    FOR EACH ROW
    EXECUTE FUNCTION verify_sales_generation_head_target();

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        REVOKE UPDATE ON TABLE sales_import_stage_rows FROM unihub_runtime;
    END IF;
END
$$;

COMMENT ON COLUMN import_snapshots.stage_rows_sha256 IS
    'Canonical digest of staged sales rows captured at validation and cryptographically bound by the approved manifest.';

COMMENT ON FUNCTION sales_stage_rows_sha256(INTEGER) IS
    'Canonical SHA-256 over every staged sales field in row_number order; scalar encoding matches services.sales_generation.';

COMMENT ON TRIGGER trg_verify_sales_generation_head_target
    ON sales_generation_heads IS
    'Prevents promote/rollback when staged rows differ from the validated or retained generation.';
