CREATE TABLE IF NOT EXISTS grile_v2_sheet_exports (
    id                  BIGSERIAL PRIMARY KEY,
    run_month           TEXT NOT NULL,
    site_code           TEXT NOT NULL,
    file_id             TEXT NOT NULL,
    root_folder_id      TEXT,
    template_id         TEXT,
    index_id            TEXT,
    source_hash         TEXT,
    published_hash      TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    last_attempt_at     TIMESTAMPTZ,
    last_success_at     TIMESTAMPTZ,
    last_error_at       TIMESTAMPTZ,
    last_error_code     TEXT,
    last_error_message  TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_grile_v2_sheet_exports_month_site
        UNIQUE (run_month, site_code),
    CONSTRAINT uq_grile_v2_sheet_exports_file_id
        UNIQUE (file_id),
    CONSTRAINT fk_grile_v2_sheet_exports_site
        FOREIGN KEY (site_code) REFERENCES stores (site_code),
    CONSTRAINT ck_grile_v2_sheet_exports_month
        CHECK (run_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    CONSTRAINT ck_grile_v2_sheet_exports_status
        CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'blocked'))
);

CREATE INDEX IF NOT EXISTS idx_grile_v2_sheet_exports_pending
    ON grile_v2_sheet_exports (run_month, status, updated_at);

COMMENT ON TABLE grile_v2_sheet_exports IS
    'Durable per-month/store mapping and content-hash state for the Grile V2 pilot; no credentials.';

REVOKE ALL ON TABLE grile_v2_sheet_exports FROM PUBLIC;
REVOKE ALL ON SEQUENCE grile_v2_sheet_exports_id_seq FROM PUBLIC;
GRANT SELECT ON TABLE grile_v2_sheet_exports TO unihub_web_read, unihub_operations;
GRANT SELECT, INSERT, UPDATE ON TABLE grile_v2_sheet_exports TO unihub_operations;
GRANT USAGE, SELECT ON SEQUENCE grile_v2_sheet_exports_id_seq TO unihub_operations;
