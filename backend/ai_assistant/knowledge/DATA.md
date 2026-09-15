# Retail data guide

The sandbox receives a dedicated PostgreSQL DSN whose database role is read-only. Direct `psql`, Python/psycopg and pandas usage are expected.

## High-value sources

### `stores`
Current store identity and organization attributes. Prefer `site_code` as the stable join key. Use this source when the question is explicitly about current organization/scope.

### `reporting_agent_day`
Modern daily Retail reporting read model. Useful for current-period/day-level sales, quantity, receipts, agent/store aggregation and many dashboard metrics.

### `reporting_agent_month`
Modern monthly Retail reporting read model. Useful for historical month comparisons and aggregated agent/store/organization analysis.

### `store_targets`
Store target values by month/site. Target freshness is independent from sales-reporting rebuilds.

### `agent_targets`
Explicit agent target values where configured.

### `sales_transactions`
Live promoted sales transaction source. Prefer reporting read models for normal dashboards/analysis unless transaction-level detail is actually needed.

### Historical legacy sources
`historical_monthly_sales` and `historical_annual_sales` support older year-history paths. They have documented eligibility/organization limitations; do not mix them into modern reporting silently.

### `fieldops_visits`
External FieldOps-owned visits source. Retail does not own or manufacture this table. It may legitimately be unavailable in an isolated Retail environment.

### Salary / P&L
Salary and P&L surfaces have stronger privacy/access semantics than ordinary commercial reporting. Query them only when the owner asks for those data and only through whatever read permissions the dedicated assistant DB identity actually receives.

## Query strategy

1. Start with the smallest source/granularity that answers the question.
2. Push filters/aggregation into SQL when practical instead of loading huge raw sets into model context.
3. For larger intermediate result sets, save query output to `/workspace/work` (CSV/Parquet/etc.) and analyze with Python rather than echoing rows into the conversation.
4. Use parameterized Python queries for values supplied by the user when practical.
5. Inspect schema/catalog metadata when a column or source is uncertain; do not guess.
6. Keep current-vs-historical organization semantics explicit.

The database itself enforces read-only access. Do not waste turns asking for confirmation before ordinary SELECT/CTE/temporary analytical work that the database identity permits.