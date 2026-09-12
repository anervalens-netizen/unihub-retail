-- V3 Audit Lot 35: expose a scalar sales-generation epoch without widening
-- access to the protected generation ledger.
CREATE OR REPLACE FUNCTION public.current_sales_generation_epoch()
RETURNS BIGINT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT COUNT(*)::BIGINT
    FROM public.sales_generation_promotions
$$;

REVOKE ALL ON FUNCTION public.current_sales_generation_epoch() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.current_sales_generation_epoch() TO unihub_web_read;
