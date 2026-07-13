# Retail refactoring master plan - current

Ultima actualizare: 2026-07-13
Owner operational: Codex
Status general: in executie; refactoringul functional continua dupa inchiderea
Wave 2 de securitate si privacy.

Acest fisier este sursa activa pentru refactoring-ul complet Retail. Documentele
anterioare de audit, handover si roadmap sunt pastrate doar pentru trasabilitate
in `docs/archive/refactoring-2026-06-27/`.

## Obiectiv

Refactoring-ul urmareste o aplicatie Retail mai usor de intretinut, mai rapida
si mai sigura, fara schimbari accidentale de business. Tinta nu este doar cod
mai "frumos", ci reducerea riscului operational:

- contracte API clare si stabile;
- backend cu router -> service -> repository respectat pe domenii;
- SQL construit in repository, nu injectat din service;
- frontend cu primitive comune, query cache predictibil si componente sparte pe
  responsabilitati;
- performanta masurata, nu presupusa;
- validari automate si live deployment checks dupa fiecare transa relevanta.

## Reguli fixe

- Nu combinam refactorizari structurale cu schimbari de business.
- Nu relaxam Authentik OIDC si nu adaugam fallback local de auth.
- Nu schimbam raportarea Retail: `Cartele` si locatiile `TR %` nu intra in KPI
  Retail, iar cartela ramane informationala separat.
- Cand `site_code` este selectat, domina scope-ul istoric.
- Salariile sub 2000 RON sunt excluse doar din medii, nu din totaluri sau istoric.
- `print()` din `backend/services/grile_monthly.py` ramane load-bearing; daca
  se adauga logging, se face dual-write `print()` + logger.
- `get_stores_coverage` nu se migreaza la builderul generic de scope; are
  contract diferit.
- Nu introducem `ScopeFilters` dataclass pana cand exista un motiv concret si
  acoperire de teste suficienta.
- `viewCache.ts` ramane cat timp `Settings.tsx` il foloseste.
- Frontend vizibil: `npm run build` inainte de restart live.
- Backend live: restart `unihub-backend.service` si health local/public.

## Stare curenta validata

Snapshot 2026-07-13:

- `main` include Wave 1, Wave 2, P&L si hotfixurile OIDC/H-07;
- H-01A, H-04/H-05 si H-07 sunt active in productie;
- H-02 migration lifecycle, H-01B retained-CNP boundary si H-06 BFF/session
  sunt CI-green si active in productie;
- wave-urile de performanta, modularizare si operatiuni raman active;
- navigatia tinta este Agenti: Prezentare Generala, Grile, Analiza agenti;
  Management: Manageri, Calculator Target, Salarii, P&L.

Planul de audit detaliat este in
`docs/engineering/audit-remediation-status.md`, iar starea Wave 2 in
`docs/engineering/audit-remediation-wave2-status.md`. Milestone-urile de mai
jos raman backlogul de refactoring si nu dubleaza finding-urile de audit.

Ultima transa de cod validata:

- Commit: `a0e2624 refactor: move dashboard data to query cache`
- CI: `28290623749` - OK
- Branch: `main`
- Remote: `origin/main`

Inchise in transele anterioare:

- helper-e comune pentru date si download Blob;
- generice explicite pe clientul API in zonele atinse;
- `currentMonth` selecteaza prima luna returnata de backend, nu luna salvata in
  `localStorage`;
- no-store headers pe `/api/*`;
- builder public `services.filters.build_scoped_params` folosit in locul
  aliasurilor private in call-site-urile refactorizate;
- `.replace()` fragil eliminat din `fetch_summary` pentru cartela CTE;
- repository boundary inchis pentru `Campaigns`;
- repository boundary inchis pentru `Salarii`;
- teste DB izolate pentru summary/cartela/forecast si pentru invarianta
  salariilor sub prag;
- validare completa trecuta: typecheck, strict typecheck, lint, frontend tests,
  backend isolated tests, mypy, build, restart live si health.

## Milestone 0 - Documentatie, baseline, guardrails

Status: in executie.

Livrabile:

- [x] commit + push pentru snapshotul validat anterior;
- [x] arhivare documente vechi de refactoring/audit/handover;
- [x] un singur plan activ: acest fisier;
- [x] plan actualizat dupa fiecare transa implementata;
- [ ] status git curat dupa fiecare commit/push.

Criteriu de iesire:

- `README.md` si `docs/archive/README.md` trimit catre planul activ;
- documentele vechi nu mai sunt prezentate ca sursa curenta;
- worktree curat sau cu schimbari in lucru explicate.

## Milestone 1 - Primitive frontend si query foundation

Status: partial implementat.

Scop: reducem duplicarea si pregatim spargerea componentelor mari fara sa
schimbam payload-uri sau UI business.

### 1.1 `queryKeys`

Livrabile:

- [x] `src/lib/queryKeys.ts`;
- [x] key factories stabile pentru dashboard, campaigns, agents, grile, settings
  acolo unde exista deja query-uri;
- [x] tipuri suficient de stricte pentru a evita typo-uri in invalidari.

Criteriu:

- nu se schimba niciun request;
- `npm run typecheck:strict` trece.

### 1.2 `useSortable<T>`

Livrabile:

- [x] hook comun pentru sortare numeric/string/null-safe;
- [x] teste pentru directie, toggle si chei cu directie default ascendenta;
- [x] adoptare initiala in tabelul generic din `Campaigns.tsx`.

Criteriu:

- logica veche de sortare ramane compatibila;
- primul adoptator nu schimba coloane sau ordinea initiala.

### 1.3 `SegmentedTabs`

Livrabile:

- [x] componenta comuna pentru switcherele repetitive;
- [x] props simple: `options`, `value`, `onChange`, `ariaLabel`;
- [x] test de render server-side;
- [x] adoptare initiala pentru sectiunile `Campaigns`.

Criteriu:

- adoptare initiala pe `Campaigns` sau alta zona mica;
- nu se modifica routing-ul sau state-ul global.

### 1.4 `SideDrawer`

Livrabile:

- [x] shell comun pentru drawer lateral: backdrop, close button, title, content;
- [x] close pe backdrop si Escape;
- [x] test de render open/closed.

Criteriu:

- adoptare initiala doar dupa ce testul componentului comun e verde.

### 1.5 `usePersistentState`

Livrabile:

- [x] hook comun pentru localStorage, cu parse fallback robust;
- [x] teste pentru read/write, string plain, JSON invalid si remove condition;
- [x] adoptare initiala in `App.tsx` pentru tab activ, sectiune Focus, tema,
  sectiune Hub si subtab Management;
- [x] adoptare in `Agents.tsx`, cu validarea valorilor persistate si fara
  acces direct la `localStorage`.

Criteriu:

- nu reintroduce bugul de luna curenta; `currentMonth` ramane derivat din backend.

### 1.6 Campaigns pe TanStack Query

Livrabile:

- [x] `Campaigns.tsx` trece de la fetch/cache manual la TanStack Query;
- [x] `staleTime: 3 * 60_000`;
- [x] `placeholderData: keepPreviousData`;
- [x] query keys din `queryKeys`;
- [x] test de render pentru separarea metricilor promo vs incentive.

Criteriu:

- [x] `Campaigns.tsx` nu mai foloseste cache manual pentru fluxurile principale;
- [x] nu se sterge `viewCache.ts`;
- [x] validare frontend completa + build.

Validare transa:

- `npm run typecheck` - OK;
- `npm run typecheck:strict` - OK;
- `npm run lint` - OK;
- `npm run test` - OK, 18 fisiere / 156 teste;
- `npm run build` - OK;
- `sudo systemctl restart unihub-backend.service` - OK;
- health local si public - OK;
- jurnal `unihub-backend.service` dupa restart - fara warnings.

## Milestone 2 - Dashboard pe TanStack Query si split frontend

Status: partial implementat.

Livrabile:

- [x] `Dashboard` current/history/history-detail migreaza pe TanStack Query;
- [x] `currentHistory` si `yearHistory` raman query-uri separate, cu scopuri si
  chei separate;
- [x] prefetch-ul istoric este reimplementat explicit cu
  `queryClient.prefetchQuery`;
- [x] agregatul multi-month ramane un singur query cu key dedicat;
- [x] `aggregateDashboardDetails` are test pentru totaluri, ponderari KPI,
  daily aggregation si regula `special_cards` din ultima luna;
- [x] `queryKeys.dashboard.yearHistory` adaugat si testat;
- [x] data-fetching-ul Dashboard este extras in `useDashboardData`;
- [ ] `Dashboard.tsx` se imparte in subcomponente:
  `CurrentDashboard`, `HistoryDashboard`, `BreakdownTable`;
- [x] drawerul de performanta, graficele si sumarul salarial sunt extrase in
  `dashboard/PerformanceDetailDrawer.tsx`;
- [x] sortarile repetitive din tabelele Dashboard folosesc `useSortable`;
- [x] `useSortable` accepta chei virtuale prin `getValue` custom.

Criteriu:

- payload-urile dashboard nu se schimba;
- la schimbarea filtrelor/lunii nu se afiseaza date din scope-ul anterior;
- query cache in-memory pastreaza `staleTime` de 3 minute pentru reintoarceri
  rapide in acelasi scope;
- teste pentru KPI-uri agregate, trendul curent si cartela informationala.

Validare transa curenta:

- `npm run typecheck` - OK;
- `npm run lint` - OK;
- `npm run test` - OK, 19 fisiere / 158 teste;
- `npm run build` - OK;
- `sudo systemctl restart unihub-backend.service` - OK;
- health local si public - OK;
- jurnal `unihub-backend.service` dupa restart - fara warnings;
- GitHub Actions CI `28290623749` - OK;
- `/api/dashboard/all?month=2026-06` local a raspuns `401`, asteptat fara
  sesiune Authentik; nu s-a folosit ca proba de business fara autentificare.

Validare extractie `useDashboardData`:

- `npm run typecheck` - OK;
- `npm run lint` - OK;
- `npm run test` - OK, 19 fisiere / 158 teste;
- `npm run build` - OK;
- `sudo systemctl restart unihub-backend.service` - OK;
- health local si public - OK dupa warm-up;
- jurnal `unihub-backend.service` dupa restart - fara warnings.

Validare sortari Dashboard:

- `npm run typecheck` - OK;
- `npm run lint` - OK;
- `npm run test` - OK, 19 fisiere / 159 teste;
- `npm run build` - OK;
- `sudo systemctl restart unihub-backend.service` - OK;
- health local si public - OK;
- jurnal `unihub-backend.service` dupa restart - fara warnings.

## Milestone 3 - Backend domain boundaries ramase

Status: partial inchis.

Inchise:

- Campaigns repository boundary;
- Salarii repository boundary;
- `fetch_summary` cartela CTE fara SQL string surgery.

Ramase:

- [x] `get_agent_evaluation_v2` separat in repository SQL, scoring Python pur
  si response assembler;
- [x] teste pentru pragurile, ponderile, eligibilitatea si trendurile evaluarii
  agentilor;
- [x] state machine-ul pur pentru lifecycle-ul operatiilor lunare Grile este
  separat si acoperit exhaustiv, iar CAS-urile start/heartbeat/finish/fail si
  atasarea jobului sunt mutate in repository;
- [ ] rezervarea initiala si checkpointurile per magazin pentru reset trebuie
  mutate din `grile_monthly.py` in acelasi boundary de repository;
- [x] `dashboard_service.get_dashboard_all` mutat de la gather pozitional la
  rezultate concurente adresate nominal, fara indexuri numerice fragile;
- eliminare punctuala a celorlalte `replace()` pe SQL numai daca exista test
  care confirma comportamentul.

Criteriu:

- fiecare domeniu are teste contract inainte de mutari mari;
- `backend/scripts/run_tests_isolated.sh` si mypy trec dupa fiecare pas.

## Milestone 4 - Performanta si optimizare masurata

Status: in executie.

Livrabile:

- [x] baseline de latenta pentru `/api/dashboard/all`, `/api/campaigns/*`,
  `/api/agents/evaluation-v2`, `/api/salarii/*`;
- [x] primul `EXPLAIN (ANALYZE, BUFFERS)` pentru Agent Evaluation v2 confirma
  scanarea completa a `sales_transactions` pe calea premium glass;
- [x] indexul Agent Evaluation v2 este justificat, activ si acceptat: rezultat
  identic, plannerul foloseste indexul partial si mediana este redusa cu 76,7%;
- [x] sumarul promo/incentive este calculat o singura data in Dashboard all;
  raspuns identic si mediana redusa cu 25,8%;
- reducere presiune pool DB in dashboard gather;
- audit bundle frontend dupa spliturile mari;
- pastrarea lazy-loading-ului pe ecranele principale.

Criteriu:

- optimizarile au masuratori inainte/dupa;
- nu se adauga indexuri speculative;
- nu se cache-uieste global ceva ce depinde de importuri fara invalidare clara.

## Milestone 5 - Hardening API, auth si erori

Status: partial implementat prin audit Wave 1 si Wave 2.

Livrabile:

- [x] `ApiError` frontend cu `status`, `detail`, `body`;
- [x] helper uniform pentru mesajele sigure 401/403/404/409/422, adoptat in
  fluxurile cu impact ridicat Calculator Target, Grile si exporturi/importuri;
- [x] OIDC/JWKS cache protejat cu lock, single-flight, cooldown si max-stale explicit;
- [x] issuer/config auth tipizat si fail-closed, fara default-uri periculoase;
- [x] exceptii tipizate pentru conflictele de revizie/finalizare Target
  Calculator, mapate la 409 si afisate cu mesajul controlat de backend;
- [x] rate limiter distribuit Valkey, cu trusted-proxy parsing, HMAC si failure-closed;

Ramase: modulele legacy Tasks/HR/CRM trebuie sa afiseze erorile actiunilor in
UI, nu doar in consola; fallback-urile pentru 5xx si erori de retea raman
intentionat generice.

Criteriu:

- nu apare fallback local de auth;
- testele auth/client/rate-limit acopera cazurile noi;
- mesajele UI raman clare pentru 403 si stale writes.

## Milestone 6 - Curatenie de model si constante

Status: planificat.

Livrabile:

- `models.py` impartit gradual pe domenii;
- `Literal`, pattern-uri si constrangeri Pydantic pentru status/luni/valori;
- magic literals mutate in constante business numite;
- `SELECT *` eliminat din repo-urile unde schema drift poate produce bug-uri;
- grupurile RBAC similare documentate sau unificate.

Criteriu:

- fiecare mutare de model pastreaza compatibilitatea API;
- testele de serializare si mypy trec.

## Milestone 7 - Inchidere

Status: in executie.

Livrabile:

- [x] workflow CI extins cu typecheck general si strict, lint, unit tests,
  audit npm runtime, build, Playwright si artefacte de diagnostic;
- [x] smoke WCAG A/AA automat pentru Hub si Management, fara excluderi de reguli;
- [x] acceptarea workflow-ului pe merge ref-ul PR #50: GitHub Actions
  `29225724923`, backend si frontend verzi;
- [x] readiness/liveness separate, SLO-uri, alerte si unitati systemd
  versionate; PR #58 acceptat pe merge ref si rollout controlat la
  `2fdb5e8ed3fe2f70ede820bc6247b6075da07e14`, cu probe locale/publice si
  target Prometheus `up`;
- audit final pe docs, status git si live health;
- checklist de performanta cu valori finale;
- verificare ca documentele arhivate nu mai sunt folosite ca instructiuni active;
- commit/push final;
- optional: tag sau release intern daca se doreste.

Criteriu final:

- toate suitele relevante trec;
- `npm run build` si restart live reusite;
- local si public health OK;
- jurnalele serviciului fara erori noi;
- planul curent marcheaza clar ce este inchis si ce ramane backlog explicit.

## Protocol de validare

Pentru frontend:

```bash
npm run typecheck
npm run typecheck:strict
npm run lint
npm run test
npm audit --omit=dev --audit-level=high
npm run build
CI=1 npm run test:e2e
```

Pentru backend:

```bash
backend/scripts/run_tests_isolated.sh
backend/venv/bin/mypy backend --ignore-missing-imports --explicit-package-bases
backend/venv/bin/mypy . --ignore-missing-imports --explicit-package-bases
```

Pentru live path:

```bash
sudo systemctl restart unihub-backend.service
curl -fsS http://127.0.0.1:9898/health
curl -fsS https://retail.unihub.ro/health
```

Ruleaza validarile secvential, nu in paralel, pentru ca `typecheck` si Vite
build pot concura pe `dist/`.

## Update log

- 2026-07-13: `/livez` process-only si `/readyz` dependency-backed sunt
  separate; `/health` ramane alias compatibil. Readiness are timeout total de
  doua secunde, metrici finite si raspuns 503 fara detalii. Regulile SLO exclud
  probele, iar unitatile systemd web/worker/migrations sunt versionate si
  hardenizate. Validarea merge-ref si rolloutul raman criterii de acceptare.
- 2026-07-13: gate-urile frontend CI au fost extinse cu typecheck strict,
  ESLint, audit runtime, build si 15 scenarii Playwright. Doua smoke-uri axe
  acopera Hub si Management pentru incalcari WCAG A/AA critical/serious;
  problemele reale de nume accesibil si contrast gasite la introducerea gate-ului
  au fost remediate. Acceptarea locala si merge ref-ul PR #50 sunt verzi;
  GitHub Actions `29225724923` a trecut backend si frontend.
- 2026-07-13: Dashboard reutilizeaza acelasi task promo/incentive pentru carduri
  si payload; hash identic, mediana 486,7 -> 361,0 ms (-25,8%). Comparatia
  acceptata foloseste explicit aceleasi fisiere live ignorate din `data/`.
- 2026-07-13: migratia 025 activa in productie; Agent Evaluation v2 pastreaza
  exact 151 rezultate si acelasi hash, foloseste indexul partial de 19 MB,
  reduce `EXPLAIN` 647,7 -> 179,1 ms si mediana service 565,6 -> 131,8 ms.
- 2026-07-13: baseline read-only pe rolul DB runtime: Dashboard median 489,7
  ms, Agent Evaluation v2 565,6 ms, Campaigns 6,5 ms si Salarii 22,5 ms.
  `EXPLAIN ANALYZE` a justificat exclusiv indexul partial covering din migratia
  025; rezultatele dupa migrare raman gate obligatoriu.
- 2026-07-13: evaluarea agentilor separata in query-uri repository, scoring
  Python pur si assembler testat; `Agents.tsx` foloseste persistenta comuna;
  `ApiError` pastreaza status/detail/body; drawerul de performanta a fost extras
  din `Dashboard.tsx`. Validari locale: 1070 backend tests, 184 frontend tests,
  mypy, typecheck strict, lint, build si 13 scenarii Playwright verzi; preview-ul
  E2E este detinut exclusiv de fiecare rulare si nu mai reutilizeaza procese
  efemere ramase de la rulari intrerupte.
- 2026-07-13: H-02, H-01B si H-06 reconciliate ca active in productie;
  `get_dashboard_all` foloseste rezultate concurente adresate nominal.
  Validare locala: mypy verde si 1053 teste backend trecute, 7 sarite.
- 2026-07-12: reconciliat planul cu Wave 1/Wave 2; H-01A, H-04/H-05 si H-07
  sunt implementate si CI-green pe branchul Wave 2, cu activarea de productie
  H-07 si finding-urile H-06/H-01B/H-02 ramase explicit deschise; actualizata
  navigatia Salarii/Grile.

- 2026-06-27: creat planul activ unic; arhivate documentele vechi de audit,
  roadmap si handover; snapshotul validat anterior a fost commit-uit si impins
  pe `origin/main` ca `0a7c5a1`.
- 2026-06-27: Milestone 1 partial inchis: adaugate `queryKeys`,
  `useSortable`, `SegmentedTabs`, `SideDrawer`, `usePersistentState`; `Campaigns`
  a trecut pe TanStack Query pentru fluxurile principale, iar cache-ul manual cu
  `isMountedRef`/`viewCache` a fost eliminat din acest ecran.
- 2026-06-27: `usePersistentState` a fost adoptat in `App.tsx` pentru
  persistarile simple. `currentMonth` a ramas exclus intentionat si continua sa
  fie setat din lista backend de luni disponibile.
- 2026-06-27: CI backend a fost facut independent de fisierul local
  `data/visits/visits.db`; `run_tests_isolated.sh` creeaza acum un SQLite
  temporar pentru testele CRM. Comanda backend CI cu coverage a trecut local:
  544 passed / 7 skipped, critical coverage PASS.
