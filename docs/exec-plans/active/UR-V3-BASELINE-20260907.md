---
title: "UniHub Retail V3 — baseline de cod, complexitate și performanță"
status: complete
created: 2026-09-07
repository: anervalens-netizen/unihub-retail
master_tracker: 267
lot_issue: 268
integration_branch: v3/main
working_branch: v3/baseline-code-map
base_commit: cc39a023b63387fbc2f610b0270bc114b0b6591d
production_main_at_start: 1f40c81bd54d67b5cd6ceadb5a619c1a299e5323
runtime_behavior_changed: false
production_changed: false
excluded_internal_scope: Grile
---

# UniHub Retail V3 — baseline de cod, complexitate și performanță

## 1. Verdict executiv

Nu este justificată o rescriere a aplicației.

Structura actuală are deja elementele potrivite pentru V3:

- frontend React/TypeScript împărțit pe funcționalități;
- încărcare lazy a ecranelor principale;
- API client și contracte generate;
- backend FastAPI cu composition root;
- separare declarată router → service → repository;
- PostgreSQL ca sursă autoritativă;
- teste și ratchets de complexitate existente;
- telemetrie, deadline-uri și mecanisme operaționale mature.

Datoria tehnică relevantă pentru V3 este concentrată în patru zone:

1. componentele de afișare a datelor sunt fragmentate și insuficient configurabile;
2. graficele sunt implementate direct în ecrane, cu tipuri, culori și axe fixe;
3. există un număr limitat de hotspoturi backend cu logică densă;
4. baseline-urile de performanță din repository sunt istorice și trebuie revalidate pe candidatul exact V3 înainte de optimizări noi.

Strategia recomandată rămâne:

```text
caracterizare și măsurare
→ simplificare locală
→ DataGrid pilot
→ ChartFrame pilot
→ Hub/Istoric V3
→ configurare business limitată
→ migrare graduală a modulelor
→ re-audit exact-SHA
```

Nu se introduc microservicii, un motor generic de workflow, dashboarduri active pe rol sau un nou strat de guvernanță GitHub.

## 2. Identitatea baseline-ului

| Element | Valoare |
|---|---|
| Producție/main | `1f40c81bd54d67b5cd6ceadb5a619c1a299e5323` |
| Ramură integrare V3 la pornirea lotului | `v3/main@cc39a023b63387fbc2f610b0270bc114b0b6591d` |
| Ramură de lucru | `v3/baseline-code-map` |
| Tree de pornire V3 | `721a31267cc7cb403fbf4cb1f651c3a4ea86600b` |
| Modificări runtime în acest lot | niciuna |
| Modificări producție | niciuna |
| Scope intern Grile | exclus |

Baseline-ul este static, bazat pe codul și documentele versionate. Valorile de producție mai vechi sunt marcate explicit drept istorice.

## 3. Harta arhitecturală actuală

### 3.1 Fluxul frontend comun

```text
src/main.tsx
→ src/App.tsx
→ src/useAppController.ts
→ src/AppAuthenticatedView.tsx
→ src/screenLoaders.ts
→ src/features/<module>/*Page.tsx
→ hook/controller local
→ src/api/<module>.ts sau src/api/generated/client.ts
→ FastAPI
```

Responsabilități observate:

- `useAppController.ts` coordonează autentificarea, deep-linkurile, taburile persistente, tema, lunile disponibile și trei contexte de filtre;
- `AppAuthenticatedView.tsx` alege filtrul activ, compune `MainLayout` și ecranul curent;
- `screenLoaders.ts` păstrează lazy loading pentru Dashboard, Campaigns, Agents, Settings și Management;
- modulele mai noi folosesc frecvent structura `Page → controller/hook → views/model`;
- contractele API sunt generate și centralizate în `src/api/generated/`;
- TanStack Query gestionează server state pe suprafețele moderne;
- P&L este separat prin capability și autorizare server-side.

Evaluare:

- fundația este adecvată;
- nu există motiv pentru un framework frontend nou;
- `useAppController.ts` nu depășește ratchetul TypeScript, dar trebuie evitată adăugarea de noi responsabilități globale;
- personalizarea V3 trebuie să rămână locală modulelor sau într-un model comun mic, nu să transforme controllerul aplicației într-un mega-store.

### 3.2 Module frontend non-Grile

| Modul | Boundary principal | Observație V3 |
|---|---|---|
| Hub/Dashboard | `src/features/dashboard/` | pilotul principal pentru DataGrid și ChartFrame |
| Agents | `src/features/agents/` | numeroase tabele și drill-downuri; al doilea consumator bun |
| Agent Evaluation | `src/features/agent-evaluation/` | tabele dense; migrare după validarea gridului |
| Campaigns | `src/features/campaigns/` | are propriul `SortableTable`; semnal de duplicare reală |
| AI Forecast | `src/features/ai-forecast/` | grafice și tabele mari; necesită chart semantics/freshness |
| Target Calculator | `src/features/target-calculator/` | logică sensibilă; migrare vizuală separată de formule |
| P&L | `src/features/pnl/` | owner-only; contractul de acces rămâne neschimbat |
| Salary | `src/features/salary/` | suprafață sensibilă și volum mare de UI/teste |
| Settings/Imports/Exports | `src/features/settings/` | fluxuri cu efecte; nu sunt pilot de primitive vizuale |
| Visits | `src/features/visits/` | arbore și drawer; poate reutiliza ulterior filtre/componente |

### 3.3 Fluxul backend comun

```text
backend/main.py
→ backend/routers/<module>.py
→ backend/composition.py
→ backend/services/<module>*.py
→ backend/repositories/<module>*.py
→ reporting views / PostgreSQL tables
```

`backend/main.py` este composition/bootstrap runtime și include:

- lifespan;
- inițializarea OIDC, sesiuni, rate limiting și pool DB;
- validarea migrațiilor;
- middleware de securitate, body limits și request context;
- metrici HTTP;
- montarea routerelor;
- servirea SPA.

`backend/composition.py` construiește serviciile și injectează repositories/adapters.

Contractul `backend/architecture_contract.json` declară:

- flow implicit `router -> service -> repository`;
- routerele nu accesează direct baza;
- domeniul nu importă infrastructura;
- orice acces nou la date din service necesită clasificare explicită.

Există încă 55 de excepții istorice în `backend/architecture_direct_db_baseline_v1.json`, grupate în:

- query services;
- transaction scripts;
- orchestration boundaries.

Acestea nu trebuie eliminate mecanic. Se reduc numai când un lot atinge traseul respectiv și rezultatul devine mai simplu, mai testabil și cel puțin la fel de rapid.

### 3.4 Fluxurile sensibile

| Suprafață | Protecția care trebuie păstrată |
|---|---|
| P&L | capability frontend + autorizare server-side; acces owner-only |
| Salary | permisiuni server-side, identități fără expunere CNP în contracte publice |
| Imports | admin-only, worker separat, staging/manifest/CAS/rollback |
| Exports | permisiune dedicată, spool/chunking, audit operațional |
| Target | snapshot, rule-set, hashuri, limite floor/cap, scenarii versionate |
| Auth | OIDC BFF, sesiune server-side, Valkey, CSRF și rate limiting |

V3 nu folosește Saved Views, filtre sau personalizare vizuală pentru a modifica aceste permisiuni.

## 4. Baseline de complexitate

### 4.1 Python

Contractul de complexitate înregistrează 28 de funcții cu proxy de complexitate cel puțin 20. Două sunt în Grile și sunt excluse; rămân 26 non-Grile.

Valoarea maximă non-Grile este 28.

### Hotspoturi prioritare

| Prioritate tehnică | Fișier / simbol | Proxy | Risc | Decizie |
|---:|---|---:|---|---|
| 1 | `backend/services/target_calculator/serialization.py::regional_summary` | 28 | business ridicat | caracterizare înainte de refactor; nu primul lot runtime |
| 2 | upload spreadsheet validation | 27 | securitate/import ridicat | numai cu teste și review AI independent |
| 3 | import incentive script `main` | 26 | operațional | nu este user-path V3 prioritar |
| 4 | import overlap gate `main` | 26 | operațional | păstrat până la nevoie demonstrată |
| 5 | OIDC token verification | 25 | securitate critică | nu se refactorizează cosmetic |
| 6 | HR manager overview | 25 | business/readiness | după clarificarea contractului HR |
| 7 | logging handlers/settings | 22–23 | operațional | lot separat numai dacă simplifică operarea |
| 8 | ERP reconciliation parser | 23 | import/business | după fixture/golden coverage |
| 9 | client IP / CORS / DB authority | 21–22 | securitate | risc mare, beneficiu V3 redus |
| 10 | export/import workers | 20–21 | operațional | doar pe bottleneck demonstrat |

### `regional_summary`

Funcția agregă pe regional:

- număr de magazine;
- floor/proposed/final totals;
- forecastul lunii curente;
- fallback din `history` când detaliile lipsesc;
- sezonalitatea anului anterior;
- perioade base/target;
- trei variații procentuale;
- conversii `Decimal → float`.

Problema este densitatea responsabilităților, nu un defect demonstrat.

Refactorul corect trebuie să înceapă cu teste de caracterizare pentru:

- schema modernă;
- schema legacy;
- lipsa `calculation_details`;
- fallbackuri din `history`;
- zero target/base;
- mai multe magazine din aceeași regiune;
- multiple regiuni și sortare;
- `None`, string JSON și valori Decimal;
- paritatea JSON exactă.

Abia după aceea se poate separa în:

```text
parse row inputs
→ accumulate regional state
→ finalize regional projection
```

### 4.2 Fișiere Python legacy mari

Ratchetul de linii are prag implicit 600 și cinci excepții versionate:

| Fișier | Baseline linii | Relevanță V3 |
|---|---:|---|
| `backend/logging_config.py` | 794 | operațional; nu user-path direct |
| `backend/scripts/import_ai_forecast.py` | 872 | script offline |
| `backend/scripts/run_ai_forecast_backtest.py` | 979 | script offline |
| `backend/scripts/run_ai_forecast_xreg.py` | 1189 | script offline |
| `backend/services/ai_forecast_cohort.py` | 678 | runtime/business; candidat ulterior |

Aceste fișiere nu justifică singure un proiect de refactor. Prioritatea se acordă codului runtime modificat frecvent și traseelor lente.

### 4.3 TypeScript/React

Ratchetul TypeScript are prag de 120 linii per funcție și nu are excepții legacy.

Concluzii:

- nu există un monolit TypeScript unic care să necesite intervenție imediată;
- datoria este distribuită în componente/views mari și repetitive;
- mai multe module au tabele implementate separat;
- graficele sunt implementate local, cu configurare hard-coded;
- o abstracție comună este justificată de consumatori concreți, nu de scorul de complexitate al unei singure funcții.

Fișiere cu volum relevant pentru migrarea V3:

| Fișier | Dimensiune aproximativă | Semnal |
|---|---:|---|
| `src/features/salary/SalaryViews.tsx` | 21,5 KB | view dens; sensibil |
| `src/features/target-calculator/TargetStoreAllocationViews.tsx` | 21,5 KB | view dens; business sensibil |
| `src/features/dashboard/DashboardWidgets.tsx` | 19,8 KB | multe widgeturi/grafice |
| `src/features/dashboard/presenters.ts` | 18,1 KB | transformări multe; bun pentru teste de parity |
| `src/features/ai-forecast/ForecastCurrentTables.tsx` | 17,1 KB | tabele candidate după pilot |
| `src/features/agent-evaluation/AgentEvaluationTables.tsx` | 16,2 KB | tabele candidate după pilot |
| `src/features/dashboard/CurrentDashboardSections.tsx` | 15,7 KB | compoziție vizuală |
| `src/features/pnl/PnlViews.tsx` | 15,5 KB | owner-only, migrare târzie |
| `src/features/campaigns/PremiumView.tsx` | 15,3 KB | tabele/grafice locale |

Dimensiunea nu este tratată automat ca defect. Se folosește împreună cu duplicarea, frecvența schimbării și impactul asupra utilizatorului.

## 5. Baseline pentru tabele

### 5.1 Ce există

`src/features/dashboard/BreakdownTable.tsx` oferă:

- definiție generică și tipizată a coloanelor;
- randare custom pe celulă;
- sortare pe o singură coloană;
- header sticky;
- export;
- layout compact și scroll.

Alte implementări există în:

- `src/features/campaigns/SortableTable.tsx`;
- `src/features/agent-evaluation/*Table*.tsx`;
- `src/features/ai-forecast/*Tables.tsx`;
- `src/features/target-calculator/*Table*.tsx`;
- `src/components/asm/ManagerDesktopTable.tsx`;
- `src/lib/useSortable.ts`;
- `src/components/common/TableHeader.tsx`.

Aceasta demonstrează doi sau mai mulți consumatori și justifică un DataGrid comun, dar nu justifică adoptarea imediată a unui framework foarte greu.

### 5.2 Gap V3

Lipsesc sau sunt inconsistente:

- filtre tipizate pe coloană;
- căutare globală;
- multi-sort;
- vizibilitate/reordonare/redimensionare/pinning;
- stare empty comună;
- totaluri/subtotaluri comune;
- navigare completă din tastatură;
- mod responsive unificat;
- persistarea configurației;
- server-side mode tipizat;
- export exact după filtre locale;
- contract dataset-level.

### 5.3 Decizia de pilot

Primul adaptor va fi `Hub > Istoric`, pe un tabel read-only.

Motive:

- datele sunt deja afișate și testate;
- nu există efecte de scriere;
- sortarea și exportul există deja;
- parity poate fi demonstrată numeric;
- permite testarea filtrelor, configurării coloanelor și responsive fără risc asupra importurilor, salariilor sau P&L.

## 6. Baseline pentru grafice

### 6.1 Ce există

`src/features/dashboard/HistoryDashboardTrend.tsx` conține direct:

- `ComposedChart` pentru vânzări/target/% target;
- `AreaChart` pentru KPI;
- axe și tooltipuri locale;
- culori hard-coded;
- două implementări similare pentru history curent/an selectat;
- selector KPI local.

Grafice separate există și în:

- `DashboardWidgets.tsx`;
- `useDashboardCurrentCharts.ts`;
- `useDashboardMixCharts.ts`;
- `ForecastCharts.tsx`;
- `SalaryAgentBarChart.tsx`;
- `SalaryAreaChart.tsx`;
- `PnlViews.tsx`.

### 6.2 Gap V3

- nu există un contract comun al graficului;
- tipul de grafic nu poate fi schimbat;
- compatibilitatea semantică nu este validată;
- culorile nu sunt centralizate complet în tokens;
- accesibilitatea și fallbackul tabelar nu sunt uniforme;
- freshness/formula/source nu sunt prezentate unitar;
- logica repetată crește costul schimbărilor vizuale.

### 6.3 Decizia de pilot

Primul pilot ChartFrame va fi trendul lunar din `Hub > Istoric`.

V1 a pilotului permite numai tipuri compatibile:

- column/combo;
- line;
- area pentru o singură serie compatibilă;
- tabel.

Nu se schimbă datasetul, formulele, filtrele sau backendul în același lot.

## 7. Baseline de performanță

## 7.1 Ce este deja bun în cod

`vite.config.ts` are deja:

- chunk separat `charts`;
- chunk `ui`;
- chunk `vendor`;
- charts excluse din module preload;
- charts excluse din precache-ul shellului PWA;
- runtime cache pentru assete content-hashed;
- lazy loading la nivel de ecran.

Backendul are:

- metrici HTTP;
- identificarea requesturilor lente peste 3 secunde;
- request deadlines pentru trasee critice;
- pool prewarming;
- observabilitate pe componente;
- `pg_stat_statements` tooling;
- cancellation/cleanup pe fluxurile modernizate.

Aceasta înseamnă că V3 trebuie să optimizeze incremental, nu să înlocuiască toolchainul.

## 7.2 Dovezi istorice disponibile

Aceste valori nu sunt declarate drept măsurători exacte ale branchului V3; sunt repere istorice din producție:

- frontend inițial aproximativ 202 KiB Brotli;
- chunk charts aproximativ 121 KiB Brotli, încărcat lazy;
- Dashboard p50 467 ms / p95 1,27 s într-o fereastră de șapte zile;
- Promo/Incentive p50 519 ms / p95 2,25 s în aceeași perioadă;
- Agent Evaluation v2 a avut perioade lente și apoi optimizări importante;
- optimizarea shared-promo a redus mediana Dashboard cu 25,8% păstrând hashul răspunsului;
- indexul evidence-driven pentru Agent Evaluation a redus mediana service cu 76,7% păstrând hashul canonic;
- o optimizare Promo ulterioară a redus mediana de la 2.781 ms la 312 ms, cu hash business identic.

Lecția demonstrată de repository este corectă:

> Optimizarea se face pe aceeași lună și același scope, cu `EXPLAIN`/timings și hash business identic, nu prin cache/index/refactor speculativ.

## 7.3 Ce nu este încă măsurat pe candidatul V3

- bundle exact la `v3/main`;
- initial JS exact și distribuția chunkurilor;
- LCP/INP/CLS pe branch;
- numărul actual de requesturi pentru fiecare ecran;
- requesturile duplicate actuale;
- time-to-first-row pentru tabelele pilot;
- costul sort/filter pe volume reale;
- payloadurile per modul;
- p95 actual al endpointurilor pe exact aceeași configurație;
- query plans actuale după toate schimbările din august/septembrie;
- peak memory actual pentru import/export.

Orice țintă V3 rămâne provizorie până la colectarea acestor valori.

## 7.4 Setul minim de măsurători înainte de optimizare runtime

```text
frontend build manifest + gzip/brotli sizes
route/chunk ownership
Lighthouse/browser trace pe Hub curent și Istoric
RUM LCP/INP/CLS unde există trafic suficient
request count + transferred bytes per navigation
API p50/p95/p99 per route
component timings Dashboard
pg_stat_statements + EXPLAIN pentru query-urile dominante
memory/runtime pentru import și export mare
business response hash înainte/după
```

Nu este necesară o nouă GitHub Action înainte de a exista o măsurătoare stabilă care merită automatizată.

## 8. Baseline de testare

### Frontend

`vitest.config.ts` impune în prezent:

- statements 65%;
- branches 55%;
- functions 55%;
- lines 67%.

Puncte forte:

- există teste pentru controller/hook/view în modulele principale;
- există teste pentru P&L access/capability;
- există teste pentru API client, filtre, sorting, export, PWA și web vitals;
- există teste critice separate pentru Dashboard, Campaigns, Agents, Salary, Target și Visits.

Politica V3:

- changed-line coverage ridicat pentru cod nou;
- teste de comportament, nu snapshoturi voluminoase;
- golden/parity pentru calcule;
- testarea DataGrid și ChartFrame la nivel de contract;
- creșterea agregatului prin migrarea modulelor, nu prin teste artificiale.

### Backend

Puncte forte:

- suite extinse și runner PostgreSQL izolat;
- golden business contract;
- architecture and direct-DB ratchets;
- complexity ratchets;
- migration manifest/checksums;
- teste pentru auth/import/export/concurrency.

Politica V3:

- orice refactor business începe cu caracterizare;
- nu se modifică formula și structura în același commit;
- pentru auth/import/salary/P&L/Target se cere review AI independent la milestone.

## 9. Baseline de acces și produs

Contractul aprobat pentru V3 este:

- un singur dashboard canonic pentru toți utilizatorii autentificați;
- toate informațiile normale rămân vizibile utilizatorilor care au acces la aplicație;
- P&L rămâne singura suprafață owner-only;
- hooks/capabilities viitoare pot exista intern, dar dashboardurile pe rol rămân inactive;
- Saved Views personalizează numai prezentarea și filtrarea;
- filtrele nu extind autorizarea;
- Grile rămâne exclus intern.

## 10. Matrice minimă de compatibilitate pentru pilotul Hub/Istoric

| Contract | Dovadă necesară |
|---|---|
| Total vânzări | valoare exact identică V2/V3 |
| Target | valoare exact identică |
| % target | aceeași regulă și rotunjire |
| Forecast lună curentă | aceeași identificare și etichetare |
| Trend 13 luni | aceeași ordine, aceleași puncte |
| An selectat | aceleași luni și aggregate |
| KPI Bon2Acc | aceeași serie și unitate |
| KPI Focus | aceeași serie și unitate |
| Total bonuri | aceeași serie și format |
| Filtre firmă/regional/magazin/agent | aceeași semnificație |
| `site_code` | rămâne identitatea dominantă unde contractul o cere |
| Empty/loading/error | niciun rezultat incomplet transformat în zero |
| Sortare | aceeași ordine pentru aceleași date |
| Export | exact rândurile și coloanele vederii filtrate |
| URL/deep-link | nu pierde perioada sau contextul existent |
| Autorizare | neschimbată |
| P&L | neatins |
| Grile | neatins |
| Mobil | conținut complet fără scroll orizontal obligatoriu pentru fluxul de bază |
| Tastatură | filtre, sortare și selector chart operabile |
| Chart table fallback | aceleași date ca graficul |

## 11. Prioritizarea loturilor următoare

Scor intern:

```text
prioritate = impact utilizator + claritate + reutilizare + performanță posibilă
             - risc business - cost - extindere de proces
```

### Lot A — ErrorBoundary accesibil

| Dimensiune | Evaluare |
|---|---|
| Impact | mic, dar cert |
| Risc | foarte mic |
| Cost | foarte mic |
| Schimbare business | nu |
| Motiv | închide o constatare Low și verifică fluxul V3 de implementare/test |

Scope:

- live-region/alert semantics;
- focus management numai dacă testul demonstrează necesitatea;
- test focalizat;
- fără alte schimbări vizuale.

### Lot B — DataGrid core + primul adaptor Hub/Istoric

| Dimensiune | Evaluare |
|---|---|
| Impact | mare |
| Risc | mediu-scăzut |
| Reutilizare | mare, demonstrată de mai multe tabele |
| Schimbare business | nu |
| Motiv | cea mai directă îmbunătățire UX cerută de owner |

Prima versiune:

- column model tipizat;
- sortare;
- filtre text/enum/numeric de bază;
- empty/loading;
- configurare vizibilitate;
- keyboard basics;
- export after-filter;
- fără server-side generic;
- fără virtualizare până când row count justifică.

### Lot C — ChartFrame + trend Hub/Istoric

| Dimensiune | Evaluare |
|---|---|
| Impact | mare |
| Risc | mediu-scăzut |
| Reutilizare | mare |
| Schimbare business | nu |
| Motiv | răspunde direct cerinței de schimbare a tipului de grafic |

Prima versiune:

- contract minimal;
- tipuri allowlisted;
- tokens;
- tooltip/legend comune;
- fallback tabel;
- chart selector;
- aceeași serie de date ca V2.

### Lot D — Target `regional_summary` characterization/refactor

| Dimensiune | Evaluare |
|---|---|
| Impact | mentenabilitate mare |
| Risc | ridicat |
| Schimbare business | nu |
| Review | AI independent necesar |

Acest lot începe după primele primitive vizuale sau când Target devine blocker real. Nu este quick win.

## 12. Zone amânate intenționat

- refactor OIDC doar pentru complexitate;
- refactor import validators fără defect sau nevoie;
- partitionarea tabelelor fără benchmark;
- mutarea tuturor celor 55 de excepții direct-DB;
- înlocuirea Recharts;
- înlocuirea TanStack Query;
- un store global nou;
- un generic query builder;
- un workflow engine;
- role dashboards;
- Action Center;
- integrare generică/webhooks;
- multi-tenancy/microservices;
- containerizarea obligatorie a producției;
- orice schimbare internă Grile.

## 13. Riscurile primei faze

| Risc | Control |
|---|---|
| DataGrid devine framework intern prea mare | prima versiune limitată la nevoile pilotului |
| ChartFrame ascunde prea mult Recharts | wrapper subțire, API concret |
| personalizarea schimbă rezultatul | datele și formulele rămân externe primitivei |
| parity este evaluată vizual | teste pe dataset și export, nu doar screenshot |
| optimizarea mută costul | măsurare end-to-end, request count și bundle |
| Target refactor schimbă fallbackuri | teste de caracterizare înainte de cod |
| V3 derivă de main | forward merge controlat și conflict audit |
| procesul devine mai greu | niciun gate/document/issue fără utilitate activă |

## 14. Decizia finală a lotului

Baseline-ul confirmă următoarea ordine:

1. se închide quick win-ul ErrorBoundary;
2. se măsoară buildul exact al branchului când există runner;
3. se implementează DataGrid minimal pe Hub/Istoric;
4. al doilea tabel confirmă designul comun;
5. se implementează ChartFrame minimal pe trendul lunar;
6. se măsoară bundle/interacțiuni și se ajustează;
7. numai după aceea se extind primitivele la modulele mari;
8. hotspoturile business se refactorizează separat, cu parity și review independent.

Nu a fost identificat niciun motiv tehnic pentru o rescriere și niciun motiv pentru complicarea sistemului de procese.

## 15. Definition of Done — Lot 1

- [x] harta frontend non-Grile este documentată;
- [x] harta backend și boundary-urile sunt documentate;
- [x] hotspoturile sunt legate de fișiere și contracte actuale;
- [x] baseline-ul de complexitate este separat de prioritizarea după impact;
- [x] dovezile istorice de performanță sunt etichetate corect;
- [x] necunoscutele de performanță exact-SHA sunt declarate;
- [x] matricea pilotului Hub/Istoric este definită;
- [x] primele loturi sunt ordonate;
- [x] nu s-a schimbat runtime-ul;
- [x] nu s-a modificat `main` sau producția;
- [x] implementarea internă Grile nu a fost inclusă.
