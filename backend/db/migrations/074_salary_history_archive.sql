-- Historical evidence, never a replacement for approved salary_records.
CREATE TABLE salary_history_batches (
    manifest_sha256 TEXT PRIMARY KEY CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    row_count INTEGER NOT NULL CHECK (row_count > 0),
    applied_by TEXT NOT NULL CHECK (length(applied_by) BETWEEN 1 AND 200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE salary_history_rows (
    source_row_key TEXT PRIMARY KEY,
    batch_sha256 TEXT NOT NULL REFERENCES salary_history_batches(manifest_sha256),
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    period TEXT CHECK (period ~ '^(19|20)[0-9]{2}-(0[1-9]|1[0-2])$'),
    company_name TEXT CHECK (company_name IN ('Mobiup','Mobicell')),
    full_name TEXT NOT NULL,
    location TEXT,
    site_code TEXT,
    salary_amount NUMERIC(16,2),
    meal_vouchers NUMERIC(16,2),
    total_amount NUMERIC(16,2),
    candidate_person_id TEXT CHECK (candidate_person_id ~ '^sp1_[0-9a-f]{64}$'),
    identity_status TEXT NOT NULL,
    review_reasons TEXT[] NOT NULL DEFAULT '{}',
    selected BOOLEAN NOT NULL DEFAULT false,
    pnl_eligible BOOLEAN NOT NULL DEFAULT false,
    already_recorded BOOLEAN NOT NULL DEFAULT false,
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL CHECK (source_row > 0),
    CHECK (NOT pnl_eligible OR (selected AND period IS NOT NULL AND company_name IS NOT NULL AND total_amount IS NOT NULL)),
    CHECK (candidate_person_id IS NULL OR identity_status = 'verified_existing'),
    UNIQUE (source_sha256, source_sheet, source_row)
);
CREATE INDEX salary_history_period_idx ON salary_history_rows(period, company_name);
CREATE INDEX salary_history_person_idx ON salary_history_rows(candidate_person_id, period) WHERE candidate_person_id IS NOT NULL;
GRANT SELECT ON salary_history_batches, salary_history_rows TO unihub_web_read;
-- No grant to runtime writers. Loading evidence uses the migration principal.
-- Official company-month coverage dominates history, including partial old sources.
CREATE VIEW salary_history_estimation_inputs AS
SELECT h.* FROM salary_history_rows h
WHERE h.pnl_eligible AND h.selected AND NOT h.already_recorded
AND NOT EXISTS (
    SELECT 1 FROM salary_records s
    WHERE s.year = left(h.period, 4)::integer
      AND s.month = right(h.period, 2)::integer
      AND lower(s.company_name) = lower(h.company_name)
);
GRANT SELECT ON salary_history_estimation_inputs TO unihub_web_read;
COMMENT ON VIEW salary_history_estimation_inputs IS
'Historical net pay plus meal vouchers; partial coverage may remain. Not employer total cost, not official payroll, never add to official company-month totals.';
