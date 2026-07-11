# ADR-003 — Canonical receipt identity

**Status:** Proposed  
**Date:** 2026-07-11  
**Audit finding:** H-03  
**Decision owner:** Backend/Data; business reconciliation required before production rollout.

## Context

Sales rows do not have a globally unique `bon_nr`. The same receipt number can appear on different dates, in different stores, or for different agents. Counting return receipts with `COUNT(DISTINCT bon_nr)` therefore merges unrelated receipts and undercounts returns.

## Decision

Within UniHub Retail reporting, a receipt is identified by the tuple:

```text
sale_date
site_code
normalized_agent
bon_nr
```

`normalized_agent` is `BTRIM(agent)`, with null or blank values mapped to the stable sentinel `<unknown>`.

The canonical PostgreSQL expression is maintained in one Python helper and reused by dashboard queries:

```sql
(
  alias.sale_date,
  alias.site_code,
  COALESCE(NULLIF(BTRIM(alias.agent), ''), '<unknown>'),
  alias.bon_nr
)
```

The identity deliberately excludes `import_month`: `sale_date` already carries the year and month, and adding both would be redundant. It also excludes line-level product fields because multiple lines belonging to the same receipt must collapse to one receipt.

## Consequences

- Store, agent, regional and global return metrics use the same identity definition.
- Historical KPI values may increase where receipt-number collisions existed.
- A production reconciliation query is required before rollout to quantify the delta.
- A future `reporting_receipt_day` read model should materialize this identity and return flags, reducing repeated raw-transaction scans.

## Rollback

The implementation is query-only and introduces no schema change. Rollback is a code revert to the previous aggregation. Production rollout must record the before/after KPI delta so a rollback does not silently change reported history.
