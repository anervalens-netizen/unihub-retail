CREATE SCHEMA IF NOT EXISTS salary_private;
REVOKE ALL ON SCHEMA salary_private FROM PUBLIC;

CREATE TABLE IF NOT EXISTS salary_private.people (
    person_id TEXT PRIMARY KEY,
    cnp TEXT,
    normalized_name TEXT NOT NULL,
    identity_source TEXT NOT NULL CHECK (identity_source IN ('cnp', 'name')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (person_id ~ '^sp1_[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_salary_private_people_cnp
    ON salary_private.people (BTRIM(cnp))
    WHERE NULLIF(BTRIM(cnp), '') IS NOT NULL;

ALTER TABLE salary_records
    ADD COLUMN IF NOT EXISTS person_id TEXT;

CREATE INDEX IF NOT EXISTS idx_salary_records_person_id
    ON salary_records (person_id, year DESC, month DESC);

ALTER TABLE agent_salary_links
    ADD COLUMN IF NOT EXISTS person_id TEXT;

CREATE INDEX IF NOT EXISTS idx_agent_salary_links_person_id
    ON agent_salary_links (person_id)
    WHERE person_id IS NOT NULL;
