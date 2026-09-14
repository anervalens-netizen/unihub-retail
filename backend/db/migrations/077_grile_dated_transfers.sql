-- Owner-approved effective-dated planning; POS activation is independent metadata.
CREATE TABLE grile_calendar_transfers (
    month TEXT NOT NULL,
    agent_code TEXT NOT NULL,
    effective_from DATE NOT NULL,
    home_site_code TEXT NOT NULL REFERENCES stores(site_code),
    location_code_active_from DATE,
    roster_revision INTEGER NOT NULL CHECK (roster_revision > 0),
    updated_by_sub TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (month, agent_code, roster_revision),
    FOREIGN KEY (month, agent_code) REFERENCES grile_calendar_roster(month, agent_code),
    CHECK (month = to_char(effective_from, 'YYYY-MM')),
    CHECK (location_code_active_from IS NULL OR location_code_active_from >= effective_from)
);
CREATE INDEX grile_transfers_effective ON grile_calendar_transfers(month, agent_code, effective_from);
GRANT SELECT ON grile_calendar_transfers TO unihub_web_read;
GRANT SELECT, INSERT ON grile_calendar_transfers TO unihub_business_write;
