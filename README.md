# UniHub Retail

**Release curent:** `v2.0.1` — detalii și dovezi în
[`docs/releases/v2.0.1.md`](docs/releases/v2.0.1.md). Tagul istoric `v2.0.0`
rămâne nemodificat.

UniHub Retail este aplicația centrală pentru vânzări retail, targete, campanii,
salarii, P&L, raportarea vizitelor și interfața activă Grile.

## Surse canonice

- reguli de lucru și verificare: [`AGENTS.md`](AGENTS.md);
- arhitectură și contracte de business: [`APP_ARCHITECTURE.md`](APP_ARCHITECTURE.md);
- regula canonică pentru multiplicitatea rândurilor de vânzare:
  [`docs/adr/004-sales-row-multiplicity.md`](docs/adr/004-sales-row-multiplicity.md);
- instalare locală: [`LOCAL_SETUP.md`](LOCAL_SETUP.md);
- audit tehnic și riscuri rămase:
  [`docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md`](docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md);
- plan activ după `v2.0.1`:
  [`docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md`](docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md);
- plan activ de performanță și operativitate P0-P2:
  [`docs/PLAN_PERFORMANTA_OPERATIVITATE_2026-07-21.md`](docs/PLAN_PERFORMANTA_OPERATIVITATE_2026-07-21.md);
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
| Workeri | `unihub-worker.service` pentru operații și `unihub-import-worker.service` pentru importuri, fiecare serializat |
| Backend service | `unihub-backend.service` |
| Migrații | `unihub-retail-migrate.service`, one-shot |
| URL public | `https://retail.unihub.ro` |

Probe:

- `/livez` verifică numai procesul;
- `/readyz` verifică PostgreSQL și sesiunea Valkey;
- `/health` este alias compatibil pentru `/readyz`;
- `/metrics`, `/docs`, `/redoc` și `/openapi.json` nu sunt accesibile public.

## Module

- **Hub:** KPI retail, comparații, istoric și forecasturi AI persistate;
- **Focus:** Incentive, Promo, Concurs și Folii premium;
- **Agenți:** echipă, acoperire, Grile și evaluare;
- **Management:** manageri, Calculator Target, Salarii și P&L;
- **Setări:** importuri, exporturi și preferințe;
- **Vizite:** read model Retail peste sursa comună FieldOps.

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

## Setup local

Cerințe: Node.js 22, Python 3.12+ și Docker pentru testele PostgreSQL izolate.

```bash
cp .env.example .env
npm ci
python3 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt
npm run dev
npm run dev:backend
```

Folosește numai o bază locală dedicată. Instrucțiunile complete, inclusiv
configurația OIDC și protecțiile DB, sunt în `LOCAL_SETUP.md`.

Pachetele private `@unihub/*` sunt tarball-uri cu integritate verificată în
`vendor/npm/`. Un checkout curat și CI-ul PR nu folosesc Verdaccio, tokenuri de
registry sau rețeaua internă.

## Date și importuri

Fluxul standard al importului de vânzări:

1. validează antete, identificatori, valori numerice și metadate;
2. rezervă în PostgreSQL un singur snapshot `processing` pentru lună;
3. persistă coverage/diff agregat înainte de promovare;
4. actualizează metadatele numai pentru magazinele prezente, fără scriere de
   activitate;
5. înlocuiește snapshotul și reconstruiește `reporting_*` în aceeași operație;
6. marchează snapshotul `completed` sau `failed`, fără stare parțială.

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
npm run typecheck:strict
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

Fluxul implicit este autorizat de cererea explicită din conversația
operațională: implementare, verificări locale proporționale, commit direct pe
`main`, push fără a aștepta CI, deploy și verificare live. Push-ul direct este
acceptat pentru schimbări obișnuite; operatorul nu trebuie să repete aprobarea
în terminal. Dacă agentul deschide un PR, îl duce fără o nouă confirmare prin
CI, merge, deploy și verificare.

Pentru release-uri formale și schimbări cu risc mare rămâne disponibilă calea cu
PR, artefact CI imutabil, backup, migrații controlate, health local/public și
rollback compatibil. Alegerea căii este proporțională cu riscul. Decizia
canonică este [`ADR-005`](docs/adr/005-chat-authorized-delivery.md); mecanismul
formal este documentat în `ops/README.md` și
`docs/engineering/pr-runner-isolation.md`.

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
- organizare Retail: `docs/retail-org-analysis.md`;
- simularea grilei salariale: `docs/salary-grid-simulation.md`.
