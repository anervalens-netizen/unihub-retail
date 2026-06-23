CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Auth removed: drop legacy auth tables + FK columns on existing DBs
DROP TABLE IF EXISTS tl_store_assignments CASCADE;
ALTER TABLE IF EXISTS focus_products DROP COLUMN IF EXISTS added_by;
ALTER TABLE IF EXISTS import_snapshots DROP COLUMN IF EXISTS imported_by;
ALTER TABLE IF EXISTS error_logs DROP COLUMN IF EXISTS user_id;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE IF NOT EXISTS team_leaders (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    asm TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE IF EXISTS team_leaders
    ADD COLUMN IF NOT EXISTS asm TEXT;

CREATE TABLE IF NOT EXISTS stores (
    site_code TEXT PRIMARY KEY,
    locatie TEXT NOT NULL,
    firma TEXT NOT NULL,
    regional TEXT NOT NULL,
    asm TEXT NOT NULL,
    team_leader_id TEXT REFERENCES team_leaders(id) ON DELETE SET NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    first_seen_month TEXT NOT NULL,
    last_seen_month TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE IF EXISTS stores
    ADD COLUMN IF NOT EXISTS team_leader_id TEXT REFERENCES team_leaders(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_stores_team_leader_id
    ON stores (team_leader_id);

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

CREATE TABLE IF NOT EXISTS focus_products (
    item_code TEXT PRIMARY KEY,
    item_name TEXT,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS import_snapshots (
    id SERIAL PRIMARY KEY,
    import_month TEXT NOT NULL,
    filename TEXT NOT NULL,
    upload_date DATE NOT NULL DEFAULT CURRENT_DATE,
    is_month_final BOOLEAN NOT NULL DEFAULT false,
    rows_in_file INTEGER,
    rows_imported INTEGER,
    status TEXT NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    heartbeat_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_import_snapshots_month_processing
    ON import_snapshots (import_month)
    WHERE status = 'processing';

CREATE TABLE IF NOT EXISTS sales_transactions (
    id BIGSERIAL PRIMARY KEY,
    import_month TEXT NOT NULL,
    sale_date DATE NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code),
    bon_nr TEXT NOT NULL,
    item_code TEXT NOT NULL,
    item_name TEXT NOT NULL,
    brand TEXT,
    category TEXT,
    subcategory TEXT,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    total_value NUMERIC(10, 2) NOT NULL,
    agent TEXT NOT NULL,
    is_cartela BOOLEAN NOT NULL DEFAULT false,
    is_return BOOLEAN NOT NULL DEFAULT false,
    snapshot_id INTEGER NOT NULL REFERENCES import_snapshots(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS premium_glass_item_models (
    item_code TEXT NOT NULL,
    item_name TEXT NOT NULL,
    is_premium_glass BOOLEAN NOT NULL,
    model_key TEXT NOT NULL,
    model_label TEXT NOT NULL,
    PRIMARY KEY (item_code, model_key)
);

CREATE INDEX IF NOT EXISTS idx_premium_glass_item_models_item
    ON premium_glass_item_models (item_code);

CREATE INDEX IF NOT EXISTS idx_premium_glass_item_models_premium
    ON premium_glass_item_models (is_premium_glass);

TRUNCATE premium_glass_item_models;

WITH target_models(model_key, model_label, model_regex, exclude_regex) AS (
    VALUES
        ('iphone_15', 'iPhone 15', 'IPHONE 15', 'IPHONE 15 PRO|IPHONE 15 PLUS -'),
        ('iphone_15_pro', 'iPhone 15 Pro', 'IPHONE 15 PRO|15 PRO/', 'IPHONE 15 PRO MAX|15 PRO MAX'),
        ('iphone_15_pro_max', 'iPhone 15 Pro Max', 'IPHONE 15 PRO MAX|15 PRO MAX', NULL),
        ('iphone_16', 'iPhone 16', 'IPHONE 16|/16([[:space:]]|-|$)', 'IPHONE 16 PRO|16 PRO|IPHONE 15 PLUS/16 PLUS|IPHONE 16 PLUS -'),
        ('iphone_16_pro', 'iPhone 16 Pro', 'IPHONE 16 PRO|16 PRO/', 'IPHONE 16 PRO MAX|16 PRO MAX'),
        ('iphone_16_pro_max', 'iPhone 16 Pro Max', 'IPHONE 16 PRO MAX|16 PRO MAX', NULL),
        ('iphone_17', 'iPhone 17', 'IPHONE 17|PRO/17([[:space:]]|-|$)', 'IPHONE 17 PRO|IPHONE 17 AIR'),
        ('iphone_17_pro', 'iPhone 17 Pro', 'IPHONE 17 PRO|17 PRO/', 'IPHONE 17 PRO MAX|17 PRO MAX'),
        ('iphone_17_pro_max', 'iPhone 17 Pro Max', 'IPHONE 17 PRO MAX|17 PRO MAX', NULL),
        ('samsung_s26_ultra', 'Samsung S26 Ultra', 'SAMSUNG GALAXY S26 ULTRA|S26 ULTRA', NULL)
),
source_products AS (
    SELECT DISTINCT
        st.item_code,
        st.item_name,
        UPPER(COALESCE(st.item_name, '')) AS item_name_upper
    FROM sales_transactions st
    WHERE LOWER(TRIM(COALESCE(st.category, ''))) = 'folii sticla'
)
INSERT INTO premium_glass_item_models (
    item_code,
    item_name,
    is_premium_glass,
    model_key,
    model_label
)
SELECT DISTINCT ON (sp.item_code, tm.model_key)
    sp.item_code,
    sp.item_name,
    (sp.item_name_upper ~ '(SAPPHIRE|CERAMIC|CORNING)') AS is_premium_glass,
    tm.model_key,
    tm.model_label
FROM source_products sp
JOIN target_models tm
    ON sp.item_name_upper ~ tm.model_regex
   AND (tm.exclude_regex IS NULL OR sp.item_name_upper !~ tm.exclude_regex)
ORDER BY sp.item_code, tm.model_key, sp.item_name;

ANALYZE premium_glass_item_models;

CREATE OR REPLACE VIEW v_premium_glass_item_models AS
SELECT
    item_code,
    item_name,
    is_premium_glass,
    model_key,
    model_label
FROM premium_glass_item_models;

CREATE OR REPLACE VIEW v_premium_glass_products AS
SELECT
    item_code,
    MAX(item_name) AS item_name,
    BOOL_OR(is_premium_glass) AS is_premium_glass,
    ARRAY_AGG(DISTINCT model_key ORDER BY model_key) AS model_keys,
    ARRAY_AGG(DISTINCT model_label ORDER BY model_label) AS model_labels
FROM premium_glass_item_models
GROUP BY item_code;

CREATE TABLE IF NOT EXISTS store_targets (
    import_month TEXT NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code),
    target_value NUMERIC(12, 2) NOT NULL DEFAULT 0,
    source_file TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (import_month, site_code)
);

-- Target Calculator keeps editable planning scenarios separate from official targets.
CREATE TABLE IF NOT EXISTS target_scenarios (
    id SERIAL PRIMARY KEY,
    target_month TEXT NOT NULL,
    cohort_month TEXT NOT NULL,
    total_target NUMERIC(14, 2) NOT NULL,
    min_floor NUMERIC(12, 2) NOT NULL DEFAULT 0,
    previous_month_floor_pct NUMERIC(7, 4) NOT NULL DEFAULT 0.9,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'finalized')),
    revision INTEGER NOT NULL DEFAULT 1,
    calculation_method TEXT NOT NULL DEFAULT 'weighted_floor_forecast_v2',
    source_months JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalized_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_target_scenarios_month_created
    ON target_scenarios (target_month, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_target_scenarios_target_month
    ON target_scenarios (target_month);

CREATE TABLE IF NOT EXISTS target_scenario_rows (
    scenario_id INTEGER NOT NULL REFERENCES target_scenarios(id) ON DELETE CASCADE,
    site_code TEXT NOT NULL REFERENCES stores(site_code),
    locatie TEXT NOT NULL,
    firma TEXT NOT NULL,
    regional TEXT NOT NULL,
    asm TEXT NOT NULL,
    calculated_weight NUMERIC(16, 10) NOT NULL DEFAULT 0,
    floor_target NUMERIC(12, 2) NOT NULL DEFAULT 0,
    proposed_target NUMERIC(12, 2) NOT NULL DEFAULT 0,
    final_target NUMERIC(12, 2),
    is_floor_limited BOOLEAN NOT NULL DEFAULT false,
    history JSONB NOT NULL DEFAULT '[]'::jsonb,
    note TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scenario_id, site_code)
);

CREATE INDEX IF NOT EXISTS idx_target_scenario_rows_regional
    ON target_scenario_rows (scenario_id, regional);

CREATE TABLE IF NOT EXISTS agent_targets (
    import_month TEXT NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code),
    agent TEXT NOT NULL,
    target_value NUMERIC(12, 2) NOT NULL DEFAULT 0,
    source_agent_name TEXT,
    source_store_key TEXT,
    source_file TEXT,
    manager TEXT,
    match_method TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (import_month, site_code, agent)
);

CREATE INDEX IF NOT EXISTS idx_agent_targets_month_manager
    ON agent_targets (import_month, manager);

CREATE TABLE IF NOT EXISTS incentive_campaigns (
    id SERIAL PRIMARY KEY,
    month TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    subtitle TEXT,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS incentive_products (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES incentive_campaigns(id) ON DELETE CASCADE,
    item_code TEXT NOT NULL,
    item_name TEXT,
    reward_value NUMERIC(10, 2) NOT NULL,
    UNIQUE (campaign_id, item_code)
);

CREATE INDEX IF NOT EXISTS idx_incentive_products_campaign ON incentive_products(campaign_id);
CREATE INDEX IF NOT EXISTS idx_incentive_products_code ON incentive_products(item_code);

CREATE TABLE IF NOT EXISTS historical_annual_sales (
    site_code TEXT NOT NULL REFERENCES stores(site_code),
    year INTEGER NOT NULL,
    firma TEXT NOT NULL,
    total_value NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total_qty INTEGER NOT NULL DEFAULT 0,
    is_partial_year BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (site_code, year, firma)
);

CREATE TABLE IF NOT EXISTS visits (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    data_raport DATE,
    ora_trimitere TIME,
    firma TEXT,
    regional TEXT,
    asm TEXT,
    magazin TEXT,
    site_code TEXT REFERENCES stores(site_code) ON DELETE SET NULL,
    durata_vizita_ore NUMERIC(4, 2),
    curatenie BOOLEAN NOT NULL DEFAULT false,
    imagine BOOLEAN NOT NULL DEFAULT false,
    uniforma BOOLEAN NOT NULL DEFAULT false,
    afise BOOLEAN NOT NULL DEFAULT false,
    produse_promo BOOLEAN NOT NULL DEFAULT false,
    tpu NUMERIC(10, 2),
    sticla NUMERIC(10, 2),
    altele NUMERIC(10, 2),
    avizat BOOLEAN NOT NULL DEFAULT false,
    avize NUMERIC(10, 2),
    charisma NUMERIC(10, 2),
    casa NUMERIC(10, 2),
    incarcari_epay NUMERIC(10, 2),
    incarcari_charisma NUMERIC(10, 2),
    agent1_nume TEXT,
    agent1_perf NUMERIC(6, 2),
    agent1_doi_pe_bon NUMERIC(6, 2),
    agent1_focus NUMERIC(6, 2),
    agent1_analiza TEXT,
    agent1_plan TEXT,
    agent2_nume TEXT,
    agent2_perf NUMERIC(6, 2),
    agent2_doi_pe_bon NUMERIC(6, 2),
    agent2_focus NUMERIC(6, 2),
    agent2_analiza TEXT,
    agent2_plan TEXT,
    foto1 TEXT,
    foto2 TEXT,
    foto3 TEXT,
    foto4 TEXT,
    status TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted', 'approved', 'rejected')),
    completion_pct SMALLINT NOT NULL DEFAULT 0 CHECK (completion_pct BETWEEN 0 AND 100),
    tl TEXT,
    notes TEXT,
    source TEXT NOT NULL DEFAULT 'platform'
);

-- ============================================================
-- SALARII DB INTEGRATION
-- Source: C:\Users\andre\Desktop\Workspace\unihub\salarii_simplu.db (SQLite)
-- ============================================================

CREATE TABLE IF NOT EXISTS salary_records (
    id SERIAL PRIMARY KEY,
    year SMALLINT NOT NULL CHECK (year BETWEEN 2020 AND 2100),
    month SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    full_name TEXT NOT NULL,
    cnp TEXT,
    total_salary NUMERIC(12, 2) NOT NULL DEFAULT 0,
    company_name TEXT NOT NULL CHECK (company_name IN ('Mobicell', 'Mobiup')),
    site_code TEXT REFERENCES stores(site_code) ON DELETE SET NULL,
    locatie TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (year, month, cnp, full_name, company_name)
);

-- Ensure FK exists on salary_records.site_code for existing databases (idempotent migration)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'salary_records_site_code_fkey'
          AND conrelid = 'salary_records'::regclass
    ) THEN
        -- Nullify any site_code values that don't exist in stores (e.g. pseudo-codes like 'TL')
        UPDATE salary_records
        SET site_code = NULL
        WHERE site_code IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM stores WHERE site_code = salary_records.site_code);

        ALTER TABLE salary_records
            ADD CONSTRAINT salary_records_site_code_fkey
            FOREIGN KEY (site_code) REFERENCES stores(site_code) ON DELETE SET NULL;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_salary_records_year_month ON salary_records (year, month);
CREATE INDEX IF NOT EXISTS idx_salary_records_company ON salary_records (company_name);
CREATE INDEX IF NOT EXISTS idx_salary_records_site_code ON salary_records (site_code);
CREATE INDEX IF NOT EXISTS idx_salary_records_cnp ON salary_records (cnp) WHERE cnp IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sales_month_site
    ON sales_transactions (import_month, site_code)
    WHERE is_cartela = false;

CREATE INDEX IF NOT EXISTS idx_sales_month_agent
    ON sales_transactions (import_month, agent)
    WHERE is_cartela = false;

CREATE INDEX IF NOT EXISTS idx_sales_item
    ON sales_transactions (item_code)
    WHERE is_cartela = false;

CREATE INDEX IF NOT EXISTS idx_sales_brand
    ON sales_transactions (brand)
    WHERE is_cartela = false;

CREATE INDEX IF NOT EXISTS idx_sales_date
    ON sales_transactions (sale_date);

CREATE INDEX IF NOT EXISTS idx_sales_snapshot
    ON sales_transactions (snapshot_id);

CREATE INDEX IF NOT EXISTS idx_sales_transactions_month_cartela
    ON sales_transactions (import_month)
    WHERE is_cartela = false;

CREATE INDEX IF NOT EXISTS idx_visits_site_date
    ON visits (site_code, data_raport);

CREATE INDEX IF NOT EXISTS idx_visits_asm_date
    ON visits (asm, data_raport);

CREATE INDEX IF NOT EXISTS idx_visits_status
    ON visits (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_targets_month
    ON store_targets (import_month);

CREATE TABLE IF NOT EXISTS reporting_agent_day (
    import_month TEXT NOT NULL,
    sale_date DATE NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE CASCADE,
    locatie TEXT NOT NULL,
    firma TEXT NOT NULL,
    regional TEXT NOT NULL,
    asm TEXT NOT NULL,
    agent TEXT NOT NULL,
    total_sales NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_quantity INTEGER NOT NULL DEFAULT 0,
    focus_quantity INTEGER NOT NULL DEFAULT 0,
    receipt_count INTEGER NOT NULL DEFAULT 0,
    receipt_2plus_count INTEGER NOT NULL DEFAULT 0,
    receipt_1_count INTEGER NOT NULL DEFAULT 0,
    receipt_2_count INTEGER NOT NULL DEFAULT 0,
    receipt_3_count INTEGER NOT NULL DEFAULT 0,
    receipt_4plus_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (import_month, sale_date, site_code, agent)
);

CREATE TABLE IF NOT EXISTS reporting_agent_month (
    import_month TEXT NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE CASCADE,
    locatie TEXT NOT NULL,
    firma TEXT NOT NULL,
    regional TEXT NOT NULL,
    asm TEXT NOT NULL,
    agent TEXT NOT NULL,
    total_sales NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_quantity INTEGER NOT NULL DEFAULT 0,
    focus_quantity INTEGER NOT NULL DEFAULT 0,
    receipt_count INTEGER NOT NULL DEFAULT 0,
    receipt_2plus_count INTEGER NOT NULL DEFAULT 0,
    receipt_1_count INTEGER NOT NULL DEFAULT 0,
    receipt_2_count INTEGER NOT NULL DEFAULT 0,
    receipt_3_count INTEGER NOT NULL DEFAULT 0,
    receipt_4plus_count INTEGER NOT NULL DEFAULT 0,
    working_days INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (import_month, site_code, agent)
);

CREATE TABLE IF NOT EXISTS reporting_agent_lifecycle_month (
    import_month TEXT NOT NULL,
    agent TEXT NOT NULL,
    total_sales NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_quantity INTEGER NOT NULL DEFAULT 0,
    receipt_count INTEGER NOT NULL DEFAULT 0,
    working_days INTEGER NOT NULL DEFAULT 0,
    active_store_count INTEGER NOT NULL DEFAULT 0,
    active_firma_count INTEGER NOT NULL DEFAULT 0,
    active_regional_count INTEGER NOT NULL DEFAULT 0,
    active_asm_count INTEGER NOT NULL DEFAULT 0,
    first_seen_month TEXT NOT NULL,
    prev_active_month TEXT,
    gap_since_prev_active_months INTEGER NOT NULL DEFAULT 0,
    is_new BOOLEAN NOT NULL DEFAULT false,
    is_reactivated BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true,
    PRIMARY KEY (import_month, agent)
);

CREATE TABLE IF NOT EXISTS reporting_agent_profile (
    agent TEXT PRIMARY KEY,
    first_seen_month TEXT NOT NULL,
    last_seen_month TEXT NOT NULL,
    active_months_count INTEGER NOT NULL DEFAULT 0,
    distinct_store_count INTEGER NOT NULL DEFAULT 0,
    distinct_firma_count INTEGER NOT NULL DEFAULT 0,
    distinct_regional_count INTEGER NOT NULL DEFAULT 0,
    distinct_asm_count INTEGER NOT NULL DEFAULT 0,
    months_since_last_seen INTEGER NOT NULL DEFAULT 0,
    reactivation_count INTEGER NOT NULL DEFAULT 0,
    longest_active_streak INTEGER NOT NULL DEFAULT 0,
    career_total_sales NUMERIC(12, 2) NOT NULL DEFAULT 0,
    career_total_quantity INTEGER NOT NULL DEFAULT 0,
    avg_monthly_sales NUMERIC(12, 2) NOT NULL DEFAULT 0,
    best_month TEXT,
    best_month_sales NUMERIC(12, 2) NOT NULL DEFAULT 0,
    current_status TEXT NOT NULL DEFAULT 'active'
        CHECK (current_status IN ('active', 'inactive_recent', 'churned'))
);

CREATE TABLE IF NOT EXISTS reporting_item_day (
    import_month TEXT NOT NULL,
    sale_date DATE NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE CASCADE,
    locatie TEXT NOT NULL,
    firma TEXT NOT NULL,
    regional TEXT NOT NULL,
    asm TEXT NOT NULL,
    agent TEXT NOT NULL,
    item_code TEXT NOT NULL,
    item_name TEXT NOT NULL,
    total_sales NUMERIC(12, 2) NOT NULL DEFAULT 0,
    net_quantity INTEGER NOT NULL DEFAULT 0,
    positive_quantity INTEGER NOT NULL DEFAULT 0,
    return_quantity INTEGER NOT NULL DEFAULT 0,
    receipt_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (import_month, sale_date, site_code, agent, item_code)
);

CREATE TABLE IF NOT EXISTS reporting_item_month (
    import_month TEXT NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE CASCADE,
    locatie TEXT NOT NULL,
    firma TEXT NOT NULL,
    regional TEXT NOT NULL,
    asm TEXT NOT NULL,
    agent TEXT NOT NULL,
    item_code TEXT NOT NULL,
    item_name TEXT NOT NULL,
    total_sales NUMERIC(12, 2) NOT NULL DEFAULT 0,
    net_quantity INTEGER NOT NULL DEFAULT 0,
    positive_quantity INTEGER NOT NULL DEFAULT 0,
    return_quantity INTEGER NOT NULL DEFAULT 0,
    receipt_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (import_month, site_code, agent, item_code)
);

CREATE TABLE IF NOT EXISTS reporting_focus_item_month (
    import_month TEXT NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE CASCADE,
    locatie TEXT NOT NULL,
    firma TEXT NOT NULL,
    regional TEXT NOT NULL,
    asm TEXT NOT NULL,
    agent TEXT NOT NULL,
    item_code TEXT NOT NULL,
    item_name TEXT NOT NULL,
    focus_subcategory TEXT NOT NULL,
    total_sales NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (import_month, site_code, agent, item_code)
);

CREATE TABLE IF NOT EXISTS reporting_category_month (
    import_month TEXT NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE CASCADE,
    locatie TEXT NOT NULL,
    firma TEXT NOT NULL,
    regional TEXT NOT NULL,
    asm TEXT NOT NULL,
    agent TEXT NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT NOT NULL,
    brand_group TEXT NOT NULL,
    total_sales NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (import_month, site_code, agent, category, subcategory, brand_group)
);

CREATE INDEX IF NOT EXISTS idx_reporting_agent_day_month
    ON reporting_agent_day (import_month);

CREATE INDEX IF NOT EXISTS idx_reporting_agent_day_month_site
    ON reporting_agent_day (import_month, site_code);

CREATE INDEX IF NOT EXISTS idx_reporting_agent_day_month_agent
    ON reporting_agent_day (import_month, agent);

CREATE INDEX IF NOT EXISTS idx_reporting_agent_month_month
    ON reporting_agent_month (import_month);

CREATE INDEX IF NOT EXISTS idx_reporting_agent_month_month_site
    ON reporting_agent_month (import_month, site_code);

CREATE INDEX IF NOT EXISTS idx_reporting_agent_month_month_agent
    ON reporting_agent_month (import_month, agent);

CREATE INDEX IF NOT EXISTS idx_reporting_agent_lifecycle_month_month
    ON reporting_agent_lifecycle_month (import_month);

CREATE INDEX IF NOT EXISTS idx_reporting_agent_lifecycle_month_agent
    ON reporting_agent_lifecycle_month (agent);

CREATE INDEX IF NOT EXISTS idx_reporting_agent_profile_status
    ON reporting_agent_profile (current_status, last_seen_month);

CREATE INDEX IF NOT EXISTS idx_reporting_item_day_month
    ON reporting_item_day (import_month);

CREATE INDEX IF NOT EXISTS idx_reporting_item_day_month_item_date
    ON reporting_item_day (import_month, item_code, sale_date);

CREATE INDEX IF NOT EXISTS idx_reporting_item_day_month_site
    ON reporting_item_day (import_month, site_code);

CREATE INDEX IF NOT EXISTS idx_reporting_item_day_month_agent
    ON reporting_item_day (import_month, agent);

CREATE INDEX IF NOT EXISTS idx_reporting_item_month_month
    ON reporting_item_month (import_month);

CREATE INDEX IF NOT EXISTS idx_reporting_item_month_month_item
    ON reporting_item_month (import_month, item_code);

CREATE INDEX IF NOT EXISTS idx_reporting_item_month_month_site
    ON reporting_item_month (import_month, site_code);

CREATE INDEX IF NOT EXISTS idx_reporting_item_month_month_agent
    ON reporting_item_month (import_month, agent);

CREATE INDEX IF NOT EXISTS idx_reporting_focus_item_month_month
    ON reporting_focus_item_month (import_month);

CREATE INDEX IF NOT EXISTS idx_reporting_focus_item_month_subcategory
    ON reporting_focus_item_month (import_month, focus_subcategory);

CREATE INDEX IF NOT EXISTS idx_reporting_category_month_month
    ON reporting_category_month (import_month);

CREATE INDEX IF NOT EXISTS idx_reporting_category_month_category
    ON reporting_category_month (import_month, category);

CREATE INDEX IF NOT EXISTS idx_reporting_category_month_brand_group
    ON reporting_category_month (import_month, brand_group);

CREATE OR REPLACE VIEW v_agent_monthly AS
WITH bon_agg AS (
    SELECT
        import_month,
        agent,
        site_code,
        bon_nr,
        SUM(quantity) AS qty_net
    FROM sales_transactions
    WHERE NOT is_cartela
    GROUP BY import_month, agent, site_code, bon_nr
)
SELECT
    st.import_month,
    st.agent,
    s.site_code,
    s.locatie,
    s.firma,
    s.regional,
    s.asm,
    SUM(st.quantity) FILTER (WHERE NOT st.is_return AND st.quantity > 0) AS acc_qty_realizat,
    COUNT(DISTINCT st.bon_nr) AS nr_bonuri,
    COUNT(DISTINCT ba.bon_nr) FILTER (WHERE ba.qty_net >= 2) AS nr_bon2acc,
    ROUND(
        COUNT(DISTINCT ba.bon_nr) FILTER (WHERE ba.qty_net >= 2) * 100.0
        / NULLIF(COUNT(DISTINCT st.bon_nr), 0),
        2
    ) AS proc_bon2acc,
    SUM(st.total_value) AS total_vanzari,
    COUNT(DISTINCT st.sale_date) AS zile_lucrate,
    ROUND(SUM(st.total_value) / NULLIF(COUNT(DISTINCT st.sale_date), 0), 2) AS medie_zilnica,
    COALESCE(
        SUM(st.quantity) FILTER (WHERE fp.item_code IS NOT NULL AND st.quantity > 0),
        0
    ) AS acc_focus_qty,
    ROUND(
        COALESCE(SUM(st.quantity) FILTER (WHERE fp.item_code IS NOT NULL AND st.quantity > 0), 0) * 100.0
        / NULLIF(SUM(st.quantity) FILTER (WHERE st.quantity > 0), 0),
        2
    ) AS prc_focus_acc_qty
FROM sales_transactions st
JOIN stores s ON s.site_code = st.site_code
LEFT JOIN focus_products fp ON fp.item_code = st.item_code
LEFT JOIN bon_agg ba
    ON ba.bon_nr = st.bon_nr
    AND ba.import_month = st.import_month
    AND ba.agent = st.agent
    AND ba.site_code = st.site_code
WHERE NOT st.is_cartela
GROUP BY st.import_month, st.agent, s.site_code, s.locatie, s.firma, s.regional, s.asm;

CREATE OR REPLACE VIEW v_store_monthly AS
SELECT
    st.import_month,
    s.site_code,
    s.locatie,
    s.firma,
    s.regional,
    s.asm,
    SUM(st.total_value) AS total_vanzari,
    SUM(st.quantity) FILTER (WHERE NOT st.is_return) AS qty_total,
    COUNT(DISTINCT st.bon_nr) AS nr_bonuri,
    COUNT(DISTINCT st.agent) AS nr_agenti,
    COUNT(DISTINCT st.sale_date) AS zile_active,
    COALESCE(t.target_value, 0) AS target,
    CASE
        WHEN COALESCE(t.target_value, 0) > 0 THEN ROUND(SUM(st.total_value) * 100.0 / t.target_value, 2)
        ELSE NULL
    END AS proc_realizare_target
FROM sales_transactions st
JOIN stores s ON s.site_code = st.site_code
LEFT JOIN store_targets t ON t.site_code = st.site_code AND t.import_month = st.import_month
WHERE NOT st.is_cartela
GROUP BY st.import_month, s.site_code, s.locatie, s.firma, s.regional, s.asm, t.target_value;

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

CREATE OR REPLACE VIEW v_cartele_monthly AS
SELECT
    import_month,
    site_code,
    agent,
    item_code,
    item_name,
    SUM(quantity) AS qty_total,
    COUNT(DISTINCT bon_nr) AS nr_bonuri
FROM sales_transactions
WHERE is_cartela = true
GROUP BY import_month, site_code, agent, item_code, item_name;

CREATE OR REPLACE FUNCTION replace_month_snapshot(p_month TEXT)
RETURNS void AS $$
DECLARE
    v_old_snapshot_id INTEGER;
BEGIN
    SELECT id INTO v_old_snapshot_id
    FROM import_snapshots
    WHERE import_month = p_month AND status = 'completed'
    ORDER BY created_at DESC
    LIMIT 1;

    IF v_old_snapshot_id IS NOT NULL THEN
        DELETE FROM sales_transactions WHERE snapshot_id = v_old_snapshot_id;
        DELETE FROM import_snapshots WHERE id = v_old_snapshot_id;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- VIEW-URI COMPATIBILITATE PLATFORMA-MOBIUP
-- Permit Platforma-Mobiup sa citeasca din PostgreSQL UniHub
-- in loc de SQLite-ul propriu, eliminand dubla import zilnic.
-- ============================================================

CREATE OR REPLACE VIEW v_platforma_dashboard AS
SELECT
    ram.import_month,
    s.firma,
    s.regional,
    s.asm,
    ram.site_code,
    s.locatie,
    ram.agent,
    ram.receipt_count                                           AS transactions_count,
    ram.total_quantity,
    ram.total_sales,
    ram.working_days,
    CASE WHEN ram.working_days > 0
         THEN ROUND(ram.total_sales / ram.working_days, 2)
         ELSE 0 END                                             AS avg_daily_sales,
    ram.total_quantity                                          AS acc_qty_realizat,
    ram.receipt_count                                           AS nr_bonuri,
    ram.receipt_2plus_count                                     AS nr_bon2acc,
    CASE WHEN ram.receipt_count > 0
         THEN ROUND(ram.receipt_2plus_count * 100.0 / ram.receipt_count, 2)
         ELSE 0 END                                             AS proc_bon2acc,
    ram.focus_quantity                                          AS acc_focus_qty,
    CASE WHEN ram.total_quantity > 0
         THEN ROUND(ram.focus_quantity * 100.0 / ram.total_quantity, 2)
         ELSE 0 END                                             AS prc_focus_acc_qty
FROM reporting_agent_month ram
JOIN stores s ON s.site_code = ram.site_code;

CREATE OR REPLACE VIEW v_platforma_import_meta AS
SELECT
    last_snap.import_month,
    TO_CHAR(
        DATE_TRUNC('month', (last_snap.import_month || '-01')::date),
        'YYYY-MM-DD'
    )                                                           AS period_start,
    CASE WHEN last_snap.is_month_final THEN
        TO_CHAR(
            DATE_TRUNC('month', (last_snap.import_month || '-01')::date)
            + INTERVAL '1 month - 1 day',
            'YYYY-MM-DD'
        )
    ELSE
        TO_CHAR(
            (SELECT MAX(st.sale_date)
             FROM sales_transactions st
             WHERE st.import_month = last_snap.import_month),
            'YYYY-MM-DD'
        )
    END                                                         AS period_end,
    CASE WHEN last_snap.is_month_final THEN 0 ELSE 1 END       AS is_partial,
    CASE WHEN last_snap.is_month_final
         THEN last_snap.import_month || ' (final)'
         ELSE last_snap.import_month || ' (intermediar)'
    END                                                         AS label,
    last_snap.created_at::text                                  AS updated_at
FROM (
    SELECT DISTINCT ON (import_month)
        import_month, is_month_final, created_at
    FROM import_snapshots
    WHERE status = 'completed'
    ORDER BY import_month, created_at DESC
) last_snap;

CREATE OR REPLACE VIEW v_platforma_raw_sales AS
SELECT
    st.id,
    st.import_month,
    st.sale_date::text          AS sale_date,
    st.site_code,
    s.locatie,
    s.firma,
    s.regional,
    s.asm,
    st.agent,
    st.bon_nr                   AS nr,
    st.item_code,
    st.item_name,
    st.category,
    st.subcategory,
    st.brand,
    st.quantity,
    st.unit_price,
    st.total_value,
    st.is_cartela,
    st.is_return
FROM sales_transactions st
JOIN stores s ON s.site_code = st.site_code;

CREATE OR REPLACE VIEW v_platforma_store_targets AS
SELECT
    st.import_month,
    st.site_code,
    s.regional,
    s.asm,
    s.firma,
    s.locatie,
    st.target_value
FROM store_targets st
JOIN stores s ON s.site_code = st.site_code;

-- =====================================================================
-- MANAGEMENT: Tasks
-- =====================================================================
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    assignee TEXT,
    site_code TEXT,
    deadline DATE,
    status TEXT NOT NULL DEFAULT 'deschis',
    source TEXT NOT NULL DEFAULT 'manual',
    source_meta JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- =====================================================================
-- MANAGEMENT: HR — Concedii
-- =====================================================================
CREATE TABLE IF NOT EXISTS leave_requests (
    id SERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    leave_type TEXT NOT NULL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- =====================================================================
-- MANAGEMENT: HR — Pontaj
-- =====================================================================
CREATE TABLE IF NOT EXISTS attendance_records (
    id SERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    record_date DATE NOT NULL,
    status TEXT NOT NULL,
    notes TEXT,
    UNIQUE(agent_name, record_date)
);

-- =====================================================================
-- MANAGEMENT: CRM — Scoruri magazine
-- =====================================================================
CREATE TABLE IF NOT EXISTS store_scores (
    id SERIAL PRIMARY KEY,
    site_code TEXT NOT NULL,
    score_month TEXT NOT NULL,
    score INTEGER NOT NULL,
    breakdown JSONB,
    calculated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(site_code, score_month)
);

-- =====================================================================
-- VISITS SNAPSHOT — Agregate vizite din SQLite, cacheate în PG
-- Sincronizat la boot și via POST /api/admin/sync-visits-snapshot
-- =====================================================================
CREATE TABLE IF NOT EXISTS visits_snapshot (
    asm             TEXT NOT NULL,
    month           TEXT NOT NULL,
    total_visits    INT  NOT NULL DEFAULT 0,
    avg_completion  NUMERIC(5,1),
    avg_duration    NUMERIC(6,2),
    distinct_stores INT  NOT NULL DEFAULT 0,
    checklist_score NUMERIC(5,1),
    approved_pct    NUMERIC(5,1),
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (asm, month)
);

-- =====================================================================
-- ERROR LOGS — Capturare erori backend + frontend, vizibile în Settings
-- =====================================================================
CREATE TABLE IF NOT EXISTS error_logs (
    id          SERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    source      TEXT NOT NULL CHECK (source IN ('backend', 'frontend')),
    level       TEXT NOT NULL CHECK (level IN ('error', 'warning')),
    message     TEXT NOT NULL,
    traceback   TEXT,
    path        TEXT,
    extra       JSONB,
    seen        BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_error_logs_ts   ON error_logs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_error_logs_seen ON error_logs(seen) WHERE seen = false;

-- =====================================================================
-- GRILE — verificare grile salariale (K5/L5 Google Sheets vs DB target/vanzari)
-- Integrare nativa retail (strangler). Read-only la Google. Vezi
-- docs/grile-integration-plan.md.
-- =====================================================================
CREATE TABLE IF NOT EXISTS grile_sheets (
    site_code    TEXT PRIMARY KEY REFERENCES stores(site_code),
    sheet_id     TEXT NOT NULL UNIQUE,
    registry_key TEXT,                              -- "Company/Store" original (audit)
    is_active    BOOLEAN NOT NULL DEFAULT true,
    source_hash  TEXT,                              -- hash registry -> detectie drift la reseed
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS grile_runs (
    id                 SERIAL PRIMARY KEY,
    run_month          TEXT NOT NULL,               -- YYYY-MM
    source_snapshot_id INT REFERENCES import_snapshots(id) ON DELETE SET NULL,
    status             TEXT NOT NULL DEFAULT 'queued'
                         CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    source             TEXT NOT NULL DEFAULT 'manual'
                         CHECK (source IN ('manual', 'auto')),
    progress_current   INT NOT NULL DEFAULT 0,
    progress_total     INT NOT NULL DEFAULT 0,
    ok_count           INT NOT NULL DEFAULT 0,
    problem_count      INT NOT NULL DEFAULT 0,
    error_count        INT NOT NULL DEFAULT 0,
    duration_ms        INT,
    triggered_by_email TEXT,
    error_message      TEXT,
    started_at         TIMESTAMPTZ,
    heartbeat_at       TIMESTAMPTZ,
    finished_at        TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_grile_runs_month ON grile_runs(run_month, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_grile_runs_month_active
    ON grile_runs(run_month)
    WHERE status IN ('queued', 'running');

CREATE TABLE IF NOT EXISTS grile_store_status (
    run_id           INT NOT NULL REFERENCES grile_runs(id) ON DELETE CASCADE,
    site_code        TEXT NOT NULL,
    completion_pct   NUMERIC(5,1),
    last_edit        TIMESTAMPTZ,
    grila_target     NUMERIC(12,2),                 -- K5
    grila_sales      NUMERIC(12,2),                 -- L5
    db_target        NUMERIC(12,2),                 -- store_targets.target_value
    db_sales_mtd     NUMERIC(12,2),                 -- SUM(reporting_item_month.total_sales)
    db_max_sale_date DATE,                          -- ultima zi din DB (status IN_URMA)
    fill_status      TEXT,                          -- NECOMPLETAT | COMPLETAT
    target_status    TEXT,                          -- OK | DIFERENTA
    sales_status     TEXT,                          -- OK | DIFERENTA | IN_URMA
    tolerance        NUMERIC(12,2),
    error_code       TEXT,
    error_message    TEXT,
    raw_summary      JSONB,
    PRIMARY KEY (run_id, site_code)
);

CREATE TABLE IF NOT EXISTS grile_monthly_operations (
    id                 SERIAL PRIMARY KEY,
    op                 TEXT NOT NULL CHECK (op IN ('finalize', 'archive', 'reset')),
    closing_month      TEXT NOT NULL,               -- YYYY-MM
    only_filter        TEXT,
    dry_run            BOOLEAN NOT NULL DEFAULT true,
    status             TEXT NOT NULL DEFAULT 'queued'
                         CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    job_id             TEXT,
    triggered_by_email TEXT,
    result             JSONB,
    error_message      TEXT,
    started_at         TIMESTAMPTZ,
    heartbeat_at       TIMESTAMPTZ,
    finished_at        TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_grile_monthly_operations_month_active
    ON grile_monthly_operations(closing_month)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS idx_grile_monthly_operations_month_created
    ON grile_monthly_operations(closing_month, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_grile_monthly_reset_live_completed
    ON grile_monthly_operations(closing_month, COALESCE(only_filter, ''))
    WHERE op = 'reset' AND dry_run = false AND status = 'completed';

CREATE TABLE IF NOT EXISTS grile_monthly_reset_items (
    id              SERIAL PRIMARY KEY,
    operation_id    INT NOT NULL REFERENCES grile_monthly_operations(id) ON DELETE CASCADE,
    closing_month   TEXT NOT NULL,                  -- YYYY-MM
    next_month      TEXT NOT NULL,                  -- YYYY-MM
    site_code       TEXT NOT NULL,
    sheet_id        TEXT NOT NULL,
    company         TEXT NOT NULL,
    store           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'error', 'uncertain', 'skipped')),
    ranges          JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (operation_id, site_code)
);

CREATE INDEX IF NOT EXISTS idx_grile_monthly_reset_items_month_site
    ON grile_monthly_reset_items(closing_month, site_code);

CREATE INDEX IF NOT EXISTS idx_grile_monthly_reset_items_status
    ON grile_monthly_reset_items(closing_month, status);

CREATE INDEX IF NOT EXISTS idx_grile_store_status_run ON grile_store_status(run_id);
