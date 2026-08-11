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

Raw CNP remains stored in PostgreSQL by explicit business decision. The binding decision and prohibited destructive changes are recorded in `docs/engineering/h01-cnp-database-retention-decision.md`.

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
name:<lower-cased trimmed full name>
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

Missing or invalid configuration in development/test must fail closed for person-ID operations, while test fixtures can set a synthetic value explicitly. Salary endpoints that do not use `person_id` should not fail solely because the development key is absent.

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

PostgreSQL already has `pgcrypto`; use `hmac(..., ..., 'sha256')` and `encode(..., 'hex')`. Add an integration test proving the actual Python and SQL helper implementations produce the same identifier for:

- a CNP-backed synthetic identity;
- a name-fallback identity;
- whitespace and case normalization;
- Unicode Romanian names.

No test may include a real CNP or a 13-digit value.

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

`person_id` is validated as `sp1_` followed by 64 lowercase hexadecimal characters. Malformed values return 422 and valid but unknown values return a generic 404. The old CNP route is not registered.

### Retail-code history

`GET /salarii/agents/history-by-retail-code` may use CNP internally for existing matching, but its `link` payload must expose a non-null `person_id` only for a confirmed salary identity and must not expose `salary_cnp`. Unknown/unmatched links expose `person_id: null`.

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

1. secret validation: missing, too short, any whitespace/control/non-printable character and valid;
2. deterministic person ID;
3. different identities produce different IDs;
4. actual Python/PostgreSQL helper equivalence;
5. summary response contains `person_id` and no forbidden keys;
6. history lookup succeeds by `person_id`;
7. malformed ID -> 422;
8. unknown valid ID -> 404;
9. retail-code link contains no `salary_cnp` and unmatched links use `person_id: null`;
10. records endpoint contains no `cnp`;
11. OpenAPI contains the new route and not the legacy route;
12. static frontend gate forbids `cnp`, `salary_cnp`, `maskCnp` and the legacy route in salary API/components;
13. existing salary totals, averages and pagination remain unchanged;
14. missing development HMAC key does not break salary endpoints that do not generate or resolve `person_id`.

### Read-only production reconciliation

Before merge, execute a transaction marked `READ ONLY` and report only aggregate metadata:

- total distinct canonical salary identities;
- total distinct generated person IDs;
- collision count, defined as one generated ID mapping to more than one canonical identity;
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

Rollback must not remove, rewrite or otherwise alter CNP values in PostgreSQL.

## Residual risk and H-01B

Raw CNP intentionally remains inside PostgreSQL and approved internal matching/import paths. This is a business requirement, not a temporary deletion backlog.

H-01B is therefore limited to retained-data protection:

- dedicated schema/role and least-privilege grants;
- audited internal access paths;
- optional durable `salary_people.person_id` alongside the retained CNP;
- encrypted storage/backups and recovery controls;
- documented retention and incident procedures.

H-01B must not drop, blank, hash-overwrite or destructively migrate CNP values without a new explicit business approval.

## H-01A implementation evidence

## Final response-contract hardening

The salary public boundary is represented by strict Pydantic v2 models with
`extra="forbid"`: agent summary, history record/history response, retail-code
link and generic salary record. Services construct every public field
explicitly; database rows are never serialized wholesale.

The four identity-bearing routes declare response models in OpenAPI:
agent summary, opaque history, retail-code history and generic records. Their
schemas exclude internal matching fields. The canonical SQL grouping expression
is the same helper used for `person_id`; an empty private ID and empty name
produces no canonical identity and fails the public identity path safely.

Final read-only reconciliation reported 370 canonical/370 generated IDs, zero
collisions, zero empty canonical rows, matching legacy/canonical grouping
counts, and zero grouping ambiguities or sampled-history mismatches. CNP data
remains retained and untouched in PostgreSQL.

- `backend/salary_identity.py` centralizes HMAC-SHA256 identity creation and strict key/person-ID validation. SQL receives the HMAC key only as a bind parameter.
- A read-only production reconciliation was executed with synthetic/temporary key material and aggregate-only output.
- Engineering review hardening aligns Python and SQL on the exact expression:
  `cnp:` plus trimmed non-empty CNP, otherwise `name:` plus lower-cased trimmed
  name. Every H-01A SQL HMAC expression is derived from the central helper.
- Confirmed retail-code links expose a non-null opaque ID; unknown or incomplete
  links expose `person_id: null` and never trigger a history lookup.
- In development without a configured key, overview/evolution/summary/trend/
  stores remain available while identity endpoints return generic 503. Production
  startup remains fail-closed. An absent or exactly empty development/test value
  is allowed; any non-empty invalid value, including whitespace, remains a
  configuration error and is never normalized into an absent key.
- The actual SQL helper equivalence test runs against the isolated PostgreSQL
  fixture and covers synthetic private IDs, fallback names, whitespace, Unicode
  and case normalization.
- Real ASGI contract tests exercise the mounted FastAPI routes with dependency
  overrides only in memory. They verify that serialized identity responses omit
  private matching fields, return the generic 503 when the key is absent, and
  reject an unexpected response field. Dedicated isolated PostgreSQL tests cover
  the summary, opaque-history, generic-record and retail-link queries, including
  a confirmed link whose display name is empty but whose valid opaque ID remains
  usable.
- The final test hardening corrected the query aliases used by the SQL HMAC
  expression; this is a query-only correction, with no schema, migration, import
  or matching-data change. Because canonical identity rules did not change, the
  prior production reconciliation remains applicable and was not re-run.
- Final local CI-equivalent gate: 766 passed, 7 skipped, one pre-existing
  duplicate OpenAPI operation-ID warning; `services/salarii.py` coverage is
  100 percent (minimum 98 percent). Mypy checked 203 source files with no
  errors; frontend tests, typecheck and staged production build passed.
- CI run #295 failed because the backend coverage gate measured
  `services/salarii.py` below its 98 percent threshold, despite no test failure.
  The new branch coverage tests raise it to 100 percent in the local CI-equivalent
  run: 750 passed, 7 skipped; the critical coverage gate passes.
- Frontend tests: 177 passed; typecheck and a staged, non-deployed production
  build passed. Mypy passed for 199 source files.
- `.env` and `.env.worker` were not modified; no schema migration, production write, deploy or service restart was performed.

## 2026-08-11 monetary and export boundary

Salary money is now retained as quantized `Decimal` through repository,
service and Pydantic response models; JSON uses decimal strings and no backend
salary total is converted to binary float. Sensitive XLSX exports are generated
only by the dedicated `salary_exports` worker from a canonical, owner-bound
request on `arq:retail:salary-exports`. Its database LOGIN inherits only
`unihub_salary_export`: exact salary/reporting columns plus kind-scoped RLS over
the durable operation rows. The generic operations/export worker cannot read
salary sources or salary operations. Artifacts use the private `salary/`
namespace, masked by systemd from non-salary workers.

The workbook never contains `person_id`, CNP or private matching data.
Migrations 065/066 record the authenticated subject, request hash, actual
rendered row count, artifact SHA-256, size, generation/expiry timestamps and
preserve that evidence across expiry or an attested integrity failure. A
client-supplied `row_count` is rejected.
