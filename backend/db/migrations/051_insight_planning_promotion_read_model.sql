-- Explicit Planning promotion boundary for UniHub Insight.
--
-- Completed forecast runs remain candidates. Only a run selected through the
-- revision-CAS head below is authoritative. Target scenarios are published
-- only when their finalized values and exact versioned rule snapshot still
-- reconcile with the append-only rule registry. No business data is promoted
-- by this migration.

CREATE TABLE planning_forecast_heads (
    forecast_month TEXT NOT NULL
        CHECK (forecast_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    metric TEXT NOT NULL CHECK (metric IN ('sales_value', 'units')),
    horizon TEXT NOT NULL CHECK (horizon IN ('current_month', 'rolling_12m')),
    run_id BIGINT NOT NULL REFERENCES ai_forecast_runs(id) ON DELETE RESTRICT,
    revision BIGINT NOT NULL CHECK (revision >= 1),
    run_sha256 TEXT NOT NULL CHECK (run_sha256 ~ '^[0-9a-f]{64}$'),
    row_count BIGINT NOT NULL CHECK (row_count > 0),
    approval_artifact_sha256 TEXT NOT NULL
        CHECK (approval_artifact_sha256 ~ '^[0-9a-f]{64}$'),
    promoted_by_sub TEXT NOT NULL CHECK (btrim(promoted_by_sub) <> ''),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (forecast_month, metric, horizon)
);

CREATE TABLE planning_forecast_promotions (
    id BIGSERIAL PRIMARY KEY,
    forecast_month TEXT NOT NULL
        CHECK (forecast_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    metric TEXT NOT NULL CHECK (metric IN ('sales_value', 'units')),
    horizon TEXT NOT NULL CHECK (horizon IN ('current_month', 'rolling_12m')),
    from_run_id BIGINT REFERENCES ai_forecast_runs(id) ON DELETE RESTRICT,
    to_run_id BIGINT NOT NULL REFERENCES ai_forecast_runs(id) ON DELETE RESTRICT,
    head_revision BIGINT NOT NULL CHECK (head_revision >= 1),
    action TEXT NOT NULL CHECK (action IN ('promote', 'rollback')),
    run_sha256 TEXT NOT NULL CHECK (run_sha256 ~ '^[0-9a-f]{64}$'),
    row_count BIGINT NOT NULL CHECK (row_count > 0),
    approval_artifact_sha256 TEXT NOT NULL
        CHECK (approval_artifact_sha256 ~ '^[0-9a-f]{64}$'),
    requested_by_sub TEXT NOT NULL CHECK (btrim(requested_by_sub) <> ''),
    reason TEXT NOT NULL CHECK (btrim(reason) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (forecast_month, metric, horizon, head_revision)
);

CREATE INDEX idx_planning_forecast_promotions_target
    ON planning_forecast_promotions (
        forecast_month, metric, horizon, to_run_id, head_revision
    );

CREATE OR REPLACE FUNCTION public.planning_forecast_run_sha256(p_run_id BIGINT)
RETURNS TEXT
LANGUAGE SQL
STABLE
STRICT
SET search_path = pg_catalog, public
AS $$
    SELECT encode(
        digest(
            convert_to(
                jsonb_build_array(
                    run.id,
                    run.forecast_month,
                    run.source_month,
                    run.metric,
                    run.horizon,
                    run.model_name,
                    run.model_mode,
                    run.variant,
                    run.status,
                    run.generated_at,
                    run.metadata
                )::text
                || E'\x1e'
                || COALESCE(
                    string_agg(
                        jsonb_build_array(
                            item.site_code,
                            item.forecast_sales,
                            item.metadata
                        )::text,
                        E'\x1e'
                        ORDER BY item.site_code COLLATE "C"
                    ),
                    ''
                ),
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    )
    FROM public.ai_forecast_runs AS run
    LEFT JOIN public.ai_forecast_store_month AS item
      ON item.run_id = run.id
    WHERE run.id = p_run_id
    GROUP BY
        run.id,
        run.forecast_month,
        run.source_month,
        run.metric,
        run.horizon,
        run.model_name,
        run.model_mode,
        run.variant,
        run.status,
        run.generated_at,
        run.metadata
$$;

CREATE OR REPLACE FUNCTION public.guard_planning_forecast_head_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'planning forecast head cannot be deleted';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.revision <> 1 THEN
            RAISE EXCEPTION 'planning forecast head must start at revision 1';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.forecast_month IS DISTINCT FROM NEW.forecast_month
       OR OLD.metric IS DISTINCT FROM NEW.metric
       OR OLD.horizon IS DISTINCT FROM NEW.horizon
       OR NEW.revision <> OLD.revision + 1
       OR OLD.run_id IS NOT DISTINCT FROM NEW.run_id THEN
        RAISE EXCEPTION 'planning forecast head accepts only a new run and revision CAS advance';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_planning_forecast_heads_cas
BEFORE INSERT OR UPDATE OR DELETE ON planning_forecast_heads
FOR EACH ROW EXECUTE FUNCTION public.guard_planning_forecast_head_mutation();

CREATE OR REPLACE FUNCTION public.guard_planning_forecast_promotion_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    head planning_forecast_heads%ROWTYPE;
    target ai_forecast_runs%ROWTYPE;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'planning forecast promotion ledger is append-only';
    END IF;

    SELECT * INTO head
    FROM public.planning_forecast_heads
    WHERE forecast_month = NEW.forecast_month
      AND metric = NEW.metric
      AND horizon = NEW.horizon;
    IF NOT FOUND
       OR head.run_id IS DISTINCT FROM NEW.to_run_id
       OR head.revision IS DISTINCT FROM NEW.head_revision
       OR head.run_sha256 IS DISTINCT FROM NEW.run_sha256
       OR head.row_count IS DISTINCT FROM NEW.row_count
       OR head.approval_artifact_sha256 IS DISTINCT FROM NEW.approval_artifact_sha256
       OR head.promoted_by_sub IS DISTINCT FROM NEW.requested_by_sub THEN
        RAISE EXCEPTION 'planning forecast promotion must attest to the current CAS head';
    END IF;

    SELECT * INTO target
    FROM public.ai_forecast_runs
    WHERE id = NEW.to_run_id;
    IF NOT FOUND
       OR target.status <> 'completed'
       OR target.forecast_month IS DISTINCT FROM NEW.forecast_month
       OR target.metric IS DISTINCT FROM NEW.metric
       OR target.horizon IS DISTINCT FROM NEW.horizon
       OR public.planning_forecast_run_sha256(target.id) IS DISTINCT FROM NEW.run_sha256 THEN
        RAISE EXCEPTION 'planning forecast promotion target is not the frozen completed run';
    END IF;

    IF NEW.action = 'rollback' AND NOT EXISTS (
        SELECT 1
        FROM public.planning_forecast_promotions AS prior
        WHERE prior.forecast_month = NEW.forecast_month
          AND prior.metric = NEW.metric
          AND prior.horizon = NEW.horizon
          AND prior.to_run_id = NEW.to_run_id
          AND prior.run_sha256 = NEW.run_sha256
    ) THEN
        RAISE EXCEPTION 'planning forecast rollback target lacks retained promotion lineage';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_planning_forecast_promotions_immutable
BEFORE INSERT OR UPDATE OR DELETE ON planning_forecast_promotions
FOR EACH ROW EXECUTE FUNCTION public.guard_planning_forecast_promotion_mutation();

CREATE OR REPLACE FUNCTION public.advance_planning_forecast_head(
    p_forecast_month TEXT,
    p_metric TEXT,
    p_horizon TEXT,
    p_to_run_id BIGINT,
    p_expected_revision BIGINT,
    p_approval_artifact_sha256 TEXT,
    p_requested_by_sub TEXT,
    p_reason TEXT,
    p_action TEXT DEFAULT 'promote'
)
RETURNS public.planning_forecast_heads
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    target ai_forecast_runs%ROWTYPE;
    current_head planning_forecast_heads%ROWTYPE;
    next_head planning_forecast_heads%ROWTYPE;
    target_hash TEXT;
    target_count BIGINT;
    next_revision BIGINT;
BEGIN
    IF p_forecast_month !~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
       OR p_metric NOT IN ('sales_value', 'units')
       OR p_horizon NOT IN ('current_month', 'rolling_12m')
       OR p_expected_revision < 0
       OR p_approval_artifact_sha256 !~ '^[0-9a-f]{64}$'
       OR NULLIF(btrim(p_requested_by_sub), '') IS NULL
       OR NULLIF(btrim(p_reason), '') IS NULL
       OR p_action NOT IN ('promote', 'rollback') THEN
        RAISE EXCEPTION 'planning forecast promotion request is invalid';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            'planning-forecast:' || p_forecast_month || ':' || p_metric || ':' || p_horizon,
            0
        )
    );

    SELECT * INTO target
    FROM public.ai_forecast_runs
    WHERE id = p_to_run_id;
    IF NOT FOUND
       OR target.status <> 'completed'
       OR target.forecast_month IS DISTINCT FROM p_forecast_month
       OR target.metric IS DISTINCT FROM p_metric
       OR target.horizon IS DISTINCT FROM p_horizon THEN
        RAISE EXCEPTION 'planning forecast promotion requires a matching completed run';
    END IF;

    SELECT COUNT(*)::BIGINT INTO target_count
    FROM public.ai_forecast_store_month
    WHERE run_id = p_to_run_id;
    target_hash := public.planning_forecast_run_sha256(p_to_run_id);
    IF target_count <= 0 OR target_hash IS NULL THEN
        RAISE EXCEPTION 'planning forecast promotion requires a non-empty frozen run';
    END IF;

    SELECT * INTO current_head
    FROM public.planning_forecast_heads
    WHERE forecast_month = p_forecast_month
      AND metric = p_metric
      AND horizon = p_horizon
    FOR UPDATE;

    IF FOUND THEN
        IF current_head.revision IS DISTINCT FROM p_expected_revision THEN
            RAISE EXCEPTION 'planning forecast head revision CAS failed';
        END IF;
        IF current_head.run_id IS NOT DISTINCT FROM p_to_run_id THEN
            RAISE EXCEPTION 'planning forecast head already selects this run';
        END IF;
        IF p_action = 'rollback' AND NOT EXISTS (
            SELECT 1
            FROM public.planning_forecast_promotions AS prior
            WHERE prior.forecast_month = p_forecast_month
              AND prior.metric = p_metric
              AND prior.horizon = p_horizon
              AND prior.to_run_id = p_to_run_id
              AND prior.run_sha256 = target_hash
        ) THEN
            RAISE EXCEPTION 'planning forecast rollback target lacks retained promotion lineage';
        END IF;
        next_revision := current_head.revision + 1;
        UPDATE public.planning_forecast_heads
        SET run_id = p_to_run_id,
            revision = next_revision,
            run_sha256 = target_hash,
            row_count = target_count,
            approval_artifact_sha256 = p_approval_artifact_sha256,
            promoted_by_sub = btrim(p_requested_by_sub),
            updated_at = now()
        WHERE forecast_month = p_forecast_month
          AND metric = p_metric
          AND horizon = p_horizon
          AND revision = p_expected_revision
        RETURNING * INTO next_head;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'planning forecast head revision CAS failed';
        END IF;
    ELSE
        IF p_expected_revision <> 0 OR p_action <> 'promote' THEN
            RAISE EXCEPTION 'planning forecast head creation requires promote at revision 0';
        END IF;
        next_revision := 1;
        INSERT INTO public.planning_forecast_heads (
            forecast_month,
            metric,
            horizon,
            run_id,
            revision,
            run_sha256,
            row_count,
            approval_artifact_sha256,
            promoted_by_sub
        ) VALUES (
            p_forecast_month,
            p_metric,
            p_horizon,
            p_to_run_id,
            next_revision,
            target_hash,
            target_count,
            p_approval_artifact_sha256,
            btrim(p_requested_by_sub)
        )
        RETURNING * INTO next_head;
    END IF;

    INSERT INTO public.planning_forecast_promotions (
        forecast_month,
        metric,
        horizon,
        from_run_id,
        to_run_id,
        head_revision,
        action,
        run_sha256,
        row_count,
        approval_artifact_sha256,
        requested_by_sub,
        reason
    ) VALUES (
        p_forecast_month,
        p_metric,
        p_horizon,
        current_head.run_id,
        p_to_run_id,
        next_revision,
        p_action,
        target_hash,
        target_count,
        p_approval_artifact_sha256,
        btrim(p_requested_by_sub),
        btrim(p_reason)
    );

    RETURN next_head;
END
$$;

CREATE OR REPLACE VIEW reporting_source_snapshot_v3 (
    domain,
    period,
    source,
    source_generation,
    authority,
    authority_head,
    contract_version,
    rule_version,
    status,
    as_of,
    cutoff,
    is_final,
    coverage_numerator,
    coverage_denominator,
    produced_at,
    warnings
)
WITH (security_barrier = true)
AS
WITH completed_forecast AS (
    SELECT
        run.forecast_month AS period,
        COUNT(*)::bigint AS candidate_count,
        MAX(run.generated_at) AS produced_at
    FROM ai_forecast_runs AS run
    WHERE run.status = 'completed'
    GROUP BY run.forecast_month
),
promoted_forecast AS (
    SELECT
        head.forecast_month AS period,
        COUNT(*)::bigint AS head_count,
        COUNT(*) FILTER (
            WHERE run.status = 'completed'
              AND run.forecast_month = head.forecast_month
              AND run.metric = head.metric
              AND run.horizon = head.horizon
              AND head.run_sha256 = public.planning_forecast_run_sha256(head.run_id)
              AND head.row_count = (
                  SELECT COUNT(*)::bigint
                  FROM ai_forecast_store_month AS item
                  WHERE item.run_id = head.run_id
              )
        )::bigint AS eligible_head_count,
        COALESCE(SUM(head.row_count) FILTER (
            WHERE run.status = 'completed'
              AND run.forecast_month = head.forecast_month
              AND run.metric = head.metric
              AND run.horizon = head.horizon
              AND head.run_sha256 = public.planning_forecast_run_sha256(head.run_id)
              AND head.row_count = (
                  SELECT COUNT(*)::bigint
                  FROM ai_forecast_store_month AS item
                  WHERE item.run_id = head.run_id
              )
        ), 0)::bigint AS eligible_row_count,
        string_agg(
            head.metric || ':' || head.horizon || ':run:' || head.run_id::text,
            ',' ORDER BY head.metric, head.horizon
        ) FILTER (
            WHERE run.status = 'completed'
              AND head.run_sha256 = public.planning_forecast_run_sha256(head.run_id)
        ) AS source_generation,
        string_agg(
            head.metric || ':' || head.horizon || ':revision:' || head.revision::text,
            ',' ORDER BY head.metric, head.horizon
        ) AS authority_head,
        MAX(head.updated_at) AS produced_at
    FROM planning_forecast_heads AS head
    JOIN ai_forecast_runs AS run ON run.id = head.run_id
    GROUP BY head.forecast_month
),
finalized_target AS (
    SELECT
        scenario.id,
        scenario.target_month AS period,
        scenario.revision,
        scenario.rule_set_hash,
        COALESCE(scenario.finalized_at, scenario.updated_at) AS produced_at,
        COUNT(target.site_code)::bigint AS row_count,
        BOOL_AND(target.final_target IS NOT NULL) AS complete_values,
        (
            scenario.rule_set_hash ~ '^[0-9a-f]{64}$'
            AND scenario.rule_set_id = registry.id
            AND scenario.rule_set_hash = registry.rules_sha256
            AND scenario.target_month >= registry.effective_from_month
            AND (
                registry.effective_to_month IS NULL
                OR scenario.target_month < registry.effective_to_month
            )
            AND scenario.rule_set_snapshot = jsonb_build_object(
                'schema_version', 1,
                'rule_set_id', registry.id,
                'version', registry.version,
                'effective_from_month', registry.effective_from_month,
                'effective_to_month', registry.effective_to_month,
                'rules_hash', registry.rules_sha256,
                'rules', registry.rules
            )
        ) AS exact_rule_snapshot,
        ROW_NUMBER() OVER (
            PARTITION BY scenario.target_month
            ORDER BY
                scenario.revision DESC,
                scenario.finalized_at DESC NULLS LAST,
                scenario.id DESC
        ) AS selection_rank
    FROM target_scenarios AS scenario
    JOIN target_scenario_rows AS target ON target.scenario_id = scenario.id
    LEFT JOIN target_calculator_effective_rule_sets AS registry
      ON registry.id = scenario.rule_set_id
    WHERE scenario.status = 'finalized'
    GROUP BY
        scenario.id,
        scenario.target_month,
        scenario.revision,
        scenario.rule_set_hash,
        scenario.rule_set_snapshot,
        scenario.rule_set_id,
        scenario.finalized_at,
        scenario.updated_at,
        registry.id,
        registry.version,
        registry.effective_from_month,
        registry.effective_to_month,
        registry.rules,
        registry.rules_sha256
),
selected_target AS (
    SELECT * FROM finalized_target WHERE selection_rank = 1
),
planning_period AS (
    SELECT period FROM completed_forecast
    UNION
    SELECT period FROM promoted_forecast
    UNION
    SELECT period FROM selected_target
),
planning AS (
    SELECT
        period.period,
        COALESCE(candidate.candidate_count, 0) AS candidate_count,
        candidate.produced_at AS candidate_produced_at,
        COALESCE(head.head_count, 0) AS head_count,
        COALESCE(head.eligible_head_count, 0) AS eligible_head_count,
        COALESCE(head.eligible_row_count, 0) AS eligible_forecast_rows,
        head.source_generation AS forecast_source_generation,
        head.authority_head AS forecast_authority_head,
        head.produced_at AS forecast_produced_at,
        target.id AS target_id,
        target.revision AS target_revision,
        target.rule_set_hash,
        target.row_count AS target_row_count,
        target.produced_at AS target_produced_at,
        COALESCE(target.complete_values AND target.exact_rule_snapshot, false) AS target_eligible
    FROM planning_period AS period
    LEFT JOIN completed_forecast AS candidate USING (period)
    LEFT JOIN promoted_forecast AS head USING (period)
    LEFT JOIN selected_target AS target USING (period)
)
SELECT
    snapshot.domain,
    snapshot.period,
    snapshot.source,
    snapshot.source_generation,
    snapshot.authority,
    snapshot.authority_head,
    snapshot.contract_version,
    snapshot.rule_version,
    snapshot.status,
    snapshot.as_of,
    snapshot.cutoff,
    snapshot.is_final,
    snapshot.coverage_numerator,
    snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings
FROM reporting_source_snapshot_v2 AS snapshot
WHERE snapshot.domain <> 'planning'

UNION ALL

SELECT
    'planning'::text,
    planning.period,
    'planning_forecast_heads'::text,
    concat_ws(
        '|',
        CASE
            WHEN planning.eligible_head_count > 0
            THEN 'forecast-heads:' || planning.forecast_source_generation
        END,
        CASE
            WHEN planning.target_eligible
            THEN 'target-scenario:' || planning.target_id::text
        END
    ),
    concat_ws(
        '|',
        CASE WHEN planning.eligible_head_count > 0 THEN 'planning_forecast_heads' END,
        CASE WHEN planning.target_eligible THEN 'finalized_target_scenario' END
    ),
    concat_ws(
        '|',
        planning.forecast_authority_head,
        CASE
            WHEN planning.target_eligible
            THEN 'target:' || planning.target_id::text || ':revision:' || planning.target_revision::text
        END
    ),
    2::integer,
    'planning-promoted-target-snapshot-v2'::text,
    CASE
        WHEN planning.eligible_head_count > 0
         AND planning.eligible_head_count = planning.head_count
         AND planning.target_eligible THEN 'official'::text
        ELSE 'partial'::text
    END,
    NULL::date,
    NULL::date,
    (
        planning.eligible_head_count > 0
        AND planning.eligible_head_count = planning.head_count
        AND planning.target_eligible
    ),
    planning.eligible_forecast_rows
        + CASE WHEN planning.target_eligible THEN planning.target_row_count ELSE 0 END,
    planning.eligible_forecast_rows
        + CASE WHEN planning.target_eligible THEN planning.target_row_count ELSE 0 END,
    GREATEST(
        COALESCE(planning.forecast_produced_at, '-infinity'::timestamptz),
        COALESCE(planning.target_produced_at, '-infinity'::timestamptz),
        CASE
            WHEN planning.eligible_head_count = 0
            THEN COALESCE(planning.candidate_produced_at, '-infinity'::timestamptz)
            ELSE '-infinity'::timestamptz
        END
    ),
    ARRAY[]::text[]
    || CASE
        WHEN planning.candidate_count = 0 THEN ARRAY['completed_forecast_unavailable']::text[]
        WHEN planning.eligible_head_count = 0 THEN ARRAY['forecast_run_not_promoted']::text[]
        ELSE ARRAY[]::text[]
    END
    || CASE
        WHEN planning.head_count > planning.eligible_head_count
        THEN ARRAY['promoted_forecast_integrity_mismatch']::text[]
        ELSE ARRAY[]::text[]
    END
    || CASE
        WHEN planning.target_id IS NULL THEN ARRAY['finalized_target_unavailable']::text[]
        WHEN planning.target_eligible THEN ARRAY[]::text[]
        ELSE ARRAY['finalized_target_lacks_a_versioned_rule_snapshot_or_values']::text[]
    END
FROM planning;

CREATE OR REPLACE VIEW reporting_planning_scenario_v2 (
    authority_kind,
    period,
    site_code,
    locatie,
    firma,
    regional,
    asm,
    forecast_run_id,
    target_scenario_id,
    target_scenario_revision,
    metric,
    horizon,
    model_name,
    model_mode,
    variant,
    source_month,
    rule_set_hash,
    forecast_value,
    target_value,
    source,
    source_generation,
    authority,
    authority_head,
    contract_version,
    rule_version,
    status,
    as_of,
    cutoff,
    is_final,
    coverage_numerator,
    coverage_denominator,
    produced_at,
    warnings
)
WITH (security_barrier = true)
AS
WITH eligible_forecast_head AS (
    SELECT head.*, run.source_month, run.model_name, run.model_mode, run.variant
    FROM planning_forecast_heads AS head
    JOIN ai_forecast_runs AS run ON run.id = head.run_id
    WHERE run.status = 'completed'
      AND run.forecast_month = head.forecast_month
      AND run.metric = head.metric
      AND run.horizon = head.horizon
      AND head.run_sha256 = public.planning_forecast_run_sha256(head.run_id)
      AND head.row_count = (
          SELECT COUNT(*)::bigint
          FROM ai_forecast_store_month AS item
          WHERE item.run_id = head.run_id
      )
),
eligible_target AS (
    SELECT scenario.id
    FROM target_scenarios AS scenario
    JOIN target_calculator_effective_rule_sets AS registry
      ON registry.id = scenario.rule_set_id
    WHERE scenario.status = 'finalized'
      AND scenario.rule_set_hash ~ '^[0-9a-f]{64}$'
      AND scenario.rule_set_hash = registry.rules_sha256
      AND scenario.target_month >= registry.effective_from_month
      AND (
          registry.effective_to_month IS NULL
          OR scenario.target_month < registry.effective_to_month
      )
      AND scenario.rule_set_snapshot = jsonb_build_object(
          'schema_version', 1,
          'rule_set_id', registry.id,
          'version', registry.version,
          'effective_from_month', registry.effective_from_month,
          'effective_to_month', registry.effective_to_month,
          'rules_hash', registry.rules_sha256,
          'rules', registry.rules
      )
      AND EXISTS (
          SELECT 1 FROM target_scenario_rows AS item WHERE item.scenario_id = scenario.id
      )
      AND NOT EXISTS (
          SELECT 1
          FROM target_scenario_rows AS item
          WHERE item.scenario_id = scenario.id
            AND item.final_target IS NULL
      )
)
SELECT
    'forecast'::text,
    head.forecast_month,
    item.site_code,
    store.locatie,
    store.firma,
    store.regional,
    store.asm,
    head.run_id,
    NULL::integer,
    NULL::integer,
    head.metric,
    head.horizon,
    head.model_name,
    head.model_mode,
    head.variant,
    head.source_month,
    NULL::text,
    item.forecast_sales,
    NULL::numeric,
    snapshot.source,
    snapshot.source_generation,
    snapshot.authority,
    snapshot.authority_head,
    snapshot.contract_version,
    snapshot.rule_version,
    snapshot.status,
    snapshot.as_of,
    snapshot.cutoff,
    snapshot.is_final,
    snapshot.coverage_numerator,
    snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings
FROM eligible_forecast_head AS head
JOIN ai_forecast_store_month AS item ON item.run_id = head.run_id
JOIN stores AS store ON store.site_code = item.site_code
JOIN reporting_source_snapshot_v3 AS snapshot
  ON snapshot.domain = 'planning'
 AND snapshot.period = head.forecast_month

UNION ALL

SELECT
    'target'::text,
    scenario.target_month,
    target.site_code,
    target.locatie,
    target.firma,
    target.regional,
    target.asm,
    NULL::bigint,
    scenario.id,
    scenario.revision,
    NULL::text,
    NULL::text,
    NULL::text,
    NULL::text,
    NULL::text,
    scenario.cohort_month,
    scenario.rule_set_hash,
    NULL::numeric,
    target.final_target,
    snapshot.source,
    snapshot.source_generation,
    snapshot.authority,
    snapshot.authority_head,
    snapshot.contract_version,
    snapshot.rule_version,
    snapshot.status,
    snapshot.as_of,
    snapshot.cutoff,
    snapshot.is_final,
    snapshot.coverage_numerator,
    snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings
FROM target_scenarios AS scenario
JOIN eligible_target AS eligible ON eligible.id = scenario.id
JOIN target_scenario_rows AS target ON target.scenario_id = scenario.id
JOIN reporting_source_snapshot_v3 AS snapshot
  ON snapshot.domain = 'planning'
 AND snapshot.period = scenario.target_month;

REVOKE ALL ON TABLE planning_forecast_heads, planning_forecast_promotions
FROM PUBLIC, unihub_web_read, unihub_business_write, unihub_sales_import,
    unihub_finance_import, unihub_operations, unihub_migrate;
REVOKE ALL ON SEQUENCE planning_forecast_promotions_id_seq
FROM PUBLIC, unihub_web_read, unihub_business_write, unihub_sales_import,
    unihub_finance_import, unihub_operations, unihub_migrate;
REVOKE ALL ON FUNCTION public.advance_planning_forecast_head(
    TEXT, TEXT, TEXT, BIGINT, BIGINT, TEXT, TEXT, TEXT, TEXT
) FROM PUBLIC, unihub_web_read, unihub_business_write, unihub_sales_import,
    unihub_finance_import, unihub_operations, unihub_migrate;

GRANT SELECT ON TABLE planning_forecast_heads, planning_forecast_promotions
TO unihub_operations;
GRANT EXECUTE ON FUNCTION public.advance_planning_forecast_head(
    TEXT, TEXT, TEXT, BIGINT, BIGINT, TEXT, TEXT, TEXT, TEXT
) TO unihub_operations;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        REVOKE ALL ON TABLE planning_forecast_heads, planning_forecast_promotions
        FROM unihub_runtime;
        REVOKE ALL ON SEQUENCE planning_forecast_promotions_id_seq
        FROM unihub_runtime;
        REVOKE ALL ON FUNCTION public.advance_planning_forecast_head(
            TEXT, TEXT, TEXT, BIGINT, BIGINT, TEXT, TEXT, TEXT, TEXT
        ) FROM unihub_runtime;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_insight_reader') THEN
        GRANT SELECT ON TABLE reporting_source_snapshot_v3,
                              reporting_planning_scenario_v2
        TO unihub_insight_reader;
    END IF;
END
$$;

COMMENT ON TABLE planning_forecast_heads IS
    'Approved per-month/metric/horizon forecast head; completed runs alone remain candidates.';
COMMENT ON TABLE planning_forecast_promotions IS
    'Append-only Planning promotion and rollback evidence bound to a revision CAS head.';
COMMENT ON VIEW reporting_planning_scenario_v2 IS
    'Planning read model: frozen promoted forecasts plus exact finalized Target rule snapshots only.';
COMMENT ON FUNCTION public.advance_planning_forecast_head(
    TEXT, TEXT, TEXT, BIGINT, BIGINT, TEXT, TEXT, TEXT, TEXT
) IS 'Approval-artifact-bound Planning forecast promote/rollback with revision CAS.';
