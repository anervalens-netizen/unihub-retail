# Retail refactoring roadmap - 2026-06-26

## Scop

Acest plan transforma analiza din `CODE_REVIEW.md` intr-un roadmap executabil.
Obiectivul este reducerea riscului operational si a costului de mentenanta fara
sa schimbam contractele business existente: raportarea Retail exclude Cartele si
locatiile `TR %`, `site_code` domina scope-ul istoric, Salarii ramane
backend-gated, iar Grile si importurile grele raman pe worker.

Planul este incremental. Fiecare etapa trebuie sa lase aplicatia intr-o stare
verificabila prin teste si typecheck, iar refactorizarile mari se fac doar dupa
ce exista helper-e comune si teste de contract.

## Principii de executie

- Nu se combina refactorizari structurale cu schimbari business.
- Se pastreaza contractele API si payload-urile frontend pana cand exista un
  motiv explicit de schimbare.
- Se prefera helper-e publice si testate in locul importurilor din simboluri
  private `_...`.
- SQL-ul se muta din services in repositories pe domenii mici, nu printr-o
  mutare masiva de fisiere.
- Fiecare pas are validare proportionata; validarea completa ramane secventiala:
  `npm run typecheck`, `npm run typecheck:strict`, `npm run lint`,
  `npm run test`, `pytest backend/tests/ -q`,
  `mypy backend/ --ignore-missing-imports --explicit-package-bases`,
  `npm run build`.

## Etapa 0 - Baseline si guardrails

Livrabile:

- inventar explicit al ariilor refactorizate in acest roadmap;
- teste pentru helper-ele de scope/filter si maparea componentelor din
  `/api/dashboard/all`;
- teste sau asertii pentru contractele care nu trebuie schimbate:
  `TR %`, `NOT is_cartela` in KPI Retail, `site_code` peste firma/RM/ASM,
  Salarii 403 pentru roluri nepermise;
- status local curat inainte de fiecare transe majora.

Criteriu de iesire:

- testele existente pentru filtre, dashboard, campaigns, salarii si grile trec;
- orice schimbare viitoare are un test de contract inainte sau in acelasi patch.

## Etapa 1 - Quick wins cu risc mic

Livrabile frontend:

- `src/lib/dates.ts` pentru luni romanesti si formatare `YYYY-MM`;
- `src/lib/download.ts` pentru download-uri Blob consistente;
- generice pe apelurile `client.get/post/patch` care returnau implicit `any`;
- constantele `ALL_FIRMS`, `ALL_SCOPE`, `ALL_STORES` folosite in loc de string-uri
  hardcodate in filtre;
- eliminare duplicari locale evidente: `LoadingCard`/`ErrorCard`/`Metric`,
  formatters si dead code clar.

Livrabile backend:

- helper public pentru prefixul de distributie si clauzele Retail, fara a
  amesteca raportarea informativa de Cartele (`is_cartela = true`) cu excluderea
  KPI (`NOT is_cartela`);
- paths Vizite citite din env/config, cu fallback local compatibil;
- in flow-urile async Grile, delay-urile explicite devin `await asyncio.sleep`.

Criteriu de iesire:

- `npm run typecheck`;
- `npm run test`;
- teste backend tintite pentru fisierele schimbate.

## Etapa 2 - Primitive frontend comune

Livrabile:

- `useSortable<T>` pentru sortarea tabelelor;
- `SegmentedTabs` pentru switcherele repetate;
- `SideDrawer` pentru drawer-ele laterale;
- `usePersistentState` pentru localStorage;
- adoptare TanStack Query in `Dashboard` si `Campaigns` inainte de spargerea
  componentelor mari.

Criteriu de iesire:

- `Dashboard.tsx` si `Campaigns.tsx` nu mai au cache manual cu `isMountedRef`
  pentru fluxurile principale;
- `npm run typecheck`, `npm run typecheck:strict`, `npm run test`.

## Etapa 3 - Backend scope si repository boundaries

Livrabile:

- un singur builder public pentru params/clauze, fara `ScopeFilters` dataclass
  pana cand exista un motiv sigur si acoperire suficienta;
- `campaigns.py` si `salarii.py` refactorizate primele, pentru ca au suprafata
  mai mica decat Dashboard;
- eliminarea pattern-ului `join_sql`/`where_sql`/`clauses` injectate in repo;
- inlocuirea `.replace()` pe SQL din `repositories/dashboard.py` cu clauze
  generate pentru aliasul corect.

Criteriu de iesire:

- nu exista parametri asyncpg nefolositi in query-urile refactorizate;
- testele de filtre/campaigns/salarii/dashboard trec;
- `mypy backend/ --ignore-missing-imports --explicit-package-bases`.

## Etapa 4 - Spargerea god-files

Livrabile:

- `Dashboard.tsx` impartit in hooks de date si subcomponente current/history;
- `Campaigns.tsx` impartit pe sectiuni Incentive/Promo/Concurs/Focus;
- `get_agent_evaluation_v2` impartit in repository SQL, scoring Python si
  assembler de raspuns;
- `grile_monthly.py` separat in service orchestration + repository + state
  machine pentru operatii lunare;
- `models.py` impartit gradual pe domenii doar dupa stabilizarea importurilor.

Criteriu de iesire:

- fiecare fisier mare scade fara sa schimbe payload-uri;
- testele domeniului si typecheck-ul trec dupa fiecare mutare.

## Etapa 5 - Hardening API, auth si rate limits

Livrabile:

- `ApiError` frontend cu `status`, `detail` si corp JSON parsat;
- `client.ts` fara `any` default si cu `buildUrl` comun pentru toate verbele;
- OIDC discovery rewrite prin JSON parse, nu string replace;
- JWKS cache protejat cu lock si max-stale explicit;
- rate limiter shared prin Valkey/DB doar daca se trece la mai multi workers sau
  mai multe instante.

Criteriu de iesire:

- testele `client.test.ts`, auth si rate-limit acopera cazurile noi;
- nu se relaxeaza politica Authentik/OIDC si nu apare fallback local.

## Etapa 6 - Curatenie finala

Livrabile:

- magic literals business mutate in constante/config cu nume clare;
- query keys TanStack centralizate;
- `SELECT *` eliminat din repo-urile unde schema drift poate produce bug-uri;
- documentatia actualizata dupa fiecare decizie stabila.

## Prima transa de implementare

Prima transa acopera Etapa 1:

1. adaugare `src/lib/dates.ts` si `src/lib/download.ts`;
2. inlocuire duplicari evidente in API/frontend;
3. paths Vizite din env/config cu fallback;
4. `await asyncio.sleep` pentru delay-urile async Grile;
5. validari tintite: `npm run typecheck`, `npm run test`, teste backend pentru
   config/vizite/grile relevante.

## Status implementare - 2026-06-26

Prima transa a fost implementata si extinsa cu doua piese din Etapa 3:
scope/filter canonical si prima mutare SQL Campaigns service -> repository.

Livrabile inchise:

- `src/lib/dates.ts` si `src/lib/download.ts` centralizeaza formatarea lunilor si
  download-urile Blob;
- `src/api/client.ts` are `buildUrl` comun, params pentru toate verbele, default
  generic `unknown`, handling pentru raspunsuri goale si reset pentru latch-ul
  401 dupa un raspuns reusit;
- wrapper-ele API `hr`, `tasks`, `crm`, `salarii`, `grile` si `targetCalculator`
  au generice explicite si folosesc helper-ele comune unde era duplicare;
- componentele cu luni romanesti si filtre "Toate/Toti" folosesc helper-ele
  comune deja existente sau nou adaugate;
- `backend/retail_filters.py` este sursa unica pentru excluderea locatiilor
  `TR %` si pentru clauza `NOT is_cartela`; call-site-urile simple si
  `reporting_refresh.py` folosesc acest helper;
- paths Vizite vin din `config.py`, cu fallback la layout-ul repo-ului;
- delay-urile explicite din flow-urile async Grile folosesc `await asyncio.sleep`;
- OIDC discovery rewrite parseaza JSON si rescrie doar endpoint-urile proxy-uite;
- `services.filters.build_scoped_params` este helper public pentru scope params,
  iar Campaigns/Dashboard utils il folosesc in locul loop-urilor locale;
- interogarea pentru top agenti incentive a fost mutata din
  `services/campaigns.py` in `repositories/campaigns.py`.

Validari rulate:

- `npm run typecheck` - OK;
- `npm run typecheck:strict` - OK;
- `npm run lint` - OK;
- `npm run test` - OK, 11 fisiere / 134 teste;
- `PYTHONPATH=backend backend/venv/bin/pytest backend/tests/ -q` - guard-ul de DB
  a blocat intentionat testele de integrare pe baza de productie; inainte de
  blocaj au trecut 492 teste si 21 au fost skipped;
- `backend/scripts/run_tests_isolated.sh` - OK, PostgreSQL temporar, 535 teste
  passed / 7 skipped;
- `backend/venv/bin/mypy backend --ignore-missing-imports --explicit-package-bases`
  - OK, 153 source files;
- `npm run build` - OK.

Urmatorul batch recomandat:

1. consolidarea builderului public de scope si eliminarea fragment-injection din
   Campaigns repo, dupa ce exista teste pentru fiecare set de clauze;
2. `SegmentedTabs`, `SideDrawer`, `useSortable` si `usePersistentState` pentru
   reducerea duplicarii frontend inainte de spargerea `Dashboard.tsx`;
3. primul split real din `Dashboard.tsx`: data hooks + subcomponente current/history,
   fara schimbari de payload.

## Status implementare - 2026-06-27 (transa 2)

A doua transan a fost executata de un agent de revizuire (opencode) cu verificare
prin 4 subagenti pe zonele riscante. Documentatia (`AGENTS.md`, `README.md`,
`APP_ARCHITECTURE.md`, memoria Codex) a fost citita inainte de implementare.

Livrabile inchise in transa 2:

- **Pasul 1.4** — `_build_scoped_params` din `services/dashboard/utils.py` a fost
  transformat din wrapper functie in import alias direct (`from services.filters
  import build_scoped_params as _build_scoped_params`). Elimina indirection-ul
  fara sa atinga cele 30+ call-site-uri. Zero risc (verificat subagent: wrapper-ul
  era passthrough pur).
- **Pasul 0.2** — 5 teste de integrare noi in
  `backend/tests/test_dashboard_summary_integration.py` care seed-uiesc DB izolat
  si valideaza: (1) Cartela nu contamineaza Retail totals, (2) Cartela respecta
  site_code scope, (3) Forecast math pentru luni partiale, (4) Manager-scope
  OR-expansion se aplica cartela CTE, (5) `TR %` locations excluse. Toate trec
  pe codul vechi (cu `.replace()`) — safety net inainte de refactor.
- **Pasul 3.1 (PRIORITATEA #1)** — Eliminat cele 11 lanțuri `.replace()` din
  `repositories/dashboard.py:fetch_summary` (cel mai fragil cod din codebase).
  Inlocuit cu `cartela_clauses` construite direct de `scoped_clauses(positions,
  site_alias="c", store_alias="cs", agent_alias="c")` in `dashboard_service.py
  :get_summary` — mirror al pattern-ului deja probat in `queries.py:1188-1211`.
  Subtilitatea manager-scope OR-expansion a fost pastrata prin parametrizarea
  `_expand_current_manager_scope` cu `store_alias: str = "s"` (default backward-
  compatible; cartela foloseste `store_alias="cs"`).
- **Ajustari plan** — 3 recomandari din auditul initial au fost corectate ca
  nesigure de subagenti si ELIMINATE din plan: (a) `print()` in `grile_monthly.py`
  e load-bearing (UI + DB + teste) — NU se inlocuieste; (b) `get_stores_coverage`
  are comportament genuin diferit (sentinel, SQL shape) — NU se migreaza; (c)
  `ScopeFilters` dataclass e riscant (~25 site-uri, coverage partiala) — NU se
  introduce.

Validari rulate (toate verzi):

- `npm run typecheck` - OK;
- `npm run typecheck:strict` - OK;
- `npm run lint` - OK;
- `npm run test` - OK, 11 fisiere / 134 teste;
- `backend/scripts/run_tests_isolated.sh` - OK, 540 passed / 7 skipped
  (535 existente + 5 noi);
- `backend/venv/bin/mypy . --ignore-missing-imports --explicit-package-bases`
  - OK, 154 source files;
- `npm run build` - OK;
- `sudo systemctl restart unihub-backend` + `curl http://127.0.0.1:9898/health`
  - OK, `{"status":"ok"}`;
- Logs backend curate (nicio eroare, 401 corect pe dashboard endpoints care
  necesita auth OIDC).

Urmatorul batch recomandat (transa 3):

1. **Pasul 3.2** — Elimina `join_sql`/`where_sql` injection din
   `repositories/salarii.py` (8 metode) — adauga teste repo-level inainte
   (subagent a confirmat coverage WEAK la repo);
2. **Pasul 3.3** — Elimina fragment-injection din `repositories/campaigns.py`
   (5 metode ramase) — campaigns e STRONG testat, securizeaza refactorul;
3. **Pasul 2.1-2.4** — Primitive frontend (`useSortable`, `SegmentedTabs`,
   `SideDrawer`, `usePersistentState`) inainte de spargerea `Dashboard.tsx`;
4. **Pasul 2.5a** — Migreaza `Campaigns.tsx` la TanStack Query (Campaigns intai,
   mai simplu; Dashboard dupa validare in productie).

## Status implementare - 2026-06-27 (Codex follow-up)

Follow-up-ul Codex a verificat handover-ul opencode si a rezolvat regresia
`Hub > Luna in curs`:

- root cause: `App.tsx` pastra luna din `localStorage` daca era valida, deci
  `2026-05` ramanea selectata chiar cand `/api/filters/months` returna
  `2026-06` ca prima luna disponibila;
- fix: `selectCurrentMonth()` selecteaza explicit prima luna backend pentru
  fluxul de luna curenta, iar `currentMonth` nu mai porneste din valoarea salvata;
- hardening: toate rutele `/api/*` primesc `Cache-Control: no-cache, no-store,
  must-revalidate`, `CDN-Cache-Control: no-store` si `Surrogate-Control:
  no-store`;
- curatenie plan Etapa 1/3: call-site-urile backend au fost mutate de pe aliasul
  privat `_build_scoped_params` pe `services.filters.build_scoped_params`, iar
  `Campaigns.tsx` refoloseste `Metric`/`LoadingCard`/`ErrorCard` comune;
- `Agents.tsx` foloseste constantele `ALL_FIRMS`/`ALL_SCOPE`/`ALL_STORES` in
  locul sentinel-elor hardcodate pentru filtrele locale.
- **Pasul 3.3 pentru Campaigns repository**: `repositories/campaigns.py`
  construieste intern clauzele pentru overview/history/promo/incentive si nu mai
  primeste `where_sql`/`*_clauses` din `services/campaigns.py`.
- **Pasul 3.2 pentru Salarii repository**: `repositories/salarii.py` construieste
  intern scope-ul pentru overview/evolution/agents/summary/trend/stores/records;
  `services/salarii.py` nu mai construieste fragmente SQL si paseaza doar filtre
  business.

Decizie confirmata: `VisiteSubtab.tsx` pastreaza `URL.createObjectURL()` pentru
preview de imagine autentificata; nu este un download Blob si nu se migreaza la
`downloadBlob`.

Validari finale follow-up:

- `npm run typecheck` - OK;
- `npm run typecheck:strict` - OK;
- `npm run lint` - OK;
- `npm run test` - OK, 12 fisiere / 136 teste;
- `backend/scripts/run_tests_isolated.sh` - OK, 544 passed / 7 skipped;
- `backend/venv/bin/mypy backend --ignore-missing-imports --explicit-package-bases`
  - OK, 155 source files;
- `backend/venv/bin/mypy . --ignore-missing-imports --explicit-package-bases`
  - OK, 157 source files;
- `npm run build` - OK;
- `sudo systemctl restart unihub-backend.service`, health local si public - OK;
- `/api/filters/months` are no-store headers local si public;
- DB live confirma `2026-06` ca prima luna complet importata, partiala
  (`is_month_final=false`).

Criteriu Pasul 3.3 verificat:

- `rg "where_sql|join_sql|focus_where_sql|totals_where_sql|_clauses: list\\[str\\]"`
  pe `backend/repositories/campaigns.py backend/services/campaigns.py` - fara
  rezultate;
- `PYTHONPATH=backend backend/venv/bin/pytest backend/tests/test_campaign_clauses.py backend/tests/test_campaigns_promos.py -q`
  - OK, 18 passed.

Criteriu Pasul 3.2 verificat:

- `rg "join_sql|where_sql|join_stores|where_clause|where =|conditions:
  list\\[str\\]|params: list\\[Any\\]"` pe Salarii/Campaigns service+repo - fara
  rezultate de injection;
- `PYTHONPATH=backend backend/venv/bin/pytest backend/tests/test_salarii_service.py backend/tests/test_salarii_repository.py -q`
  - OK, 26 passed / 2 skipped fara DB izolata;
- `backend/scripts/run_tests_isolated.sh -k "salarii_repository or salarii_service or salarii_service_overview or salarii_service_summary"`
  - OK, 30 passed;
- testele repo-level confirma invarianta: salariul de 1500 RON ramane in total,
  dar este exclus din media calculata peste pragul de 2000 RON.
