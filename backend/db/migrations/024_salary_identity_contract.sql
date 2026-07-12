ALTER TABLE salary_records
    ALTER COLUMN person_id SET NOT NULL;

ALTER TABLE salary_records
    ADD CONSTRAINT salary_records_person_id_format
    CHECK (person_id ~ '^sp1_[0-9a-f]{64}$');

ALTER TABLE salary_records
    ADD CONSTRAINT salary_records_person_id_fkey
    FOREIGN KEY (person_id)
    REFERENCES salary_private.people(person_id)
    ON UPDATE RESTRICT
    ON DELETE RESTRICT;

ALTER TABLE agent_salary_links
    ADD CONSTRAINT agent_salary_links_person_id_format
    CHECK (person_id IS NULL OR person_id ~ '^sp1_[0-9a-f]{64}$');

ALTER TABLE agent_salary_links
    ADD CONSTRAINT agent_salary_links_person_id_fkey
    FOREIGN KEY (person_id)
    REFERENCES salary_private.people(person_id)
    ON UPDATE RESTRICT
    ON DELETE RESTRICT;

ALTER TABLE agent_salary_links
    ADD CONSTRAINT agent_salary_links_identity_state
    CHECK (
        (match_status = 'confirmed' AND person_id IS NOT NULL)
        OR (match_status = 'unknown' AND person_id IS NULL)
    );
