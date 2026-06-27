# Retail refactoring master plan - current

Ultima actualizare: 2026-06-27
Owner operational: Codex
Status general: in executie, incremental, cu commit/push dupa fiecare transa stabila.

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

Snapshot publicat:

- Commit: `0a7c5a1 refactor: stabilize retail scope boundaries`
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
- [ ] plan actualizat dupa fiecare transa implementata;
- [ ] status git curat dupa fiecare commit/push.

Criteriu de iesire:

- `README.md` si `docs/archive/README.md` trimit catre planul activ;
- documentele vechi nu mai sunt prezentate ca sursa curenta;
- worktree curat sau cu schimbari in lucru explicate.

## Milestone 1 - Primitive frontend si query foundation

Status: urmatoarea transa tehnica.

Scop: reducem duplicarea si pregatim spargerea componentelor mari fara sa
schimbam payload-uri sau UI business.

### 1.1 `queryKeys`

Livrabile:

- `src/lib/queryKeys.ts`;
- key factories stabile pentru dashboard, campaigns, agents, grile, settings
  acolo unde exista deja query-uri;
- tipuri suficient de stricte pentru a evita typo-uri in invalidari.

Criteriu:

- nu se schimba niciun request;
- `npm run typecheck:strict` trece.

### 1.2 `useSortable<T>`

Livrabile:

- hook comun pentru sortare numeric/string/null-safe;
- teste pentru directie, toggle si chei cu directie default ascendenta;
- adoptare initiala intr-o componenta cu risc mic.

Criteriu:

- logica veche de sortare ramane compatibila;
- primul adoptator nu schimba coloane sau ordinea initiala.

### 1.3 `SegmentedTabs`

Livrabile:

- componenta comuna pentru switcherele repetitive;
- props simple: `options`, `value`, `onChange`, optional `ariaLabel`;
- test de render/click.

Criteriu:

- adoptare initiala pe `Campaigns` sau alta zona mica;
- nu se modifica routing-ul sau state-ul global.

### 1.4 `SideDrawer`

Livrabile:

- shell comun pentru drawer lateral: backdrop, close button, title, content;
- close pe backdrop si Escape unde se potriveste;
- test de open/close.

Criteriu:

- adoptare initiala doar dupa ce testul componentului comun e verde.

### 1.5 `usePersistentState`

Livrabile:

- hook comun pentru localStorage, cu parse fallback robust;
- teste pentru initializare, update si JSON invalid;
- adoptare graduala in `App.tsx`/`Agents.tsx`.

Criteriu:

- nu reintroduce bugul de luna curenta; `currentMonth` ramane derivat din backend.

### 1.6 Campaigns pe TanStack Query

Livrabile:

- `Campaigns.tsx` trece de la fetch/cache manual la TanStack Query;
- `staleTime: 3 * 60_000`;
- `placeholderData: keepPreviousData`;
- query keys din `queryKeys`;
- test de render pentru separarea metricilor promo vs incentive.

Criteriu:

- `Campaigns.tsx` nu mai foloseste cache manual pentru fluxurile principale;
- nu se sterge `viewCache.ts`;
- validare frontend completa + build.

## Milestone 2 - Dashboard pe TanStack Query si split frontend

Status: dupa Milestone 1.

Livrabile:

- `Dashboard` current/history/history-detail migreaza pe TanStack Query;
- prefetch-ul istoric este reimplementat explicit cu `queryClient.prefetchQuery`;
- agregatul multi-month ramane un singur query cu key dedicat;
- `Dashboard.tsx` se imparte in hooks de date si subcomponente:
  `CurrentDashboard`, `HistoryDashboard`, `BreakdownTable`;
- sortarile repetitive folosesc `useSortable`.

Criteriu:

- payload-urile dashboard nu se schimba;
- primul paint la schimbarea filtrelor ramane rapid cu `keepPreviousData`;
- teste de render pentru KPI-uri si cartela informationala.

## Milestone 3 - Backend domain boundaries ramase

Status: partial inchis.

Inchise:

- Campaigns repository boundary;
- Salarii repository boundary;
- `fetch_summary` cartela CTE fara SQL string surgery.

Ramase:

- `get_agent_evaluation_v2` separat in repository SQL, scoring Python pur si
  response assembler;
- teste pentru pragurile si ponderile evaluarii agentilor inainte de refactor;
- `grile_monthly.py` separat in orchestration + repository + state machine;
- `dashboard_service.get_dashboard_all` mutat de la gather pozitional la gather
  dict-keyed;
- eliminare punctuala a celorlalte `replace()` pe SQL numai daca exista test
  care confirma comportamentul.

Criteriu:

- fiecare domeniu are teste contract inainte de mutari mari;
- `backend/scripts/run_tests_isolated.sh` si mypy trec dupa fiecare pas.

## Milestone 4 - Performanta si optimizare masurata

Status: planificat.

Livrabile:

- baseline de latenta pentru `/api/dashboard/all`, `/api/campaigns/*`,
  `/api/agents/evaluation-v2`, `/api/salarii/*`;
- `EXPLAIN (ANALYZE, BUFFERS)` pentru query-urile lente confirmate;
- indexuri doar unde exista dovada si impact clar;
- reducere presiune pool DB in dashboard gather;
- audit bundle frontend dupa spliturile mari;
- pastrarea lazy-loading-ului pe ecranele principale.

Criteriu:

- optimizarile au masuratori inainte/dupa;
- nu se adauga indexuri speculative;
- nu se cache-uieste global ceva ce depinde de importuri fara invalidare clara.

## Milestone 5 - Hardening API, auth si erori

Status: planificat.

Livrabile:

- `ApiError` frontend cu `status`, `detail`, `body`;
- handling uniform pentru 401/403/409/422;
- OIDC/JWKS cache protejat cu lock si max-stale explicit;
- issuer/config auth fara default-uri periculoase;
- exceptii tipizate pentru Target Calculator finalize conflicts;
- rate limiter shared doar daca runtime-ul trece la multi-worker.

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

Status: planificat.

Livrabile:

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
npm run build
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

- 2026-06-27: creat planul activ unic; arhivate documentele vechi de audit,
  roadmap si handover; snapshotul validat anterior a fost commit-uit si impins
  pe `origin/main` ca `0a7c5a1`.
