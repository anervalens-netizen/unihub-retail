# PR-fast lane (current additive fast PR gate)

`pr-fast` is the repository's consolidated self-hosted fast feedback lane in
`.github/workflows/ci.yml`. It duplicates a bounded, selected subset of the
existing exhaustive validation on purpose: the repository has no native
server-side branch enforcement, and `main-push-policy.yml` is a detector, not
perfect server-side prevention. Release correctness must not depend on the
assumption that a SHA previously passed a PR-fast run, so the existing FULL
content is preserved exactly.

The normal target is **under 10 minutes**. The job timeout remains exactly
**15 minutes as a guardrail, not a target**. Efficiency is a correctness
requirement: large affected-backend fan-out escalates to PR-DEEP instead of
expanding `pr-fast`, and unchanged failures/timeouts are not blindly rerun.
Still-valid exact-SHA evidence is reused; `FULL` runs only when tracker policy
actually justifies it.

## Active orthogonal gates (already on main)

- `.github/workflows/high-risk-governance.yml` — A3 PR metadata gate
  (`pull_request_target`, base-branch trusted code only, `ubuntu-latest`,
  5 min). Categories: `auth-identity`, `migrations-db-authority`,
  `deploy-release-ci`, `salary-private-identity`, `target-calculator`.
  Manifest: `.github/governance/high-risk-paths.json`.
- `.github/workflows/main-push-policy.yml` — detects unauthorized
  `push` events on `main` by validating parent commit and ancestry.

`pr-fast` complements both; it does not replace them.

## Triggers (current)

```yaml
on:
  workflow_dispatch:
  pull_request:
    branches:
      - main
    paths-ignore:
      - "**/*.md"
      - "docs/**"
```

Markdown/docs-only pull requests do not launch the heavy PR verification
workflows under the current no-native-required-checks model. Runtime/code PRs
retain the normal `ci` path; high-risk governance and `pr-deep-policy` use the
same safe docs-only exclusion. There is no `push: branches: [main]` trigger in
this workflow.

## Current job graph

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
- PR-B3b backend affected coverage: trusted base selector over the exact
  candidate checkout; selected pytest plus the existing changed-line authority
  when safe, or `ESCALATION_REQUIRED` without executing the selected suite.
  The selector budget is `MAX_PR_FAST_SELECTED_TEST_FILES = 120`; a result
  above 120 routes to exact-head PR-DEEP.
- Current PR-fast-only: `Runtime import smoke` (single-line `import auth; import
  main; import worker`, no second venv)
- `Upload mypy diagnostics` (on failure)

Frontend (copied verbatim from current `frontend-check`):

- `Verify pinned Node.js and npm` + `Verify vendored private packages` +
  `Install frontend dependencies` (`npm ci --include=dev`)
- `Frontend typecheck` + `TypeScript complexity ratchet` +
  `Frontend lint`
- `Bundle budget` (after build)
- Current PR-fast frontend verification: affected `vitest run --coverage`
  with the existing changed-line coverage authority; test-infrastructure
  changes deliberately force the full frontend coverage path.
- Current PR-fast `Build` (with PR DSN secret), separate from the FULL build
  that runs with the dispatch DSN.

## Coverage and authority split

PR-fast uses affected frontend coverage and the existing changed-line gate for
ordinary PR diffs. The exact-main FULL lane retains its independent global
coverage thresholds and exhaustive frontend suite. Backend PR-fast coverage is
also selective only when the trusted selector proves the fan-out is within the
120-file budget; otherwise PR-fast emits `ESCALATION_REQUIRED` and does not
start the oversized selected backend suite. PR-DEEP remains the exhaustive
backend certification authority for that path.

## Behavioral matrix

| Event | runner-isolation | pr-fast | FULL jobs | release-artifact |
|---|---|---|---|---|
| `pull_request` (internal runtime/code) | runs | runs | skipped | skipped |
| `pull_request` (Markdown/docs-only) | skipped | skipped | skipped | skipped |
| `pull_request` (fork) | skipped (existing fork guard) | skipped | skipped | skipped |
| `workflow_dispatch` + main | runs | skipped | runs sequentially | runs after all 4 FULL |
| `workflow_dispatch` (other ref) | skipped | skipped | skipped | skipped |

## Measured PR-fast wall-clock and routing boundary

The evidence-based boundary is not a promise that every 120-file suite is
under 10 minutes. Validation PR #173 selected 111 backend test files and
completed in about 7m35s; C7 PR #184 selected 133 files, spent 11m38s in the
affected-backend step, and hit the 15-minute job timeout before completion.
Therefore selection counts above 120 escalate to PR-DEEP. More profiling is
required before changing the threshold; increasing the timeout is prohibited.

## Release/deploy contract: unchanged

- `release-artifact` `if:`, `needs:`, `permissions:`, signing commands,
  artifact provenance — all remain unchanged.
- `.github/workflows/deploy.yml` is not modified.
- `main-push-policy.yml` is not modified.
- `release-artifact` and exact-main FULL authority remain unchanged.


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

### PR-DEEP escalation authority

`PR-DEEP` remains a separate, manually dispatched, exact-head workflow for
`ESCALATION_REQUIRED`. It is the exhaustive backend certification authority
and is not hidden inside `pr-fast`. The selection budget only changes routing;
it does not weaken changed-line coverage, high-risk governance, architecture,
security, release, deploy, or exact-main FULL authorities.

### What does NOT change

- `runner-isolation` — unchanged for runtime/code PRs
- `backend-check` (FULL) — unchanged (30 steps)
- `frontend-check` (FULL) — unchanged (23 steps)
- `browser-smoke` (FULL) — unchanged (7 steps)
- `integration-e2e` (FULL) — unchanged (8 steps)
- `release-artifact` (FULL) — unchanged (9 steps)
- high-risk governance authority — unchanged; only redundant docs-only trigger
  execution is filtered
- `main-push-policy.yml` — unchanged
- `deploy.yml` — unchanged
- Tracked secret regression scan — still exhaustive in PR-fast
- `release-artifact` and exact-main release authority — unchanged

