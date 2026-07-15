# UniHub Retail — development plan status

Last reconciled: 2026-07-15 on code candidate
`6dafc72899dcf9e500e675d68973aec21e495880`

This is the executive view of the active development plan. Detailed acceptance
evidence remains in the finding-specific documents; structural refactoring is
tracked in `docs/refactoring-plan-current.md`.

## Current position

| Area | Status | Remaining exit work |
| --- | --- | --- |
| v2.0.1 P0 import/Grile/salary | Integrated through PRs #96-#98; PostgreSQL import evidence strengthened in PR #101 | Migrations 026-028, approved rollout, production acceptance and rollback |
| v2.0.1 PR runner boundary | GitHub-hosted PR CI integrated in PR #95; direct TimesFM probe corrected in PR #101; former production-host runner stopped/removed | Required production environment reviewers and the root-owned deploy entrypoint are not provisioned, so deploy remains fail-closed |
| v2.0.1 isolated hardening | no-store, HTTP surface, Target Calculator atomicity and session refresh integrated in PR #99 | Caddy rollout verification and production acceptance |
| Wave 1 correctness/security | Integrated in `main`; H-15 closed with explicit residual-risk acceptance | Ongoing monitoring only |
| H-01A salary API privacy | Merged and active in production | Continue with the retained-data boundary in H-01B |
| H-04/H-05 OIDC and JWKS | Merged and active in production | Ongoing operational monitoring |
| H-07 distributed rate limiting | Merged and active in production | Ongoing metrics and alert monitoring |
| H-06 BFF/server-side session | Merged and active in production | User-interactive login/logout observation and ongoing session metrics |
| H-01B retained-CNP protection | Merged and active in production | Ongoing access/backup monitoring |
| H-02 migration lifecycle | Merged and active in production | Ongoing checksum and migration-runner monitoring |
| Performance/modularization | Dashboard split, bounded DB fan-out, bundle audit, domain schemas and contract hardening complete and active | Ongoing evidence-driven optimization only |
| CI/CD and operations | V2 acceptance complete; quality gates, readiness/liveness and SLO guardrails active in production | Ongoing SLO observation |

## What is already delivered

The items below remain the accepted V2 baseline. In addition, the `v2.0.1` code
candidate now includes:

- sales imports that validate strictly, persist coverage/diff and never change
  store activity by omission; explicit audited store activity writes;
- read-only Grile checks plus separate OIDC-subject-audited privileged diff/sync;
- fail-closed salary finalization/archive/reset with persistent verified manifests,
  complete source backups, checkpoints and verified rollback;
- GitHub-hosted PR checks, vendored private packages and an immutable verified
  main artifact boundary;
- private/no-store sensitive responses, disabled public FastAPI docs in the app,
  namespace-safe SPA fallback, atomic Target Calculator batches and bounded
  race-safe session refresh.

- P&L management dashboard and the OIDC/P&L login-race hotfix;
- P&L actual-over-estimate precedence, authoritative company/store filtering,
  current-year default scope and separate monthly/annual trends;
- canonical return-receipt identity;
- Grile monthly idempotency and safe transitions;
- bounded, redacted DB error logging;
- spreadsheet formula neutralization;
- privileged capability authorization by OIDC groups, without email fallback;
- generated-artifact cleanup from Git HEAD and rewritten `main` history, with
  governed local/NAS rollback storage;
- opaque salary `person_id`, with CNP removed from browser and public API;
- typed fail-closed OIDC settings, real JWKS rotation and bounded stale cache;
- trusted client-IP resolution and atomic distributed Valkey rate limiting;
- foundational query-cache/frontend primitives and repository boundaries,
  including the complete monthly Grile operation lifecycle;
- measured Agent Evaluation and Dashboard optimizations, with identical response
  evidence and median reductions of 76.7% and 25.8% respectively;
- bounded Dashboard fan-out, component queue metrics, reusable breakdown
  tables and separate typed Current/History views;
- net Retail quantity as the canonical KPI rule across all 35 reporting
  months: returns reduce quantity, Focus, averages and breakdowns, while
  return receipts remain monitored separately;
- Management navigation reconciled to Manageri, Calculator Target, Salarii
  and P&L; unreachable legacy Tasks/HR/CRM frontend code removed while the CRM
  scoring read model and compatible backend endpoints remain available;
- bundle audit confirms screen-level lazy loading and keeps the shared chart
  runtime outside initial preload; AI Forecast and Contest public models are
  bounded schemas extracted from monolit, impreuna cu contractele complete de
  lifecycle/evaluare Agents si contractele Campaigns/Premium Glass/Dashboard;
- public month/status/value contracts are constrained in OpenAPI, persisted
  Grile reads use explicit columns, and repeated business/retry literals have
  named sources of truth;
- frontend CI gates for general and strict typecheck, lint, unit tests, runtime
  dependency audit, production build, Playwright flows and WCAG A/AA smoke scans
  (GitHub Actions merge-ref run `29225724923`: backend and frontend green).
- bounded `/livez` and `/readyz` probes, external readiness monitoring, Retail
  SLO recording/alert rules and hardened versioned systemd units (PR #58,
  production rollout `2fdb5e8ed3fe2f70ede820bc6247b6075da07e14`).

## V2 release acceptance

UniHub Retail V2 was accepted operationally on 2026-07-13. The final contract
hardening was integrated through PR #78 at merge commit
`dbcedf0310685b9ad91e80c6d5d7452aa3b4ebb0`; merge-ref CI run `29247244063`
passed backend and frontend, including strict typing, isolated PostgreSQL tests,
coverage gates, build, browser flows and WCAG smoke tests. Backend and worker
were then restarted cleanly, with local/public liveness and readiness, OpenAPI
contracts and Prometheus targets verified.

Remaining work is operational or separately scoped backlog, not a V2 release
blocker:

1. continue monitoring privacy, OIDC/JWKS, sessions, rate limiting and SLOs;
2. optionally ask GitHub Support to remove historical H-15 PR refs and cached
   views as additional repository hygiene; the accepted private residual is not
   an open audit finding or release blocker;
3. split worker queues and persistent upload/job orchestration only when load or
   reliability evidence justifies that next platform tranche;
4. apply further query/index optimization only from measured production
   baselines.

## v2.0.1 release gate

The code candidate passed local isolated PostgreSQL tests and GitHub merge-ref
checks. Main CI run `29444282142` passed runner isolation, dependency/security
scans, mypy, backend coverage, frontend typechecks/lint/tests/build and sequential
Playwright/accessibility, then produced the verified artifact for
`6dafc72899dcf9e500e675d68973aec21e495880`.

This is not yet a released/deployed claim. Before tagging `v2.0.1`, the exact
final documentation merge SHA must pass CI, receive enforced environment approval,
run migrations and deploy from the verified artifact, pass local/public acceptance
and demonstrate rollback. The deploy workflow intentionally cannot start while
required environment reviewers are unavailable; manual deployment is not a valid
substitute.

## Release versioning

The accepted product generation is V2. Formal releases should use a
SemVer-inspired scheme:

- `v2.0.0` identifies the accepted V2 baseline;
- `v2.0.1` is the prepared compatible integrity/security hotfix and remains
  unpublished until its deployment gates pass;
- `v2.MINOR.0` identifies a compatible tranche of product functionality;
- `v2.MINOR.PATCH` identifies compatible fixes and hardening;
- `v3.0.0` is reserved for a deliberate, materially incompatible product,
  contract or architecture transition with its own migration and acceptance.

Feature count alone does not justify a major version. The first formal release
is `v2.0.0`; package metadata and canonical release notes are versioned with the
release, and the Git tag/GitHub Release identify its CI-green merge commit.
