-- P1-A roll-forward: the authenticated web startup synchronizes the retained
-- FieldOps PostgreSQL source into visits_snapshot before becoming ready.
-- Keep the source SELECT-only and inside the explicit web-read authority.

DO $$
BEGIN
    -- FieldOps owns this table and provisions it before Retail in production.
    -- A fresh isolated Retail schema may intentionally omit the external
    -- source, so the migration must not manufacture or own a shadow table.
    IF to_regclass('public.fieldops_visits') IS NOT NULL THEN
        GRANT SELECT ON TABLE fieldops_visits TO unihub_web_read;
    END IF;
END
$$;
