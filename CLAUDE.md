# CLAUDE.md — UniHub Retail

**Phase: C3 COMPLETED + Hub filter/reporting fixes — 2026-05-07 | Server audit + optimization — 2026-05-19**

## Overview

Sursa de adevar pentru vanzari + vizite in ecosistemul MobiUp. Module: Hub, Focus, Agenti (+Salarii), Vizite, Management (Echipa/Magazine/Tasks/HR), Setari.

## Stack

- Frontend: React 19 + Vite 8 + TypeScript + TanStack Query + Tailwind 4
- Backend: FastAPI + asyncpg + PostgreSQL (unihub_postgres:5432/unihub)
- Auth: authentik OIDC (auth.unihub.ro) — JWT RS256 + JWKS validation
- Error tracking: GlitchTip (Sentry-compatible SDK, self-hosted)
- Test: pytest (backend), vitest (frontend)
- Registry: Verdaccio (npm.unihub.ro:4873) for @unihub/* packages
- Observability: Prometheus /metrics + structlog (opt-in via LOG_FORMAT)

## Deploy

- Path: `/opt/Mobiup/unihub-retail`
- Service: `unihub-backend.service`
- URL public: `https://retail.unihub.ro/`
- Deploy standard:
  ```bash
  cd /opt/Mobiup/unihub-retail
  git pull
  npm run build
  sudo systemctl restart unihub-backend
  ```

## Commands

```bash
npm run build                # frontend Vite build
npx tsc --noEmit             # TypeScript typecheck
npm run test                 # vitest
pytest backend/tests/ -v     # backend tests
mypy backend/ --ignore-missing-imports --explicit-package-bases  # Python typecheck
sudo journalctl -u unihub-backend -f   # logs live
```

## Structura

### Frontend `src/`
| Fisier | Rol |
|--------|-----|
| `main.tsx` | AuthProvider + QueryClientProvider + GlitchTip init |
| `App.tsx` | Tab routing + auth guard + localStorage persistence |
| `api/client.ts` | Fetch wrapper (axios-free) cu auto-injectare token OIDC |
| `auth/AuthContext.tsx` | OIDC auth context (oidc-client-ts + authentik) |
| `components/MainLayout.tsx` | Shell principal, navigare, filtre globale |
| `components/Dashboard.tsx` | Tab Hub — Luna curenta + Istoric (2016 linii dupa refactor 2026-05-19) |
| `components/dashboard/DashboardWidgets.tsx` | Componente prezentare extracte din Dashboard (tabele, sortare, pie charts) |
| `components/Campaigns.tsx` | Tab Focus — campanii, incentive, Top |
| `components/Agents.tsx` | Tab Agenti (refactorizat cu useQuery) |
| `components/Management.tsx` + sub-taburi ASM/CRM/Tasks/HR | Management |

### Backend `backend/` — Architecture: router → service → repository (3-tier)

| Router | Service | Repository |
|--------|---------|------------|
| `routers/agents.py` | `services/agents.py` | `repositories/agents.py` |
| `routers/campaigns.py` | `services/campaigns.py` | `repositories/campaigns.py` |
| `routers/crm.py` | `services/crm.py` | `repositories/crm.py` |
| `routers/dashboard.py` | `services/dashboard_service.py` | `repositories/dashboard.py` |
| `routers/filters.py` | `services/filter_options.py` | `repositories/filters.py` |
| `routers/hr.py` | `services/hr.py` | `repositories/hr.py` |
| `routers/imports.py` | `services/imports.py` + `services/importer.py` | `repositories/imports.py` |
| `routers/salarii.py` | `services/salarii.py` | `repositories/salarii.py` |
| `routers/stores.py` | `services/stores.py` | `repositories/stores.py` |
| `routers/tasks.py` | `services/tasks.py` | `repositories/tasks.py` |
| `routers/visits_report.py` | `services/visits_report.py` | `repositories/visits_report.py` |

**Auth:** `backend/auth.py` — JWT RS256 validation via JWKS from authentik. All API routers are protected by `require_auth` dependency in `main.py`. Health and metrics endpoints are public.

**Core services:**
- `services/filters.py` — normalizare + where clauses for SQL filtering; suporta multi-select prin valori comma-separated si exclude locatiile de distributie `TR %`
- `services/forecast.py` — forecast factor calculation (shared by CRM/HR)
- `services/dashboard/` — queries.py, specials_data.py, utils.py; include comparatie perioade, mixuri Hub si builder comun `_build_scoped_params`
- `services/dashboard_specials.py` — hub_specials.json config parsing
- `services/dashboard/specials_data.py` — cardurile speciale Hub (promo + incentive), folosind aceleasi reguli de filtre ca dashboard-ul
- `services/incentive_db.py` — incentive campaigns from DB

## Auth (authentik OIDC)

- Provider: `https://auth.unihub.ro/application/o/unihub-retail/`
- Client ID: `4yiNauwNNzIoIE3Mq9IFnylxtdih9jFSqSKGw93t` (from CREDENTIALS.md)
- Frontend: `oidc-client-ts` with `AuthProvider` + `useAuth()` hook, scope `openid profile email offline_access`, `automaticSilentRenew: true`
- Backend: `auth.py` validates JWTs against JWKS, returns `AuthClaims(sub, email, groups, ...)`
- All API endpoints are protected via `require_auth` FastAPI dependency
- `api/client.ts` auto-injects `Authorization: Bearer <token>` in all requests
- `/auth/proxy/application/o/token/` injects the confidential client secret from local `.env` (`OIDC_CLIENT_SECRET`). Do not hardcode this value in code or docs.
- Provider session policy: Authentik fields must be `hours=8` for access token validity and `days=180` for refresh token validity.

## Shared packages (@unihub/*)

Instalat din Verdaccio: `@unihub/ui-kit`, `@unihub/api-client`, `@unihub/auth-client`, `@unihub/design-tokens`, `@unihub/types`

Registry config in `.npmrc`: `@unihub:registry=http://127.0.0.1:4873/`

## Baza de date

- **Production:** `postgresql://unihub:unihub_dev_password@127.0.0.1:5432/unihub` (container `unihub_postgres`)
- NU confunda cu `mobiup-dwh-postgres` (port 5433) — acela e pentru Distribution/Academy/Faza A4
- Schema: `backend/db/schema_v2.sql` — applied hash-based at boot via `ensure_schema_current()`
- Nu modifica schema direct in DB — editeaza `schema_v2.sql` si reporneste

### Tabele principale
| Tabel | Continut |
|-------|----------|
| `sales_transactions` | Tranzactii detaliate 2023-09 → prezent |
| `historical_annual_sales` | Agregate anuale: 2022 complet, 2023 Ian-Aug |
| `incentive_campaigns` + `incentive_products` | Campanii incentive + produse eligibile |
| `store_targets` | Targete lunare per magazin |
| `stores` | Magazine: site_code, locatie, firma, asm, regional |
| `reporting_agent_month` / `reporting_item_month` | Agregate lunare (sursa dashboard) |
| `reporting_agent_day` / `reporting_item_day` | Agregate zilnice |
| `reporting_agent_lifecycle_month` | Ciclu viata agent per luna |
| `reporting_agent_profile` | Profil agregat per agent |
| `reporting_category_month` | Agregate per categorie produs |
| `reporting_focus_item_month` | Focus products agregate |
| `tasks` | Task-uri per agent/magazin |
| `leave_requests` | Cereri concediu |
| `store_scores` | Scoruri CRM per magazin/luna |
| `store_targets` | Targete lunare magazin |
| `salary_records` | Salarii angajati |
| `agent_targets` | Override optional target real per agent, importat pilot din Grile Salarii |
| `import_snapshots` | Metadata import fisiere Excel |
| `visits_snapshot` | Agregat vizite sync din SQLite la boot |
| `error_logs` | Legacy error table (inactiv — replaced by GlitchTip) |

### Acoperire date
| Perioada | Sursa | Granularitate |
|----------|-------|---------------|
| 2022 | `historical_annual_sales` | anual/magazin |
| 2023 Ian-Aug | `historical_annual_sales` | anual/magazin |
| 2023 Sep → prezent | `sales_transactions` | tranzactie |

## Observability

- **Error tracking:** GlitchTip via `sentry-sdk` (backend) / `@sentry/react` (frontend). DSN in `.env` (`SENTRY_DSN` / `VITE_SENTRY_DSN`). Source maps upload in CI post-build.
- **Metrics:** `/metrics` endpoint with `prometheus_client`. Scraped by Prometheus.
- **Structured logging:** `LOG_FORMAT=json` for JSON lines, `LOG_FORMAT=structlog` for structlog.
- **DB error logging:** `DBErrorHandler` in `logging_config.py` (optional).

## CI/CD

Workflow: `.github/workflows/ci.yml`
- Runner: `unihub-server-runner` (self-hosted)
- Backend: mypy typecheck + pytest
- Frontend: tsc --noEmit + vitest + build
- Source maps: upload to GlitchTip post-build (optional, needs VITE_GLITCHTIP_DSN secret)

**Runner startup:**
```bash
cd /opt/Mobiup/ops/runners/retail
./run.sh
```

**Background worker (arq + Valkey):**
- Valkey ruleaza in Docker (`unihub-valkey`, port 6379) — NU e systemd service
- Worker: `unihub-worker.service` (systemd, enabled, runs `backend/worker.py`)
- Import async: `POST /api/import/sales?background=true` → arq job → `GET /api/import/jobs/{job_id}`

## Conventions

- Nu citi din `sales_transactions` pentru raportare — foloseste agregatele `reporting_*`
- Exceptie controlata: cardurile care afiseaza explicit `Cartele` citesc cantitatea din `sales_transactions` cu `is_cartela=true`, dar KPI-urile de vanzari/cantitate/bonuri raman excluse de cartela.
- Reporting-ul operational exclude categoria `Cartele` din agregatele `reporting_*`; nu reintroduce `is_cartela` in totaluri, medii sau procente.
- Locatiile de distributie cu `stores.locatie ILIKE 'TR %'` sunt excluse din calculele Retail si din optiunile de filtre; regula este centralizata in `services/filters.py` si trebuie pastrata si in rebuild-ul reporting.
- Filtrele Hub/Focus accepta multi-select pentru magazine si agenti; frontend-ul trimite valori comma-separated, iar SQL foloseste `= ANY(string_to_array($n::TEXT, ','))`.
- Filtrele persistate in browser folosesc localStorage keys: `unihub_hub_filters`, `unihub_focus_filters`, `unihub_agents_filters`. Daca utilizatorul raporteaza filtre "blocate" dupa refresh, verifica aceste chei inainte de a schimba logica API.
- Cand `site_code` este prezent, el domina scope-ul: backend-ul ignora `firma`, `regional` si `asm` pentru dashboard/history/comparatii/special_cards, ca istoricul unui magazin sa ramana vizibil chiar daca magazinul si-a schimbat RM/firma in timp.
- ASM a fost scos din filtrele si cardurile Hub; Hub ramane pe layer RM + magazine + agenti. Nu reintroduce cardul ASM pana cand structura DB nu este actualizata.
- Comparatia perioade din Hub foloseste aceeasi fereastra de zile: luna curenta pana la ultima zi importata daca luna e partiala, aceeasi perioada din luna trecuta si aceeasi perioada din anul trecut.
- Cardul `Comparatie perioade` afiseaza delte pentru vanzari, bonuri si cantitate, fiecare cu valoare absoluta si procent.
- Tabelele curente Hub `RM` si `Magazine` expun `forecast_target_pct` dupa `proc_realizare_target`; formula proiecteaza vanzarile la luna intreaga cand `import_snapshots.is_month_final=false`.
- Toate modelele Pydantic din `backend/models.py` cu `ConfigDict(from_attributes=True)` trebuie sa declare explicit campurile returnate
- Salarii LEFT JOIN stores conditionat (doar cand regional/asm sunt prezente)
- Salarii company_name case-insensitive la JOIN (`LOWER()` pe ambele parti)
- Targetele din tabelul Hub pe agent folosesc `agent_targets` daca exista override pentru `(import_month, site_code, agent)`; altfel raman pe fallback-ul vechi `store_targets / agenti activi`.
- Importul pilot din Grile Salarii se ruleaza cu `python backend/scripts/import_grile_agent_targets.py --month YYYY-MM [--apply]` si este limitat implicit la managerul `Andrei Stancu`.
- Filtre: `MainLayout.hubFilters` shared Hub+Focus; `Agents` uses `agentsFilters` independent

## Vizite

- SQLite DB: `data/visits/visits.db` + `data/visits/images/`
- `visits_report.py` reads via `run_in_executor` (async wrapper)
- Photos served via `/api/visits-report/photo/{visit_id}/{filename}`
- `visits_snapshot` table in PG synced at boot for HR/CRM use

## Gotchas

- **2023-2024 `agent = '-'`:** lipsa coloana Agent in fisierele sursa — nu e bug
- **Promo_qty calculat dar neafisat:** SQL returneaza promo_qty si pentru Istoric, componenta filtreaza la render pe RM/Agenti
- **Magazin selectat + RM curent:** daca API primeste `firma=MobiCell&regional=Elena...&site_code=CRELECTROP`, istoricul trebuie calculat dupa `site_code`, nu dupa RM-ul curent. Altfel lunile istorice pot iesi 0 daca magazinul era la alt RM.
- **Parametri SQL fara clauze:** cand `site_code` domina scope-ul, nu pastra `firma/regional/asm` in lista de parametri. Asyncpg poate arunca `IndeterminateDatatypeError: could not determine data type of parameter $n`.
- **OIDC session policy:** pastreaza `offline_access`, `automaticSilentRenew: true` si provider validity `hours=8` / `days=180`. Nu salva in Authentik valori Python de tip `8:00:00`; authorize crapa la parsarea duratei.
- **Recharts ResponsiveContainer:** graficele au `minWidth={1}` / `minHeight={1}` ca sa evite warning-ul width/height `-1` in containere ascunse sau tranzitionate.
- **Auth routes public:** `/health`, `/metrics`, `/auth/callback` (frontend), SPA static files — nu necesita authentik
- **Import Excel:** maintain `import_sales_file()` in `services/importer.py`; nu introduce axios back
- **Doua baze de date PG separate:** `unihub_postgres` (port 5432, DB `unihub`) = retail production cu 33 luni date; `mobiup-dwh-postgres` (port 5433) = DWH + Academy + Faza A4 DB-uri. NU confunda — `.env` DATABASE_URL TREBUIE sa pointeze la 5432/unihub
- **`get_dashboard_all` trebuie sa includa `special_cards`:** fara ele, Hub tab arata "Incentive neconfigurat". Apelul la `_get_special_cards_data()` e in `asyncio.gather` alaturi de celelalte query-uri
- **Campaigns tab `promoMonth` state:** permite selectia lunii pentru promo/incentive, independent de `currentMonth`. `loadCurrentFocus` foloseste `promoMonth`, nu `currentMonth`
- **`get_promotions_incentives` response:** TREBUIE sa returneze `top_agents`, `incentive_categories`, `incentive_product_count`, `promo_category_qty` — frontend-ul le acceseaza direct (ex: `promoData.top_agents.length`)

## Ce sa nu faci

- Nu crea fisiere temporare in radacina (`fix.py`, `patch.txt`)
- Nu modifica schema direct in DB — editeaza `schema_v2.sql`
- Nu readauga axios — foloseste fetch wrapper-ul din `api/client.ts`
- Nu reintroduce auth local — doar OIDC via authentik
- Nu scoate stratul de service/repository din routere
- Nu schimba DATABASE_URL la alt port/DB — retail e pe 5432/unihub, NU pe 5433/unihub_retail
- Nu returna raspunsuri partiale din `get_promotions_incentives` — frontend-ul crashuieste pe `undefined.length`
