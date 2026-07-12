# UniHub Retail — development plan status

Last reconciled: 2026-07-12

This is the executive view of the active development plan. Detailed acceptance
evidence remains in the finding-specific documents; structural refactoring is
tracked in `docs/refactoring-plan-current.md`.

## Current position

| Area | Status | Remaining exit work |
| --- | --- | --- |
| Wave 1 correctness/security | Integrated in `main` | H-15 governed storage and any separately approved history purge |
| H-01A salary API privacy | Implemented, CI green on Wave 2 | Merge, production configuration and controlled release verification |
| H-04/H-05 OIDC and JWKS | Implemented, CI green on Wave 2 | Merge and controlled release verification |
| H-07 distributed rate limiting | Application implemented, CI green | Coordinated Caddy, firewall, environment and backend activation |
| H-06 BFF/server-side session | Not implemented | Design decision, phased implementation and migration |
| H-01B retained-CNP protection | Not implemented | Dedicated storage boundary, least privilege, audit and recovery controls |
| H-02 migration lifecycle | Not implemented | Immutable checksums, advisory lock, migration runner, remove web-startup DDL |
| Performance/modularization | Partially implemented | Measured baselines, remaining backend boundaries and frontend splits |
| CI/CD and operations | Partially implemented | Required E2E/a11y/security gates, readiness, SLOs, alerts and service hardening |

## What is already delivered

- P&L management dashboard and the OIDC/P&L login-race hotfix;
- canonical return-receipt identity;
- Grile monthly idempotency and safe transitions;
- bounded, redacted DB error logging;
- spreadsheet formula neutralization;
- privileged capability authorization by OIDC groups, without email fallback;
- generated-artifact cleanup from Git HEAD;
- opaque salary `person_id`, with CNP removed from browser and public API;
- typed fail-closed OIDC settings, real JWKS rotation and bounded stale cache;
- trusted client-IP resolution and atomic distributed Valkey rate limiting;
- foundational query-cache/frontend primitives and selected backend repository boundaries.

## Path to the new release

The next releasable increment is Wave 2, not the end of the entire modernization
program. Its shortest safe path is:

1. review and merge the Wave 2 PR;
2. provision the required production secrets/settings without exposing values;
3. activate H-07 through the coordinated proxy/firewall/backend runbook;
4. deploy and execute authenticated privacy, OIDC/JWKS and rate-limit smoke tests;
5. then implement H-06, H-01B and H-02 as separate reviewed changes;
6. continue the measured performance, modularization and operational milestones;
7. close with full regression, migration, security, accessibility and live-path acceptance.

The application should not be described as the final new version while H-06,
H-01B, H-02 and the production activation of H-07 remain open. Wave 2 can be
released independently once its merge and production gates are satisfied.
