CREATE TABLE IF NOT EXISTS target_calculator_store_exclusions (
    site_code TEXT NOT NULL,
    effective_from_month TEXT NOT NULL CHECK (effective_from_month ~ '^[0-9]{4}-[0-9]{2}$'),
    reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (site_code, effective_from_month)
);

INSERT INTO target_calculator_store_exclusions (site_code, effective_from_month, reason)
VALUES
    ('CRFVUL', '2026-07', 'Mobiup Carrefour Vulcan inchis in iunie 2026; exclus din targetele viitoare.'),
    ('CRFARENA', '2026-07', 'MobiCell Grand Arena inchis in iunie 2026; exclus din targetele viitoare.')
ON CONFLICT (site_code, effective_from_month) DO UPDATE
SET reason = EXCLUDED.reason,
    updated_at = now();
