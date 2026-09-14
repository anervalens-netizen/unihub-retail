-- Monthly owner-authorized manager targets. Legacy imports cannot overwrite these.
CREATE TABLE grile_agent_target_settings (
    month TEXT NOT NULL,
    agent_code TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('automatic','manual')),
    manual_target NUMERIC(12,2),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_by_sub TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (month,agent_code),
    FOREIGN KEY (month,agent_code) REFERENCES grile_calendar_roster(month,agent_code),
    CHECK ((mode='automatic' AND manual_target IS NULL) OR
           (mode='manual' AND manual_target IS NOT NULL AND manual_target > 0 AND manual_target <= 1000000))
);
CREATE TABLE grile_agent_target_events (
    month TEXT NOT NULL, agent_code TEXT NOT NULL, revision INTEGER NOT NULL,
    old_mode TEXT NOT NULL, old_target NUMERIC(12,2),
    new_mode TEXT NOT NULL, new_target NUMERIC(12,2),
    actor TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (month,agent_code,revision),
    FOREIGN KEY (month,agent_code) REFERENCES grile_agent_target_settings(month,agent_code)
);
GRANT SELECT ON grile_agent_target_settings, grile_agent_target_events TO unihub_web_read;
GRANT SELECT, INSERT, UPDATE ON grile_agent_target_settings TO unihub_business_write;
GRANT SELECT, INSERT ON grile_agent_target_events TO unihub_business_write;

-- One target contribution per physical home site, month and explicit agent code.
-- Transfers use their effective date, independently of POS code activation.
CREATE VIEW reporting_grile_agent_targets_v2 AS
WITH work AS (
    SELECT d.*, CASE WHEN t.roster_revision IS NOT NULL THEN t.home_site_code ELSE r.home_site_code END AS home_site
    FROM grile_calendar_days d
    JOIN grile_calendar_roster r USING (month,agent_code)
    LEFT JOIN LATERAL (
        SELECT home_site_code,roster_revision FROM grile_calendar_transfers t
        WHERE t.month=d.month AND t.agent_code=d.agent_code AND t.effective_from<=d.work_date
        ORDER BY t.effective_from DESC,t.roster_revision DESC LIMIT 1
    ) t ON true
    WHERE d.status='work'
), selling AS (
    SELECT month,site_code,COUNT(*) AS days FROM work GROUP BY month,site_code
), home_work AS (
    SELECT month,agent_code,site_code,COUNT(*) AS days FROM work
    WHERE site_code=home_site GROUP BY month,agent_code,site_code
), homes AS (
    SELECT month,agent_code,site_code FROM home_work
    UNION
    SELECT r.month,r.agent_code,r.home_site_code FROM grile_calendar_roster r
    WHERE r.home_site_code IS NOT NULL
      AND (EXISTS (SELECT 1 FROM grile_calendar_days d WHERE d.month=r.month AND d.agent_code=r.agent_code)
           OR EXISTS (SELECT 1 FROM grile_agent_target_settings c WHERE c.month=r.month AND c.agent_code=r.agent_code))
), basis AS (
    SELECT h.*,COALESCE(w.days,0) AS days,
        CASE WHEN COALESCE(w.days,0)=0 THEN 0::NUMERIC
             WHEN st.target_value>0 AND s.days>0 THEN st.target_value*w.days/s.days END AS automatic_target,
        COALESCE(c.mode,'automatic') AS mode,c.manual_target
    FROM homes h
    LEFT JOIN home_work w USING (month,agent_code,site_code)
    LEFT JOIN selling s USING (month,site_code)
    LEFT JOIN store_targets st ON st.import_month=h.month AND st.site_code=h.site_code
    LEFT JOIN grile_agent_target_settings c USING (month,agent_code)
), weighted AS (
    SELECT *,SUM(automatic_target) OVER (PARTITION BY month,agent_code) AS total_auto,
        SUM(days) OVER (PARTITION BY month,agent_code) AS total_days,
        ROW_NUMBER() OVER (PARTITION BY month,agent_code ORDER BY site_code) AS position
    FROM basis
)
SELECT month AS import_month,site_code,agent_code AS agent,automatic_target,mode,
    CASE WHEN mode='manual' THEN
        CASE WHEN total_auto>0 THEN manual_target*automatic_target/total_auto
             WHEN total_days>0 THEN manual_target*days/total_days
             WHEN position=1 THEN manual_target ELSE 0 END
        ELSE automatic_target END AS target_value
FROM weighted;

CREATE VIEW reporting_effective_agent_targets_v2 AS
SELECT import_month,site_code,agent,target_value FROM reporting_grile_agent_targets_v2
UNION ALL
SELECT a.import_month,a.site_code,a.agent,a.target_value FROM agent_targets a
WHERE NOT EXISTS (SELECT 1 FROM reporting_grile_agent_targets_v2 v
                  WHERE v.import_month=a.import_month AND v.site_code=a.site_code AND v.agent=a.agent);
GRANT SELECT ON reporting_grile_agent_targets_v2,reporting_effective_agent_targets_v2 TO unihub_web_read;
