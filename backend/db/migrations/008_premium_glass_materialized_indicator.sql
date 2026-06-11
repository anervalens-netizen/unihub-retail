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
      AND st.item_code IS NOT NULL
      AND TRIM(st.item_code) != ''
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
