-- V3 Audit Lot 45 P1 remediation: grant EXECUTE on the scalar sales-generation
-- epoch to the durable export operations authority.
--
-- Migration 076 (V3 Audit Lot 35) exposes public.current_sales_generation_epoch()
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
-- The defensive assertion block mirrors the audit gate style of migrations
-- 039 / 040 / 066 / 068 and uses *structured* catalog ACL inspection via
-- aclexplode() so the PUBLIC-only assertion and the named-authority assertions
-- read directly from the catalog (grantee OID 0 == PUBLIC,
-- grantee::regrole for named authorities), not from textual formatting of
-- proacl that PostgreSQL never renders consistently across versions.

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
    function_record record;
    rec record;
    expected_auth_with_execute text;
    unexpected_acl text := '';
    forbidden_auth_with_execute text := '';
    ops_has_no_ledger_acl boolean := true;
    unexpected_ledger_acl text := '';
    explicit_execute_grantees text[] := '{}';
    explicit_other_grantees text[] := '{}';
BEGIN
    -- Locate the function so we have its owner; the owner row in proacl
    -- is self-granted and we always allow it.
    SELECT
        p.oid,
        p.proowner,
        pg_catalog.pg_get_userbyid(p.proowner) AS owner_role_name
    INTO function_record
    FROM pg_proc p
    JOIN pg_namespace nsp ON nsp.oid = p.pronamespace
    WHERE nsp.nspname = 'public'
      AND p.proname = 'current_sales_generation_epoch';

    IF function_record.oid IS NULL THEN
        RAISE EXCEPTION
            'public.current_sales_generation_epoch() missing during ACL inspection';
    END IF;

    -- Walk every ACL entry on the function. aclexplode() emits one row per
    -- (grantee, privilege_type). PUBLIC = grantee::oid = 0.
    FOR rec IN
        SELECT
            a.grantee,
            a.grantee::regrole::text AS grantee_role,
            a.grantor,
            a.privilege_type,
            a.is_grantable
        FROM pg_proc p
        CROSS JOIN LATERAL aclexplode(p.proacl) AS a
        WHERE p.oid = function_record.oid
    LOOP
        -- Owner self-grant: implicit, always allowed.
        IF rec.grantee = rec.grantor
           AND rec.grantee = function_record.proowner THEN
            CONTINUE;
        END IF;

        -- Any privilege other than EXECUTE on a SQL SECURITY DEFINER function
        -- is unexpected (the function body is read-only).
        IF rec.privilege_type <> 'EXECUTE' THEN
            unexpected_acl := unexpected_acl
                || format(
                    'unexpected privilege %s for %s (oid=%s); ',
                    rec.privilege_type, rec.grantee_role, rec.grantee
                );
        END IF;

        -- PUBLIC (grantee OID 0) on this function is forbidden.
        IF rec.grantee = 0 THEN
            forbidden_auth_with_execute := forbidden_auth_with_execute
                || 'PUBLIC';
        END IF;

        -- Sibling-authority EXECUTE grants are forbidden.
        IF rec.grantee <> 0
           AND rec.grantee_role IN (
               'unihub_salary_export', 'unihub_sales_import',
               'unihub_finance_import'
           )
           AND rec.privilege_type = 'EXECUTE' THEN
            forbidden_auth_with_execute := forbidden_auth_with_execute
                || format('%s ', rec.grantee_role);
        END IF;

        -- Track every explicit named-non-owner EXECUTE grant so we can
        -- confirm the surface is exactly the expected two.
        IF rec.grantee <> 0
           AND rec.privilege_type = 'EXECUTE' THEN
            explicit_execute_grantees := array_append(
                explicit_execute_grantees, rec.grantee_role
            );
        ELSIF rec.grantee <> 0 AND rec.privilege_type <> 'EXECUTE' THEN
            explicit_other_grantees := array_append(
                explicit_other_grantees,
                format('%s/%s', rec.grantee_role, rec.privilege_type)
            );
        END IF;
    END LOOP;

    IF forbidden_auth_with_execute <> '' THEN
        RAISE EXCEPTION
            'unauthorized EXECUTE on public.current_sales_generation_epoch(): %',
            forbidden_auth_with_execute;
    END IF;

    -- The expected EXECUTE surface is exactly {unihub_web_read, unihub_operations}
    -- plus the owner self-grant filtered above. Anything else is unexpected.
    FOREACH expected_auth_with_execute IN ARRAY
        ARRAY['unihub_web_read', 'unihub_operations']
    LOOP
        IF NOT (expected_auth_with_execute = ANY (explicit_execute_grantees)) THEN
            RAISE EXCEPTION
                'expected EXECUTE on current_sales_generation_epoch() for % missing',
                expected_auth_with_execute;
        END IF;
    END LOOP;
    FOREACH expected_auth_with_execute IN ARRAY explicit_execute_grantees LOOP
        IF expected_auth_with_execute NOT IN (
            'unihub_web_read', 'unihub_operations'
        ) THEN
            unexpected_acl := unexpected_acl
                || format('unexpected EXECUTE grantee %s; ', expected_auth_with_execute);
        END IF;
    END LOOP;
    IF array_length(explicit_other_grantees, 1) IS NOT NULL THEN
        unexpected_acl := unexpected_acl
            || format('unexpected other privileges: %s',
                      array_to_string(explicit_other_grantees, ', '));
    END IF;
    IF unexpected_acl <> '' THEN
        RAISE EXCEPTION
            'unexpected ACL on public.current_sales_generation_epoch(): %',
            unexpected_acl;
    END IF;

    -- Surface 2: unihub_operations must remain revoked from the immutable
    -- ledger. Migration 040 REVOKEs the ledger from unihub_operations; the
    -- structural check guards against any future regression that re-grants.
    FOR rec IN
        SELECT a.privilege_type, a.grantee::regrole::text AS grantee_role
        FROM pg_class c
        CROSS JOIN LATERAL aclexplode(c.relacl) AS a
        WHERE c.oid = 'public.sales_generation_promotions'::regclass
          AND a.grantee::regrole::text = 'unihub_operations'
    LOOP
        ops_has_no_ledger_acl := false;
        unexpected_ledger_acl := unexpected_ledger_acl
            || format(
                'unihub_operations has %s on public.sales_generation_promotions; ',
                rec.privilege_type
            );
    END LOOP;
    IF NOT ops_has_no_ledger_acl THEN
        RAISE EXCEPTION
            'unihub_operations must not gain any privilege on public.sales_generation_promotions: %',
            unexpected_ledger_acl;
    END IF;
END
$$;
