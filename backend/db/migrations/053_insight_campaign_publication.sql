-- Immutable campaign publication boundary for UniHub Insight.
--
-- Focus, Promo and Incentive are evaluated by the canonical Retail service and
-- published as one candidate generation.  Insight reads only the selected CAS
-- head.  The v1/v3 contracts intentionally remain untouched as N-1 rollback
-- anchors; this migration introduces additive v2/v4 contracts only.

CREATE OR REPLACE FUNCTION public.campaign_reporting_product_codes_are_canonical(
    p_codes TEXT[]
)
RETURNS BOOLEAN
LANGUAGE SQL
IMMUTABLE
STRICT
SET search_path = pg_catalog, public
AS $$
    SELECT p_codes = COALESCE(
        ARRAY(
            SELECT DISTINCT code COLLATE "C"
            FROM unnest(p_codes) AS code
            ORDER BY code COLLATE "C"
        ),
        ARRAY[]::TEXT[]
    )
$$;

CREATE TABLE campaign_reporting_generations (
    id BIGSERIAL PRIMARY KEY,
    period TEXT NOT NULL
        CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    sales_source_generation TEXT NOT NULL CHECK (btrim(sales_source_generation) <> ''),
    sales_authority TEXT NOT NULL CHECK (btrim(sales_authority) <> ''),
    sales_authority_head TEXT NOT NULL CHECK (btrim(sales_authority_head) <> ''),
    sales_status TEXT NOT NULL CHECK (sales_status IN ('official', 'partial', 'unavailable')),
    sales_is_final BOOLEAN NOT NULL,
    promo_generation_id TEXT
        CHECK (promo_generation_id IS NULL OR promo_generation_id ~ '^[0-9a-f]{32}$'),
    promo_config_sha256 TEXT
        CHECK (promo_config_sha256 IS NULL OR promo_config_sha256 ~ '^[0-9a-f]{64}$'),
    promo_actuals_sha256 TEXT
        CHECK (promo_actuals_sha256 IS NULL OR promo_actuals_sha256 ~ '^[0-9a-f]{64}$'),
    promo_material_sha256 TEXT
        CHECK (promo_material_sha256 IS NULL OR promo_material_sha256 ~ '^[0-9a-f]{64}$'),
    incentive_campaign_id BIGINT REFERENCES incentive_campaigns(id) ON DELETE RESTRICT,
    incentive_input_sha256 TEXT
        CHECK (incentive_input_sha256 IS NULL OR incentive_input_sha256 ~ '^[0-9a-f]{64}$'),
    cutoff DATE,
    coverage_numerator BIGINT NOT NULL CHECK (coverage_numerator >= 0),
    coverage_denominator BIGINT NOT NULL CHECK (coverage_denominator >= 0),
    input_sha256 TEXT NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    output_sha256 TEXT NOT NULL CHECK (output_sha256 ~ '^[0-9a-f]{64}$'),
    row_count BIGINT NOT NULL CHECK (row_count > 0),
    status TEXT NOT NULL CHECK (status IN ('official', 'partial', 'unavailable')),
    warnings TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    created_by_sub TEXT NOT NULL CHECK (btrim(created_by_sub) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (period, input_sha256)
);

CREATE TABLE campaign_reporting_rows (
    generation_id BIGINT NOT NULL REFERENCES campaign_reporting_generations(id) ON DELETE RESTRICT,
    mechanism TEXT NOT NULL CHECK (mechanism IN ('focus', 'promo', 'incentive')),
    campaign_key TEXT NOT NULL CHECK (btrim(campaign_key) <> ''),
    site_code TEXT NOT NULL CHECK (btrim(site_code) <> ''),
    agent TEXT NOT NULL CHECK (btrim(agent) <> ''),
    locatie TEXT,
    firma TEXT,
    regional TEXT,
    asm TEXT,
    actual_sales NUMERIC(16, 2),
    actual_quantity BIGINT,
    active_product_count BIGINT NOT NULL,
    active_product_codes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    promo_qualifying_bons BIGINT,
    promo_discounted_units BIGINT,
    promo_discount_value NUMERIC(16, 2),
    incentive_sold_quantity BIGINT,
    incentive_eligible_quantity BIGINT,
    incentive_qualified_quantity BIGINT,
    incentive_value NUMERIC(16, 2),
    incentive_potential NUMERIC(16, 2),
    incentive_store_qualified BOOLEAN,
    status TEXT NOT NULL CHECK (status IN ('official', 'partial', 'unavailable')),
    warnings TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    PRIMARY KEY (generation_id, mechanism, campaign_key, site_code, agent),
    CHECK (active_product_count >= 0),
    CHECK (active_product_count = cardinality(active_product_codes)),
    CHECK (public.campaign_reporting_product_codes_are_canonical(active_product_codes)),
    CHECK (promo_qualifying_bons IS NULL OR promo_qualifying_bons >= 0),
    CHECK (promo_discounted_units IS NULL OR promo_discounted_units >= 0),
    CHECK (incentive_eligible_quantity IS NULL OR incentive_eligible_quantity >= 0),
    CHECK (incentive_qualified_quantity IS NULL OR incentive_qualified_quantity >= 0),
    CHECK (
        (mechanism = 'focus'
            AND promo_qualifying_bons IS NULL
            AND promo_discounted_units IS NULL
            AND promo_discount_value IS NULL
            AND incentive_sold_quantity IS NULL
            AND incentive_eligible_quantity IS NULL
            AND incentive_qualified_quantity IS NULL
            AND incentive_value IS NULL
            AND incentive_potential IS NULL
            AND incentive_store_qualified IS NULL)
        OR (mechanism = 'promo'
            AND incentive_sold_quantity IS NULL
            AND incentive_eligible_quantity IS NULL
            AND incentive_qualified_quantity IS NULL
            AND incentive_value IS NULL
            AND incentive_potential IS NULL
            AND incentive_store_qualified IS NULL)
        OR (mechanism = 'incentive'
            AND promo_qualifying_bons IS NULL
            AND promo_discounted_units IS NULL
            AND promo_discount_value IS NULL)
    )
);

CREATE INDEX idx_campaign_reporting_rows_period_mechanism
    ON campaign_reporting_rows (generation_id, mechanism, site_code);

CREATE TABLE campaign_reporting_heads (
    period TEXT PRIMARY KEY
        CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    generation_id BIGINT NOT NULL REFERENCES campaign_reporting_generations(id) ON DELETE RESTRICT,
    revision BIGINT NOT NULL CHECK (revision >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE campaign_reporting_promotions (
    id BIGSERIAL PRIMARY KEY,
    period TEXT NOT NULL
        CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    from_generation_id BIGINT REFERENCES campaign_reporting_generations(id) ON DELETE RESTRICT,
    to_generation_id BIGINT NOT NULL REFERENCES campaign_reporting_generations(id) ON DELETE RESTRICT,
    head_revision BIGINT NOT NULL CHECK (head_revision >= 1),
    action TEXT NOT NULL CHECK (action IN ('promote', 'rollback')),
    input_sha256 TEXT NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    output_sha256 TEXT NOT NULL CHECK (output_sha256 ~ '^[0-9a-f]{64}$'),
    row_count BIGINT NOT NULL CHECK (row_count > 0),
    requested_by_sub TEXT NOT NULL CHECK (btrim(requested_by_sub) <> ''),
    reason TEXT NOT NULL CHECK (btrim(reason) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (period, head_revision)
);

CREATE INDEX idx_campaign_reporting_promotions_target
    ON campaign_reporting_promotions (period, to_generation_id, head_revision);

CREATE OR REPLACE FUNCTION public.guard_campaign_reporting_generation_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'campaign reporting generations are append-only';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_campaign_reporting_generations_immutable
BEFORE INSERT OR UPDATE OR DELETE ON campaign_reporting_generations
FOR EACH ROW EXECUTE FUNCTION public.guard_campaign_reporting_generation_mutation();

CREATE OR REPLACE FUNCTION public.guard_campaign_reporting_row_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'campaign reporting rows are append-only';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_campaign_reporting_rows_immutable
BEFORE INSERT OR UPDATE OR DELETE ON campaign_reporting_rows
FOR EACH ROW EXECUTE FUNCTION public.guard_campaign_reporting_row_mutation();

CREATE OR REPLACE FUNCTION public.guard_campaign_reporting_head_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'campaign reporting head cannot be deleted';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.revision <> 1 THEN
            RAISE EXCEPTION 'campaign reporting head must start at revision 1';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.period IS DISTINCT FROM NEW.period
       OR NEW.revision <> OLD.revision + 1
       OR OLD.generation_id IS NOT DISTINCT FROM NEW.generation_id THEN
        RAISE EXCEPTION 'campaign reporting head accepts only a new generation and revision CAS advance';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_campaign_reporting_heads_cas
BEFORE INSERT OR UPDATE OR DELETE ON campaign_reporting_heads
FOR EACH ROW EXECUTE FUNCTION public.guard_campaign_reporting_head_mutation();

CREATE OR REPLACE FUNCTION public.guard_campaign_reporting_promotion_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    head campaign_reporting_heads%ROWTYPE;
    target campaign_reporting_generations%ROWTYPE;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'campaign reporting promotion ledger is append-only';
    END IF;

    SELECT * INTO head
    FROM public.campaign_reporting_heads
    WHERE period = NEW.period;
    SELECT * INTO target
    FROM public.campaign_reporting_generations
    WHERE id = NEW.to_generation_id;
    IF NOT FOUND
       OR target.period IS DISTINCT FROM NEW.period
       OR head.generation_id IS DISTINCT FROM NEW.to_generation_id
       OR head.revision IS DISTINCT FROM NEW.head_revision
       OR target.input_sha256 IS DISTINCT FROM NEW.input_sha256
       OR target.output_sha256 IS DISTINCT FROM NEW.output_sha256
       OR target.row_count IS DISTINCT FROM NEW.row_count THEN
        RAISE EXCEPTION 'campaign reporting promotion must attest to the current CAS head';
    END IF;
    IF NEW.action = 'rollback' AND NOT EXISTS (
        SELECT 1
        FROM public.campaign_reporting_promotions AS prior
        WHERE prior.period = NEW.period
          AND prior.to_generation_id = NEW.to_generation_id
          AND prior.input_sha256 = NEW.input_sha256
          AND prior.output_sha256 = NEW.output_sha256
    ) THEN
        RAISE EXCEPTION 'campaign reporting rollback target lacks retained promotion lineage';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_campaign_reporting_promotions_immutable
BEFORE INSERT OR UPDATE OR DELETE ON campaign_reporting_promotions
FOR EACH ROW EXECUTE FUNCTION public.guard_campaign_reporting_promotion_mutation();

CREATE OR REPLACE FUNCTION public.publish_campaign_reporting_generation(
    p_period TEXT,
    p_sales_source_generation TEXT,
    p_sales_authority TEXT,
    p_sales_authority_head TEXT,
    p_sales_status TEXT,
    p_sales_is_final BOOLEAN,
    p_promo_generation_id TEXT,
    p_promo_config_sha256 TEXT,
    p_promo_actuals_sha256 TEXT,
    p_promo_material_sha256 TEXT,
    p_incentive_campaign_id BIGINT,
    p_incentive_input_sha256 TEXT,
    p_cutoff DATE,
    p_coverage_numerator BIGINT,
    p_coverage_denominator BIGINT,
    p_status TEXT,
    p_warnings TEXT[],
    p_input_sha256 TEXT,
    p_rows JSONB,
    p_expected_revision BIGINT,
    p_requested_by_sub TEXT,
    p_reason TEXT,
    p_action TEXT DEFAULT 'promote'
)
RETURNS public.campaign_reporting_heads
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    existing_generation campaign_reporting_generations%ROWTYPE;
    current_head campaign_reporting_heads%ROWTYPE;
    next_head campaign_reporting_heads%ROWTYPE;
    v_generation_id BIGINT;
    v_row_count BIGINT;
    v_output_sha256 TEXT;
    v_next_revision BIGINT;
BEGIN
    IF p_period !~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
       OR NULLIF(btrim(p_sales_source_generation), '') IS NULL
       OR NULLIF(btrim(p_sales_authority), '') IS NULL
       OR NULLIF(btrim(p_sales_authority_head), '') IS NULL
       OR p_sales_status NOT IN ('official', 'partial', 'unavailable')
       OR p_status NOT IN ('official', 'partial', 'unavailable')
       OR p_coverage_numerator < 0
       OR p_coverage_denominator < 0
       OR p_input_sha256 !~ '^[0-9a-f]{64}$'
       OR NULLIF(btrim(p_requested_by_sub), '') IS NULL
       OR NULLIF(btrim(p_reason), '') IS NULL
       OR p_expected_revision < 0
       OR p_action NOT IN ('promote', 'rollback')
       OR jsonb_typeof(p_rows) <> 'array'
       OR jsonb_array_length(p_rows) = 0 THEN
        RAISE EXCEPTION 'campaign reporting publication request is invalid';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended('campaign-reporting:' || p_period, 0)
    );
    v_output_sha256 := encode(digest(convert_to(p_rows::text, 'UTF8'), 'sha256'), 'hex');
    v_row_count := jsonb_array_length(p_rows)::BIGINT;

    SELECT * INTO existing_generation
    FROM public.campaign_reporting_generations
    WHERE period = p_period
      AND input_sha256 = p_input_sha256;
    IF FOUND AND (
        existing_generation.output_sha256 IS DISTINCT FROM v_output_sha256
        OR existing_generation.row_count IS DISTINCT FROM v_row_count
    ) THEN
        RAISE EXCEPTION 'campaign reporting input hash conflicts with retained generation';
    END IF;

    IF NOT FOUND THEN
        INSERT INTO public.campaign_reporting_generations (
            period,
            sales_source_generation,
            sales_authority,
            sales_authority_head,
            sales_status,
            sales_is_final,
            promo_generation_id,
            promo_config_sha256,
            promo_actuals_sha256,
            promo_material_sha256,
            incentive_campaign_id,
            incentive_input_sha256,
            cutoff,
            coverage_numerator,
            coverage_denominator,
            input_sha256,
            output_sha256,
            row_count,
            status,
            warnings,
            created_by_sub
        ) VALUES (
            p_period,
            btrim(p_sales_source_generation),
            btrim(p_sales_authority),
            btrim(p_sales_authority_head),
            p_sales_status,
            p_sales_is_final,
            p_promo_generation_id,
            p_promo_config_sha256,
            p_promo_actuals_sha256,
            p_promo_material_sha256,
            p_incentive_campaign_id,
            p_incentive_input_sha256,
            p_cutoff,
            p_coverage_numerator,
            p_coverage_denominator,
            p_input_sha256,
            v_output_sha256,
            v_row_count,
            p_status,
            COALESCE(p_warnings, ARRAY[]::TEXT[]),
            btrim(p_requested_by_sub)
        )
        RETURNING id INTO v_generation_id;

        INSERT INTO public.campaign_reporting_rows (
            generation_id,
            mechanism,
            campaign_key,
            site_code,
            agent,
            locatie,
            firma,
            regional,
            asm,
            actual_sales,
            actual_quantity,
            active_product_count,
            active_product_codes,
            promo_qualifying_bons,
            promo_discounted_units,
            promo_discount_value,
            incentive_sold_quantity,
            incentive_eligible_quantity,
            incentive_qualified_quantity,
            incentive_value,
            incentive_potential,
            incentive_store_qualified,
            status,
            warnings
        )
        SELECT
            v_generation_id,
            candidate.mechanism,
            candidate.campaign_key,
            candidate.site_code,
            candidate.agent,
            candidate.locatie,
            candidate.firma,
            candidate.regional,
            candidate.asm,
            candidate.actual_sales,
            candidate.actual_quantity,
            candidate.active_product_count,
            candidate.active_product_codes,
            candidate.promo_qualifying_bons,
            candidate.promo_discounted_units,
            candidate.promo_discount_value,
            candidate.incentive_sold_quantity,
            candidate.incentive_eligible_quantity,
            candidate.incentive_qualified_quantity,
            candidate.incentive_value,
            candidate.incentive_potential,
            candidate.incentive_store_qualified,
            candidate.status,
            COALESCE(candidate.warnings, ARRAY[]::TEXT[])
        FROM jsonb_to_recordset(p_rows) AS candidate(
            mechanism TEXT,
            campaign_key TEXT,
            site_code TEXT,
            agent TEXT,
            locatie TEXT,
            firma TEXT,
            regional TEXT,
            asm TEXT,
            actual_sales NUMERIC(16, 2),
            actual_quantity BIGINT,
            active_product_count BIGINT,
            active_product_codes TEXT[],
            promo_qualifying_bons BIGINT,
            promo_discounted_units BIGINT,
            promo_discount_value NUMERIC(16, 2),
            incentive_sold_quantity BIGINT,
            incentive_eligible_quantity BIGINT,
            incentive_qualified_quantity BIGINT,
            incentive_value NUMERIC(16, 2),
            incentive_potential NUMERIC(16, 2),
            incentive_store_qualified BOOLEAN,
            status TEXT,
            warnings TEXT[]
        );
        IF (
            SELECT COUNT(*)
            FROM public.campaign_reporting_rows AS published_row
            WHERE published_row.generation_id = v_generation_id
        ) <> v_row_count THEN
            RAISE EXCEPTION 'campaign reporting rows are not structurally unique';
        END IF;
    ELSE
        v_generation_id := existing_generation.id;
    END IF;

    SELECT * INTO current_head
    FROM public.campaign_reporting_heads
    WHERE period = p_period
    FOR UPDATE;
    IF FOUND AND current_head.generation_id = v_generation_id THEN
        RETURN current_head;
    END IF;
    IF (NOT FOUND AND p_expected_revision <> 0)
       OR (FOUND AND current_head.revision <> p_expected_revision) THEN
        RAISE EXCEPTION 'campaign reporting head revision conflict';
    END IF;
    IF p_action = 'rollback' AND NOT EXISTS (
        SELECT 1 FROM public.campaign_reporting_promotions
        WHERE period = p_period AND to_generation_id = v_generation_id
    ) THEN
        RAISE EXCEPTION 'campaign reporting rollback target lacks retained promotion lineage';
    END IF;

    v_next_revision := COALESCE(current_head.revision, 0) + 1;
    IF FOUND THEN
        UPDATE public.campaign_reporting_heads
        SET generation_id = v_generation_id,
            revision = v_next_revision,
            updated_at = now()
        WHERE period = p_period
        RETURNING * INTO next_head;
    ELSE
        INSERT INTO public.campaign_reporting_heads (period, generation_id, revision)
        VALUES (p_period, v_generation_id, v_next_revision)
        RETURNING * INTO next_head;
    END IF;

    INSERT INTO public.campaign_reporting_promotions (
        period,
        from_generation_id,
        to_generation_id,
        head_revision,
        action,
        input_sha256,
        output_sha256,
        row_count,
        requested_by_sub,
        reason
    )
    SELECT
        p_period,
        current_head.generation_id,
        generation.id,
        v_next_revision,
        p_action,
        generation.input_sha256,
        generation.output_sha256,
        generation.row_count,
        btrim(p_requested_by_sub),
        btrim(p_reason)
    FROM public.campaign_reporting_generations AS generation
    WHERE generation.id = v_generation_id;
    RETURN next_head;
END
$$;

CREATE OR REPLACE VIEW reporting_source_snapshot_v4 (
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
WITH sales_periods AS (
    SELECT *
    FROM reporting_source_snapshot_v3
    WHERE domain = 'sales'
),
campaign_heads AS (
    SELECT
        head.period,
        head.revision,
        head.updated_at AS head_updated_at,
        generation.id AS generation_id,
        generation.sales_source_generation,
        generation.sales_authority,
        generation.sales_authority_head,
        generation.sales_status,
        generation.sales_is_final,
        generation.cutoff,
        generation.coverage_numerator,
        generation.coverage_denominator,
        generation.input_sha256,
        generation.status,
        generation.warnings,
        generation.created_at
    FROM campaign_reporting_heads AS head
    JOIN campaign_reporting_generations AS generation
      ON generation.id = head.generation_id
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
FROM reporting_source_snapshot_v3 AS snapshot
WHERE snapshot.domain <> 'campaigns'

UNION ALL

SELECT
    'campaigns'::TEXT,
    sales.period,
    'campaign_reporting_heads'::TEXT,
    'campaign-generation:' || campaign.generation_id::TEXT || ':input:' || campaign.input_sha256,
    'campaign_reporting_head'::TEXT,
    'campaign:' || campaign.revision::TEXT,
    2::INTEGER,
    'campaign-publication-v2'::TEXT,
    campaign.status,
    campaign.cutoff,
    campaign.cutoff,
    campaign.sales_is_final,
    campaign.coverage_numerator,
    campaign.coverage_denominator,
    GREATEST(campaign.created_at, campaign.head_updated_at),
    campaign.warnings
FROM sales_periods AS sales
JOIN campaign_heads AS campaign
  ON campaign.period = sales.period
 AND campaign.sales_source_generation = sales.source_generation
 AND campaign.sales_authority = sales.authority
 AND campaign.sales_authority_head = sales.authority_head

UNION ALL

SELECT
    'campaigns'::TEXT,
    sales.period,
    'campaign_reporting_heads'::TEXT,
    'campaign-unpublished:' || sales.source_generation,
    'campaign_reporting_head'::TEXT,
    'none'::TEXT,
    2::INTEGER,
    'campaign-publication-v2'::TEXT,
    'unavailable'::TEXT,
    sales.as_of,
    sales.cutoff,
    false,
    0::BIGINT,
    sales.coverage_denominator,
    sales.produced_at,
    sales.warnings || ARRAY['campaign_reporting_not_published']::TEXT[]
FROM sales_periods AS sales
LEFT JOIN campaign_heads AS campaign
  ON campaign.period = sales.period
 AND campaign.sales_source_generation = sales.source_generation
 AND campaign.sales_authority = sales.authority
 AND campaign.sales_authority_head = sales.authority_head
WHERE campaign.generation_id IS NULL;

CREATE OR REPLACE VIEW reporting_campaign_month_v2 (
    period,
    mechanism,
    campaign_key,
    site_code,
    agent,
    locatie,
    firma,
    regional,
    asm,
    actual_sales,
    actual_quantity,
    active_product_count,
    active_product_codes,
    promo_qualifying_bons,
    promo_discounted_units,
    promo_discount_value,
    incentive_sold_quantity,
    incentive_eligible_quantity,
    incentive_qualified_quantity,
    incentive_value,
    incentive_potential,
    incentive_store_qualified,
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
SELECT
    generation.period,
    row.mechanism,
    row.campaign_key,
    row.site_code,
    row.agent,
    row.locatie,
    row.firma,
    row.regional,
    row.asm,
    row.actual_sales,
    row.actual_quantity,
    row.active_product_count,
    row.active_product_codes,
    row.promo_qualifying_bons,
    row.promo_discounted_units,
    row.promo_discount_value,
    row.incentive_sold_quantity,
    row.incentive_eligible_quantity,
    row.incentive_qualified_quantity,
    row.incentive_value,
    row.incentive_potential,
    row.incentive_store_qualified,
    snapshot.source,
    snapshot.source_generation,
    snapshot.authority,
    snapshot.authority_head,
    snapshot.contract_version,
    snapshot.rule_version,
    row.status,
    snapshot.as_of,
    snapshot.cutoff,
    snapshot.is_final,
    snapshot.coverage_numerator,
    snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings || row.warnings
FROM campaign_reporting_heads AS head
JOIN campaign_reporting_generations AS generation
  ON generation.id = head.generation_id
JOIN campaign_reporting_rows AS row
  ON row.generation_id = generation.id
JOIN reporting_source_snapshot_v4 AS snapshot
  ON snapshot.domain = 'campaigns'
 AND snapshot.period = generation.period
 AND snapshot.authority_head = 'campaign:' || head.revision::TEXT;

COMMENT ON VIEW reporting_source_snapshot_v4 IS
    'Additive Campaigns publication snapshot. Missing head is explicit unavailable; v3 stays rollback-compatible.';
COMMENT ON VIEW reporting_campaign_month_v2 IS
    'Head-selected immutable Focus, Promo and Incentive rows. Metric status is per mechanism/site, never zero-filled.';

REVOKE ALL ON FUNCTION public.publish_campaign_reporting_generation(
    TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, TEXT, BIGINT,
    TEXT, DATE, BIGINT, BIGINT, TEXT, TEXT[], TEXT, JSONB, BIGINT, TEXT, TEXT, TEXT
) FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_sales_import') THEN
        GRANT SELECT ON TABLE campaign_reporting_heads TO unihub_sales_import;
        GRANT EXECUTE ON FUNCTION public.publish_campaign_reporting_generation(
            TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, TEXT, BIGINT,
            TEXT, DATE, BIGINT, BIGINT, TEXT, TEXT[], TEXT, JSONB, BIGINT, TEXT, TEXT, TEXT
        ) TO unihub_sales_import;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_insight_reader') THEN
        GRANT USAGE ON SCHEMA public TO unihub_insight_reader;
        GRANT SELECT ON TABLE reporting_source_snapshot_v4, reporting_campaign_month_v2
            TO unihub_insight_reader;
    END IF;
END
$$;
