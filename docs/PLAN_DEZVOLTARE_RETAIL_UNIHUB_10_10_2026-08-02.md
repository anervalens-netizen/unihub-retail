---
title: "UniHub Retail development plan toward 10 out of 10"
tags: [unihub-retail, roadmap, performance, refactoring]
status: superseded
created: 2026-08-02
---

> **HISTORICAL / SUPERSEDED — 2026-08-06.** Acest document păstrează contextul
> programului v2.1.0. Singurul plan activ este
> [`PLAN_UNIC_UNIHUB_RETAIL_PESTE_9_2026-08-06.md`](PLAN_UNIC_UNIHUB_RETAIL_PESTE_9_2026-08-06.md).

# Obiectiv

Ridicarea UniHub Retail de la o aplicație internă solidă la un produs foarte
predictibil: date corecte, operații recuperabile, latență măsurată, reguli
business reproductibile și module ușor de schimbat fără regresii.

Planul păstrează React/FastAPI/PostgreSQL/Valkey, importul cumulativ lunar și
strategia local-first. Nu introduce Kubernetes, microservicii, cache general,
partiționare sau CI la fiecare push fără dovadă de nevoie.

# Status implementare 2026-08-03

- `v2.1.0` livrează local P0, P1 și suprafața măsurabilă P2, inclusiv
  migrațiile aditive 032–036 și documentația canonică.
- Finance/TVA rămâne shadow-only; importul salary live rămâne NO-GO până la
  reconcilierea HR. Niciuna dintre aceste mutații nu este implicit autorizată
  de deployul aplicației.
- Gate-ul final P2 rămâne deschis: șapte zile curate, minimum 100 requesturi per
  rută, pragurile p95/3s și LCP/INP production. P3 nu începe înaintea acestei
  dovezi.
- Identitatea release-ului este tagul adnotat `v2.1.0` = CI `head_sha` =
  artifact `SOURCE_SHA` = deploy `source_sha`; runurile și digestul sunt
  evidence operațional, nu text self-referential în commit.

# Principii

1. `Stage -> validate -> promote`; nicio sursă incompletă nu devine adevăr live.
2. Un writer care și-a pierdut lease-ul nu mai poate publica.
3. Operațiile externe se termină `verified`, `rolled_back` sau `uncertain`;
   niciodată „probabil reușit”.
4. Regulile în bani au versiune, effective date și hash salvat în rezultat.
5. Date lipsă nu devin zero și erorile tranzitorii nu șterg ultima stare bună.
6. Optimizarea păstrează hashurile business și pornește din profile live.
7. Refactorizarea urmează boundary-uri de domeniu, nu obiective arbitrare de LOC.

# P0 — adevărul datelor

P0 nu blochează întreaga dezvoltare. Se opresc numai extinderile în aceleași
zone financiare/Google până la trecerea gate-urilor lor.

## Gate 0 — livrare sigură pentru loturile P0

- repară workflowul manual astfel încât runul aprobat să producă artefactul
  imutabil pe SHA-ul exact consumat de deploy;
- păstrează local-first și nu adaugă CI automat la fiecare push;
- validează o singură dată artifact -> deploy -> rollback pe un lot fără
  schimbare business, înaintea primului P0.

## P0.1 Import vânzări: snapshot cumulativ sigur

Decizie: se păstrează înlocuirea completă a lunii curente. Nu se trece la
append/upsert pe rând deoarece sursa nu are ID stabil și poate corecta trecutul.

Schimbări:

- staging separat pentru noua generație;
- manifest cu SHA, cutoff, rânduri, magazine, bonuri, valori, cantități și
  agregate `(site_code, sale_date)`;
- pentru prima generație a lunii: cutoff explicit, control totals și anomaly
  review; lipsa unui magazin fără vânzări nu este singură eroare;
- pentru generațiile următoare: cutoff nu poate regresa, iar un `site-day`
  observat anterior nu poate dispărea fără override explicit și motiv;
- praguri pentru regresii de rânduri/bonuri/valoare/cantitate și raport vizibil
  înainte de promote;
- metadata generațiilor nu se mai șterge; ultima sursă și penultima sursă sunt
  păstrate bounded pentru rollback;
- token de generație + heartbeat + compare-and-set la promote/finalize;
- spoolul se șterge numai după terminal confirmat; retry citește același hash;
- override admin auditabil, fără bypass ascuns.

Acceptanță:

- fixture fără o zi sau un `site-day` existent este refuzat înainte de schimbări;
- fixture complet produce exact hashul business canonic;
- două conexiuni concurente nu pot promova ambele;
- workerul stale nu mai modifică date/status;
- rollbackul la generația anterioară este demonstrat;
- importul nu dezactivează magazine și păstrează multiplicitatea rândurilor.

## P0.2 Grile reset: anulare și recuperare

Schimbări:

- tratare explicită `asyncio.CancelledError`, `SIGTERM` și shutdown în toate
  etapele destructive;
- checkpoint înainte/după fiecare mutație Google;
- stare `uncertain` înainte de orice ieșire neconfirmată;
- rollback/reconcile idempotent din backupurile hash-uite;
- zero retry automat pentru reset live până la reconciliere;
- timeout worker și `TimeoutStopSec` aliniate cu durata măsurată plus marjă;
- runbook de recover, fără a folosi reset real doar ca smoke test.

Acceptanță:

- fault injection după fiecare clear, la timeout, `SIGTERM`, cădere DB și
  cădere Google produce exclusiv `rolled_back` verificat sau `uncertain`;
- niciun retry nu pornește peste checkpoint `uncertain`;
- manifestul DB, backupul și starea Google se reconciliază determinist.

## P0.3 P&L și TVA

Schimbări:

- delete/replace limitat exact la perechile `(company, period)` din batch;
- bucketul `__FINANCE_UNALLOCATED__` înlocuit numai în același scope;
- dry-run compară inventarul DB și blochează regresia de acoperire;
- Decimal până la serializare, rotunjire o singură dată la 0,01;
- registry fiscal effective-dated: 1,19 înainte de 2025-08-01, 1,21 după;
- aceeași funcție fiscală în P&L, estimator, Target și export;
- regenerare controlată a estimărilor afectate, cu diff și control totals;
- scenariile Target finalizate nu se rescriu automat.

Acceptanță:

- importul a trei luni nu modifică celelalte nouă;
- importul unei companii nu modifică alta;
- aceeași valoare brută produce același net în toate modulele;
- estimările afectate sunt regenerate exact, iar actualele Finance rămân intacte;
- totalurile API/Excel/DB coincid la cent.

## P0.4 Identitate salarială

Schimbări:

- CNP validat la 13 cifre și checksum înainte de scriere;
- înaintea oricărui invariant DB, reconciliază cele 8 grupuri cu fișierele
  sursă și stabilește dacă HR permite componente salariale legitime multiple;
- dacă sursa este un total per persoană, unicitate pe
  `(year, month, company_name, person_id)`; dacă sursa are componente, păstrează
  identitatea liniei/componentului și construiește un read model unic agregat;
- conflict de nume/CNP produce raport și zero scrieri;
- reconciliere business pentru cele 8 grupuri duplicate și 10 identități
  structural invalide live; nu se șterge automat nimic;
- importul oficial păstrează replace pe perioada/companiile declarate și
  verifică totalurile înainte/după;
- toate joinurile și contractele folosesc `person_id`.

Acceptanță:

- zero duplicate period-person-company;
- zero identități invalide noi;
- totalurile salariale reconciliate nu se schimbă fără justificare aprobată;
- istoricul și `agent_salary_links` rămân funcționale.

## P0.5 Memoria workerului Grile

Stare confirmată: după patru full-check-uri de la restart, workerul are
aproximativ 1,1 GB RSS / 1,4 GB peak, predominant memorie anonimă; import
workerul are aproximativ 99 MB. Nu se presupune încă dacă retenția este Python,
client Google, thread pool sau allocator nativ.

Schimbări:

- benchmark repetabil de 10 full-check-uri read-only cu același fixture/scope;
- RSS/USS, `tracemalloc`, object-count și thread/client lifecycle diff per run;
- profilează înainte/după GC și după închiderea serviciilor Google;
- remediază cauza, apoi elimină instrumentarea temporară;
- nu ridica `MemoryHigh/MemoryMax` ca substitut pentru fix.

Acceptanță:

- 10 rulări consecutive fără creștere monotonă post-GC;
- pantă post-warmup sub 5 MB/rulare și RSS stabil sub 300 MB;
- durată și rezultate Grile nemodificate semantic;
- canary live read-only confirmă plafonul fără swap suplimentar relevant.

# P1 — state machines și reguli business

## P1.1 Grile observation model

Un singur epic închide H-04..H-10 și M-19:

- full-run și refresh per magazin rulează în coada operațională;
- endpointul web returnează rapid operation ID;
- observațiile sunt immutable; proiecția curentă este separată;
- update monotonic pe generație/`checked_at`, cu fencing pe owner;
- ultima observație reușită rămâne vizibilă; ultima eroare și stale age sunt
  câmpuri separate;
- răspunsul Google validează cardinalitatea, ordinea, range-ul și forma;
- completarea folosește luna verificată, cutoff business și
  `Europe/Bucharest`, nu ziua calendaristică a procesului;
- rolloutul v3 cere inventar și validare structurală, deși registry-ul live
  curent este coerent.

Acceptanță: full-run vechi nu poate suprascrie refresh nou; Google parțial nu
scrie; refresh eșuat păstrează datele bune; o lună fără full-run afișează
refreshurile individuale.

## P1.2 Promo/Incentive/Concurs

- import promo actuals staged și atomic cu configul versionat;
- config all-or-nothing: chei unice, intervale, overlap și cutoff validate;
- cantitățile fracționare/NaN/Inf respinse;
- actuals cumulative folosite numai în fereastra acoperită;
- clasamentul nu mai folosește cheia textuală globală de agent;
- politică explicită pentru transfer: `(site_code, agent)` sau `person_id`
  stabil, ales per tip de concurs;
- masterul Premium este validat/materializat înainte de promote; sursa lipsă
  păstrează generația bună și ridică alertă.

Acceptanță: totalurile promo/incentive se conservă, aceeași unitate nu este
dublată, iar doi agenți omonimi/mutați au rezultat determinist.

## P1.3 Target Calculator și registry de reguli

- allocatorul respinge bugetul infezabil; nu încalcă floor/cap ca fallback;
- override-ul managerial rămâne separat și explicit de propunerea algoritmică;
- TVA, salariu de bază, tichete, comision, număr agenți și excepții pe magazin
  intră într-un rule-set versionat, effective-dated;
- scenariul salvează rule-set ID/hash și snapshotul parametrilor;
- mapările manager/magazin/alias se mută gradual într-un registry business
  validat, nu într-o interfață generică nouă.

Acceptanță: recalcularea aceleiași versiuni este deterministă; schimbarea unei
reguli nu modifică retrospectiv scenariile; cazurile infezabile nu devin
publicabile.

## P1.4 Availability și job lifecycle

- backendul pornește fără coada ARQ operațională; citirile rămân disponibile;
- endpointurile de enqueue răspund 503 explicit când coada lipsește;
- statusurile disting `not_found`, `backend_unavailable`, `unknown`;
- config web/worker/import devine tipizat și validat la startup;
- timeouturile și poolurile au limite/relații validate;
- timezone business și clock injectabil sunt unice.

# P2 — performanță măsurată

Ordinea este bazată pe baseline-ul live, nu pe auditul static.

## P2.1 Hotspot imediat

- scoaterea Google refresh din requestul web; țintă enqueue p95 sub 300 ms;
- instrumentare separată pentru queue wait, provider time, DB time și total job;
- deduplicare persistentă per lună/magazin.

## P2.2 Dashboard și API

- păstrează optimizările recente; nu adaugă cache acum;
- toate componentele intră în același buget global real;
- deadline end-to-end per endpoint, cu timpul rămas propagat către DB;
- scope-ul `site_code` se normalizează o singură dată la boundary API;
- forecast current folosește cutoff per magazin sau declară coverage neuniform;
- profilează din nou numai după o fereastră curată de șapte zile.
- dacă fereastra curată sau RUM arată din nou Promo/Special drept blocaj,
  optimizează/collapse calculele; încărcarea separată după dashboardul core este
  permisă numai dacă UX și hashul business rămân corecte.

Gate-ul se evaluează pe minimum șapte zile curate și minimum 100 de
requesturi per rută.

Ținte:

- Dashboard warm p95 sub 1 s pe 7 zile;
- Promo și Agent Evaluation p95 sub 1 s;
- toate citirile normale p95 sub 2 s;
- zero requesturi peste 3 s în fereastra de acceptanță;
- import/export nu cresc p95 Dashboard cu mai mult de 20%.

## P2.3 PostgreSQL și exporturi

- `pg_stat_statements` lunar: top total time, mean, rows și buffers;
- optimizează doar query-uri user-facing care depășesc bugetul;
- mută raw scans pe agregatele canonice când rezultatul business rămâne identic;
- exportul mare devine plan -> extract -> transform -> writer spooled/streamed;
- benchmark înainte de partiționarea `reporting_item_day/month`;
- nicio indexare fără `EXPLAIN (ANALYZE, BUFFERS)` și A/B.

Trigger de partiționare: volum/timp de mentenanță sau query dovedit, nu simpla
dimensiune de aproximativ 1,5 milioane de rânduri.

## P2.4 Frontend și RUM

- păstrează lazy loading și cache immutable doar pentru chunkuri hash-uite;
- test PWA N -> N+1 și rollback, fără schimbare speculativă de strategie;
- profilează rerenderurile ecranelor grele înainte de memoizare;
- History se mută în agregare backend numai după comparație de hash;
- RUM: LCP p75 sub 2,5 s și INP p75 sub 200 ms pe mobil 4G.

# P3 — refactorizare controlată

## Backend

- `grile_monthly`: domain policy, Google adapter, state machine, artifact store,
  recovery/reconcile;
- `target_calculator`: rule registry, profitability, allocator, workflow,
  export/presentation;
- `exports`: validation/query plan, extractors, aggregators, writers;
- `dashboard_service`: orchestrator subțire peste componente finite;
- un model tipizat de config per proces și un singur business clock.

Fiecare extracție păstrează testele și hashul business înainte de următoarea;
nu se combină refactor structural cu schimbarea formulelor.

## Frontend

- containere de date separate de componentele de prezentare;
- `TargetCalculatorSubtab` și `Campaigns` împărțite pe fluxuri deja testate;
- contracte API generate/tipizate și migrare graduală la TypeScript strict;
- strict începe cu importuri, Management, Grile și permisiuni, apoi restul
  fișierelor de producție.

## Legacy cleanup

- SQLite Vizite mutat în tool offline după expirarea rollbackului;
- `visits_snapshot` refresh mutat din startup într-un job observabil când
  volumul justifică;
- importuri duplicate/comentarii temporare și float-uri financiare eliminate;
- versiune unică pentru package/build/UI/release.

# P4 — livrare și documentație

- local-first rămâne default pentru schimbări mici;
- fluxul manual hosted este reparat să producă artefact la același SHA;
- hosted gate obligatoriu doar pentru P0, migrații, auth și release formal;
- fault-injection și teste concurente devin gate pentru state machines;
- coverage floors urmăresc modulele de risc actuale, nu doar istorice;
- README/AGENTS/arhitectură/runbookuri actualizate după fiecare lot;
- auditul și planul din 15 iulie sunt marcate istorice după adoptarea acestui
  plan.

# Ordine de livrare

1. `manual-artifact-gate` — permite livrarea sigură a loturilor critice.
2. `pnl-vat-scope` și `salary-identity-reconcile` — defecte financiare live.
3. `sales-promotion-gate` și `spool-retry` — protejează ingestul zilnic.
4. `grile-cancel-recovery` + `grile-worker-rss` — mutație și operabilitate.
5. `import-grile-fencing` — închide writerii stale.
6. `grile-observation-model` — performanță web + stare monotonică.
7. `promo-contest-rule-contracts` — payout reproductibil.
8. `availability-deadlines-scope` — degradare controlată și latență bounded.
9. `measured-performance` — profile live și optimizări A/B.
10. `domain-refactors` + docs — module și surse canonice după stabilizare.

# Definition of Done pentru „aproape 10/10”

- zero delete/replace în afara scope-ului declarat;
- zero writer stale capabil să publice;
- fiecare import oficial are manifest, diff, source hash și rollback;
- zero duplicate salariale sau identități structurale invalide necarantinate;
- reguli financiare effective-dated și rezultate exacte la cent;
- operațiile Google sunt queued, recuperabile și observabile;
- target/promo/concurs reproducibile prin rule-set hash;
- Dashboard p95 sub 1 s și citiri normale p95 sub 2 s pe șapte zile;
- fără churn susținut de swap și iowait p95 sub 10%;
- TypeScript strict acoperă producția sau are allowlist temporar descrescător;
- full package tests verzi pentru lotul schimbat, fault tests pentru P0 și un
  singur hosted run la release;
- runtime, Git, docs și artefact indică același SHA.

# Ce nu facem acum

- rescriere frontend/backend;
- microservicii/Kubernetes/orchestrator nou;
- append pe importul lunar;
- cache general peste răspunsuri financiare;
- partiționare fără benchmark;
- security enterprise sau RBAC organizațional extins fără cerință de produs;
- CI hosted la fiecare commit.
