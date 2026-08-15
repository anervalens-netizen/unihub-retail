# UniHub Retail

**Release semantic curent:** `v2.1.0`, rezolvat prin pointerul canonic
[`docs/releases/current.json`](docs/releases/current.json); pointerul trimite la
dovada exactă `SOURCE_SHA` / artefact / digest, fără un SHA viitor
self-referențial. Tagurile istorice `v2.0.0` și `v2.0.1` rămân nemodificate.

UniHub Retail este aplicația centrală pentru vânzări retail, targete, campanii,
salarii, P&L, raportarea vizitelor și interfața activă Grile.

## Surse canonice

- reguli de lucru și verificare: [`AGENTS.md`](AGENTS.md);
- arhitectură și contracte de business: [`APP_ARCHITECTURE.md`](APP_ARCHITECTURE.md);
- regula canonică pentru multiplicitatea rândurilor de vânzare:
  [`docs/adr/004-sales-row-multiplicity.md`](docs/adr/004-sales-row-multiplicity.md);
- instalare locală: [`LOCAL_SETUP.md`](LOCAL_SETUP.md);
- indexul canonic pentru candidatul Retail 9.5, readiness și documentele active:
  [`docs/README.md`](docs/README.md);
- auditul și planurile datate sunt evidence istoric și nu suprascriu indexul canonic;
- deploy privilegiat și rollback: [`ops/README.md`](ops/README.md).

Planurile și rapoartele închise nu sunt duplicate într-o arhivă Markdown din
HEAD; istoricul lor rămâne disponibil în Git.

## Runtime

| Componentă | Valoare |
| --- | --- |
| Frontend | React + TypeScript + Vite, build servit din `dist/` |
| Backend | FastAPI + asyncpg |
| Bază de date | PostgreSQL `unihub` |
| Auth | Authentik OIDC BFF, sesiune criptată în Valkey |
| Workeri | procese/cozi separate: operations, imports, Grile, exports și salary-exports (`unihub-*-worker.service`) |
| Backend service | `unihub-backend.service` |
| Migrații | `unihub-retail-migrate.service`, one-shot |
| URL public | `https://retail.unihub.ro` |

Probe:

- `/livez` verifică numai procesul;
- `/readyz` verifică PostgreSQL și sesiunea Valkey;
- `/health` este alias compatibil pentru `/readyz`;
- `/metrics`, `/docs`, `/redoc` și `/openapi.json` nu sunt accesibile public.

Coada ARQ este o dependență opțională pentru procesul web: indisponibilitatea
ei nu schimbă `/readyz` cât timp PostgreSQL și sesiunea Valkey sunt sănătoase și
nu blochează citirile autentificate. Enqueue răspunde bounded cu 503, iar
statusurile interne disting `not_found`, `backend_unavailable` și `unknown`;
starea terminală din PostgreSQL rămâne autoritativă.

## Module

- **Hub:** KPI retail, comparații, istoric și forecasturi AI persistate;
- **Focus:** Incentive, Promo, Concurs și Folii premium;
- **Agenți:** echipă, acoperire, Grile și evaluare;
- **Management:** manageri, Calculator Target, Salarii și P&L;
- **Setări:** importuri, exporturi și preferințe;
- **Vizite:** read model Retail peste sursa comună FieldOps.

Deep-link-urile venite din UniHub Insight folosesc `source_context=insight` și
deschid direct suprafața operațională cerută, cu perioada și filtrele
Firma/Manager/Magazin/Agent. Un scope cu mai multe magazine rămâne la nivelul
părinte; Retail nu alege implicit primul magazin. Autorizarea fiecărui modul se
recalculează normal în Retail.

Detaliile de navigare, autorizare și responsabilitățile router → service →
repository sunt în `APP_ARCHITECTURE.md`.

## Invariante esențiale

- `Cartele` și locațiile `TR %` sunt excluse din KPI-urile Retail normale;
- cantitățile sunt nete, astfel încât retururile reduc volumele;
- când există `site_code`, acesta domină filtrele istorice părinte;
- raportarea normală citește tabelele și view-urile `reporting_*`;
- importurile de vânzări rulează admin-only în worker și înlocuiesc atomic
  snapshotul lunar;
- uploadul Excel este transferat workerului prin spool local verificat SHA-256,
  nu ca payload binar în Valkey; coada de import este separată de operații;
- absența unui magazin din fișier nu modifică `stores.is_active`;
- activarea/dezactivarea magazinului este o operație separată și auditabilă;
- Grile check este read-only; sincronizarea targetelor este separată și
  privilegiată;
- finalizarea, arhivarea și resetul Grile sunt fail-closed pe coverage și
  manifest;
- salariile sunt protejate server-side, iar contractele publice folosesc
  `person_id`, nu CNP;
- `total_salary` include bonurile de masă, iar pragul de 2.000 RON se aplică
  numai mediilor;
- targetul agentului se alocă proporțional cu zilele de vânzare;
- un draft Calculator Target finalizat nu poate fi recalculat;
- bonurile promo calificate și cantitatea incentive sunt metrici distincte;
- vizitele se grupează după snapshotul Team Leader al autorului.

## Starea P0 istorică

Secțiunea descrie baseline-ul istoric `f9c0b1efe15686bcda532d22528e6e2644925aec`.
Identitatea candidatului curent este exclusiv SHA-ul exact din CI și provenance,
conform [`docs/README.md`](docs/README.md). Lotul P0 introduce garduri de date și state machines pentru vânzări, shadow
P&L/TVA și importul HR, împreună cu migrațiile aditive 032–034. Orice worker
care pierde lease-ul este fencing-uit, iar datele sunt promovate numai după
manifest, control totals, business hash și CAS.

P&L/TVA este în prezent numai dry-run/shadow: registry-ul effective-dated
folosește 1,19 înainte de 2025-08-01 și 1,21 de la 2025-08-01, dar nu există
activare live sau apply Finance. Actualele Finance, estimările și scenariile
Target finalizate nu se rescriu automat.

Importul salarial este fail-closed și cere ambele firme, CNP validat,
provenance și rollback tranzacțional. Importul live rămâne NO-GO până la
reconcilierea HR a celor 8 grupuri; nu se șterg sau repară automat datele
existente. Procedurile sunt în
[`docs/RUNBOOK-import-pnl-tva-P0.md`](docs/RUNBOOK-import-pnl-tva-P0.md) și
[`docs/RUNBOOK-import-salarii-HR.md`](docs/RUNBOOK-import-salarii-HR.md).

## Starea P1.1–P1.2 la SHA-ul documentat

Baseline-ul documentat este `82e8d49dd8f1856329546605f79e2d726b288323`.
Grile păstrează observațiile append-only și actualizează proiecția curentă
numai prin claim/CAS; un refresh stale rămâne auditabil, dar nu poate înlocui
un rezultat mai nou. Ultimul succes, ultima eroare și vârsta rezultatului sunt
stări separate, iar răspunsurile structural invalide sunt respinse fail-closed.

Promo validează și materializează configurația și sursele într-o generație
imutabilă, apoi mută atomic `data/promo_generations/current.json` numai dacă
pointerul nu s-a schimbat. Runtime-ul reverifică hashurile configurației și
surselor; o sursă lipsă sau alterată păstrează ultima generație bună. Concursul
declară explicit identitatea `site_agent` sau `person_id`; politica
`person_id` acceptă numai linkuri confirmate și nu unește implicit omonime.
Procedura completă este în
[`docs/RUNBOOK-campanii-promo-incentive-concursuri.md`](docs/RUNBOOK-campanii-promo-incentive-concursuri.md).

## Starea P1.3–P2 la release-ul v2.1.0

Migrarea aditivă 036 introduce registry-ul Target append-only. Scenariile noi
salvează rule-setul, hashurile și snapshotul de profitabilitate; GET/export nu
recitesc P&L sau forecast live. Allocatorul refuză bugete în afara
`sum(floor) <= buget <= sum(cap)` înainte de write. Scenariile legacy rămân
`legacy-unversioned`, fără backfill inventat.

Migrarea 051 adaugă autoritatea Planning pentru Insight: head per
lună/metrică/orizont, promotion/rollback cu revision CAS și ledger append-only.
Niciun run `completed` și niciun Target legacy fără snapshot exact nu este
publicat implicit; migrarea instalează contractul, dar nu promovează date live.
Migrarea 052 permite reader-ului Insight să execute numai funcția definer de
digest folosită de aceste view-uri; accesul la tabelele forecast brute rămâne
revocat.

Fiecare request Dashboard are un deadline monotonic unic, implicit 2.500 ms și
configurabil până la maximum 3.000 ms, creat înainte de rezolvarea poolului.
Acquire-urile și query-urile asyncpg primesc timpul rămas; copiii sunt anulați
și așteptați înainte de răspuns. `site_code` se canonizează o singură dată la
boundary, păstrând case și prima ordine. Calculator Target v2 acceptă numai
coverage forecast complet și uniform per magazin; lipsa/neuniformitatea
produce 409 înainte de orice scenariu sau revision write.

P2 adaugă faze fixe pentru Grile, raport PostgreSQL read-only, export XLSX
spooled/chunked, LCP/INP cu cardinalitate limitată și gate browser PWA
N -> N+1 -> rollback. Fereastra de 7 zile cu minimum 100 requesturi per rută
rămâne criteriu separat de acceptanță SLO în trafic real; nu este finding în
registrul tehnic M/R/N și nu blochează loturile P2/P3 definite în secțiunea 14
din planul tehnic 2026-08-04. Baseline-ul și limitele sunt în
[`docs/PERFORMANCE_REVIEW_2026-07-22.md`](docs/PERFORMANCE_REVIEW_2026-07-22.md).

## Setup local

Cerințe: Node.js 22, Python 3.12+ și Docker pentru testele PostgreSQL izolate.

```bash
cp .env.example .env
npm ci
python3 -m venv backend/venv
backend/venv/bin/pip install --require-hashes -r backend/requirements-dev.lock
npm run dev
npm run dev:backend
```

Producția instalează strict `backend/requirements.lock`; dezvoltarea și CI
folosesc supersetul `backend/requirements-dev.lock`. Fișierele `.txt` sunt
sursele editabile, iar lockfile-urile se regenerează cu Python 3.12 și
`pip-compile --generate-hashes` după orice schimbare de dependențe.

Folosește numai o bază locală dedicată. Instrucțiunile complete, inclusiv
configurația OIDC și protecțiile DB, sunt în `LOCAL_SETUP.md`.

Pachetele private `@unihub/*` sunt tarball-uri cu integritate verificată în
`vendor/npm/`. Un checkout curat și CI-ul PR nu folosesc Verdaccio, tokenuri de
registry sau rețeaua internă.

## Date și importuri

Fluxul standard al importului de vânzări:

1. validează antete, identificatori, valori numerice și metadate;
2. rezervă în PostgreSQL un singur snapshot `processing` cu token, owner și
   lease;
3. scrie generația în staging și persistă manifestul, coverage/diff și hashul
   business înainte de promovare;
4. claim-uiește atomic generația `validated` în `promoting`, cu fencing și CAS;
5. înlocuiește snapshotul și reconstruiește `reporting_*` în aceeași operație;
6. păstrează generația precedentă pentru rollback și șterge spoolul numai după
   stare terminală confirmată;
7. marchează snapshotul `completed` sau `failed`, fără stare parțială.

Interfața tolerează întreruperile temporare în verificarea jobului. Lipsa unei
confirmări de rețea este afișată ca stare necunoscută, nu ca import eșuat; doar
respingerea explicită din API sau eroarea confirmată de worker este eșec.

În `Setări -> Importuri`, raportul detaliat ERP poate fi încărcat și pentru o
verificare ocazională care nu importă și nu persistă fișierul. Aplicația citește
cutoff-ul din raport și compară Retail strict de la ziua 1 până la acea dată;
un raport 1–16 rămâne comparat cu 1–16 chiar dacă snapshotul curent conține deja
ziua 17. În variantele ERP în care `Locatii` conține numai procentele Focus,
valorile absolute lipsă sunt însumate din `Agenti` după `CodLocatie`. Dacă
valorile absolute există în ambele foi, totalurile lor trebuie să coincidă.
Promo și Incentive sunt afișate informativ, dar nu sunt declarate
reconciliate deoarece raportul agregat nu include granularitatea necesară.

Rândurile identice în coloanele disponibile nu sunt o cheie de unicitate:
exportul nu are ID stabil de linie, iar mai multe bucăți identice de pe același
bon pot apărea separat. Importul păstrează multiplicitatea; idempotency este
asigurată la nivel de fișier/coadă și prin înlocuirea atomică a snapshotului
lunar. Contractul complet este în ADR-004.

Configurațiile runtime din `data/`, fișierele Google și `.env*` sunt
neversionate și incluse în backupul operațional. Nu le copia în teste, loguri
sau documentație.

## Validare

Rulează secvențial:

```bash
node scripts/verify_vendored_npm_packages.mjs
backend/scripts/run_tests_isolated.sh
mypy backend/ --ignore-missing-imports --explicit-package-bases
npm run typecheck
npm run complexity:ts
npm run lint
npm run test
npm audit --omit=dev --audit-level=high
npm run build
npm run test:e2e
```

CI adaugă auditul dependențelor Python, detectarea secretelor, Bandit,
manifestul imutabil de migrații, verificarea systemd/Prometheus și proba de
izolare a runnerului PR.

## Deploy

Orice schimbare runtime urmează calea formală exact-SHA: branch/PR, CI verde,
merge, CI manual pe noul SHA `main`, artefact imutabil, digest verificat, deploy
workflow și probe. Serverul nu construiește din checkout și `main` nu este
folosit drept branch de dezvoltare.

Cererea explicită din conversația operațională autorizează agentul să execute
autonom întregul flux, inclusiv remedierea CI și deployul, dar nu autorizează
sărirea porților. Calea fără artefact rămâne numai pentru documentație
non-runtime; break-glass este limitat prin ADR-006.

Un run manual `CI` de pe `main` livrează artefactul numit după `head_sha`; acel
SHA și digestul publicat sunt singurele valori admise pentru deploy. Decizia
canonică este [`ADR-006`](docs/adr/006-verified-runtime-delivery.md), iar
mecanismul este documentat în `ops/README.md`.

## Documentație specializată

- campanii: `docs/RUNBOOK-campanii-promo-incentive-concursuri.md`;
- identitate bon: `docs/adr/003-receipt-identity.md`;
- identitate salarială și CNP: documentele `docs/engineering/h01*.md`;
- migrații: `docs/engineering/h02-immutable-migration-lifecycle.md` și
  `backend/db/migrations/README.md`;
- OIDC/sesiuni/rate limit: documentele `h04-h05`, `h06` și `h07`;
- acces privilegiat: `docs/engineering/h08-privileged-access-fail-closed.md`;
- integrarea Grile: `docs/grile-integration-plan.md`;
- Grile lunar: `docs/engineering/h11-grile-monthly-idempotency.md`;
- siguranță spreadsheet: `docs/engineering/h12-spreadsheet-formula-safety.md`;
- SLO și readiness: `docs/operations/retail-slo-readiness.md`;
- performanță: `docs/engineering/performance-baseline-v2.md`;
- organizare Retail: `docs/retail-org-analysis.md`.
