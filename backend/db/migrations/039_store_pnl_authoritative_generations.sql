-- Finance-authorized P&L Stage -> Validate -> Promote boundary.
--
-- This migration deliberately does not change schema_v2.sql.  The migration
-- manifest is maintained only by the integrating release lane.

CREATE TABLE store_pnl_generations (
    id UUID PRIMARY KEY,
    operation TEXT NOT NULL CHECK (operation IN ('promote', 'rollback')),
    authority_manifest_sha256 TEXT NOT NULL
        CHECK (authority_manifest_sha256 ~ '^[0-9a-f]{64}$'),
    authority_manifest JSONB NOT NULL,
    generation_manifest_sha256 TEXT NOT NULL UNIQUE
        CHECK (generation_manifest_sha256 ~ '^[0-9a-f]{64}$'),
    generation_manifest JSONB NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('building', 'staged', 'promoted')),
    inverse_of_generation_id UUID
        REFERENCES store_pnl_generations(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_at TIMESTAMPTZ
);

CREATE TABLE store_pnl_generation_scopes (
    generation_id UUID NOT NULL
        REFERENCES store_pnl_generations(id) ON DELETE RESTRICT,
    company_name TEXT NOT NULL CHECK (company_name IN ('Mobicell', 'Mobiup')),
    period DATE NOT NULL CHECK (period = date_trunc('month', period)::date),
    revision_id TEXT NOT NULL CHECK (btrim(revision_id) <> ''),
    parent_revision_id TEXT NOT NULL CHECK (btrim(parent_revision_id) <> ''),
    cutoff DATE NOT NULL,
    source_path TEXT NOT NULL CHECK (source_path !~ '(^|/)\.\.(/|$)'),
    source_sha256 TEXT NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    candidate_rows_sha256 TEXT NOT NULL
        CHECK (candidate_rows_sha256 ~ '^[0-9a-f]{64}$'),
    candidate_coverage_sha256 TEXT NOT NULL
        CHECK (candidate_coverage_sha256 ~ '^[0-9a-f]{64}$'),
    candidate_row_count INTEGER NOT NULL CHECK (candidate_row_count >= 0),
    candidate_total_amount NUMERIC(16, 2) NOT NULL,
    preimage_sha256 TEXT NOT NULL CHECK (preimage_sha256 ~ '^[0-9a-f]{64}$'),
    expected_head_revision BIGINT NOT NULL CHECK (expected_head_revision >= 0),
    PRIMARY KEY (generation_id, company_name, period)
);

CREATE TABLE store_pnl_generation_rows (
    generation_id UUID NOT NULL
        REFERENCES store_pnl_generations(id) ON DELETE RESTRICT,
    row_set TEXT NOT NULL CHECK (row_set IN ('candidate', 'preimage')),
    company_name TEXT NOT NULL CHECK (company_name IN ('Mobicell', 'Mobiup')),
    period DATE NOT NULL CHECK (period = date_trunc('month', period)::date),
    source_site_code TEXT NOT NULL,
    source_location_name TEXT NOT NULL,
    category_code TEXT NOT NULL CHECK (
        category_code IN ('v1', 'v11', 'v2', 'v3', 'c1', 'c11', 'c2', 'c3', 'c4', 'c5', 'c6', 'a1')
    ),
    category_name TEXT NOT NULL,
    amount NUMERIC(16, 2) NOT NULL,
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (
        generation_id, row_set, company_name, period, source_site_code, category_code
    ),
    FOREIGN KEY (generation_id, company_name, period)
        REFERENCES store_pnl_generation_scopes(generation_id, company_name, period)
        ON DELETE RESTRICT
);

CREATE TABLE store_pnl_generation_heads (
    company_name TEXT NOT NULL CHECK (company_name IN ('Mobicell', 'Mobiup')),
    period DATE NOT NULL CHECK (period = date_trunc('month', period)::date),
    active_generation_id UUID NOT NULL
        REFERENCES store_pnl_generations(id) ON DELETE RESTRICT,
    revision BIGINT NOT NULL CHECK (revision >= 1),
    revision_id TEXT NOT NULL CHECK (btrim(revision_id) <> ''),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (company_name, period)
);

CREATE TABLE store_pnl_generation_ledger (
    id BIGSERIAL PRIMARY KEY,
    generation_id UUID NOT NULL
        REFERENCES store_pnl_generations(id) ON DELETE RESTRICT,
    action TEXT NOT NULL CHECK (action IN ('staged', 'promoted')),
    company_name TEXT CHECK (company_name IN ('Mobicell', 'Mobiup')),
    period DATE CHECK (period = date_trunc('month', period)::date),
    details JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_store_pnl_generation_scopes_lookup
    ON store_pnl_generation_scopes (company_name, period, generation_id);
CREATE INDEX idx_store_pnl_generation_rows_lookup
    ON store_pnl_generation_rows (generation_id, row_set, company_name, period);
CREATE INDEX idx_store_pnl_generation_ledger_generation
    ON store_pnl_generation_ledger (generation_id, id);

CREATE OR REPLACE FUNCTION prevent_store_pnl_generation_history_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'store_pnl generation history is immutable';
    END IF;

    IF TG_TABLE_NAME = 'store_pnl_generations' THEN
        IF OLD.id IS NOT DISTINCT FROM NEW.id
           AND OLD.operation IS NOT DISTINCT FROM NEW.operation
           AND OLD.authority_manifest_sha256 IS NOT DISTINCT FROM NEW.authority_manifest_sha256
           AND OLD.authority_manifest IS NOT DISTINCT FROM NEW.authority_manifest
           AND OLD.generation_manifest_sha256 IS NOT DISTINCT FROM NEW.generation_manifest_sha256
           AND OLD.generation_manifest IS NOT DISTINCT FROM NEW.generation_manifest
           AND OLD.inverse_of_generation_id IS NOT DISTINCT FROM NEW.inverse_of_generation_id
           AND OLD.created_at IS NOT DISTINCT FROM NEW.created_at
       AND (
           (OLD.state = 'building' AND NEW.state = 'staged'
            AND OLD.promoted_at IS NULL AND NEW.promoted_at IS NULL)
           OR
           (OLD.state = 'staged' AND NEW.state = 'promoted'
            AND OLD.promoted_at IS NULL AND NEW.promoted_at IS NOT NULL)
       ) THEN
            RETURN NEW;
        END IF;
    END IF;

    RAISE EXCEPTION 'store_pnl generation history is immutable';
END;
$$;

CREATE TRIGGER store_pnl_generations_immutable
BEFORE UPDATE OR DELETE ON store_pnl_generations
FOR EACH ROW EXECUTE FUNCTION prevent_store_pnl_generation_history_mutation();

CREATE TRIGGER store_pnl_generation_scopes_immutable
BEFORE UPDATE OR DELETE ON store_pnl_generation_scopes
FOR EACH ROW EXECUTE FUNCTION prevent_store_pnl_generation_history_mutation();

CREATE TRIGGER store_pnl_generation_rows_immutable
BEFORE UPDATE OR DELETE ON store_pnl_generation_rows
FOR EACH ROW EXECUTE FUNCTION prevent_store_pnl_generation_history_mutation();

CREATE TRIGGER store_pnl_generation_ledger_immutable
BEFORE UPDATE OR DELETE ON store_pnl_generation_ledger
FOR EACH ROW EXECUTE FUNCTION prevent_store_pnl_generation_history_mutation();

CREATE OR REPLACE FUNCTION require_store_pnl_generation_building()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM store_pnl_generations
        WHERE id = NEW.generation_id AND state = 'building'
    ) THEN
        RAISE EXCEPTION 'store_pnl generation rows may be added only while building';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER store_pnl_generation_scopes_building_only
BEFORE INSERT ON store_pnl_generation_scopes
FOR EACH ROW EXECUTE FUNCTION require_store_pnl_generation_building();

CREATE TRIGGER store_pnl_generation_rows_building_only
BEFORE INSERT ON store_pnl_generation_rows
FOR EACH ROW EXECUTE FUNCTION require_store_pnl_generation_building();

CREATE OR REPLACE FUNCTION validate_store_pnl_generation_ledger_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF (NEW.action = 'staged' AND EXISTS (
        SELECT 1 FROM store_pnl_generations
        WHERE id = NEW.generation_id AND state = 'building'
    )) OR (NEW.action = 'promoted' AND EXISTS (
        SELECT 1 FROM store_pnl_generations
        WHERE id = NEW.generation_id AND state = 'staged'
    )) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'store_pnl generation ledger action does not match generation state';
END;
$$;

CREATE TRIGGER store_pnl_generation_ledger_state_checked
BEFORE INSERT ON store_pnl_generation_ledger
FOR EACH ROW EXECUTE FUNCTION validate_store_pnl_generation_ledger_insert();

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        REVOKE ALL ON TABLE store_pnl_generations,
                            store_pnl_generation_scopes,
                            store_pnl_generation_rows,
                            store_pnl_generation_heads,
                            store_pnl_generation_ledger
            FROM unihub_runtime;
        REVOKE INSERT, UPDATE, DELETE ON TABLE store_pnl_monthly FROM unihub_runtime;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_finance_import') THEN
        GRANT SELECT, INSERT, UPDATE ON TABLE store_pnl_generations,
                                              store_pnl_generation_heads
            TO unihub_finance_import;
        GRANT SELECT, INSERT ON TABLE store_pnl_generation_scopes,
                                      store_pnl_generation_rows,
                                      store_pnl_generation_ledger
            TO unihub_finance_import;
        GRANT SELECT, INSERT, DELETE ON TABLE store_pnl_monthly
            TO unihub_finance_import;
        GRANT USAGE, SELECT ON SEQUENCE store_pnl_monthly_id_seq,
                                        store_pnl_generation_ledger_id_seq
            TO unihub_finance_import;
    END IF;
END
$$;

COMMENT ON TABLE store_pnl_generations IS
    'Immutable Finance-authorized P&L promotion and inverse-rollback generations.';
COMMENT ON TABLE store_pnl_generation_heads IS
    'Per-company/month CAS head; the runtime is denied mutation rights.';
