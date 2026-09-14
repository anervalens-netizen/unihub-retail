-- Include explicit Team Leader payroll in P&L as a separate non-selling location.
-- The source is HR net pay plus vouchers; it is never allocated to a store.
DO $$
DECLARE
    v_source_sha256 TEXT := encode(sha256(convert_to('salary_history_rows:TEAM_LEADER', 'UTF8')), 'hex');
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.store_pnl_monthly
        WHERE source_site_code = 'TL'
    ) THEN
        RAISE EXCEPTION 'TL P&L rows already exist; refuse duplicate publication';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM public.stores WHERE site_code = 'TL') THEN
        INSERT INTO public.stores (
            site_code, locatie, firma, regional, asm, team_leader_id,
            is_active, first_seen_month, last_seen_month
        ) VALUES (
            'TL', 'TL', 'Mobiup', 'TL', 'TL', NULL,
            true, '2023-01', '2026-07'
        );
    END IF;

    INSERT INTO public.store_pnl_monthly (
        company_name, period, source_site_code, source_location_name,
        category_code, category_name, amount, data_kind,
        source_file, source_sha256
    )
    SELECT
        h.company_name,
        to_date(h.period || '-01', 'YYYY-MM-DD'),
        'TL', 'TL', 'c3', 'Cost salarii',
        sum(h.total_amount)::numeric(16, 2), 'estimated',
        'salary_history_rows:TEAM_LEADER', v_source_sha256
    FROM public.salary_history_rows h
    WHERE h.selected
      AND h.pnl_eligible
      AND h.site_code IS NULL
      AND upper(btrim(coalesce(h.location, ''))) = 'TEAM LEADER'
    GROUP BY h.company_name, h.period;
END
$$;

COMMENT ON TABLE public.stores IS
    'Operational stores plus explicit non-selling P&L location TL for Team Leader payroll.';
