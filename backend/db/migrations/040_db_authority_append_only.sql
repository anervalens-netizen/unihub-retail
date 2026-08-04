-- P1-A: explicit database authorities and immutable promotion evidence.
--
-- This delta intentionally does not activate any LOGIN/service identity.  The
-- separately reviewed provisioner may attach an existing service identity to
-- exactly one NOLOGIN authority after the operational credential boundary is
-- approved.  Do not add default grants here.

DO $$
DECLARE
    authority_name TEXT;
BEGIN
    FOREACH authority_name IN ARRAY ARRAY[
        'unihub_web_read',
        'unihub_business_write',
        'unihub_sales_import',
        'unihub_finance_import',
        'unihub_operations',
        'unihub_migrate'
    ]
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = authority_name) THEN
            EXECUTE format(
                'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT',
                authority_name
            );
        ELSE
            EXECUTE format(
                'ALTER ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT',
                authority_name
            );
        END IF;
        EXECUTE format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO %I', current_database(), authority_name);
        EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', authority_name);
    END LOOP;
END
$$;

-- Default ACLs are an owner-scoped fence.  Explicit future-object grants must
-- be added in their owning migration; no authority receives a catch-all grant.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

DO $$
DECLARE
    authority_name TEXT;
BEGIN
    FOREACH authority_name IN ARRAY ARRAY[
        'unihub_web_read',
        'unihub_business_write',
        'unihub_sales_import',
        'unihub_finance_import',
        'unihub_operations',
        'unihub_migrate',
        'unihub_runtime'
    ]
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = authority_name) THEN
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I',
                authority_name
            );
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I',
                authority_name
            );
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I',
                authority_name
            );
        END IF;
    END LOOP;
END
$$;

-- Explicit read surface.  Private salary identity data and generation/staging
-- evidence are deliberately absent.
GRANT SELECT ON TABLE
    team_leaders,
    stores,
    store_org_assignments,
    focus_products,
    import_snapshots,
    sales_transactions,
    historical_annual_sales,
    historical_monthly_sales,
    incentive_campaigns,
    incentive_products,
    reporting_agent_day,
    reporting_agent_lifecycle_month,
    reporting_agent_month,
    reporting_agent_profile,
    reporting_cartela_day,
    reporting_category_month,
    reporting_focus_item_month,
    reporting_item_day,
    reporting_item_month,
    ai_forecast_runs,
    ai_forecast_store_day,
    ai_forecast_store_month,
    store_targets,
    agent_targets,
    premium_glass_item_models,
    store_pnl_monthly,
    store_pnl_site_links,
    target_calculator_rule_sets,
    target_calculator_effective_rule_sets,
    target_calculator_store_exclusions,
    target_scenarios,
    target_scenario_rows,
    tasks,
    leave_requests,
    attendance_records,
    store_scores,
    store_activity_events,
    visits_snapshot,
    error_logs,
    grile_sheets,
    grile_runs,
    grile_store_status,
    grile_store_current_status,
    grile_store_observations,
    grile_store_projection_generations,
    grile_store_refreshes,
    grile_run_store_generations,
    grile_monthly_operations,
    grile_monthly_manifests,
    grile_monthly_reset_items,
    grile_agent_target_sync_runs,
    schema_meta,
    schema_migrations
TO unihub_web_read;

GRANT SELECT (
    id, year, month, full_name, total_salary, company_name, site_code,
    locatie, created_at, person_id
) ON salary_records TO unihub_web_read;
GRANT SELECT (
    agent_code, site_code, salary_full_name, match_status, match_source,
    confidence, effective_from_month, note, created_at, updated_at, person_id
) ON agent_salary_links TO unihub_web_read;

-- Business writes are intentionally limited to online management mutations.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    tasks,
    leave_requests,
    attendance_records,
    store_scores,
    store_activity_events,
    target_calculator_store_exclusions,
    target_scenarios,
    target_scenario_rows,
    store_targets,
    incentive_campaigns,
    incentive_products
TO unihub_business_write;
GRANT UPDATE ON TABLE stores TO unihub_business_write;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    focus_products,
    visits_snapshot,
    error_logs
TO unihub_business_write;
GRANT SELECT, INSERT, UPDATE ON TABLE
    grile_runs,
    grile_store_refreshes,
    grile_monthly_operations,
    grile_monthly_manifests,
    grile_monthly_reset_items,
    grile_agent_target_sync_runs
TO unihub_business_write;
GRANT USAGE, SELECT ON SEQUENCE
    tasks_id_seq,
    leave_requests_id_seq,
    attendance_records_id_seq,
    store_scores_id_seq,
    store_activity_events_id_seq,
    target_scenarios_id_seq,
    error_logs_id_seq,
    grile_runs_id_seq,
    grile_store_refreshes_id_seq,
    grile_monthly_operations_id_seq,
    grile_monthly_manifests_id_seq,
    grile_monthly_reset_items_id_seq,
    grile_agent_target_sync_runs_id_seq
TO unihub_business_write;

-- The sales worker may stage/replace the sales projection, but never mutate an
-- authoritative head or its ledger directly.
GRANT SELECT, INSERT, UPDATE ON TABLE import_snapshots TO unihub_sales_import;
GRANT SELECT, INSERT ON TABLE sales_import_stage_rows TO unihub_sales_import;
GRANT SELECT ON TABLE sales_generation_heads, sales_generation_promotions TO unihub_sales_import;
GRANT SELECT, INSERT, DELETE ON TABLE sales_transactions TO unihub_sales_import;
GRANT SELECT, INSERT, UPDATE ON TABLE stores TO unihub_sales_import;
GRANT SELECT ON TABLE focus_products TO unihub_sales_import;
GRANT INSERT, TRUNCATE, MAINTAIN ON TABLE
    premium_glass_item_models
TO unihub_sales_import;
GRANT SELECT, INSERT, DELETE ON TABLE
    reporting_agent_day,
    reporting_agent_lifecycle_month,
    reporting_agent_month,
    reporting_agent_profile,
    reporting_cartela_day,
    reporting_category_month,
    reporting_focus_item_month,
    reporting_item_day,
    reporting_item_month
TO unihub_sales_import;
GRANT MAINTAIN ON TABLE
    reporting_agent_day,
    reporting_agent_lifecycle_month,
    reporting_agent_month,
    reporting_agent_profile,
    reporting_cartela_day,
    reporting_category_month,
    reporting_focus_item_month,
    reporting_item_day,
    reporting_item_month
TO unihub_sales_import;
GRANT SELECT, INSERT, UPDATE ON TABLE grile_runs TO unihub_sales_import;
GRANT USAGE, SELECT ON SEQUENCE
    import_snapshots_id_seq,
    sales_transactions_id_seq,
    grile_runs_id_seq
TO unihub_sales_import;

-- Finance remains its own NOLOGIN authority.  Direct head and ledger writes
-- are denied; table permissions are only those required to build/replay an
-- immutable generation.
GRANT SELECT, INSERT, DELETE ON TABLE store_pnl_monthly TO unihub_finance_import;
GRANT SELECT, INSERT, UPDATE ON TABLE store_pnl_generations TO unihub_finance_import;
GRANT SELECT, INSERT ON TABLE
    store_pnl_generation_scopes,
    store_pnl_generation_rows
TO unihub_finance_import;
GRANT SELECT ON TABLE
    store_pnl_generation_heads,
    store_pnl_generation_ledger
TO unihub_finance_import;
GRANT USAGE, SELECT ON SEQUENCE store_pnl_monthly_id_seq TO unihub_finance_import;

-- Operations may capture immutable shadow evidence and operate its review
-- pointer only through the CAS functions below.
GRANT SELECT, INSERT ON TABLE
    store_pnl_shadow_generations,
    store_pnl_shadow_rows,
    store_pnl_shadow_preimage_rows
TO unihub_operations;
GRANT SELECT ON TABLE store_pnl_shadow_pointer TO unihub_operations;
GRANT SELECT ON TABLE
    team_leaders,
    stores,
    historical_monthly_sales,
    reporting_agent_month,
    reporting_item_day,
    reporting_item_month,
    store_targets,
    agent_targets,
    grile_sheets,
    store_pnl_monthly,
    store_pnl_site_links
TO unihub_operations;
GRANT SELECT (
    id, year, month, full_name, total_salary, company_name, site_code,
    locatie, created_at, person_id
) ON salary_records TO unihub_operations;
GRANT SELECT, INSERT, UPDATE ON TABLE
    grile_runs,
    grile_store_status,
    grile_store_current_status,
    grile_store_projection_generations,
    grile_store_refreshes,
    grile_monthly_operations,
    grile_monthly_manifests,
    grile_monthly_reset_items,
    grile_agent_target_sync_runs
TO unihub_operations;
GRANT SELECT, INSERT ON TABLE
    grile_store_observations,
    grile_run_store_generations
TO unihub_operations;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE agent_targets TO unihub_operations;
GRANT USAGE, SELECT ON SEQUENCE
    grile_runs_id_seq,
    grile_store_observations_id_seq,
    grile_store_refreshes_id_seq,
    grile_monthly_operations_id_seq,
    grile_monthly_manifests_id_seq,
    grile_monthly_reset_items_id_seq,
    grile_agent_target_sync_runs_id_seq
TO unihub_operations;

-- Migration authority is a non-owning process marker. A separate NOLOGIN
-- schema owner is installed by the ownership-handoff migration.

-- Existing broad runtime ACLs are fenced away from safety-critical evidence.
-- Other legacy application grants are intentionally not inferred here: their
-- replacement requires an approved service-identity cutover.
REVOKE ALL ON TABLE
    sales_import_stage_rows,
    sales_generation_heads,
    sales_generation_promotions,
    store_pnl_generations,
    store_pnl_generation_scopes,
    store_pnl_generation_rows,
    store_pnl_generation_heads,
    store_pnl_generation_ledger,
    store_pnl_shadow_generations,
    store_pnl_shadow_rows,
    store_pnl_shadow_preimage_rows,
    store_pnl_shadow_pointer
FROM PUBLIC, unihub_web_read, unihub_business_write, unihub_sales_import,
    unihub_finance_import, unihub_operations, unihub_migrate;
REVOKE ALL ON TABLE
    sales_generation_heads,
    sales_generation_promotions,
    store_pnl_generation_heads,
    store_pnl_generation_ledger,
    store_pnl_shadow_generations,
    store_pnl_shadow_rows,
    store_pnl_shadow_preimage_rows,
    store_pnl_shadow_pointer
FROM unihub_sales_import, unihub_finance_import, unihub_operations;
REVOKE UPDATE, DELETE ON TABLE sales_import_stage_rows FROM unihub_sales_import;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        REVOKE ALL ON TABLE
            sales_import_stage_rows,
            sales_generation_heads,
            sales_generation_promotions,
            store_pnl_generations,
            store_pnl_generation_scopes,
            store_pnl_generation_rows,
            store_pnl_generation_heads,
            store_pnl_generation_ledger,
            store_pnl_shadow_generations,
            store_pnl_shadow_rows,
            store_pnl_shadow_preimage_rows,
            store_pnl_shadow_pointer
        FROM unihub_runtime;
        REVOKE ALL ON SEQUENCE sales_generation_promotions_id_seq,
                               store_pnl_generation_ledger_id_seq
        FROM unihub_runtime;
    END IF;
END
$$;

-- Re-grant only the explicit writer surfaces after the deny-first sensitive
-- fence above.  Head/pointer/ledger mutation remains function-only.
GRANT SELECT, INSERT ON TABLE sales_import_stage_rows TO unihub_sales_import;
GRANT SELECT ON TABLE sales_generation_heads, sales_generation_promotions TO unihub_sales_import;
GRANT SELECT, INSERT, UPDATE ON TABLE store_pnl_generations TO unihub_finance_import;
GRANT SELECT, INSERT ON TABLE
    store_pnl_generation_scopes,
    store_pnl_generation_rows
TO unihub_finance_import;
GRANT SELECT ON TABLE
    store_pnl_generation_heads,
    store_pnl_generation_ledger
TO unihub_finance_import;
GRANT SELECT, INSERT ON TABLE
    store_pnl_shadow_generations,
    store_pnl_shadow_rows,
    store_pnl_shadow_preimage_rows
TO unihub_operations;
GRANT SELECT ON TABLE store_pnl_shadow_pointer TO unihub_operations;

ALTER TABLE store_pnl_shadow_generations
    ADD COLUMN IF NOT EXISTS shadow_rows_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS shadow_row_count BIGINT,
    ADD COLUMN IF NOT EXISTS preimage_rows_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS preimage_row_count BIGINT,
    ADD COLUMN IF NOT EXISTS sealed_at TIMESTAMPTZ;

ALTER TABLE store_pnl_shadow_generations
    DROP CONSTRAINT IF EXISTS ck_store_pnl_shadow_generation_seal;

ALTER TABLE store_pnl_shadow_generations
    ADD CONSTRAINT ck_store_pnl_shadow_generation_seal CHECK (
        (sealed_at IS NULL
         AND shadow_rows_sha256 IS NULL
         AND shadow_row_count IS NULL
         AND preimage_rows_sha256 IS NULL
         AND preimage_row_count IS NULL)
        OR
        (sealed_at IS NOT NULL
         AND shadow_rows_sha256 ~ '^[0-9a-f]{64}$'
         AND shadow_row_count >= 0
         AND preimage_rows_sha256 ~ '^[0-9a-f]{64}$'
         AND preimage_row_count >= 0)
    );

CREATE OR REPLACE FUNCTION public.store_pnl_shadow_rows_sha256(p_generation_id UUID)
RETURNS TEXT
LANGUAGE SQL
STABLE
STRICT
SET search_path = pg_catalog, public
AS $$
    SELECT encode(
        digest(
            convert_to(
                COALESCE(
                    string_agg(
                        jsonb_build_array(
                            variant, company_name, period, site_code,
                            source_site_code, source_location_name, category_code,
                            category_name, amount
                        )::TEXT,
                        E'\\x1e'
                        ORDER BY variant, company_name, period, site_code, category_code
                    ),
                    ''
                ),
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    )
    FROM public.store_pnl_shadow_rows
    WHERE generation_id = p_generation_id
$$;

CREATE OR REPLACE FUNCTION public.store_pnl_shadow_preimage_rows_sha256(p_generation_id UUID)
RETURNS TEXT
LANGUAGE SQL
STABLE
STRICT
SET search_path = pg_catalog, public
AS $$
    SELECT encode(
        digest(
            convert_to(
                COALESCE(
                    string_agg(
                        jsonb_build_array(
                            company_name, period, source_site_code,
                            source_location_name, category_code, category_name,
                            amount, data_kind, source_file, source_sha256, captured_at
                        )::TEXT,
                        E'\\x1e'
                        ORDER BY company_name, period, source_site_code, category_code, data_kind
                    ),
                    ''
                ),
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    )
    FROM public.store_pnl_shadow_preimage_rows
    WHERE generation_id = p_generation_id
$$;

CREATE OR REPLACE FUNCTION public.seal_store_pnl_shadow_generation(p_generation_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    shadow_digest TEXT;
    shadow_count BIGINT;
    preimage_digest TEXT;
    preimage_count BIGINT;
BEGIN
    PERFORM 1
    FROM public.store_pnl_shadow_generations
    WHERE id = p_generation_id
      AND state = 'staged'
      AND sealed_at IS NULL
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'only an unsealed staged store_pnl shadow generation can seal';
    END IF;
    SELECT COUNT(*), public.store_pnl_shadow_rows_sha256(p_generation_id)
    INTO shadow_count, shadow_digest
    FROM public.store_pnl_shadow_rows
    WHERE generation_id = p_generation_id;
    SELECT COUNT(*), public.store_pnl_shadow_preimage_rows_sha256(p_generation_id)
    INTO preimage_count, preimage_digest
    FROM public.store_pnl_shadow_preimage_rows
    WHERE generation_id = p_generation_id;
    UPDATE public.store_pnl_shadow_generations
    SET shadow_rows_sha256 = shadow_digest,
        shadow_row_count = shadow_count,
        preimage_rows_sha256 = preimage_digest,
        preimage_row_count = preimage_count,
        sealed_at = now()
    WHERE id = p_generation_id AND sealed_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'store_pnl shadow generation seal changed concurrently';
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION guard_sales_stage_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    snapshot_month TEXT;
    snapshot_status TEXT;
    stored_digest TEXT;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'sales staging rows are append-only; retention is a later controlled lifecycle';
    END IF;

    SELECT import_month, status, stage_rows_sha256
    INTO snapshot_month, snapshot_status, stored_digest
    FROM public.import_snapshots
    WHERE id = NEW.snapshot_id;

    IF NOT FOUND
       OR snapshot_status <> 'processing'
       OR snapshot_month IS DISTINCT FROM NEW.import_month THEN
        RAISE EXCEPTION 'sales staging row does not belong to an active matching snapshot';
    END IF;
    IF stored_digest IS NOT NULL THEN
        RAISE EXCEPTION 'validated sales staging for snapshot % is immutable', NEW.snapshot_id;
    END IF;
    RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION guard_sales_generation_promotion_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    head_snapshot_id INTEGER;
    head_revision BIGINT;
    target_month TEXT;
    target_status TEXT;
    target_previous_snapshot_id INTEGER;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'sales promotion ledger is append-only';
    END IF;

    SELECT snapshot_id, revision
    INTO head_snapshot_id, head_revision
    FROM public.sales_generation_heads
    WHERE import_month = NEW.import_month;
    IF NOT FOUND
       OR head_snapshot_id IS DISTINCT FROM NEW.to_snapshot_id
       OR head_revision IS DISTINCT FROM NEW.head_revision THEN
        RAISE EXCEPTION 'sales promotion ledger must attest to the current CAS head';
    END IF;

    SELECT import_month, status, previous_snapshot_id
    INTO target_month, target_status, target_previous_snapshot_id
    FROM public.import_snapshots
    WHERE id = NEW.to_snapshot_id;
    IF NOT FOUND
       OR target_month IS DISTINCT FROM NEW.import_month
       OR target_status <> 'completed'
       OR target_previous_snapshot_id IS DISTINCT FROM NEW.from_snapshot_id THEN
        RAISE EXCEPTION 'sales promotion ledger target is not the completed CAS generation';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_sales_generation_promotions_immutable ON sales_generation_promotions;
CREATE TRIGGER trg_sales_generation_promotions_immutable
BEFORE INSERT OR UPDATE OR DELETE ON sales_generation_promotions
FOR EACH ROW EXECUTE FUNCTION guard_sales_generation_promotion_mutation();

CREATE OR REPLACE FUNCTION guard_store_pnl_shadow_evidence_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_TABLE_NAME IN ('store_pnl_shadow_rows', 'store_pnl_shadow_preimage_rows') THEN
        IF TG_OP <> 'INSERT' OR EXISTS (
            SELECT 1
            FROM public.store_pnl_shadow_generations
            WHERE id = NEW.generation_id
              AND (state <> 'staged' OR sealed_at IS NOT NULL)
        ) THEN
            RAISE EXCEPTION 'store_pnl shadow evidence is append-only and sealed before promote';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_TABLE_NAME = 'store_pnl_shadow_pointer' THEN
        IF TG_OP <> 'UPDATE'
           OR OLD.id <> 1
           OR NEW.id <> 1
           OR NEW.revision <> OLD.revision + 1 THEN
            RAISE EXCEPTION 'store_pnl shadow pointer accepts only a revision CAS advance';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP <> 'UPDATE'
       OR OLD.id IS DISTINCT FROM NEW.id
       OR OLD.scope IS DISTINCT FROM NEW.scope
       OR OLD.scope_sha256 IS DISTINCT FROM NEW.scope_sha256
       OR OLD.input_cutoff IS DISTINCT FROM NEW.input_cutoff
       OR OLD.source_sha256 IS DISTINCT FROM NEW.source_sha256
       OR OLD.input_sha256 IS DISTINCT FROM NEW.input_sha256
       OR OLD.legacy_ruleset_sha256 IS DISTINCT FROM NEW.legacy_ruleset_sha256
       OR OLD.effective_ruleset_sha256 IS DISTINCT FROM NEW.effective_ruleset_sha256
       OR OLD.legacy_model_sha256 IS DISTINCT FROM NEW.legacy_model_sha256
       OR OLD.effective_model_sha256 IS DISTINCT FROM NEW.effective_model_sha256
       OR OLD.legacy_output_sha256 IS DISTINCT FROM NEW.legacy_output_sha256
       OR OLD.effective_output_sha256 IS DISTINCT FROM NEW.effective_output_sha256
       OR OLD.fiscal_delta IS DISTINCT FROM NEW.fiscal_delta
       OR OLD.input_or_model_delta IS DISTINCT FROM NEW.input_or_model_delta
       OR OLD.baseline_generation_id IS DISTINCT FROM NEW.baseline_generation_id
       OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
        RAISE EXCEPTION 'store_pnl shadow evidence is immutable';
    END IF;

    IF OLD.state = 'staged' AND NEW.state = 'staged'
       AND OLD.sealed_at IS NULL
       AND NEW.sealed_at IS NOT NULL
       AND NEW.shadow_rows_sha256 ~ '^[0-9a-f]{64}$'
       AND NEW.shadow_row_count >= 0
       AND NEW.preimage_rows_sha256 ~ '^[0-9a-f]{64}$'
       AND NEW.preimage_row_count >= 0 THEN
        RETURN NEW;
    END IF;

    IF (OLD.state = 'staged' AND NEW.state = 'promoted'
            AND OLD.promoted_at IS NULL AND NEW.promoted_at IS NOT NULL
            AND OLD.rolled_back_at IS NULL AND NEW.rolled_back_at IS NULL
            AND OLD.sealed_at IS NOT NULL
            AND OLD.shadow_rows_sha256 IS NOT DISTINCT FROM NEW.shadow_rows_sha256
            AND OLD.shadow_row_count IS NOT DISTINCT FROM NEW.shadow_row_count
            AND OLD.preimage_rows_sha256 IS NOT DISTINCT FROM NEW.preimage_rows_sha256
            AND OLD.preimage_row_count IS NOT DISTINCT FROM NEW.preimage_row_count
            AND OLD.sealed_at IS NOT DISTINCT FROM NEW.sealed_at)
       OR (OLD.state = 'promoted' AND NEW.state = 'superseded'
            AND NEW.promoted_at IS NOT NULL
            AND OLD.rolled_back_at IS NULL AND NEW.rolled_back_at IS NULL
            AND OLD.shadow_rows_sha256 IS NOT DISTINCT FROM NEW.shadow_rows_sha256
            AND OLD.shadow_row_count IS NOT DISTINCT FROM NEW.shadow_row_count
            AND OLD.preimage_rows_sha256 IS NOT DISTINCT FROM NEW.preimage_rows_sha256
            AND OLD.preimage_row_count IS NOT DISTINCT FROM NEW.preimage_row_count
            AND OLD.sealed_at IS NOT DISTINCT FROM NEW.sealed_at)
       OR (OLD.state = 'superseded' AND NEW.state = 'promoted'
            AND NEW.promoted_at IS NOT NULL
            AND OLD.rolled_back_at IS NULL AND NEW.rolled_back_at IS NULL
            AND OLD.shadow_rows_sha256 IS NOT DISTINCT FROM NEW.shadow_rows_sha256
            AND OLD.shadow_row_count IS NOT DISTINCT FROM NEW.shadow_row_count
            AND OLD.preimage_rows_sha256 IS NOT DISTINCT FROM NEW.preimage_rows_sha256
            AND OLD.preimage_row_count IS NOT DISTINCT FROM NEW.preimage_row_count
            AND OLD.sealed_at IS NOT DISTINCT FROM NEW.sealed_at)
       OR (OLD.state = 'promoted' AND NEW.state = 'rolled_back'
            AND NEW.promoted_at IS NOT NULL
            AND OLD.rolled_back_at IS NULL AND NEW.rolled_back_at IS NOT NULL
            AND OLD.shadow_rows_sha256 IS NOT DISTINCT FROM NEW.shadow_rows_sha256
            AND OLD.shadow_row_count IS NOT DISTINCT FROM NEW.shadow_row_count
            AND OLD.preimage_rows_sha256 IS NOT DISTINCT FROM NEW.preimage_rows_sha256
            AND OLD.preimage_row_count IS NOT DISTINCT FROM NEW.preimage_row_count
            AND OLD.sealed_at IS NOT DISTINCT FROM NEW.sealed_at) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'store_pnl shadow state transition is not allowed';
END
$$;

DROP TRIGGER IF EXISTS trg_store_pnl_shadow_generations_immutable ON store_pnl_shadow_generations;
CREATE TRIGGER trg_store_pnl_shadow_generations_immutable
BEFORE UPDATE OR DELETE ON store_pnl_shadow_generations
FOR EACH ROW EXECUTE FUNCTION guard_store_pnl_shadow_evidence_mutation();
DROP TRIGGER IF EXISTS trg_store_pnl_shadow_rows_immutable ON store_pnl_shadow_rows;
CREATE TRIGGER trg_store_pnl_shadow_rows_immutable
BEFORE INSERT OR UPDATE OR DELETE ON store_pnl_shadow_rows
FOR EACH ROW EXECUTE FUNCTION guard_store_pnl_shadow_evidence_mutation();
DROP TRIGGER IF EXISTS trg_store_pnl_shadow_preimage_rows_immutable ON store_pnl_shadow_preimage_rows;
CREATE TRIGGER trg_store_pnl_shadow_preimage_rows_immutable
BEFORE INSERT OR UPDATE OR DELETE ON store_pnl_shadow_preimage_rows
FOR EACH ROW EXECUTE FUNCTION guard_store_pnl_shadow_evidence_mutation();
DROP TRIGGER IF EXISTS trg_store_pnl_shadow_pointer_cas ON store_pnl_shadow_pointer;
CREATE TRIGGER trg_store_pnl_shadow_pointer_cas
BEFORE UPDATE OR DELETE ON store_pnl_shadow_pointer
FOR EACH ROW EXECUTE FUNCTION guard_store_pnl_shadow_evidence_mutation();

CREATE OR REPLACE FUNCTION public.advance_sales_generation_head(
    p_import_month TEXT,
    p_snapshot_id INTEGER,
    p_generation_token UUID,
    p_owner_id UUID,
    p_expected_revision BIGINT
)
RETURNS TABLE(previous_snapshot_id INTEGER, revision BIGINT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    current_snapshot_id INTEGER;
    current_revision BIGINT;
BEGIN
    IF p_import_month !~ '^[0-9]{4}-[0-9]{2}$' OR p_expected_revision < 0 THEN
        RAISE EXCEPTION 'sales head CAS parameters are invalid';
    END IF;
    PERFORM 1
    FROM public.import_snapshots
    WHERE id = p_snapshot_id
      AND import_month = p_import_month
      AND generation_token = p_generation_token
      AND owner_id = p_owner_id
      AND status = 'processing'
      AND lease_until > now()
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'sales head target is not the current leased generation';
    END IF;

    SELECT head.snapshot_id, head.revision
    INTO current_snapshot_id, current_revision
    FROM public.sales_generation_heads AS head
    WHERE head.import_month = p_import_month
    FOR UPDATE;
    IF NOT FOUND THEN
        IF p_expected_revision <> 0 THEN
            RAISE EXCEPTION 'sales generation head disappeared';
        END IF;
        INSERT INTO public.sales_generation_heads (import_month, snapshot_id, revision)
        VALUES (p_import_month, p_snapshot_id, 1);
        RETURN QUERY SELECT NULL::INTEGER, 1::BIGINT;
        RETURN;
    END IF;
    IF current_revision <> p_expected_revision THEN
        RAISE EXCEPTION 'sales generation head changed before promote';
    END IF;
    UPDATE public.sales_generation_heads AS head
    SET snapshot_id = p_snapshot_id,
        revision = current_revision + 1,
        updated_at = now()
    WHERE head.import_month = p_import_month
      AND head.revision = p_expected_revision;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'sales generation head CAS failed';
    END IF;
    RETURN QUERY SELECT current_snapshot_id, current_revision + 1;
END
$$;

CREATE OR REPLACE FUNCTION public.record_sales_generation_promotion(
    p_import_month TEXT,
    p_from_snapshot_id INTEGER,
    p_to_snapshot_id INTEGER,
    p_head_revision BIGINT,
    p_action TEXT,
    p_requested_by_sub TEXT,
    p_override_reason TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    ledger_id BIGINT;
BEGIN
    IF p_action NOT IN ('promote', 'rollback')
       OR p_requested_by_sub IS NULL
       OR char_length(btrim(p_requested_by_sub)) NOT BETWEEN 1 AND 256 THEN
        RAISE EXCEPTION 'sales promotion ledger parameters are invalid';
    END IF;
    INSERT INTO public.sales_generation_promotions (
        import_month, from_snapshot_id, to_snapshot_id, head_revision,
        action, requested_by_sub, override_reason
    ) VALUES (
        p_import_month, p_from_snapshot_id, p_to_snapshot_id, p_head_revision,
        p_action, p_requested_by_sub, p_override_reason
    ) RETURNING id INTO ledger_id;
    RETURN ledger_id;
END
$$;

CREATE OR REPLACE FUNCTION public.advance_store_pnl_generation_head(
    p_company_name TEXT,
    p_period DATE,
    p_generation_id UUID,
    p_expected_revision BIGINT,
    p_expected_parent_revision_id TEXT,
    p_new_revision_id TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    current_generation_id UUID;
    current_revision BIGINT;
    current_revision_id TEXT;
    scope_expected_revision BIGINT;
    scope_parent_revision_id TEXT;
    scope_revision_id TEXT;
BEGIN
    SELECT expected_head_revision, parent_revision_id, revision_id
    INTO scope_expected_revision, scope_parent_revision_id, scope_revision_id
    FROM public.store_pnl_generation_scopes
    WHERE generation_id = p_generation_id
      AND company_name = p_company_name
      AND period = p_period;
    IF NOT FOUND
       OR scope_expected_revision <> p_expected_revision
       OR scope_parent_revision_id IS DISTINCT FROM p_expected_parent_revision_id
       OR scope_revision_id IS DISTINCT FROM p_new_revision_id
       OR NOT EXISTS (
            SELECT 1 FROM public.store_pnl_generations
            WHERE id = p_generation_id AND state = 'staged'
       ) THEN
        RAISE EXCEPTION 'store_pnl generation head CAS parameters are invalid';
    END IF;

    SELECT active_generation_id, revision, revision_id
    INTO current_generation_id, current_revision, current_revision_id
    FROM public.store_pnl_generation_heads
    WHERE company_name = p_company_name AND period = p_period
    FOR UPDATE;
    IF NOT FOUND THEN
        IF p_expected_revision <> 0 OR p_expected_parent_revision_id <> 'legacy' THEN
            RAISE EXCEPTION 'store_pnl generation head disappeared';
        END IF;
        INSERT INTO public.store_pnl_generation_heads (
            company_name, period, active_generation_id, revision, revision_id
        ) VALUES (p_company_name, p_period, p_generation_id, 1, p_new_revision_id);
        RETURN 1;
    END IF;
    IF current_revision <> p_expected_revision
       OR current_revision_id IS DISTINCT FROM p_expected_parent_revision_id THEN
        RAISE EXCEPTION 'store_pnl generation head changed before promote';
    END IF;
    UPDATE public.store_pnl_generation_heads
    SET active_generation_id = p_generation_id,
        revision = current_revision + 1,
        revision_id = p_new_revision_id,
        updated_at = now()
    WHERE company_name = p_company_name
      AND period = p_period
      AND revision = p_expected_revision
      AND revision_id = p_expected_parent_revision_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'store_pnl generation head CAS failed';
    END IF;
    RETURN current_revision + 1;
END
$$;

CREATE OR REPLACE FUNCTION public.append_store_pnl_generation_ledger(
    p_generation_id UUID,
    p_action TEXT,
    p_company_name TEXT,
    p_period DATE,
    p_details JSONB
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    ledger_id BIGINT;
BEGIN
    IF p_action NOT IN ('staged', 'promoted') OR p_details IS NULL THEN
        RAISE EXCEPTION 'store_pnl generation ledger parameters are invalid';
    END IF;
    INSERT INTO public.store_pnl_generation_ledger (
        generation_id, action, company_name, period, details
    ) VALUES (
        p_generation_id, p_action, p_company_name, p_period, p_details
    ) RETURNING id INTO ledger_id;
    RETURN ledger_id;
END
$$;

CREATE OR REPLACE FUNCTION public.promote_store_pnl_shadow_generation(
    p_generation_id UUID,
    p_expected_revision BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_active_generation_id UUID;
    v_current_revision BIGINT;
    v_sealed_shadow_digest TEXT;
    v_sealed_shadow_count BIGINT;
    v_sealed_preimage_digest TEXT;
    v_sealed_preimage_count BIGINT;
    v_actual_shadow_digest TEXT;
    v_actual_shadow_count BIGINT;
    v_actual_preimage_digest TEXT;
    v_actual_preimage_count BIGINT;
BEGIN
    SELECT pointer.active_generation_id, pointer.revision
    INTO v_active_generation_id, v_current_revision
    FROM public.store_pnl_shadow_pointer AS pointer
    WHERE pointer.id = 1
    FOR UPDATE;
    IF NOT FOUND OR v_current_revision <> p_expected_revision THEN
        RAISE EXCEPTION 'store_pnl shadow pointer revision changed';
    END IF;
    SELECT shadow_rows_sha256, shadow_row_count,
           preimage_rows_sha256, preimage_row_count
    INTO v_sealed_shadow_digest, v_sealed_shadow_count,
         v_sealed_preimage_digest, v_sealed_preimage_count
    FROM public.store_pnl_shadow_generations
    WHERE id = p_generation_id
      AND state = 'staged'
      AND sealed_at IS NOT NULL
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'only a sealed staged store_pnl shadow generation can promote';
    END IF;
    SELECT COUNT(*), public.store_pnl_shadow_rows_sha256(p_generation_id)
    INTO v_actual_shadow_count, v_actual_shadow_digest
    FROM public.store_pnl_shadow_rows
    WHERE generation_id = p_generation_id;
    SELECT COUNT(*), public.store_pnl_shadow_preimage_rows_sha256(p_generation_id)
    INTO v_actual_preimage_count, v_actual_preimage_digest
    FROM public.store_pnl_shadow_preimage_rows
    WHERE generation_id = p_generation_id;
    IF (v_actual_shadow_digest, v_actual_shadow_count, v_actual_preimage_digest, v_actual_preimage_count)
       IS DISTINCT FROM
       (v_sealed_shadow_digest, v_sealed_shadow_count, v_sealed_preimage_digest, v_sealed_preimage_count) THEN
        RAISE EXCEPTION 'store_pnl shadow evidence does not match its sealed digest';
    END IF;
    UPDATE public.store_pnl_shadow_pointer
        SET active_generation_id = p_generation_id,
        previous_generation_id = v_active_generation_id,
        revision = v_current_revision + 1,
        updated_at = now()
    WHERE id = 1 AND revision = p_expected_revision;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'store_pnl shadow pointer CAS failed';
    END IF;
    UPDATE public.store_pnl_shadow_generations
    SET state = 'promoted', promoted_at = now()
    WHERE id = p_generation_id;
    IF v_active_generation_id IS NOT NULL THEN
        UPDATE public.store_pnl_shadow_generations
        SET state = 'superseded'
        WHERE id = v_active_generation_id AND state = 'promoted';
    END IF;
    RETURN v_current_revision + 1;
END
$$;

CREATE OR REPLACE FUNCTION public.rollback_store_pnl_shadow_pointer(
    p_expected_revision BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_active_generation_id UUID;
    v_previous_generation_id UUID;
    v_current_revision BIGINT;
BEGIN
    SELECT pointer.active_generation_id, pointer.previous_generation_id, pointer.revision
    INTO v_active_generation_id, v_previous_generation_id, v_current_revision
    FROM public.store_pnl_shadow_pointer AS pointer
    WHERE pointer.id = 1
    FOR UPDATE;
    IF NOT FOUND OR v_current_revision <> p_expected_revision THEN
        RAISE EXCEPTION 'store_pnl shadow pointer revision changed';
    END IF;
    IF v_active_generation_id IS NULL OR v_previous_generation_id IS NULL THEN
        RAISE EXCEPTION 'store_pnl shadow pointer has no rollback predecessor';
    END IF;
    UPDATE public.store_pnl_shadow_pointer
    SET active_generation_id = v_previous_generation_id,
        previous_generation_id = NULL,
        revision = v_current_revision + 1,
        updated_at = now()
    WHERE id = 1 AND revision = p_expected_revision;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'store_pnl shadow pointer CAS failed';
    END IF;
    UPDATE public.store_pnl_shadow_generations
    SET state = 'rolled_back', rolled_back_at = now()
    WHERE id = v_active_generation_id;
    UPDATE public.store_pnl_shadow_generations
    SET state = 'promoted', promoted_at = now()
    WHERE id = v_previous_generation_id;
    RETURN v_current_revision + 1;
END
$$;

REVOKE ALL ON FUNCTION
    public.advance_sales_generation_head(TEXT, INTEGER, UUID, UUID, BIGINT),
    public.record_sales_generation_promotion(TEXT, INTEGER, INTEGER, BIGINT, TEXT, TEXT, TEXT),
    public.advance_store_pnl_generation_head(TEXT, DATE, UUID, BIGINT, TEXT, TEXT),
    public.append_store_pnl_generation_ledger(UUID, TEXT, TEXT, DATE, JSONB),
    public.seal_store_pnl_shadow_generation(UUID),
    public.promote_store_pnl_shadow_generation(UUID, BIGINT),
    public.rollback_store_pnl_shadow_pointer(BIGINT)
FROM PUBLIC, unihub_web_read, unihub_business_write, unihub_sales_import,
    unihub_finance_import, unihub_operations, unihub_migrate;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        REVOKE ALL ON FUNCTION
            public.advance_sales_generation_head(TEXT, INTEGER, UUID, UUID, BIGINT),
            public.record_sales_generation_promotion(TEXT, INTEGER, INTEGER, BIGINT, TEXT, TEXT, TEXT),
            public.advance_store_pnl_generation_head(TEXT, DATE, UUID, BIGINT, TEXT, TEXT),
            public.append_store_pnl_generation_ledger(UUID, TEXT, TEXT, DATE, JSONB),
            public.seal_store_pnl_shadow_generation(UUID),
            public.promote_store_pnl_shadow_generation(UUID, BIGINT),
            public.rollback_store_pnl_shadow_pointer(BIGINT)
        FROM unihub_runtime;
    END IF;
END
$$;

GRANT EXECUTE ON FUNCTION
    public.advance_sales_generation_head(TEXT, INTEGER, UUID, UUID, BIGINT),
    public.record_sales_generation_promotion(TEXT, INTEGER, INTEGER, BIGINT, TEXT, TEXT, TEXT)
TO unihub_sales_import;
GRANT EXECUTE ON FUNCTION
    public.advance_store_pnl_generation_head(TEXT, DATE, UUID, BIGINT, TEXT, TEXT),
    public.append_store_pnl_generation_ledger(UUID, TEXT, TEXT, DATE, JSONB)
TO unihub_finance_import;
GRANT EXECUTE ON FUNCTION
    public.seal_store_pnl_shadow_generation(UUID),
    public.promote_store_pnl_shadow_generation(UUID, BIGINT),
    public.rollback_store_pnl_shadow_pointer(BIGINT)
TO unihub_operations;

COMMENT ON FUNCTION public.advance_sales_generation_head(TEXT, INTEGER, UUID, UUID, BIGINT) IS
    'Sales authoritative-head advance: leased writer plus revision CAS only.';
COMMENT ON FUNCTION public.advance_store_pnl_generation_head(TEXT, DATE, UUID, BIGINT, TEXT, TEXT) IS
    'Finance authoritative-head advance: staged scope plus revision/parent CAS only.';
COMMENT ON FUNCTION public.promote_store_pnl_shadow_generation(UUID, BIGINT) IS
    'Shadow review-pointer advance: revision CAS only; never writes live P&L.';
