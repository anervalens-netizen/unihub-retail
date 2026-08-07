ALTER TABLE grile_store_status
    ADD COLUMN IF NOT EXISTS completion_algorithm_version SMALLINT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS completion_as_of DATE;

ALTER TABLE grile_store_observations
    ADD COLUMN IF NOT EXISTS completion_algorithm_version SMALLINT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS completion_as_of DATE;

ALTER TABLE grile_store_current_status
    ADD COLUMN IF NOT EXISTS completion_algorithm_version SMALLINT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS completion_as_of DATE;

ALTER TABLE grile_store_refreshes
    ADD COLUMN IF NOT EXISTS projection_applied BOOLEAN,
    ADD COLUMN IF NOT EXISTS error_code TEXT;

ALTER TABLE grile_store_refreshes
    DROP CONSTRAINT IF EXISTS grile_store_refreshes_status_check;
ALTER TABLE grile_store_refreshes
    ADD CONSTRAINT grile_store_refreshes_status_check
    CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled'));

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_grile_store_status_completion_algorithm'
          AND conrelid = 'grile_store_status'::regclass
    ) THEN
        ALTER TABLE grile_store_status
            ADD CONSTRAINT ck_grile_store_status_completion_algorithm
            CHECK (completion_algorithm_version >= 1) NOT VALID;
    END IF;
END
$$;
ALTER TABLE grile_store_status
    VALIDATE CONSTRAINT ck_grile_store_status_completion_algorithm;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_grile_observation_completion_algorithm'
          AND conrelid = 'grile_store_observations'::regclass
    ) THEN
        ALTER TABLE grile_store_observations
            ADD CONSTRAINT ck_grile_observation_completion_algorithm
            CHECK (completion_algorithm_version >= 1) NOT VALID;
    END IF;
END
$$;
ALTER TABLE grile_store_observations
    VALIDATE CONSTRAINT ck_grile_observation_completion_algorithm;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_grile_current_completion_algorithm'
          AND conrelid = 'grile_store_current_status'::regclass
    ) THEN
        ALTER TABLE grile_store_current_status
            ADD CONSTRAINT ck_grile_current_completion_algorithm
            CHECK (completion_algorithm_version >= 1) NOT VALID;
    END IF;
END
$$;
ALTER TABLE grile_store_current_status
    VALIDATE CONSTRAINT ck_grile_current_completion_algorithm;

CREATE INDEX IF NOT EXISTS idx_grile_store_refresh_heartbeat
    ON grile_store_refreshes (status, heartbeat_at)
    WHERE status IN ('queued', 'running');

COMMENT ON COLUMN grile_store_observations.completion_algorithm_version IS
    'Version of the deterministic completion-window algorithm. Version 2 evaluates the requested run month.';
COMMENT ON COLUMN grile_store_observations.completion_as_of IS
    'Business date used to derive the completion window.';
COMMENT ON COLUMN grile_store_refreshes.projection_applied IS
    'Whether the fenced observation won the current projection CAS.';
COMMENT ON COLUMN grile_store_refreshes.error_code IS
    'Finite machine-readable terminal error code; details remain in error_message.';
