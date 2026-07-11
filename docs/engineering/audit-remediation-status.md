# UniHub Retail — Audit remediation status

**Integration branch:** `stabilization/audit-remediation-2026-07`  
**Baseline branch:** `main`  
**Baseline commit:** `d55b35eba9ccaf643bf603490fed7f28debe2ab6`  
**Audit source date:** 2026-07-11  
**Execution model:** incremental, tested, reversible; no big-bang rewrite.

## Purpose

This document is the live execution ledger for the July 2026 technical audit remediation. The original audit and development plan were produced against commit `5af4dd98f6f79086af5ec271965795aa4615af29`; therefore every finding must be revalidated against the current baseline before implementation.

## Rules

1. Every remediation commit references one or more audit finding IDs.
2. Security, privacy, financial correctness and migration changes remain isolated from visual redesigns.
3. Database changes use expand/migrate/switch/contract and must include rollback notes.
4. External side effects require persistent idempotency and reconciliation.
5. CI must pass before a remediation wave is eligible for merge.
6. Production deployment is performed only after a reviewed merge and an explicit server runbook.
7. No sensitive identifiers, secrets or generated business reports are added to Git.

## Already completed after the audited snapshot

- P&L management dashboard integrated into `main` and deployed.
- Obsolete agent/Codex branches removed and automatic branch deletion enabled.
- Dependabot concurrency reduced and stale dependency PRs cleaned up.
- Backend dependency update PR #28 merged after frontend, mypy and backend tests passed.
- FastAPI upgraded to 0.139.0; route-level permission and rate-limit tests adapted to nested route contexts.
- CI diagnostics for mypy and backend tests improved.

These items are not automatically considered to close an audit finding unless the finding acceptance criteria are explicitly satisfied.

## Execution waves

### Wave 0 — Rebaseline and safety gates

- [ ] Revalidate all P0/P1 findings against current `main`.
- [ ] Record current Node/Python/PostgreSQL/Valkey/runtime versions.
- [ ] Add or verify runtime clean-install smoke test.
- [ ] Verify branch protection and required checks.
- [ ] Establish current performance/queue/DB baselines from staging or production-safe metrics.

### Wave 1 — Immediate correctness and security

- [ ] H-03 Canonical return receipt identity and regression fixtures.
- [ ] H-11 Grile monthly idempotency/state transitions.
- [ ] H-16 DB error logging reliability and bounded failure path.
- [ ] H-12 Spreadsheet formula neutralization across XLSX/CSV/Sheets outputs.
- [ ] H-08 Remove privileged real-email fallbacks and fail closed.
- [ ] H-15 Remove generated business reports and obsolete backup assets from Git HEAD.

### Wave 2 — Privacy and identity

- [ ] H-01 Introduce opaque salary person identifiers.
- [ ] H-01 Remove CNP from API responses, URLs, frontend state, query keys and logs.
- [ ] H-04 Typed fail-closed environment/OIDC settings.
- [ ] H-05 JWKS rotation, lock, bounded stale cache and failure metrics.
- [ ] H-06 BFF/server-side session design and phased implementation.
- [ ] H-07 Trusted-proxy-aware distributed rate limiting.

### Wave 3 — Database lifecycle and jobs

- [ ] H-02 Freeze bootstrap baseline and introduce immutable migration checksums.
- [ ] H-02 Add advisory lock and separate migration runner.
- [ ] Remove schema mutation from web startup.
- [ ] Split worker queues and service units by workload class.
- [ ] Stage upload files outside Valkey and enqueue references plus hashes.
- [ ] Add persistent job state, heartbeat, retry and reconciliation.

### Wave 4 — Performance and modularization

- [ ] Add DB pool wait/query metrics and bounded dashboard concurrency.
- [ ] Consolidate dashboard read models and receipt summaries.
- [ ] Optimize only after measured `EXPLAIN (ANALYZE, BUFFERS)` baselines.
- [ ] Extract dashboard, salaries, grile, imports and agents into domain modules.
- [ ] Split oversized frontend screens into typed, testable use-case components.
- [ ] Add typed API errors, cancellation, generated contracts and runtime validation.
- [ ] Standardize accessible routing, drawers and keyboard behavior.

### Wave 5 — CI/CD, governance and operations

- [ ] Harden PR runners and workflow permissions/timeouts/concurrency.
- [ ] Make lint, strict TS, E2E, accessibility, migration and security scans required.
- [ ] Move business/generated artifacts to governed storage with retention and audit.
- [ ] Add liveness/readiness/dependency health separation.
- [ ] Add runbooks, SLOs, alerts and service hardening.

## Active implementation

### H-03 — Canonical return receipt identity

**Status:** in progress  
**Draft PR:** #30

Completed on the integration branch:

- ADR defining `sale_date + site_code + normalized_agent + bon_nr` as the canonical identity;
- centralized, alias-validated SQL expression helper;
- unit tests for the helper and unsafe alias rejection;
- helper wired into Dashboard historical, store, agent and regional return aggregations;
- isolated PostgreSQL collision fixture proving the legacy undercount and canonical counts;
- read-only month-level production reconciliation query;
- documented deploy and rollback procedure.

Remaining before H-03 can be closed:

- run the read-only reconciliation and record aggregate deltas only;
- obtain business approval for the KPI definition;
- pass CI and complete a production verification after the wave is merged.

## Acceptance model

A finding is closed only when:

- its regression/security test exists and passes;
- the documented acceptance criteria are demonstrated;
- rollback or forward-fix procedure is recorded where relevant;
- configuration and operational documentation are updated;
- no new sensitive data, generated artifact or CI warning is introduced;
- production deployment and health verification are completed where required.

## Current status

`Wave 0 — rebaseline in progress; Wave 1/H-03 implementation started`
