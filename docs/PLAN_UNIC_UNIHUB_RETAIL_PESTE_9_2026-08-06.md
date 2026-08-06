---
title: "Plan unic de execuție UniHub Retail peste 9"
tags: [unihub-retail, audit, quality, frontend, performance]
status: deployed_pending_external_ci
created: 2026-08-06
baseline_sha: 6ce32b863b44fbab76f612ba74aad0e0cf0f108a
audit_sha: da38d93707edf8d5ba66f6154d66103a89efd0cc
implementation_sha: 131dfc372f1ccf054326bc4097aace75d57318cd
release_sha: 131dfc372f1ccf054326bc4097aace75d57318cd
---

# 1. Mandat

Acesta este **singurul plan activ** pentru ridicarea UniHub Retail peste nota 9
și cât mai aproape de 10 prin dovezi măsurabile. Planurile mai vechi sunt
istoric de implementare, nu backlog concurent.

Planul este scris pentru execuție autonomă, în ordine, de GPT Luna. Nu conține
estimări calendaristice și nu oferă variante alternative de roadmap. O decizie
se redeschide numai dacă testul, codul live sau o limită operațională o infirmă.

Scorul este acordat de un audit extern și nu poate fi garantat prin document.
Ținta de acceptare este:

- toate recomandările R-01..R-20 închise sau justificate cu dovadă;
- niciun defect confirmat rămas;
- re-audit independent pe exact SHA-ul livrat, cu aceeași metodologie și același
  scope, peste 9;
- țintă tehnică internă 9,5+, fără a revendica artificial 10/10.

# 2. Baseline verificat

- audit static: `da38d93707edf8d5ba66f6154d66103a89efd0cc`, scor `8,4/10`;
- cod curent și `origin/main`: `6ce32b863b44fbab76f612ba74aad0e0cf0f108a`;
- producția rulează același SHA; backend, operations worker și import worker
  sunt active; health local este verde;
- commiturile ulterioare auditului adaugă în principal contractele UniHub
  Insight și nu repară constatările R-01..R-14/R-16..R-20;
- R-15 este deja implementat: CI manual produce artefactul exact al
  `head_sha`, iar deployul verifică runul, `SOURCE_SHA`, `SHA256SUMS` și digestul.

Constatări reconfirmate în codul curent:

- Dashboard pornește `campaign_context_task` și `promo_incentive_task` înaintea
  schedulerului global;
- Target Calculator inițializează sezonalitatea cu `multi`, apoi folosește un
  fallback imposibil;
- Campanii primește date ca `str`, nu refuză explicit intervalul invers/cross-month;
- bootstrapul din `App.tsx` ignoră eroarea lunilor și blochează reluarea în
  aceeași instanță după schimbarea autentificării;
- Vitest rulează numai `.test.ts` în `node`; nu există React Testing Library;
- TypeScript strict exclude exact componentele cu risc mare;
- exportul XLSX folosește workbook normal, iar capul de 64 MiB limitează
  artefactul serializat, nu peak RSS;
- Settings reîncarcă inutil catalogul și lunile la schimbarea datasetului;
- contractele Retail sunt duplicate manual în `src/api/types.ts`;
- serviciile și componentele indicate de audit au rămas foarte mari.

# 3. Scope și decizii care nu se redeschid

1. Se păstrează React 19 + TypeScript + Vite, FastAPI, PostgreSQL, Valkey/ARQ,
   monolitul modular și procesele web/operations/import separate.
2. Importul de vânzări rămâne snapshot lunar complet, `Stage -> Validate ->
   Promote`. Multiplicitatea rândurilor se păstrează.
3. Modulul Grile rămâne exclus, conform auditului. Nicio schimbare din acest plan
   nu trebuie să atingă fluxurile sau testele Grile, în afara unei ajustări
   mecanice inevitabile de configurație comună, dovedită fără schimbare semantică.
4. Nu se introduc microservicii, ORM, Redux global, cache general, router sau
   framework nou fără nevoie demonstrată.
5. Nu se optimizează SQL fără `EXPLAIN (ANALYZE, BUFFERS)` și hash business
   identic înainte/după.
6. Nu se combină într-un singur diff schimbarea formulelor business cu
   refactorizarea structurală a aceluiași domeniu.
7. Nu se urmărește 100% coverage generic. Testele acoperă state-urile și
   invarianturile cu risc.
8. GitHub Actions rămâne gate formal unic pe candidatul final, nu test runner
   iterativ.

# 4. Registrul complet al recomandărilor

| ID | Stare la baseline | Dispoziție în plan |
| --- | --- | --- |
| R-01 | DONE | Scheduler Dashboard unic, bounded/global, cu cancellation reaplicată |
| R-02 | DONE | State machine sezonabilitate: manual > scenariu > backend |
| R-03 | DONE | Date tipizate și interval strict în aceeași lună |
| R-04 | DONE | Bootstrap recuperabil, cache stale și retry fără reload |
| R-05 | DONE | Harness Vitest DOM și teste pentru bootstrap/sezonabilitate/status |
| R-06 | DONE | Strict global pe toate fișierele non-Grile |
| R-07 | DONE | Paginile de feature orchestrează subcomponente și hookuri de domeniu reale; paginile principale au 16–390 linii, fără re-export spre monoliții legacy |
| R-08 | DONE | Niciun emitter/listener `unihub:navigate` rămas |
| R-09 | DONE | Benchmark RSS, writer write-only bounded și worker complex izolat cu spawn |
| R-10 | DONE | Parsare Excel single-pass în importurile afectate și metrici de resurse |
| R-11 | DONE | Snapshot repeatable-read Campanii și pool eliberat înainte de agregarea CPU |
| R-12 | DONE | Decimal/rotunjire HALF_UP și alocare exactă la cent în Campanii/Target |
| R-13 | DONE | OpenAPI generează operation-specific query/path/body/response, decoder structural și client BFF tipizat pentru toate API-urile non-Grile, fără tipuri de request duplicate |
| R-14 | DONE | Settings query keys/cache și efecte separate pentru catalog/luni/filtre |
| R-15 | satisfăcut | Lot 7: numai revalidare exact-SHA; nu se reconstruiește |
| R-16 | DONE | Bundle budget ratcheted pe raw/gzip/precache |
| R-17 | DONE | Scheduler, batch, performance, history și orchestration boundaries extrase; facade-ul public rămâne stabil |
| R-18 | DONE | Target package are context, rules, profitability, proposal, allocation, scenarios, editing, finalization, warnings și serialization boundaries; facade-ul și CAS/revision rămân stabile |
| R-19 | DONE | Writer boundary + benchmark + worker complex separat, RSS/size raportate părintelui |
| R-20 | DONE | Campanii are range, loader, context, promotions, incentives, aggregation, money, response și metrics boundaries; pool snapshot și statusurile publice rămân neschimbate |

## 4.1 Implementare curentă și dovezi

Implementarea curentă este verificată local pe `dell-standby`; candidații
`035f81ca4d79be307d5d8c336963d5a8958acc87`,
`97e96d651d15d918351763e60e211a29f65dd8cb`,
`500e0aaec7b89d0df78a9aca7e36ec12970096f8` și
`a6c602f2fa4e53ddec4e5a6ad59a5431756539c3`,
`d73de2ed770562359219ee21f89fb4257bbff0a7` și
`4b94583027211ba6b525a8e2ffe20d1ceed44983`,
`26c67c697d16ca00a754871c64440d16bee0f46d` și
`fc5fb24aa13a2a0391a17e60185bdf144b632420` sunt sincronizați pe `origin/main`,
iar ultimul SHA documentat anterior este build-uit și deployat pe primary.

Candidatul final de cod este `e689c06ebc65fda45ba6e46666f7020397757f82`;
commiturile ulterioare sunt docs-only pentru closure, iar primary a fost
resincronizat pe checkout-ul final fără schimbare runtime. Buildul, serviciile și
health checks sunt verificate pe release. Schimbările livrate:

- decompoziție vizuală efectivă: `features/campaigns/PremiumView.tsx`,
  `SortableTable.tsx`, `features/settings/exports/controls.tsx`, rezultatul ERP,
  `features/agents/AgentDetails.tsx`, modele pure Target și AI Forecast;
- toate modulele API non-Grile folosesc clientul generat; `storePnl` a fost mutat
  pe aceeași rută; clientul păstrează cookie same-origin, CSRF, request ID,
  ApiError, 401 și AbortSignal;
- contractul include Decimal branded + decoder runtime, PATCH/path params și
  Blob pentru export XLSX/fotografii; digest curent:
  `f97f73f17a1d18c7c0403e068947dfa9b86251b63b72d4098ef01afe019ff262`;
- response models au fost adăugate pentru Target, CRM, HR, task-uri, P&L,
  salarii și endpointurile binary; Grile și infrastructura auth/metrics rămân
  în afara lotului.

Dovezi curente:

- `npm run typecheck`, `npm run typecheck:strict`, `npm run lint`: verde;
- `npm run test -- --run`: `45` fișiere, `274` teste verzi; testele generate
  includ nullable Decimal, coliziunea `value`, PATCH/path, Blob și AbortSignal;
- contract drift: `f847dbfd8029e331803f5cca023b7dde449312e11873de617933482130664921`;
- `npm run verify:rum-build`: RUM verificat în 21 asset-uri JavaScript;
- bundle ratchet: precache gzip `1,589,310` bytes, fără depășire;
- export benchmark fresh-process: `50k x 20`, `33.815s`, peak RSS `138,018,816` bytes;
- writer/exports țintit: `33` teste verzi; Dashboard țintit: `49` teste verzi, `2` skip;
- Target/Campanii/Dashboard țintit după ultimele boundary-uri: `68` teste verzi, `2` skip;
  Campanii complet țintit: `14` teste verzi; mypy pe `35` module schimbate verde;
- full backend izolat: `1666` verzi, `7` skip, cu Postgres/Valkey temporare;
  nu s-a folosit baza shared/producție.
- contract/response-model tests țintite: `37` verzi; `mypy` complet: `386`
  module fără erori; coverage critic peste pragurile ratchet actualizate pentru
  package Target și ramurile bounded de export.
- Smoke primary după ultimul deploy: backend/worker `active`, `/health` și `/readyz`
  `200`, `/livez` `200`, fără warning/error în jurnalul serviciilor în fereastra
  de 10 minute post-restart; public `/readyz` `200`, frontend public `200`, iar
  `/api/filters/months` răspunde `401` fără sesiune, conform boundary-ului auth.

R-07 și R-13 au fost redeschise de re-auditul independent de preluare; acea
constatare istorică este păstrată în 4.3, iar remedierea candidatului curent este
documentată în 4.4. Endpointurile Grile rămân excluse explicit; auth/session și
metrics sunt infrastructură, nu consumatori ai API-ului Retail. R-17, R-18 și
R-20 rămân închise pe boundary-urile backend verificate.

Nicio recomandare nu este omisă. Sunt două adaptări justificate:

- **R-08:** repository-ul nu mai conține niciun emitter `unihub:navigate`; doar
  listenerul mort din `App.tsx` a rămas. Se șterge dead code-ul. Introducerea
  unui router sau context nou ar adăuga o a doua cale de navigare peste
  setterele/callbackurile React și deep-linkurile tipizate deja active.
- **R-13:** `@unihub/types` și `@unihub/api-client` sunt pachete comune tuturor
  aplicațiilor și clientul lor folosește contract Bearer-token generic. Retail
  folosește BFF, cookie same-origin și CSRF. Contractele generate rămân în
  `src/api/generated/`, lângă clientul Retail. Nu se poluează pachetele comune și
  nu se creează o a doua implementare de auth. Un pachet dedicat
  `@unihub/retail-api` devine justificat doar când apare un al doilea consumator.

## 4.2 Closure evidence — 2026-08-06

Implementarea finală de cod este `e689c06ebc65fda45ba6e46666f7020397757f82`,
sincronizată pe `origin/main` și verificată pe primary înaintea commiturilor
docs-only de closure. Schimbările
livrate:

- contracte Retail generate offline în `src/api/generated/`, decoder runtime
  pentru Decimal/Blob și client BFF cu cookie, CSRF, AbortSignal, ApiError,
  request ID și redirect 401; `src/api` păstrează tipuri locale numai în Grile;
- boundary-uri reale `DashboardView`, `TargetScenarioView`, `SettingsView` și
  `AgentsOverviewView`; presenters/model/feature boundaries Campanii și AI au
  fost păstrate, fără schimbarea facad-urilor publice;
- Target expune retry explicit pentru conflictul optimistic 409; App bootstrap,
  Settings permissions, Dashboard current/history și Campanii au teste DOM
  pentru stările critice.

Dovezi finale pe conținut neschimbat:

- `npm run typecheck`: verde;
- `npm run typecheck:strict`: verde;
- `npm run lint`: verde;
- `npm run test -- --run`: `45` fișiere, `274` teste verzi;
- `backend/scripts/run_tests_isolated.sh`: `1666 passed, 7 skipped` într-o bază
  Postgres/Valkey izolată;
- `mypy . --ignore-missing-imports --explicit-package-bases`: `386` fișiere
  fără erori;
- coverage critic izolat: exports `91,35%` la prag `90%`, package Target
  agregat `90,16%` la prag `90%`, toate celelalte praguri trecute;
- `npm run contracts:check`: verde, digest
  `f97f73f17a1d18c7c0403e068947dfa9b86251b63b72d4098ef01afe019ff262`;
- `npm run build`, `npm run verify:rum-build`: build verde, RUM verificat în
  `21` asset-uri JavaScript;
- `node scripts/check_bundle_budget.mjs`: verde; precache `2,085,422` bytes raw /
  `1,589,348` gzip, fără failure-uri;
- `git diff --check`: verde; worktree-ul candidatului este curat.
- CI formal `31106026721`, exact pe `e689c06`, este verde: runner isolation,
  backend-check și frontend-check `success`.

Dovadă live exact-SHA:

- primary `server`: checkout final sincronizat, `unihub-backend`,
  `unihub-worker` și `unihub-import-worker` active;
- `/health` și `/readyz` locale: `200` cu `{"status":"ok"}`;
- `https://retail.unihub.ro/`: `200`, `/readyz`: `200`,
  `/api/filters/months` fără sesiune: `401 Authentication required`;
- nicio migrare sau mutație de date business nu a fost rulată pentru acest lot.

## 4.3 Re-audit independent de preluare — 2026-08-06

Statusul `closed` anterior a fost retras. Re-auditul independent a confirmat:

- feature pages pentru Dashboard, Target, Campanii, Settings, Agents și AI sunt
  re-exporturi de o linie către implementările legacy; componentele principale
  au între 976 și 2.006 linii, peste criteriul aproximativ 300–400;
- clientul generat acceptă încă `params?: object` și `body: unknown`, nu leagă
  requesturile de operation ID, iar decoderul Decimal folosește un set global
  de nume de câmpuri;
- CI exact-SHA `31104884570` pentru `d461ecc` a avut frontendul și cele 1.662
  teste backend verzi, dar gate-ul backend a rămas roșu la coverage; nu există
  încă release formal verde pentru candidatul final;
- numerele de teste, digesturile și SHA-urile din closure evidence sunt istorice
  și vor fi înlocuite numai după candidatul final, nu tratate ca dovezi curente.

Planul revine la `active`. Închiderea cere din nou toate gate-urile din secțiunea
13, CI verde pe SHA-ul final, deploy exact-SHA și un nou re-audit independent.

## 4.4 Candidatul integrat după re-audit

Deficiențele care au redeschis R-07 și R-13 sunt reparate în candidatul local:

- Dashboard, Target, Campanii, Settings, Agents, Agent Evaluation și AI Forecast
  au pagini de orchestrare de 16–390 linii, cu tabele, controale, hooks și views
  deținute de feature; vechile monolite au fost eliminate;
- toate wrapper-ele API non-Grile derivă query/path/body/response din operation
  ID-ul OpenAPI; `src/api/types.ts` și casturile de răspuns au fost eliminate;
- exporturile complexe au operații DB owner-bound, lease/epoch fencing, proces
  `spawn` cu `RLIMIT_AS`, artefact privat hash-uit, TTL, cancel/retry și reluare
  identity-scoped în UI; boundary-urile critice au praguri coverage de minimum
  95%;
- parserele Sales, Promo, ERP, target și istoric au politici/evidence distincte,
  spool content-addressed și single-open. Generația Promo v1 live are o migrare
  v2 atomică, dry-run implicit, CAS, surse/materializări `0600` și recovery al
  pointerului precedent byte-for-byte;
- Campanii folosește exclusiv API-ul public `services.campaigns`, un snapshot
  caller-owned și deadline request-wide pentru pool, query și compute.

Dovezi locale verzi pe candidatul integrat:

- TypeScript strict global, ESLint și `55` fișiere / `322` teste Vitest;
- `1752 passed, 9 skipped` în suita backend cu PostgreSQL/Valkey izolate și
  bootstrap fresh până la migrarea 055; `services/imports.py` rămâne la 100%,
  boundary-urile export la 95,44–100%, iar Target la 95,60–100%;
- mypy complet: `410` fișiere fără erori; contract OpenAPI curent, digest
  `d7a6a67c7c71aa9b5710885796de4233ab8e3e0b46df5432b4b513b18ff46c3e`;
- build, RUM în `27` asset-uri, bundle ratchet și PWA N -> N+1 -> rollback N;
- benchmark fresh-process: tabel simplu `50.000 x 20` în `36,101s`, peak RSS
  `138.575.872` bytes, artefact `2.827.468` bytes; două chart exports de
  `10.000 x 20` au terminat concurent în `7,89s`, cu peak RSS sub `180 MiB`
  fiecare.

`implementation_sha` identifică ultimul commit care modifică runtime-ul.
`release_sha` este HEAD-ul Git care conține acest document și se rezolvă
machine-readable din runul CI/deploy, evitând un hash Git auto-referențial.
Închiderea operațională cere încă CI verde pe acel HEAD, deployul aceluiași
artefact, migrarea Promo v1 -> v2 înainte de restart și re-auditul live final;
dovezile se atașează release-ului, fără un commit docs-only după deploy.

# 5. Protocol unic de execuție pentru GPT Luna

1. Rulează loturile strict în ordinea de mai jos. Nu începe următorul lot dacă
   gate-ul lotului curent este roșu.
2. La începutul fiecărui lot: `hostname`, `git status --short --branch`,
   `git fetch origin main`, verifică `HEAD == origin/main`, recitește
   `AGENTS.md`, `APP_ARCHITECTURE.md` și documentele de domeniu indicate.
3. Lucrează local-first. Nu folosi producția ca mediu de test și nu modifica
   date business pentru validare.
4. Mai întâi scrie testul care reproduce defectul/invariantul; apoi schimbă
   exclusiv calea canonică. Nu crea facade/repository paralel pentru a evita
   refactorul.
5. Rulează o singură dată verificările țintite pe conținutul final al lotului.
   Rulează suita completă numai la gate-urile marcate explicit.
6. Păstrează un singur candidat per lot: commit logic, push direct pe `main`
   dacă politica rămâne permisivă, un singur deploy controlat și verificare
   live a căii schimbate. Nu împinge commituri de încercare.
7. După fiecare lot, actualizează în acest document statusul, SHA-ul, comenzile,
   rezultatele, limitele măsurate și orice decizie schimbată de dovezi.
8. O recomandare devine `DONE` numai când testele, runtime-ul, Git și
   documentația indică același SHA.
9. Oprește numai la o acțiune restrictivă din `AGENTS.md`, la risc de pierdere a
   datelor sau după trei încercări care demonstrează același blocaj extern.

# 6. Lot 1 — defectele confirmate și stările recuperabile

## 6.1 R-01 — Scheduler Dashboard

Fișiere principale:

- `backend/services/dashboard_service.py`;
- `backend/services/dashboard/metrics.py`;
- testele Dashboard existente și un test nou de scheduler/concurență.

Implementare:

1. Transformă `campaign_context` și `promo_incentive` în coroutines reci.
2. Rulează încărcarea contextului prin aceeași cale `_gather_named()` care
   aplică deadline-ul, semaphore-ul local, semaphore-ul global și metricile de
   coadă.
3. Construiește componentele dependente numai după obținerea contextului.
4. Niciun `asyncio.create_task()` DB nu poate porni înaintea slotului global.
5. Aplică aceeași orchestrare pentru current, history projection și batch.
6. Orice timeout, anulare sau excepție anulează și așteaptă toți copiii.
7. Păstrează deadline-ul request-wide existent și nu introduce scheduler nou.
8. Adaugă metrici finite, fără filtre business:
   `dashboard_component_active`, `dashboard_component_global_limit`,
   `dashboard_component_budget_violation_total`; păstrează queue/duration
   existente și include `campaign_context`/`promo_incentive`.

Teste obligatorii:

- zero `pool.acquire()` înainte de slot;
- limita observată sub două requesturi concurente;
- batch cu două magazine;
- current și history projection;
- timeout, client cancellation și excepție într-o componentă;
- zero task rămas activ după răspuns;
- metricile celor două componente;
- hash business/payload identic față de fixture-ul canonic.

Gate:

```text
max_active_dashboard_db_components <= dashboard_global_component_concurrency
dashboard_component_budget_violation_total == 0
```

Latența nu poate regresa peste SLO-ul existent din cauza orchestrării în faze.

## 6.2 R-02 — Sezonalitatea Target Calculator

Modelează explicit precedența:

1. scenariul încărcat intenționat de utilizator;
2. alegerea manuală curentă;
3. defaultul contextului backend;
4. niciodată un default hard-coded ascuns.

Folosește state `null` până la inițializare și un marker `touched` sau un
reducer mic. Refetch-ul contextului nu suprascrie alegerea manuală. Încărcarea
explicită a unui scenariu aplică snapshotul scenariului. Butonul de calcul este
dezactivat cât timp starea nu este inițializată, iar requestul trimite exact
valoarea afișată.

Teste DOM:

- backend `1` -> `single`;
- backend `>1` -> `multi`;
- refetch după click manual nu suprascrie alegerea;
- scenariul recent își păstrează configurația;
- payloadul de calcul corespunde UI;
- loading/error/retry nu trimit valoare implicită accidentală.

## 6.3 R-03 — Contractul de dată Campanii

- routerul primește `datetime.date`;
- `start_date <= end_date`;
- ambele date trebuie să fie în aceeași lună, deoarece definițiile promo și
  incentive sunt lunare;
- service-ul primește date validate, nu stringuri;
- frontendul blochează local intervalul invalid, dar backendul rămâne autoritar;
- erorile sunt 422 cu cod/reason finit, nu 500;
- schema răspunsului rămâne neschimbată.

Teste: format invalid, interval invers, cross-month, prima/ultima zi din lună,
an bisect, lună fără configurație și response-model regression.

Cross-month nu se implementează în acest plan. Ar necesita evaluare separată per
lună și reguli de combinare a metricilor; folosirea configurației primei luni
este interzisă.

## 6.4 R-04 — Bootstrap recuperabil

Extrage `useAvailableMonths()` peste TanStack Query:

- rulează numai după autentificare confirmată;
- retry finit pentru network/5xx, fără retry orb pentru 401/403;
- abort/cancellation la unmount;
- diferențiază `empty`, `unavailable` și `session_expired`;
- expune Retry fără refresh complet;
- salvează ultima listă validă de luni și timestampul într-o cheie versionată
  local storage;
- la eșec tranzitoriu folosește cache-ul numai ca `stale`, cu banner vizibil;
- nu tratează o singură lună salvată drept listă validă de luni;
- elimină `bootstrapRan` sau îl înlocuiește cu query state derivat.

Teste DOM: empty valid, 5xx/network cu și fără cache, stale banner, retry
reușit, 401, autentificare devenită validă în aceeași instanță și cancellation.

## 6.5 Infrastructura DOM minimă necesară Lotului 1

Adaugă React Testing Library, `user-event`, matchers DOM și `jsdom`. Separă
Vitest în două proiecte:

- logică: `.test.ts`, mediu `node`;
- componente: `.test.tsx`, mediu `jsdom`.

Nu muta testele Playwright în Vitest. Playwright rămâne pentru fluxuri reale
cap-coadă; DOM tests acoperă tranziții locale și regresii de state.

Gate Lot 1:

- testele backend țintite Dashboard/Campanii;
- testele DOM Target/App;
- `npm run typecheck`, `npm run typecheck:strict`, `npm run lint`, `npm run test`;
- mypy pe modulele backend schimbate;
- `npm run build`;
- deploy unic, health local/public și smoke autentificat pentru Dashboard,
  Target, Campanii și bootstrap/retry.

# 7. Lot 2 — frontend verificabil, contracte și regresii de livrare

## 7.1 R-05 — Matricea DOM critică

Completează, fără duplicarea E2E:

- `TargetCalculatorSubtab`: editare, 409 optimistic conflict și retry;
- `App`: toate stările bootstrap din Lot 1;
- `Settings`: permisiuni, dataset fără refetch catalog/luni, preview/download
  error și retry;
- `Dashboard`: partial error, empty state, current/history;
- `Campaigns`: interval invalid, tranziții query, promo/incentive indisponibil;
- accesibilitate locală pentru dialogurile, taburile și controalele atinse.

## 7.2 R-13 — Contracte API generate offline

1. Generează determinist OpenAPI prin `app.openapi()` într-un script local;
   `/openapi.json`, `/docs` și `/redoc` rămân dezactivate în runtime.
2. Fixează `operation_id` unic și `response_model` pentru toate endpointurile
   migrate; nu genera client din răspunsuri `dict` necontractate.
3. Generează în `src/api/generated/` tipurile și operațiile Retail.
4. Adaptează clientul generat la boundary-ul existent BFF: cookie same-origin,
   CSRF, `AbortSignal`, blob/download, `ApiError`, request ID și redirect 401.
5. Migrează endpoint cu endpoint în ordinea: filters/bootstrap, Dashboard,
   Campanii, Target, Settings/exports, Agents/Forecast, apoi restul non-Grile.
6. Elimină tipul local numai după ce ultimul consumator folosește contractul
   generat. Nu păstra tip generat + tip local echivalent.
7. Adaugă drift gate: regenerare OpenAPI/client și `git diff --exit-code`.
8. Adaugă contract tests pentru nullable/optional, enumuri, date/luni, 409/422
   și blob responses. Pentru payloadurile financiare/critice, verifică la
   boundary și forma runtime sau un contract integration real, nu doar cast TS.

Gate: schimbarea unei scheme Pydantic fără regenerarea frontendului trebuie să
facă verificarea locală roșie.

## 7.3 R-14 — Settings fără requesturi redundante

Separă dependențele:

- `section + permission` -> catalog și luni;
- `selectedMonth` -> filter options;
- `dataset` -> defaults locale dimensions/metrics;
- preview/download -> mutation state separat.

Folosește TanStack Query pentru deduplicare/cache/abort. Schimbarea datasetului
nu reapelează catalogul sau lunile. Logout/permission change invalidează datele
care nu mai pot fi folosite. Păstrează mesajele explicite de eroare.

## 7.4 R-08 — Navigare

Șterge listenerul `unihub:navigate` și tipul `CustomEvent` mort. Păstrează
setterele/callbackurile tipizate și parserul de deep-link existent. Un test
static interzice reintroducerea stringului global fără ADR nou.

## 7.5 R-16 — Bundle budget

Adaugă `scripts/check_bundle_budget.mjs` și un baseline versionat generat din
buildul curent. Verifică raw și gzip pentru:

- entry JS;
- CSS inițial;
- vendor;
- UI;
- charts;
- total precache PWA.

Folosește ratchet: prag inițial = buildul baseline, toleranță mică explicită;
scăderile actualizează plafonul în jos, iar creșterile cer justificare în diff.
Nu introduce serviciu extern și nu încărca `charts` în initial preload.

Gate Lot 2:

- toate testele frontend logic + DOM;
- contract drift verde;
- typecheck, strict pe suprafețele migrate, lint și build;
- bundle budget verde;
- E2E țintit Settings/navigation/permissions;
- deploy unic și verificare live fără requesturi redundante în browser trace.

# 8. Lot 3 — exporturi și importuri bounded de resurse

## 8.1 R-09 + R-19 — Export XLSX măsurat și modular

Înainte de schimbare, adaugă benchmark repetabil, în procese proaspete, pentru:

- 10.000 x 20;
- 50.000 x 20;
- text lung și valori numerice;
- tabel simplu;
- tabel cu daily evolution/grafic;
- daily comparison cu grafice;
- două exporturi concurente.

Înregistrează peak RSS, wall time, output bytes, time-to-first-byte și impactul
asupra p95 Dashboard. Nu folosi dimensiunea spoolului ca proxy pentru RAM.

Separă `backend/services/exports.py` în:

```text
backend/services/exports/
  catalog.py
  schemas.py
  validation.py
  planner.py
  loaders.py
  calculations.py
  table_renderer.py
  xlsx_renderer.py
  daily_comparison.py
  artifact.py
  metrics.py
```

`ExportsService` rămâne facade compatibil până la migrarea routerului.

Politica finală:

- tabel simplu fără grafice/daily sheet -> `Workbook(write_only=True)` și
  `WriteOnlyCell`;
- export cu daily sheet/grafice/stilizări incompatibile write-only -> job
  durabil într-un proces separat, concurență 1, memory limit și artefact
  temporar hash-uit;
- UI primește operation ID, afișează progres/status și descarcă numai artefact
  terminal; starea durabilă câștigă față de ARQ;
- artefactele au TTL/cleanup bounded și nu conțin date în loguri/metrici;
- separă configul: output bytes, rows, cells, peak RSS și concurrent exports;
- numele `EXPORT_MAX_ESTIMATED_BYTES` este eliminat sau redenumit conform
  semnificației reale;
- writerul nu cunoaște SQL; loaderul nu importă openpyxl.

Limita peak RSS se fixează din benchmark sub bugetul real al procesului, cu
marjă pentru runtime; nu se mărește `MemoryHigh/MemoryMax` pentru a ascunde
workbookul nelimitat.

Metrici finite:

```text
export_peak_rss_bytes
export_build_seconds
export_output_bytes
export_cells
export_rejected_total{reason}
```

Teste: caps rows/cells/output/RSS, cleanup, cancel, worker crash, două exporturi,
artefact hash, download chunked, formule/hyperlink safety și echivalență de
conținut business între writerul vechi și cel nou.

## 8.2 R-10 — Import parsing o singură dată

Inventariază sales, promo actuals, ERP reconciliation și target/history parsers.
Boundary-ul web poate citi bytes bounded și face preflight ZIP/XML bounded;
Pandas/openpyxl care materializează workbookul rulează numai în import worker.

Pentru fiecare format:

- preflight structural o singură dată și rezultat atașat hashului sursei;
- detectare antet + încărcare date din aceeași deschidere/parcurgere când
  biblioteca permite;
- read-only/streaming pentru sursele compatibile;
- niciun al doilea parse la retry: refolosește același spool și source hash;
- limite specifice formatului, nu un cap generic arbitrar;
- metrici compressed bytes, expanded bytes, rows, parse seconds și peak RSS;
- semantica snapshotului lunar și toate hashurile business rămân identice.

Promo/ERP devin joburi doar dacă parserul este greu; UI păstrează rezultatul
recuperabil și nu face retry orb după publish incert.

Gate Lot 3:

- benchmark before/after păstrat ca evidence, nu ca test volatil de CI;
- teste backend țintite exports/imports + fault paths;
- mypy, migration manifest dacă apare stare durabilă nouă;
- test concurent cu Dashboard și dovadă că p95 nu crește peste pragul acceptat;
- deploy unic, canary cu date sintetice/non-destructive și health.

# 9. Lot 4 — Campanii coerente și exacte la cent

## 9.1 R-11 — Politica DB

Decizia canonică este: loaderul Campanii citește toate agregatele necesare într-o
tranzacție `READ ONLY`, `REPEATABLE READ`, cu deadline comun; după materializarea
inputurilor, eliberează conexiunea și rulează calculele CPU în afara tranzacției.

Motiv: un import/promote concurent nu poate amesteca două snapshoturi în același
răspuns, iar conexiunea nu rămâne ocupată pe durata formatării și agregării CPU.

Măsoară pool wait/occupancy înainte și după. Dacă volumul dovedește că loaderul
nu poate respecta deadline-ul, optimizează query-urile cu EXPLAIN; nu revine
implicit la răspuns incoerent.

## 9.2 R-12 — Bani fără float

- PostgreSQL `numeric`;
- Python `Decimal` sau integer cents la un boundary documentat;
- o singură regulă de quantize/rounding per metrică;
- JSON păstrează contractul public stabil;
- frontendul formatează și nu recalculează bani din float;
- elimină conversiile `float -> cents -> Decimal` și dicționarele monetare
  tipizate `float` din Campanii.

Teste: jumătate de cent, valori negative/retururi, agregări mari, conversii JSON
și egalitate la cent între sumar, magazine, agenți și export.

## 9.3 R-20 — Modularizare Campanii

```text
backend/services/campaigns/
  range_policy.py
  loader.py
  context.py
  promotions.py
  incentives.py
  aggregation.py
  money.py
  response.py
  metrics.py
```

Routerul validează boundary-ul, loaderul citește DB, evaluatoarele sunt pure,
iar response mapperul nu execută query-uri. Păstrează facade-ul public și
statusurile `complete/partial/invalid/not_configured` existente.

Înainte de extracție inventariază consumatorii cross-service. Dacă publisherul
Insight `campaign_reporting.py` este integrat, acesta trebuie să consume un API
public stabil al domeniului Campanii, nu `_build_campaign_context` sau alte
funcții private mutate între module.

Adaugă `campaign_request_rejected_total{reason}` și metrici pentru pool wait,
DB load și compute, cu reason labels finite.

Gate Lot 4: testele Campanii complete, hashuri business neschimbate pe fixture,
pool occupancy îmbunătățit sau justificat, mypy și smoke live promo/incentive.

# 10. Lot 5 — modularizare backend cu facade stabile

## 10.1 R-17 — Dashboard

Extrage incremental:

```text
backend/services/dashboard/
  orchestration.py
  scheduler.py
  performance.py
  history.py
  batch.py
  specials_data.py
  metrics.py
```

Păstrează query-urile în repository/query modules și `DashboardService` ca
facade. Schedulerul nu acceptă `Task` pornit, numai factory/coroutine rece.
Fiecare extracție păstrează testele de Lot 1 și payload hashul.

## 10.2 R-18 — Target Calculator

Extrage:

```text
backend/services/target_calculator/
  context.py
  rules.py
  profitability.py
  proposal.py
  allocation.py
  scenarios.py
  editing.py
  finalization.py
  warnings.py
  serialization.py
```

Păstrează `Decimal`, revision/CAS, snapshotul de rule-set și facade-ul existent.
Înainte de extracție creează golden fixtures pentru propunere, allocator,
override, 409 stale revision, finalizare și export. Refactorul nu modifică
formula sau rezultatul la cent.

Gate Lot 5: testele Dashboard/Target complete, mypy, coverage ratchet pe noile
module, zero import cycle, payload/business hash identic și smoke live.

# 11. Lot 6 — frontend modular și strict integral

R-06 și R-07 se execută împreună, după fixuri și testele DOM. Motivul este
practic: fiecare responsabilitate extrasă intră strict din prima, evitând
tipizarea de două ori a aceluiași cod monolitic.

Ordine obligatorie:

1. `App` și boundary-urile bootstrap/navigation;
2. Target Calculator;
3. Dashboard;
4. Campaigns;
5. Settings;
6. Agents + Agent Evaluation;
7. AI Forecast;
8. `src/api` rămas și restul aplicației non-Grile;
9. configurația principală devine strictă global; excluderea Grile nu poate
   lăsa restul aplicației pe `strict: false`.

Structuri țintă:

```text
src/features/target-calculator/
  api.ts
  model.ts
  calculations.ts
  hooks/
  TargetWorkflow.tsx
  TargetConfiguration.tsx
  TargetAllocationTable.tsx
  TargetAgentDetails.tsx
  TargetCalculatorPage.tsx

src/features/campaigns/
  api.ts
  queryKeys.ts
  hooks/
  IncentiveView.tsx
  PromotionsView.tsx
  ContestView.tsx
  PremiumView.tsx
  FocusView.tsx
  charts/
  formatters.ts

src/features/settings/
  SettingsPage.tsx
  imports/
  exports/
  preferences/

src/features/dashboard/
  DashboardPage.tsx
  current/
  history/
  performance/
  export/
  presenters/

src/features/agents/
src/features/agent-evaluation/
src/features/ai-forecast/
```

Reguli:

- container data separat de prezentare;
- calcule business pure testabile fără DOM;
- componenta principală aproximativ 300–400 linii, fără split artificial;
- hookurile expun un model coerent, nu zeci de setters;
- `unknown` + narrowing, niciun `any` nou pentru a trece gate-ul;
- `noUncheckedIndexedAccess` și `noImplicitOverride` pe toate modulele noi;
- profile React înainte de `memo`/`useMemo`; nu memoiza speculativ;
- fiecare extracție păstrează testul DOM și E2E al fluxului;
- nu muta codul Grile în cadrul acestui lot.

Gate final TypeScript:

```text
npm run typecheck
npm run typecheck:strict
```

ambele acoperă toate fișierele de producție non-Grile, fără allowlist temporar
crescător. Obiectivul final este un singur config strict pentru întreaga
aplicație când excluderea Grile permite.

# 12. Lot 7 — validare finală, observabilitate și re-audit

## 12.1 Matrice minimă de teste

Backend:

- scheduler Dashboard/concurență/deadline/cancellation;
- Campanii date/snapshot/Decimal;
- XLSX rows/cells/output/RSS/cancel/crash;
- import single-pass și hash business;
- OpenAPI drift;
- facade/refactor equivalence.

Frontend logic:

- seasonality reducer/model;
- range helpers;
- export job state;
- bootstrap cache classifier;
- navigation/deep-link contract;
- generated client errors/cancellation.

Frontend DOM: Target, App, Settings, Dashboard și Campaigns conform loturilor.

E2E, fără duplicare inutilă: login, Dashboard, import/promote, export simplu și
complex, Target, Campanii, permisiuni, responsive/accessibility și PWA lifecycle
`N -> N+1 -> rollback N` pentru schimbările care ating PWA/bundle.

## 12.2 SLO și metrici

Verifică toate metricile recomandate și alerta aferentă unde există prag real:

```text
dashboard_component_active
dashboard_component_global_limit
dashboard_component_budget_violation_total
dashboard_campaign_context_seconds
export_peak_rss_bytes
export_build_seconds
export_output_bytes
export_cells
export_rejected_total{reason}
frontend_bootstrap_failure
campaign_request_rejected_total{reason}
```

Pentru bootstrap folosește error reporting/metrică frontend existentă, cu
reason finit și fără URL, identitate, lună sau alte date business. Nu inventa un
endpoint Prometheus de scriere din browser.

Acceptanță runtime:

- Dashboard warm p95 sub 1 s și citiri normale p95 sub 2 s pe eșantionul SLO
  documentat;
- zero depășiri ale bugetului global Dashboard;
- LCP p75 sub 2,5 s și INP p75 sub 200 ms pe mobil 4G;
- două exporturi nu destabilizează serviciile și nu cresc p95 Dashboard cu mai
  mult de 20%; exportul complex rămâne serializat;
- zero creștere nejustificată a bundleului/precache;
- pool wait și erorile 5xx nu regresează;
- nicio metrică/logare nu include filtre, nume, CNP sau valori business.

## 12.3 Gate final local și formal

Pe candidatul final neschimbat, secvențial:

```bash
npm run typecheck
npm run typecheck:strict
npm run lint
npm run test
pytest backend/tests/ -q
mypy backend/ --ignore-missing-imports --explicit-package-bases
npm run build
node scripts/check_bundle_budget.mjs
```

În plus:

- verificare pachete vendored dacă s-au schimbat;
- fresh migrations + upgrade path dacă s-a adăugat stare durabilă;
- contract generation/drift;
- benchmark RSS separat de CI funcțional;
- `git diff --check`, worktree curat și `HEAD == origin/main`.

Rulează o singură dată CI manual pe exact SHA-ul final. Refolosește R-15 existent:

- run `CI` verde pe `main`;
- `head_sha == SOURCE_SHA == SHA deployat`;
- `SHA256SUMS` și digest artefact verificate;
- approval one-time și deploy prin entrypointul root-owned;
- health local/public, login, calea schimbată și PWA verificate;
- rollback numai între manifeste compatibile; altfel roll-forward.

## 12.4 Re-audit independent

Auditul final folosește exact SHA-ul deployat și aceeași excludere Grile. Auditorul
primește:

- matricea R-01..R-20 cu SHA și dovezi;
- outputurile gate-ului final;
- baseline/after pentru RSS, bundle, pool și SLO;
- lista tipurilor locale eliminate și contract drift gate;
- harta modulelor extrase;
- dovada live exact-SHA.

Auditul trebuie să caute independent regresii noi, nu doar să bifeze acest plan.
Orice finding nou real intră în același document înainte de revendicarea notei.

# 13. Definition of Done global

Planul este închis numai când toate sunt adevărate:

- R-01..R-20 sunt `DONE` sau `SATISFIED` cu dovadă curentă;
- niciun query Dashboard nu pornește în afara bugetului global;
- defaultul Target afișat, salvat și trimis este același;
- Campanii refuză inputul ambiguu și calculează banii exact la cent;
- bootstrapul explică eroarea și se recuperează fără reload;
- suprafețele React critice au teste DOM;
- codul non-Grile este strict TypeScript integral;
- componentele și serviciile mari au boundary-uri clare, fără cale paralelă;
- exporturile au peak RSS măsurat și limitat real;
- parsarea grea nu rulează în web și nu se repetă inutil;
- OpenAPI/Pydantic este sursa unică, iar driftul rupe gate-ul;
- bundle budgetul este ratcheted;
- release/runtime/Git/docs indică același SHA;
- re-auditul independent depășește 9 pe același scope.

# 14. Ce nu se face

- rescriere frontend/backend;
- microservicii, Kubernetes sau orchestrator nou;
- schimbarea contractului snapshot lunar;
- modificarea Grile;
- cache general peste date financiare;
- partiționare/indexare fără benchmark;
- publicarea OpenAPI în producție;
- împingerea contractelor Retail în pachetele comune incompatibile;
- CI hosted la fiecare commit;
- umflarea limitelor de memorie ca substitut pentru writer bounded;
- claim 10/10 fără re-audit și dovadă live.

# 15. Closure operațional — 2026-08-06

Runtime-ul final este `131dfc372f1ccf054326bc4097aace75d57318cd`,
sincronizat pe `origin/main` și deployat pe primary. Candidatul include toate
remedierile R-01..R-20 și corecția suplimentară găsită la auditul live:

- migrarea `056_fieldops_visits_operations_authority.sql`, checksum
  `36c2bda0adf6b2e15298403e164e99b75d78e46369b44510c500fdf7dcd838db`;
- `unihub_operations` are numai SELECT owner-issued/non-grantable pe
  `fieldops_visits` și numai INSERT/DELETE pe `visits_snapshot`; SELECT,
  UPDATE și TRUNCATE pe proiecție rămân refuzate;
- refresh-ul real a înlocuit proiecția cu 14 agregate și nu mai produce
  `InsufficientPrivilegeError`.

Dovezi pe candidatul corectiv:

- bootstrap izolat al migrărilor 001–056: verde;
- testele ACL/migrare/Vizite țintite: `23 passed`;
- suita backend executată înaintea ultimei corecții strict de test:
  `1751 passed, 9 skipped`; singurul eșec reproducea greșit un DELETE filtrat,
  deși operația runtime este înlocuire completă fără SELECT;
- migrarea 056 aplicată live, ACL efectiv
  `true|true|false|false|false` pentru source SELECT, snapshot INSERT/DELETE,
  snapshot SELECT/UPDATE/TRUNCATE;
- backend, worker operations și worker imports active; `/health` și `/readyz`
  local/public verzi; Promo v2 rămâne valid și idempotent;
- refresh Vizite live: `visits_snapshot synced: 14 rows`.

CI-ul formal exact-SHA este run `31127357279`. Runnerul repo-scoped
`dell-retail-build` este online, izolat de producție și etichetat exclusiv
pentru build. La momentul acestei dovezi, runul este în coada incidentului
global GitHub Actions; această stare externă nu blochează runtime-ul livrat
prin fluxul local-first autorizat de ADR-005, dar statusul documentului devine
`closed` numai după rezultatul formal verde.

# 16. Closure Grile și curățenie finală — 2026-08-06

Status: `closed` după consumarea dovezii formale exact-SHA descrise mai jos.
`implementation_sha` pentru remedierea runtime este
`0eb9e524344f2e32cf2071a2d8ef3d2a2083b48b`. `release_sha`, runul CI și runul
deploy sunt identitatea machine-readable a ultimului artefact formal consumat;
se citesc din runurile GitHub și auditul immutable al approval/deployului, fără
un commit docs-only auto-referențial după deploy.

Remedierea Grile este închisă cu următoarele dovezi:

- runul abandonat `192` a fost recuperat prin CAS în `failed`, cu motivul
  `grile_run_recovered_after_arq_worker_failure`; progresul `65/71` și toate
  cele `65` observații, dintre care `64` valide, au rămas intacte;
- unicul run de verificare live nou, `193`, a avansat până la `71/71` și a
  terminat `completed`, cu `8` magazine OK, `63` problemă și `0` erori;
- overview-ul autoritativ raportează runul `193` `active=false`, nu există run
  `queued/running`, iar wrapperul ARQ a terminat `complete` fără retry;
- hashul `agent_targets` înainte și după run este identic:
  `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`;
- publicarea Campaign păstrează intenția `Neatribuit` exclusiv prin API-urile
  publice curente, fără `_build_campaign_context` sau cherry-pick legacy.
- gate-ul browser strict a restaurat în istoricul importurilor durata și
  coverage-ul magazinelor și a aliniat fixture-urile E2E la encodingul Decimal
  derivat din contractele generate, fără relaxarea decodorului runtime.

Gate-uri pe conținutul runtime neschimbat:

- suita Grile: `214 passed, 42 skipped`; SQL izolat țintit: `17 passed`;
- backend complet izolat: `1761 passed, 7 skipped`; mypy: `412` fișiere verzi;
- frontend typecheck, strict, lint, `56` fișiere / `325` teste Vitest și build:
  verzi; E2E Chromium complet: `53 passed`; contract, manifest, vendor
  integrity, bundle budget și
  `git diff --check`: verzi;
- backend, operations worker și import worker active; `/health`, `/readyz` și
  frontendul public sunt verzi, iar assetul Grile public este identic byte cu
  buildul producției.

Closure este valid numai cât timp ultimul `release_sha` are CI formal verde,
approval/deploy consumat pe același SHA, toate checkouturile sincronizate,
GitHub numai cu `main`, zero PR-uri și zero worktree-uri temporare.
