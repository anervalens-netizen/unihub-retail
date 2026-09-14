-- A null dated home ends an allocation without deleting the agent or attendance.
ALTER TABLE grile_calendar_transfers ALTER COLUMN home_site_code DROP NOT NULL;
