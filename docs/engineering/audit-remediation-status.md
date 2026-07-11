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

- [x] H-03 Canonical return receipt identity and regression fixtures — implemented, reconciled, business-approved and CI-green; production deploy pending Wave 1 release.
- [x] H-11 Grile monthly idempotency/state transitions — implemented, review-hardened and CI-green; production deploy pending Wave 1 release.
- [x] H-16 DB error logging reliability and bounded failure path — implemented, review-hardened and CI-green; production deploy pending Wave 1 release.
- [x] H-12 Spreadsheet formula neutralization across XLSX/CSV/Sheets outputs — runtime/offline writers and DataFrame missing-value handling are review-hardened and CI-green; production deploy pending Wave 1 release.
- [x] H-08 Remove privileged real-email fallbacks and fail closed — technically complete; production deploy pending dedicated-group provisioning.
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

## Implemented findings

### H-08 — Privileged access fail-closed

**Status:** technically complete on the integration branch; deployment pending
**Draft PR:** #30
**Implementation commit:** `487a2ac7c599cf1116c58894d95452016edadba8`
**P&L owner-policy hardening:** `07718960c2ff55d53ebb2284ba4886c8025cc07b`
**Capability-cache hardening:** `a841d7dfdbb2bba7e917df0e9c0a89630851e0de`
**Auth-bootstrap wiring hardening:** pending current H-08 commit
**CI:** pending final PR run; local policy/config/router tests, mypy and full
backend/frontend checks are required before merge.

Completed:

- dedicated Target and Grile OIDC group policies, parsed all-or-nothing at
  runtime with no import-time environment cache;
- removal of email authorization and broad-role fallback from the two
  privileged capabilities;
- removal of the residual P&L email-owner fallback in favor of its existing
  management-group access policy plus a dedicated P&L owner group;
- backend P&L capability endpoint and subject-scoped frontend query replacing
  frontend email authorization; both fail closed on errors.
- P&L query cache revalidates on every mount and hides cached capability while
  fetching or after a refetch error.
- production validation requiring both group lists and rejecting deprecated
  email variables;
- structured allow/deny audit events limited to resource, verified subject and
  route template;
- static regression gate and router/config tests covering fail-closed behavior.

Remaining before deployment:

- create and assign the dedicated groups in Authentik;
- emit the groups claim and configure all three backend service variables;
- merge, deploy and run the non-destructive permission verification.

### H-12 — Spreadsheet formula neutralization

**Status:** technically complete and review-hardened on the integration branch; production deploy pending  
**Draft PR:** #30  
**Implementation commit:** `3e67adb7aa86c1f315154c3abeabd618684a1701`  
**Writer-bypass hardening commit:** `9d36e5e07a71e704cadf15f0dd6d8d2ce5a552da`  
**DataFrame correctness hardening commits:** `4f4ebc128a03fbb47b5b6974e32f18471bf59a0d`, `0da36ab73cd0b524f7846e336e3c9c2d0579474b`  
**CI:** run #277 passed backend mypy/tests and frontend typecheck/tests/build for the writer hardening; the subsequent focused DataFrame review hardening remains subject to the latest PR CI before merge.

Completed:

- all runtime XLSX rows route through the central safety boundary, including Exports daily-comparison `Configuratie`;
- Grile constructs its two formulas as `TrustedFormula` at origin;
- writer-level tests block raw `Worksheet.append` and inspect XLSX XML;
- human-opened offline XLSX/CSV reports are neutralized while retaining native numeric columns;
- pandas object/string/categorical text columns are neutralized without turning missing values into literal `nan`/`<NA>` strings;
- deployment remains explicitly pending and no real Sheets or business data was used for the verification.

Remaining before H-12 is operationally closed:

- latest PR CI after the final DataFrame review hardening;
- merge as part of the approved Wave 1 release;
- controlled post-deploy export verification with synthetic harmless values.

### H-03 — Canonical return receipt identity

**Status:** implemented and business-approved on the integration branch; production deploy pending  
**Draft PR:** #30  
**Implementation commit:** `3ed251b6fa193a635a3a3f400a2ac422b84af039`  
**Review hardening commit:** `3aa0a5e56fc765ad3482bc12353b2494f857aa4d`  
**Business approval record:** `docs/engineering/h03-business-approval.md`  
**CI:** run #255 passed backend mypy/tests and frontend typecheck/tests/build.

Completed:

- ADR defining `sale_date + site_code + normalized_agent + bon_nr` as the canonical identity;
- centralized, alias-validated SQL expression helper;
- unit tests for the helper and unsafe alias rejection;
- helper wired into Dashboard historical, store, agent and regional return aggregations;
- isolated PostgreSQL collision fixture proving legacy `2` versus canonical `5` and exercising the real queries;
- the fixture preserves the production `bon_nr NOT NULL` schema constraint while testing NULL semantics in an isolated CTE;
- read-only month-level production reconciliation query;
- documented deploy and rollback procedure;
- explicit approval from the business/application owner on 2026-07-11.

Production reconciliation executed in an explicit read-only transaction and rolled back:

- period: `2023-09` through `2026-07`;
- months checked: `35`;
- canonical return receipts checked: `26,211`;
- months with a delta: `0`;
- colliding receipt numbers: `0` in every checked month;
- absolute and relative delta: `0` / `0.00%` in every checked month;
- no raw receipt number, agent identity or transaction row was copied into this ledger.

Remaining before H-03 is operationally closed:

- merge as part of the approved Wave 1 release;
- backend deployment and post-deploy Dashboard/health verification.

### H-11 — Grile monthly idempotency and state transitions

**Status:** implemented and review-hardened on the integration branch; production deploy pending  
**Draft PR:** #30  
**Implementation commit:** `ca8425e62f68336574fcb415626570272364e6a0`  
**Queue-publication hardening commits:** `0ae51bd289e819fca798883692179d7425fc65e4`, `fd7b08af255e67625d0d9477620f8b04ada10dae`  
**CI:** run #267 passed backend mypy/tests and frontend typecheck/tests/build.

Completed:

- typed `MonthlyOperationStartResult` for atomic worker acquisition;
- guarded `queued -> running`, `running -> completed|failed` and `queued|running -> failed` transitions without terminal-row overwrite;
- no-op/replay worker responses for duplicate and missing operation IDs;
- finalize/archive/reset, heartbeat, finish, checkpoint, file and Google side effects are skipped on duplicate delivery;
- deterministic job ID is persisted while the operation is still queued, before ARQ publication;
- queue exceptions and null enqueue results fail only a still-queued reservation;
- a fast worker or ambiguous publish outcome cannot clobber an already-running operation;
- isolated PostgreSQL concurrency and duplicate-delivery tests for finalize, archive and reset, with Google-facing calls mocked;
- queue-ordering tests cover attach-before-publish, rejected attachment, Valkey failure and existing active reservations.

No schema migration, Google operation, deployment, restart or production PostgreSQL write was performed while implementing H-11.

Remaining before H-11 is operationally closed:

- merge as part of the approved Wave 1 release;
- backend/worker deployment;
- controlled dry-run verification and duplicate-delivery no-op verification without live Google writes.

### H-16 — DB error logging reliability and bounded failure path

**Status:** implemented and review-hardened on integration branch; production deploy pending  
**Draft PR:** #30  
**Implementation commit:** `ddf8ff7344cb73400cee1f8858afed6a1ab8bbe6`  
**Review hardening commit:** `9eb887431ae611597210fcecc8e113a856ed41a5`  
**CI:** run #274 passed backend mypy/tests and frontend typecheck/tests/build.

Completed:

- immutable, bounded DB error events and recursive secret/CNP redaction;
- one bounded queue and consumer per process, with timeout-bounded persistence;
- stable dropped-event Prometheus reasons and direct non-recursive stderr fallback;
- idempotent attach and controlled detach before PostgreSQL pool shutdown;
- isolated PostgreSQL regression coverage for traceback persistence and redaction;
- review hardening for valid bounded JSONB extras, iterator-safe redaction, exact shutdown accounting and guaranteed lifespan cleanup.

No schema migration, production DB write, intentional production error, Sentry event, deployment or service restart was performed while implementing H-16.

Remaining before H-16 is operationally closed:

- merge as part of the approved Wave 1 release;
- backend deployment;
- controlled synthetic ERROR verification without simulating a production DB outage.

## Active finding

### H-08 — Privileged access must fail closed

**Status:** current email-based fallbacks revalidated; implementation specification ready  
**Specification:** `docs/engineering/h08-privileged-access-fail-closed.md`

The target policy uses dedicated OIDC groups, denies access when configuration is absent, rejects deprecated email allowlists in production and requires Authentik group provisioning before deployment.

## Acceptance model

A finding is closed only when:

- its regression/security test exists and passes;
- the documented acceptance criteria are demonstrated;
- rollback or forward-fix procedure is recorded where relevant;
- configuration and operational documentation are updated;
- no new sensitive data, generated artifact or CI warning is introduced;
- production deployment and health verification are completed where required.

## Current status

`Wave 0 — rebaseline in progress; Wave 1/H-03, H-11, H-16 and H-12 technically validated; H-08 implementation next`
