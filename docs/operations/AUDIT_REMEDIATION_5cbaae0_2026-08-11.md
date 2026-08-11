# Audit remediation — snapshot 5cbaae0 — 2026-08-11

## Scope

This run closes the 11 findings from the independent static audit of
`5cbaae0e22ac2bbe2a5d7c2223672c1aa4273d5d`. The previously deployed runtime
source was `2cb2785c2340b901e07af7fcf40241e5bfd3555e`. No finding requires a rewrite;
the changes preserve the existing BFF, DB-authority, worker fencing and
immutable-artifact architecture.

Until the exact candidate is merged, CI-built and deployed, every status below
means **implemented and locally verified**, not production-closed. The release
evidence section is deliberately incomplete until the formal gates produce
immutable identifiers.

## Finding reconciliation

| ID | Control | Verification |
| --- | --- | --- |
| UH-01 High | Box-constrained Decimal allocator solves floors and caps simultaneously; cent remainder is deterministic; bound flags are rebuilt from the final result. | Exact `50/54/6` regression, property matrix, zero-weight/permutation/flags cases and 8/8 targeted mutations. |
| UH-02 Medium | Every failed import attempt keeps the exact queued bytes for deterministic ARQ retry. Retry adopts an exact validated generation whether retain failed before or after the filesystem move, then idempotently completes content-addressed retain and DB acknowledgement without restaging or worker restart. | Stage-failure retry over identical bytes, pre-move fsync/ENOSPC window, fault injection after `Path.replace` and before DB retain acknowledgement, artifact lifecycle/import suites. |
| UH-03 Medium | All active units use `ProtectSystem=strict`, `PYTHONDONTWRITEBYTECODE=1` and exact authority-specific write directories; `/opt/Mobiup` and release/code/config ancestors are absent. The web process remains read-only to export artifacts: integrity failures are marked in DB and cleanup is routed to the owning generic/salary worker, with its periodic orphan sweep as fallback. The salary namespace is hidden from every non-salary authority. | `systemd-analyze verify`, checked-in allowlist/mount-mask regression, cross-namespace cleanup rejection and deploy/rollback sandbox. Dedicated OS service users remain a separately owner-authorized identity migration. |
| UH-04 Medium | Callback requires equal `(iss, sub)` for independently verified access/ID tokens; refresh requires continuity with the encrypted session record and fails closed. | Callback and refresh issuer/subject mismatch tests; finite mismatch metric. |
| UH-05 Medium | Startup prewarms JWKS; readiness accepts fresh or bounded-stale validated keys and rejects absent/expired failed bootstrap; finite one-hot state metric. | Startup/readiness and cache-state tests. |
| UH-06 Low | The pre-parser 413 path now applies request ID, security/no-store headers, bounded CORS and request metrics just like normal responses. | Content-Length and streamed/chunked oversize contract tests. |
| UH-07 Low | SIGTERM refuses new refresh ownership, drains current local refresh tasks, then cancels/awaits overdue tasks before Valkey/HTTP shutdown. | Bounded shutdown-drain tests. |
| UH-08 Low | Frontend Sentry uses explicit recursive redaction for events and transactions, disables default PII, removes complete route/transaction/span paths that can contain stable IDs and keeps captured API bodies non-enumerable. | Token/header/query/body/path redaction tests, including salary person IDs, and typecheck. |
| UH-09 Low | Salary money stays quantized Decimal (0.01; ratios 0.0001) through backend contracts and is emitted as decimal strings. | Exact `0.10 + 0.20 = "0.30"` API regression and salary suite. |
| UH-10 Low | Multi-select values use repeated query parameters; commas are ordinary data; exact duplicates are removed and `site_code` dominates hierarchy. Durable export campaign and incentive loaders preserve the normalized value sequences through the same canonical scoped builders instead of collapsing them into CSV. | Frontend URL/deep-link/filter tests, 141-test backend filter set and exact multi-firm/store/agent export regressions. |
| UH-11 Low | Salary exports are owner-bound durable operations on their own queue, worker, DB authority and filesystem namespace. PostgreSQL column grants/RLS prevent the generic worker from reading salary sources or salary operation rows. The server records canonical request, actor, actual rows, artifact SHA-256/size, timestamps and expiry; browser row counts are forbidden. | Migrations 065/066, authenticated authority matrix, privacy/formula/digest workbook test, API reservation test, retryable UI operation ID and export lifecycle suite. |

## Target production reconciliation

At `2026-08-11T18:42:04+03:00`, production was queried read-only for every
scenario whose rows contain at least one `is_floor_limited` and at least one
`is_cap_limited`. Result: **0 scenarios**. Therefore there is no affected draft
or finalized month, no dry-run delta to approve and no business-data write to
perform. This result must be rechecked immediately before deploy; if non-zero,
stop promotion and generate a per-store old/new Decimal diff before any target
mutation.

Canonical query (run through the existing protected PostgreSQL path, never with
credentials in output):

```sql
SELECT ts.id, ts.target_month, ts.status,
       bool_or(tr.is_floor_limited) AS has_floor,
       bool_or(tr.is_cap_limited) AS has_cap,
       count(*) AS stores
FROM target_scenarios AS ts
JOIN target_scenario_rows AS tr ON tr.scenario_id = ts.id
GROUP BY ts.id, ts.target_month, ts.status
HAVING bool_or(tr.is_floor_limited) AND bool_or(tr.is_cap_limited)
ORDER BY ts.id;
```

## Migration and rollout order

Migrations `065_salary_export_evidence.sql` and
`066_salary_export_authority.sql` are additive. 065 extends the existing
`export_operations` kind constraint, adds nullable `row_count`, requires a real
worker-attested row count for completed salary artifacts and makes it immutable
across download, expiry and integrity-failure transitions. Existing daily
exports remain valid with `row_count = NULL`. 066 requires the exact preprovisioned
NOLOGIN authority `unihub_salary_export`, grants only the source columns needed
by the renderer and enables kind-scoped RLS. The authenticated LOGIN
`unihub_salary_export_worker` and its root-protected DSN are an explicit
identity/credential gate and are never created by a migration.

Formal release order:

1. re-run the read-only mixed-bound Target query and require zero rows;
2. merge only after PR exact-SHA CI passes all required gates;
3. run exact-main CI and use only its signed immutable release artifact;
4. verify backup/restore evidence, artifact digest and migration manifest;
5. provision/verify the dedicated salary-export authority, LOGIN and secret;
6. apply migrations 065/066 through `unihub-retail-migrate.service`;
7. deploy the matching frontend, backend and all changed worker/systemd units;
8. verify local/public liveness/readiness, JWKS state, six Prometheus targets,
   queues, logs and protected routes;
9. exercise a controlled authenticated salary export and verify DB row count,
   digest, owner, download and expiry without exposing salary values;
10. verify the Target exact regression through the deployed code path or a
   release-artifact test, without creating/finalizing production scenarios.

Rollback restores the prior exact artifact and unit set. Migrations 065/066 and
the dedicated NOLOGIN authority remain; they are backward-compatible with the
prior code and must not be removed. Before a
rollback, require no queued/running salary export operation; an active operation
is allowed to terminalize or is cancelled through its owner-bound API. No
Target, salary, Finance or import business data is rolled back by direct SQL.

## Local evidence before PR

- Isolated PostgreSQL backend suite: 1,904 passed, 7 skipped; 81.93% global
  coverage. The six subsequently added OIDC/solver critical-branch cases pass
  in their 38-test focused run.
- Critical coverage: OIDC verifier 97.03% (minimum 95%); Target calculations
  97.37% (minimum 97%); backend changed-line coverage 86.13% (minimum 80%).
- Target mutation gate: 8/8 killed (100%), including simultaneous floor/cap
  active-set recomputation and largest-remainder order.
- Frontend: 63 files / 372 tests passed; changed-line coverage 87.78%; typecheck,
  lint, production build, RUM artifact verification and bundle budget passed.
- Browser/accessibility/responsive suite: 53 Chromium cases passed; Firefox and
  WebKit smoke: 12/12 passed.
- Security and supply chain: pip/npm audits report zero known vulnerabilities;
  tracked-secret and Bandit gates passed; reproducible CycloneDX validation
  passed for 60 Python and 154 npm runtime components.
- Contracts: migration manifest, OpenAPI hash
  `420756d13c95101303697ebcec05ab83fe1679c27203c4589031e6d537cb6844`,
  104-variable/7-template environment schema, architecture, complexity,
  shellcheck and vendored-package integrity passed.
- Operations: systemd units, sudoers, Caddy, 25 Prometheus rules and rule tests,
  six-target scrape topology and exact-SHA deploy/reverify/rollback/recovery
  sandbox passed.
- Review-closure delta: 60 prior focused backend checks passed (3 isolated-DB
  skips); the final multi-select review closure passed 117 campaign/export/filter
  checks locally with one destructive isolated-PostgreSQL case delegated to PR
  CI. Telemetry privacy 3/3, mypy 445 modules, architecture 274 modules,
  complexity, Bandit, tracked-secret, typecheck and lint gates passed. The
  export extraction reduced both touched legacy complexity allowances; no
  threshold was relaxed.

These counts are diagnostic only. Final authority is the unchanged candidate's
PR CI, exact-main CI, artifact attestation, deployment run and live probes.

## Exact release evidence

Fill only from successful tooling output after the gates complete:

| Evidence | Value |
| --- | --- |
| Candidate SHA | pending |
| PR / PR CI run | pending |
| Merge SHA / exact-main CI run | pending |
| Release archive / SHA-256 | pending |
| Migration manifest SHA-256 | `b29fa8db12ac459a58f25313bd5ab0b2e2199e26c1cb733ef4f37df2eb5b5c60` (candidate-local; reverify on merge SHA) |
| Restore evidence SHA-256 | pending |
| Deploy run / rollback handle | pending |
| Production runtime SHA | pending |
| Post-deploy Target mixed-bound count | pending |
| Post-deploy salary export evidence | pending |
