# H-01A — Opaque salary identity and CNP surface removal

## Problem

The current salary surface exposes CNP through:

- agent-summary API responses;
- `/salarii/agents/history/{cnp}` URLs;
- frontend TypeScript models and component state;
- drawer props and visual rendering;
- retail-code salary link responses;
- generic salary-record responses.

Visual masking does not reduce the technical exposure because the complete value has already crossed the API and browser boundary.

## Incremental target

H-01A removes CNP from the browser and public API without changing the current salary import or database schema.

The backend derives a deterministic opaque identifier using HMAC-SHA256 and a server-only secret:

```text
person_id = "sp1_" + hex(HMAC-SHA256(identity_key, SALARY_PERSON_ID_HMAC_KEY))
```

The canonical internal identity key is:

```text
cnp:<trimmed CNP>
```

when CNP is present, otherwise:

```text
name:<case-folded trimmed full name>
```

The secret is never returned, logged, stored in PostgreSQL, placed in Git or sent to the browser. The `sp1_` prefix versions the contract and permits a future controlled rotation/migration.

## Configuration contract

Environment variable:

```text
SALARY_PERSON_ID_HMAC_KEY
```

Requirements:

- required in production;
- minimum 43 printable non-whitespace characters;
- recommended generation: `python -c 'import secrets; print(secrets.token_urlsafe(48))'`;
- identical value for all web processes and any worker that validates production config;
- stable across deployments;
- never included in error text;
- backup and rotation handled as a secret-management operation.

Missing or invalid configuration in development/test must fail closed for person-ID operations, while test fixtures can set a synthetic value explicitly.

## Backend design

Create `backend/salary_identity.py` (or an equivalently focused module) with:

- `SALARY_PERSON_ID_HMAC_KEY_ENV`;
- `PERSON_ID_PREFIX = "sp1_"`;
- strict secret validation;
- canonical Python identity normalization;
- `make_salary_person_id(cnp, full_name, key=None)`;
- `validate_salary_person_id(value)`;
- safe SQL helpers for the canonical identity expression and HMAC expression;
- alias/placeholder validation to prevent SQL-fragment injection.

PostgreSQL already has `pgcrypto`; use `hmac(..., ..., 'sha256')` and `encode(..., 'hex')`. Add an integration test proving Python and PostgreSQL produce the same identifier for:

- a CNP-backed identity;
- a name-fallback identity;
- whitespace and case normalization;
- Unicode Romanian names.

## API contract

### Agent summary

Each item must contain:

```json
{
  "person_id": "sp1_<64 lowercase hex characters>",
  "full_name": "...",
  "company_name": "...",
  "locatie": "...",
  "month_count": 0,
  "avg_month_count": 0,
  "total_salary": 0,
  "avg_salary": 0
}
```

It must not contain `cnp` or any equivalent raw identity value.

### History

Replace the CNP route with:

```text
GET /salarii/agents/{person_id}/history
```

Rules:

- reject malformed identifiers with 422;
- return 404 for a valid but unknown identifier;
- do not log the underlying identity;
- do not include CNP in the response;
- preserve the existing history payload and salary calculations.

The legacy route `/salarii/agents/history/{cnp}` must be absent from the final OpenAPI contract.

The implemented route is:

```text
GET /salarii/agents/{person_id}/history
```

`person_id` is validated as `sp1_` followed by 64 lowercase hexadecimal
characters. Malformed values return 422 and valid but unknown values return a
generic 404. The old CNP route is not registered.

### Retail-code history

`GET /salarii/agents/history-by-retail-code` may use CNP internally for existing matching, but its `link` payload must expose `person_id` and must not expose `salary_cnp`.

### Generic records

`GET /salarii/records` must not select or return `cnp`. If a consumer needs identity correlation, return the opaque `person_id` instead.

## Frontend contract

Update all salary UI code so that:

- `SalaryAgentSummary` uses `person_id` and has no `cnp` field;
- `AgentSalaryLink` uses `person_id` and has no `salary_cnp` field;
- history fetch uses `/salarii/agents/{person_id}/history`;
- drawer state and props use `personId`;
- row keys use `person_id` with a non-sensitive fallback;
- no CNP is displayed, even masked;
- no CNP appears in local storage, query keys, URLs, console messages or export rows.

## Required tests

### Unit and integration

1. secret validation: missing, too short, whitespace/control and valid;
2. deterministic person ID;
3. different identities produce different IDs;
4. Python/PostgreSQL equivalence;
5. summary response contains `person_id` and no forbidden keys;
6. history lookup succeeds by `person_id`;
7. malformed ID -> 422;
8. unknown valid ID -> 404;
9. retail-code link contains no `salary_cnp`;
10. records endpoint contains no `cnp`;
11. OpenAPI contains the new route and not the legacy route;
12. static frontend gate forbids `cnp`, `salary_cnp`, `maskCnp` and the legacy route in salary API/components;
13. existing salary totals, averages and pagination remain unchanged.

### Read-only production reconciliation

Before merge, execute a transaction marked `READ ONLY` and report only aggregate metadata:

- total distinct canonical salary identities;
- total distinct generated person IDs;
- collision count;
- identities with empty CNP using name fallback;
- duplicate CNP groups, count only;
- duplicate normalized-name fallback groups, count only;
- history row counts compared between legacy identity and person-ID lookup on a synthetic/sample set without printing names or CNP.

Acceptance:

- generated-ID count equals canonical-identity count;
- collision count is zero;
- history counts match;
- no raw identity values are printed or persisted.

## Deployment sequence

1. generate one production HMAC key securely;
2. back up `.env` and `.env.worker` root-only;
3. add the same key to both environment files without displaying it;
4. validate config before restart;
5. build frontend and backend from reviewed merge commit;
6. deploy backend and frontend coherently;
7. force PWA update/hard refresh as needed;
8. verify OpenAPI and an authenticated salary list/history flow;
9. verify access logs contain opaque IDs only;
10. retain rollback artifacts.

## Rollback

Rollback code and frontend together. Keep the HMAC key in the environment during rollback; it is harmless to the old release and avoids another secret mutation during an incident. Do not re-enable a CNP URL after H-01A has been operationally verified; prefer forward-fixing the opaque-ID route.

## Residual risk after H-01A

Raw CNP still exists inside PostgreSQL and selected internal matching paths. H-01A closes the browser/API/URL exposure but does not complete database minimization. H-01B remains required after the migration lifecycle and DB role separation are ready.

## H-01A implementation evidence

- `backend/salary_identity.py` centralizes HMAC-SHA256 identity creation and
  strict key/person-ID validation. SQL receives the HMAC key only as a bind
  parameter.
- Python/PostgreSQL equivalence was verified in a read-only transaction using
  synthetic identities and a temporary in-memory key; no production identity
  values were selected or printed.
- Production reconciliation ran in an explicit read-only transaction with a
  temporary in-memory key: 370 canonical identities, 370 generated IDs, 0
  collisions, 100 deterministic history samples and 0 mismatches. No identity
  values were printed or persisted.
- Focused H-01A and affected salary tests: 49 passed, 12 skipped. The full
  isolated backend suite passed with 739 tests and 8 skips. Frontend tests:
  177 passed; typecheck, build and mypy passed.
- `.env` and `.env.worker` were not modified; no schema migration, production
  write, deploy or service restart was performed. H-01B remains pending.
