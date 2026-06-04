WITH current_store_month AS (
    SELECT MAX(last_seen_month) AS month
    FROM stores
)
UPDATE stores s
SET is_active = (s.last_seen_month = csm.month),
    updated_at = now()
FROM current_store_month csm
WHERE csm.month IS NOT NULL
  AND s.is_active IS DISTINCT FROM (s.last_seen_month = csm.month);
