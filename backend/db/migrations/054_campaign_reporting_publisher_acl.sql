-- Campaign reporting is produced by the isolated sales-import authority.
-- Grant only the three existing inputs additionally read by the canonical
-- Incentive evaluator; publication writes remain behind the definer function
-- introduced by migration 053.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_sales_import') THEN
        GRANT SELECT ON TABLE
            incentive_campaigns,
            incentive_products,
            ai_forecast_runs,
            ai_forecast_store_day,
            store_targets
        TO unihub_sales_import;
    END IF;
END
$$;
