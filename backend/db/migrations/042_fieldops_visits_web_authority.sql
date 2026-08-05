-- P1-A roll-forward: the authenticated web startup synchronizes the retained
-- FieldOps PostgreSQL source into visits_snapshot before becoming ready.
-- Keep the source SELECT-only and inside the explicit web-read authority.

DO $$
DECLARE
    has_direct_owner_select BOOLEAN;
BEGIN
    -- FieldOps owns this table and provisions it before Retail in production.
    -- A fresh isolated Retail schema may intentionally omit the external
    -- source, so the migration must not manufacture or own a shadow table.
    IF to_regclass('public.fieldops_visits') IS NULL THEN
        RETURN;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM pg_class AS relation
        CROSS JOIN LATERAL aclexplode(
            COALESCE(relation.relacl, acldefault('r', relation.relowner))
        ) AS acl
        WHERE relation.oid = 'public.fieldops_visits'::regclass
          AND acl.grantee = 'unihub_web_read'::regrole
          AND acl.grantor = relation.relowner
          AND acl.privilege_type = 'SELECT'
          AND NOT acl.is_grantable
    ) INTO has_direct_owner_select;

    IF NOT has_direct_owner_select THEN
        -- The stable Retail schema owner may grant only when it owns the
        -- relation. A genuinely external FieldOps owner must hand off SELECT
        -- itself before retry; never capture ownership or require an
        -- administrative migration.
        IF has_table_privilege(
            current_user, 'public.fieldops_visits', 'SELECT WITH GRANT OPTION'
        ) AND current_user::regrole = (
            SELECT relowner
            FROM pg_class
            WHERE oid = 'public.fieldops_visits'::regclass
        ) THEN
            GRANT SELECT ON TABLE fieldops_visits TO unihub_web_read;
        ELSE
            RAISE EXCEPTION
                'FieldOps owner must grant SELECT on public.fieldops_visits to unihub_web_read before migration';
        END IF;
    END IF;

    -- Require one owner-issued, non-grantable SELECT ACL and nothing else on
    -- the web authority. Effective DML or PUBLIC grants are never tolerated.
    IF EXISTS (
        SELECT 1
        FROM pg_class AS relation
        CROSS JOIN LATERAL aclexplode(
            COALESCE(relation.relacl, acldefault('r', relation.relowner))
        ) AS acl
        WHERE relation.oid = 'public.fieldops_visits'::regclass
          AND acl.grantee = 'unihub_web_read'::regrole
          AND (
              acl.grantor <> relation.relowner
              OR acl.privilege_type <> 'SELECT'
              OR acl.is_grantable
          )
    ) THEN
        RAISE EXCEPTION
            'unihub_web_read must have exactly owner-issued non-grantable SELECT on public.fieldops_visits';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_class AS relation
        CROSS JOIN LATERAL aclexplode(
            COALESCE(relation.relacl, acldefault('r', relation.relowner))
        ) AS acl
        WHERE relation.oid = 'public.fieldops_visits'::regclass
          AND acl.grantee = 0
    ) THEN
        RAISE EXCEPTION
            'PUBLIC privileges are forbidden on public.fieldops_visits';
    END IF;

    IF has_table_privilege('unihub_web_read', 'public.fieldops_visits', 'INSERT')
       OR has_table_privilege('unihub_web_read', 'public.fieldops_visits', 'UPDATE')
       OR has_table_privilege('unihub_web_read', 'public.fieldops_visits', 'DELETE')
       OR has_table_privilege('unihub_web_read', 'public.fieldops_visits', 'TRUNCATE')
       OR has_table_privilege('unihub_web_read', 'public.fieldops_visits', 'REFERENCES')
       OR has_table_privilege('unihub_web_read', 'public.fieldops_visits', 'TRIGGER') THEN
        RAISE EXCEPTION
            'unihub_web_read effective DML is forbidden on public.fieldops_visits';
    END IF;
END
$$;
