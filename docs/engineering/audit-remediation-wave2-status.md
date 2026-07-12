# Audit remediation Wave 2 — Privacy and identity

**Base:** `main` at `0c2834f69d47094e469a31fec9111bae06edd519`  
**Branch:** `stabilization/audit-remediation-wave2-privacy`  
**Status:** implementation branch; no production deployment from this branch

## Scope

Wave 2 addresses the privacy and identity findings that remain after Wave 1:

- H-01 — remove CNP from browser, public API, URLs and ordinary logs;
- H-04 — typed, fail-closed OIDC/runtime settings;
- H-05 — JWKS rotation and bounded stale-key handling;
- H-07 — trusted-proxy and distributed rate limiting;
- H-06 — BFF/session migration design and staged implementation.

The first delivery is **H-01A**, an expand step that introduces an opaque salary person identifier while retaining the existing database columns internally. Raw CNP removal from PostgreSQL is a later contract step, after the migration lifecycle is hardened.

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
- [x] Python and PostgreSQL implementations of the person ID were verified
  equivalent in a read-only transaction using synthetic identities and a
  temporary test key; the optional isolated-DB pytest remains skipped unless
  `H01_TEST_DATABASE_URL` is configured.
- [x] Production reconciliation proves stable one-to-one identity mapping before merge.

H-01A reconciliation (read-only, 2026-07-12): 370 canonical identities,
370 generated IDs, 0 collisions, 2 name-fallback identities, 339 duplicate
non-empty private-ID groups, 2 duplicate normalized-name fallback groups, 100
sampled history identities and 0 history mismatches. The temporary HMAC key was
generated in memory and was not persisted or printed.

### Non-goals for H-01A

- no deletion or encryption of the existing CNP columns;
- no database schema migration;
- no modification of salary import business rules;
- no change to salary totals, averages, eligibility thresholds or matching decisions;
- no CNP values in Git, tests, logs or documentation.

## H-01B — database minimization (later)

Pending the migration-runner remediation:

- introduce a durable `salary_people.person_id` model;
- backfill and dual-read;
- restrict the application DB role from raw CNP;
- remove raw CNP indexes and columns according to the approved retention policy;
- reconcile matching accuracy and provide a forward-fix/rollback plan.

## Release gates

Every finding must have:

1. focused and full backend tests;
2. frontend tests, typecheck and build when applicable;
3. a read-only production reconciliation where data identity may change;
4. explicit rollback instructions;
5. CI green before merge;
6. no production changes until a reviewed runbook is approved.
