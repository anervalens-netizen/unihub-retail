-- Dedicated least-privilege authority for server-attested salary workbooks.
--
-- The NOLOGIN authority is created operationally before this migration. The
-- immutable migration grants only the columns needed to aggregate a salary
-- workbook and fences durable export rows by kind with PostgreSQL RLS.

DO $$
DECLARE
    authority RECORD;
BEGIN
    SELECT rolcanlogin, rolsuper, rolinherit, rolcreatedb, rolcreaterole,
           rolbypassrls, rolreplication
    INTO authority
    FROM pg_roles
    WHERE rolname = 'unihub_salary_export';

    IF authority IS NULL THEN
        RAISE EXCEPTION
            'unihub_salary_export NOLOGIN authority must be provisioned before migration 066';
    END IF;
    IF authority.rolcanlogin
       OR authority.rolsuper
       OR authority.rolinherit
       OR authority.rolcreatedb
       OR authority.rolcreaterole
       OR authority.rolbypassrls
       OR authority.rolreplication THEN
        RAISE EXCEPTION 'unihub_salary_export authority flags are invalid';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM pg_auth_members membership
        JOIN pg_roles member ON member.oid = membership.member
        WHERE member.rolname = 'unihub_salary_export'
    ) THEN
        RAISE EXCEPTION 'unihub_salary_export must not inherit another authority';
    END IF;
END
$$;

REVOKE ALL ON TABLE salary_records FROM unihub_salary_export;
REVOKE ALL ON TABLE stores FROM unihub_salary_export;
REVOKE ALL ON TABLE reporting_agent_month FROM unihub_salary_export;
REVOKE ALL ON TABLE export_operations FROM unihub_salary_export;
REVOKE ALL ON SEQUENCE export_operations_id_seq FROM unihub_salary_export;
REVOKE ALL ON SCHEMA salary_private FROM unihub_salary_export;
REVOKE CREATE ON SCHEMA public FROM unihub_salary_export;

GRANT SELECT (
    id, year, month, full_name, person_id, total_salary,
    company_name, site_code, locatie
) ON TABLE salary_records TO unihub_salary_export;
GRANT SELECT (site_code, regional, asm)
    ON TABLE stores TO unihub_salary_export;
GRANT SELECT (import_month, site_code, firma, total_sales)
    ON TABLE reporting_agent_month TO unihub_salary_export;

GRANT SELECT ON TABLE export_operations TO unihub_salary_export;
GRANT UPDATE (
    status, execution_owner, execution_epoch, execution_lease_until,
    artifact_key, artifact_sha256, artifact_size, peak_rss_bytes,
    build_seconds, cell_count, row_count, download_filename, error_code,
    updated_at, started_at, finished_at, expires_at
) ON TABLE export_operations TO unihub_salary_export;

ALTER TABLE export_operations ENABLE ROW LEVEL SECURITY;

CREATE POLICY export_operations_web_read
    ON export_operations FOR SELECT TO unihub_web_read
    USING (TRUE);
CREATE POLICY export_operations_business_insert
    ON export_operations FOR INSERT TO unihub_business_write
    WITH CHECK (TRUE);
CREATE POLICY export_operations_business_update
    ON export_operations FOR UPDATE TO unihub_business_write
    USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY export_operations_operations_read
    ON export_operations FOR SELECT TO unihub_operations
    USING (kind IN ('daily_metrics', 'daily_comparison'));
CREATE POLICY export_operations_operations_update
    ON export_operations FOR UPDATE TO unihub_operations
    USING (kind IN ('daily_metrics', 'daily_comparison'))
    WITH CHECK (kind IN ('daily_metrics', 'daily_comparison'));
CREATE POLICY export_operations_salary_read
    ON export_operations FOR SELECT TO unihub_salary_export
    USING (kind IN ('salary_store_summary', 'salary_monthly_trend', 'salary_agents'));
CREATE POLICY export_operations_salary_update
    ON export_operations FOR UPDATE TO unihub_salary_export
    USING (kind IN ('salary_store_summary', 'salary_monthly_trend', 'salary_agents'))
    WITH CHECK (kind IN ('salary_store_summary', 'salary_monthly_trend', 'salary_agents'));

DO $$
BEGIN
    IF NOT (
        SELECT relrowsecurity
        FROM pg_class
        WHERE oid = 'public.export_operations'::regclass
    ) THEN
        RAISE EXCEPTION 'export_operations RLS must be enabled';
    END IF;
    IF has_schema_privilege('unihub_salary_export', 'salary_private', 'USAGE')
       OR has_schema_privilege('unihub_salary_export', 'public', 'CREATE')
       OR has_sequence_privilege(
           'unihub_salary_export', 'public.export_operations_id_seq', 'USAGE'
       ) THEN
        RAISE EXCEPTION 'salary export authority received forbidden privileges';
    END IF;
    IF has_table_privilege('unihub_salary_export', 'public.salary_records', 'SELECT')
       OR has_table_privilege('unihub_salary_export', 'public.stores', 'SELECT')
       OR has_table_privilege(
           'unihub_salary_export', 'public.reporting_agent_month', 'SELECT'
       ) THEN
        RAISE EXCEPTION 'salary source access must remain column-scoped';
    END IF;
    IF NOT has_table_privilege(
        'unihub_salary_export', 'public.export_operations', 'SELECT'
    ) OR NOT has_any_column_privilege(
        'unihub_salary_export', 'public.export_operations', 'UPDATE'
    ) THEN
        RAISE EXCEPTION 'salary export lifecycle privileges are incomplete';
    END IF;
END
$$;
