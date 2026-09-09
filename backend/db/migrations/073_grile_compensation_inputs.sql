-- Provisional manager inputs, separate from official HR salary records.
CREATE TABLE grile_calendar_compensation (
    month TEXT NOT NULL,
    agent_code TEXT NOT NULL,
    salary_base NUMERIC(12,2) CHECK (salary_base BETWEEN 0 AND 1000000),
    vouchers NUMERIC(12,2) CHECK (vouchers BETWEEN 0 AND 1000000),
    sim_quantity INTEGER CHECK (sim_quantity BETWEEN 0 AND 100000),
    epay_under_50 INTEGER CHECK (epay_under_50 BETWEEN 0 AND 100000),
    epay_over_50 INTEGER CHECK (epay_over_50 BETWEEN 0 AND 100000),
    incentive NUMERIC(12,2) CHECK (incentive BETWEEN 0 AND 1000000),
    adjustment NUMERIC(12,2) CHECK (adjustment BETWEEN -1000000 AND 1000000),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_by_sub TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (month, agent_code),
    FOREIGN KEY (month, agent_code) REFERENCES grile_calendar_roster(month, agent_code)
);
GRANT SELECT ON grile_calendar_compensation TO unihub_web_read;
GRANT SELECT, INSERT, UPDATE ON grile_calendar_compensation TO unihub_business_write;
