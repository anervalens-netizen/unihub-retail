ALTER TABLE import_snapshots
    ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;

COMMENT ON COLUMN import_snapshots.finished_at IS
    'Momentul terminal al importurilor noi; NULL pentru istoricul fara masurare fiabila.';
