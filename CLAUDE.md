# CLAUDE.md — UniHub Retail

**Phase: C3 Complete (11/11) — 2026-05-06 | Pending: E2E tests, source maps, coverage**

## Overview

Sursa de adevar pentru vanzari + vizite in ecosistemul MobiUp. Module: Hub, Focus, Agenti (+Salarii), Vizite, Management (Echipa/Magazine/Tasks/HR), Setari.

## Stack

- Frontend: React 19 + Vite + TypeScript + TanStack Query + Tailwind 4
- Backend: FastAPI + asyncpg + PostgreSQL (mobiup-dwh-postgres:5433/unihub_retail)
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
| `components/Dashboard.tsx` | Tab Hub — Luna curenta + Istoric |
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
- `services/filters.py` — normalizare + where clauses for SQL filtering
- `services/forecast.py` — forecast factor calculation (shared by CRM/HR)
- `services/dashboard/` — queries.py, specials_data.py, utils.py
- `services/dashboard_specials.py` — hub_specials.json config parsing
- `services/incentive_db.py` — incentive campaigns from DB

## Auth (authentik OIDC)

- Provider: `https://auth.unihub.ro/application/o/unihub-retail/`
- Client ID: `4yiNauwNNzIoIE3Mq9IFnylxtdih9jFSqSKGw93t` (from CREDENTIALS.md)
- Frontend: `oidc-client-ts` with `AuthProvider` + `useAuth()` hook
- Backend: `auth.py` validates JWTs against JWKS, returns `AuthClaims(sub, email, groups, ...)`
- All API endpoints are protected via `require_auth` FastAPI dependency
- `api/client.ts` auto-injects `Authorization: Bearer <token>` in all requests

## Shared packages (@unihub/*)

Instalat din Verdaccio: `@unihub/ui-kit`, `@unihub/api-client`, `@unihub/auth-client`, `@unihub/design-tokens`, `@unihub/types`

Registry config in `.npmrc`: `@unihub:registry=http://127.0.0.1:4873/`

## Baza de date

- **Production:** `postgresql://unihub_retail_app@127.0.0.1:5433/unihub_retail` (mobiup-dwh-postgres)
- **Local dev:** `postgresql://unihub@localhost:5432/unihub`
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
- Backend: mypy typecheck + pytest + coverage
- Frontend: tsc --noEmit + vitest + build
- E2E: playwright tests (chromium)
- Source maps: upload to GlitchTip post-build

**Runner startup:**
```bash
cd /opt/Mobiup/gh-runner
./run.sh
```

**Background worker (arq + Valkey):**
```bash
sudo systemctl enable --now valkey
sudo cp /opt/Mobiup/unihub-retail/unihub-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now unihub-worker
```

## Conventions

- Nu citi din `sales_transactions` pentru raportare — foloseste agregatele `reporting_*`
- Toate modelele Pydantic din `backend/models.py` cu `ConfigDict(from_attributes=True)` trebuie sa declare explicit campurile returnate
- Salarii LEFT JOIN stores conditionat (doar cand regional/asm sunt prezente)
- Salarii company_name case-insensitive la JOIN (`LOWER()` pe ambele parti)
- Filtre: `MainLayout.hubFilters` shared Hub+Focus; `Agents` uses `agentsFilters` independent

## Vizite

- SQLite DB: `data/visits/visits.db` + `data/visits/images/`
- `visits_report.py` reads via `run_in_executor` (async wrapper)
- Photos served via `/api/visits-report/photo/{visit_id}/{filename}`
- `visits_snapshot` table in PG synced at boot for HR/CRM use

## Gotchas

- **2023-2024 `agent = '-'`:** lipsa coloana Agent in fisierele sursa — nu e bug
- **Promo_qty calculat dar neafisat:** SQL returneaza promo_qty si pentru Istoric, componenta filtreaza la render pe RM/ASM/Agenti
- **Auth routes public:** `/health`, `/metrics`, `/auth/callback` (frontend), SPA static files — nu necesita authentik
- **Import Excel:** maintain `import_sales_file()` in `services/importer.py`; nu introduce axios back
- **O singura baza de date PG:** `mobiup-dwh-postgres` (port 5433, DB `unihub_retail`) = retail production (C3.7 migrated). NU mai exista DB-ul vechi pe 5432.
- **`get_dashboard_all` trebuie sa includa `special_cards`:** fara ele, Hub tab arata "Incentive neconfigurat". Apelul la `_get_special_cards_data()` e in `asyncio.gather` alaturi de celelalte query-uri
- **Campaigns tab `promoMonth` state:** permite selectia lunii pentru promo/incentive, independent de `currentMonth`. `loadCurrentFocus` foloseste `promoMonth`, nu `currentMonth`
- **`get_promotions_incentives` response:** TREBUIE sa returneze `top_agents`, `incentive_categories`, `incentive_product_count`, `promo_category_qty` — frontend-ul le acceseaza direct (ex: `promoData.top_agents.length`)

## Ce sa nu faci

- Nu crea fisiere temporare in radacina (`fix.py`, `patch.txt`)
- Nu modifica schema direct in DB — editeaza `schema_v2.sql`
- Nu readauga axios — foloseste fetch wrapper-ul din `api/client.ts`
- Nu reintroduce auth local — doar OIDC via authentik
- Nu scoate stratul de service/repository din routere
- Nu schimba DATABASE_URL la alt port/DB — retail e pe 5433/unihub_retail (mobiup-dwh-postgres)
- Nu returna raspunsuri partiale din `get_promotions_incentives` — frontend-ul crashuieste pe `undefined.length`
