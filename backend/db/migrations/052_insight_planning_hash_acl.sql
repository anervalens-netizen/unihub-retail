-- Let the read-only Insight projection validate promoted forecast integrity.
--
-- PostgreSQL checks EXECUTE and the SQL function's underlying table access as
-- the view caller. The function returns only a deterministic digest for one
-- run id; it does not expose forecast rows. A fixed search_path and the stable
-- NOLOGIN schema owner make this a narrow, auditable SECURITY DEFINER bridge.

ALTER FUNCTION public.planning_forecast_run_sha256(BIGINT)
    SECURITY DEFINER;
ALTER FUNCTION public.planning_forecast_run_sha256(BIGINT)
    SET search_path = pg_catalog, public;

REVOKE ALL ON FUNCTION public.planning_forecast_run_sha256(BIGINT)
FROM PUBLIC, unihub_web_read, unihub_business_write, unihub_sales_import,
    unihub_finance_import, unihub_operations, unihub_migrate;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        REVOKE ALL ON FUNCTION public.planning_forecast_run_sha256(BIGINT)
        FROM unihub_runtime;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_insight_reader') THEN
        GRANT EXECUTE ON FUNCTION public.planning_forecast_run_sha256(BIGINT)
        TO unihub_insight_reader;
    END IF;
END
$$;

COMMENT ON FUNCTION public.planning_forecast_run_sha256(BIGINT) IS
    'Narrow definer digest used by read-only Planning views to fail closed on promoted-run drift.';
