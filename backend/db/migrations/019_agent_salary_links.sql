CREATE TABLE IF NOT EXISTS agent_salary_links (
    agent_code TEXT NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE CASCADE,
    salary_full_name TEXT,
    salary_cnp TEXT,
    match_status TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (match_status IN ('confirmed', 'unknown')),
    match_source TEXT NOT NULL DEFAULT 'manual'
        CHECK (match_source IN ('auto', 'manual')),
    confidence TEXT NOT NULL DEFAULT 'high'
        CHECK (confidence IN ('high', 'medium', 'low', 'unknown')),
    effective_from_month TEXT CHECK (effective_from_month IS NULL OR effective_from_month ~ '^[0-9]{4}-[0-9]{2}$'),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (agent_code, site_code),
    CHECK (
        (match_status = 'unknown' AND salary_full_name IS NULL)
        OR (match_status = 'confirmed' AND salary_full_name IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_agent_salary_links_name
    ON agent_salary_links (LOWER(BTRIM(salary_full_name)))
    WHERE salary_full_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_agent_salary_links_cnp
    ON agent_salary_links (salary_cnp)
    WHERE salary_cnp IS NOT NULL;
