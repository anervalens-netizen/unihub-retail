ALTER TABLE ai_forecast_runs
    ADD COLUMN IF NOT EXISTS metric TEXT NOT NULL DEFAULT 'sales_value';

ALTER TABLE ai_forecast_runs
    ADD COLUMN IF NOT EXISTS horizon TEXT NOT NULL DEFAULT 'current_month';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ai_forecast_runs_metric_check'
          AND conrelid = 'ai_forecast_runs'::regclass
    ) THEN
        ALTER TABLE ai_forecast_runs
            ADD CONSTRAINT ai_forecast_runs_metric_check
            CHECK (metric IN ('sales_value', 'units'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ai_forecast_runs_horizon_check'
          AND conrelid = 'ai_forecast_runs'::regclass
    ) THEN
        ALTER TABLE ai_forecast_runs
            ADD CONSTRAINT ai_forecast_runs_horizon_check
            CHECK (horizon IN ('current_month', 'rolling_12m'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_ai_forecast_runs_metric_horizon_month
    ON ai_forecast_runs(metric, horizon, forecast_month, status, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_forecast_runs_anchor_month
    ON ai_forecast_runs((metadata->>'anchor_month'), metric, horizon, forecast_month, status, generated_at DESC);
