-- V3 Lot 30: personal Saved Views.
--
-- One minimal owner-scoped model for the already-stable V3 URL context: module
-- (tab), period, section/subtab and the canonical bounded filters. Owner
-- identity is always the canonical OIDC `AuthClaims.sub` supplied by the API
-- layer; `saved_views` never stores a client-provided owner and never grants
-- any data access beyond the caller's own rows.
--
-- The v1 state contract is deliberately closed: no columns/sort/chart/layout
-- state, no sharing/publishing and no per-owner limit trigger beyond the
-- serialized API check. `schema_version = 1` is the only accepted version.

CREATE TABLE saved_views (
    id BIGSERIAL PRIMARY KEY,

    owner_subject TEXT NOT NULL
        CHECK (
            btrim(owner_subject) = owner_subject
            AND length(owner_subject) BETWEEN 1 AND 256
        ),

    module_id TEXT NOT NULL
        CHECK (module_id IN ('hub', 'focus', 'agents', 'management')),

    name TEXT NOT NULL
        CHECK (
            btrim(name) = name
            AND length(name) BETWEEN 1 AND 80
        ),

    state JSONB NOT NULL
        CHECK (jsonb_typeof(state) = 'object'),

    schema_version SMALLINT NOT NULL DEFAULT 1
        CHECK (schema_version = 1),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (state ? 'tab' AND state->>'tab' = module_id),
    CHECK (jsonb_typeof(state->'filters') = 'object')
);

-- Case-insensitive uniqueness is per owner: two owners may reuse a name.
CREATE UNIQUE INDEX uq_saved_views_owner_name_ci
    ON saved_views (owner_subject, lower(name));

-- Deterministic personal list ordering.
CREATE INDEX idx_saved_views_owner_updated
    ON saved_views (owner_subject, updated_at DESC, id DESC);

-- Explicit authority only: no implicit grant to PUBLIC or to any other
-- NOLOGIN authority. The web service identity is a member of both the read
-- and the business-write authority, so INSERT/UPDATE ... RETURNING resolves
-- its SELECT privilege through unihub_web_read.
REVOKE ALL ON TABLE saved_views FROM PUBLIC;
REVOKE ALL ON SEQUENCE saved_views_id_seq FROM PUBLIC;

GRANT SELECT ON TABLE saved_views TO unihub_web_read;
GRANT INSERT, UPDATE, DELETE ON TABLE saved_views TO unihub_business_write;
GRANT USAGE, SELECT ON SEQUENCE saved_views_id_seq TO unihub_business_write;
