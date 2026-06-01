# CLAUDE.md — UniHub Retail

**Phase: C3 COMPLETED + Hub filter/reporting fixes — 2026-05-07 | Server audit + optimization — 2026-05-19 | Calculator Target — 2026-05-27 | Campanii Iunie 2026 (promo co-purchase + excludere incentive + Concurs config-driven) — 2026-05-30**

## Overview

Sursa de adevar pentru vanzari + vizite in ecosistemul MobiUp. Module: Hub, Focus, Agenti (+Salarii), Vizite, Management (Echipa/Magazine/Tasks/HR/Calculator Target/Grile), Setari.

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
| `components/Campaigns.tsx` | Tab Focus — 4 sub-sectiuni: **Incentive · Promo · Concurs · Focus** (split din vechiul "Campanii"). Concurs = leaderboard agenti (`ContestView`) |
| `api/contests.ts` | Fetch `/api/contests/active?month=` (leaderboard concurs, scoped server-side) |
| `components/Agents.tsx` | Tab Agenti (refactorizat cu useQuery) |
| `components/Management.tsx` + sub-taburi ASM/CRM/Tasks/HR/TargetCalculator/**Grile** | Management |
| `components/GrileSubtab.tsx` + `api/grile.ts` | Subtab Grile — verificare K5/L5 vs target+vanzari DB; layout responsive (card pe mobil, grid pe desktop); captions integrate in barele ASM+TL (pliabile); TL fara nume nu afiseaza rand. Vezi `docs/grile-integration-plan.md` |
| `components/GrileMonthlyPanel.tsx` | Card "Inchidere luna" (proxy catre grile-salarii): Finalizeaza / Exporta arhiva / Reset simulare / Reset LIVE + download final/arhiva. Vizibil doar admin (`/api/grile/monthly/permissions`); poll job arq |

### Backend `backend/` — Architecture: router → service → repository (3-tier)

| Router | Service | Repository |
|--------|---------|------------|
| `routers/agents.py` | `services/agents.py` | `repositories/agents.py` |
| `routers/campaigns.py` | `services/campaigns.py` | `repositories/campaigns.py` |
| `routers/contests.py` | `services/contests.py` (+ `services/contests_config.py`) | `repositories/contests.py` |
| `routers/crm.py` | `services/crm.py` | `repositories/crm.py` |
| `routers/dashboard.py` | `services/dashboard_service.py` | `repositories/dashboard.py` |
| `routers/filters.py` | `services/filter_options.py` | `repositories/filters.py` |
| `routers/hr.py` | `services/hr.py` | `repositories/hr.py` |
| `routers/imports.py` | `services/imports.py` + `services/importer.py` | `repositories/imports.py` |
| `routers/salarii.py` | `services/salarii.py` | `repositories/salarii.py` |
| `routers/stores.py` | `services/stores.py` | `repositories/stores.py` |
| `routers/tasks.py` | `services/tasks.py` | `repositories/tasks.py` |
| `routers/target_calculator.py` | `services/target_calculator.py` | `repositories/target_calculator.py` |
| `routers/visits_report.py` | `services/visits_report.py` | `repositories/visits_report.py` |
| `routers/grile.py` | `services/grile.py` (+ `services/grile_sheets.py` client Google read-only) | `repositories/grile.py` |

**Auth:** `backend/auth.py` — JWT RS256 validation via JWKS from authentik. All API routers are protected by `require_auth` dependency in `main.py`. Health and metrics endpoints are public.

**Core services:**
- `services/filters.py` — normalizare + where clauses for SQL filtering; suporta multi-select prin valori comma-separated si exclude locatiile de distributie `TR %`
- `services/forecast.py` — forecast factor calculation (shared by CRM/HR/Calculator Target)
- `services/dashboard/` — queries.py, specials_data.py, utils.py; include comparatie perioade, mixuri Hub si builder comun `_build_scoped_params`
- `services/dashboard_specials.py` — hub_specials.json config parsing
- `services/dashboard/specials_data.py` — cardurile speciale Hub (promo + incentive), folosind aceleasi reguli de filtre ca dashboard-ul
- `services/incentive_db.py` — incentive campaigns from DB
- `services/promo_copurchase.py` — **regula co-purchase** (campania -20%): bon calificat + unitate redusa per bon, scoped. Helper partajat de cardul Hub, tab Focus si Concurs
- `services/contests_config.py` — loader + parser `data/contests.json` (concursuri config-driven: scope, reguli, premii)

## Auth (authentik OIDC)

- Provider: `https://auth.unihub.ro/application/o/unihub-retail/`
- Client ID: `4yiNauwNNzIoIE3Mq9IFnylxtdih9jFSqSKGw93t` (from CREDENTIALS.md)
- Frontend: `oidc-client-ts` with `AuthProvider` + `useAuth()` hook, scope `openid profile email offline_access`, `automaticSilentRenew: true`
- Backend: `auth.py` validates JWTs against JWKS, returns `AuthClaims(sub, email, groups, ...)`
- All API endpoints are protected via `require_auth` FastAPI dependency
- Current deploy has authentication-only access control for most modules: `groups` are extracted but not used as RBAC. Grant Authentik access only to trusted internal users until per-role/per-manager scope is implemented.
- Salary endpoints expose CNP and salary data to authenticated users. Treat the Salarii tab as HR/internal-only at the Authentik app assignment level.
- Target Calculator is the only module with a narrower server-side owner gate today: calculate/recalculate/finalize are limited by `TARGET_CALCULATOR_FINALIZER_EMAILS`; saving `Final manager` rows remains intentionally collaborative for authenticated managers.
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
| `focus_products` | Lista produse focus (item_code) — sursa pentru focus_quantity + punctaj Concurs |
| `tasks` | Task-uri per agent/magazin |
| `leave_requests` | Cereri concediu |
| `store_scores` | Scoruri CRM per magazin/luna |
| `target_scenarios` / `target_scenario_rows` | Documentul lunar Calculator Target si randurile editabile inainte de publicare |
| `salary_records` | Salarii angajati |
| `agent_targets` | Override optional target real per agent, importat pilot din Grile Salarii |
| `import_snapshots` | Metadata import fisiere Excel |
| `visits_snapshot` | Agregat vizite sync din SQLite la boot |
| `error_logs` | Backend ERROR+ logs scrise de `DBErrorHandler`; GlitchTip ramane error tracking principal |
| `grile_sheets` | Maparea read-only `site_code` → `sheet_id` Google (copie din grile-salarii registry; seed cu `backend/scripts/seed_grile_sheets.py`) |
| `grile_runs` | Istoric rulari verificare grile (status, progres, ok/problem/error, source manual/auto, `source_snapshot_id`) |
| `grile_store_status` | Rezultat per magazin per run: K5/L5 grila vs target+vanzari MTD DB, completare %, fill/target/sales status |

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
- **DB error logging:** `DBErrorHandler` in `logging_config.py` scrie ERROR+ in `error_logs` dupa atasarea pool-ului la startup; GlitchTip ramane error tracking principal.

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
- **Grile check async:** `grile_check_background(month, source, snapshot_id, email)` — verifica K5/L5 toate grilele vs DB. Declansat manual (`POST /api/grile/run`) sau **automat dupa fiecare import de vanzari reusit** (best-effort, `trigger_grile_check_after_import` in `services/imports.py` + `worker.py`; NU poate strica importul). La modificarea jobului, restart `unihub-worker`.
- **Secret Google:** `backend/config/google/service-account.json` (chmod 600, gitignored). Scope-uri READ-ONLY (`spreadsheets.readonly` + `drive.metadata.readonly`).
- **Inchidere luna async (PROXY, nu port):** `grile_monthly_background(op, month, only, dry_run, email)` deleaga `finalize`/`archive`/`reset` la **grile-salarii** pe localhost (`services/grile_monthly.py` → `http://127.0.0.1:47000/api/{op}`, header `X-Grile-Internal`). Ruleaza in worker fiindca dureaza minute (peste timeout-ul edge Cloudflare). UI: `GrileMonthlyPanel.tsx`, vizibil doar pentru admin. Endpoints: `POST /api/grile/monthly/run` (gate `require_grile_admin`), `GET /api/grile/monthly/job/{id}` (poll arq), `GET /api/grile/monthly/permissions`, `GET /api/grile/monthly/download/{final|archive}/{YYYY-MM}`. Retail **NU** capata write-capability pe Google — doar deleaga; scripturile + SA Editor raman in grile-salarii.
- **Env proxy Grile** (in `.env` din root — incarcat si de backend prin `EnvironmentFile`+`load_dotenv`, si de worker prin `load_dotenv(find_dotenv())`): `GRILE_BASE_URL` (default `http://127.0.0.1:47000`), `GRILE_INTERNAL_SECRET` (acelasi ca drop-in systemd `unihub-grile`), `GRILE_FINALIZER_EMAILS` (default `aner.valens@gmail.com`). Fara secret, proxy-ul e dezactivat (fail-closed). Luna `YYYY-MM` → label RO (`Mai 2026`) in `services/grile_monthly.py`.
- **Limita Grile in Retail:** verificarea K5/L5 ramane read-only (scope Google read-only). Operatiile WRITE se fac DOAR prin proxy-ul de mai sus catre grile-salarii — nu reimplementa `reset_month.py`/`finalize_month.py`/`archive_month.py` in retail. Pe 2026-06-01, closeout Mai 2026 + reset spre Iunie 2026 a fost finalizat in `grile-salarii` fara schimbare de linkuri.

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
- Comparatia perioade din Hub este like-for-like: cohorta este lista magazinelor cu vanzari Retail in luna analizata. Pentru luna trecuta/anul trecut se filtreaza dupa aceleasi `site_code`, fara reaplicarea RM/firma/ASM istorice, deoarece magazinele pot fi mutate.
- Cardul `Comparatie perioade` afiseaza delte pentru vanzari, bonuri si cantitate, fiecare cu valoare absoluta si procent.
- Calculator Target foloseste un singur draft per luna tinta; recalcularea actualizeaza documentul existent si reseteaza valorile finale/observatiile numai dupa confirmare. Nu adauga selector de scenarii sau versiuni paralele.
- Calculator Target stabileste cohorta din magazinele cu vanzari in ultima luna disponibila anterioara lunii tinta; la finalizare, `store_targets` pentru luna tinta este inlocuit strict cu cohorta aprobata.
- Formula curenta Calculator Target este `weighted_floor_forecast_v2`: surse `M-13`, `M-12`, `M-1`, cu forecast pentru referintele partiale prin `services/forecast.py`. Excel-ul initial este numai referinta de business, nu sursa runtime.
- Procedura lunara: spre finalul lunii se alege luna tinta urmatoare, se introduce targetul total, se calculeaza propunerea, managerii completeaza `Final manager`, iar finalizatorul publica doar cand toate randurile sunt completate si `Ramas de distribuit` este 0. Exemplu: target `2026-07` foloseste `2025-06`, `2025-07`, `2026-06`; daca `2026-06` este partiala, intra forecastul.
- Interfata Calculator Target afiseaza coloana `Calculat`; floor-ul ramane in algoritm si export, dar nu este expus ca un card sau o coloana operationala.
- Coloana `Final manager` este campul evidentiat/editabil pentru manageri si porneste goala in drafturile noi; finalizarea trebuie blocata cat timp exista randuri necompletate. Salvarea ramane colaborativa, dar calculul/recalcularea si `Finalizeaza` trebuie protejate server-side prin `TARGET_CALCULATOR_FINALIZER_EMAILS` (implicit `aner.valens@gmail.com`).
- Cardul cu parametrii `Calculator Target` nu se afiseaza utilizatorilor fara aceasta permisiune; ei lucreaza numai in documentul pregatit si au ca actiune manuala vizibila `Salveaza acum` pentru `Final manager`.
- Tabelul Calculator Target are filtru multi-select pe locatie, fara cautare manuala separata. Click pe numele locatiei deschide drawer-ul de detaliu cu 16 luni, toggle grafic `Vanzari` / `Bon2Acc` / `Focus/Acc`, KPI-uri Retail si ponderea agentilor; endpointul este `/api/target-calculator/scenarios/{id}/stores/{site_code}`.
- In drawer-ul Calculator Target, `Zile cu vanzari` se calculeaza din `COUNT(DISTINCT reporting_agent_day.sale_date)` pe magazin/luna. Nu folosi `MAX(reporting_agent_month.working_days)` decat fallback, deoarece valoarea pe agent poate afisa 14 zile pentru un magazin care are 26+ zile cu vanzari.
- CSP-ul production permite CSS local, nu Google Fonts sau `<style>` injectat din componente. Pastreaza fontul sistemic din `src/index.css`; pentru animatii foloseste clase CSS globale, iar pentru grafice ascunse pe mobil monteaza conditionat componenta in loc sa o ascunzi cu CSS.
- Tabelele curente Hub `RM` si `Magazine` expun `forecast_target_pct` dupa `proc_realizare_target`; formula proiecteaza vanzarile la luna intreaga cand `import_snapshots.is_month_final=false`.
- Toate modelele Pydantic din `backend/models.py` cu `ConfigDict(from_attributes=True)` trebuie sa declare explicit campurile returnate
- Salarii LEFT JOIN stores conditionat (doar cand regional/asm sunt prezente)
- Salarii company_name case-insensitive la JOIN (`LOWER()` pe ambele parti)
- Targetele din tabelul Hub pe agent folosesc `agent_targets` daca exista override pentru `(import_month, site_code, agent)`; altfel raman pe fallback-ul vechi `store_targets / agenti activi`.
- Importul pilot din Grile Salarii se ruleaza cu `python backend/scripts/import_grile_agent_targets.py --month YYYY-MM [--apply]` si este limitat implicit la managerul `Andrei Stancu`.
- Filtre: `MainLayout.hubFilters` shared Hub+Focus; `Agents` uses `agentsFilters` independent

### Campania Iunie 2026 — promo co-purchase, excludere incentive, Concurs (2026-05-30)
- **Promotia** (`data/hub_specials.json`, gitignored) = campania "-20% la produsele selectate" (47 coduri, 01–30 iunie). Cardul Hub si tab Focus folosesc **regula co-purchase** din `services/promo_copurchase.py`.
- **Bon calificat** = cheie `(sale_date, site_code, agent, bon_nr)` cu ≥1 produs din lista promo SI ≥2 unitati pozitive totale; se exclud cartele + locatii `TR %` (identic cu `reporting_refresh.py`). Unitatea redusa = produsul din lista cu cel mai mic `unit_price` pe bon (tie-break determinist `unit_price, item_code, id`), 1 per bon.
- **Cardul promo Hub**: highlight = Bonuri calificate; metrici = Produse reduse / Magazine / Agenti (NU mai e currency). Vezi `build_promotion_card` in `dashboard_specials.py`.
- **Tab Focus → sub-sectiunea Promo** afiseaza ACELEASI metrici co-purchase (`campaigns.py` populeaza `promo_qualifying_bons/discounted_units/active_stores/active_agents` din `promo_cp`; Top Magazine arata bonuri calificate per magazin, nu cantitate simpla). NU folosi `promo_qty` simplu (din `_fetch_promo_incentive_summary`, ramas pentru KPI Hub-summary + coloane Hub) ca headline promo — supraestimeaza fata de regula co-purchase.
- **Excludere incentive**: unitatea redusa (vanduta in promo) NU se incentiveaza. `specials_data.py` (card Hub) + `campaigns.py` (top_agents/top_stores/incentive_categories + headline `incentive_value`/`incentive_qty`) scad `excluded_units` din `net_quantity`. Se aplica DOAR cand exista promo activ pe luna; lunile fara promo raman neschimbate. Coloanele Hub `promo_qty`/`incentive_qty` din tabele raman pe agregatul simplu (neajustate, intentionat).
- **Incentive iunie = clona EXACTA a lunii mai** (967 produse, tiere 5/10/25 RON, total 5945 RON). Clonata in DB (`incentive_campaigns`/`incentive_products`, month `2026-06`). Lista/valorile NU se schimba — singura "modificare" e regula de excludere de mai sus.
- **Concursul** (`data/contests.json`, gitignored, config-driven) = leaderboard agenti, scope `asm='Andrei Stancu'` (23 magazine non-TR), iunie. Punctaj **per agent**, fara gate de target: +1/unitate produs focus, +1/bon promo calificat, +1/unitate cu `unit_price > 150`. Premii top 6 (M7 Plus / BoomX / Macaron). Endpoint `/api/contests/active?month=` ignora filtrul global (scoped server-side din config). Reguli/scope/premii parametrizabile in JSON.
- **Invariant luni UI:** `/api/filters/months` listeaza doar importuri `completed`. Nu forta `2026-06` in selector cat timp nu exista import de vanzari iunie; acesta a fost finding Codex #1 si este by-design.
- **Audit Codex final:** cu config temporar pe mai, calea completa Focus intoarce `promo_qty=710` simplu, dar `promo_qualifying_bons=314` co-purchase si top magazin 17 bonuri. Fixul corect este sa folosesti campurile co-purchase dedicate in UI, nu sa modifici `_fetch_promo_incentive_summary`.

## Vizite

- SQLite DB: `data/visits/visits.db` + `data/visits/images/`
- `visits_report.py` reads via `run_in_executor` (async wrapper)
- Meniul Retail `Vizite` citeste randurile din SQLite, dar filtrele firma/RM/ASM/magazin si afisarea ierarhiei se rezolva prin tabela curenta `stores` dupa `visits.magazin = stores.site_code`. Nu filtra direct pe `visits.regional`/`visits.asm`: FieldOps poate avea valori istorice sau goale in randurile vechi.
- Tree-ul (`/api/visits-report/tree`) e grupat pe **team leader** (cine a facut vizita = snapshot `visits.team_leader_name`, NU ASM-ul magazinului). Response: `team_leaders: [TeamLeaderGroup{team_leader, nr_vizite, months}]` (nu `asms`). `team_leader_name` e populat de FieldOps la creare; randurile pre-2026-05-29 au fost backfilled. Drawer-ul afiseaza Team Leader + ASM.
- In rndul vizitei + header drawer: logo firma `<FirmaBadge>` (M rosu Mobiup / M albastru MobiCell, component partajat `components/FirmaBadge.tsx`, acelasi din Focus/top magazine). Vizitele dintr-o zi sunt sortate pe firma apoi magazin.
- **Vizite ignora filtrul global** (firma/RM/ASM/magazin): `VisiteSubtab` cere mereu setul complet (`ALL_FILTERS`), nu primeste prop `filters`. Butonul de filtru e ascuns deja in sectiunea visits (`App.tsx`: `showFilterButton={!(activeTab==='hub' && hubSection==='visits')}`). Gruparea fiind pe team leader, filtrele celorlalte taburi nu se aplica. Singurul filtru local ramas: `MonthPicker` (luna).
- UI tree (ca FieldOps): `TeamLeaderRow` → la expand arata **magazinele unice** ale lunii selectate (`storesOfGroup` grupeaza pe `magazin`), fiecare `StoreRow` = logo firma + nume magazin (`locatie`) + nr vizite; click pe magazin expandeaza **vizitele** lui (`VisitLeaf`: data + ora + completare). Fara sub-niveluri luna/zi (luna din `MonthPicker`). Sortare: firma apoi nume magazin; vizitele in magazin pe data desc. `VisitSummaryItem` are `locatie` (din `_enrich_visit_row`, store metadata). `VisitDayGroup`/`VisitMonthGroup` raman pe contractul API backend.
- Photos served via `/api/visits-report/photo/{visit_id}/{filename}`
- `visits_snapshot` table in PG synced at boot for HR/CRM use

## Gotchas

- **2023-2024 `agent = '-'`:** lipsa coloana Agent in fisierele sursa — nu e bug
- **Promo_qty calculat dar neafisat:** SQL returneaza promo_qty si pentru Istoric, componenta filtreaza la render pe RM/Agenti
- **Magazin selectat + RM curent:** daca API primeste `firma=MobiCell&regional=Elena...&site_code=CRELECTROP`, istoricul trebuie calculat dupa `site_code`, nu dupa RM-ul curent. Altfel lunile istorice pot iesi 0 daca magazinul era la alt RM.
- **Parametri SQL fara clauze:** cand `site_code` domina scope-ul, nu pastra `firma/regional/asm` in lista de parametri. Asyncpg poate arunca `IndeterminateDatatypeError: could not determine data type of parameter $n`.
- **OIDC session policy:** pastreaza `offline_access`, `automaticSilentRenew: true` si provider validity `hours=8` / `days=180`. Nu salva in Authentik valori Python de tip `8:00:00`; authorize crapa la parsarea duratei.
- **Recharts ResponsiveContainer:** graficele au `minWidth={1}` / `minHeight={1}` si, cand sunt in layout-uri ascunse pe mobil/desktop, trebuie montate conditionat. Un `ResponsiveContainer` intr-un container `hidden` poate produce warning-uri width/height `0` sau `-1`.
- **Auth routes public:** `/health`, `/metrics`, `/auth/callback` (frontend), SPA static files — nu necesita authentik
- **Import Excel:** maintain `import_sales_file()` in `services/importer.py`; nu introduce axios back
- **Doua baze de date PG separate:** `unihub_postgres` (port 5432, DB `unihub`) = retail production cu 33 luni date; `mobiup-dwh-postgres` (port 5433) = DWH + Academy + Faza A4 DB-uri. NU confunda — `.env` DATABASE_URL TREBUIE sa pointeze la 5432/unihub
- **`get_dashboard_all` trebuie sa includa `special_cards`:** fara ele, Hub tab arata "Incentive neconfigurat". Apelul la `_get_special_cards_data()` e in `asyncio.gather` alaturi de celelalte query-uri
- **Campaigns tab `promoMonth` state:** permite selectia lunii pentru promo/incentive, independent de `currentMonth`. `loadCurrentFocus` foloseste `promoMonth`, nu `currentMonth`
- **`get_promotions_incentives` response:** TREBUIE sa returneze `top_agents`, `incentive_categories`, `incentive_product_count`, `promo_category_qty` — frontend-ul le acceseaza direct (ex: `promoData.top_agents.length`)
- **Grile — Google client NU e thread-safe:** `googleapiclient`/`httplib2` da `free(): invalid next size` (corupere memorie) daca un `build()` service e folosit din mai multe thread-uri. In `services/grile.py` fiecare thread isi construieste propriile servicii (thread-local) pe un `ThreadPoolExecutor` dedicat dimensionat la `concurrency` (default 3). NU partaja un service intre thread-uri.
- **Grile — quota Google read:** ~60 req/min/user. La `concurrency=3` + retry backoff, 75 magazine ruleaza ~2 min fara 429. Crescand concurrency apar 429 (apar ca `error_code=GOOGLE_ERROR` per magazin, se rezolva la urmatoarea rulare — nu silent failure).
- **Grile — luna interna `YYYY-MM`** (nu "Mai 2026"). Expected = `store_targets` + `SUM(reporting_item_month.total_sales)` pe `site_code`; comparat cu K5(target)/L5(realizat) din grila. Diferentele de vanzari sunt asteptate cand grila e completata inainte de ultimul import (status `IN_URMA`).
- **Grile — nu reimplementa operatiile write in Retail:** `reset_month.py`, `archive_month.py`, `finalize_month.py`, `add_store.py`, `generate_missing_grile.py`, `unlock_agent_name_cells.py`, `repair_agent1_extra_section.py` raman in grile-salarii. Retail le declanseaza DOAR prin proxy (`services/grile_monthly.py` → `unihub-grile` localhost cu `X-Grile-Internal`); pastreaza scope-uri Google read-only. `Reset LIVE` e ireversibil — UI cere confirmare; nu adauga cai care sar peste ea.

## Ce sa nu faci

- Nu crea fisiere temporare in radacina (`fix.py`, `patch.txt`)
- Nu modifica schema direct in DB — editeaza `schema_v2.sql`
- Nu readauga axios — foloseste fetch wrapper-ul din `api/client.ts`
- Nu reintroduce auth local — doar OIDC via authentik
- Nu scoate stratul de service/repository din routere
- Nu schimba DATABASE_URL la alt port/DB — retail e pe 5432/unihub, NU pe 5433/unihub_retail
- Nu returna raspunsuri partiale din `get_promotions_incentives` — frontend-ul crashuieste pe `undefined.length`
