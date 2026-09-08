-- Monthly opening hours; other calendar months remain unchanged.
CREATE TABLE grile_calendar_store_hours (
    month TEXT NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    site_code TEXT NOT NULL REFERENCES stores(site_code),
    opens TEXT NOT NULL CHECK (opens ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
    closes TEXT NOT NULL CHECK (closes ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
    break_minutes INTEGER NOT NULL CHECK (break_minutes BETWEEN 0 AND 720),
    revision INTEGER NOT NULL CHECK (revision > 0),
    updated_by_sub TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (month, site_code),
    CHECK (closes::time - opens::time > break_minutes * interval '1 minute')
);
GRANT SELECT ON grile_calendar_store_hours TO unihub_web_read;
GRANT SELECT, INSERT, UPDATE ON grile_calendar_store_hours TO unihub_business_write;
