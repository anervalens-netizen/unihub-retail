CREATE TABLE IF NOT EXISTS target_calculator_rule_sets (
    id TEXT PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9-]{2,127}$'),
    version INTEGER NOT NULL CHECK (version > 0),
    effective_from_month TEXT NOT NULL CHECK (effective_from_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    rules JSONB NOT NULL,
    rules_sha256 TEXT NOT NULL CHECK (rules_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version),
    UNIQUE (effective_from_month)
);

CREATE OR REPLACE FUNCTION target_calculator_rule_sets_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    latest_effective_from_month TEXT;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('target_calculator_rule_sets_append_only', 0));
    SELECT MAX(effective_from_month) INTO latest_effective_from_month
    FROM target_calculator_rule_sets;
    IF latest_effective_from_month IS NOT NULL
       AND NEW.effective_from_month <= latest_effective_from_month THEN
        RAISE EXCEPTION 'target calculator rule-sets must append after the latest effective month';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_target_calculator_rule_sets_append_only ON target_calculator_rule_sets;
CREATE TRIGGER trg_target_calculator_rule_sets_append_only
    BEFORE INSERT ON target_calculator_rule_sets
    FOR EACH ROW EXECUTE FUNCTION target_calculator_rule_sets_append_only();

CREATE OR REPLACE FUNCTION target_calculator_rule_sets_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'target calculator rule-sets are append-only; updates and deletes are forbidden';
END
$$;

DROP TRIGGER IF EXISTS trg_target_calculator_rule_sets_immutable ON target_calculator_rule_sets;
CREATE TRIGGER trg_target_calculator_rule_sets_immutable
    BEFORE UPDATE OR DELETE ON target_calculator_rule_sets
    FOR EACH ROW EXECUTE FUNCTION target_calculator_rule_sets_immutable();

CREATE OR REPLACE VIEW target_calculator_effective_rule_sets AS
SELECT
    id,
    version,
    effective_from_month,
    LEAD(effective_from_month) OVER (ORDER BY effective_from_month) AS effective_to_month,
    rules,
    rules_sha256,
    created_at
FROM target_calculator_rule_sets;

ALTER TABLE target_scenarios
    ADD COLUMN IF NOT EXISTS rule_set_id TEXT,
    ADD COLUMN IF NOT EXISTS rule_set_hash TEXT CHECK (rule_set_hash IS NULL OR rule_set_hash ~ '^[0-9a-f]{64}$'),
    ADD COLUMN IF NOT EXISTS rule_set_snapshot JSONB,
    ADD COLUMN IF NOT EXISTS calculation_input_sha256 TEXT CHECK (calculation_input_sha256 IS NULL OR calculation_input_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN IF NOT EXISTS profitability_input_sha256 TEXT CHECK (profitability_input_sha256 IS NULL OR profitability_input_sha256 ~ '^[0-9a-f]{64}$');

ALTER TABLE target_scenario_rows
    ADD COLUMN IF NOT EXISTS cap_target NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS is_cap_limited BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS manager_override_target NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS manager_override_reason TEXT,
    ADD COLUMN IF NOT EXISTS manager_override_actor TEXT,
    ADD COLUMN IF NOT EXISTS manager_override_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS manager_override_revision INTEGER,
    ADD COLUMN IF NOT EXISTS profitability_snapshot JSONB;

CREATE OR REPLACE FUNCTION target_calculator_block_legacy_v2_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    algorithm TEXT;
BEGIN
    SELECT calculation_method INTO algorithm FROM target_scenarios WHERE id = NEW.scenario_id;
    IF algorithm = 'seasonal_blended_multiyear_v2_ruleset'
       AND NEW.manager_override_revision IS NULL THEN
        RAISE EXCEPTION 'legacy target mutation blocked for ruleset draft';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_target_calculator_block_legacy_v2_mutation ON target_scenario_rows;
CREATE TRIGGER trg_target_calculator_block_legacy_v2_mutation
    BEFORE UPDATE OF final_target, note ON target_scenario_rows
    FOR EACH ROW EXECUTE FUNCTION target_calculator_block_legacy_v2_mutation();

CREATE OR REPLACE FUNCTION target_calculator_block_legacy_v2_recalculation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.calculation_method = 'seasonal_blended_multiyear_v2_ruleset'
       AND NEW.calculation_method IS DISTINCT FROM OLD.calculation_method THEN
        RAISE EXCEPTION 'legacy target recalculation blocked for ruleset draft';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_target_calculator_block_legacy_v2_recalculation ON target_scenarios;
CREATE TRIGGER trg_target_calculator_block_legacy_v2_recalculation
    BEFORE UPDATE OF calculation_method ON target_scenarios
    FOR EACH ROW EXECUTE FUNCTION target_calculator_block_legacy_v2_recalculation();

INSERT INTO target_calculator_rule_sets (
    id, version, effective_from_month, rules, rules_sha256
)
VALUES
(
    'target-finance-legacy-19-v1',
    1,
    '1900-01',
    '{"vat":{"ruleset_id":"ro-standard-vat-v1","rule_id":"ro-standard-vat-19","rate":"0.19","multiplier":"1.19"},"salary":{"pnl_factor":"1.6955","meal_vouchers_per_agent":"480","sales_commission_rate":"0.03","assumed_attainment":"0.90","default_agent_count":2,"base_salary":"2400"},"store_exceptions":{"AFICOTRO":{"base_salary":"2600"},"AUCHMIL2":{"base_salary":"2600"},"AUCHMILI":{"base_salary":"2600"},"AUCHTRIC":{"base_salary":"2600"},"CCTCIT":{"base_salary":"2600"},"CJIULMALL":{"base_salary":"2600"},"CJPPOL":{"base_salary":"2600"},"CLUJCFPOL":{"base_salary":"2600"},"CORALEX":{"base_salary":"2600"},"COTROCENI":{"base_salary":"2600"},"CRFFEER":{"base_salary":"2600"},"CTAUCH":{"base_salary":"2600"},"CTCITYPRK":{"base_salary":"2600"},"CTCORA":{"base_salary":"2600"},"CTCRFTOM":{"base_salary":"2600"},"CTVIVO":{"base_salary":"2600"},"MC-MEGAMALL":{"base_salary":"2600"},"MCRFBAL":{"base_salary":"2600"},"MEGAMALL":{"base_salary":"2600"},"PRKLK":{"base_salary":"2600"},"PROM":{"base_salary":"2600"},"PROMEN":{"base_salary":"2600"},"SUNPLZ":{"agent_count":3,"base_salary":"2600"},"TMACUH":{"base_salary":"2600"},"TMSHOPCITY":{"base_salary":"2600"},"UNIRII":{"base_salary":"2600"}}}'::jsonb,
    'e72c9db3b7426dd79fa54a55aee91cc9656f2da8fff4fb5e146cd0609264136d'
),
(
    'target-finance-21-v1',
    2,
    '2025-08',
    '{"vat":{"ruleset_id":"ro-standard-vat-v1","rule_id":"ro-standard-vat-21","rate":"0.21","multiplier":"1.21"},"salary":{"pnl_factor":"1.6955","meal_vouchers_per_agent":"480","sales_commission_rate":"0.03","assumed_attainment":"0.90","default_agent_count":2,"base_salary":"2400"},"store_exceptions":{"AFICOTRO":{"base_salary":"2600"},"AUCHMIL2":{"base_salary":"2600"},"AUCHMILI":{"base_salary":"2600"},"AUCHTRIC":{"base_salary":"2600"},"CCTCIT":{"base_salary":"2600"},"CJIULMALL":{"base_salary":"2600"},"CJPPOL":{"base_salary":"2600"},"CLUJCFPOL":{"base_salary":"2600"},"CORALEX":{"base_salary":"2600"},"COTROCENI":{"base_salary":"2600"},"CRFFEER":{"base_salary":"2600"},"CTAUCH":{"base_salary":"2600"},"CTCITYPRK":{"base_salary":"2600"},"CTCORA":{"base_salary":"2600"},"CTCRFTOM":{"base_salary":"2600"},"CTVIVO":{"base_salary":"2600"},"MC-MEGAMALL":{"base_salary":"2600"},"MCRFBAL":{"base_salary":"2600"},"MEGAMALL":{"base_salary":"2600"},"PRKLK":{"base_salary":"2600"},"PROM":{"base_salary":"2600"},"PROMEN":{"base_salary":"2600"},"SUNPLZ":{"agent_count":3,"base_salary":"2600"},"TMACUH":{"base_salary":"2600"},"TMSHOPCITY":{"base_salary":"2600"},"UNIRII":{"base_salary":"2600"}}}'::jsonb,
    'af09bc2b7e20a68b854e2cc58ce1b406118b6e94d99312f061b946c64b25c81c'
)
ON CONFLICT (id) DO NOTHING;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        GRANT SELECT ON TABLE target_calculator_rule_sets TO unihub_runtime;
        GRANT SELECT ON TABLE target_calculator_effective_rule_sets TO unihub_runtime;
    END IF;
END
$$;

COMMENT ON TABLE target_calculator_rule_sets IS
    'Append-only Target financial rule history. Effective [from,to) ends are derived from the next inserted version; scenario snapshots, not current rules, are used on later reads.';
COMMENT ON COLUMN target_scenarios.rule_set_snapshot IS
    'Immutable calculation-time copy of the validated Target rule-set; legacy scenarios intentionally remain null/unversioned.';
COMMENT ON COLUMN target_scenario_rows.manager_override_target IS
    'Explicit manager decision kept separately from the immutable algorithmic proposed_target.';
