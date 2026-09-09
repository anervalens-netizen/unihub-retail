-- Virtual TL bases belong to Grile only, never to the commercial stores catalog.
ALTER TABLE grile_calendar_roster ALTER COLUMN home_site_code DROP NOT NULL;
ALTER TABLE grile_calendar_roster ADD COLUMN regional TEXT;
ALTER TABLE grile_calendar_roster ADD CONSTRAINT grile_calendar_virtual_base_region
    CHECK (home_site_code IS NOT NULL OR NULLIF(btrim(regional), '') IS NOT NULL);

-- A TL absence has no physical store. Worked days must always retain one.
ALTER TABLE grile_calendar_days ALTER COLUMN site_code DROP NOT NULL;
ALTER TABLE grile_calendar_days ADD CONSTRAINT grile_calendar_virtual_absence
    CHECK (site_code IS NOT NULL OR status IN ('leave', 'off', 'cancelled'));
