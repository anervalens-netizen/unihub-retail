CREATE TABLE grile_calendar_closures (
    month TEXT NOT NULL, work_date DATE NOT NULL, site_code TEXT NOT NULL REFERENCES stores(site_code),
    revision INTEGER NOT NULL CHECK (revision > 0), updated_by_sub TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (month, work_date, site_code), CHECK (month = to_char(work_date, 'YYYY-MM'))
);
GRANT SELECT ON grile_calendar_closures TO unihub_web_read;
GRANT SELECT, INSERT, UPDATE, DELETE ON grile_calendar_closures TO unihub_business_write;
