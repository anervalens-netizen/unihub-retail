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

## 14. Plan de execuție rămas — actualizat 2026-08-05

Această secțiune este backlogul executabil după închiderea P1-A. Ordinea este impusă de
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
| P1-A | M-06, M-07, R-01, R-02 | `CLOSED LIVE 2026-08-05` | dovezi complete în 16.5 |
| P1-B | M-08, M-09 | `CANDIDATE 7cb8375` | retain/hash/fsync/readback, stare intermediară, reconciler, retenție și fault injection |
| P1-C | M-10, R-03 | `CANDIDATE 7cb8375` | boundary privat, manifest aprobat exact, 8/8/0 și review independent; apply live blocat |
| P1-D | M-11, M-12 | `CANDIDATE 7cb8375` | checkpoint/lease/epoch fenced, adapter thread-affine și reconciler determinist |
| P2-A | M-13, R-06, R-17, R-19, R-20 | `CANDIDATE 7cb8375` | preflight/decompression/cell budgets, containment foto și capability existente verificate |
| P2-B | M-16, R-04, R-05, R-10 | `CANDIDATE 7cb8375` | scope istoric explicit, mapare companie fail-closed și cohorte verificate |
| P2-C | M-14, M-15, R-07, R-08, R-09, R-11, R-12 | `CANDIDATE 7cb8375` | export caps/spool, startup bounded, 2 workeri web și query-plan evidence |
| P3 | M-17–M-19, R-13–R-18, N-01–N-09 | `CANDIDATE 7cb8375` | lock cu hashuri, strict TS, timezone, forecast business, payload cleanup și paging bounded |

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

P2 păstrează trei domenii de verificare: boundaries/upload/streaming, cohorte
istorice și Dashboard/export/startup/load. Ele pot intra într-un singur candidat
consolidat dacă ownershipul fișierelor este disjunct și porțile țintite rămân
clare; nu se forțează trei release-uri. P3 începe read-only, în paralel, cu
inventare pentru scope organizațional, roluri OS/DB, query plans, dependencies,
strict TS și cleanup. Remedierile se integrează în următorul candidat util, cu
gate proporțional, fără câte un release sau handoff per finding.

### 14.5 Condiție de continuare

După fiecare lot se actualizează această secțiune cu SHA, checksumuri, comenzi,
business hashes, rollback și verdict. Următorul lot poate începe numai dacă
candidatul curent este curat, sincronizat, verificat live și fără date
neexplicate. Pentru P0-B, READY înseamnă cod/schema deployate și căile legacy
închise; nu autorizează o promovare Finance live.

### 14.6 Mod accelerat pentru închiderea completă P1-B -> P3

Tot backlogul rămas se execută într-un singur goal persistent. P1-B, P1-C,
P1-D, P2-A/B/C și P3 sunt faze interne și checkpointuri de integrare, nu
goal-uri sau handoff-uri separate. Agentul continuă autonom până când P3 este
`CLOSED LIVE`, cu excepția unei limite restrictive reale din `AGENTS.md`.

Reguli de eficiență fără reducerea calității:

- Luna xhigh este executorul implicit pentru inventare/call graph, fixtures,
  implementări mecanice bine delimitate, teste negative, verificări statice și
  documentație. Scrie numai în worktree izolat, cu interdicție explicită pentru
  `.env*`, credentials, keys, secrets, CNP și date production;
- Terra xhigh se folosește numai pentru schema/state-machine/concurrency/ACL cu
  risc mare și pentru review arhitectural sau audit exact-SHA unde independența
  chiar aduce valoare. Nu dubla mecanic munca Luna;
- Sol/root păstrează contractul, ordinea migrărilor, maximum doi writeri cu
  fișiere disjuncte, integrarea, Git, release, deploy, live evidence și cleanup;
- se combină schimbările compatibile în cât mai puțini candidați integrați.
  Fiecare lane rulează o singură poartă țintită; full gate și CI formal se
  rulează numai pe candidați consolidați care urmează să fie deployați;
- dovezile exacte încă valide se reutilizează. Nu se repetă build/test/CI pe
  conținut neschimbat, docs-only nu pornește CI și nu se creează PR-uri sau
  release-uri ceremoniale;
- inventarele P2/P3 pot rula read-only în paralel cu implementarea P1, dar
  mutațiile păstrează ordinea dependențelor. Findingurile intră direct în
  candidatul următor, fără oprire între faze;
- QA final pe același SHA este Luna xhigh + Terra xhigh. Orice finding care
  schimbă sursa produce SHA nou și repetă numai porțile invalidate;
- Finance și salary live apply, credentiale/identități noi și operații
  ireversibile rămân în afara autonomiei implicite și cer exact confirmarea
  prevăzută de `AGENTS.md`. Implementarea, testele și deployul gardurilor nu se
  opresc din acest motiv.

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
Lanțul integrat până la contractele inițiale este `2b944de`; candidatul formal
corectat, auditat și deployat este
`4cc3d322e0c0559615c642568fe914af29370b8e`.

Migrații immutable:

- 040 `59a15b051d73fdbbce2ce8d465b6d7a9f41ffdc7abe45744e1de6ae1db69bce9`;
- 041 `a14a3d170fce29ca9326144e358ce6ead054999cbb31599b3bde092924f00311`;
- 042 `6e120625c69ff8528bec5074782e822ba8b7c8828ed1dbb71dc1c97919013cb4`.

Contractul rezultat:

- grupuri NOLOGIN separate pentru web-read, business-write, sales import,
  Finance import, operations și migrate; grants numai pe obiecte enumerate;
- patru LOGIN-uri de proces verificate la conectare, cu set exact de membershipuri
  directe/tranzitive și opțiuni, fără granturi directe, default ACL, obiecte
  deținute, superuser, replication, create role/database/schema ori bypass RLS;
  detectorul folosește dependențele ACL/owner canonice `pg_shdepend`, inclusiv
  language, large object, tablespace, FDW/server și parameter ACL; autoritatea
  lipsă sau suplimentară este fatală în production;
- ownerul obiectelor este NOLOGIN `unihub_schema_owner`; runnerul NOINHERIT îl
  activează numai tranzacțional cu `SET LOCAL ROLE`;
- stagingul sales, promotion ledgerul și evidence-ul shadow sunt append-only;
  generațiile shadow trebuie să pornească `staged` și ne-sealed;
  headurile/pointerii/ledgerul Finance se mută numai prin funcții SQL controlate
  cu fencing, digest rehash și CAS; seal-ul Finance recompută în DB row hash,
  coverage, count, total și pre-image, iar sales CAS reverifică starea validată,
  digestul, control totals și absența contradicțiilor blocking; Finance nu are
  DML direct pe actuale sau stare, iar promovarea atomică DB-side face replace,
  head CAS, ledger și complete pentru toate scope-urile ambelor companii;
- `authoritative_replace` păstrează reducerile față de snapshotul precedent ca
  informație și blochează numai contradicții interne ale candidatului;
- 041 nu preia obiecte deținute de un owner extern; în producție,
  `fieldops_visits` era deținut de principalul administrativ al schemei și a
  trecut controlat la `unihub_schema_owner`. Webul primește numai SELECT
  owner-issued, non-grantable prin `unihub_web_read`; 042 refuză orice
  privilegiu prin `unihub_business_write`, LOGIN-ul web direct, PUBLIC,
  ACL-uri columnare sau membershipuri moștenite;
- Finance are grupul și contractul viitorului principal
  `unihub_finance_import_worker` pregătite, dar niciun LOGIN, credential sau
  stage/apply live; numai sales-import primește `TEMPORARY`.

### 16.2 Dovezi pre-deploy

- matrice autentificată PostgreSQL, provisioner și negative ACL:
  `31 passed`;
- sales generation/staging, master-data safety și P&L generation/shadow:
  `24 passed`;
- manifestul 001–042 și checksumurile 040/041/042: verificate;
- fixture-ul master-data raportează coverage global relativ la baseline, fără
  a presupune o bază izolată goală;
- datele production au fost doar citite la baseline: un sales head, două
  promotions, 7.022 staged rows, zero generații Finance, zero generații shadow
  și shadow pointer revision 0.

### 16.3 Cutover autorizat și frontiera restrictivă

Ordinea obligatorie este:

1. oprește backendul și ambii workeri, rulează backupul verificat și salvează business hashes;
2. aplică 040/041 o singură dată prin identitatea administrativă existentă,
   cu `UNIHUB_DB_AUTHORITY_CUTOVER_BOOTSTRAP=1` doar în procesul de cutover și
   fără `UNIHUB_DB_PROCESS_AUTHORITY`; nu persista flagul în `.env`/systemd;
3. creează cele patru LOGIN-uri de serviciu în boundary-ul operațional separat;
4. atașează contractele exacte cu provisionerul; ownerul FieldOps acordă
   SELECT către autoritatea web-read după existența ei; verifică zero
   sesiuni/membri legacy și setează `unihub_runtime NOLOGIN`; apoi scrie separat
   `.env`, `.env.worker`, `.env.import-worker`, `.env.migrations`, fără
   afișarea DSN;
5. instalează unitățile, `daemon-reload`, apoi deployează artefactul formal;
6. verifică principal/flags/membership, ACL negative, migrations, servicii,
   health local/public, head/digest/fingerprints și absența mutațiilor Finance.

Pasul 3–4 modifică identități/credentiale și este singura confirmare umană
necesară. Nu se creează LOGIN `unihub_finance_import_worker` și nu se rulează
nicio operație Finance live.

Runnerul acceptă pasul 2 numai dacă identitatea curentă și cea de sesiune sunt
același superuser, baza existentă este tracked cu checksums până la 039 și
toate migrările de la 040 încolo sunt restante. Invocarea bootstrap aplică
exclusiv 040/041 și se oprește; 042 și orice migrare ulterioară rămân pentru
runnerul restricționat după provisionare și grantul ownerului FieldOps. Fresh
bootstrap, istoric incomplet, orice migrare post-039 deja aplicată, role switch,
principal neprivilegiat sau reutilizare după 041 sunt refuzate.

### 16.4 Rollback și limite

Înainte ca migration service să pornească, rollbackul folosește handle-ul normal
de backup. După aplicarea 040/041, manifestul vechi este incompatibil și
rollbackul de cod este refuzat deliberat; deployul păstrează candidatul și
handle-ul în `recovery_required`, apoi execută roll-forward pe același SHA sau
pe un candidat corectiv aprobat. Migrațiile nu se editează și nu se dau jos.
Scriptul legacy `--rollback` reface doar flagul LOGIN pentru recovery controlat;
nu schimbă credentiale și nu permite pornirea unui artefact cu manifest vechi.

Rollbackurile business sunt inverse generations/CAS: sales clonează generația
reținută, Finance ar crea o generație inversă numai într-un lot viitor aprobat,
iar shadow mută doar pointerul de review după rehash. Stagingul, ledgers și
pre-image-ul nu se șterg. P1-A nu rezolvă lifecycle-ul artefactului sales
(P1-B), privacy/approval salary (P1-C) sau recovery Google/Grile (P1-D).

### 16.5 Închidere live

Identitate release și gate-uri:

- source/artifact SHA: `4cc3d322e0c0559615c642568fe914af29370b8e`;
- CI formal `30982550494`, integral verde; artifact GitHub digest
  `sha256:18240bf1a36b7764275dd30e5b269fb1dbf64fa06b2999c6dba748c6747a086f`;
- tarball verificat prin `SHA256SUMS`, SHA-256
  `95f5dbdf7d597b310e17d10cd187e25ff3369d1ab0b4a4f846e0437dad947c65`;
- deploy formal `30982809274`, verde; rollback handle
  `/opt/Mobiup/ops/backups/retail-deploy/20260805T065144Z-2e506e34483c-to-4cc3d322e0c0-dd26ab38fe8413db`;
- migrațiile live 040/041/042 au exact checksumurile din 16.1;
- Terra xhigh și Luna xhigh au auditat independent același SHA exact și au dat
  GO, fără findings P0/P1/P2; Luna a rulat 56 verificări PostgreSQL/Valkey
  izolate. Finance nu a fost exercitat live.

Findings și candidați refuzați înainte de release:

- granturi sau dependențe directe pe LOGIN, bypassul composite web către
  `fieldops_visits`, DML columnar FieldOps și bootstrapul care ar fi consumat
  042 au fost găsite independent, corectate și reauditate pe SHA-uri noi;
- CI `30981407131` pe `8b24e659` a respins un checksum public ca posibil secret;
  baselineul a primit numai fingerprintul hash-uit, fără slăbirea hookului;
- deployurile intermediare `30977246956` și `30977407851` au expus, respectiv,
  permisiunea greșită `0600 root:root` pentru `.env*` și lipsa grantului
  owner-issued FieldOps. Primul rollback a refuzat corect manifestul vechi;
  recuperarea roll-forward a păstrat handle-ul
  `/opt/Mobiup/ops/backups/retail-deploy/20260805T050933Z-83194c653b78-to-2e506e34483c-b56f2a8de32a6552`.

Dovezi live după deploy:

- primary `main`, `origin/main` și checkoutul de producție sunt curate la SHA-ul
  artifactului; backend, worker și import worker sunt active, migration service
  are `Result=success`, iar health local/public este verde;
- cele șase authority-uri și `unihub_schema_owner` sunt NOLOGIN/fără capabilități
  privilegiate. Cele patru LOGIN-uri au exclusiv contractele directe așteptate;
  runnerul este NOINHERIT și poate seta numai schema owner. LOGIN-urile au zero
  ACL-uri directe, default ACL sau obiecte deținute; PUBLIC nu are CREATE;
- `unihub_runtime` este NOLOGIN fără sesiuni, iar principalul Finance de
  producție nu există. Fișierele `.env*` sunt `root:andrei 0640`; fișierul de
  migrare conține ca nume de cheie numai `MIGRATION_DATABASE_URL`;
- `fieldops_visits` este sub `unihub_schema_owner`, cu SELECT owner-issued,
  non-grantable către `unihub_web_read`, zero ACL columnar/PUBLIC și zero DML
  efectiv pentru web-read, business-write sau LOGIN-ul web. Startupul a
  sincronizat 14 vizite și a devenit ready;
- P&L este neschimbat: 97.687 rânduri, două companii, 2017-01..2026-06,
  569.813.991,84 RON, fingerprint `d0506e8af8fb1730786132fb7979d870`;
- sales păstrează un head, revizia 2, două promotions și fingerprintul
  `f2bd5d1bea45a22911b4dba684fc8a78`. Stagingul a crescut de la 7.022 la
  12.696 prin snapshotul normal 214 (5.674 rânduri, `processing`, nepromovat),
  pornit înainte de deploy; nu este mutație a headului sau ledgerului;
- toate cele cinci tabele Finance generation și cele trei tabele shadow au zero
  rânduri; shadow pointerul rămâne revizia 0. Nu s-a creat credential Finance și
  nu s-a executat Finance stage/apply/rollback.

Backup și rollback:

- backupul de cutover `20260805_080132` este `verified`, nouă fișiere și toate
  checksumurile locale trec; copia `.env*` pre-cutover este root-only 0600;
- backupul predeploy `20260805_095145` este verificat integral atât local, cât
  și pe NAS (`nas_sync_ok=1`), nouă fișiere, 126.051.171 bytes;
- handle-ul final păstrează sursa/dist-ul pre-switch. După 040/041 nu există
  downgrade automat sigur la manifestul vechi: recovery-ul de cod este
  roll-forward verificat, iar rollbackurile business rămân inverse
  generations/CAS fără ștergerea stagingului, ledgerelor sau pre-image-ului.

Verdict P1-A: **CLOSED LIVE**. M-06, M-07, R-01 și R-02 sunt închise integral.
Finance live rămâne **NO-GO**. P1-B nu a fost început în acest goal.

### 16.6 Hotfix operațional sales import — 2026-08-05

La reîncărcarea fișierului `Vanzari_MobiUp_MobiCell (77).xlsx`, cutoff
`2026-08-04`, UI a raportat eronat că există deja un import în curs. Dovezile
live au arătat că primul job reușise: snapshotul 214 era `processing` cu
manifest `validated`, 5.674 rânduri staged, headul 213/revizia 2 și datele live
neschimbate. Rezultatul ARQ efemer nu mai era recuperabil de UI, iar retry-ul
cu același digest a eșuat pe lease și a eliminat spool-ul comun al candidatului.

Hotfixul `2fe927794d302a3c5d14a4f2d345e6f27c546fb0`:

- caută înainte de enqueue o generație `validated` cu exact același SHA-256 al
  fișierului și același cutoff;
- reface atomic spool-ul content-addressed din bytes reîncărcați și verifică
  egalitatea căii cu sursa legată în DB;
- returnează manifestul și tokenul generației existente ca rezultat `complete`,
  fără al doilea job, fără alt staging și fără schimbarea headului live;
- refuză fail-closed dacă sursa validată indică altă cale.

Poarta locală: 47 teste trecute, 6 skip-uri DB izolate și mypy verde pe
repository/service/jobs. Commitul este pe `main`, sincronizat și deployat
direct pe primary; backendul a fost restartat, startupul a sincronizat 14
vizite, iar health local/public este verde. Pentru închiderea operațională a
snapshotului 214, operatorul reîncarcă o singură dată exact același fișier cu
cutoff `2026-08-04`; UI trebuie să afișeze manifestul deja validat și butonul de
promovare. Promovarea rămâne explicită și nu este executată automat de hotfix.

### 16.7 Candidat consolidat P1-B -> P3 — 2026-08-05

SHA-ul sursă local verificat este
`7cb8375ef559a866d8944c60c22b9f416c8c36c4`. Registrul de mai jos este
registrul unic de dispoziție; mențiunile anterioare din document sunt istoric,
nu dispoziții suplimentare.

| Finding | Dispoziție unică | Dovadă / justificare |
| --- | --- | --- |
| M-01 | demonstrat deja | integritatea staging/promote și multiplicitatea au fost închise în P0-A |
| M-02 | demonstrat deja | autoritatea P&L per magazin-lună a fost închisă în P0-A |
| M-03 | demonstrat deja | identitatea/proveniența salarială a fost închisă în P0-A |
| M-04 | demonstrat deja | bypassul `replace_month_snapshot` este eliminat și revocat live |
| M-05 | demonstrat deja | Finance folosește generații/manifest/CAS; live apply rămâne NO-GO |
| M-06 | demonstrat deja | authority roles și matricea ACL au fost închise live în P1-A |
| M-07 | demonstrat deja | ledgers/staging/head sunt protejate append-only DB-side |
| M-08 | implementat | artefact sales content-addressed, `0600`, hash, fsync și readback înainte de terminal DB |
| M-09 | implementat | stare intermediară, reconciler idempotent și retention head/predecessor/ledger |
| M-10 | implementat | salary approval leagă exact manifestul, ambele companii, reconcilierea 8/8/0 și reviewer distinct |
| M-11 | implementat | Grile are owner/epoch/lease și checkpoint înainte de Google I/O |
| M-12 | implementat | Google I/O rulează prin adapter thread-affine bounded; reconcilerul nu reia automat starea incertă |
| M-13 | implementat | XLS/XLSX au signature, ZIP/XML, expanded-bytes, ratio, member și cell budgets |
| M-14 | implementat | exporturile au caps 50.000 rânduri, 1.000.000 celule și 64 MiB estimate, cu spool/chunks |
| M-15 | implementat | startupul web nu mai face sync/prewarm business; ARQ rămâne degradabil |
| M-16 | implementat | scope-urile istorice domină explicit prin `site_code`; compania Grile necunoscută este refuzată |
| M-17 | neaplicabil justificat | nu este confirmat un model multi-tenant; utilizatorii autorizați au scope Retail global, deci nu se inventează segmentare |
| M-18 | neaplicabil justificat | schimbarea identității OS a serviciului este limită restrictivă `AGENTS.md`; hardeningul existent rămâne, fără mutație neautorizată |
| M-19 | implementat | backendul pornește cu 2 workeri web; operations/import sunt deja servicii separate, fiecare cu concurență bounded |
| R-01 | demonstrat deja | contractele DB least-privilege au fost verificate live în P1-A |
| R-02 | demonstrat deja | rolul Finance dedicat este implementat; credentialul live nu este creat |
| R-03 | implementat | scanul negativ de privacy și gate-ul de aprobare salarială sunt fail-closed |
| R-04 | demonstrat deja | `site_code` domină scope-ul istoric în exporturi/dashboard |
| R-05 | demonstrat deja | cohortele curent/istoric sunt separate în fixtures și query-uri canonice |
| R-06 | implementat | fotografiile sunt legate de vizita DB, cale canonică, fișier regulat și non-symlink |
| R-07 | implementat | preview-ul nu mai construiește exportul complet |
| R-08 | implementat | daily/incentive export folosesc limite DB și livrare XLSX spooled |
| R-09 | implementat | bugetul DB permite 2 workeri web, cu session/rate-limit shared și shutdown bounded |
| R-10 | demonstrat deja | P&L/ERP/HR folosesc atribute curente sau snapshoturi/effective dates explicite |
| R-11 | implementat | lucrul greu a fost scos din lifespan; readiness nu depinde de refresh business |
| R-12 | demonstrat deja | EXPLAIN/BUFFERS pe DB izolat: agent-day 9,639 ms; item-day 316,855 ms, ambele sub 2.500 ms |
| R-13 | implementat | forecastul parțial folosește distribuția zilnică din ultima rulare business, nu extrapolare calendaristică implicită |
| R-14 | implementat | datele UI folosesc helperi Europe/Bucharest testați determinist |
| R-15 | implementat | `any`-urile de producție din lane-ul Agents/salary chart au fost eliminate, strict TS extins |
| R-16 | implementat | runtime/dev Python au lockfile-uri complete cu hashuri și CI instalează `--require-hashes` |
| R-17 | implementat | XML-ul XLSX neîncrezător folosește `defusedxml`; formulele/hyperlinkurile neîncrezătoare rămân neutralizate |
| R-18 | implementat | payloadurile ARQ sales/Grile transportă identități persistate, nu bytes sau stări business complete |
| R-19 | demonstrat deja | `/metrics`, docs și OpenAPI răspund public 404; health rămâne separat |
| R-20 | demonstrat deja | capabilitățile/rate-limit-urile Grile și write boundaries sunt deja aplicate |
| N-01 | implementat | runtime Visits este PostgreSQL-only; proiecția HR se reîmprospătează în worker sub advisory lock, fără fallback SQLite |
| N-02 | implementat | Tasks/HR au inputuri typed, limite și envelope de paginare cu count separat corect la pagini goale |
| N-03 | implementat | erorile worker Grile persistă coduri finite, fără excepții necontrolate în stare |
| N-04 | implementat | jobul Grile leagă request context determinist de `operation_id` |
| N-05 | implementat | actorul sales implicit ambiguu este `unknown`, nu o identitate legacy inventată |
| N-06 | implementat | denumirile stale `sqlite_map` au fost înlocuite cu `visits_map` |
| N-07 | implementat | tooltipurile Recharts și modulele P3 trec typecheck complet/strict fără `any` local |
| N-08 | implementat | warningurile ESLint locale nefolosite au fost eliminate; lint are zero warnings |
| N-09 | demonstrat deja | cache-ul filtrelor este invalidat prin versiune DB cross-process, nu memorie locală |

Porți locale pe candidatul sursă:

- PostgreSQL 18 + Valkey izolate, migrări fresh 014..044: `1589 passed, 7 skipped`;
- frontend: 34 fișiere / 245 teste; `typecheck`, `typecheck:strict`, lint și build verzi;
- mypy: 346 fișiere, zero erori; 133 teste backend țintite post-fix verzi;
- runtime/dev lock `--require-hashes`, import smoke, `pip check`, `pip-audit`
  strict, secret scan și Bandit regression gate verzi;
- checksum migrare 043:
  `bf997d5e2f74aa3b464ac0cc0c8529247cfc63b1ed5af7d7ff231fb339b9064d`;
  checksum migrare 044:
  `762c6352f8a00deb6989bd24ffac5ebefc9d537817233507d92e8dd4422d7a1c`;
- lock runtime:
  `bdabff0b5e7f4931d386f1b95d92dd3c9499a716e5de7e65ba8935c62d2a213f`;
  lock dev: `052ab1469d523d16a1639a702e13180fc528335e098987616a3cd61f0bd358ce`.

Snapshotul sales 214 și Finance/salary live apply nu sunt mutate de candidat.
Auditul independent exact-SHA, CI-ul formal, deployul, probele live cu doi
workeri și dovada de rollback sunt porțile rămase înainte de `CLOSED LIVE`.
