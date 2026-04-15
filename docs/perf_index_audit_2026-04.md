# Index Audit — Phase 5 diagnostic (2026-04-15)

Scope: EXPLAIN ANALYZE on the hot `_fetch_*` queries in
`backend/services/dashboard/queries.py` and the cartela receipt count in
`backend/services/dashboard/specials_data.py`. No indexes added here —
findings only. Index creation belongs on a dedicated branch with
before/after measurements, per advisor guidance.

Target month: `2026-03` (fully loaded, 2575 agent-day rows / 31819 tx).
Database: PostgreSQL 18 on 192.168.0.68.

## Results per hot query

| Query | Exec time | Buffers (hit/read) | Plan note |
|-------|----------:|-------------------:|-----------|
| `_fetch_store_stats_rows` | 6.8 ms | 83 / 0 | `idx_reporting_agent_day_month_agent` + `idx_targets_month` — fine |
| `_fetch_agent_stats_rows` (reporting_agent_month) | 0.3 ms | 10 / 0 | `idx_reporting_agent_month_month` — fine |
| `_fetch_period_comparison` (1 period) | 1.2 ms | 71 / 0 | PK `reporting_agent_day_pkey` — fine; ×3 periods ≈ 3.6 ms |
| `_fetch_receipt_bucket_mix` | 0.7 ms | 55 / 0 | `idx_reporting_agent_day_month_agent` — fine |
| `reporting_item_month` group by site+item | 0.07 ms | 3 / 0 | `idx_reporting_item_month_month_item` — fine |
| **cartela receipt count** (specials_data) | **39.4 ms** | **922 / 25** | BitmapAnd of `idx_sales_transactions_month_cartela` + `idx_sales_date`; 872 heap blocks re-checked |

## The one candidate worth filing as follow-up

`sales_transactions` cartela receipt count is the slowest hot query at
~40 ms. Plan currently does BitmapAnd of two indexes (partial-month +
date-range) and re-checks 872 heap blocks. Two options for a follow-up
branch:

1. Composite partial index:
   ```sql
   CREATE INDEX idx_sales_month_date_cartela
     ON sales_transactions (import_month, sale_date)
     WHERE is_cartela = false;
   ```
   Expected: single index scan, no BitmapAnd, ~10–15 ms.

2. Covering variant (index-only scan):
   ```sql
   CREATE INDEX idx_sales_month_date_cartela_bon
     ON sales_transactions (import_month, sale_date) INCLUDE (bon_nr)
     WHERE is_cartela = false;
   ```
   Expected: zero heap reads, ~2–5 ms — but larger on-disk index.

Size/write-cost tradeoff needs measuring on the prod dataset. Do not
add either blindly — build the composite on a staging dump, compare
EXPLAIN (ANALYZE, BUFFERS) before/after, and confirm writes don't
regress the import path.

## What is NOT a candidate

Everything else runs in single-digit ms with zero disk reads. The
`reporting_*` aggregates are already well-indexed for the current
access patterns. No action needed on them.

## Out-of-scope (moved to their own tickets)

- GROUPING SETS consolidation of `_fetch_{store,agent,regional,asm}_stats`
  into fewer round-trips. Behavior-changing; separate branch.
- `visits_snapshot` PG table (cache SQLite-derived visit aggregates in PG).
  Schema change + new service code; feature, not a refactor.
