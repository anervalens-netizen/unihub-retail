-- V3 Audit Lot 45 P1 remediation: grant EXECUTE on the scalar sales-generation
-- epoch to the durable export operations authority.
--
-- Migration 076 (V3 Audit Lot 35) exposed public.current_sales_generation_epoch()
-- to unihub_web_read only. V3 Lot 45 fences composed sales-derived reads in
-- the durable export path through the same scalar epoch, so the export worker's
-- real authority (unihub_operations_worker, a member only of unihub_operations)
-- must also be able to call the scalar function.
--
-- This delta is the smallest possible authority change:
--
--   - GRANT EXECUTE on the scalar function to unihub_operations ONLY.
--   - PUBLIC remains denied (REVOKE ALL from PUBLIC is preserved by 076).
--   - unihub_web_read remains allowed (existing grant is untouched).
--   - unihub_sales_import / unihub_finance_import / unihub_salary_export
--     receive no new EXECUTE.
--   - No DML, no SELECT on public.sales_generation_promotions, no grant to
--     any other object is added.
--   - The function body, signature, STABLE / SECURITY DEFINER / search_path
--     are NOT recreated or altered.
--
-- The defensive assertion block mirrors the audit gate style established by
-- migrations 039 / 040 / 066 and fails closed when any invariant regresses.

DO $$
DECLARE
    function_record record;
BEGIN
    SELECT prox.prosecdef, prox.proconfig
    INTO function_record
    FROM pg_proc prox
    JOIN pg_namespace nsp ON nsp.oid = prox.pronamespace
    WHERE nsp.nspname = 'public'
      AND prox.proname = 'current_sales_generation_epoch';

    IF function_record IS NULL THEN
        RAISE EXCEPTION
            'public.current_sales_generation_epoch() must be provisioned by migration 076 before 077';
    END IF;
    IF function_record.prosecdef IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION
            'public.current_sales_generation_epoch() must remain SECURITY DEFINER';
    END IF;
END
$$;

GRANT EXECUTE ON FUNCTION public.current_sales_generation_epoch()
    TO unihub_operations;

DO $$
DECLARE
    proacl_text TEXT;
    public_has_execute boolean := false;
    web_has_execute boolean := false;
    ops_has_execute boolean := false;
    salary_has_execute boolean := false;
    sales_has_execute boolean := false;
    finance_has_execute boolean := false;
    ops_has_select boolean := false;
    ops_has_insert boolean := false;
    ops_has_update boolean := false;
    ops_has_delete boolean := false;
BEGIN
    -- Parse pg_proc.proacl once: each entry is "grantee=privs/grantor".
    -- PUBLIC appears as the literal grantee name "PUBLIC" when granted.
    SELECT p.proacl::text
    INTO proacl_text
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND p.proname = 'current_sales_generation_epoch';

    public_has_execute := proacl_text LIKE '%PUBLIC=X%' OR proacl_text LIKE '%PUBLIC=U%'
                          OR proacl_text = '{PUBLIC=X/' || current_user || '}';
    web_has_execute    := proacl_text LIKE '%unihub_web_read=X/%';
    ops_has_execute    := proacl_text LIKE '%unihub_operations=X/%';
    salary_has_execute := proacl_text LIKE '%unihub_salary_export=X/%';
    sales_has_execute  := proacl_text LIKE '%unihub_sales_import=X/%';
    finance_has_execute:= proacl_text LIKE '%unihub_finance_import=X/%';

    ops_has_select := has_table_privilege(
        'unihub_operations', 'public.sales_generation_promotions', 'SELECT'
    );
    ops_has_insert := has_table_privilege(
        'unihub_operations', 'public.sales_generation_promotions', 'INSERT'
    );
    ops_has_update := has_table_privilege(
        'unihub_operations', 'public.sales_generation_promotions', 'UPDATE'
    );
    ops_has_delete := has_table_privilege(
        'unihub_operations', 'public.sales_generation_promotions', 'DELETE'
    );

    IF NOT ops_has_execute THEN
        RAISE EXCEPTION
            'unihub_operations must acquire EXECUTE on public.current_sales_generation_epoch()';
    END IF;
    IF NOT web_has_execute THEN
        RAISE EXCEPTION
            'unihub_web_read must retain EXECUTE on public.current_sales_generation_epoch()';
    END IF;
    IF public_has_execute THEN
        RAISE EXCEPTION
            'PUBLIC must remain denied on public.current_sales_generation_epoch()';
    END IF;
    IF salary_has_execute OR sales_has_execute OR finance_has_execute THEN
        RAISE EXCEPTION
            'salary / sales-import / finance-import authorities must not receive EXECUTE';
    END IF;
    IF ops_has_select OR ops_has_insert OR ops_has_update OR ops_has_delete THEN
        RAISE EXCEPTION
            'unihub_operations must not gain any DML on public.sales_generation_promotions';
    END IF;
END
$$;
