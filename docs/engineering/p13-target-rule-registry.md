# P1.3 Target rule registry and bounded allocation

## Scope

Migration `036_target_rule_registry.sql` introduces the versioned Target rule
registry. The table is append-only; the effective end is derived with `LEAD`
from the next inserted version, yielding contiguous `[effective_from_month,
effective_to_month)` intervals without rewriting prior rows. It seeds two immutable
business configurations:

- `target-finance-legacy-19-v1`, effective through `2025-07`;
- `target-finance-21-v1`, effective from `2025-08`.

A rule-set contains the official effective TVA rule, salary P&L factor, base
salary, meal vouchers, commission, assumed attainment, default agent count and
validated per-store exceptions. The service validates the canonical JSON
SHA-256, exact schema, numeric ranges, fiscal registry equality and every
exception as one exact code in both current master and active cohort; aliases,
unknown codes, duplicate mappings and master/cohort name mismatches fail closed
before any metrics query or Target write.

## Calculation and override contract

The proposal allocator is deterministic to cents and accepts a requested budget
only when:

```text
sum(floor_target) <= total_target <= sum(cap_target)
```

It rejects an infeasible budget before `save_draft_scenario`; it never exceeds a
floor or cap merely to return a partial result. Both floor and cap are persisted
with the scenario rows.

`proposed_target` remains algorithmic. A manager decision is stored separately
as `manager_override_target` and `manager_override_reason` when `final_target`
differs from the proposal. The proposal is never overwritten by an override;
revision CAS on the scenario still guards concurrent manager edits and
finalization. The audit separately retains reason, OIDC actor, timestamp and the
revision written by the override; actor is not exposed in the public payload.

## Historical freeze

At calculation, `target_scenarios` stores `rule_set_id`, `rule_set_hash` and the
full `rule_set_snapshot`. Profitability/read/export resolve from this snapshot,
not the mutable current registry. Legacy scenarios with no snapshot continue as
`legacy-unversioned`; their finalized reads and published rows are therefore not
rewritten or reinterpreted by migration 036.

The rule-set table is append-only: UPDATE and DELETE are forbidden, including
effective boundaries. A future additive migration only inserts a successor with
a later `effective_from_month`; the view derives the predecessor's ending month.
It cannot alter a rule-set's business content or an existing scenario snapshot.

The same freeze stores canonical calculation/source-input and profitability-input
SHA-256 values, plus profitability per Target row. New scenarios' GET/export
path uses only that scenario snapshot and never re-reads current P&L or
forecast data. Legacy records retain NULL rule-set/snapshot fields as
`legacy-unversioned`, without backfill; their public export payload/hash is
unchanged.

## Verification

```bash
cd /opt/Mobiup/unihub-retail
backend/scripts/run_tests_isolated.sh -q
backend/venv/bin/mypy backend/ --ignore-missing-imports --explicit-package-bases
```

Target-specific evidence covers deterministic multi-row residual-cent
allocation, infeasible floor/cap rejection before persistence, registry
hash/schema/fiscal validation, append-only successor-derived `[from,to)` ranges,
exact master/cohort exception reconciliation,
frozen source/profitability snapshots, separate override audit, stale revision
conflict and legacy read/export compatibility. Migration 036 is additive and
issues no UPDATE for legacy scenarios. DB fencing rejects old final-target
mutation against a ruleset draft, and repository recalculation rejects an
algorithm mismatch.
Rollback of code keeps the registry, snapshots and override audit data intact.
No P1.3 command promotes Finance data, mutates live Target scenarios, deploys,
or changes published Target hashes.
