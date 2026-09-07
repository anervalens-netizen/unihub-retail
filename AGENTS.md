# UniHub Retail

## Operating rule — smallest safe action

Default behavior is **product delivery with proportional verification**, not
ceremonial certification.

Canonical verification/cost policy:
`docs/engineering/verification-efficiency-policy.md`.

Before starting any expensive check (`PR-DEEP`, `FULL`, large-suite replay,
extra independent review), answer:

1. What concrete risk does it verify?
2. What materially new evidence will it add?

If there is no meaningful new evidence, do not run it. Owner waiting time,
self-hosted runner time and AI/model usage are engineering costs.

For bounded UI fixes, local corrections, config/docs and small changes, prefer
completion in minutes without sacrificing correctness. Do not create a new
framework, tracker, plan, temporary environment or audit unless the task truly
requires one.

## GitHub / verification routing

- `main` is server-side protected. Current ruleset requires PRs, merge commits,
  review-thread resolution and required status checks; there are no bypass
  actors.
- `pr-fast` is the normal code/runtime PR lane; target **under 10 minutes** and
  15 minutes remains a guardrail, not a target.
- Docs/Markdown-only work must not launch heavy code CI under the current
  paths-ignore model.
- `PR-DEEP` is an escalation lane. Run it only when the trusted native policy
  requires it for exact current HEAD/base or a concrete unresolved risk makes
  it necessary. Do not dispatch it merely because a change is runtime code.
- `FULL` is not a per-PR/per-merge ritual. Run it for formal release/deploy
  artifact creation, a deliberate checkpoint, a demonstrated unresolved
  cross-lane/control-plane question, or explicit owner request.
- Never default to `PR-DEEP -> merge -> FULL`. If PR-DEEP certified the relevant
  candidate and merge introduced the identical certified tree, no extra FULL is
  needed unless a release/checkpoint has a distinct purpose.
- Server status authority may be SHA-bound; technical test evidence is
  content/scope-bound. A new SHA alone does not invalidate every test result.
- Do not blindly rerun failures/timeouts. Diagnose job -> step -> log/artifact ->
  root cause first.
- Never lower thresholds, broaden snapshots or weaken gates only to make CI
  green.
- Do not repeat lint/typecheck/build/tests on unchanged relevant content merely
  for ceremony.
- GitHub-hosted execution follows the global USD 1 per-task ceiling.

Retail is the source of truth for retail sales, targets, campaigns, salaries,
visits reporting and the active Grile UI.

Read `APP_ARCHITECTURE.md` for module boundaries and `README.md` for setup. For
promo/incentive/contest work read
`docs/RUNBOOK-campanii-promo-incentive-concursuri.md`; for salary-grid work read
the focused salary docs. For monthly HR salary import follow
`docs/RUNBOOK-import-salarii-HR.md`; always dry-run both companies, validate the
manifest and reconcile HR before apply.

Historical audit trackers #159 and #226 (K1-K10 #227-#236) are completed
evidence. Do not resume them or invent a next audit item unless the owner
explicitly asks to revisit that history.

## Runtime

- Service: `unihub-backend.service`
- Worker: `unihub-worker.service`
- Public URL: `https://retail.unihub.ro`
- Database: `unihub_postgres:5432`, DB `unihub`
- Frontend build output: `dist/`

Typical local validation commands when relevant:

```bash
npm run typecheck
npm run complexity:ts
npm run lint
npm run test
pytest backend/tests/ -q
mypy backend/ --ignore-missing-imports --explicit-package-bases
npm run build
```

Do not run all commands automatically. Choose the smallest set relevant to the
change. Validation that regenerates `dist/` should remain sequential with
operations that read it.

Private `@unihub/*` packages are integrity-pinned tarballs under `vendor/npm/`.
Never commit `.npmrc` or Verdaccio tokens; run
`node scripts/verify_vendored_npm_packages.mjs` after package changes.

## Architecture rules

- Backend flow defaults to router -> service -> repository. Truthful hybrid
  exceptions are explicit in `backend/architecture_contract.json`; keep SQL and
  business logic out of routers.
- Use `reporting_*` tables/views for reporting. Raw `sales_transactions` is
  allowed only for documented cases such as cartela quantity.
- Retail excludes `Cartele` and locations matching `TR %` from normal retail
  KPIs.
- When `site_code` is selected it dominates historical scope; do not also
  constrain by current company/RM/ASM.
- Global filter UI exposes Firma / Manager / Magazin / Agent. `Manager` is the UI
  label for `regional`; do not re-add an ASM selector. Keep separate `regional`
  and `asm` source fields/report columns.
- Use canonical scoped-parameter builders. Do not leave unused asyncpg
  parameters.
- Every application DB connection sets PostgreSQL statement, lock and idle
  transaction timeouts. Change via documented `DB_*_TIMEOUT_MS`, not ad-hoc SQL.
- Sales imports replace the current monthly snapshot and rebuild reporting
  aggregates.
- Sales imports are admin-only and run in the worker. Uploads are bounded by
  `MAX_SALES_UPLOAD_BYTES`; one `processing` snapshot per month is the DB lease,
  and stale leases become failed audit entries.
- Auth is Authentik OIDC. Do not add local login or remove `offline_access`.
- Dashboard, Focus, Agenti, Vizite, Grile overview and filters require auth.
  Management-only modules and server-side exports require `unihub-manager`,
  `unihub-hr`, `unihub-admin` or `authentik Admins`.
- Business writes require `unihub-manager`, `unihub-admin` or
  `authentik Admins`. Official imports remain admin-only. Target Calculator
  calculate/edit/finalize remains owner-gated by configured allowlist.
- Risky/costly endpoints use `backend/rate_limits.py`; preserve rate limits on
  auth proxy, import uploads, server-side exports, Grile jobs, Target Calculator
  mutations and business writes.
- Server-side XLSX downloads use the bounded spool/chunked path; do not replace
  it with `BytesIO.getvalue()` or one-chunk `StreamingResponse`.
- Review PostgreSQL workload with read-only
  `backend/scripts/report_pg_stat_statements.py`; optimize only proven
  user-facing queries using EXPLAIN/BUFFERS plus unchanged business hash.
- Frontend RUM reports only LCP/INP as low-cardinality Sentry distributions; no
  URLs, user IDs or unbounded labels.
- Salary endpoints are backend-gated to `unihub-manager`, `unihub-admin`,
  `authentik Admins`, and reserved future `unihub-hr`; Agents and Team Leaders
  must receive 403.
- Shared Google API clients are not thread-safe. Build one service per worker
  thread and keep conservative concurrency.
- Retail ARQ worker serializes heavy jobs (`ARQ_MAX_JOBS=1` by default). Web
  startup/authenticated reads must not require optional ARQ; only enqueue/status
  boundaries map typed transport failures to bounded 503. Durable terminal DB
  state wins over ephemeral ARQ state.
- Runtime config is parsed per process. Keep
  `DB_LOCK_TIMEOUT_MS < DB_STATEMENT_TIMEOUT_MS`, at least two web DB
  connections, ARQ connection budget <=3s, result retention >= completion
  window, and systemd `TimeoutStopSec` >=60s above worker completion wait.
- Every Dashboard route uses one request-wide monotonic deadline before pool
  resolution. Keep `DASHBOARD_REQUEST_DEADLINE_MS` at 2500ms by default and
  never above 3000ms; bound acquire/queries by remaining budget, cancel/await
  children and propagate client cancellation.
- Canonicalize Dashboard `site_code` once at API boundary: trim, drop empty/
  sentinel tokens and exact duplicates, preserve case/order.
- Target v2 requires complete, uniform per-store forecast coverage; missing or
  nonuniform coverage is 409 before scenario/revision write, never zero.
- Business dates/months use injectable aware clock in `Europe/Bucharest`;
  persist instants UTC, reject naive datetimes and use monotonic time for
  durations.
- Sales imports use Stage -> Validate -> Promote. Manifest contains source/
  cutoff/control totals, site-day coverage and business hash. Lease loss fences
  writer; promote/rollback use owner fencing and CAS.
- Source/worker failure never replaces last good generation. Missing source data
  is explicit anomaly, never implicit zero. Reuse same source hash/spool for
  retry.
- P&L/TVA dry-run is scoped to `(company, period)`, uses Decimal/effective-dated
  rules and records source/input/rule/model/output hashes. Finance actuals,
  estimates and finalized Target scenarios remain protected until separately
  approved live promotion.
- Salary imports require exact 13-digit CNP + checksum; reject blank/conflicting
  identity before writes and preserve source-line provenance. Dry-run manifest
  includes both companies without CNP. Identity/salary writes are one
  transaction; any fault rolls back batch.
- Promo config/POS actuals are materialized into immutable generation before
  atomic `current.json` switch. Switch uses lock + pointer-hash CAS; missing/
  tampered sources or stale writers never replace last good generation. Runtime
  reverifies source hashes.
- Contest identity is explicit per contest: `site_agent` preserves row per store
  and normalized agent; `person_id` requires confirmed salary link. Never merge
  homonyms or transfer sales across stores by name.
- Grile observations are append-only. Full/per-store refreshes reserve and claim
  store generation before Google I/O; only winning fenced writer may update
  current projection. Persist last success/error/stale age separately.
- Never log or put CNP in API, metrics, manifests, diffs or handoffs.

## Business invariants

- Sales rows have no stable source-line identity. Identical visible values may
  be separate units on the same receipt; imports preserve multiplicity. See
  `docs/adr/004-sales-row-multiplicity.md`.
- Salary averages exclude agent-month values below 2,000 RON only from averages,
  not totals/history.
- `total_salary` already includes meal vouchers.
- Agent target allocation = store target / store selling days * agent selling
  days.
- Grile months use `YYYY-MM`; reset is irreversible/admin-gated, clears only
  documented editable ranges and never recreates permanent links.
- Grile checks have at most one `queued`/`running` run per month; reserve DB run
  before enqueue and expire abandoned reservations through heartbeat lease.
- Grile monthly closeout reserves a DB operation before enqueue. Only one
  monthly operation may run for a closing month. Live reset uses per-store
  checkpoint and blocks auto retry if stale checkpoint is `uncertain`.
- Target Calculator has one draft per month. Finalized months cannot be
  recalculated. Draft recalc/save/finalize use scenario revision; stale writes
  return 409. Finalization requires all manager values and zero remaining
  allocation.
- Promo qualifying receipts and incentive quantity are distinct metrics.
- Promo cutoff cannot regress in active generation. Actuals are cumulative only
  through cutoff; receipt rule covers only tail after cutoff. Source failure is
  never zero/implicit legacy fallback.
- Visits group by visit author's Team Leader snapshot, not store ASM. Enrich
  store hierarchy from current `stores`.
- PostgreSQL `fieldops_visits` is the only production visit source. SQLite is
  archive only, never runtime fallback; photo bytes remain protected filesystem.

## Deployment / production boundary

A request to implement or merge code does **not** automatically authorize a
release/deploy. Separate development from production promotion.

Normal code task:

```text
branch/PR -> proportional checks -> required native gates -> merge -> required post-merge policy -> STOP
```

If production release/deploy is explicitly in scope, follow ADR-006:

```text
certified main -> exact-main FULL release run -> immutable artifact/provenance
-> approval/deploy workflow -> health + changed-path verification
```

- Never push runtime code directly to `main`.
- Never deploy a local checkout or rebuild release source on the server.
- Do not start FULL merely because a merge occurred.
- Do not deploy/tag/release/migrate/restart production without explicit scope/
  authorization for that operation.
- Frontend is live only after release artifact build is installed.
- Backend release requires `unihub-backend.service` restart; worker changes may
  also require the relevant worker restart, but only as part of authorized
  deployment.
- Verify health/metrics and the changed user path after an actual deployment.
- See `docs/adr/006-verified-runtime-delivery.md` and `ops/README.md`.

## Planning

Use `.agent/PLANS.md`. Ordinary bounded work does not need an execution plan.
Substantial multi-session/high-risk/coordination-heavy work may use exactly one
living plan. Completed audit trackers are never default active plans.