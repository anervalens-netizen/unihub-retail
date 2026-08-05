ALTER TABLE salary_import_batches
    ADD COLUMN IF NOT EXISTS approval_artifact_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS reviewer_key_id TEXT;

ALTER TABLE salary_import_batches
    DROP CONSTRAINT IF EXISTS salary_import_batches_approval_artifact_sha256_check,
    DROP CONSTRAINT IF EXISTS salary_import_batches_reviewer_key_id_check;

ALTER TABLE salary_import_batches
    ADD CONSTRAINT salary_import_batches_approval_artifact_sha256_check CHECK (
        approval_artifact_sha256 IS NULL
        OR approval_artifact_sha256 ~ '^[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT salary_import_batches_reviewer_key_id_check CHECK (
        reviewer_key_id IS NULL
        OR char_length(btrim(reviewer_key_id)) BETWEEN 1 AND 128
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_salary_import_batches_approval_artifact
    ON salary_import_batches (approval_artifact_sha256)
    WHERE approval_artifact_sha256 IS NOT NULL;

COMMENT ON COLUMN salary_import_batches.approval_artifact_sha256 IS
    'One-time cryptographically signed reviewer approval consumed atomically with the salary batch.';
COMMENT ON COLUMN salary_import_batches.reviewer_key_id IS
    'Trusted public reviewer key identity used to verify the approval artifact.';
