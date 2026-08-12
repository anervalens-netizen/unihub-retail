-- Release A: inert additive foundations for immutable AI cohorts and the
-- transactional outbox. No producer, dispatcher or live promotion is enabled
-- by this migration.

CREATE TABLE ai_forecast_cohort_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_month TEXT NOT NULL
        CHECK (source_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    target_month TEXT NOT NULL
        CHECK (target_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    cutoff_at TIMESTAMPTZ NOT NULL,
    source_generation TEXT NOT NULL
        CHECK (source_generation ~ '^[A-Za-z0-9._-]{1,128}$'),
    source_generation_sha256 TEXT NOT NULL
        CHECK (source_generation_sha256 ~ '^[0-9a-f]{64}$'),
    cohort_sha256 TEXT CHECK (cohort_sha256 IS NULL OR cohort_sha256 ~ '^[0-9a-f]{64}$'),
    authority_version TEXT NOT NULL
        CHECK (authority_version ~ '^[a-z][a-z0-9_.-]{0,79}$'),
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    expected_pair_count INTEGER NOT NULL CHECK (expected_pair_count >= 0),
    state TEXT NOT NULL DEFAULT 'building'
        CHECK (state IN ('building', 'sealed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sealed_at TIMESTAMPTZ,
    UNIQUE (id, source_month, source_generation),
    UNIQUE (id, source_month, target_month),
    UNIQUE (
        source_month,
        target_month,
        source_generation,
        cohort_sha256
    ),
    CHECK (
        (state = 'building' AND cohort_sha256 IS NULL AND sealed_at IS NULL)
        OR (state = 'sealed' AND cohort_sha256 IS NOT NULL AND sealed_at IS NOT NULL)
    )
);

CREATE INDEX idx_ai_forecast_cohort_snapshots_lookup
    ON ai_forecast_cohort_snapshots (
        source_month,
        target_month,
        created_at DESC
    );

CREATE TABLE ai_forecast_cohort_rows (
    snapshot_id UUID NOT NULL,
    site_code TEXT NOT NULL CHECK (btrim(site_code) <> '' AND length(site_code) <= 80),
    source_month TEXT NOT NULL
        CHECK (source_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    is_operating BOOLEAN,
    firma TEXT CHECK (firma IS NULL OR (btrim(firma) <> '' AND length(firma) <= 160)),
    regional TEXT
        CHECK (regional IS NULL OR (btrim(regional) <> '' AND length(regional) <= 160)),
    asm TEXT CHECK (asm IS NULL OR (btrim(asm) <> '' AND length(asm) <= 160)),
    authority_source TEXT NOT NULL
        CHECK (authority_source ~ '^[a-z][a-z0-9_.:+-]{0,159}$'),
    confidence TEXT NOT NULL CHECK (confidence IN ('confirmed', 'unknown', 'ambiguous')),
    source_generation TEXT NOT NULL
        CHECK (source_generation ~ '^[A-Za-z0-9._-]{1,128}$'),
    source_row_sha256 TEXT NOT NULL CHECK (source_row_sha256 ~ '^[0-9a-f]{64}$'),
    first_seen_month TEXT NOT NULL
        CHECK (first_seen_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    last_seen_month TEXT NOT NULL
        CHECK (last_seen_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_id, site_code),
    FOREIGN KEY (snapshot_id, source_month, source_generation)
        REFERENCES ai_forecast_cohort_snapshots (id, source_month, source_generation)
        ON DELETE RESTRICT,
    CHECK (first_seen_month <= source_month AND source_month <= last_seen_month),
    CHECK (
        confidence <> 'confirmed'
        OR (
            is_operating IS NOT NULL
            AND firma IS NOT NULL
            AND regional IS NOT NULL
            AND asm IS NOT NULL
        )
    )
);

CREATE INDEX idx_ai_forecast_cohort_rows_source_site
    ON ai_forecast_cohort_rows (source_month, site_code);

CREATE OR REPLACE FUNCTION public.ai_forecast_cohort_rows_sha256(p_snapshot_id UUID)
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
                            row.site_code,
                            row.source_month,
                            row.is_operating,
                            row.firma,
                            row.regional,
                            row.asm,
                            row.authority_source,
                            row.confidence,
                            row.source_generation,
                            row.source_row_sha256,
                            row.first_seen_month,
                            row.last_seen_month
                        )::TEXT,
                        E'\x1e'
                        ORDER BY row.site_code COLLATE "C"
                    ),
                    ''
                ),
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    )
    FROM public.ai_forecast_cohort_rows AS row
    WHERE row.snapshot_id = p_snapshot_id
$$;

CREATE OR REPLACE FUNCTION public.guard_ai_forecast_cohort_snapshot_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'AI forecast cohort evidence is append-only';
    END IF;
    IF OLD.state = 'building'
       AND NEW.state = 'sealed'
       AND OLD.id IS NOT DISTINCT FROM NEW.id
       AND OLD.source_month IS NOT DISTINCT FROM NEW.source_month
       AND OLD.target_month IS NOT DISTINCT FROM NEW.target_month
       AND OLD.cutoff_at IS NOT DISTINCT FROM NEW.cutoff_at
       AND OLD.source_generation IS NOT DISTINCT FROM NEW.source_generation
       AND OLD.source_generation_sha256 IS NOT DISTINCT FROM NEW.source_generation_sha256
       AND OLD.authority_version IS NOT DISTINCT FROM NEW.authority_version
       AND OLD.row_count IS NOT DISTINCT FROM NEW.row_count
       AND OLD.expected_pair_count IS NOT DISTINCT FROM NEW.expected_pair_count
       AND OLD.created_at IS NOT DISTINCT FROM NEW.created_at
       AND OLD.cohort_sha256 IS NULL
       AND NEW.cohort_sha256 ~ '^[0-9a-f]{64}$'
       AND OLD.sealed_at IS NULL
       AND NEW.sealed_at IS NOT NULL THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'AI forecast cohort snapshot accepts only one verified seal';
END
$$;

CREATE TRIGGER trg_ai_forecast_cohort_snapshots_immutable
BEFORE UPDATE OR DELETE ON ai_forecast_cohort_snapshots
FOR EACH ROW EXECUTE FUNCTION public.guard_ai_forecast_cohort_snapshot_mutation();

CREATE OR REPLACE FUNCTION public.guard_ai_forecast_cohort_row_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    snapshot_state TEXT;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'AI forecast cohort rows are append-only';
    END IF;
    SELECT state INTO snapshot_state
    FROM public.ai_forecast_cohort_snapshots
    WHERE id = NEW.snapshot_id
    FOR UPDATE;
    IF NOT FOUND OR snapshot_state <> 'building' THEN
        RAISE EXCEPTION 'AI forecast cohort rows require a building snapshot';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_ai_forecast_cohort_rows_immutable
BEFORE INSERT OR UPDATE OR DELETE ON ai_forecast_cohort_rows
FOR EACH ROW EXECUTE FUNCTION public.guard_ai_forecast_cohort_row_mutation();

CREATE OR REPLACE FUNCTION public.seal_ai_forecast_cohort_snapshot(p_snapshot_id UUID)
RETURNS public.ai_forecast_cohort_snapshots
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    snapshot public.ai_forecast_cohort_snapshots%ROWTYPE;
    actual_row_count INTEGER;
    actual_sha256 TEXT;
BEGIN
    SELECT * INTO snapshot
    FROM public.ai_forecast_cohort_snapshots
    WHERE id = p_snapshot_id
    FOR UPDATE;
    IF NOT FOUND OR snapshot.state <> 'building' THEN
        RAISE EXCEPTION 'AI forecast cohort snapshot is absent or already sealed';
    END IF;

    SELECT count(*)::INTEGER,
           public.ai_forecast_cohort_rows_sha256(p_snapshot_id)
    INTO actual_row_count, actual_sha256
    FROM public.ai_forecast_cohort_rows
    WHERE snapshot_id = p_snapshot_id;
    IF actual_row_count IS DISTINCT FROM snapshot.row_count THEN
        RAISE EXCEPTION 'AI forecast cohort row count differs from its declaration';
    END IF;

    UPDATE public.ai_forecast_cohort_snapshots
    SET state = 'sealed',
        cohort_sha256 = actual_sha256,
        sealed_at = now()
    WHERE id = p_snapshot_id
    RETURNING * INTO snapshot;
    RETURN snapshot;
END
$$;

ALTER TABLE ai_forecast_runs
    ADD COLUMN cohort_snapshot_id UUID,
    ADD COLUMN request_sha256 TEXT
        CHECK (request_sha256 IS NULL OR request_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN raw_response_sha256 TEXT
        CHECK (raw_response_sha256 IS NULL OR raw_response_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN response_sha256 TEXT
        CHECK (response_sha256 IS NULL OR response_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN expected_pair_count INTEGER
        CHECK (expected_pair_count IS NULL OR expected_pair_count >= 0),
    ADD COLUMN model_pair_count INTEGER
        CHECK (model_pair_count IS NULL OR model_pair_count >= 0),
    ADD COLUMN fallback_pair_count INTEGER
        CHECK (fallback_pair_count IS NULL OR fallback_pair_count >= 0),
    ADD COLUMN precision_loss_count INTEGER
        CHECK (precision_loss_count IS NULL OR precision_loss_count >= 0),
    ADD COLUMN coverage_mode TEXT
        CHECK (coverage_mode IS NULL OR coverage_mode IN ('fail_closed', 'seasonal_fallback')),
    ADD COLUMN response_profile TEXT
        CHECK (response_profile IS NULL OR response_profile IN ('point_only_v1', 'point_quantiles_v1'));

ALTER TABLE ai_forecast_runs
    ADD CONSTRAINT ai_forecast_runs_cohort_snapshot_fk
    FOREIGN KEY (cohort_snapshot_id, source_month, forecast_month)
    REFERENCES ai_forecast_cohort_snapshots (id, source_month, target_month)
    ON DELETE RESTRICT;

ALTER TABLE ai_forecast_runs
    ADD CONSTRAINT ai_forecast_runs_pair_counts_check CHECK (
        (
            cohort_snapshot_id IS NULL
            AND request_sha256 IS NULL
            AND raw_response_sha256 IS NULL
            AND response_sha256 IS NULL
            AND expected_pair_count IS NULL
            AND model_pair_count IS NULL
            AND fallback_pair_count IS NULL
            AND precision_loss_count IS NULL
            AND coverage_mode IS NULL
            AND response_profile IS NULL
        )
        OR (
            request_sha256 IS NOT NULL
            AND expected_pair_count IS NOT NULL
            AND coverage_mode IS NOT NULL
            AND response_profile IS NOT NULL
            AND expected_pair_count > 0
            AND (
                status <> 'completed'
                OR (
                    raw_response_sha256 IS NOT NULL
                    AND response_sha256 IS NOT NULL
                    AND model_pair_count IS NOT NULL
                    AND fallback_pair_count IS NOT NULL
                    AND precision_loss_count IS NOT NULL
                    AND model_pair_count + fallback_pair_count = expected_pair_count
                )
            )
        )
    );

CREATE OR REPLACE FUNCTION public.guard_ai_forecast_run_cohort_lineage()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    snapshot_state TEXT;
    snapshot_pair_count INTEGER;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF OLD.cohort_snapshot_id IS NULL AND NEW.cohort_snapshot_id IS NOT NULL THEN
            RAISE EXCEPTION 'AI forecast cohort lineage cannot be attached retroactively';
        END IF;
        IF OLD.cohort_snapshot_id IS NOT NULL THEN
            IF NEW.cohort_snapshot_id IS DISTINCT FROM OLD.cohort_snapshot_id
               OR NEW.source_month IS DISTINCT FROM OLD.source_month
               OR NEW.forecast_month IS DISTINCT FROM OLD.forecast_month
               OR NEW.request_sha256 IS DISTINCT FROM OLD.request_sha256
               OR NEW.expected_pair_count IS DISTINCT FROM OLD.expected_pair_count
               OR NEW.coverage_mode IS DISTINCT FROM OLD.coverage_mode
               OR NEW.response_profile IS DISTINCT FROM OLD.response_profile
               OR (OLD.raw_response_sha256 IS NOT NULL
                   AND NEW.raw_response_sha256 IS DISTINCT FROM OLD.raw_response_sha256)
               OR (OLD.response_sha256 IS NOT NULL
                   AND NEW.response_sha256 IS DISTINCT FROM OLD.response_sha256)
               OR (OLD.model_pair_count IS NOT NULL
                   AND NEW.model_pair_count IS DISTINCT FROM OLD.model_pair_count)
               OR (OLD.fallback_pair_count IS NOT NULL
                   AND NEW.fallback_pair_count IS DISTINCT FROM OLD.fallback_pair_count)
               OR (OLD.precision_loss_count IS NOT NULL
                   AND NEW.precision_loss_count IS DISTINCT FROM OLD.precision_loss_count) THEN
                RAISE EXCEPTION 'AI forecast cohort lineage is append-only';
            END IF;
            IF OLD.status IN ('completed', 'failed') AND NEW IS DISTINCT FROM OLD THEN
                RAISE EXCEPTION 'terminal AI forecast run is immutable';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status
               AND NOT (
                    (OLD.status = 'queued' AND NEW.status IN ('running', 'completed', 'failed'))
                    OR (OLD.status = 'running' AND NEW.status IN ('completed', 'failed'))
               ) THEN
                RAISE EXCEPTION 'invalid AI forecast run status transition';
            END IF;
        END IF;
    END IF;
    IF NEW.cohort_snapshot_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT state, expected_pair_count
    INTO snapshot_state, snapshot_pair_count
    FROM public.ai_forecast_cohort_snapshots
    WHERE id = NEW.cohort_snapshot_id;
    IF NOT FOUND OR snapshot_state <> 'sealed' THEN
        RAISE EXCEPTION 'AI forecast run requires a sealed cohort snapshot';
    END IF;
    IF NEW.expected_pair_count IS DISTINCT FROM snapshot_pair_count THEN
        RAISE EXCEPTION 'AI forecast run pair count differs from its sealed cohort';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_ai_forecast_runs_cohort_lineage
BEFORE INSERT OR UPDATE
ON ai_forecast_runs
FOR EACH ROW EXECUTE FUNCTION public.guard_ai_forecast_run_cohort_lineage();

CREATE INDEX idx_ai_forecast_runs_cohort_snapshot
    ON ai_forecast_runs (cohort_snapshot_id)
    WHERE cohort_snapshot_id IS NOT NULL;

CREATE TABLE retail_outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'retail.sales_generation_promoted.v1',
        'retail.pnl_generation_promoted.v1',
        'retail.salary_import_completed.v1',
        'retail.planning_forecast_promoted.v1',
        'retail.grile_manifest_approved.v1'
    )),
    event_schema_version SMALLINT NOT NULL DEFAULT 1
        CHECK (event_schema_version = 1),
    aggregate_type TEXT NOT NULL
        CHECK (aggregate_type ~ '^[a-z][a-z0-9_.-]{0,79}$'),
    aggregate_id TEXT NOT NULL
        CHECK (
            aggregate_id ~ '^[A-Za-z][A-Za-z0-9._-]{0,127}$'
            AND aggregate_id !~ '^[0-9]{13}$'
            AND aggregate_id !~* '^sp1_[0-9a-f]{64}$'
            AND aggregate_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        ),
    generation_hash TEXT NOT NULL CHECK (generation_hash ~ '^[0-9a-f]{64}$'),
    revision BIGINT NOT NULL CHECK (revision >= 1),
    aggregate_sequence BIGINT NOT NULL CHECK (aggregate_sequence >= 1),
    event_key TEXT NOT NULL UNIQUE,
    payload JSONB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'processing', 'completed', 'dead')),
    attempt_count SMALLINT NOT NULL DEFAULT 0
        CHECK (attempt_count BETWEEN 0 AND 8),
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claim_owner TEXT
        CHECK (claim_owner IS NULL OR claim_owner ~ '^[A-Za-z0-9._-]{1,128}$'),
    claim_epoch BIGINT NOT NULL DEFAULT 0 CHECK (claim_epoch >= 0),
    lease_until TIMESTAMPTZ,
    claimed_at TIMESTAMPTZ,
    last_error_code TEXT
        CHECK (last_error_code IS NULL OR last_error_code ~ '^[a-z][a-z0-9_.-]{0,79}$'),
    last_error_at TIMESTAMPTZ,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    dead_at TIMESTAMPTZ,
    replay_count INTEGER NOT NULL DEFAULT 0 CHECK (replay_count >= 0),
    UNIQUE (aggregate_type, aggregate_id, aggregate_sequence),
    CHECK (
        event_key = event_type || ':' || aggregate_id || ':' || generation_hash || ':' || revision::TEXT
    ),
    CHECK (
        payload_sha256 = encode(
            digest(convert_to(payload::TEXT, 'UTF8'), 'sha256'),
            'hex'
        )
    ),
    CHECK (
        jsonb_typeof(payload) = 'object'
        AND payload ?& ARRAY[
            'event_schema', 'aggregate_type', 'aggregate_id',
            'generation_hash', 'source_hash', 'month', 'revision', 'occurred_at'
        ]
        AND payload - ARRAY[
            'event_schema', 'aggregate_type', 'aggregate_id', 'generation_hash',
            'source_hash', 'cutoff', 'month', 'revision', 'occurred_at'
        ] = '{}'::JSONB
        AND jsonb_typeof(payload->'event_schema') = 'string'
        AND payload->>'event_schema' = event_type
        AND jsonb_typeof(payload->'aggregate_type') = 'string'
        AND payload->>'aggregate_type' = aggregate_type
        AND jsonb_typeof(payload->'aggregate_id') = 'string'
        AND payload->>'aggregate_id' = aggregate_id
        AND jsonb_typeof(payload->'generation_hash') = 'string'
        AND payload->>'generation_hash' = generation_hash
        AND jsonb_typeof(payload->'revision') = 'number'
        AND payload->>'revision' = revision::TEXT
        AND jsonb_typeof(payload->'occurred_at') = 'string'
        AND payload->>'occurred_at' ~
            '^[0-9]{4}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?(Z|[+-][0-2][0-9]:[0-5][0-9])$'
        AND (payload->>'occurred_at')::TIMESTAMPTZ = occurred_at
        AND jsonb_typeof(payload->'source_hash') = 'string'
        AND payload->>'source_hash' ~ '^[0-9a-f]{64}$'
        AND jsonb_typeof(payload->'month') = 'string'
        AND payload->>'month' ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
        AND CASE
            WHEN NOT payload ? 'cutoff' THEN TRUE
            WHEN jsonb_typeof(payload->'cutoff') <> 'string' THEN FALSE
            WHEN payload->>'cutoff' ~
                '^[0-9]{4}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])$'
            THEN to_char((payload->>'cutoff')::DATE, 'YYYY-MM-DD') = payload->>'cutoff'
            WHEN payload->>'cutoff' ~
                '^[0-9]{4}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?(Z|[+-][0-2][0-9]:[0-5][0-9])$'
            THEN (payload->>'cutoff')::TIMESTAMPTZ IS NOT NULL
            ELSE FALSE
        END
    ),
    CHECK (
        (state = 'pending'
            AND claim_owner IS NULL
            AND lease_until IS NULL
            AND completed_at IS NULL
            AND dead_at IS NULL)
        OR (state = 'processing'
            AND claim_owner IS NOT NULL
            AND claim_epoch > 0
            AND lease_until IS NOT NULL
            AND claimed_at IS NOT NULL
            AND completed_at IS NULL
            AND dead_at IS NULL)
        OR (state = 'completed'
            AND claim_owner IS NULL
            AND lease_until IS NULL
            AND completed_at IS NOT NULL
            AND dead_at IS NULL)
        OR (state = 'dead'
            AND claim_owner IS NULL
            AND lease_until IS NULL
            AND completed_at IS NULL
            AND dead_at IS NOT NULL
            AND attempt_count = 8)
    ),
    CHECK (
        attempt_count <> 0
        OR (last_error_code IS NULL AND last_error_at IS NULL)
    )
);

CREATE INDEX idx_retail_outbox_claimable
    ON retail_outbox_events (available_at, created_at, id)
    WHERE state = 'pending';
CREATE INDEX idx_retail_outbox_aggregate_head
    ON retail_outbox_events (
        aggregate_type,
        aggregate_id,
        aggregate_sequence,
        state
    );
CREATE INDEX idx_retail_outbox_processing_lease
    ON retail_outbox_events (lease_until, id)
    WHERE state = 'processing';
CREATE INDEX idx_retail_outbox_type_state_created
    ON retail_outbox_events (event_type, state, created_at);
CREATE INDEX idx_retail_outbox_dead
    ON retail_outbox_events (dead_at, id)
    WHERE state = 'dead';

CREATE OR REPLACE FUNCTION public.emit_retail_outbox_event_internal(
    p_event_type TEXT,
    p_aggregate_type TEXT,
    p_aggregate_id TEXT,
    p_generation_hash TEXT,
    p_source_hash TEXT,
    p_cutoff TIMESTAMPTZ,
    p_month TEXT,
    p_revision BIGINT,
    p_occurred_at TIMESTAMPTZ
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    canonical_payload JSONB;
    canonical_payload_sha256 TEXT;
    canonical_event_key TEXT;
    next_sequence BIGINT;
    existing public.retail_outbox_events%ROWTYPE;
    event_id UUID;
BEGIN
    IF NOT (
        (p_event_type = 'retail.sales_generation_promoted.v1'
            AND p_aggregate_type = 'sales_generation')
        OR (p_event_type = 'retail.pnl_generation_promoted.v1'
            AND p_aggregate_type = 'pnl_generation')
        OR (p_event_type = 'retail.salary_import_completed.v1'
            AND p_aggregate_type = 'salary_import')
        OR (p_event_type = 'retail.planning_forecast_promoted.v1'
            AND p_aggregate_type = 'planning_forecast')
        OR (p_event_type = 'retail.grile_manifest_approved.v1'
            AND p_aggregate_type = 'grile_manifest')
    ) THEN
        RAISE EXCEPTION 'unsupported transactional outbox producer contract';
    END IF;
    IF p_aggregate_id IS NULL
       OR p_generation_hash IS NULL
       OR p_source_hash IS NULL
       OR p_month IS NULL
       OR p_revision IS NULL
       OR p_occurred_at IS NULL THEN
        RAISE EXCEPTION 'transactional outbox producer lineage is incomplete';
    END IF;

    canonical_payload := jsonb_strip_nulls(jsonb_build_object(
        'event_schema', p_event_type,
        'aggregate_type', p_aggregate_type,
        'aggregate_id', p_aggregate_id,
        'generation_hash', p_generation_hash,
        'source_hash', p_source_hash,
        'cutoff', CASE
            WHEN p_cutoff IS NULL THEN NULL
            ELSE to_char(
                p_cutoff AT TIME ZONE 'UTC',
                'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
            )
        END,
        'month', p_month,
        'revision', p_revision,
        'occurred_at', to_char(
            p_occurred_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
        )
    ));
    canonical_payload_sha256 := encode(
        digest(convert_to(canonical_payload::TEXT, 'UTF8'), 'sha256'),
        'hex'
    );
    canonical_event_key :=
        p_event_type || ':' || p_aggregate_id || ':' || p_generation_hash || ':' || p_revision::TEXT;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(p_aggregate_type || E'\x1f' || p_aggregate_id, 0)
    );
    SELECT * INTO existing
    FROM public.retail_outbox_events
    WHERE event_key = canonical_event_key
    FOR UPDATE;
    IF FOUND THEN
        IF existing.event_type IS DISTINCT FROM p_event_type
           OR existing.aggregate_type IS DISTINCT FROM p_aggregate_type
           OR existing.aggregate_id IS DISTINCT FROM p_aggregate_id
           OR existing.generation_hash IS DISTINCT FROM p_generation_hash
           OR existing.revision IS DISTINCT FROM p_revision
           OR existing.payload IS DISTINCT FROM canonical_payload
           OR existing.payload_sha256 IS DISTINCT FROM canonical_payload_sha256
           OR existing.occurred_at IS DISTINCT FROM p_occurred_at THEN
            RAISE EXCEPTION 'transactional outbox idempotency key payload differs';
        END IF;
        RETURN existing.id;
    END IF;

    SELECT COALESCE(MAX(aggregate_sequence), 0) + 1
    INTO next_sequence
    FROM public.retail_outbox_events
    WHERE aggregate_type = p_aggregate_type
      AND aggregate_id = p_aggregate_id;

    INSERT INTO public.retail_outbox_events (
        event_type,
        aggregate_type,
        aggregate_id,
        generation_hash,
        revision,
        aggregate_sequence,
        event_key,
        payload,
        payload_sha256,
        occurred_at
    ) VALUES (
        p_event_type,
        p_aggregate_type,
        p_aggregate_id,
        p_generation_hash,
        p_revision,
        next_sequence,
        canonical_event_key,
        canonical_payload,
        canonical_payload_sha256,
        p_occurred_at
    )
    RETURNING id INTO event_id;
    RETURN event_id;
END
$$;

CREATE OR REPLACE FUNCTION public.emit_retail_sales_generation_promoted(
    p_aggregate_id TEXT,
    p_generation_hash TEXT,
    p_source_hash TEXT,
    p_cutoff TIMESTAMPTZ,
    p_month TEXT,
    p_revision BIGINT,
    p_occurred_at TIMESTAMPTZ
)
RETURNS UUID
LANGUAGE SQL
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT public.emit_retail_outbox_event_internal(
        'retail.sales_generation_promoted.v1', 'sales_generation',
        p_aggregate_id, p_generation_hash, p_source_hash, p_cutoff,
        p_month, p_revision, p_occurred_at
    )
$$;

CREATE OR REPLACE FUNCTION public.emit_retail_pnl_generation_promoted(
    p_aggregate_id TEXT,
    p_generation_hash TEXT,
    p_source_hash TEXT,
    p_cutoff TIMESTAMPTZ,
    p_month TEXT,
    p_revision BIGINT,
    p_occurred_at TIMESTAMPTZ
)
RETURNS UUID
LANGUAGE SQL
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT public.emit_retail_outbox_event_internal(
        'retail.pnl_generation_promoted.v1', 'pnl_generation',
        p_aggregate_id, p_generation_hash, p_source_hash, p_cutoff,
        p_month, p_revision, p_occurred_at
    )
$$;

CREATE OR REPLACE FUNCTION public.emit_retail_salary_import_completed(
    p_aggregate_id TEXT,
    p_generation_hash TEXT,
    p_source_hash TEXT,
    p_cutoff TIMESTAMPTZ,
    p_month TEXT,
    p_revision BIGINT,
    p_occurred_at TIMESTAMPTZ
)
RETURNS UUID
LANGUAGE SQL
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT public.emit_retail_outbox_event_internal(
        'retail.salary_import_completed.v1', 'salary_import',
        p_aggregate_id, p_generation_hash, p_source_hash, p_cutoff,
        p_month, p_revision, p_occurred_at
    )
$$;

CREATE OR REPLACE FUNCTION public.emit_retail_planning_forecast_promoted(
    p_aggregate_id TEXT,
    p_generation_hash TEXT,
    p_source_hash TEXT,
    p_cutoff TIMESTAMPTZ,
    p_month TEXT,
    p_revision BIGINT,
    p_occurred_at TIMESTAMPTZ
)
RETURNS UUID
LANGUAGE SQL
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT public.emit_retail_outbox_event_internal(
        'retail.planning_forecast_promoted.v1', 'planning_forecast',
        p_aggregate_id, p_generation_hash, p_source_hash, p_cutoff,
        p_month, p_revision, p_occurred_at
    )
$$;

CREATE OR REPLACE FUNCTION public.emit_retail_grile_manifest_approved(
    p_aggregate_id TEXT,
    p_generation_hash TEXT,
    p_source_hash TEXT,
    p_cutoff TIMESTAMPTZ,
    p_month TEXT,
    p_revision BIGINT,
    p_occurred_at TIMESTAMPTZ
)
RETURNS UUID
LANGUAGE SQL
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT public.emit_retail_outbox_event_internal(
        'retail.grile_manifest_approved.v1', 'grile_manifest',
        p_aggregate_id, p_generation_hash, p_source_hash, p_cutoff,
        p_month, p_revision, p_occurred_at
    )
$$;

CREATE TABLE retail_outbox_consumer_receipts (
    event_id UUID NOT NULL REFERENCES retail_outbox_events(id) ON DELETE RESTRICT,
    consumer TEXT NOT NULL CHECK (consumer ~ '^[a-z][a-z0-9_.-]{0,79}$'),
    domain_generation_key TEXT NOT NULL
        CHECK (
            domain_generation_key ~ '^[A-Za-z][A-Za-z0-9._:-]{0,239}$'
            AND domain_generation_key !~ '(^|[^0-9])[0-9]{13}([^0-9]|$)'
            AND domain_generation_key !~* 'sp1_[0-9a-f]{64}'
            AND domain_generation_key !~* '(^|[^0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}([^0-9a-f]|$)'
        ),
    effect_sha256 TEXT NOT NULL CHECK (effect_sha256 ~ '^[0-9a-f]{64}$'),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, consumer),
    UNIQUE (consumer, domain_generation_key)
);

CREATE INDEX idx_retail_outbox_receipts_received
    ON retail_outbox_consumer_receipts (received_at, consumer);

CREATE TABLE retail_outbox_replay_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES retail_outbox_events(id) ON DELETE RESTRICT,
    replay_number INTEGER NOT NULL CHECK (replay_number >= 1),
    previous_attempt_count SMALLINT NOT NULL CHECK (previous_attempt_count = 8),
    previous_dead_at TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL CHECK (reason ~ '^[a-z][a-z0-9_.:-]{0,79}$'),
    requested_by_sub_sha256 TEXT NOT NULL
        CHECK (requested_by_sub_sha256 ~ '^[0-9a-f]{64}$'),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (event_id, replay_number)
);

CREATE INDEX idx_retail_outbox_replay_requested
    ON retail_outbox_replay_audit (requested_at, event_id);

CREATE OR REPLACE FUNCTION public.guard_retail_outbox_event_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'transactional outbox events cannot be deleted';
    END IF;
    IF OLD.id IS DISTINCT FROM NEW.id
       OR OLD.event_type IS DISTINCT FROM NEW.event_type
       OR OLD.event_schema_version IS DISTINCT FROM NEW.event_schema_version
       OR OLD.aggregate_type IS DISTINCT FROM NEW.aggregate_type
       OR OLD.aggregate_id IS DISTINCT FROM NEW.aggregate_id
       OR OLD.generation_hash IS DISTINCT FROM NEW.generation_hash
       OR OLD.revision IS DISTINCT FROM NEW.revision
       OR OLD.aggregate_sequence IS DISTINCT FROM NEW.aggregate_sequence
       OR OLD.event_key IS DISTINCT FROM NEW.event_key
       OR OLD.payload IS DISTINCT FROM NEW.payload
       OR OLD.payload_sha256 IS DISTINCT FROM NEW.payload_sha256
       OR OLD.occurred_at IS DISTINCT FROM NEW.occurred_at
       OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
        RAISE EXCEPTION 'transactional outbox event identity and payload are immutable';
    END IF;
    IF NEW.updated_at < OLD.updated_at
       OR NEW.claim_epoch < OLD.claim_epoch THEN
        RAISE EXCEPTION 'transactional outbox clocks and fences cannot regress';
    END IF;
    IF OLD.state = 'completed' THEN
        RAISE EXCEPTION 'completed transactional outbox event is immutable';
    END IF;
    IF OLD.state = 'pending' THEN
        IF NEW.state <> 'processing'
           OR NEW.claim_epoch <= OLD.claim_epoch
           OR NEW.attempt_count <> OLD.attempt_count + 1
           OR NEW.replay_count <> OLD.replay_count THEN
            RAISE EXCEPTION 'pending outbox event may only enter a new fenced attempt';
        END IF;
    ELSIF OLD.state = 'processing' THEN
        IF NEW.state = 'processing' THEN
            IF NEW.claim_owner IS DISTINCT FROM OLD.claim_owner
               OR NEW.claim_epoch IS DISTINCT FROM OLD.claim_epoch
               OR NEW.attempt_count IS DISTINCT FROM OLD.attempt_count
               OR NEW.replay_count IS DISTINCT FROM OLD.replay_count THEN
                RAISE EXCEPTION 'processing outbox lease renewal cannot change its fence';
            END IF;
        ELSIF NEW.state IN ('pending', 'completed', 'dead') THEN
            IF NEW.claim_epoch IS DISTINCT FROM OLD.claim_epoch
               OR NEW.attempt_count IS DISTINCT FROM OLD.attempt_count
               OR NEW.replay_count IS DISTINCT FROM OLD.replay_count THEN
                RAISE EXCEPTION 'outbox attempt completion cannot change its fence or attempt';
            END IF;
        ELSE
            RAISE EXCEPTION 'invalid processing outbox transition';
        END IF;
    ELSIF OLD.state = 'dead' THEN
        IF NEW.state <> 'pending'
           OR NEW.replay_count <> OLD.replay_count + 1
           OR NEW.attempt_count <> 0
           OR NEW.claim_epoch IS DISTINCT FROM OLD.claim_epoch
           OR NEW.last_error_code IS NOT NULL
           OR NEW.last_error_at IS NOT NULL
           OR NOT EXISTS (
                SELECT 1
                FROM public.retail_outbox_replay_audit AS replay
                WHERE replay.event_id = OLD.id
                  AND replay.replay_number = NEW.replay_count
                  AND replay.previous_attempt_count = OLD.attempt_count
                  AND replay.previous_dead_at = OLD.dead_at
           ) THEN
            RAISE EXCEPTION 'dead outbox event requires matching append-only replay evidence';
        END IF;
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_retail_outbox_events_guard
BEFORE UPDATE OR DELETE ON retail_outbox_events
FOR EACH ROW EXECUTE FUNCTION public.guard_retail_outbox_event_mutation();

CREATE OR REPLACE FUNCTION public.reject_retail_outbox_evidence_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    RAISE EXCEPTION 'transactional outbox delivery evidence is append-only';
END
$$;

CREATE TRIGGER trg_retail_outbox_receipts_immutable
BEFORE UPDATE OR DELETE ON retail_outbox_consumer_receipts
FOR EACH ROW EXECUTE FUNCTION public.reject_retail_outbox_evidence_mutation();

CREATE OR REPLACE FUNCTION public.guard_retail_outbox_replay_insert()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    target public.retail_outbox_events%ROWTYPE;
BEGIN
    SELECT * INTO target
    FROM public.retail_outbox_events
    WHERE id = NEW.event_id
    FOR UPDATE;
    IF NOT FOUND
       OR target.state <> 'dead'
       OR target.attempt_count <> 8
       OR target.dead_at IS DISTINCT FROM NEW.previous_dead_at
       OR target.attempt_count IS DISTINCT FROM NEW.previous_attempt_count
       OR NEW.replay_number <> target.replay_count + 1 THEN
        RAISE EXCEPTION 'only the next replay of an exact dead event may be audited';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_retail_outbox_replay_audit_insert
BEFORE INSERT ON retail_outbox_replay_audit
FOR EACH ROW EXECUTE FUNCTION public.guard_retail_outbox_replay_insert();

CREATE TRIGGER trg_retail_outbox_replay_audit_immutable
BEFORE UPDATE OR DELETE ON retail_outbox_replay_audit
FOR EACH ROW EXECUTE FUNCTION public.reject_retail_outbox_evidence_mutation();

REVOKE ALL ON TABLE
    ai_forecast_cohort_snapshots,
    ai_forecast_cohort_rows,
    retail_outbox_events,
    retail_outbox_consumer_receipts,
    retail_outbox_replay_audit
FROM PUBLIC, unihub_web_read, unihub_business_write, unihub_sales_import,
    unihub_finance_import, unihub_operations, unihub_migrate;

REVOKE ALL ON FUNCTION
    public.ai_forecast_cohort_rows_sha256(UUID),
    public.guard_ai_forecast_cohort_snapshot_mutation(),
    public.guard_ai_forecast_cohort_row_mutation(),
    public.seal_ai_forecast_cohort_snapshot(UUID),
    public.guard_ai_forecast_run_cohort_lineage(),
    public.guard_retail_outbox_event_mutation(),
    public.guard_retail_outbox_replay_insert(),
    public.reject_retail_outbox_evidence_mutation(),
    public.emit_retail_outbox_event_internal(
        TEXT, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, BIGINT, TIMESTAMPTZ
    ),
    public.emit_retail_sales_generation_promoted(
        TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, BIGINT, TIMESTAMPTZ
    ),
    public.emit_retail_pnl_generation_promoted(
        TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, BIGINT, TIMESTAMPTZ
    ),
    public.emit_retail_salary_import_completed(
        TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, BIGINT, TIMESTAMPTZ
    ),
    public.emit_retail_planning_forecast_promoted(
        TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, BIGINT, TIMESTAMPTZ
    ),
    public.emit_retail_grile_manifest_approved(
        TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, BIGINT, TIMESTAMPTZ
    )
FROM PUBLIC, unihub_web_read, unihub_business_write, unihub_sales_import,
    unihub_finance_import, unihub_operations, unihub_migrate;

GRANT SELECT ON TABLE
    ai_forecast_cohort_snapshots,
    ai_forecast_cohort_rows
TO unihub_web_read, unihub_operations;

GRANT INSERT ON TABLE
    ai_forecast_cohort_snapshots,
    ai_forecast_cohort_rows
TO unihub_operations;

GRANT EXECUTE ON FUNCTION public.seal_ai_forecast_cohort_snapshot(UUID)
TO unihub_operations;

GRANT SELECT, INSERT, UPDATE ON TABLE ai_forecast_runs TO unihub_operations;
GRANT SELECT, INSERT ON TABLE
    ai_forecast_store_month,
    ai_forecast_store_day
TO unihub_operations;
GRANT USAGE, SELECT ON SEQUENCE ai_forecast_runs_id_seq TO unihub_operations;

GRANT SELECT ON TABLE retail_outbox_events TO unihub_operations;

GRANT EXECUTE ON FUNCTION public.emit_retail_sales_generation_promoted(
    TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, BIGINT, TIMESTAMPTZ
) TO unihub_sales_import;
GRANT EXECUTE ON FUNCTION public.emit_retail_pnl_generation_promoted(
    TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, BIGINT, TIMESTAMPTZ
) TO unihub_finance_import;
GRANT EXECUTE ON FUNCTION public.emit_retail_salary_import_completed(
    TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, BIGINT, TIMESTAMPTZ
) TO unihub_migrate;
GRANT EXECUTE ON FUNCTION public.emit_retail_planning_forecast_promoted(
    TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, BIGINT, TIMESTAMPTZ
) TO unihub_operations;
GRANT EXECUTE ON FUNCTION public.emit_retail_grile_manifest_approved(
    TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, BIGINT, TIMESTAMPTZ
) TO unihub_business_write;

GRANT UPDATE (
    state,
    attempt_count,
    available_at,
    claim_owner,
    claim_epoch,
    lease_until,
    claimed_at,
    last_error_code,
    last_error_at,
    updated_at,
    completed_at,
    dead_at,
    replay_count
) ON retail_outbox_events TO unihub_operations;

GRANT SELECT, INSERT ON TABLE
    retail_outbox_consumer_receipts,
    retail_outbox_replay_audit
TO unihub_operations;

COMMENT ON TABLE ai_forecast_cohort_snapshots IS
    'Immutable as-of AI cohort identity; Release A creates no snapshot automatically.';
COMMENT ON TABLE ai_forecast_cohort_rows IS
    'Append-only historical store authority rows; current stores is not a historical fallback.';
COMMENT ON TABLE retail_outbox_events IS
    'At-least-once ordered transactional outbox; Release A has no producer or dispatcher.';
COMMENT ON FUNCTION public.emit_retail_outbox_event_internal(
    TEXT, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, BIGINT, TIMESTAMPTZ
) IS 'Private canonical outbox insert; event-specific wrappers are the only runtime producer surface.';
COMMENT ON TABLE retail_outbox_consumer_receipts IS
    'Effective-once consumer and domain-generation receipt evidence.';
COMMENT ON TABLE retail_outbox_replay_audit IS
    'Append-only audit for bounded admin replay of dead events.';
