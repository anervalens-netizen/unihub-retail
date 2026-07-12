# Audit remediation Wave 2 — Privacy and identity

**Base:** `main` at `0c2834f69d47094e469a31fec9111bae06edd519`  
**Branch:** `stabilization/audit-remediation-wave2-privacy`  
**Status:** implementation branch; no production deployment from this branch

## Scope

Wave 2 addresses the privacy and identity findings that remain after Wave 1:

- H-01 — remove CNP from browser, public API, URLs and ordinary logs while retaining it in the canonical PostgreSQL database;
- H-04 — typed, fail-closed OIDC/runtime settings;
- H-05 — JWKS rotation and bounded stale-key handling;
- H-07 — trusted-proxy and distributed rate limiting;
- H-06 — BFF/session migration design and staged implementation.

The first delivery is **H-01A**, an API-boundary change that introduces an opaque salary person identifier while retaining the existing database columns and values internally.

The approved database-retention constraint is recorded in `docs/engineering/h01-cnp-database-retention-decision.md`. No Wave 2 task may delete, null, overwrite or destructively migrate CNP values without a new explicit business approval.

## H-01A — salary identity boundary

### Required outcomes

- [x] `SALARY_PERSON_ID_HMAC_KEY` is required and validated in production.
- [x] Salary list responses contain `person_id`, never `cnp`.
- [x] Salary history is requested through an opaque `person_id` route.
- [x] The legacy CNP path is absent from OpenAPI.
- [x] Retail-code salary links never return `salary_cnp`.
- [x] Generic salary-record responses never return `cnp`.
- [x] Frontend types, state, keys, drawers and URLs contain no CNP.
- [x] Contract/static tests fail on `cnp` or `salary_cnp` in the public salary surface.
- [x] Python and PostgreSQL helper implementations are proven equivalent through the actual SQL helper expression.
- [x] Production reconciliation was executed read-only.
- [x] Engineering review hardening is complete.
- [x] Local CI-equivalent coverage gate is green; remote CI must run on the pushed commit.

H-01A reconciliation (read-only, 2026-07-12): 370 canonical identities,
370 generated IDs, 0 reported collisions, 2 name-fallback identities, 339 duplicate
non-empty private-ID groups, 2 duplicate normalized-name fallback groups, 100
sampled history identities and 0 history mismatches. The temporary HMAC key was
generated in memory and was not persisted or printed. The engineering review
confirmed the canonical `cnp:` prefix and correct collision grouping by generated
person ID.

### Non-goals for H-01A

- no deletion, blanking, hashing-overwrite or removal of existing CNP columns/values;
- no database schema migration;
- no modification of salary import business rules;
- no change to salary totals, averages, eligibility thresholds or matching decisions;
- no CNP values in Git, tests, logs or documentation.

## H-01B — retained-CNP database protection (later)

Raw CNP remains in PostgreSQL by explicit business decision. H-01B is therefore a protection and access-control phase, not a deletion phase:

- introduce a durable internal `salary_people.person_id` model alongside the retained CNP where useful;
- isolate salary storage behind a dedicated schema/role;
- restrict raw-CNP reads to approved internal import and matching operations;
- add audited access paths and least-privilege grants;
- strengthen encrypted backups, recovery and incident procedures;
- preserve the original CNP columns and values;
- require a separate explicit approval for any future destructive CNP migration.

## Release gates

Every finding must have:

1. focused and full backend tests;
2. frontend tests, typecheck and build when applicable;
3. a read-only production reconciliation where data identity may change;
4. explicit rollback instructions;
5. CI green before merge;
6. no production changes until a reviewed runbook is approved.
