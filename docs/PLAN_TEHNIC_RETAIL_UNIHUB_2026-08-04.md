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
