-- Native calendar only. No salary, Google or production data backfill.
CREATE TABLE grile_calendar_roster (
    month TEXT NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    agent_code TEXT NOT NULL CHECK (agent_code = btrim(agent_code) AND length(agent_code) BETWEEN 1 AND 80),
    home_site_code TEXT NOT NULL REFERENCES stores(site_code),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    revision INTEGER NOT NULL CHECK (revision > 0),
    updated_by_sub TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (month, agent_code)
);

CREATE TABLE grile_calendar_days (
    month TEXT NOT NULL,
    work_date DATE NOT NULL,
    agent_code TEXT NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code),
    status TEXT NOT NULL CHECK (status IN ('work', 'leave', 'off', 'cancelled')),
    supplemental BOOLEAN NOT NULL DEFAULT FALSE,
    revision INTEGER NOT NULL CHECK (revision > 0),
    updated_by_sub TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (agent_code, work_date),
    FOREIGN KEY (month, agent_code) REFERENCES grile_calendar_roster(month, agent_code),
    CHECK (month = to_char(work_date, 'YYYY-MM')),
    CHECK (NOT supplemental OR status = 'work')
);

CREATE UNIQUE INDEX grile_calendar_one_worker_per_store_day
    ON grile_calendar_days(site_code, work_date) WHERE status = 'work';
CREATE INDEX grile_calendar_days_month_site
    ON grile_calendar_days(month, site_code);

GRANT SELECT ON grile_calendar_roster, grile_calendar_days TO unihub_web_read;
GRANT SELECT, INSERT, UPDATE ON grile_calendar_roster, grile_calendar_days
    TO unihub_business_write;
