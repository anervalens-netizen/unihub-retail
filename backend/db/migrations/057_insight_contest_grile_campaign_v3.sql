-- Additive Insight contracts: canonical Contest publication, fenced Grile
-- projection and Campaign mechanism variants.  Earlier v2/v4 contracts remain
-- readable for N-1 clients.

ALTER TABLE campaign_reporting_rows
    ADD COLUMN mechanism_variant TEXT;

ALTER TABLE campaign_reporting_rows
    ADD CONSTRAINT ck_campaign_reporting_mechanism_variant
    CHECK (
        mechanism_variant IS NULL
        OR (mechanism = 'focus' AND mechanism_variant = 'focus')
        OR (mechanism = 'incentive' AND mechanism_variant = 'incentive')
        OR (
            mechanism = 'promo'
            AND mechanism_variant IN (
                'selected_item_copurchase',
                'same_model_screen_camera',
                'trigger_discounted'
            )
        )
    ) NOT VALID;

ALTER TABLE campaign_reporting_rows
    VALIDATE CONSTRAINT ck_campaign_reporting_mechanism_variant;

-- Keep the v2 publisher byte-for-byte at its old contract.  The v3 wrapper
-- passes the candidate through a transaction-local envelope so a BEFORE INSERT
-- trigger can populate the newly materialized value without changing v2 rows.
ALTER FUNCTION public.publish_campaign_reporting_generation(
    TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, TEXT, BIGINT,
    TEXT, DATE, BIGINT, BIGINT, TEXT, TEXT[], TEXT, JSONB, BIGINT, TEXT, TEXT, TEXT
) RENAME TO publish_campaign_reporting_generation_v2;

CREATE OR REPLACE FUNCTION public.set_campaign_reporting_mechanism_variant()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    candidate JSONB;
    variant TEXT;
    envelope TEXT;
BEGIN
    envelope := NULLIF(current_setting('unihub.campaign_reporting_rows', true), '');
    IF envelope IS NOT NULL THEN
        SELECT item INTO candidate
        FROM jsonb_array_elements(envelope::JSONB) AS item
        WHERE item->>'mechanism' = NEW.mechanism
          AND item->>'campaign_key' = NEW.campaign_key
          AND item->>'site_code' = NEW.site_code
          AND item->>'agent' = NEW.agent;
        variant := NULLIF(btrim(candidate->>'mechanism_variant'), '');
        IF variant IS NOT NULL THEN
            NEW.mechanism_variant := variant;
        END IF;
    END IF;
    IF NEW.mechanism_variant IS NOT NULL AND NOT (
        (NEW.mechanism = 'focus' AND NEW.mechanism_variant = 'focus')
        OR (NEW.mechanism = 'incentive' AND NEW.mechanism_variant = 'incentive')
        OR (
            NEW.mechanism = 'promo'
            AND NEW.mechanism_variant IN (
                'selected_item_copurchase',
                'same_model_screen_camera',
                'trigger_discounted'
            )
        )
    ) THEN
        RAISE EXCEPTION 'campaign mechanism variant is not canonical';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_campaign_reporting_rows_variant
BEFORE INSERT ON campaign_reporting_rows
FOR EACH ROW EXECUTE FUNCTION public.set_campaign_reporting_mechanism_variant();

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
    next_head public.campaign_reporting_heads;
BEGIN
    IF p_action IS DISTINCT FROM 'promote' THEN
        RAISE EXCEPTION 'campaign reporting public publisher accepts promote only';
    END IF;
    PERFORM set_config('unihub.campaign_reporting_rows', p_rows::TEXT, true);
    SELECT * INTO next_head
    FROM public.publish_campaign_reporting_generation_v2(
        p_period, p_sales_source_generation, p_sales_authority, p_sales_authority_head,
        p_sales_status, p_sales_is_final, p_promo_generation_id, p_promo_config_sha256,
        p_promo_actuals_sha256, p_promo_material_sha256, p_incentive_campaign_id,
        p_incentive_input_sha256, p_cutoff, p_coverage_numerator,
        p_coverage_denominator, p_status, p_warnings, p_input_sha256, p_rows,
        p_expected_revision, p_requested_by_sub, p_reason, p_action
    );
    RETURN next_head;
END
$$;

CREATE TABLE contest_reporting_generations (
    id BIGSERIAL PRIMARY KEY,
    period TEXT NOT NULL CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    sales_source_generation TEXT NOT NULL CHECK (btrim(sales_source_generation) <> ''),
    sales_authority TEXT NOT NULL CHECK (btrim(sales_authority) <> ''),
    sales_authority_head TEXT NOT NULL CHECK (btrim(sales_authority_head) <> ''),
    sales_status TEXT NOT NULL CHECK (sales_status IN ('official', 'partial', 'unavailable')),
    sales_is_final BOOLEAN NOT NULL,
    contest_config_sha256 TEXT NOT NULL CHECK (contest_config_sha256 ~ '^[0-9a-f]{64}$'),
    contest_metadata JSONB NOT NULL CHECK (jsonb_typeof(contest_metadata) = 'array'),
    cutoff DATE,
    coverage_numerator BIGINT NOT NULL CHECK (coverage_numerator >= 0),
    coverage_denominator BIGINT NOT NULL CHECK (coverage_denominator >= 0),
    input_sha256 TEXT NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    output_sha256 TEXT NOT NULL CHECK (output_sha256 ~ '^[0-9a-f]{64}$'),
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    status TEXT NOT NULL CHECK (status IN ('official', 'partial', 'unavailable')),
    warnings TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    created_by_sub TEXT NOT NULL CHECK (btrim(created_by_sub) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (period, input_sha256)
);

CREATE TABLE contest_reporting_rows (
    generation_id BIGINT NOT NULL REFERENCES contest_reporting_generations(id) ON DELETE RESTRICT,
    contest_key TEXT NOT NULL CHECK (btrim(contest_key) <> ''),
    title TEXT NOT NULL,
    subtitle TEXT NOT NULL,
    scope_label TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL CHECK (end_date >= start_date),
    store_count INTEGER NOT NULL CHECK (store_count >= 0),
    identity_policy TEXT NOT NULL CHECK (identity_policy IN ('site_agent', 'person_id')),
    rank INTEGER NOT NULL CHECK (rank >= 1),
    agent TEXT NOT NULL CHECK (btrim(agent) <> ''),
    site_code TEXT NOT NULL CHECK (btrim(site_code) <> ''),
    store_name TEXT,
    locatie TEXT,
    firma TEXT,
    regional TEXT,
    asm TEXT,
    focus_units BIGINT NOT NULL CHECK (focus_units >= 0),
    promo_units BIGINT NOT NULL CHECK (promo_units >= 0),
    price_units BIGINT NOT NULL CHECK (price_units >= 0),
    focus_points BIGINT NOT NULL,
    promo_points BIGINT NOT NULL,
    price_points BIGINT NOT NULL,
    total_points BIGINT NOT NULL,
    prize TEXT,
    status TEXT NOT NULL CHECK (status IN ('official', 'partial', 'unavailable')),
    warnings TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    PRIMARY KEY (generation_id, contest_key, site_code, agent),
    CHECK (total_points = focus_points + promo_points + price_points)
);

CREATE TABLE contest_reporting_heads (
    period TEXT PRIMARY KEY CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    generation_id BIGINT NOT NULL REFERENCES contest_reporting_generations(id) ON DELETE RESTRICT,
    revision BIGINT NOT NULL CHECK (revision >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE contest_reporting_promotions (
    id BIGSERIAL PRIMARY KEY,
    period TEXT NOT NULL CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    from_generation_id BIGINT REFERENCES contest_reporting_generations(id) ON DELETE RESTRICT,
    to_generation_id BIGINT NOT NULL REFERENCES contest_reporting_generations(id) ON DELETE RESTRICT,
    head_revision BIGINT NOT NULL CHECK (head_revision >= 1),
    action TEXT NOT NULL CHECK (action IN ('promote', 'rollback')),
    input_sha256 TEXT NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    output_sha256 TEXT NOT NULL CHECK (output_sha256 ~ '^[0-9a-f]{64}$'),
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    requested_by_sub TEXT NOT NULL CHECK (btrim(requested_by_sub) <> ''),
    reason TEXT NOT NULL CHECK (btrim(reason) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (period, head_revision)
);

CREATE OR REPLACE FUNCTION public.guard_contest_reporting_generation_mutation()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'contest reporting generations are append-only'; END IF;
    RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION public.guard_contest_reporting_row_mutation()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'contest reporting rows are append-only'; END IF;
    RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION public.guard_contest_reporting_head_mutation()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'contest reporting head cannot be deleted'; END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.revision <> 1 THEN RAISE EXCEPTION 'contest reporting head must start at revision 1'; END IF;
        RETURN NEW;
    END IF;
    IF OLD.period IS DISTINCT FROM NEW.period
       OR NEW.revision <> OLD.revision + 1
       OR OLD.generation_id IS NOT DISTINCT FROM NEW.generation_id THEN
        RAISE EXCEPTION 'contest reporting head accepts only a new generation and revision CAS advance';
    END IF;
    RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION public.guard_contest_reporting_promotion_mutation()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE head contest_reporting_heads%ROWTYPE; generation contest_reporting_generations%ROWTYPE;
BEGIN
    IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'contest reporting promotion ledger is append-only'; END IF;
    SELECT * INTO head FROM public.contest_reporting_heads WHERE period = NEW.period;
    SELECT * INTO generation FROM public.contest_reporting_generations WHERE id = NEW.to_generation_id;
    IF NOT FOUND OR head.generation_id IS DISTINCT FROM NEW.to_generation_id
       OR head.revision IS DISTINCT FROM NEW.head_revision
       OR generation.input_sha256 IS DISTINCT FROM NEW.input_sha256
       OR generation.output_sha256 IS DISTINCT FROM NEW.output_sha256
       OR generation.row_count IS DISTINCT FROM NEW.row_count THEN
        RAISE EXCEPTION 'contest reporting promotion must attest to the current CAS head';
    END IF;
    IF NEW.action = 'rollback' AND NOT EXISTS (
        SELECT 1 FROM public.contest_reporting_promotions prior
        WHERE prior.period = NEW.period AND prior.to_generation_id = NEW.to_generation_id
    ) THEN RAISE EXCEPTION 'contest reporting rollback target lacks retained promotion lineage'; END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_contest_reporting_generations_immutable BEFORE INSERT OR UPDATE OR DELETE ON contest_reporting_generations FOR EACH ROW EXECUTE FUNCTION public.guard_contest_reporting_generation_mutation();
CREATE TRIGGER trg_contest_reporting_rows_immutable BEFORE INSERT OR UPDATE OR DELETE ON contest_reporting_rows FOR EACH ROW EXECUTE FUNCTION public.guard_contest_reporting_row_mutation();
CREATE TRIGGER trg_contest_reporting_heads_cas BEFORE INSERT OR UPDATE OR DELETE ON contest_reporting_heads FOR EACH ROW EXECUTE FUNCTION public.guard_contest_reporting_head_mutation();
CREATE TRIGGER trg_contest_reporting_promotions_immutable BEFORE INSERT OR UPDATE OR DELETE ON contest_reporting_promotions FOR EACH ROW EXECUTE FUNCTION public.guard_contest_reporting_promotion_mutation();

CREATE OR REPLACE FUNCTION public.publish_contest_reporting_generation(
    p_period TEXT, p_sales_source_generation TEXT, p_sales_authority TEXT,
    p_sales_authority_head TEXT, p_sales_status TEXT, p_sales_is_final BOOLEAN,
    p_contest_config_sha256 TEXT, p_cutoff DATE, p_coverage_numerator BIGINT,
    p_coverage_denominator BIGINT, p_status TEXT, p_warnings TEXT[],
    p_input_sha256 TEXT, p_contest_metadata JSONB, p_rows JSONB,
    p_expected_revision BIGINT, p_requested_by_sub TEXT, p_reason TEXT,
    p_action TEXT DEFAULT 'promote'
) RETURNS public.contest_reporting_heads
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE existing_generation contest_reporting_generations%ROWTYPE;
    current_head contest_reporting_heads%ROWTYPE; next_head contest_reporting_heads%ROWTYPE;
    v_generation_id BIGINT; v_output_sha256 TEXT; v_row_count BIGINT; v_next_revision BIGINT;
BEGIN
    IF p_period !~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
       OR NULLIF(btrim(p_sales_source_generation), '') IS NULL
       OR NULLIF(btrim(p_sales_authority), '') IS NULL
       OR NULLIF(btrim(p_sales_authority_head), '') IS NULL
       OR p_sales_status NOT IN ('official', 'partial', 'unavailable')
       OR p_status NOT IN ('official', 'partial', 'unavailable')
       OR p_contest_config_sha256 !~ '^[0-9a-f]{64}$'
       OR p_input_sha256 !~ '^[0-9a-f]{64}$'
       OR p_coverage_numerator < 0 OR p_coverage_denominator < 0
       OR p_expected_revision < 0 OR p_action IS DISTINCT FROM 'promote'
       OR NULLIF(btrim(p_requested_by_sub), '') IS NULL OR NULLIF(btrim(p_reason), '') IS NULL
       OR jsonb_typeof(p_contest_metadata) <> 'array' OR jsonb_typeof(p_rows) <> 'array' THEN
        RAISE EXCEPTION 'contest reporting publication request is invalid';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('contest-reporting:' || p_period, 0));
    v_output_sha256 := encode(digest(convert_to(p_rows::TEXT, 'UTF8'), 'sha256'), 'hex');
    v_row_count := jsonb_array_length(p_rows)::BIGINT;
    SELECT * INTO existing_generation FROM public.contest_reporting_generations
    WHERE period = p_period AND input_sha256 = p_input_sha256;
    IF FOUND AND (existing_generation.output_sha256 IS DISTINCT FROM v_output_sha256
        OR existing_generation.row_count IS DISTINCT FROM v_row_count) THEN
        RAISE EXCEPTION 'contest reporting input hash conflicts with retained generation';
    END IF;
    IF NOT FOUND THEN
        INSERT INTO public.contest_reporting_generations (
            period, sales_source_generation, sales_authority, sales_authority_head,
            sales_status, sales_is_final, contest_config_sha256, contest_metadata,
            cutoff, coverage_numerator, coverage_denominator, input_sha256, output_sha256,
            row_count, status, warnings, created_by_sub
        ) VALUES (
            p_period, btrim(p_sales_source_generation), btrim(p_sales_authority), btrim(p_sales_authority_head),
            p_sales_status, p_sales_is_final, p_contest_config_sha256, p_contest_metadata,
            p_cutoff, p_coverage_numerator, p_coverage_denominator, p_input_sha256, v_output_sha256,
            v_row_count, p_status, COALESCE(p_warnings, ARRAY[]::TEXT[]), btrim(p_requested_by_sub)
        ) RETURNING id INTO v_generation_id;
        INSERT INTO public.contest_reporting_rows (
            generation_id, contest_key, title, subtitle, scope_label, start_date, end_date,
            store_count, identity_policy, rank, agent, site_code, store_name, locatie, firma,
            regional, asm,
            focus_units, promo_units, price_units, focus_points, promo_points, price_points,
            total_points, prize, status, warnings
        ) SELECT v_generation_id, candidate.contest_key, candidate.title, candidate.subtitle,
            candidate.scope_label, candidate.start_date, candidate.end_date, candidate.store_count,
            candidate.identity_policy, candidate.rank, candidate.agent, candidate.site_code,
            candidate.store_name, candidate.locatie, candidate.firma, candidate.regional, candidate.asm,
            candidate.focus_units, candidate.promo_units, candidate.price_units, candidate.focus_points,
            candidate.promo_points, candidate.price_points, candidate.total_points,
            candidate.prize, candidate.status, COALESCE(candidate.warnings, ARRAY[]::TEXT[])
        FROM jsonb_to_recordset(p_rows) AS candidate(
            contest_key TEXT, title TEXT, subtitle TEXT, scope_label TEXT, start_date DATE, end_date DATE,
            store_count INTEGER, identity_policy TEXT, rank INTEGER, agent TEXT, site_code TEXT,
            store_name TEXT, locatie TEXT, firma TEXT, regional TEXT, asm TEXT,
            focus_units BIGINT, promo_units BIGINT, price_units BIGINT, focus_points BIGINT,
            promo_points BIGINT, price_points BIGINT, total_points BIGINT,
            prize TEXT, status TEXT, warnings TEXT[]
        );
        IF (SELECT COUNT(*) FROM public.contest_reporting_rows WHERE generation_id = v_generation_id) <> v_row_count THEN
            RAISE EXCEPTION 'contest reporting rows are not structurally unique';
        END IF;
    ELSE v_generation_id := existing_generation.id;
    END IF;
    SELECT * INTO current_head FROM public.contest_reporting_heads WHERE period = p_period FOR UPDATE;
    IF FOUND AND current_head.generation_id = v_generation_id THEN RETURN current_head; END IF;
    IF (NOT FOUND AND p_expected_revision <> 0) OR (FOUND AND current_head.revision <> p_expected_revision) THEN
        RAISE EXCEPTION 'contest reporting head revision conflict';
    END IF;
    v_next_revision := COALESCE(current_head.revision, 0) + 1;
    IF FOUND THEN
        UPDATE public.contest_reporting_heads SET generation_id = v_generation_id, revision = v_next_revision, updated_at = now()
        WHERE period = p_period RETURNING * INTO next_head;
    ELSE
        INSERT INTO public.contest_reporting_heads (period, generation_id, revision)
        VALUES (p_period, v_generation_id, v_next_revision) RETURNING * INTO next_head;
    END IF;
    INSERT INTO public.contest_reporting_promotions (
        period, from_generation_id, to_generation_id, head_revision, action, input_sha256,
        output_sha256, row_count, requested_by_sub, reason
    ) SELECT p_period, current_head.generation_id, generation.id, v_next_revision,
        p_action, generation.input_sha256, generation.output_sha256, generation.row_count,
        btrim(p_requested_by_sub), btrim(p_reason)
    FROM public.contest_reporting_generations generation WHERE generation.id = v_generation_id;
    RETURN next_head;
END $$;

CREATE OR REPLACE VIEW reporting_source_snapshot_v5 (
    domain, period, source, source_generation, authority, authority_head,
    contract_version, rule_version, status, as_of, cutoff, is_final,
    coverage_numerator, coverage_denominator, produced_at, warnings
) WITH (security_barrier = true) AS
WITH sales_periods AS (
    SELECT * FROM reporting_source_snapshot_v4 WHERE domain = 'sales'
), campaign_heads AS (
    SELECT head.period, head.revision, head.updated_at AS head_updated_at,
        generation.id AS generation_id, generation.sales_source_generation,
        generation.sales_authority, generation.sales_authority_head, generation.sales_is_final,
        generation.cutoff, generation.coverage_numerator, generation.coverage_denominator,
        generation.input_sha256, generation.status, generation.warnings, generation.created_at,
        NOT EXISTS (
            SELECT 1 FROM campaign_reporting_rows row
            WHERE row.generation_id = generation.id AND row.mechanism_variant IS NULL
        ) AS variants_complete
    FROM campaign_reporting_heads head
    JOIN campaign_reporting_generations generation ON generation.id = head.generation_id
), contest_heads AS (
    SELECT head.period, head.revision, head.updated_at AS head_updated_at,
        generation.id AS generation_id, generation.sales_source_generation,
        generation.sales_authority, generation.sales_authority_head, generation.sales_is_final,
        generation.cutoff, generation.coverage_numerator, generation.coverage_denominator,
        generation.input_sha256, generation.status, generation.warnings, generation.created_at
    FROM contest_reporting_heads head
    JOIN contest_reporting_generations generation ON generation.id = head.generation_id
), grile_eligible AS (
    SELECT sales.period, sheet.site_code, status.generation, status.current_observation_id,
        status.checked_at, status.db_max_sale_date
    FROM sales_periods sales
    JOIN grile_sheets sheet ON sheet.is_active
       AND (sheet.active_from_month IS NULL OR sheet.active_from_month <= sales.period)
    JOIN stores store ON store.site_code = sheet.site_code
       AND store.locatie NOT ILIKE 'TR%' AND store.locatie NOT ILIKE '%cartel%'
    LEFT JOIN grile_store_current_status status
      ON status.run_month = sales.period AND status.site_code = sheet.site_code
), grile_heads AS (
    SELECT period, COUNT(*)::BIGINT AS denominator,
        COUNT(*) FILTER (WHERE current_observation_id IS NOT NULL)::BIGINT AS numerator,
        MAX(generation) AS max_generation, MAX(checked_at) AS produced_at,
        MAX(db_max_sale_date) AS cutoff
    FROM grile_eligible GROUP BY period
)
SELECT domain, period, source, source_generation, authority, authority_head,
    contract_version, rule_version, status, as_of, cutoff, is_final,
    coverage_numerator, coverage_denominator, produced_at, warnings
FROM reporting_source_snapshot_v4 WHERE domain <> 'campaigns'
UNION ALL
SELECT 'campaigns', sales.period, 'campaign_reporting_heads',
    'campaign-generation:' || campaign.generation_id::TEXT || ':input:' || campaign.input_sha256,
    'campaign_reporting_head', 'campaign:' || campaign.revision::TEXT, 3,
    'campaign-publication-v3',
    CASE WHEN campaign.variants_complete THEN campaign.status ELSE 'partial' END,
    campaign.cutoff, campaign.cutoff, campaign.sales_is_final,
    campaign.coverage_numerator, campaign.coverage_denominator,
    GREATEST(campaign.created_at, campaign.head_updated_at),
    campaign.warnings || CASE WHEN campaign.variants_complete THEN ARRAY[]::TEXT[] ELSE ARRAY['campaign_variant_unpublished']::TEXT[] END
FROM sales_periods sales JOIN campaign_heads campaign ON campaign.period = sales.period
    AND campaign.sales_source_generation = sales.source_generation
    AND campaign.sales_authority = sales.authority AND campaign.sales_authority_head = sales.authority_head
UNION ALL
SELECT 'campaigns', sales.period, 'campaign_reporting_heads', 'campaign-unpublished:' || sales.source_generation,
    'campaign_reporting_head', 'none', 3, 'campaign-publication-v3', 'unavailable',
    sales.as_of, sales.cutoff, false, 0::BIGINT, sales.coverage_denominator, sales.produced_at,
    sales.warnings || ARRAY['campaign_reporting_not_published']::TEXT[]
FROM sales_periods sales LEFT JOIN campaign_heads campaign ON campaign.period = sales.period
    AND campaign.sales_source_generation = sales.source_generation
    AND campaign.sales_authority = sales.authority AND campaign.sales_authority_head = sales.authority_head
WHERE campaign.generation_id IS NULL
UNION ALL
SELECT 'contest', sales.period, 'contest_reporting_heads',
    'contest-generation:' || contest.generation_id::TEXT || ':input:' || contest.input_sha256,
    'contest_reporting_head', 'contest:' || contest.revision::TEXT, 1, 'contest-publication-v1',
    contest.status, contest.cutoff, contest.cutoff, contest.sales_is_final,
    contest.coverage_numerator, contest.coverage_denominator,
    GREATEST(contest.created_at, contest.head_updated_at), contest.warnings
FROM sales_periods sales JOIN contest_heads contest ON contest.period = sales.period
    AND contest.sales_source_generation = sales.source_generation
    AND contest.sales_authority = sales.authority AND contest.sales_authority_head = sales.authority_head
UNION ALL
SELECT 'contest', sales.period, 'contest_reporting_heads', 'contest-unpublished:' || sales.source_generation,
    'contest_reporting_head', 'none', 1, 'contest-publication-v1', 'unavailable',
    sales.as_of, sales.cutoff, false, 0::BIGINT, sales.coverage_denominator, sales.produced_at,
    sales.warnings || ARRAY['contest_reporting_not_published']::TEXT[]
FROM sales_periods sales LEFT JOIN contest_heads contest ON contest.period = sales.period
    AND contest.sales_source_generation = sales.source_generation
    AND contest.sales_authority = sales.authority AND contest.sales_authority_head = sales.authority_head
WHERE contest.generation_id IS NULL
UNION ALL
SELECT 'grile', sales.period, 'grile_store_current_status',
    'grile-current-v1:' || sales.period || ':' || COALESCE(grile.max_generation, 0)::TEXT,
    'grile_store_current_status_fence',
    'grile:' || sales.period || ':projection:' || COALESCE(grile.max_generation, 0)::TEXT,
    1, 'grile-current-fenced-v1',
    CASE WHEN COALESCE(grile.denominator, 0) = 0 THEN 'unavailable'
         WHEN grile.numerator = grile.denominator THEN 'official'
         WHEN grile.numerator > 0 THEN 'partial' ELSE 'unavailable' END,
    grile.cutoff, grile.cutoff, false, COALESCE(grile.numerator, 0),
    COALESCE(grile.denominator, 0), COALESCE(grile.produced_at, sales.produced_at),
    ARRAY['grile_current_fenced_projection_not_month_final']::TEXT[] ||
      CASE WHEN COALESCE(grile.numerator, 0) = COALESCE(grile.denominator, 0)
           AND COALESCE(grile.denominator, 0) > 0 THEN ARRAY[]::TEXT[]
           ELSE ARRAY['grile_coverage_incomplete']::TEXT[] END
FROM sales_periods sales LEFT JOIN grile_heads grile ON grile.period = sales.period;

CREATE OR REPLACE VIEW reporting_campaign_month_v3 (
    period, mechanism, mechanism_variant, campaign_key, site_code, agent, locatie, firma,
    regional, asm, actual_sales, actual_quantity, active_product_count, active_product_codes,
    promo_qualifying_bons, promo_discounted_units, promo_discount_value,
    incentive_sold_quantity, incentive_eligible_quantity, incentive_qualified_quantity,
    incentive_value, incentive_potential, incentive_store_qualified, source, source_generation,
    authority, authority_head, contract_version, rule_version, status, as_of, cutoff,
    is_final, coverage_numerator, coverage_denominator, produced_at, warnings
) WITH (security_barrier = true) AS
SELECT generation.period, row.mechanism, row.mechanism_variant, row.campaign_key,
    row.site_code, row.agent, row.locatie, row.firma, row.regional, row.asm,
    row.actual_sales, row.actual_quantity, row.active_product_count, row.active_product_codes,
    row.promo_qualifying_bons, row.promo_discounted_units, row.promo_discount_value,
    row.incentive_sold_quantity, row.incentive_eligible_quantity, row.incentive_qualified_quantity,
    row.incentive_value, row.incentive_potential, row.incentive_store_qualified,
    snapshot.source, snapshot.source_generation, snapshot.authority, snapshot.authority_head,
    snapshot.contract_version, snapshot.rule_version,
    CASE WHEN snapshot.status = 'unavailable' THEN 'unavailable' ELSE row.status END,
    snapshot.as_of, snapshot.cutoff, snapshot.is_final, snapshot.coverage_numerator,
    snapshot.coverage_denominator, snapshot.produced_at, snapshot.warnings || row.warnings
FROM campaign_reporting_heads head
JOIN campaign_reporting_generations generation ON generation.id = head.generation_id
JOIN campaign_reporting_rows row ON row.generation_id = generation.id
JOIN reporting_source_snapshot_v5 snapshot ON snapshot.domain = 'campaigns'
  AND snapshot.period = generation.period AND snapshot.authority_head = 'campaign:' || head.revision::TEXT;

CREATE OR REPLACE VIEW reporting_contest_month_v1 (
    period, contest_key, title, subtitle, scope_label, start_date, end_date, store_count,
    identity_policy, rank, agent, site_code, store_name, locatie, firma, regional, asm,
    focus_units, promo_units, price_units, focus_points, promo_points, price_points, total_points, prize,
    source, source_generation, authority, authority_head, contract_version, rule_version,
    status, as_of, cutoff, is_final, coverage_numerator, coverage_denominator, produced_at, warnings
) WITH (security_barrier = true) AS
SELECT generation.period, row.contest_key, row.title, row.subtitle, row.scope_label,
    row.start_date, row.end_date, row.store_count, row.identity_policy, row.rank, row.agent,
    row.site_code, row.store_name, row.locatie, row.firma, row.regional, row.asm,
    row.focus_units,
    row.promo_units, row.price_units, row.focus_points, row.promo_points, row.price_points,
    row.total_points, row.prize, snapshot.source, snapshot.source_generation,
    snapshot.authority, snapshot.authority_head, snapshot.contract_version, snapshot.rule_version,
    CASE WHEN snapshot.status = 'unavailable' THEN 'unavailable' ELSE row.status END,
    snapshot.as_of, snapshot.cutoff, snapshot.is_final, snapshot.coverage_numerator,
    snapshot.coverage_denominator, snapshot.produced_at, snapshot.warnings || row.warnings
FROM contest_reporting_heads head
JOIN contest_reporting_generations generation ON generation.id = head.generation_id
JOIN contest_reporting_rows row ON row.generation_id = generation.id
JOIN reporting_source_snapshot_v5 snapshot ON snapshot.domain = 'contest'
  AND snapshot.period = generation.period AND snapshot.authority_head = 'contest:' || head.revision::TEXT;

CREATE OR REPLACE VIEW reporting_grile_month_v1 (
    period, run_month, site_code, locatie, firma, regional, asm, source_run_id,
    observation_generation, generation, checked_at, completion_status, fill_status, target_status,
    sales_status, last_error_code, status, covered, eligible, source, source_generation,
    authority, authority_head, contract_version, rule_version, as_of, cutoff, is_final,
    coverage_numerator, coverage_denominator, produced_at, warnings
) WITH (security_barrier = true) AS
SELECT snapshot.period, COALESCE(current.run_month, snapshot.period), store.site_code, store.locatie, store.firma,
    store.regional, store.asm, current.source_run_id,
    CASE WHEN current.current_observation_id IS NULL THEN NULL
         ELSE 'grile-observation:' || current.current_observation_id::TEXT END,
    current.generation, current.checked_at,
    CASE WHEN current.current_observation_id IS NULL THEN 'unavailable'
         WHEN current.error_code IS NOT NULL THEN 'error'
         WHEN current.completion_pct IS NULL THEN 'incomplete'
         WHEN current.completion_pct >= 100 THEN 'complete' ELSE 'in_progress' END,
    current.fill_status, current.target_status, current.sales_status, current.last_error_code,
    CASE WHEN current.current_observation_id IS NULL OR current.error_code IS NOT NULL THEN 'unavailable'
         WHEN current.fill_status IS DISTINCT FROM 'COMPLETAT'
           OR current.target_status IS DISTINCT FROM 'OK'
           OR current.sales_status IS DISTINCT FROM 'OK' THEN 'partial'
         ELSE snapshot.status END,
    current.current_observation_id IS NOT NULL, true,
    snapshot.source, snapshot.source_generation, snapshot.authority, snapshot.authority_head,
    snapshot.contract_version, snapshot.rule_version, snapshot.as_of, snapshot.cutoff,
    snapshot.is_final, snapshot.coverage_numerator, snapshot.coverage_denominator,
    snapshot.produced_at,
    snapshot.warnings || ARRAY_REMOVE(ARRAY[
        CASE WHEN current.current_observation_id IS NULL THEN 'grile_observation_missing' END,
        CASE WHEN current.last_error_code IS NOT NULL THEN 'grile_last_error:' || current.last_error_code END
    ], NULL)
FROM reporting_source_snapshot_v5 snapshot
JOIN grile_sheets sheet ON sheet.is_active
  AND (sheet.active_from_month IS NULL OR sheet.active_from_month <= snapshot.period)
JOIN stores store ON store.site_code = sheet.site_code
  AND store.locatie NOT ILIKE 'TR%' AND store.locatie NOT ILIKE '%cartel%'
LEFT JOIN grile_store_current_status current ON current.run_month = snapshot.period
  AND current.site_code = store.site_code
WHERE snapshot.domain = 'grile';

COMMENT ON VIEW reporting_source_snapshot_v5 IS
    'Additive v5 source metadata: Campaigns v3 mechanism variants, canonical Contest heads and fenced Grile current projection.';
COMMENT ON VIEW reporting_campaign_month_v3 IS
    'Campaign v3 has a stable config-derived mechanism_variant; NULL requires canonical republish and is partial in v5 metadata.';
COMMENT ON VIEW reporting_contest_month_v1 IS
    'Head-selected immutable output of ContestsService; promo_units are source units, never inferred receipts.';
COMMENT ON VIEW reporting_grile_month_v1 IS
    'Eligible Grile store projection with per-store fence generation, coverage and retained last error metadata.';

REVOKE ALL ON FUNCTION public.publish_campaign_reporting_generation_v2(
    TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, TEXT, BIGINT,
    TEXT, DATE, BIGINT, BIGINT, TEXT, TEXT[], TEXT, JSONB, BIGINT, TEXT, TEXT, TEXT
) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.publish_campaign_reporting_generation(
    TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, TEXT, BIGINT,
    TEXT, DATE, BIGINT, BIGINT, TEXT, TEXT[], TEXT, JSONB, BIGINT, TEXT, TEXT, TEXT
) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.publish_contest_reporting_generation(
    TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, DATE, BIGINT, BIGINT, TEXT,
    TEXT[], TEXT, JSONB, JSONB, BIGINT, TEXT, TEXT, TEXT
) FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_sales_import') THEN
        REVOKE EXECUTE ON FUNCTION public.publish_campaign_reporting_generation_v2(
            TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, TEXT, BIGINT,
            TEXT, DATE, BIGINT, BIGINT, TEXT, TEXT[], TEXT, JSONB, BIGINT, TEXT, TEXT, TEXT
        ) FROM unihub_sales_import;
        GRANT SELECT (agent_code, site_code, match_status, effective_from_month, person_id)
            ON TABLE agent_salary_links TO unihub_sales_import;
        GRANT SELECT ON TABLE campaign_reporting_heads, contest_reporting_heads TO unihub_sales_import;
        GRANT EXECUTE ON FUNCTION public.publish_campaign_reporting_generation(
            TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, TEXT, BIGINT,
            TEXT, DATE, BIGINT, BIGINT, TEXT, TEXT[], TEXT, JSONB, BIGINT, TEXT, TEXT, TEXT
        ) TO unihub_sales_import;
        GRANT EXECUTE ON FUNCTION public.publish_contest_reporting_generation(
            TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, DATE, BIGINT, BIGINT, TEXT,
            TEXT[], TEXT, JSONB, JSONB, BIGINT, TEXT, TEXT, TEXT
        ) TO unihub_sales_import;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_insight_reader') THEN
        GRANT USAGE ON SCHEMA public TO unihub_insight_reader;
        GRANT SELECT ON TABLE reporting_source_snapshot_v5, reporting_campaign_month_v3,
            reporting_contest_month_v1, reporting_grile_month_v1 TO unihub_insight_reader;
    END IF;
END
$$;
