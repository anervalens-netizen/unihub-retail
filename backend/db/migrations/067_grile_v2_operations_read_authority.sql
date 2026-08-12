-- The isolated Grile worker projects read-only Retail reporting data to the
-- Grile V2 pilot. Keep its authority limited to the exact reporting inputs.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_operations') THEN
        GRANT SELECT ON TABLE
            reporting_agent_day,
            reporting_cartela_day,
            ai_forecast_runs,
            ai_forecast_store_day,
            reporting_sales_cutoff_v1,
            reporting_campaign_month_v3
        TO unihub_operations;
    END IF;
END
$$;
