-- reporting_campaign_month_v3 joins reporting_source_snapshot_v5, whose
-- integrity fence calls this narrow SECURITY DEFINER digest.  The Grile V2
-- worker needs EXECUTE on the digest, but no access to the underlying
-- planning tables.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_operations') THEN
        GRANT EXECUTE ON FUNCTION public.planning_forecast_run_sha256(BIGINT)
        TO unihub_operations;
    END IF;
END
$$;
