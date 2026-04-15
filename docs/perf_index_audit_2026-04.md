# Index Audit — Phase 5 diagnostic (2026-04-15)

Scope: EXPLAIN ANALYZE on the hot `_fetch_*` queries in
`backend/services/dashboard/queries.py` and the cartela receipt count in
`backend/services/dashboard/specials_data.py`. No indexes added here —
findings only. Index creation belongs on a dedicated branch with
before/after measurements, per advisor guidance.

## Follow-up: `idx_sales_month_date_cartela` — applied 2026-04-15

Branch `perf/cartela-index`, migration `001_add_cartela_composite_index.sql`.

| Metric | Before | After | Delta |
|--------|-------:|------:|------:|
| Execution time (cold) | 63.2 ms | 44.2 ms | −30% |
| Execution time (warm) | ~39 ms | ~49 ms* | — |
| **Index bitmap scan time** | **15.4 ms** | **0.85 ms** | **−94%** |
| Index disk reads | 65 blocks | 31 blocks | −52% |
| Plan node | `BitmapAnd` (2 indexes) | Single `Bitmap Index Scan` | ✓ |
| Heap blocks re-checked | 872 | 872 | unchanged** |

\* Warm-cache total rămâne ~49ms: `COUNT(DISTINCT bon_nr)` pe 31255 rânduri domină
agregarea. Indexul nu poate optimiza hash-ul de aggregate — acesta e noul bottleneck.

\*\* Heap re-checks dispar complet doar cu opțiunea B (covering, INCLUDE bon_nr)
care permite index-only scan. Opțiunea B rămâne candidat pentru sprint viitor dacă
query-ul rămâne hot după filtrare reală pe `item_code`.

**Concluzie:** BitmapAnd eliminat, index scan 18× mai rapid. Câștigul vizibil în
producție va fi mai mare decât în test sintetic deoarece query-ul real filtrează
și pe `item_code = ANY(...)` → subset mai mic de rânduri de agregat.

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

## Remaining candidate (optional upgrade)

Opțiunea B — covering index cu `INCLUDE (bon_nr)`:
```sql
CREATE INDEX idx_sales_month_date_cartela_bon
  ON sales_transactions (import_month, sale_date) INCLUDE (bon_nr)
  WHERE is_cartela = false;
```
Ar permite index-only scan, eliminând cele 872 heap re-checks → ~2–5ms total.
Tradeoff: index mai mare pe disk. De măsurat dacă query-ul rămâne hot.

## What is NOT a candidate

Everything else runs in single-digit ms with zero disk reads. The
`reporting_*` aggregates are already well-indexed for the current
access patterns. No action needed on them.

## Out-of-scope (moved to their own tickets)

- GROUPING SETS consolidation of `_fetch_{store,agent,regional,asm}_stats`
  into fewer round-trips. Behavior-changing; separate branch.
- `visits_snapshot` PG table (cache SQLite-derived visit aggregates in PG).
  Schema change + new service code; feature, not a refactor.

## GROUPING SETS consolidation — decizie 2026-04-15

Analizat și decis **skip** pentru `_fetch_regional_stats` + `_fetch_asm_stats`.

Motivare: cele 4 funcții `_fetch_*_stats` rulează deja în `asyncio.gather()` —
fiecare pe conexiune proprie, în paralel. Latența totală = MAX(fiecare query),
nu SUM. GROUPING SETS ar economisi o singură conexiune din pool și ar deduplica
~120 linii de enrichment identic, dar nu ar reduce latența vizibilă pentru user.

Raport risc/câștig nefavorabil:
- SQL mai complex cu markeri `GROUPING()` → mai greu de debugat
- Python side trebuie să split rezultatele după marker → logică adițională
- Risc de regresie pe enrichment promo/incentive (același cod duplicat, dar izolat)
- Zero reducere de latență (già parallele)

Dacă pool-ul devine bottleneck (>50 req/s concurrent pe `/all`), reevaluăm.
