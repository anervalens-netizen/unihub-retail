-- P1-A: separate the migration process marker from durable schema ownership.
-- This migration is applied once by the pre-cutover administrative migration
-- identity. Later deltas authenticate as a NOINHERIT runner and SET LOCAL ROLE
-- to this NOLOGIN owner inside each checksum-controlled transaction.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_schema_owner') THEN
        CREATE ROLE unihub_schema_owner
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
            NOBYPASSRLS NOREPLICATION;
    ELSE
        ALTER ROLE unihub_schema_owner
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
            NOBYPASSRLS NOREPLICATION;
    END IF;
END
$$;

DO $$
DECLARE
    item RECORD;
    command TEXT;
BEGIN
    FOR item IN
        SELECT class.relkind, class.oid::regclass AS object_name
        FROM pg_class AS class
        JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
        WHERE namespace.nspname IN ('public', 'salary_private')
          AND class.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
          AND class.relowner = current_user::regrole
          AND NOT EXISTS (
              SELECT 1
              FROM pg_depend AS dependency
              WHERE dependency.classid = 'pg_class'::regclass
                AND dependency.objid = class.oid
                AND dependency.deptype = 'e'
          )
        ORDER BY CASE class.relkind
            WHEN 'r' THEN 1
            WHEN 'p' THEN 1
            WHEN 'f' THEN 1
            WHEN 'S' THEN 2
            ELSE 3
        END, class.oid
    LOOP
        command := CASE item.relkind
            WHEN 'S' THEN 'ALTER SEQUENCE '
            WHEN 'v' THEN 'ALTER VIEW '
            WHEN 'm' THEN 'ALTER MATERIALIZED VIEW '
            WHEN 'f' THEN 'ALTER FOREIGN TABLE '
            ELSE 'ALTER TABLE '
        END;
        EXECUTE command || item.object_name || ' OWNER TO unihub_schema_owner';
    END LOOP;

    FOR item IN
        SELECT routine.oid::regprocedure AS object_name
        FROM pg_proc AS routine
        JOIN pg_namespace AS namespace ON namespace.oid = routine.pronamespace
        WHERE namespace.nspname IN ('public', 'salary_private')
          AND routine.prokind IN ('f', 'p')
          AND routine.proowner = current_user::regrole
          AND NOT EXISTS (
              SELECT 1
              FROM pg_depend AS dependency
              WHERE dependency.classid = 'pg_proc'::regclass
                AND dependency.objid = routine.oid
                AND dependency.deptype = 'e'
          )
        ORDER BY routine.oid
    LOOP
        EXECUTE 'ALTER ROUTINE ' || item.object_name || ' OWNER TO unihub_schema_owner';
    END LOOP;

    FOR item IN
        SELECT format('%I.%I', namespace.nspname, type.typname) AS object_name
        FROM pg_type AS type
        JOIN pg_namespace AS namespace ON namespace.oid = type.typnamespace
        WHERE namespace.nspname IN ('public', 'salary_private')
          AND type.typtype IN ('d', 'e')
          AND type.typowner = current_user::regrole
          AND NOT EXISTS (
              SELECT 1
              FROM pg_depend AS dependency
              WHERE dependency.classid = 'pg_type'::regclass
                AND dependency.objid = type.oid
                AND dependency.deptype = 'e'
          )
        ORDER BY type.oid
    LOOP
        EXECUTE 'ALTER TYPE ' || item.object_name || ' OWNER TO unihub_schema_owner';
    END LOOP;
END
$$;

ALTER SCHEMA public OWNER TO unihub_schema_owner;
ALTER SCHEMA salary_private OWNER TO unihub_schema_owner;
GRANT USAGE, CREATE ON SCHEMA public TO unihub_schema_owner;
GRANT USAGE, CREATE ON SCHEMA salary_private TO unihub_schema_owner;

ALTER DEFAULT PRIVILEGES FOR ROLE unihub_schema_owner IN SCHEMA public
    REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE unihub_schema_owner IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE unihub_schema_owner IN SCHEMA public
    REVOKE ALL ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE unihub_schema_owner
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE unihub_schema_owner IN SCHEMA salary_private
    REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE unihub_schema_owner IN SCHEMA salary_private
    REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE unihub_schema_owner IN SCHEMA salary_private
    REVOKE ALL ON FUNCTIONS FROM PUBLIC;

DO $$
DECLARE
    item RECORD;
BEGIN
    FOR item IN
        SELECT expected.function_name::REGPROCEDURE AS function_name,
               expected.grantee::REGROLE AS grantee
        FROM (VALUES
            ('public.advance_sales_generation_head(text,integer,uuid,uuid,bigint)', 'unihub_sales_import'),
            ('public.record_sales_generation_promotion(text,integer,integer,bigint,text,text,text)', 'unihub_sales_import'),
            ('public.reserve_sales_import_grile_run(text,integer)', 'unihub_sales_import'),
            ('public.advance_store_pnl_generation_head(text,date,uuid,bigint,text,text)', 'unihub_finance_import'),
            ('public.append_store_pnl_generation_ledger(uuid,text,text,date,jsonb)', 'unihub_finance_import'),
            ('public.seal_store_pnl_generation(uuid,text)', 'unihub_finance_import'),
            ('public.complete_store_pnl_generation(uuid,text)', 'unihub_finance_import'),
            ('public.seal_store_pnl_shadow_generation(uuid)', 'unihub_operations'),
            ('public.promote_store_pnl_shadow_generation(uuid,bigint)', 'unihub_operations'),
            ('public.rollback_store_pnl_shadow_pointer(bigint)', 'unihub_operations')
        ) AS expected(function_name, grantee)
    LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM pg_proc
            WHERE oid = item.function_name
              AND proowner = 'unihub_schema_owner'::regrole
              AND prosecdef
              AND proconfig = ARRAY['search_path=pg_catalog, public']
              AND EXISTS (
                  SELECT 1
                  FROM aclexplode(COALESCE(proacl, acldefault('f', proowner))) AS acl
                  WHERE acl.grantee = item.grantee
                    AND acl.privilege_type = 'EXECUTE'
                    AND NOT acl.is_grantable
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM aclexplode(COALESCE(proacl, acldefault('f', proowner))) AS acl
                  WHERE acl.privilege_type = 'EXECUTE'
                    AND acl.grantee NOT IN (proowner, item.grantee)
              )
        ) THEN
            RAISE EXCEPTION 'controlled definer function ownership or ACL mismatch: %', item.function_name;
        END IF;
    END LOOP;
END
$$;
