-- Final manager values start blank and are completed by managers.
ALTER TABLE target_scenario_rows
    ALTER COLUMN final_target DROP NOT NULL,
    ALTER COLUMN final_target DROP DEFAULT;

UPDATE target_scenario_rows
SET final_target = NULL
WHERE final_target = proposed_target
  AND NULLIF(BTRIM(COALESCE(note, '')), '') IS NULL;
