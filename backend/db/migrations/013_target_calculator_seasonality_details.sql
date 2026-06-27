ALTER TABLE target_scenarios
    ADD COLUMN IF NOT EXISTS calculation_params JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE target_scenario_rows
    ADD COLUMN IF NOT EXISTS calculation_details JSONB NOT NULL DEFAULT '{}'::jsonb;
