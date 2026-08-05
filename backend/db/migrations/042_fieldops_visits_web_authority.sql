-- P1-A roll-forward: the authenticated web startup synchronizes the retained
-- FieldOps PostgreSQL source into visits_snapshot before becoming ready.
-- Keep the source SELECT-only and inside the explicit web-read authority.

DO $$
BEGIN
    -- FieldOps owns this table and provisions it before Retail in production.
    -- A fresh isolated Retail schema may intentionally omit the external
    -- source, so the migration must not manufacture or own a shadow table.
    IF to_regclass('public.fieldops_visits') IS NOT NULL
       AND NOT has_table_privilege(
           'unihub_web_read', 'public.fieldops_visits', 'SELECT'
       ) THEN
        -- The stable Retail schema owner may grant only when it owns the
        -- relation (or was explicitly delegated grant option).  A genuinely
        -- external FieldOps owner must hand off SELECT itself before retry;
        -- never capture ownership or require an administrative migration.
        IF has_table_privilege(
            current_user, 'public.fieldops_visits', 'SELECT WITH GRANT OPTION'
        ) THEN
            GRANT SELECT ON TABLE fieldops_visits TO unihub_web_read;
        ELSE
            RAISE EXCEPTION
                'FieldOps owner must grant SELECT on public.fieldops_visits to unihub_web_read before migration';
        END IF;
    END IF;
END
$$;
