# UniHub Retail

Retail is the source of truth for retail sales, targets, campaigns, salaries, visits reporting, and the active Grile UI.

Read `APP_ARCHITECTURE.md` for module boundaries and `README.md` for setup.
For promo, incentive, or contest work, read
`docs/RUNBOOK-campanii-promo-incentive-concursuri.md`; for salary-grid work,
read the focused salary documents under `docs/`.

## Runtime

- Service: `unihub-backend.service`
- Worker: `unihub-worker.service`
- Public URL: `https://retail.unihub.ro`
- Database: `unihub_postgres:5432`, DB `unihub`
- Frontend build output: `dist/`

```bash
npm run typecheck
npm run typecheck:strict
npm run lint
npm run test
pytest backend/tests/ -q
mypy backend/ --ignore-missing-imports --explicit-package-bases
npm run build
sudo systemctl restart unihub-backend
curl -fsS http://127.0.0.1:9898/health
```

Run validation sequentially; typecheck can race with a Vite build while `dist/` is regenerated.

Private `@unihub/*` packages are pinned as integrity-checked tarballs under
`vendor/npm/`, so clean checkouts and PR CI require no registry secret or
internal network. Local Verdaccio remains only the controlled source used when
publishing a new shared-package version. Never commit `.npmrc` or a Verdaccio
token; run `node scripts/verify_vendored_npm_packages.mjs` after package changes.

## Architecture rules

- Backend flow is router -> service -> repository. Keep SQL and business logic out of routers.
- Use `reporting_*` tables/views for reporting. Raw `sales_transactions` is allowed only for explicitly documented cases such as cartela quantity.
- Retail excludes `Cartele` and locations matching `TR %` from normal retail KPIs.
- When `site_code` is selected it dominates historical scope; do not also constrain by current company/RM/ASM.
- The global filter UI exposes Firma / Manager / Magazin / Agent. `Manager` is
  the UI label for `regional`; do not re-add an ASM selector. Keep the separate
  `regional` and `asm` source fields and report columns.
- Use canonical scoped-parameter builders. Do not leave unused asyncpg parameters.
- Every application DB connection sets PostgreSQL statement, lock, and idle
  transaction timeouts. Change them through the documented `DB_*_TIMEOUT_MS`
  variables, not ad-hoc SQL in repositories.
- Sales imports replace the current monthly snapshot and rebuild reporting aggregates.
- Sales imports are admin-only and always run in the worker. Uploads are
  bounded by `MAX_SALES_UPLOAD_BYTES`; one `processing` snapshot per month is
  the DB lease, and stale leases become failed audit entries.
- Auth is Authentik OIDC. Do not add local login or remove `offline_access`.
- Dashboard, Focus, Agenti, Vizite, Grile overview and filters require
  authentication. Management-only modules and server-side exports require
  `unihub-manager`, `unihub-hr`, `unihub-admin` or `authentik Admins`.
- Business writes (tasks, CRM recalculation, store target writes) require
  `unihub-manager`, `unihub-admin` or `authentik Admins`. Official imports
  remain admin-only, and Target Calculator calculate/edit/finalize remains
  owner-gated by the configured allowlist.
- Risky/costly endpoints use `backend/rate_limits.py`. Keep rate limits on
  auth proxy, import uploads, server-side exports, Grile jobs, Target
  Calculator mutations and business writes when changing these routes.
- Salary endpoints are backend-gated. Access is limited to `unihub-manager`,
  `unihub-admin`, `authentik Admins`, and the reserved future `unihub-hr`
  group. Agents and Team Leaders must receive 403.
- Shared Google API clients are not thread-safe. Build one service per worker thread and keep conservative concurrency.
- The Retail ARQ worker serializes heavy jobs (`max_jobs=1`), waits up to 60
  seconds for an active job on SIGTERM, and must close both ARQ and DB pools.

## Business invariants

- Sales rows have no stable source-line identity. Identical visible values can
  represent separate units on the same receipt, so imports must preserve row
  multiplicity and must not reject or deduplicate rows by the current Excel
  columns. See `docs/adr/004-sales-row-multiplicity.md`.
- Salary averages exclude agent-month values below 2,000 RON only from averages, not from totals/history.
- `total_salary` already includes meal vouchers.
- Agent target allocation uses store target / store selling days * agent selling days.
- Grile months use `YYYY-MM`; reset is irreversible, admin-gated, clears only documented editable ranges, and never recreates permanent links.
- Grile checks have at most one `queued` or `running` run per month. Reserve
  the DB run before enqueue; abandoned reservations expire through the
  documented heartbeat lease.
- Grile monthly closeout operations reserve a DB operation before enqueue.
  Only one monthly operation can run for a closing month. Live reset uses a
  per-store checkpoint and must block automatic retry if a stale checkpoint is
  `uncertain`.
- Calculator Target has one draft per target month. Finalized months cannot be
  recalculated. Draft recalculation, row saves, and finalization use the
  scenario revision; stale writes must return 409 instead of overwriting newer
  work. Finalization requires all manager values and zero remaining allocation.
- Promo qualifying receipts and incentive quantity are distinct metrics; do not reuse one field for both meanings.
- Visits are grouped by the visit author's Team Leader snapshot, not the store ASM. Enrich store hierarchy from current `stores`.
- PostgreSQL `fieldops_visits` is the only production visit source. Production
  config must reject SQLite and shadow comparison; the SQLite file is archive only.
- Retail reads visits from FieldOps-owned PostgreSQL `fieldops_visits` with
  SELECT-only access. SQLite is a retained pre-cutover archive, never a runtime
  fallback; photo bytes remain on the protected filesystem.

## Deployment

- Cererea explicită din conversația operațională autorizează implementarea,
  verificarea, commitul, sincronizarea, deployul și verificarea live pentru
  scopul cerut. Nu cere operatorului comenzi în terminal sau aprobări repetate.
- Calea implicită este local-first: verificări proporționale, commit direct pe
  `main`, push fără a aștepta CI, deploy controlat și verificare live. PR-ul și
  artefactul formal sunt opționale și se folosesc proporțional cu riscul.
- Push-ul direct în `main` este acceptat pentru schimbări obișnuite verificate.
  Dacă este deschis un PR, du-l fără o nouă confirmare prin CI, merge, deploy și
  verificare live. Vezi `docs/adr/005-chat-authorized-delivery.md`.
- Frontend changes are not live until `npm run build`.
- Backend changes require `unihub-backend.service` restart.
- Worker/job changes also require `unihub-worker.service` restart.
- Verify local health and the changed user path after deployment.
