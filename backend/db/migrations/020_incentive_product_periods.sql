ALTER TABLE incentive_products
    ADD COLUMN IF NOT EXISTS valid_from DATE,
    ADD COLUMN IF NOT EXISTS valid_to DATE,
    ADD COLUMN IF NOT EXISTS category TEXT,
    ADD COLUMN IF NOT EXISTS subcategory TEXT,
    ADD COLUMN IF NOT EXISTS source_file TEXT;

UPDATE incentive_products ip
SET valid_from = to_date(ic.month || '-01', 'YYYY-MM-DD'),
    valid_to = (to_date(ic.month || '-01', 'YYYY-MM-DD') + INTERVAL '1 month - 1 day')::DATE
FROM incentive_campaigns ic
WHERE ic.id = ip.campaign_id
  AND (ip.valid_from IS NULL OR ip.valid_to IS NULL);

ALTER TABLE incentive_products
    ALTER COLUMN valid_from SET NOT NULL,
    ALTER COLUMN valid_to SET NOT NULL;

ALTER TABLE incentive_products
    DROP CONSTRAINT IF EXISTS incentive_products_campaign_id_item_code_key;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'incentive_products_valid_period_check'
    ) THEN
        ALTER TABLE incentive_products
            ADD CONSTRAINT incentive_products_valid_period_check
            CHECK (valid_to >= valid_from);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_incentive_products_period
    ON incentive_products(campaign_id, item_code, valid_from, valid_to);

CREATE INDEX IF NOT EXISTS idx_incentive_products_validity
    ON incentive_products(campaign_id, valid_from, valid_to, item_code);
