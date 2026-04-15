CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS stores (
    site_code TEXT PRIMARY KEY,
    locatie TEXT NOT NULL,
    firma TEXT NOT NULL,
    regional TEXT NOT NULL,
    asm TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    first_seen_month TEXT NOT NULL,
    last_seen_month TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL CHECK (role IN ('admin', 'asm', 'management', 'tl')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('admin', 'asm', 'management', 'tl'));

CREATE TABLE IF NOT EXISTS focus_products (
    item_code TEXT PRIMARY KEY,
    item_name TEXT,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    added_by INTEGER REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tl_store_assignments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    site_code TEXT NOT NULL REFERENCES stores(site_code) ON DELETE CASCADE,
    UNIQUE (user_id, site_code)
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
    imported_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

CREATE TABLE IF NOT EXISTS store_targets (
    import_month TEXT NOT NULL,
    site_code TEXT NOT NULL REFERENCES stores(site_code),
    target_value NUMERIC(12, 2) NOT NULL DEFAULT 0,
    source_file TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (import_month, site_code)
);

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
    user_id     INT REFERENCES users(id) ON DELETE SET NULL,
    extra       JSONB,
    seen        BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_error_logs_ts   ON error_logs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_error_logs_seen ON error_logs(seen) WHERE seen = false;
