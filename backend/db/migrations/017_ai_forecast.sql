CREATE TABLE IF NOT EXISTS ai_forecast_runs (
    id BIGSERIAL PRIMARY KEY,
    forecast_month TEXT NOT NULL,
    source_month TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_mode TEXT NOT NULL,
    variant TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed'
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_forecast_runs_month_status
    ON ai_forecast_runs(forecast_month, status, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_forecast_runs_source_status
    ON ai_forecast_runs(source_month, status, generated_at DESC);

CREATE TABLE IF NOT EXISTS ai_forecast_store_month (
    run_id BIGINT NOT NULL REFERENCES ai_forecast_runs(id) ON DELETE CASCADE,
    site_code TEXT NOT NULL REFERENCES stores(site_code),
    forecast_sales NUMERIC(14, 2) NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (run_id, site_code)
);

CREATE INDEX IF NOT EXISTS idx_ai_forecast_store_month_site
    ON ai_forecast_store_month(site_code);

CREATE TABLE IF NOT EXISTS ai_forecast_store_day (
    run_id BIGINT NOT NULL REFERENCES ai_forecast_runs(id) ON DELETE CASCADE,
    forecast_date DATE NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code),
    forecast_sales NUMERIC(14, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, forecast_date, site_code)
);

CREATE INDEX IF NOT EXISTS idx_ai_forecast_store_day_site_date
    ON ai_forecast_store_day(site_code, forecast_date);
