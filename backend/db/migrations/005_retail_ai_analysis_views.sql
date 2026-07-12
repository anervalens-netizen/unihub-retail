-- Historical migration tombstone.
--
-- Production records this filename as applied, but the original SQL predates
-- the immutable H-02 manifest and is absent from every reachable Git object.
-- Migration 006 removed the views created by this historical step, while the
-- frozen schema_v2.sql contains the final post-006 state.
--
-- Fresh databases mark this file as incorporated by the frozen baseline.
-- Existing databases must already contain its schema_migrations row. If this
-- file is ever selected as pending, fail closed instead of pretending that a
-- reconstructed no-op is the original migration.
DO $$
BEGIN
    RAISE EXCEPTION 'historical migration 005 cannot be replayed';
END
$$;
