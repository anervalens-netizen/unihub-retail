-- Agent Evaluation v2 reads only positive premium-glass transaction lines.
-- Keep this partial covering index aligned with the exact repository predicate
-- so the query does not scan the complete sales history for one month.
CREATE INDEX IF NOT EXISTS idx_sales_agent_evaluation_premium
    ON sales_transactions (import_month, agent, item_code)
    INCLUDE (id, quantity)
    WHERE LOWER(TRIM(COALESCE(category, ''))) = 'folii sticla'
      AND quantity > 0
      AND agent IS NOT NULL
      AND TRIM(agent) != ''
      AND agent != '-'
      AND agent NOT ILIKE 'TR%';
