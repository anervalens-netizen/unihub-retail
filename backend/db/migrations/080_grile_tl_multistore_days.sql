-- A shared TL account may cover several physical stores on the same date.
-- Ordinary agents retain one revision slot per date. TL revisions are per store.
ALTER TABLE grile_calendar_days ADD COLUMN allocation_site TEXT NOT NULL DEFAULT '';
UPDATE grile_calendar_days d
SET allocation_site = COALESCE(d.site_code, 'TL')
FROM grile_calendar_roster r
WHERE r.month = d.month AND r.agent_code = d.agent_code AND r.home_site_code IS NULL;
ALTER TABLE grile_calendar_days DROP CONSTRAINT grile_calendar_days_pkey;
ALTER TABLE grile_calendar_days ADD PRIMARY KEY (agent_code, work_date, allocation_site);

-- Derive the slot from confirmed membership, never from a caller-supplied flag.
CREATE FUNCTION grile_calendar_set_allocation_site() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    SELECT CASE WHEN r.home_site_code IS NULL THEN COALESCE(NEW.site_code, 'TL') ELSE '' END
    INTO NEW.allocation_site
    FROM grile_calendar_roster r
    WHERE r.month = NEW.month AND r.agent_code = NEW.agent_code
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Confirm monthly roster before scheduling' USING ERRCODE = '23503';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER grile_calendar_allocation_site
BEFORE INSERT OR UPDATE ON grile_calendar_days
FOR EACH ROW EXECUTE FUNCTION grile_calendar_set_allocation_site();
