CREATE TABLE IF NOT EXISTS store_org_assignments (
    id BIGSERIAL PRIMARY KEY,
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE CASCADE,
    regional TEXT NOT NULL,
    asm TEXT NOT NULL,
    valid_from_month TEXT NOT NULL CHECK (valid_from_month ~ '^[0-9]{4}-[0-9]{2}$'),
    valid_to_month TEXT CHECK (
        valid_to_month IS NULL
        OR (
            valid_to_month ~ '^[0-9]{4}-[0-9]{2}$'
            AND valid_to_month >= valid_from_month
        )
    ),
    is_current BOOLEAN NOT NULL DEFAULT false,
    source TEXT NOT NULL DEFAULT 'manual',
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_store_org_assignments_period
    ON store_org_assignments (site_code, valid_from_month, COALESCE(valid_to_month, '9999-12'));

CREATE UNIQUE INDEX IF NOT EXISTS uq_store_org_assignments_current
    ON store_org_assignments (site_code)
    WHERE is_current;

CREATE INDEX IF NOT EXISTS idx_store_org_assignments_lookup
    ON store_org_assignments (site_code, valid_from_month, valid_to_month);

CREATE INDEX IF NOT EXISTS idx_store_org_assignments_current_asm
    ON store_org_assignments (asm, regional)
    WHERE is_current;

-- Freeze the pre-reorg monthly org exactly as it appears in reporting.
-- One row = one site_code/month assignment before the official 2026-05 structure.
INSERT INTO store_org_assignments (
    site_code,
    regional,
    asm,
    valid_from_month,
    valid_to_month,
    is_current,
    source,
    note
)
SELECT
    h.site_code,
    h.regional,
    h.asm,
    h.import_month AS valid_from_month,
    h.import_month AS valid_to_month,
    false AS is_current,
    'reporting_agent_month' AS source,
    'Historical monthly assignment before the official 2026-05 reorg' AS note
FROM (
    SELECT DISTINCT
        import_month,
        site_code,
        regional,
        asm
    FROM reporting_agent_month
    WHERE import_month < '2026-05'
) h
ON CONFLICT DO NOTHING;

-- Official current org starts in 2026-05. In this structure RM/regional = ASM.
INSERT INTO store_org_assignments (
    site_code,
    regional,
    asm,
    valid_from_month,
    valid_to_month,
    is_current,
    source,
    note
)
SELECT
    s.site_code,
    s.asm AS regional,
    s.asm AS asm,
    '2026-05' AS valid_from_month,
    NULL AS valid_to_month,
    true AS is_current,
    'official_reorg_2026_05' AS source,
    'Current structure: the 6 active managers are both RM/regional and ASM' AS note
FROM stores s
WHERE s.is_active
ON CONFLICT DO NOTHING;

UPDATE store_org_assignments soa
SET regional = s.asm,
    asm = s.asm,
    valid_from_month = '2026-05',
    valid_to_month = NULL,
    source = 'official_reorg_2026_05',
    note = 'Current structure: the 6 active managers are both RM/regional and ASM',
    updated_at = now()
FROM stores s
WHERE soa.site_code = s.site_code
  AND soa.is_current
  AND s.is_active;

CREATE OR REPLACE VIEW v_retail_current_store_org AS
SELECT
    soa.site_code,
    s.locatie,
    s.firma,
    soa.regional,
    soa.asm,
    soa.valid_from_month,
    soa.valid_to_month,
    s.is_active,
    soa.source,
    soa.note
FROM store_org_assignments soa
JOIN stores s ON s.site_code = soa.site_code
WHERE soa.is_current;

CREATE OR REPLACE VIEW v_retail_historical_store_org AS
SELECT
    soa.site_code,
    s.locatie,
    s.firma,
    soa.regional,
    soa.asm,
    soa.valid_from_month,
    soa.valid_to_month,
    soa.is_current,
    soa.source,
    soa.note
FROM store_org_assignments soa
JOIN stores s ON s.site_code = soa.site_code;

CREATE OR REPLACE VIEW v_retail_agent_month_current_org AS
SELECT
    ram.import_month,
    ram.site_code,
    c.locatie,
    c.firma,
    c.regional,
    c.asm,
    ram.regional AS historical_regional,
    ram.asm AS historical_asm,
    ram.agent,
    ram.total_sales,
    ram.total_quantity,
    ram.focus_quantity,
    ram.receipt_count,
    ram.receipt_2plus_count,
    ram.receipt_1_count,
    ram.receipt_2_count,
    ram.receipt_3_count,
    ram.receipt_4plus_count,
    ram.working_days,
    c.valid_from_month AS current_org_from_month,
    'current_org'::TEXT AS org_mode
FROM reporting_agent_month ram
JOIN v_retail_current_store_org c ON c.site_code = ram.site_code;

CREATE OR REPLACE VIEW v_retail_agent_month_historical_org AS
SELECT
    ram.import_month,
    ram.site_code,
    ram.locatie,
    ram.firma,
    ram.regional,
    ram.asm,
    c.regional AS current_regional,
    c.asm AS current_asm,
    ram.agent,
    ram.total_sales,
    ram.total_quantity,
    ram.focus_quantity,
    ram.receipt_count,
    ram.receipt_2plus_count,
    ram.receipt_1_count,
    ram.receipt_2_count,
    ram.receipt_3_count,
    ram.receipt_4plus_count,
    ram.working_days,
    'historical_org'::TEXT AS org_mode
FROM reporting_agent_month ram
LEFT JOIN v_retail_current_store_org c ON c.site_code = ram.site_code;

CREATE OR REPLACE VIEW v_retail_store_month_current_org AS
SELECT
    ram.import_month,
    ram.site_code,
    c.locatie,
    c.firma,
    c.regional,
    c.asm,
    MAX(ram.regional) AS historical_regional,
    MAX(ram.asm) AS historical_asm,
    SUM(ram.total_sales) AS total_sales,
    SUM(ram.total_quantity) AS total_quantity,
    SUM(ram.focus_quantity) AS focus_quantity,
    SUM(ram.receipt_count) AS receipt_count,
    SUM(ram.receipt_2plus_count) AS receipt_2plus_count,
    COUNT(DISTINCT ram.agent) AS agent_count,
    MAX(ram.working_days) AS working_days,
    COALESCE(MAX(st.target_value), 0) AS target_value,
    CASE
        WHEN COALESCE(MAX(st.target_value), 0) > 0
            THEN ROUND(SUM(ram.total_sales) * 100.0 / MAX(st.target_value), 2)
        ELSE NULL
    END AS target_pct,
    c.valid_from_month AS current_org_from_month,
    'current_org'::TEXT AS org_mode
FROM reporting_agent_month ram
JOIN v_retail_current_store_org c ON c.site_code = ram.site_code
LEFT JOIN store_targets st
    ON st.site_code = ram.site_code
    AND st.import_month = ram.import_month
GROUP BY
    ram.import_month,
    ram.site_code,
    c.locatie,
    c.firma,
    c.regional,
    c.asm,
    c.valid_from_month;

CREATE OR REPLACE VIEW v_retail_store_month_historical_org AS
SELECT
    ram.import_month,
    ram.site_code,
    ram.locatie,
    ram.firma,
    ram.regional,
    ram.asm,
    c.regional AS current_regional,
    c.asm AS current_asm,
    SUM(ram.total_sales) AS total_sales,
    SUM(ram.total_quantity) AS total_quantity,
    SUM(ram.focus_quantity) AS focus_quantity,
    SUM(ram.receipt_count) AS receipt_count,
    SUM(ram.receipt_2plus_count) AS receipt_2plus_count,
    COUNT(DISTINCT ram.agent) AS agent_count,
    MAX(ram.working_days) AS working_days,
    COALESCE(MAX(st.target_value), 0) AS target_value,
    CASE
        WHEN COALESCE(MAX(st.target_value), 0) > 0
            THEN ROUND(SUM(ram.total_sales) * 100.0 / MAX(st.target_value), 2)
        ELSE NULL
    END AS target_pct,
    'historical_org'::TEXT AS org_mode
FROM reporting_agent_month ram
LEFT JOIN v_retail_current_store_org c ON c.site_code = ram.site_code
LEFT JOIN store_targets st
    ON st.site_code = ram.site_code
    AND st.import_month = ram.import_month
GROUP BY
    ram.import_month,
    ram.site_code,
    ram.locatie,
    ram.firma,
    ram.regional,
    ram.asm,
    c.regional,
    c.asm;

CREATE OR REPLACE VIEW v_retail_item_month_current_org AS
SELECT
    rim.import_month,
    rim.site_code,
    c.locatie,
    c.firma,
    c.regional,
    c.asm,
    rim.regional AS historical_regional,
    rim.asm AS historical_asm,
    rim.agent,
    rim.item_code,
    rim.item_name,
    rim.total_sales,
    rim.net_quantity,
    rim.positive_quantity,
    rim.return_quantity,
    rim.receipt_count,
    c.valid_from_month AS current_org_from_month,
    'current_org'::TEXT AS org_mode
FROM reporting_item_month rim
JOIN v_retail_current_store_org c ON c.site_code = rim.site_code;

CREATE OR REPLACE VIEW v_retail_item_month_historical_org AS
SELECT
    rim.import_month,
    rim.site_code,
    rim.locatie,
    rim.firma,
    rim.regional,
    rim.asm,
    c.regional AS current_regional,
    c.asm AS current_asm,
    rim.agent,
    rim.item_code,
    rim.item_name,
    rim.total_sales,
    rim.net_quantity,
    rim.positive_quantity,
    rim.return_quantity,
    rim.receipt_count,
    'historical_org'::TEXT AS org_mode
FROM reporting_item_month rim
LEFT JOIN v_retail_current_store_org c ON c.site_code = rim.site_code;

CREATE OR REPLACE VIEW v_retail_targets_current_org AS
SELECT
    st.import_month,
    st.site_code,
    c.locatie,
    c.firma,
    c.regional,
    c.asm,
    st.target_value,
    st.source_file,
    st.created_at,
    c.valid_from_month AS current_org_from_month,
    'current_org'::TEXT AS org_mode
FROM store_targets st
JOIN v_retail_current_store_org c ON c.site_code = st.site_code;

CREATE OR REPLACE VIEW v_retail_sales_current_org AS
SELECT
    st.id,
    st.import_month,
    st.sale_date,
    st.site_code,
    c.locatie,
    c.firma,
    c.regional,
    c.asm,
    st.agent,
    st.bon_nr,
    st.item_code,
    st.item_name,
    st.brand,
    st.category,
    st.subcategory,
    st.quantity,
    st.unit_price,
    st.total_value,
    st.is_cartela,
    st.is_return,
    st.snapshot_id,
    c.valid_from_month AS current_org_from_month,
    'current_org'::TEXT AS org_mode
FROM sales_transactions st
JOIN v_retail_current_store_org c ON c.site_code = st.site_code;

CREATE OR REPLACE VIEW v_retail_sales_historical_org AS
SELECT
    st.id,
    st.import_month,
    st.sale_date,
    st.site_code,
    s.locatie,
    s.firma,
    COALESCE(h.regional, s.regional) AS regional,
    COALESCE(h.asm, s.asm) AS asm,
    c.regional AS current_regional,
    c.asm AS current_asm,
    st.agent,
    st.bon_nr,
    st.item_code,
    st.item_name,
    st.brand,
    st.category,
    st.subcategory,
    st.quantity,
    st.unit_price,
    st.total_value,
    st.is_cartela,
    st.is_return,
    st.snapshot_id,
    h.source AS historical_assignment_source,
    'historical_org'::TEXT AS org_mode
FROM sales_transactions st
JOIN stores s ON s.site_code = st.site_code
LEFT JOIN store_org_assignments h
    ON h.site_code = st.site_code
    AND h.valid_from_month <= st.import_month
    AND (h.valid_to_month IS NULL OR h.valid_to_month >= st.import_month)
LEFT JOIN v_retail_current_store_org c ON c.site_code = st.site_code;
