# Plan tehnic de remediere — UniHub Retail

## 1. Scop și surse de adevăr

Acest document transformă auditul static din 2026-08-04 într-un program de
implementare verificabil. Nu tratează automat toate constatările ca defecte
confirmate. Pentru fiecare lot, codul, schema, granturile, datele și runtime-ul
curent prevalează asupra raportului static.

Baseline:

- repository: `anervalens-netizen/unihub-retail`;
- commit auditat: `398501a48cdd3e154d3848994198393d3f1d5425`;
- branch P0 existent: `fix/p0-data-integrity-20260804`;
- Draft PR existent: `#122`;
- design/UI: exclus;
- contract vânzări: fiecare fișier oficial este snapshotul complet al lunii la
  cutoff și înlocuiește atomic snapshotul anterior;
- validare: local-first pe Dell, PostgreSQL și Valkey izolate, fără folosirea
  producției ca mediu de test;
- deploy: numai după migrare fresh + upgrade, teste complete, review de date,
  backup verificat și gate Git/GitHub.

## 2. Decizii care nu se redeschid în implementare

1. Importul de vânzări rămâne `Stage -> Validate -> Promote`; nu se transformă
   în merge incremental.
2. Multiplicitatea rândurilor de vânzări și salarii se păstrează. Egalitatea
   valorilor business nu este identitate.
3. Autoritatea P&L este `(company_name, period, canonical_site_code)`;
   `__FINANCE_UNALLOCATED__` este cohortă separată.
4. Un worker fără lease valid nu poate valida, promova, finaliza sau atașa
   artefactul oficial.
5. O eroare de sursă nu devine zero și nu înlocuiește ultima generație bună.
6. Nicio schimbare de rol OS/DB, credential, user/group sau firewall nu intră
   accidental într-un lot de aplicație. Aceste mutații au preflight, backup și
   fereastră operațională proprie.
7. Nu se adaugă repository-uri paralele doar pentru a evita modificarea
   implementării canonice. După remediere trebuie să existe o singură cale de
   citire pentru fiecare contract.
8. Nu se face merge sau deploy pe baza unui test care doar reproduce
   implementarea. Fiecare invariant critic are test negativ/fault injection.

## 3. Corecții față de planul concis

Auditul are o inconsistență: verdictul cere M-01, M-02 și M-03 ca P0, dar M-04
și M-05 sunt și ele etichetate P0 în corp. Decizia de execuție este:

- **P0-A, blocant pentru PR #122:** M-01, M-02, M-03;
- **P0-B, blocant înainte de următorul import P&L/istoric relevant:** M-04 și
  M-05, după verificarea consumatorilor și granturilor live;
- **P1:** integritatea artefactului, ledger-ele, CNP boundary, recovery Grile și
  corectarea contractului de regresie față de snapshot;
- **P2:** upload boundaries, containment foto/metrics, scheduler Dashboard,
  exporturi și cohortele istorice;
- **P3:** scalare web, query plans, reproductibilitate, coverage și cleanup.

Constatările despre scope organizațional rămân condiționale până când ownerul
confirmă că există utilizatori care nu trebuie să vadă întreaga rețea. Nu se
inventează un model multi-tenant dacă toți utilizatorii autorizați sunt globali.

## 4. Lot P0-A — corectitudinea datelor (PR #122)

### 4.1 Vânzări: stagingul validat este exact stagingul promovat

Implementare obligatorie:

- manifestul canonic aprobat este legat criptografic de fiecare câmp staged;
- digestul este determinist pentru `NULL`, date, text, booleeni și numere;
- `row_number` și ordinea canonică păstrează multiplicitatea;
- promovarea, inclusiv schimbarea headului, reverifică legătura în aceeași
  tranzacție înainte de mutarea datelor live;
- manifestul, source SHA, cutofful și digestul staged devin imutabile după
  validare, exceptând tranziția finită a `generation_state`;
- lease-ul și CAS-ul headului rămân obligatorii;
- headul curent și predecessorul de rollback nu pot pierde stagingul;
- generațiile vechi, nereținute, pot fi curățate fără blocaje;
- rollbackul clonează o generație reținută, reverifică digestul și publică o
  generație nouă; nu mută headul direct înapoi;
- migrarea de upgrade nu „certifică” orbește staging existent: orice backfill
  este verificat față de manifest/controale sau este raportat explicit.

Review specific pentru implementarea existentă în PR:

- decide dacă `stage_rows_sha256` este o dovadă echivalentă cu reconstruirea
  manifestului; dacă nu, înlocuiește-l cu verificarea manifestului canonic;
- verifică trigger-ele pentru insert/update/delete, cleanup, rollback și ordine
  de lock;
- nu modifica checksumul niciunei migrări vechi;
- inventariază separat `replace_month_snapshot`; nu îl șterge în P0-A dacă
  `import_historical.py` încă depinde de el.

Teste/gates:

- tamper individual pentru agent, bon, item, metadata, dată, cantitate, valori,
  `NULL`, boolean și row order;
- două rânduri vizibil identice rămân două unități;
- lease pierdut și head revision concurent refuză promote;
- fresh DB până la ultima migrare;
- upgrade DB de la 036, cu generație activă și predecessor;
- promote, cleanup și rollback după upgrade;
- checksum manifest și `git diff --check`.

Rollback deployment:

- codul poate reveni numai dacă manifestul de migrări rămâne compatibil;
- o migrare aplicată nu se șterge și nu i se modifică SHA-ul;
- dacă schema nu permite rollback de cod, se folosește roll-forward corectiv.

### 4.2 P&L: autoritate per magazin-lună

Implementare obligatorie:

- normalizează o singură dată `canonical_site_code`;
- selectează `actual` când există pentru cheia magazin-lună și `estimated`
  numai când cheia nu are actual;
- păstrează separat `__FINANCE_UNALLOCATED__`;
- `all_missing_targets()` generează estimări numai pentru magazinele lipsă, nu
  sare întreaga companie-lună;
- `rows`, `annual`, `overview`, `stores` și `regions` păstrează contractele API,
  ordinea și tipurile;
- filtrele `site_code`, `company`, `regional` și legăturile effective-dated nu
  dublează rândurile;
- implementarea rămâne în repository-ul canonic, fără subclass paralel.

Teste/gates:

- aceeași companie/lună cu magazin A actual și B estimated;
- actual + estimated pentru același magazin: câștigă actual, fără dublare;
- Finance nealocat coexistă cu magazine normale;
- mapare site lipsă/ambiguă;
- filtrele individuale și annual total;
- test direct pentru `all_missing_targets()`;
- comparație sintetică înainte/după pe companie, magazin, EBITDA și EBIT.

### 4.3 Salarii: proveniența este identitatea rândului

Implementare obligatorie:

- elimină `DISTINCT` după valori business din toate citirile salariale;
- fiecare rând activ contribuie o singură dată prin identitatea DB/proveniență;
- `agent_count` numără persoane; `record_count` numără componente;
- media se calculează din suma persoană-lună și exclude sub 2.000 RON numai din
  medie, nu din total/istoric;
- history by person și history by retail code au aceeași semantică agregată;
- filtrarea prin `stores` nu multiplică rânduri;
- rapoartele overview, evolution, agents, history, summary și trend folosesc
  aceeași bază canonică;
- se modifică repository-ul canonic și se elimină subclass-ul duplicat.

Teste/gates:

- două source rows distincte, aceeași persoană/lună/magazin/valoare;
- provenance completă și date legacy permise de schema curentă;
- total, record count, agent count, agent-month count și average;
- toate endpointurile/report surfaces;
- aceeași identitate prin person ID și retail code;
- filtre company/site/regional/ASM;
- comparație sintetică înainte/după, unde singurele diferențe acceptate sunt
  componentele anterior eliminate greșit.

### 4.4 Gate de ieșire P0-A

PR #122 rămâne Draft până când sunt adevărate simultan:

- review independent pentru toate cele trei domenii;
- teste țintite verzi pe PostgreSQL/Valkey izolate;
- suita backend completă verde pe candidatul final;
- `mypy`, verificarea manifestului și static checks verzi;
- fresh migration și upgrade 036 -> current verzi;
- rollback vânzări verificat;
- comparațiile P&L și salarii sunt explicate;
- diff fără repository-uri paralele/dead code;
- SHA final și comenzile sunt documentate în PR.

## 5. Lot P0-B — autoritatea importurilor și bypassul legacy

### 5.1 `replace_month_snapshot`

1. Inventar static și runtime: call graph, `pg_proc`, ACL, loguri/scripturi și
   joburi istorice.
2. Înlocuiește `import_historical.py` cu fluxul generațional sau izolează-l ca
   tool offline explicit.
3. Revocă `EXECUTE` pentru rolurile web/worker.
4. Elimină helperul Python și funcția DB prin migrare nouă numai după ce nu mai
   există consumatori.
5. Testează cu rolurile reale că apelul este imposibil.

### 5.2 Revizia P&L autoritativă

- înlocuiește euristica „workbook mai dens” cu revizie/cutoff/manifest explicit;
- vechi complet + nou corectiv trebuie să aleagă revizia declarată;
- dry-run produce manifest și hashuri; apply cere exact manifestul aprobat;
- niciun apply live până când snapshotul ambelor companii este reconciliat.

## 6. Lot P1 — proveniență, privacy și recovery

### 6.1 Vânzări și P&L append-only

- roluri DB distincte pentru read, import writer, operations și migrations;
- promotion ledger și shadow evidence append-only;
- head/pointer mutat numai prin funcție controlată cu CAS;
- digesturile shadow se reverifică la promote;
- matrice de granturi testată cu exact rolurile de producție.

### 6.2 Lifecycle artefact vânzări

- cale unică per job sau content-addressed store cu refcount durabil;
- stare `promoting_artifact`/echivalent;
- generația devine terminală numai după retain + hash + fsync/readback;
- headul, predecessorul și ledgerul țin artefactele în retention;
- reconciler la startup pentru DB/artefact divergente;
- fault injection la move, chmod, disk full și crash.

### 6.3 CNP boundary și salary apply gate

- toate citirile folosesc `person_id`;
- CNP rămâne numai în `salary_private`;
- backfill/reconcile fără CNP în loguri, manifests sau diff;
- aplicarea oficială impune tehnic manifestul pentru ambele companii și
  rezolvarea grupurilor cunoscute, nu doar runbook NO-GO;
- dump/API/log scan fără expunere CNP.

### 6.4 Recovery Grile și boundary Google

- reconciler la startup și periodic pentru `running/uncertain`;
- checkpoint claim/fencing înainte de Google I/O;
- adapter sincron executat în thread/subproces bounded;
- `asyncio.sleep`, timeout, heartbeat și cancellation funcționale;
- crash după primul clear ajunge la rollback verificat sau blocaj explicit cu
  alertă; nu pornește automat o operație nouă.

## 7. Lot P2 — boundaries, istoric și performanță

### 7.1 Uploaduri și suprafețe interne

- preflight ZIP/XML pentru XLSX: membri, path traversal, symlink, uncompressed
  bytes, ratio, workbook/sheet/row/cell limits;
- parsarea grea rulează numai în worker;
- `/metrics` este limitat independent de UI;
- fotografiile folosesc `Path.is_relative_to`, refuză symlinkuri și fișiere
  neregulate;
- joburile Grile costisitoare cer capabilitate dedicată;
- scope organizațional se implementează numai după confirmarea cerinței.

### 7.2 Cohorte istorice

- fiecare raport declară `historical_org` sau `current_org`;
- Grile, HR, P&L și ERP au fixtures pentru magazin închis/mutat/renumit;
- registry Grile refuză compania necunoscută, fără fallback Mobiup;
- snapshoturile manageriale sunt effective-dated.

### 7.3 Dashboard și exporturi

- niciun `Task` DB nu pornește înainte de slotul global;
- istoricul nu încarcă dashboardul lunii curente;
- preview-ul are query limitat și count separat;
- exportul are estimare, row/byte caps și writer write-only;
- exporturile peste prag rulează ca job background;
- fault/load tests măsoară wall time, DB concurrency și peak RSS.

## 8. Lot P3 — scalare, calitate și cleanup

- refreshurile secundare ies din startupul web;
- minimum două procese web se validează pentru sesiuni, rate limit, readiness și
  shutdown; nu se mărește numărul de workeri fără buget DB;
- predicatele lunare folosesc intervale și sunt validate prin
  `EXPLAIN (ANALYZE, BUFFERS)` pe copie izolată;
- forecasturile folosesc calendar business, nu extrapolare calendaristică
  implicită;
- TypeScript strict se extinde incremental pe modulele afectate;
- dependențele Python devin reproductibile cu hashuri și `pip check`;
- coverage-ul crește pe boundaries critice, cu fault injection; mutation tests
  numai unde demonstrează valoare;
- se elimină după inventar SQLite runtime, payloadurile ARQ legacy, docstringurile
  stale, cacheurile nebounded și codul neapelat;
- datele UI folosesc helperul Europe/Bucharest;
- erorile persistate sunt coduri finite/redacted;
- listările Tasks/HR primesc tipuri, limite și paginare.

## 9. Strategie Git, CI și release

- un branch/PR per lot coerent; fără mega-PR;
- commituri tematice, fără force push;
- teste locale înainte de push;
- documentația nu pornește CI;
- GitHub Actions o singură dată pe release candidate sau când auth/migrarea/
  granturile/infrastructura justifică gate-ul;
- release-ul formal folosește artefactul exact al `head_sha`, nu rebuild local;
- înainte de deploy: backup + verify, manifest DB, preflight servicii;
- deploy pe primary, migrare one-shot, restart numai serviciile afectate;
- după deploy: `/livez`, `/readyz`, `/health`, metrics și căile funcționale
  schimbate;
- rollback/recovery testat înainte, nu improvizat după incident;
- GitHub, checkoutul primary, runtime-ul și documentația trebuie să indice
  același SHA la închidere.

## 10. Dovezi obligatorii per lot

Raportul lotului conține:

1. branch și SHA;
2. diff și fișiere;
3. invariants închise;
4. migrare fresh/upgrade și checksum;
5. comenzi și rezultate teste;
6. fault injection și comparații de date;
7. limitări cunoscute;
8. decizie READY/NOT READY;
9. backup/rollback pentru loturile deployate;
10. SHA live și health după deploy.

## 11. Ordine de execuție

1. Închide P0-A în PR #122.
2. Rulează auditul read-only pentru M-04/M-05 și livrează P0-B.
3. Închide lifecycle-ul artefactului și granturile append-only.
4. Închide CNP boundary și gate-ul salarial.
5. Livrează recovery Grile + boundary Google.
6. Livrează upload/containment/capability boundaries.
7. Livrează cohortele istorice.
8. Livrează Dashboard/export performance.
9. Livrează scalarea web, query plans, coverage și cleanup.
10. Rulează gate-ul final de release și verificarea live.

Nu se începe automat lotul următor dacă lotul curent lasă date neexplicate,
migrare neverificată sau rollback incert.

## 12. Evidence P0-A — 2026-08-04

Implementare verificată:

- code SHA: `35014c5390fc9669d91c0dc5df28db6702b01d5a`;
- branch: `fix/p0-data-integrity-20260804`;
- Draft PR: `#122`;
- migration: `037_sales_generation_stage_integrity.sql`;
- migration SHA-256: `739d3da3974a247a3169e5d0bc6af57519bfbed5dff1ddaf28f15339bf207167`.

Verificări locale pe Dell:

- manifest migrations: verified;
- M-03 țintit: `10 passed`;
- P&L + Salarii țintit pe schema finală 037: `62 passed`;
- backend complet: `1491 passed, 9 skipped in 31.87s`;
- mypy: `Success: no issues found in 330 source files`;
- `git diff --check`: pass;
- fresh DB: baseline + migrări până la 037 aplicate de runner;
- upgrade 036 -> 037: mismatch legacy refuzat, backfill valid acceptat, promote
  și rollback clone verificate în test PostgreSQL izolat.

Preflight live read-only, fără migrare sau date modificate:

- primary: `main@398501a48cdd3e154d3848994198393d3f1d5425`;
- backend/worker active; `/livez` și `/readyz` verzi;
- DB live la migrarea 036;
- două generații staged reținute, 7.022 rânduri;
- preflight 037: două snapshoturi verificate, zero mismatch de control;
- salarii: 3.711 -> 3.716 componente și
  12.540.034,14 -> 12.550.322,14 RON; diferența de 10.288 RON provine din cele
  cinci componente eliminate anterior de `DISTINCT`;
- P&L: nicio cohortă mixtă actual/estimated în datele live curente; totalul
  înainte/după rămâne 569.813.991,84 RON. Fixul închide un defect latent.

Limitări și rutare:

- nicio migrare/deploy nu a fost aplicată încă pe primary la momentul acestei
  dovezi;
- `replace_month_snapshot` există și este executabil de `unihub_runtime`, dar
  este încă folosit de `import_historical.py`; remedierea este P0-B separat;
- selecția euristică a reviziei P&L rămâne P0-B;
- PR rămâne Draft până la push, verificarea GitHub și decizia de merge/deploy.

Verdict local P0-A: **READY pentru publicarea candidatului în Draft PR**.

## 13. Închidere P0-A — 2026-08-04

Închiderea de mai jos supersedează numai starea operațională din secțiunea 12;
preflight-ul și valorile sale rămân dovezi istorice nemodificate.

- code SHA P0-A: `35014c5390fc9669d91c0dc5df28db6702b01d5a`;
- merge PR #122: `526c96545694d5051ba80a7782c51c8d341c3138`;
- release source SHA: `668452e286a78ef2de5206d9a6a1edd26f8e86a7`;
- formal CI: run `30940026372`, integral verde;
- release artifact SHA-256:
  `4302f926bbae4e5cd9b147060c0fd3deb5a8c7d34554a75d938c803520c3358e`;
- formal deploy: run `30940326348`, attempt 2, verde;
- migration 037 SHA-256:
  `739d3da3974a247a3169e5d0bc6af57519bfbed5dff1ddaf28f15339bf207167`.

Prima execuție CI (`30939220001`) a expus două porți preexistente, remediate
în release source SHA: checksum-ul 037 lipsea din baseline-ul detect-secrets,
iar empty-state-ul analizei agenților lipsea pe mobil în modul legacy. După
remediere: scannerul exact CI, typecheck și toate cele 51 teste Playwright au
trecut local; runul formal a trecut backend, frontend și runner isolation.

Dovezi live după deploy:

- primary pe release source SHA, checkout curat și aliniat cu `origin/main` la
  momentul deployului;
- backend, worker și import worker active; migrarea one-shot `Result=success`;
- `/livez` și `/readyz` verzi local și public;
- migrarea 037 înregistrată cu checksum-ul din manifest;
- ambele snapshoturi staged reținute și head-ul activ își recompută exact
  digestul stocat;
- `unihub_runtime` nu are `UPDATE` pe `sales_import_stage_rows`;
- jurnalul serviciilor nu conține warning/error post-deploy.

Verdict P0-A: **CLOSED și verificat live**. M-04 și M-05 rămân P0-B, fără
extinderea retroactivă a acestui lot.

## 14. Plan de execuție rămas — baseline 2026-08-04

Această secțiune este backlogul executabil după P0-A. Ordinea este impusă de
dependențele de date și recovery, nu doar de severitatea etichetată în audit.
Fiecare lot are maximum doi writeri în paralel, ownership de fișiere disjunct,
integrare unică și QA independent pe SHA-ul integrat. Sol păstrează ownership
pentru contract, manifestul de migrări, integrare, release și verificarea live;
Terra xhigh execută state machines/schema cu risc mare, iar Luna xhigh execută
inventare, schimbări izolate, teste negative și QA.

### 14.1 Stare și ordine

| Lot | Constatări | Stare | Dependență / gate de ieșire |
| --- | --- | --- | --- |
| P0-B | M-04, M-05 | `CLOSED LIVE 2026-08-04` | bypass legacy absent; P&L numai prin generație explicită; fresh + upgrade DB; fără apply live |
| P1-A | M-06, M-07, R-01, R-02 | `READY` | ledger/staging append-only și matrice reală de roluri |
| P1-B | M-08, M-09 | `BLOCKED BY P1-A` | retain verificat înainte de terminal; reconciler/fault injection |
| P1-C | M-10, R-03 | `READY AFTER P1-A` | CNP eliminat din runtime; apply salarial fail-closed |
| P1-D | M-11, M-12 | `READY AFTER P1-A` | recovery Grile determinist; Google I/O nu blochează event loop |
| P2-A | M-13, R-06, R-17, R-19, R-20 | `BACKLOG` | preflight/decompression/streaming/containment/capability |
| P2-B | M-16, R-04, R-05, R-10 | `BACKLOG` | cohortă și structură istorică explicită |
| P2-C | M-14, M-15, R-07, R-08, R-09, R-11, R-12 | `BACKLOG` | caps, scheduler global, startup și load evidence |
| P3 | M-17–M-19, R-13–R-18, N-01–N-09 | `BACKLOG` | hardening/scalare/calitate/cleanup cu inventar separat |

Note de rutare:

- M-12 este executat cu recovery Grile, deși auditul îl etichetează P2;
- R-02 intră în P1-A deoarece rolul Finance dedicat depinde de matricea DB;
- R-09 nu înseamnă automat mai mulți workeri; întâi se demonstrează bugetul DB,
  rate-limit shared și shutdown corect;
- M-17 se implementează numai după confirmarea modelului de scope business;
- constatările minore intră în lotul care atinge componenta; restul rămân P3.

### 14.2 P0-B — contract înghețat după auditul static și live

#### M-04: eliminarea bypassului vânzări

Baseline verificat pe primary:

- `public.replace_month_snapshot(text)` există, owner `unihub`;
- `PUBLIC` și `unihub_runtime` au `EXECUTE`;
- `pg_stat_statements` arată cinci apeluri normalizate de la resetarea statisticii
  din 2026-07-28; nu există timestamp per apel și nu se presupune recența;
- singurul consumator checked-in este `backend/scripts/import_historical.py`;
- nu există unitate systemd/timer sau call-site web/worker checked-in;
- toate cele 16 luni istorice 2023-09..2024-12 sunt deja `completed`.

Implementare:

1. `import_historical.py` devine validator offline, fără conexiune DB, output
   convertit sau mod de promovare. Exporturile legacy nu exprimă `is_cartela`;
   un converter viitor cere contract separat, apoi Stage -> Validate -> Promote.
2. Se elimină helperul Python și testele care legitimează apelul legacy.
3. Migrarea 038 revocă `EXECUTE` de la `PUBLIC`/runtime și elimină funcția.
   Baseline-ul și migrațiile istorice rămân nemodificate.
4. Fresh DB și upgrade 037 -> 038 verifică absența funcției și zero mutații la
   un apel refuzat. Riscul mai larg de DML runtime rămâne P1-A, nu este ascuns.

Rollback: roll-forward; codul vechi nu se reactivează. O nevoie legitimă de
reimport istoric produce generație nouă prin fluxul canonic și nu recreează
funcția.

#### M-05: autoritate Finance explicită și legată de bytes

Euristica `populated_months` / `numeric_cells` / cale și `--apply` liber se
elimină. Contractul are două artefacte:

1. `authority manifest`, furnizat/aprobat extern, cu exact un bundle declarat
   per `(company, period)`, `revision_id`, `parent_revision_id`, cutoff,
   SHA-256 sursă, snapshot complet, coverage și control totals;
2. `generation manifest`, produs la staging, care leagă authority hash,
   source hashes, scope-uri, hashul canonic al rândurilor, preimage-ul live și
   revision/head așteptat. Rândurile candidate sunt persistate immutable.

Interfața devine:

- `--stage --authority-manifest FILE`: acceptă numai sursele declarate; detail
  și consolidat trebuie să provină din același bundle;
- `--apply-generation UUID --expected-manifest-sha SHA`: citește numai
  stagingul, ia lockuri per scope în ordine stabilă și face CAS pe head,
  parent revision și preimage;
- apply cere ambele companii reconciliate și rol Finance dedicat; în P0-B este
  implementat și testat, dar rămâne operațional **NO-GO**;
- promovarea înlocuiește numai `actual`; rândurile `estimated` nu sunt șterse;
- orice mismatch lasă headul și datele live nemodificate.

Migrarea 039 adaugă generații, scope-uri, stage rows, head-uri și ledger. Primul
staging peste date legacy captează un baseline/preimage și refuză apply dacă
acesta se schimbă. Rollbackul este o generație inversă nouă cu CAS; nu mută
pointerul înapoi și nu atinge estimările.

Teste blocante:

- vechi complet + corecție nouă: numai revizia declarată este eligibilă;
- source rename/modificare, workbook nedeclarat sau detail/summary mix: refuz;
- aceeași cheie cu altă valoare este detectată prin hash, nu prin coverage;
- lipsă companie, snapshot parțial, head/preimage stale: refuz;
- două promovări concurente: exact una câștigă;
- fault după delete/control mismatch: rollback tranzacțional, head neschimbat;
- estimările magazinelor neacoperite rămân bit-identice;
- rollback inverse generation are predecessor și CAS verificat.

### 14.3 Ownership P0-B și porți de integrare

| Lane | Model | Ownership | Interdicții |
| --- | --- | --- | --- |
| M-04 | Luna xhigh | script istoric, helper, migrarea 038, teste dedicate | fără manifest/docs/commit/deploy |
| M-05 | Terra xhigh | service/state machine P&L, CLI, migrarea 039, teste dedicate | fără manifest/docs/commit/deploy |
| integrare | Sol | contract, migration manifest, docs, conflicte, gate complet | un singur candidate SHA |
| QA | Luna xhigh + Terra xhigh | review read-only pe SHA integrat și scenarii negative | fără fix direct pe candidatul QA |

Ordinea porților:

1. teste țintite per lane și `git diff --check`;
2. manifest checksum și validare migrations;
3. upgrade 037 -> 039 și fresh DB cu rolurile reale;
4. testele P&L/sales/import, apoi backend complet o singură dată;
5. typecheck/lint/build numai dacă diff-ul le activează;
6. QA independent pe SHA integrat; orice fix produce SHA nou și re-aduce QA;
7. backup verificat, formal CI pe `main`, artefactul exact al runului, migrare
   one-shot, restart backend/worker numai dacă e necesar;
8. live: funcția absentă, ACL confirmat, schema 039, business hashes sales/P&L
   neschimbate și health verde. Nu se execută apply Finance sau reimport sales.

### 14.4 Loturile următoare — descompunere executabilă

#### P1-A — DB authority și append-only

- contract de roluri: web-read/business-write/import-finance/operations/migrate;
- privileges explicite, fără grants globale pe viitor; upgrade compatibil;
- promotion ledger, staged rows și shadow evidence protejate DB-side;
- head mutations numai prin API SQL controlat/CAS;
- politica sales `authoritative_replace` separă anomaliile informative de
  contradicțiile structurale blocante;
- test de matrice autentificat cu fiecare rol live-equivalent.

#### P1-B — lifecycle artefact sales

- path unic/content-addressed și ownership durabil;
- retain + hash + fsync/readback preced terminalul DB;
- stare intermediară și reconciler idempotent;
- retention calculat din head/predecessor/ledger;
- fault injection move/chmod/disk-full/crash și recovery demonstrat.

#### P1-C — salary privacy și approval

- citirile runtime numai prin `person_id`; CNP numai în `salary_private`;
- backfill/reconcile fără CNP în output sau manifest;
- artifact de aprobare legat de exact manifest/perioade/ambele companii;
- gate tehnic pentru cele opt grupuri cunoscute și review independent;
- dump/API/log scan negativ înainte de orice decizie de live apply.

#### P1-D — Grile recovery și Google isolation

- checkpoint fenced înainte de orice Google I/O;
- adapter sincron în thread/subproces bounded, backoff async și cancellation;
- reconciler startup + periodic pentru `running`/`uncertain`;
- crash după primul clear ajunge la rollback verificat sau recovery-required cu
  alertă; niciun retry automat peste stare incertă.

#### P2 și P3

P2 se livrează în trei candidate separate: boundaries/upload/streaming,
cohorte istorice, apoi Dashboard/export/startup/load. P3 începe cu inventare
read-only pentru scope organizațional, roluri OS/DB, query plans, dependencies,
strict TS și cleanup; fiecare remediere primește gate proporțional și nu se
comasează într-un mega-release.

### 14.5 Condiție de continuare

După fiecare lot se actualizează această secțiune cu SHA, checksumuri, comenzi,
business hashes, rollback și verdict. Următorul lot poate începe numai dacă
candidatul curent este curat, sincronizat, verificat live și fără date
neexplicate. Pentru P0-B, READY înseamnă cod/schema deployate și căile legacy
închise; nu autorizează o promovare Finance live.

## 15. Închidere P0-B — 2026-08-04

Identitate release:

- source/deploy SHA: `5fba9d899f78b4160c39e50212071bf1b505619d`;
- formal CI: run `30946990852`, integral verde;
- artifact SHA-256:
  `d9ed25e65240f75ed17ad31d8311c7c2fa328abf4176b7bae9a9e276f0eb7550`;
- formal deploy: run `30947430898`, verde;
- backup/rollback handle verificat:
  `/opt/Mobiup/ops/backups/retail-deploy/20260804T202108Z-9fc292819596-to-5fba9d899f78-6170dd2fbf405703`;
- migrarea 038 SHA-256:
  `bac85ae88b6118e877e73ad444ed3895051a432069b460d802dc2b1144735488`;
- migrarea 039 SHA-256:
  `4d9f3224195bc63b09be6a4642fb585f5a8b8f3c370c76ca799f0f8620f55b9d`.

Gate-uri și QA:

- PostgreSQL fresh și upgrade 037 -> 039 cu granturi runtime/default sequence
  preexistente: pass;
- backend integrat: 1.507 pass, 7 skip; mypy 334 fișiere, Bandit,
  detect-secrets și manifest immutable: pass;
- Terra xhigh și Luna xhigh: GO independent pe SHA exact, zero findinguri
  P0/P1/P2 deschise;
- două candidate intermediare au fost refuzate înainte de publicare: Terra a
  găsit lipsa revoke-ului direct pe secvențe în 039, iar Luna a găsit failure-ul
  detect-secrets din testul ACL. Ambele au primit regresii și QA repetat.

Dovezi live după deploy:

- primary `main` la source SHA, checkout curat; backend, worker și import worker
  active; migrarea one-shot `Result=success`;
- funcția `replace_month_snapshot(text)` este absentă;
- `unihub_runtime` păstrează numai `SELECT` pe `store_pnl_monthly`, fără write,
  acces la tabelele de generații sau privilegii pe cele două secvențe;
- rolul `unihub_finance_import` nu a fost creat și toate tabelele generaționale
  au zero rânduri: deployul nu a făcut stage/apply/rollback Finance;
- P&L neschimbat: 97.687 rânduri, două companii, 2017-01..2026-06,
  total 569.813.991,84 RON, fingerprint
  `d0506e8af8fb1730786132fb7979d870`;
- sales neschimbat: un head, fingerprint
  `f2bd5d1bea45a22911b4dba684fc8a78`;
- health local/public verde, rutele administrative publice rămân 404 și
  jurnalul serviciilor are zero warning/error în fereastra de deploy.

Verdict P0-B: **CLOSED și verificat live**. M-04 și M-05 sunt închise; P1-A
este următorul lot executabil. Promovarea Finance live rămâne **NO-GO** și cere
rol/credential separat, authority manifest real, reconciliere, backup și
aprobare operațională distinctă.

## 16. P1-A — DB authority și append-only

### 16.1 Candidat tehnic pregătit

Implementarea M-06, M-07, R-01 și R-02 pornește din `83194c653b784dce62123e7f6f655a8c94d3315f`.
Lanțul integrat până la contractele finale este `2b944de`; SHA-ul candidatului
formal și dovezile live se completează în 16.5 după gate/QA/deploy.

Migrații immutable:

- 040 `b8e3103c4013f1d0707effa53f8ebeb897734c995acff1c00d77e36a34841b14`;
- 041 `02ec466328f5a997902612e0924fecea53bbad6284af6d2a87d8caec95189582`.

Contractul rezultat:

- grupuri NOLOGIN separate pentru web-read, business-write, sales import,
  Finance import, operations și migrate; grants numai pe obiecte enumerate;
- patru LOGIN-uri de proces verificate la conectare, fără cross-membership,
  superuser, create role/database/schema ori bypass RLS;
- ownerul obiectelor este NOLOGIN `unihub_schema_owner`; runnerul NOINHERIT îl
  activează numai tranzacțional cu `SET LOCAL ROLE`;
- stagingul sales, promotion ledgerul și evidence-ul shadow sunt append-only;
  headurile/pointerii/ledgerul Finance se mută numai prin funcții SQL controlate
  cu fencing, digest rehash și CAS;
- `authoritative_replace` păstrează reducerile față de snapshotul precedent ca
  informație și blochează numai contradicții interne ale candidatului;
- Finance are grupul de autoritate pregătit în schemă, dar niciun LOGIN,
  credential sau stage/apply live.

### 16.2 Dovezi pre-deploy

- matrice autentificată PostgreSQL, provisioner și negative ACL:
  `31 passed`;
- sales generation/staging, master-data safety și P&L generation/shadow:
  `24 passed`;
- manifestul 001–041 și checksumurile 040/041: verificate;
- fixture-ul master-data raportează coverage global relativ la baseline, fără
  a presupune o bază izolată goală;
- datele production au fost doar citite la baseline: un sales head, două
  promotions, 7.022 staged rows, zero generații Finance, zero generații shadow
  și shadow pointer revision 0.

### 16.3 Cutover autorizat și frontiera restrictivă

Ordinea obligatorie este:

1. oprește workerii, rulează backupul verificat și salvează business hashes;
2. aplică 040/041 o singură dată prin identitatea administrativă existentă;
3. creează cele patru LOGIN-uri de serviciu în boundary-ul operațional separat;
4. atașează contractele exacte cu provisionerul și scrie separat `.env`,
   `.env.worker`, `.env.import-worker`, `.env.migrations`, fără afișarea DSN;
5. instalează unitățile, `daemon-reload`, apoi deployează artefactul formal;
6. verifică principal/flags/membership, ACL negative, migrations, servicii,
   health local/public, head/digest/fingerprints și absența mutațiilor Finance.

Pasul 3–4 modifică identități/credentiale și este singura confirmare umană
necesară. Nu se creează `unihub_finance_import` LOGIN și nu se rulează nicio
operație Finance live.

### 16.4 Rollback și limite

Înainte ca migration service să pornească, rollbackul folosește handle-ul normal
de backup. După aplicarea 040/041, manifestul vechi este incompatibil și
rollbackul de cod este refuzat deliberat; deployul păstrează candidatul și
handle-ul în `recovery_required`, apoi execută roll-forward pe același SHA sau
pe un candidat corectiv aprobat. Migrațiile nu se editează și nu se dau jos.

Rollbackurile business sunt inverse generations/CAS: sales clonează generația
reținută, Finance ar crea o generație inversă numai într-un lot viitor aprobat,
iar shadow mută doar pointerul de review după rehash. Stagingul, ledgers și
pre-image-ul nu se șterg. P1-A nu rezolvă lifecycle-ul artefactului sales
(P1-B), privacy/approval salary (P1-C) sau recovery Google/Grile (P1-D).

### 16.5 Închidere live

**PENDING** până la un singur gate CI-shaped, GO Terra + Luna pe același SHA,
CI formal pe `main`, boundary-ul de identități, deploy, verificarea live și
cleanup. P1-B nu începe înainte de verdictul `CLOSED LIVE` aici.
