ALTER TABLE grile_sheets
    ADD COLUMN IF NOT EXISTS template_version TEXT NOT NULL DEFAULT 'v2';

ALTER TABLE grile_sheets
    ADD COLUMN IF NOT EXISTS active_from_month TEXT;

ALTER TABLE grile_sheets
    ADD CONSTRAINT ck_grile_template_version
    CHECK (template_version IN ('v2', 'v3')) NOT VALID;

ALTER TABLE grile_sheets
    VALIDATE CONSTRAINT ck_grile_template_version;

ALTER TABLE grile_sheets
    ADD CONSTRAINT ck_grile_active_from_month
    CHECK (
        active_from_month IS NULL
        OR active_from_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
    ) NOT VALID;

ALTER TABLE grile_sheets
    VALIDATE CONSTRAINT ck_grile_active_from_month;

CREATE TABLE IF NOT EXISTS grile_store_current_status (
    run_month         TEXT NOT NULL
        CHECK (run_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    site_code         TEXT NOT NULL REFERENCES stores(site_code) ON DELETE CASCADE,
    source_run_id     INTEGER REFERENCES grile_runs(id) ON DELETE SET NULL,
    source            TEXT NOT NULL CHECK (source IN ('full', 'store')),
    completion_pct    NUMERIC(5,1),
    last_edit         TIMESTAMPTZ,
    grila_target      NUMERIC(12,2),
    grila_sales       NUMERIC(12,2),
    db_target         NUMERIC(12,2),
    db_sales_mtd      NUMERIC(12,2),
    db_max_sale_date  DATE,
    fill_status       TEXT,
    target_status     TEXT,
    sales_status      TEXT,
    tolerance         NUMERIC(12,2),
    error_code        TEXT,
    error_message     TEXT,
    raw_summary       JSONB,
    content_sha256    TEXT,
    checked_by_sub    TEXT,
    checked_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_month, site_code),
    CHECK (content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (
        checked_by_sub IS NULL
        OR char_length(btrim(checked_by_sub)) BETWEEN 1 AND 256
    )
);

CREATE INDEX IF NOT EXISTS idx_grile_store_current_checked
    ON grile_store_current_status (run_month, checked_at DESC);

INSERT INTO grile_store_current_status (
    run_month, site_code, source_run_id, source,
    completion_pct, last_edit, grila_target, grila_sales,
    db_target, db_sales_mtd, db_max_sale_date,
    fill_status, target_status, sales_status, tolerance,
    error_code, error_message, raw_summary, checked_at
)
SELECT DISTINCT ON (r.run_month, status.site_code)
    r.run_month, status.site_code, r.id, 'full',
    status.completion_pct, status.last_edit,
    status.grila_target, status.grila_sales,
    status.db_target, status.db_sales_mtd, status.db_max_sale_date,
    status.fill_status, status.target_status, status.sales_status,
    status.tolerance, status.error_code, status.error_message,
    status.raw_summary,
    COALESCE(r.finished_at, r.heartbeat_at, r.started_at, r.created_at)
FROM grile_store_status status
JOIN grile_runs r ON r.id = status.run_id
ORDER BY
    r.run_month,
    status.site_code,
    COALESCE(r.finished_at, r.heartbeat_at, r.started_at, r.created_at) DESC,
    r.id DESC
ON CONFLICT (run_month, site_code) DO NOTHING;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_runtime') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON TABLE grile_store_current_status TO unihub_runtime;
    END IF;
END
$$;

COMMENT ON COLUMN grile_sheets.template_version IS
    'v2 = standard two-agent layout; v3 = three-agent layout.';

COMMENT ON COLUMN grile_sheets.active_from_month IS
    'First YYYY-MM included in checks, closeout and agent target sync.';

COMMENT ON TABLE grile_store_current_status IS
    'Latest per-store Grile status; full runs remain immutable audit history.';
