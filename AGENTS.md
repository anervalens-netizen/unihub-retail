# UniHub Retail

## Fast lane pentru schimbări mici

- Pentru schimbări UI mici, corecții locale, configurări/documentație și date punctuale, favorizează finalizarea în 5–10 minute, fără a sacrifica corectitudinea.
- `pr-fast` are ținta normală **sub 10 minute**. Timeout-ul de 15 minute este
  doar un guardrail, nu o țintă și nu se mărește pentru a acomoda mai multă
  muncă.
- Selectorul backend folosește bugetul evidence-based
  `MAX_PR_FAST_SELECTED_TEST_FILES = 120`; fan-out-ul peste 120 devine
  `ESCALATION_REQUIRED` către PR-DEEP și nu execută suita supradimensionată în
  `pr-fast`.
- Flux implicit: inspectează strict zona afectată, implementează, rulează un singur set de verificări țintite, fă un singur deploy când este în scope, apoi verifică exact comportamentul cerut și health-ul.
- Nu crea framework-uri, scripturi generice, migrații, medii temporare, documentație nouă, screenshot-uri sau suite complete de teste decât dacă sunt strict necesare rezultatului.
- Nu repeta lint, typecheck, build sau teste pe același conținut neschimbat; reutilizează dovezile încă valide și păstrează output-ul compact.
- Nu face rerun-uri oarbe ale failure-urilor sau timeout-urilor neschimbate:
  diagnostichează cauza înainte de a relua și reutilizează dovezile încă valide
  pentru același SHA exact.
- `FULL` se execută numai când politica trackerului justifică un checkpoint,
  un release/promotion, un control-plane high-risk, o incertitudine nerezolvată
  sau o cerere explicită; nu este ritual pentru fiecare PR/merge.
- Eficiența este o cerință de corectitudine: o poartă care transformă
  `pr-fast` într-un mini-FULL este defectă chiar dacă verificarea individuală
  este validă.
- Nu instala instrumente sau browsere pentru o validare minoră dacă există deja o cale directă de verificare.
- Extinde investigația numai când ruta simplă este blocată, riscul este ridicat sau verificarea țintită eșuează; explică motivul într-o singură frază.
- Porțile obligatorii specifice proiectului rămân valabile când schimbarea le activează direct; „proportionate checks” nu înseamnă automat toate verificările disponibile.

## GitHub Actions budget

- Run checks locally first; trusted CI uses the isolated repo-scoped Dell build
  runner, never the production deploy runner.
- Markdown and `docs/**` changes must not trigger the heavy PR verification
  workflows (`ci`, high-risk governance, or PR-DEEP policy) under the current
  no-native-required-checks model. Runtime/code changes retain their existing
  verification paths.
- Push one verified candidate and never rerun historical failures. Reuse still-
  valid exact-SHA evidence; do not repeat checks on unchanged content merely for
  ceremony.
- GitHub-hosted execution follows the global USD 1 per-task ceiling.

Retail is the source of truth for retail sales, targets, campaigns, salaries, visits reporting, and the active Grile UI.

Read `APP_ARCHITECTURE.md` for module boundaries and `README.md` for setup.
For promo, incentive, or contest work, read
`docs/RUNBOOK-campanii-promo-incentive-concursuri.md`; for salary-grid work,
read the focused salary documents under `docs/`.
For the monthly official HR salary import, follow
`docs/RUNBOOK-import-salarii-HR.md`; always dry-run both companies, validate
the manifest and reconcile HR before any apply. At the P0 baseline, live salary
apply is NO-GO until the eight known groups are reconciled.

## Runtime

- Service: `unihub-backend.service`
- Worker: `unihub-worker.service`
- Public URL: `https://retail.unihub.ro`
- Database: `unihub_postgres:5432`, DB `unihub`
- Frontend build output: `dist/`

```bash
npm run typecheck
npm run complexity:ts
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

- Backend flow defaults to router -> service -> repository. The truthful hybrid
  exceptions (query services, transaction scripts and orchestration boundaries)
  are explicit in `backend/architecture_contract.json`; CI rejects unclassified
  service DB access and stale exceptions. Keep SQL and business logic out of routers.
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
- Server-side XLSX downloads use the bounded spool/chunked response path; do
  not replace it with `BytesIO.getvalue()` or a one-chunk `StreamingResponse`.
  Review PostgreSQL workload monthly with the read-only
  `backend/scripts/report_pg_stat_statements.py`, and optimize only a proven
  user-facing query with EXPLAIN/BUFFERS plus an unchanged business hash.
- Frontend RUM reports only LCP and INP as low-cardinality Sentry distributions;
  do not attach URLs, user IDs or unbounded labels. A release that changes PWA
  behavior must pass the browser lifecycle gate N -> N+1 -> rollback to N.
- Salary endpoints are backend-gated. Access is limited to `unihub-manager`,
  `unihub-admin`, `authentik Admins`, and the reserved future `unihub-hr`
  group. Agents and Team Leaders must receive 403.
- Shared Google API clients are not thread-safe. Build one service per worker thread and keep conservative concurrency.
- The Retail ARQ worker serializes heavy jobs (`ARQ_MAX_JOBS=1` by default).
  Web startup and authenticated reads must not require the optional ARQ queue;
  only enqueue/status boundaries map typed queue transport failures to bounded
  503 responses. A durable terminal DB state wins over ephemeral ARQ state.
- Runtime config is parsed per web/operations/import process. Keep
  `DB_LOCK_TIMEOUT_MS < DB_STATEMENT_TIMEOUT_MS`, at least two web DB
  connections, ARQ connection budget <=3s, result retention at least as long
  as the job/completion window, and systemd `TimeoutStopSec` at least 60s above
  the worker completion wait.
- Every Dashboard route uses one request-wide monotonic deadline created before
  pool resolution. Keep `DASHBOARD_REQUEST_DEADLINE_MS` at 2500ms by default
  and never above 3000ms; bound acquire plus every query by the remaining
  budget, cancel/await all children, and propagate client cancellation.
- Canonicalize Dashboard `site_code` once at the API boundary: trim, drop
  empty/sentinel tokens and exact duplicates, preserve case and first order.
  Target v2 requires complete, uniform per-store forecast coverage; missing or
  nonuniform coverage is a 409 before any scenario/revision write and is never
  converted to zero.
- Business dates/months use the injectable aware clock in
  `backend/business_clock.py` and `Europe/Bucharest`; persist instants in UTC,
  reject naive datetimes and use monotonic time for durations.
- Sales imports use Stage -> Validate -> Promote. A generation manifest contains
  source/cutoff/control totals, site-day coverage and a business hash. Lease
  loss fences the writer; promote and rollback use owner fencing and CAS.
- A source or worker error must not replace the last good generation. Missing
  source data is an explicit anomaly, never an implicit zero. The same source
  hash and spool are reused for a retry.
- P&L/TVA dry-run is scoped to (company, period), uses Decimal and
  effective-dated rules, and records source/input/rule/model/output hashes.
  Finance actuals, estimates and finalized Target scenarios are protected until
  a separately approved live promotion.
- Salary imports require exact 13-digit CNP plus checksum, reject blank or
  conflicting identity data before writes, and persist source-line provenance.
  The dry-run manifest must include both companies without CNP. Identity and
  salary writes are one transaction; any fault rolls back the batch.
- Promo config and POS actuals are validated and materialized into an immutable
  generation before the atomic `current.json` pointer switch. The switch uses
  a file lock and pointer-hash CAS; missing/tampered sources or stale writers
  never replace the last good generation. Runtime must reverify every source
  hash before using it.
- Contest identity is explicit per contest: `site_agent` preserves a separate
  row per store and normalized agent, while `person_id` requires a confirmed
  salary link. Never merge homonyms or transfer sales across stores by name.
- Grile observations are append-only. Full runs and per-store refreshes reserve
  and claim the store generation before Google I/O; only the winning fenced
  writer may update the current projection. Persist last success, last error
  and stale age separately; structural v3 failures remain auditable.
- Never log or put CNP in API, metrics, manifests, diffs or handoff messages.
- Documentation is updated after every P0 lot with the exact SHA, migration
  manifest checksum, evidence commands and real limits.

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
- Promo cutoff cannot regress within the active generation. Actuals are
  cumulative only through cutoff; the receipt rule may cover only the tail
  after cutoff. A configured source failure is never converted into zero or an
  implicit legacy fallback.
- Visits are grouped by the visit author's Team Leader snapshot, not the store ASM. Enrich store hierarchy from current `stores`.
- PostgreSQL `fieldops_visits` is the only production visit source. Production
  config must reject SQLite and shadow comparison; the SQLite file is archive only.
- Retail reads visits from FieldOps-owned PostgreSQL `fieldops_visits` with
  SELECT-only access. SQLite is a retained pre-cutover archive, never a runtime
  fallback; photo bytes remain on the protected filesystem.

## Deployment

- Cererea explicită din conversația operațională autorizează agentul să ducă
  sarcina cap-coadă, fără aprobări repetate, dar nu înlocuiește porțile tehnice.
- Orice modificare runtime folosește `ADR-006`: branch/PR, CI exact-SHA,
  artefactul acelui run, digest verificat, deploy formal și probe.
- Nu face push direct în `main` pentru cod, migrări, frontend, systemd, workers,
  proxy, auth sau date. Nu deploya checkout local și nu reconstrui artefactul pe
  server.
- Calea fără artefact este permisă numai pentru documentație non-runtime.
  Break-glass este rezervat incidentelor active și nu este permis pentru schema
  DB, auth/permissions, importuri, salarii, Grile destructive, rețea sau release
  tooling.
- Un PR deja autorizat se duce autonom prin remedierea CI, review, merge, CI pe
  noul `main`, deploy și verificare live; operatorul nu trebuie să repete
  aprobarea la fiecare etapă.
- Frontend changes are not live until buildul din artefactul CI este instalat.
- Backend changes require `unihub-backend.service` restart.
- Worker/job changes also require `unihub-worker.service` și/sau
  `unihub-import-worker.service` restart.
- Verify local health, metrics and the changed user path after deployment.
- Vezi `docs/adr/006-verified-runtime-delivery.md` și runbookurile din
  `docs/operations/`.
