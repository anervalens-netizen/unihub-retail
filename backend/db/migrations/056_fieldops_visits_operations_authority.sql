-- The operations worker owns the periodic FieldOps -> Retail projection refresh.
-- Keep the external source read-only and grant only the two writes used to
-- atomically replace the Retail-owned projection.

REVOKE ALL ON TABLE visits_snapshot FROM unihub_operations;
GRANT INSERT, DELETE ON TABLE visits_snapshot TO unihub_operations;

DO $$
DECLARE
    source_owner OID;
    has_direct_owner_select BOOLEAN;
BEGIN
    IF to_regclass('public.fieldops_visits') IS NULL THEN
        RETURN;
    END IF;

    SELECT relation.relowner
    INTO source_owner
    FROM pg_class AS relation
    WHERE relation.oid = 'public.fieldops_visits'::regclass;

    SELECT EXISTS (
        SELECT 1
        FROM pg_class AS relation
        CROSS JOIN LATERAL aclexplode(
            COALESCE(relation.relacl, acldefault('r', relation.relowner))
        ) AS acl
        WHERE relation.oid = 'public.fieldops_visits'::regclass
          AND acl.grantee = 'unihub_operations'::regrole
          AND acl.grantor = relation.relowner
          AND acl.privilege_type = 'SELECT'
          AND NOT acl.is_grantable
    ) INTO has_direct_owner_select;

    IF NOT has_direct_owner_select THEN
        IF current_user::regrole = source_owner
           AND has_table_privilege(
               current_user, 'public.fieldops_visits', 'SELECT WITH GRANT OPTION'
           ) THEN
            GRANT SELECT ON TABLE fieldops_visits TO unihub_operations;
        ELSE
            RAISE EXCEPTION
                'FieldOps owner must grant SELECT on public.fieldops_visits to unihub_operations before migration';
        END IF;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_class AS relation
        CROSS JOIN LATERAL aclexplode(
            COALESCE(relation.relacl, acldefault('r', relation.relowner))
        ) AS acl
        WHERE relation.oid = 'public.fieldops_visits'::regclass
          AND acl.grantee = 'unihub_operations'::regrole
          AND acl.grantor = relation.relowner
          AND acl.privilege_type = 'SELECT'
          AND NOT acl.is_grantable
    ) OR EXISTS (
        SELECT 1
        FROM pg_class AS relation
        CROSS JOIN LATERAL aclexplode(
            COALESCE(relation.relacl, acldefault('r', relation.relowner))
        ) AS acl
        WHERE relation.oid = 'public.fieldops_visits'::regclass
          AND acl.grantee = 'unihub_operations'::regrole
          AND (
              acl.grantor <> relation.relowner
              OR acl.privilege_type <> 'SELECT'
              OR acl.is_grantable
          )
    ) THEN
        RAISE EXCEPTION
            'unihub_operations must have exactly owner-issued non-grantable SELECT on public.fieldops_visits';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_attribute AS attribute
        CROSS JOIN LATERAL aclexplode(attribute.attacl) AS acl
        WHERE attribute.attrelid = 'public.fieldops_visits'::regclass
          AND attribute.attnum > 0
          AND NOT attribute.attisdropped
          AND acl.grantee = 'unihub_operations'::regrole
    ) THEN
        RAISE EXCEPTION
            'column privileges for unihub_operations are forbidden on public.fieldops_visits';
    END IF;

    IF has_table_privilege('unihub_operations', 'public.fieldops_visits', 'INSERT')
       OR has_table_privilege('unihub_operations', 'public.fieldops_visits', 'UPDATE')
       OR has_table_privilege('unihub_operations', 'public.fieldops_visits', 'DELETE')
       OR has_table_privilege('unihub_operations', 'public.fieldops_visits', 'TRUNCATE')
       OR has_table_privilege('unihub_operations', 'public.fieldops_visits', 'REFERENCES')
       OR has_table_privilege('unihub_operations', 'public.fieldops_visits', 'TRIGGER')
       OR has_any_column_privilege(
           'unihub_operations', 'public.fieldops_visits', 'INSERT'
       )
       OR has_any_column_privilege(
           'unihub_operations', 'public.fieldops_visits', 'UPDATE'
       )
       OR has_any_column_privilege(
           'unihub_operations', 'public.fieldops_visits', 'REFERENCES'
       ) THEN
        RAISE EXCEPTION
            'unihub_operations effective DML is forbidden on public.fieldops_visits';
    END IF;

    IF (SELECT rolcanlogin FROM pg_roles WHERE rolname = 'unihub_operations') THEN
        RAISE EXCEPTION 'unihub_operations must remain a NOLOGIN authority';
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT has_table_privilege(
        'unihub_operations', 'public.visits_snapshot', 'INSERT'
    ) OR NOT has_table_privilege(
        'unihub_operations', 'public.visits_snapshot', 'DELETE'
    ) OR has_table_privilege(
        'unihub_operations', 'public.visits_snapshot', 'SELECT'
    ) OR has_table_privilege(
        'unihub_operations', 'public.visits_snapshot', 'UPDATE'
    ) OR has_table_privilege(
        'unihub_operations', 'public.visits_snapshot', 'TRUNCATE'
    ) OR has_table_privilege(
        'unihub_operations', 'public.visits_snapshot', 'REFERENCES'
    ) OR has_table_privilege(
        'unihub_operations', 'public.visits_snapshot', 'TRIGGER'
    ) THEN
        RAISE EXCEPTION
            'unihub_operations must have exactly INSERT and DELETE on public.visits_snapshot';
    END IF;
END
$$;
