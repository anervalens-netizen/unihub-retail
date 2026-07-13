# UniHub Retail — development plan status

Last reconciled: 2026-07-13

This is the executive view of the active development plan. Detailed acceptance
evidence remains in the finding-specific documents; structural refactoring is
tracked in `docs/refactoring-plan-current.md`.

## Current position

| Area | Status | Remaining exit work |
| --- | --- | --- |
| Wave 1 correctness/security | Integrated in `main` | H-15 governed storage and any separately approved history purge |
| H-01A salary API privacy | Merged and active in production | Continue with the retained-data boundary in H-01B |
| H-04/H-05 OIDC and JWKS | Merged and active in production | Ongoing operational monitoring |
| H-07 distributed rate limiting | Merged and active in production | Ongoing metrics and alert monitoring |
| H-06 BFF/server-side session | Merged and active in production | User-interactive login/logout observation and ongoing session metrics |
| H-01B retained-CNP protection | Merged and active in production | Ongoing access/backup monitoring |
| H-02 migration lifecycle | Merged and active in production | Ongoing checksum and migration-runner monitoring |
| Performance/modularization | Dashboard split, bounded DB fan-out, bundle audit, domain schemas and contract hardening complete and active | Ongoing evidence-driven optimization only |
| CI/CD and operations | V2 acceptance complete; quality gates, readiness/liveness and SLO guardrails active in production | Ongoing SLO observation |

## What is already delivered

- P&L management dashboard and the OIDC/P&L login-race hotfix;
- P&L actual-over-estimate precedence, authoritative company/store filtering,
  current-year default scope and separate monthly/annual trends;
- canonical return-receipt identity;
- Grile monthly idempotency and safe transitions;
- bounded, redacted DB error logging;
- spreadsheet formula neutralization;
- privileged capability authorization by OIDC groups, without email fallback;
- generated-artifact cleanup from Git HEAD;
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
2. move generated/business artifacts to governed storage and decide separately
   whether approved history purge is required for H-15;
3. split worker queues and persistent upload/job orchestration only when load or
   reliability evidence justifies that next platform tranche;
4. apply further query/index optimization only from measured production
   baselines.
