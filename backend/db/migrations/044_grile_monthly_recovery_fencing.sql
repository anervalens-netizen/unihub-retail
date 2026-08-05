ALTER TABLE grile_monthly_operations
    ADD COLUMN IF NOT EXISTS execution_epoch BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS execution_owner TEXT,
    ADD COLUMN IF NOT EXISTS execution_lease_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reconciliation_classification TEXT,
    ADD COLUMN IF NOT EXISTS reconciled_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS alerted_at TIMESTAMPTZ;

ALTER TABLE grile_monthly_reset_items
    ADD COLUMN IF NOT EXISTS checkpoint_phase TEXT NOT NULL DEFAULT 'legacy_unknown',
    ADD COLUMN IF NOT EXISTS fence_epoch BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS destructive_intent_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reconciled_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS recovery_code TEXT;

ALTER TABLE grile_monthly_operations
    ADD CONSTRAINT ck_grile_monthly_execution_epoch
        CHECK (execution_epoch >= 0) NOT VALID,
    ADD CONSTRAINT ck_grile_monthly_reconciliation_classification
        CHECK (
            reconciliation_classification IS NULL
            OR reconciliation_classification IN ('safe_retry', 'rolled_back', 'recovery_required')
        ) NOT VALID;

ALTER TABLE grile_monthly_reset_items
    ADD CONSTRAINT ck_grile_monthly_reset_checkpoint_phase
        CHECK (
            checkpoint_phase IN (
                'legacy_unknown', 'snapshot_persisted', 'clear_intent',
                'clear_verified', 'rollback_intent', 'rollback_verified',
                'recovery_required'
            )
        ) NOT VALID,
    ADD CONSTRAINT ck_grile_monthly_reset_fence_epoch
        CHECK (fence_epoch >= 0) NOT VALID;

CREATE INDEX IF NOT EXISTS idx_grile_monthly_operations_stale_running
    ON grile_monthly_operations (heartbeat_at)
    WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_grile_monthly_reset_recovery
    ON grile_monthly_reset_items (operation_id, status, checkpoint_phase);

-- Existing in-flight or uncertain items have no durable P1-D intent.  Keep
-- them visibly legacy and blocked; never infer that Google was untouched.
UPDATE grile_monthly_reset_items
SET checkpoint_phase = 'legacy_unknown',
    recovery_code = 'recovery_required',
    updated_at = now()
WHERE status IN ('running', 'uncertain', 'completed', 'error')
  AND checkpoint_phase = 'legacy_unknown';

UPDATE grile_monthly_operations AS operation
SET reconciliation_classification = 'recovery_required'
WHERE operation.status = 'running'
  AND EXISTS (
      SELECT 1
      FROM grile_monthly_reset_items item
      WHERE item.operation_id = operation.id
        AND item.recovery_code = 'recovery_required'
  );

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        GRANT SELECT, INSERT, UPDATE
            ON TABLE grile_monthly_operations, grile_monthly_reset_items
            TO unihub_runtime;
        GRANT USAGE, SELECT, UPDATE
            ON SEQUENCE grile_monthly_reset_items_id_seq
            TO unihub_runtime;
    END IF;
END
$$;
