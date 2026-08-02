CREATE TABLE IF NOT EXISTS salary_import_batches (
    batch_id UUID PRIMARY KEY,
    year SMALLINT NOT NULL CHECK (year BETWEEN 2020 AND 2100),
    month SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    status TEXT NOT NULL CHECK (status IN ('applied', 'rolled_back')),
    manifest JSONB NOT NULL,
    manifest_sha256 TEXT NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    applied_by TEXT NOT NULL CHECK (char_length(btrim(applied_by)) BETWEEN 1 AND 256),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    rolled_back_at TIMESTAMPTZ
);

ALTER TABLE salary_records
    ADD COLUMN IF NOT EXISTS import_batch_id UUID REFERENCES salary_import_batches(batch_id),
    ADD COLUMN IF NOT EXISTS source_file TEXT,
    ADD COLUMN IF NOT EXISTS source_sheet TEXT,
    ADD COLUMN IF NOT EXISTS source_row INTEGER,
    ADD COLUMN IF NOT EXISTS source_sha256 TEXT;

ALTER TABLE salary_records
    DROP CONSTRAINT IF EXISTS salary_records_year_month_cnp_full_name_company_name_key,
    DROP CONSTRAINT IF EXISTS salary_records_source_row_check,
    DROP CONSTRAINT IF EXISTS salary_records_source_sha256_check,
    DROP CONSTRAINT IF EXISTS salary_records_source_provenance_check;

ALTER TABLE salary_records
    ADD CONSTRAINT salary_records_source_row_check CHECK (
        source_row IS NULL OR source_row > 0
    ),
    ADD CONSTRAINT salary_records_source_sha256_check CHECK (
        source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT salary_records_source_provenance_check CHECK (
        (import_batch_id IS NULL AND source_file IS NULL AND source_sheet IS NULL
            AND source_row IS NULL AND source_sha256 IS NULL)
        OR (import_batch_id IS NOT NULL AND source_file IS NOT NULL
            AND source_sheet IS NOT NULL AND source_row IS NOT NULL
            AND source_sha256 IS NOT NULL)
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_salary_records_batch_source_row
    ON salary_records (import_batch_id, source_sha256, source_sheet, source_row)
    WHERE import_batch_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_salary_records_person_month_company
    ON salary_records (year, month, company_name, person_id);

COMMENT ON TABLE salary_import_batches IS
    'Immutable applied HR batch manifests; live apply remains operator-gated by reconciliation.';
COMMENT ON INDEX uq_salary_records_batch_source_row IS
    'Raw salary identity is source-line provenance, not person-month uniqueness.';
