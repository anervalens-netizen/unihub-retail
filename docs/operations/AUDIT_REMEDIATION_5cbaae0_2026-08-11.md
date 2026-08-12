# Audit remediation — snapshot 5cbaae0 — 2026-08-11

## Scope

This run closes the 11 findings from the independent static audit of
`5cbaae0e22ac2bbe2a5d7c2223672c1aa4273d5d`. The previously deployed runtime
source was `2cb2785c2340b901e07af7fcf40241e5bfd3555e`. No finding requires a rewrite;
the changes preserve the existing BFF, DB-authority, worker fencing and
immutable-artifact architecture.

The formal release completed on `2026-08-12`. Runtime source
`2ea096daccf1c00289ac7cf7f1d9b505b9f6e0ca` is the exact signed artifact from
successful main CI and all controls below are production-live. The only
outstanding evidence item is one authenticated operator salary-export smoke;
the implementation, dedicated authority, worker, queue and automated export
lifecycle gates are closed.

On `2026-08-12`, the owner explicitly authorized the OS/DB identity migration
and creation of the dedicated salary-export credential. This authorization
does not permit salary/Finance business-data promotion and no credential value
is stored in Git or evidence.

## Finding reconciliation

| ID | Control | Verification |
| --- | --- | --- |
| UH-01 High | Box-constrained Decimal allocator solves floors and caps simultaneously; cent remainder is deterministic; bound flags are rebuilt from the final result. | Exact `50/54/6` regression, property matrix, zero-weight/permutation/flags cases and 8/8 targeted mutations. |
| UH-02 Medium | Every failed import attempt keeps the exact queued bytes for deterministic ARQ retry. Retry adopts an exact validated generation whether retain failed before or after the filesystem move, then idempotently completes content-addressed retain and DB acknowledgement without restaging or worker restart. | Stage-failure retry over identical bytes, pre-move fsync/ENOSPC window, fault injection after `Path.replace` and before DB retain acknowledgement, artifact lifecycle/import suites. |
| UH-03 Medium | All active units use distinct locked nologin OS users, `ProtectSystem=strict`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHON_DOTENV_DISABLED=1` and exact authority-specific write directories; `/opt/Mobiup` and release/code/config ancestors are absent. Four setgid groups carry only the required spool/promo/Grile/export artifacts at `2770/0660`. Import-spool directories stay import-owned, while files accept only the legitimate web/import producer owners preserved across retain. Web remains read-only to exports; the salary namespace is hidden from every non-salary authority. Deploy normalizes source modes from the Git index and installs frontend files read-only as `root:unihub-web`. | Exact User/Group/SupplementaryGroups/UMask/environment regression, provisioning verifier, `systemd-analyze verify`, checked-in allowlist/mount-mask regression, arbitrary-owner rejection, web-upload same-SHA reverification, restrictive-umask source/frontend regression, cross-namespace cleanup rejection and deploy/rollback sandbox. |
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

The same canonical query was repeated after deployment on `2026-08-12` and
again returned **0 scenarios**. The deployed pure calculation path also
returned exactly `50.00 / 54.00 / 6.00`, with only `FLOOR_APPLIED` on the first
row and no warnings.

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
5. provision/verify the seven OS identities, shared groups, dedicated salary-export authority, LOGIN and secret;
6. apply migrations 065/066 through `unihub-retail-migrate.service`;
7. deploy the matching frontend, backend and all changed worker/systemd units; after backup and stop, atomically enforce persistent artifact ownership before startup;
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

## 2026-08-12 deployment incident and corrective control

PR `#144` merged as `741efe8090a636571c1c02280ec7c3294df189a6`, but
the exact-main release was cancelled after Codex review identified a legitimate
web-owned retained-spool case rejected by the deploy verifier. PR `#145` fixed
that boundary and merged as `d645827538e40ca54425794de531f47a7be49bb8`.
Exact-main CI `31579134546` passed and produced release digest
`ad77cd1cba1fc644990a018bbd0faec6d02ce980a4548904cdb682f968dcfa49`.

The first formal deployment exposed two release-tooling assumptions hidden by
the former shared OS identity: Python bootstrap re-opened repository `.env`
files after systemd had already loaded the authority-specific environment, and
artifact extraction under deploy `umask 077` left source/frontend paths
unreadable to the new identities. No salary, Target, Finance or import business
data was changed. Migrations 065/066 applied successfully during controlled
roll-forward; all six services and the public route were restored, while the
release record remained `recovery_required` pending a versioned correction.

The corrective candidate disables Python dotenv loading in every active unit,
normalizes tracked source modes exactly from the Git index, installs frontend
content as `root:unihub-web` `0750/0640`, and verifies the same contracts during
deploy, same-SHA reverify and rollback. The isolated deploy/rollback/recovery
sandbox reproduces restrictive `0700/0600` inputs and passes. Exact hotfix SHA,
CI, artifact, deploy handle and live probes are recorded below.

Hotfix PR `#146`, candidate
`1ecdfedc9e2ebd5ed7b9dcf5391e23017d46744f`, passed exact-head CI
`31583659410` and Codex review with no material findings. It merged as
`2ea096daccf1c00289ac7cf7f1d9b505b9f6e0ca`; exact-main CI `31585029438`
passed every backend, frontend, real E2E, browser, restore, mutation,
supply-chain and release-artifact job. Formal deploy `31586605814` completed
successfully. The temporary runtime dotenv drop-ins were moved to the
root-protected recovery backup after versioned units were active.

The new salary-export metrics listener required one host-network exception.
Only `172.23.0.0/16 -> 172.23.0.1:9905/tcp` was allowed, with backup
`/opt/Mobiup/ops/backups/firewall/20260812T092747Z-retail-salary-metrics`;
the resulting `/etc/ufw/user.rules` SHA-256 is
`28575ddfbb740673f0873583546a35a2e9a54334a22b85d5323941e90f8eaf58`.

Post-deploy probes: local and public health/readiness `200`, public sensitive
surfaces `404`, unauthenticated Target route `401`, JWKS state `fresh` on both
web workers, all six Prometheus targets `UP`, all six services active with zero
restarts and zero error-priority journal entries since deployment. The OS and
salary DB provisioning verifiers pass, migrations 065/066 match their immutable
checksums, salary queued/running count is zero, source checkout is clean at the
runtime SHA, and frontend ownership/modes are `root:unihub-web` `0750/0640`.

## Exact release evidence

| Evidence | Value |
| --- | --- |
| Candidate SHA | `1ecdfedc9e2ebd5ed7b9dcf5391e23017d46744f` |
| PR / PR CI run | PR `#146` / `31583659410` (success) |
| Merge SHA / exact-main CI run | `2ea096daccf1c00289ac7cf7f1d9b505b9f6e0ca` / `31585029438` (success) |
| Release archive / SHA-256 | `retail-release-2ea096daccf1c00289ac7cf7f1d9b505b9f6e0ca.tar.gz` / `82844620558bf7fda73d1cdbafec1959b64133f0b0750f0b6473df4ef160ef05` |
| Migration manifest SHA-256 | `b29fa8db12ac459a58f25313bd5ab0b2e2199e26c1cb733ef4f37df2eb5b5c60` |
| Restore evidence SHA-256 | `40cc0a49156a60f1bb8cdf21c814a89ca7778c743099c7e0bfa62c442a665e5d` |
| Deploy run / rollback handle | `31586605814` / `/opt/Mobiup/ops/backups/retail-deploy/20260812T101553Z-d645827538e4-to-2ea096daccf1-9bdd870fbda3b14f` |
| Production runtime SHA | `2ea096daccf1c00289ac7cf7f1d9b505b9f6e0ca` |
| Post-deploy Target mixed-bound count | `0`; deployed regression `50.00 / 54.00 / 6.00` |
| Post-deploy salary export evidence | Authenticated operator smoke pending; dedicated OS/DB authority verified, worker and Prometheus target `UP`, queued/running `0`, automated lifecycle gates successful |
