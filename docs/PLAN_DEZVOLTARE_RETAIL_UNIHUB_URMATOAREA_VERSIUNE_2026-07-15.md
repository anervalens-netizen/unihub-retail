# PLAN DE DEZVOLTARE — UniHub Retail, următoarea versiune

**Data:** 2026-07-15
**Bază de cod reconciliată și verificată live:** `964f6da07ad9e4382070866275509f3be2b399a1`
**Baseline live anterior programului:** `d08add17147d9f24b23642dbb1a0084708ff9307`
**Scop:** remediere verificabilă, fără big-bang rewrite și fără funcționalități noi înainte de închiderea P0

> Actualizare 2026-07-16: migrarea vizitelor a fost inchisa. Retail citeste
> PostgreSQL `fieldops_visits`, FieldOps citeste/scrie aceeasi autoritate, iar
> SQLite este numai arhiva pre-cutover. Punctele istorice despre un viitor sync
> SQLite -> PostgreSQL nu mai reprezinta backlog activ.

## Stare de execuție la reconciliere

| Pachet | Stare | Dovadă / pas rămas |
|---|---|---|
| PR-00 / WP0.4 | **Închis și activ** | PR #95, merge `a055b85`; runnerul persistent de producție este oprit/eliminat, PR-urile rulează GitHub-hosted, iar deployul folosește runner dedicat plus approval one-time host-side. |
| WP0.1 | **Închis și activ** | PR #96, merge `9b5d17c`, migrarea 026 aplicată și reconciliere DB read-only. |
| WP0.2 | **Închis și activ** | PR #97, merge `96b9a0d`, migrarea 027 aplicată; check-ul și sync-ul au căi separate. |
| WP0.3 | **Închis și activ** | PR #98, merge `0a984a1`, migrarea 028 aplicată; backendul și workerul sunt sănătoase. |
| WP0.5 + suprafață HTTP/sesiune | **Închis și activ** | PR #99, merge `05387f9`; rutele publice diagnostice răspund 404, iar health-ul intern este verde. |
| Dovezi P0 import/runner | **Întărite și testate** | PR #101, merge `6dafc72`; conflictul/duplicatul păstrează snapshotul PostgreSQL existent, iar proba TimesFM respinge orice răspuns HTTP direct. |
| Deploy/rollback | **Demonstrat** | PR #102 și #104; CI `29489378316`, deploy `29489754125`, rollback compatibil verificat și redeploy `29489997636`. |
| Ajustare card Incentive | **Închisă și activă** | PR #103 / `ddc9eed`; cardul afișează cele patru valori business și păstrează cele două mecanisme dedesubt. |
| Documentație/release | **Ultimul gate** | PR #105 reconciliază auditul, planul, release notes și elimină arhivele/planurile redundante din `HEAD`; urmează CI-ul final, tagul și GitHub Release. |

Cele trei magazine prezente în iunie și absente în iulie au fost verificate
read-only: toate sunt inactive. Nu se reactivează automat; statutul lor rămâne o
decizie business explicită.

# 1. Decizia de produs și release

## 1.1 Oprește temporar dezvoltarea de funcționalități

Următoarele schimbări nu trebuie amestecate cu dashboarduri noi, KPI-uri noi sau redesign cosmetic:

- integritatea importului și master data;
- autorizarea și efectele ascunse Grile;
- finalizarea salarială și resetul;
- izolarea CI;
- exporturile și job orchestration;
- cache/no-store pentru date sensibile.

Adăugarea de funcționalități înainte de P0 mărește suprafața care va trebui revalidată și face rollbackul mai dificil.

## 1.2 Versionare recomandată

### `v2.0.1` — hotfix de integritate și securitate

Stare: codul hotfix este integrat și verificat live; au rămas publicarea dovezii
finale, tagul și GitHub Release.

Include obligatoriu:

- C-01: oprește dezactivarea magazinelor prin absență din import;
- C-02: transformă `/api/grile/run` în operație read-only;
- C-03: blochează finalizarea/resetul la date incomplete;
- C-04: mută sau izolează runnerul de PR;
- M-01: `no-store` pe salarii și alte răspunsuri sensibile;
- M-37: rollback complet la Target Calculator;
- M-31/m-41/m-33/m-01: suprafață HTTP, SPA fallback și refresh sesiune.

Legenda graficului și mesajul promo rămân findings minore deschise; nu au fost
amestecate în hotfix după decizia de a opri schimbările cosmetice până la P0.

### `v2.1.0` — hardening operațional și financiar

Țintă: 2–4 săptămâni după hotfix.

Include:

- staging și promovare controlată pentru importuri;
- outbox și state durabil pentru joburi;
- cozi separate și spool de fișiere;
- calcule promo/incentive fail-closed;
- exporturi background/streaming;
- roluri DB și Google cu least privilege;
- row-level organizational scope;
- validare API unificată;
- audit și retenție pentru artefacte salariale.

### `v2.2.0` — scalare, mobil și release engineering

Țintă: 4–8 săptămâni.

Include:

- endpoint batch pentru istoricul multi-lună;
- vizite paginate și sync incremental;
- backend cu minimum două instanțe;
- mobile shell și accesibilitate reală;
- E2E full-stack și mobile visual regression;
- deployment automat, canary și rollback;
- lock-uri deterministe pentru dependențe.

### `v3.0.0`

Nu folosi `v3.0.0` doar pentru că sunt multe taskuri. Major version este justificat numai dacă introduci o schimbare incompatibilă, de exemplu:

- contract nou de autorizare cu scope organizațional obligatoriu;
- înlocuirea definitivă a fișierelor JSON/Excel ca surse operaționale;
- API versionat incompatibil;
- schimbare majoră a modelului de date/master data cu migrare proprie.

# 2. Principii nenegociabile

1. **Nicio operație financiară nu este best-effort.** Ori este completă și verificată, ori eșuează explicit.
2. **Absența dintr-un fișier nu înseamnă închidere.**
3. **Un endpoint read-only nu produce side effects.**
4. **Orice operație destructivă are preview, manifest, aprobare, idempotency și rollback.**
5. **Fișierele mari nu circulă prin queue payload.**
6. **Datele salariale nu se cache-uiesc și nu rămân pe disc fără retenție.**
7. **Frontendul nu este graniță de securitate.**
8. **CI de PR nu rulează pe infrastructură de producție sau pe runner persistent cu acces intern.**
9. **Optimizarea se face după măsurare, dar integritatea și boundedness nu așteaptă un incident.**
10. **Fiecare PR are criteriu de acceptare și rollback documentat.**

# 3. P0 — pachetul `v2.0.1`

## WP0.1 — Oprirea imediată a dezactivării implicite a magazinelor

**Finding-uri:** C-01, M-11, M-13, M-14.

**Stare:** implementat în PR #96. `upsert_stores` nu scrie `is_active`, coverage-ul
și diff-ul agregat sunt persistate înaintea tranzacției de promovare, iar schimbarea
activității este endpoint/repository separat cu CAS, motiv și `requested_by_sub`.

### Modificare minimă de hotfix

În `upsert_stores`, elimină temporar blocul care marchează inactive magazinele absente din import. Importul poate actualiza magazinele prezente, dar nu poate închide altele.

### Implementare definitivă

Adaugă:

- `sales_import_jobs`;
- `sales_import_staging_rows`;
- `sales_import_store_diff`;
- câmpuri `source_sha256`, `is_full_snapshot`, `coverage_status`, `promoted_at`,
  `promoted_by_sub`, `rejected_reason`;
- workflow `uploaded -> validated -> awaiting_approval -> promoted|rejected`;
- raport de diferențe: magazine prezente, lipsă, noi, realocate și conflicte;
- praguri configurabile, nu hardcodate;
- operație separată pentru închiderea magazinului, cu dată și motiv.

### Reguli de validare

- toate câmpurile obligatorii strict parsabile;
- sumele și cantitățile reconciliate cu fișierul;
- `SiteCode` are o singură combinație de metadate;
- numărul bonului este valid;
- duplicatele sunt detectate;
- fișierul parțial nu poate promova master data;
- nicio activare/dezactivare implicită.

### Teste

- fișier complet;
- fișier cu 10% magazine lipsă;
- fișier pentru o singură firmă;
- conflict ASM pe același `SiteCode`;
- duplicate;
- valori monetare invalide;
- bonuri fără ID;
- retry identic;
- două importuri concurente pe aceeași lună.

### Rollback

Înainte de release:

1. exportă snapshotul `stores`;
2. salvează lista `site_code/is_active/manager/firma`;
3. pregătește script read-only de reconciliere;
4. rollbackul codului nu trebuie să reactiveze automat magazine;
5. orice corecție de master data se aplică prin script aprobat și auditabil.

### Criteriu de acceptare

Un fișier parțial nu schimbă `stores.is_active`. Promovarea produce un diff explicit și nu există nicio cale API/worker care să închidă prin absență.

---

## WP0.2 — Separarea verificării Grile de sincronizarea targetelor

**Finding-uri:** C-02, M-17, M-18.

**Stare:** implementat în PR #97. Check, diff și sync au rezervări separate;
check-ul este read-only, iar sync cere grup dedicat, CSRF, rate limit și audit OIDC
pe `sub`.

### Schimbări

- `grile_check_background` devine pur read-only;
- elimină `apply=True` din jobul pornit de `/api/grile/run`;
- creează `grile_agent_targets_sync_background`;
- protejează sincronizarea cu grup dedicat;
- endpointul de sync cere CSRF, rate limit și audit;
- persistă `requested_by_sub`, nu doar email;
- returnează diff înainte de apply;
- permite dry-run obligatoriu înainte de apply.

### Criteriu de acceptare

Hash-ul tabelului `agent_targets` este identic înainte și după `/api/grile/run`. Numai endpointul privilegiat schimbă datele.

---

## WP0.3 — Finalizare salarială fail-closed

**Finding-uri:** C-03, M-03, M-04, M-05.

**Stare:** integritatea cerută pentru `v2.0.1` este implementată în PR #98:
parsing strict, coverage complet, manifest persistent/hash-uit, aprobare, surse
recuperabile, checkpoint per magazin, rollback și blocarea retry-ului incert.
Retenția automată, separarea identităților Google și o regulă obligatorie cu două
persoane distincte rămân P1/politică business, nu sunt declarate închise.

### Manifest obligatoriu

Creează `grile_artifact_manifests` sau echivalent, cu:

- operație și lună;
- commit/release;
- număr așteptat și procesat de magazine;
- număr așteptat și procesat de agenți;
- lista erorilor — trebuie să fie goală;
- totaluri de control;
- hash SHA-256 al fiecărui artefact;
- timestamp;
- subiectul care a cerut operația;
- subiectul care a aprobat;
- status `draft/verified/approved/consumed`;
- relația cu resetul.

### Reguli

- o valoare numerică invalidă oprește finalizarea;
- un magazin cu eroare oprește finalizarea;
- un agent așteptat dar lipsă oprește finalizarea;
- un timeout Google nu este tratat ca rând de audit suficient;
- un artefact parțial nu folosește numele oficial;
- resetul acceptă numai manifest `approved`;
- manifestul devine `consumed` atomic cu resetul;
- resetul păstrează checkpoint per magazin și copia sursei;
- retry-ul Google trebuie demonstrat prin test.

### Two-person rule

Pentru reset live:

1. utilizatorul A generează și verifică;
2. utilizatorul B aprobă;
3. workerul execută;
4. aceeași persoană nu poate executa ambele roluri, exceptând procedură de urgență auditabilă.

### Retenție

- workbook final: retenție definită de owner HR/legal;
- artefacte intermediare/test: retenție scurtă;
- permisiuni OS dedicate;
- backup criptat;
- ștergere verificată și logată.

### Criteriu de acceptare

Nu există niciun path în care `reset` rulează doar pentru că un fișier există. Orice eroare de citire produce operație failed și zero efecte destructive.

---

## WP0.4 — Izolarea runnerului CI

**Finding:** C-04.

**Stare:** calea de pull request este închisă în PR #95. Toate check-urile rulează
GitHub-hosted, pachetele `@unihub/*` sunt vendored cu integritate verificată, iar
testul controlat blochează accesul la producție, Tailscale și peer-ul TimesFM.
Separarea deployului există în workflow. Deoarece required reviewers GitHub nu
sunt disponibili pentru repository-ul privat pe planul curent, approval-ul este
host-enforced: root-only, interactiv, one-time, valabil 30 de minute și legat de
CI run ID, SHA-ul exact din `main` și SHA-256-ul artefactului. Runnerul și
variabila de activare rămân fail-closed până la merge, instalare și verificarea
sudo policy-ului exact.

### Acțiuni imediate

- dezactivează runnerul `unihub-server` pentru evenimentul `pull_request`;
- mută PR checks pe GitHub-hosted sau runner efemer;
- verifică și rotește toate secretele/credencialele accesibile vechiului runner;
- verifică Docker socket, mount-uri, SSH keys și rețeaua internă;
- separă deploymentul pe runnerul dedicat și impune approval-ul host-side
  one-time pentru run/SHA/hash înainte de entrypoint;
- pin-uiește actions și imaginile la SHA/digest.

### Topologie țintă

- **PR runner:** efemer, fără secrete, fără acces intern, fără deploy.
- **Build/release runner:** produce artefact și SBOM, nu intră în producție.
- **Deploy runner:** protejat, rulează numai artefact semnat de pe branch/tag aprobat.
- **Host producție:** nu execută cod de PR.

### Criteriu de acceptare

Un PR malițios demonstrativ nu poate lista rețeaua internă, accesa metadata/secrete sau scrie în producție.

---

## WP0.5 — Patch-uri de confidențialitate și tranzacții

**Finding-uri:** M-01, M-37, m-06, m-08.

**Stare:** M-01 și M-37 sunt implementate în PR #99 împreună cu M-41, M-33 și
m-01. Finding-urile cosmetice m-06 și m-08 rămân în backlog și nu blochează
integritatea/security hotfix-ului.

Livrează în același release numai dacă sunt schimbări mici și izolate:

- antete `private, no-store` pe salarii/P&L/fotografii/exporturi;
- validare completă a site-code-urilor Target Calculator înainte de update;
- rollback DB la orice mismatch;
- mesaj promo error cu semantică corectă;
- fill/legend corect pentru graficul lunar.

# 4. P1 — pachetul `v2.1.0`

## WP1.1 — Platformă durabilă de import și joburi

**Finding-uri:** M-08–M-20.

### Spool, nu bytes în Valkey

Flux țintă:

1. backendul validează dimensiunea și magic bytes;
2. scrie într-un director/object storage cu permisiuni restrictive;
3. calculează SHA-256;
4. persistă jobul în PostgreSQL;
5. pune în coadă doar `job_id`;
6. workerul validează hash-ul și lease-ul;
7. scrie status/progres/heartbeat în DB;
8. șterge fișierul conform retenției.

### Cozi separate

- `retail-import`;
- `grile-read`;
- `grile-destructive`;
- `exports`;
- eventual `maintenance`.

Fiecare are:

- worker separat;
- timeout separat;
- concurrency separată;
- SLO și alertă de backlog;
- dead-letter/reconciliation;
- idempotency key.

### Transactional outbox

Importul trebuie să creeze outbox events pentru:

- rebuild reporting;
- refresh metrics;
- invalidare cache;
- sync Grile/targete dacă este aprobat;
- notificare de completitudine.

### Cache filtre

Cheia include `import_version` sau invalidarea se propagă prin Valkey pub/sub/stream. Nu mai există cache per proces fără coordonare.

### Criterii

- queue outage nu pierde joburi;
- un restart nu închide job activ fără lease expirat;
- UI distinge `queued`, `running`, `waiting_approval`, `completed`, `failed`,
  `queue_unavailable`;
- un import complet nu este declarat „gata” până când derivatele obligatorii sunt gata.

---

## WP1.2 — Campanii și incentive fail-closed

**Finding-uri:** M-06, M-07, M-25.

### Acțiuni

- extrage serviciu public `CampaignFinanceService`;
- modele tipizate pentru `CompleteCalculation`, `PartialCalculation`, `FailedCalculation`;
- nicio excludere eșuată nu devine dicționar gol;
- promo POS + tail păstrează provenance și coverage;
- campaniile multi-perioadă au test de intersecție;
- datele de request sunt `date`, intervalele sunt validate;
- exporturile și plata cer `CompleteCalculation`;
- configurația promo trece în DB cu revizie și audit.

### Reconciliere

Pentru lunile deja procesate, rulează un raport read-only:

- rezultat curent;
- rezultat după fail-closed/refactor;
- diferență per magazin/agent/produs;
- owner business aprobă orice delta înainte de deploy.

---

## WP1.3 — Export service

**Finding-uri:** M-21–M-25.

### Arhitectură

- requestul creează `export_job`;
- workerul generează write-only într-un fișier temporar;
- rezultatul merge în storage cu TTL;
- clientul vede progres și descarcă artefactul;
- serverul loghează hash, număr rânduri, scope și subiect;
- preview are query limitat și nu construiește workbook;
- un singur connection context este folosit corect;
- concurența exporturilor este limitată;
- inputul are budget de celule.

### Limite inițiale recomandate

Stabilește pe baza datelor reale, dar pornește conservator:

- maximum luni pentru export generic;
- maximum rânduri/celule;
- maximum un export greu activ per utilizator;
- maximum N exporturi per worker;
- TTL scurt pentru artefactele cu salarii;
- timeout separat de request web.

### Criteriu de acceptare

Trei exporturi maxime concurente nu cresc RSS-ul web semnificativ și nu ocupă toate conexiunile DB.

---

## WP1.4 — Autorizare pe scope organizațional

**Finding-uri:** M-28, M-29, M-30, M-31.

### Model

Persistă sau derivă autoritativ:

- `subject`;
- rol/capabilități;
- firme;
- regionali;
- magazine;
- valabilitate temporală;
- owner și sursă.

### Aplicare

- scope-ul se adaugă server-side în repository;
- filtrul client poate doar restrânge scope-ul, niciodată extinde;
- obiectele individuale — vizite, fotografii, taskuri — verifică ownership/scope;
- exporturile folosesc același scope;
- audit log păstrează subiect și resursă, nu date sensibile.

### Roluri DB

- web read;
- web business write;
- import worker;
- Grile worker;
- migration owner.

### Criteriu de acceptare

Test matrice rol × endpoint × magazin, cu toate încercările cross-scope respinse.

---

## WP1.5 — Auth/session și startup

**Finding-uri:** M-33, M-34.

### Session refresh

- singleflight distribuit cu rezultat notificat waiterilor;
- lock TTL > timeout + marjă;
- waiterul nu șterge sesiunea;
- metrici `refresh_started/success/failure/wait_timeout`;
- fault tests cu IdP lent și indisponibil.

### Startup

- critical path: config, session backend, DB, migration verification;
- ARQ lazy/best-effort;
- warmup/sync în background;
- endpointurile async întorc 503 specific când queue nu este gata;
- readiness reflectă exact contractul.

---

## WP1.6 — AI Forecast data governance

**Finding-uri:** M-32, m-12.

### Acțiuni

- interzice HTTP în producție;
- mTLS și cert pinning/CA controlată;
- minimizează/pseudonimizează `site_code` și elimină labels organizaționale dacă modelul nu le cere;
- egress allowlist;
- API key numai secret store;
- response size cap;
- config versionată per run;
- output retention și ACL;
- registru de model: sursă date, profil, excluziuni, commit, metrici, owner.

# 5. P2 — pachetul `v2.2.0`

## WP2.1 — Dashboard batch și corectitudine multi-lună

**Finding-uri:** M-38–M-40.

### Backend

Creează endpoint agregat, de exemplu:

`POST /api/dashboard/history-aggregate`

Request:

- listă bounded de luni;
- scope;
- include closed;
- metrici/sections cerute.

Răspuns:

- totaluri și cardinalități calculate în DB;
- agenți unici reali;
- mixuri și daily aggregate;
- metadata de completitudine;
- query count și timings observabile.

### Frontend

- un singur query;
- abort la schimbarea scope-ului;
- loading/partial/error explicit;
- cap UI pentru selecții extreme;
- fără `Promise.all` necontrolat.

### Criterii

- 35 luni = un request;
- agent cardinality corectă;
- pool peak bounded;
- hash de echivalență pentru metricile neschimbate.

---

## WP2.2 — Vizite

**Finding-uri:** M-26, M-27, M-29, M-35.

### Schimbări

- finalizat 2026-07-16: autoritate unica PostgreSQL si eliminarea dual-source
  din runtime;
- interval obligatoriu și cursor;
- query pe range de dată indexabil;
- endpoint sumar separat;
- atașamente cu ID opac și relație DB;
- row-level scope;
- refresh incremental al proiectiei `visits_snapshot` din PostgreSQL;
- metrică `visits_snapshot_lag_seconds`;

### Criteriu

Un milion de vizite sintetice nu schimbă semnificativ memoria per request și niciun
endpoint nu returnează istoric nelimitat.

---

## WP2.3 — Backend multi-instance și servicii separate

**Finding-uri:** M-54, M-53, M-55.

### Pași

1. elimină munca blocking din web;
2. separă users și directoare systemd;
3. construiește artefact imutabil;
4. rulează două instanțe web;
5. load balancer cu health;
6. rolling restart;
7. conexiuni DB per instanță recalibrate;
8. load test și failure test.

Nu crește numărul de workers înainte de a repara cache-urile in-memory și job lease; altfel multiplici inconsistența.

---

## WP2.4 — Mobile shell și design system

**Finding-uri:** M-47–M-49, m-05, m-08–m-10, m-13.

### Shell mobil

- CSS variables pentru header/nav/FAB;
- `env(safe-area-inset-top/bottom)`;
- ultimul element focalizabil rămâne complet vizibil;
- FAB eliminat din zonele data-dense;
- bottom sheet accesibil;
- focus trap și Escape;
- reduced motion.

### Dashboard

- maximum 1–2 grafice dense pe ecran;
- KPI primar + drill-down;
- tooltip compact;
- legendă custom;
- tabele late convertite în card/listă pe mobil;
- coloane selectabile;
- font normal minimum 12–14 px; 9 px nu mai este text informațional.

### Settings/import

- picker nativ pe mobil;
- drag-and-drop numai unde este implementat;
- progres de upload/job;
- stări success/error distincte.

### Salarii

- datele sunt marcate cu scope/lună;
- carduri responsive în loc de tabel de 860 px pe telefon;
- nu se păstrează date stale la schimbarea filtrului.

### Criteriu

Matrice de viewport:

- 360×800;
- 390×844;
- 412×915;
- iPhone cu safe-area;
- tabletă;
- dark/light.

Zero overlap, zero scroll orizontal pe fluxurile principale, exceptând tabele declarate cu alternativă accesibilă.

---

## WP2.5 — Testare reală și gate-uri

**Finding-uri:** M-49–M-52, m-15.

### Piramidă

#### Unit

- parsare/validare import;
- identități bon;
- campanii și excluderi;
- alocări target;
- state machines;
- formatters.

#### Integration PostgreSQL/Valkey

- import staging/promote;
- lease/outbox;
- Target Calculator rollback;
- RBAC scope;
- export job;
- session refresh concurent.

#### Full-stack browser

- BFF/session sintetică;
- Hub;
- Focus;
- Agents;
- Management;
- Settings/import/export;
- Grile dry-run/finalize;
- mobile viewports.

#### Fault injection

- DB pool limit;
- Valkey down;
- Google 429/503;
- IdP lent;
- fișier invalid/ZIP bomb;
- restart worker;
- response out-of-order.

### Type/lint

- extinde strict la tot `src`;
- zero warnings lint;
- limitează `any`;
- generated OpenAPI client/runtime validation.

### Coverage

- global branch coverage;
- diff coverage;
- praguri speciale pentru calcule financiare;
- frontend coverage pe state management;
- publică rapoarte ca artefact.

### SAST

- elimină gradual baseline Bandit;
- audit runtime și dev;
- SBOM;
- action pinning;
- secret scan pe istoric și HEAD.

# 6. Deployment, rollback și observabilitate

## 6.1 Pipeline țintă

1. PR checks pe runner efemer;
2. build artefact versionat;
3. SBOM și scan;
4. semnare/provenance;
5. deploy staging;
6. migrations one-shot;
7. smoke + contract + synthetic;
8. approval;
9. canary producție;
10. rollout;
11. verificare SLO;
12. rollback automat dacă pragurile eșuează.

## 6.2 Rollback

Fiecare PR care schimbă DB sau workflow financiar trebuie să conțină:

- backward compatibility window;
- migration expand/migrate/switch/contract;
- script read-only de verificare;
- rollback de aplicație;
- plan pentru date deja scrise;
- owner și deadline pentru contract phase.

## 6.3 Metrici noi obligatorii

- `sales_import_coverage_ratio`;
- `sales_import_store_diff_total{kind}`;
- `sales_import_derivation_pending`;
- `job_queue_depth{queue}`;
- `job_oldest_age_seconds{queue}`;
- `job_lease_expired_total`;
- `grile_manifest_validation_total{outcome}`;
- `grile_store_errors_total`;
- `campaign_calculation_completeness`;
- `export_active_jobs`, `export_bytes`, `export_rows`;
- `db_pool_wait_seconds`;
- `session_refresh_wait_seconds`;
- `visits_snapshot_lag_seconds`;
- `frontend_bootstrap_errors_total` prin telemetry;
- `dashboard_history_months_requested`.

Alertele trebuie să fie pe staleness și incompletitudine, nu doar pe 5xx.

# 7. Plan de PR-uri pentru execuție controlată

Execuția reală a respectat ordinea de risc și a tratat runnerul înainte ca noile
PR-uri să execute cod:

1. **PR #95 / PR-00:** runner PR izolat, pachete private vendored și artefact verificat — integrat `a055b85`.
2. **PR #96:** import/master data fail-safe — integrat `9b5d17c`.
3. **PR #97:** Grile check read-only și sync privilegiat — integrat `96b9a0d`.
4. **PR #98:** finalizare/arhivare/reset salarial fail-closed — integrat `0a984a1`.
5. **PR #99:** no-store, suprafață HTTP, Target Calculator atomic și session refresh — integrat `05387f9`.
6. **PR #101:** dovezi PostgreSQL import și proba directă de izolare TimesFM — integrat `6dafc72`.
7. **PR #102:** boundary de deploy separat și approval one-time — integrat `19a61ac`.
8. **PR #103:** semantica finală a cardului Incentive — integrat `ddc9eed`.
9. **PR #104:** rollback fail-closed și recovery auditabil — integrat `964f6da`.
10. **PR #105:** dovada finală de rollout, documentația canonică, baseline-urile
    regenerate și curățenia repository-ului — ultimul gate înainte de tag.

Backlogul P1/P2 rămâne împărțit în PR-uri logice pentru import staging/spool,
outbox și queue split, campaign finance, export jobs, organizational scope/DB
roles, dashboard batch, visits pagination/sync, dialog mobil accesibil și
evoluția mecanismului de approval dacă planul GitHub va oferi required reviewers.

Fiecare PR trebuie să fie reversibil și să nu combine refactor structural cu schimbare de business, exceptând unde contractul actual este chiar defectul.

# 8. Definition of Done

Un finding este închis numai dacă există simultan:

1. codul corect;
2. test care eșuează pe implementarea veche;
3. test de autorizare/edge case/concurență relevant;
4. metrică sau log pentru operațional;
5. documentație de runbook;
6. rollout controlat;
7. verificare post-deploy;
8. rollback testat;
9. owner business pentru orice schimbare de rezultat financiar;
10. actualizarea raportului de remediere cu dovezi, nu doar checkbox.

# 9. Criterii de acceptare pentru 10× trafic/date

Următoarea versiune nu este „gata de 10×” până când:

- niciun import parțial nu modifică master data;
- joburile sunt izolate și backlogul are SLO;
- fișierele nu trec prin Valkey;
- exporturile nu rulează în procesul web;
- Dashboard multi-lună folosește un request batch;
- pool wait p95 rămâne sub prag stabilit;
- un proces web poate cădea fără downtime;
- vizitele sunt paginate și sync lag este monitorizat;
- toate fluxurile mobile critice trec pe viewport real;
- restore-ul din backup este demonstrat;
- un utilizator nu poate ieși din scope-ul organizațional;
- runnerul de PR nu are acces la producție.

# 10. Rezumat brutal

Nu construi încă „v3” ca redesign sau set de funcționalități. Repară mai întâi mecanismele care decid ce magazine există, cine poate modifica targete, dacă salariile sunt complete și când se poate șterge sursa.

Ordinea corectă este:

1. **integritate și autorizare;**
2. **fail-closed financiar;**
3. **jobs și artefacte durabile;**
4. **least privilege;**
5. **scalare;**
6. **mobile și testare full-stack;**
7. **abia apoi funcționalități noi.**

Orice altă ordine mută riscul în producție și face aplicația mai greu de corectat.
