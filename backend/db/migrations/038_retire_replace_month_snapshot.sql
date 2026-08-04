-- The historical importer is offline-only.  Retire the destructive snapshot
-- replacement function before any legitimate reimport can use the canonical
-- Stage -> Validate -> Promote flow.
DO $$
BEGIN
    IF to_regprocedure('public.replace_month_snapshot(text)') IS NOT NULL THEN
        EXECUTE 'REVOKE EXECUTE ON FUNCTION public.replace_month_snapshot(text) FROM PUBLIC';
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
            EXECUTE 'REVOKE EXECUTE ON FUNCTION public.replace_month_snapshot(text) FROM unihub_runtime';
        END IF;
    END IF;
END
$$;

DROP FUNCTION IF EXISTS public.replace_month_snapshot(text);
