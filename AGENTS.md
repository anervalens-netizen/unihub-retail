# UniHub Retail

Retail is the source of truth for retail sales, targets, campaigns, salaries, visits reporting, and the active Grile UI.

Read `APP_ARCHITECTURE.md` for module boundaries and `README.md` for setup. Read focused documents under `docs/` for salary-grid or campaign work.

## Runtime

- Service: `unihub-backend.service`
- Worker: `unihub-worker.service`
- Public URL: `https://retail.unihub.ro`
- Database: `unihub_postgres:5432`, DB `unihub`
- Frontend build output: `dist/`

```bash
npm run typecheck
npm run test
pytest backend/tests/ -q
mypy backend/ --ignore-missing-imports --explicit-package-bases
npm run build
sudo systemctl restart unihub-backend
curl -fsS http://127.0.0.1:9898/health
```

Run validation sequentially; typecheck can race with a Vite build while `dist/` is regenerated.

Private `@unihub/*` packages use local Verdaccio. Keep the real token only in
the ignored `.npmrc`; copy `.npmrc.example` and provide `VERDACCIO_TOKEN` when
provisioning a new checkout. Never commit `.npmrc`.

## Architecture rules

- Backend flow is router -> service -> repository. Keep SQL and business logic out of routers.
- Use `reporting_*` tables/views for reporting. Raw `sales_transactions` is allowed only for explicitly documented cases such as cartela quantity.
- Retail excludes `Cartele` and locations matching `TR %` from normal retail KPIs.
- When `site_code` is selected it dominates historical scope; do not also constrain by current company/RM/ASM.
- Use canonical scoped-parameter builders. Do not leave unused asyncpg parameters.
- Sales imports replace the current monthly snapshot and rebuild reporting aggregates.
- Auth is Authentik OIDC. Do not add local login or remove `offline_access`.
- Shared Google API clients are not thread-safe. Build one service per worker thread and keep conservative concurrency.

## Business invariants

- Salary averages exclude agent-month values below 2,000 RON only from averages, not from totals/history.
- `total_salary` already includes meal vouchers.
- Agent target allocation uses store target / store selling days * agent selling days.
- Grile months use `YYYY-MM`; reset is irreversible, admin-gated, clears only documented editable ranges, and never recreates permanent links.
- Calculator Target has one draft per target month. Finalization requires all manager values and zero remaining allocation.
- Promo qualifying receipts and incentive quantity are distinct metrics; do not reuse one field for both meanings.
- Visits are grouped by the visit author's Team Leader snapshot, not the store ASM. Enrich store hierarchy from current `stores`.

## Deployment

- Frontend changes are not live until `npm run build`.
- Backend changes require `unihub-backend.service` restart.
- Worker/job changes also require `unihub-worker.service` restart.
- Verify local health and the changed user path after deployment.
