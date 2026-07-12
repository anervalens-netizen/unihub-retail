# UniHub Retail v2 — performance baseline

Last updated: 2026-07-13

## Method

Measurements run on the production host through the application service and
repository classes, using the least-privilege runtime DB role and read-only
queries. Each path was executed three times for the latest reporting month
(`2026-07`). Values include pool acquisition, SQL, model assembly and dependent
service work; they exclude browser/network latency.

## Initial baseline

| Critical read path | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: |
| Dashboard all | 418.7 ms | 489.7 ms | 1,059.6 ms |
| Campaign overview | 6.1 ms | 6.5 ms | 8.8 ms |
| Agent evaluation v2 | 557.8 ms | 565.6 ms | 618.4 ms |
| Salary overview | 22.5 ms | 22.5 ms | 27.0 ms |

The two confirmed optimization targets are Dashboard all and Agent Evaluation
v2. Campaign and salary reads are already below the initial 100 ms service
budget and receive no speculative indexes.

## Agent Evaluation v2 evidence

`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` before optimization reported 647.7 ms
execution and 11.6 ms planning. The dominant scan was
`sales_transactions`: three parallel sequential-scan loops filtered roughly
591,000 rows each to obtain about 1,912 premium-glass rows per loop. The scan
accounted for approximately 407 ms across loops and 45,794 shared-buffer hits.

Migration `025_agent_evaluation_premium_index.sql` adds a partial covering
index for the exact immutable premium-glass predicate and keys used by the
repository query. It includes the selected ID and quantity so the month-level
read can become index-only after visibility permits. The index is evidence
driven; it does not change query predicates or business results.

Post-migration acceptance must record:

- the selected plan and whether it uses the new index;
- execution time and shared-buffer delta;
- three service-level measurements using the same month and scope;
- exact result equivalence before/after;
- index size and production health.

## Dashboard observation

The cold Dashboard request expands a pool configured with three prewarmed
connections while starting fifteen named concurrent components. Component
timings therefore include connection acquisition and dependency waits. A
separate warm baseline remains around 490 ms; the next step is query-level
measurement plus bounded scheduling based on actual pool capacity, not a
speculative cache or index.
