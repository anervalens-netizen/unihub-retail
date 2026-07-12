# Audit remediation Wave 2 — Privacy and identity

**Base:** `main` at `0c2834f69d47094e469a31fec9111bae06edd519`
**Branch:** `stabilization/audit-remediation-wave2-privacy`
**Status:** merged into `main` and activated in production on 2026-07-12

**Progress summary (2026-07-12):** H-01A, H-04/H-05 and H-07 are implemented,
CI-green and activated. H-01B is operationally complete; H-06 is implemented
locally and pending CI/production activation.

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
- [x] Strict public response models and explicit service mappings are enforced.
- [x] Development/test accepts an absent or exactly empty identity key while
  production remains fail-closed; non-empty invalid keys fail in every mode.
- [x] Real ASGI and isolated PostgreSQL query tests cover the public contract,
  key-unavailable path, opaque-ID round trip and private-field exclusion.
- [x] Final local CI-equivalent gate: 766 passed, 7 skipped and
  `services/salarii.py` coverage at 100%; remote CI runs on the pushed commit.
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

## H-04/H-05 — OIDC settings and JWKS hardening

- [x] Typed OIDC verifier settings fail closed in production and permit an
  entirely absent verifier configuration only in development/test.
- [x] Runtime JWKS dependency is declared in production requirements and CI
  imports backend runtime modules from a requirements-only virtualenv.
- [x] JWKS cache lifecycle, bounded fetch, cache age limits and strict token
  header/claim validation are implemented without production changes.
- [x] Final review preserves exact configured OIDC URLs, rejects non-finite
  numeric settings, streams JWKS bodies under a hard bound and tests cleanup.
- [x] Final closure coalesces failed refreshes, bounds unknown-key retries and
  prevents malformed URL ports or claims from escaping as server errors.
- [x] Local closure covers NumericDate overflow safety, completion-based
  cooldowns, refresh-failure backoff, atomic lifecycle and explicit OIDC
  critical-coverage gates (911 passed, 7 skipped; auth 100%, settings 100%,
  verifier 95.62%).
- [x] Formal H-04/H-05 acceptance: GitHub Actions run `29192006867` is green
  on the PR merge ref; no production change is authorized by this branch.

## H-07 — trusted proxy and distributed rate limiting

- [x] Read-only infrastructure preflight identifies Cloudflare Tunnel, Caddy,
  the Docker-network direct peer, port 9898 exposure and Valkey capabilities.
- [x] Typed settings, trusted client-IP resolution and privacy-preserving HMAC
  identities are implemented fail-closed.
- [x] Valkey enforcement is atomic, server-time based and bounded by TTL; two
  independent clients share one quota and 100 concurrent calls at limit 10
  allow exactly 10.
- [x] Existing route policies and permissions remain wired; 429/503 response
  contracts, finite metrics and lifecycle cleanup are tested.
- [x] Local gates: 1,027 backend tests passed, 7 skipped; all four H-07 modules
  have 100% critical coverage; mypy, `pip check`, 177 frontend tests,
  typecheck and build are green.
- [x] Formal application acceptance: GitHub Actions run `29193554547` is green
  on the PR merge ref.
- [x] Production activation completed through the controlled
  Caddy/firewall/environment rollout, with local/public health and enforcement
  evidence recorded in `h07-production-rollout.md`.

## H-01B — retained-CNP database protection

Raw CNP remains in PostgreSQL by explicit business decision. H-01B is therefore a protection and access-control phase, not a deletion phase. The complete boundary is active in production:

- [x] introduce durable `salary_private.people` plus persisted public-safe IDs;
- [x] make ordinary runtime repositories independent of raw-CNP columns;
- [x] restrict private writes to the approved offline importer/backfill path;
- [x] activate the dedicated least-privilege runtime role in production;
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
