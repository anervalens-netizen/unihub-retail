# PR-fast lane (additive fast PR gate)

E1 adds one new self-hosted job `pr-fast` to `.github/workflows/ci.yml`. It
duplicates a selected fast subset of the existing exhaustive validation on
purpose: the repository has no native server-side branch enforcement, and
`main-push-policy.yml` is a detector, not perfect server-side prevention.
Release correctness must not depend on the assumption that a SHA previously
passed a PR-fast run, so the existing FULL content is preserved exactly.

## Active orthogonal gates (already on main)

- `.github/workflows/high-risk-governance.yml` — A3 PR metadata gate
  (`pull_request_target`, base-branch trusted code only, `ubuntu-latest`,
  5 min). Categories: `auth-identity`, `migrations-db-authority`,
  `deploy-release-ci`, `salary-private-identity`, `target-calculator`.
  Manifest: `.github/governance/high-risk-paths.json`.
- `.github/workflows/main-push-policy.yml` — detects unauthorized
  `push` events on `main` by validating parent commit and ancestry.

`pr-fast` complements both; it does not replace them.

## Triggers (current main, unchanged)

```yaml
on:
  workflow_dispatch:
  pull_request:
    branches:
      - main
```

There is no `push: branches: [main]` trigger.

## Job graph after E1

| Job | `if:` | `needs:` | timeout | Lane |
|---|---|---|---|---|
| `runner-isolation` | (PR from same repo) OR (dispatch + main) | — | 5m | shared |
| `pr-fast` | `pull_request` | runner-isolation | 15m | PR-fast |
| `backend-check` | `workflow_dispatch` + `refs/heads/main` | runner-isolation | 75m | FULL |
| `frontend-check` | `workflow_dispatch` + `refs/heads/main` | runner-isolation | 25m | FULL |
| `browser-smoke` | `workflow_dispatch` + `refs/heads/main` | runner-isolation | 20m | FULL |
| `integration-e2e` | `workflow_dispatch` + `refs/heads/main` | runner-isolation | 50m | FULL |
| `release-artifact` | `workflow_dispatch` + `refs/heads/main` | [backend, frontend, browser-smoke, integration-e2e] | 10m | release-only |

## Why additive duplication, not a move

- The repository does not enforce PR-only merges on `main`. Code can land
  via `git push` (with or without `main-push-policy` triggering).
- `main-push-policy` is a detector/compensating control, not a perfect
  server-side prevention mechanism.
- FULL on exact main must remain an independent exhaustive gate that does
  not assume the SHA previously passed PR-fast.
- Therefore E1 does NOT remove any existing step from `backend-check`,
  `frontend-check`, `browser-smoke`, `integration-e2e`, or
  `release-artifact`. The four upstream FULL jobs only gain the
  `workflow_dispatch + refs/heads/main` `if:` gate. `release-artifact` is
  untouched.

This means PR-fast and FULL overlap on roughly 20 backend static gates and
~7 frontend static gates. The duplication is the safety mechanism.

## What `pr-fast` duplicates (selected fast subset)

Backend (copied verbatim from current `backend-check`):

- `checkout` + `setup-python` + `Prepare Python environment`
- `Tracked secret regression scan` + `Bandit waiver governance` +
  `Python static security regression scan` (bandit) + `Python typecheck`
  (mypy)
- `Immutable migration manifest` + `OpenAPI contract drift` +
  `Environment schema and process templates` +
  `Versioned Retail edge request limits` (caddy validate)
- `Frontend dependency policy` + `Python complexity ratchet` +
  `Changed-function complexity gate` (PR-only via base SHA) +
  `Backend architecture boundaries` + `Shell static analysis`
- `Operational configuration validation` (systemd + promtool + scrape
  config) + `Upload Promtool cache evidence`
- `Exact-SHA deploy and rollback sandbox` (`ops/test-deploy-retail-artifact.sh`)
- `Targeted business mutation gate` (10 deterministic mutations covering
  target-calculator money/floor/cap/remainder)
- New PR-fast-only: `Runtime import smoke` (single-line `import auth; import
  main; import worker`, no second venv)
- `Upload mypy diagnostics` (on failure)

Frontend (copied verbatim from current `frontend-check`):

- `Verify pinned Node.js and npm` + `Verify vendored private packages` +
  `Install frontend dependencies` (`npm ci --include=dev`)
- `Frontend typecheck` + `TypeScript complexity ratchet` +
  `Frontend lint`
- `Bundle budget` (after build)
- New PR-fast-only: `Frontend unit tests without coverage` =
  `npm run test` (`vitest run` without v8 instrumentation) — same test
  files as FULL's `Unit tests with global coverage floor` minus the
  coverage instrumentation and threshold gates
- New PR-fast-only: `Build` (with PR DSN secret, separate from the FULL
  build that runs with the dispatch DSN)

## Why `vitest run` (no coverage) in PR-fast, coverage in FULL

`vitest run --coverage` with the 65/55/55/67 threshold gate stays in FULL
under `Unit tests with global coverage floor`. PR-fast runs the same test
suite without coverage instrumentation because:

- The FULL coverage gate must not be skipped on exact main releases.
- Coverage v8 instrumentation is heavy and not needed for behavior-regression
  coverage on PR.
- The behavior tests themselves (80 files, 657 tests) catch the same
  regressions in either mode.

## Behavioral matrix

| Event | runner-isolation | pr-fast | FULL jobs | release-artifact |
|---|---|---|---|---|
| `pull_request` (internal) | runs | runs | skipped | skipped |
| `pull_request` (fork) | skipped (existing fork guard) | skipped | skipped | skipped |
| `workflow_dispatch` + main | runs | skipped | runs sequentially | runs after all 4 FULL |
| `workflow_dispatch` (other ref) | skipped | skipped | skipped | skipped |

## Measured PR-fast wall-clock

See the E1 design report; ~6-8 min hot, ≤15 min budget.

## Release/deploy contract: unchanged

- `release-artifact` `if:`, `needs:`, `permissions:`, signing commands,
  artifact provenance — all byte-identical to current main.
- `.github/workflows/deploy.yml` is not modified.
- `.github/workflows/high-risk-governance.yml` is not modified.
- `.github/workflows/main-push-policy.yml` is not modified.
- `.github/workflows/artifact-cleanup.yml` is not modified.


## Conditional optimization gates (E1 amendment)

Two pr-fast gates are conditional. They remain fail-closed: any classifier
error fails the job, never silently skips.

### 1. Exact-SHA deploy and rollback sandbox

`scripts/is_high_risk_category_touched.py` decides whether the 187-second
`ops/test-deploy-retail-artifact.sh` step must run on a given PR.

Trigger sources (any one is sufficient):

1. **PR BASE SHA manifest** for `deploy-release-ci` in
   `.github/governance/high-risk-paths.json`. The manifest is loaded from
   the PR base SHA via `git show`, NOT from HEAD. A PR that modifies the
   governance manifest cannot weaken its own classification.
2. **Sandbox direct-input supplement** (fixed inline tuple in the
   classifier; runtime-CI semantics, NOT governance): `package.json`,
   `package-lock.json`, `unihub-worker.service`,
   `ops/observability/retail-process-scrape.yml`,
   `ops/observability/retail-slo-rules.yml`,
   `backend/requirements.lock`, `scripts/validate_release_sbom.py`.

Diff is computed from the **PR merge base** to HEAD using
`git diff --name-only --no-renames`, so renames away from governed paths
cannot hide the old path.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | TOUCHED → run `ops/test-deploy-retail-artifact.sh` |
| 10 | NOT_TOUCHED → skip with explicit log |
| 20 | ERROR → fail PR-fast |

The classifier itself is A3 deploy-release-ci governed
(see `high-risk-paths.json`).

### 2. Vitest affected mode

`vitest run --changed=<merge-base> --passWithNoTests` runs only tests
affected by the PR diff, unless any of these paths changed (forces full
`vitest run`):

- `package.json`, `package-lock.json`
- `vitest.config.ts`, `vite.config.ts`
- `tsconfig.json`, `tsconfig.*.json`
- any path under `src/test/` or `vendor/npm/`

The merge-base computation and git diff are bracketed with explicit
`set +e` / `set -e` and fail the PR-fast job on any error (no
`|| true`).

### Classifier self-test

`backend/tests/test_high_risk_category_touched.py` contains 25 durable
tests covering all 15 proof cases plus the new BASE-trust test (HEAD
manifest weakening must NOT skip). Run early in pr-fast via
`backend/venv/bin/python -I -m pytest -q backend/tests/test_high_risk_category_touched.py`.

### What does NOT change

- `runner-isolation` — unchanged
- `backend-check` (FULL) — unchanged (30 steps)
- `frontend-check` (FULL) — unchanged (23 steps)
- `browser-smoke` (FULL) — unchanged (7 steps)
- `integration-e2e` (FULL) — unchanged (8 steps)
- `release-artifact` (FULL) — unchanged (9 steps)
- `.github/workflows/high-risk-governance.yml` — unchanged
- `.github/workflows/main-push-policy.yml` — unchanged
- `.github/workflows/deploy.yml` — unchanged
- Tracked secret regression scan — still exhaustive in PR-fast
- `release-artifact` and exact-main release authority — unchanged

