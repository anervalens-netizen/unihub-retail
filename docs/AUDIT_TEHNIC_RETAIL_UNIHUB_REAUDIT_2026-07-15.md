# AUDIT TEHNIC INDEPENDENT — UniHub Retail

**Data auditului:** 2026-07-15
**Repository:** `anervalens-netizen/unihub-retail`
**Branch auditat:** `main`
**Commit de cod reconciliat și verificat live:** `964f6da07ad9e4382070866275509f3be2b399a1`
**Baseline live anterior programului:** `d08add17147d9f24b23642dbb1a0084708ff9307`
**Tip evaluare:** re-audit complet urmat de reconciliere și rollout `v2.0.1`
**Constatări inițiale:** **4 Critice, 57 Majore, 15 Minore — 76 total**
**Regulă de interpretare:** matricea de mai jos este starea curentă; descrierile
inițiale rămân păstrate ca istoric al riscului identificat pe `aba3fa0`.

> Actualizare 2026-07-16: PR #94 a adaugat citirea PostgreSQL, iar cutover-ul
> coordonat FieldOps/Retail a fost finalizat si verificat live. Retail citeste
> `fieldops_visits`; FieldOps citeste si scrie PostgreSQL. SQLite este arhiva
> pre-cutover. Aceasta actualizare prevaleaza peste descrierile istorice SQLite
> pastrate mai jos pentru trasabilitatea auditului.

## Verdict executiv

Cele patru riscuri critice inițiale sunt închise în codul `v2.0.1`:
importul nu mai deduce starea magazinelor din absență, verificarea Grile este
read-only, închiderea salarială este fail-closed, iar codul de pull request rulează
pe GitHub-hosted runners fără acces la hostul de producție. Patch-urile izolate
pentru cache, suprafața HTTP, Target Calculator și refresh-ul sesiunii sunt de
asemenea implementate și testate.

Problema dominantă a auditului inițial nu a fost o vulnerabilitate clasică de tip
SQL injection, ci **încrederea excesivă în fișiere și workflow-uri operaționale
fără validare de acoperire, separarea side effect-urilor și manifest de
integritate**. P0 corectează aceste căi pentru import, Grile și salarii; matricea
păstrează deschise domeniile în care același principiu nu este încă aplicat complet.

**Recomandare de release:** gate-urile operaționale pentru `v2.0.1` au fost
îndeplinite pe 2026-07-16: CI `main` verde, backup verificat, migrații 026-028,
approval one-time, artefact verificat, deploy, health local/public și rollback
compatibil demonstrat urmat de redeploy. Planul GitHub al repository-ului privat
nu permite required reviewers; controlul echivalent activ este host-side,
root-only, interactiv, one-time și legat de CI run/SHA/hash. Deployul manual care
ocolește acest boundary rămâne neacceptat.

## Metodă și independență

Acest raport nu reutilizează constatările, severitățile sau concluziile auditului anterior. Am recitit starea curentă a repository-ului și am evaluat independent:

- autentificarea OIDC/JWKS, sesiunea BFF, cookie-urile și CSRF;
- autorizarea generală și capabilitățile privilegiate;
- rate limiting și rezolvarea IP-ului;
- importurile Excel, master data, tranzacțiile și rebuild-ul reporting;
- Valkey/ARQ, workerul, idempotency și operațiile lunare Grile;
- salarii, target calculator, campanii, promo/incentive, P&L și exporturi;
- Dashboard, agregarea istorică, filtrele și cache-urile frontend/backend;
- vizitele SQLite/PostgreSQL și fotografiile;
- scripturile AI Forecast;
- schema, migrațiile și rolurile DB;
- CI, SAST, dependency audit, coverage, Playwright și systemd;
- capturile mobile furnizate de utilizator.

Reconcilierea a inspectat repository-ul local, worktree-urile, baza PostgreSQL în
mod read-only, serviciile systemd, health-ul local/public, setările și runnerii
GitHub, PR-urile și logurile CI. Testele grele au fost executate secvențial local,
apoi pe merge-ref și pe `main`. Pe stiva finală de cod, suita locală a avut 1.250
teste trecute și 9 skip, coverage total 99%, `services/grile_monthly.py` 98,23%,
`services/importer.py` 95,98% și Target Calculator 100%. Runurile GitHub relevante
sunt păstrate în dovada de release. După eliminarea a două wrapper-e experimentale
nefolosite, Bandit a trecut cu baseline-ul real de **16** constatări Medium; înainte
de curățenie erau 17, nu 111.

## Definiția severităților

- **Critic:** poate produce compromitere de infrastructură, corupere extinsă a datelor, modificări neautorizate cu impact financiar sau pierdere ireversibilă a sursei.
- **Major:** poate produce expunere de date, rezultate financiare greșite, indisponibilitate, race conditions, degradare severă la scalare sau control operațional insuficient.
- **Minor:** defect real, dar cu impact local, UX, hardening sau datorie tehnică limitată.

---

# Matrice de reconciliere pe `964f6da`

`Închis în cod` înseamnă că implementarea și testele sunt prezente în release;
`Închis și activ` confirmă și rolloutul. `Parțial` și `Deschis` rămân riscuri
reziduale și nu sunt prezentate drept remediate.

## Critice

| ID | Stare | Dovadă curentă exactă |
|---|---|---|
| C-01 | **Închis și activ** | PR #96 / `9b5d17c`, cu dovada PostgreSQL completată în PR #101 / `6dafc72`; `backend/services/importer.py::{load_sales_dataframe,build_import_coverage_report,upsert_stores}`, `backend/repositories/stores.py::StoresRepository.change_activity`, migrarea 026 și `backend/tests/test_import_master_data_safety.py`. |
| C-02 | **Închis și activ** | PR #97 / `96b9a0d`; `backend/routers/grile.py`, joburile separate din `backend/worker.py`, `backend/services/grile_agent_targets.py`, migrarea 027 și testele `test_grile_target_sync_api.py`, `test_grile_target_sync_safety.py`, `test_grile_run_reservations.py`. |
| C-03 | **Închis și activ** | PR #98 / `0a984a1`; `backend/services/grile_monthly.py`, `backend/services/grile_monthly_integrity.py`, migrarea 028 și suitele `test_grile_monthly_fail_closed_api.py`, `test_grile_monthly_operations.py`, `test_grile_monthly_service.py`. |
| C-04 | **Închis și activ** | PR #95 / `a055b85`, cu proba de rețea întărită în PR #101 / `6dafc72`; toate joburile PR folosesc `ubuntu-24.04`, iar `runner-isolation` respinge orice răspuns HTTP direct de la peer-ul TimesFM, inclusiv 401/403/404, fără proxy. Pachetele private sunt vendored și verificate; vechiul runner persistent de PR a fost eliminat, iar singurul runner self-hosted rămas este `unihub-retail-deploy`, dedicat deployului și fără acces PR. |

## Majore

| ID | Stare | Dovadă curentă exactă |
|---|---|---|
| M-01 | **Închis în cod** | PR #99 / `05387f9`; `backend/main.py::SecurityHeadersMiddleware` setează `private, no-store` și controalele CDN pentru `/api/*`, `/salarii` și sesiune; `backend/tests/test_http_surface_security.py`. |
| M-02 | **Deschis** | `backend/services/grile_monthly.py::build_google_services` păstrează aceeași identitate Google pentru citire/export/reset; separarea service account-urilor este încă P1. |
| M-03 | **Închis în cod** | `backend/services/grile_monthly.py::retry_api` execută retry bounded pentru batchGet, export, clear și restore; regresiile 429/503/timeout sunt în `backend/tests/test_grile_monthly_service.py`. |
| M-04 | **Închis în cod** | `_archive_month_execution` respinge `only` cu `partial_archive_forbidden`, iar resetul live parțial este interzis; `test_archive_requires_full_verified_finalization` și testele API fail-closed. |
| M-05 | **Deschis** | `backend/services/grile_monthly.py` păstrează artefacte locale fără o politică automată completă de retenție/criptare; manifestele și hash-urile reduc integritatea, nu rezolvă retenția. |
| M-06 | **Deschis** | Ramurile fail-open rămân în `backend/services/campaigns.py` pentru promo/incentive; nu au fost modificate de PR-urile `v2.0.1`. |
| M-07 | **Deschis** | Contractele de dată din `backend/routers/campaigns.py` și `backend/services/campaigns.py` nu au fost unificate. |
| M-08 | **Deschis** | Parsarea promo rămâne în `backend/services/imports.py` pe calea requestului web. |
| M-09 | **Deschis** | Actualizarea configurației promo din `backend/services/imports.py` rămâne file-based fără CAS/lock durabil. |
| M-10 | **Deschis** | `backend/services/imports.py` limitează uploadul comprimat, dar nu are încă buget complet pentru membri ZIP/decompresie/celule. |
| M-11 | **Închis în cod** | `load_sales_dataframe` respinge valori monetare/cantități nefinite, fracționare sau out-of-range; `test_load_sales_dataframe_rejects_invalid_numeric_values`. |
| M-12 | **Închis în cod** | Identificatorii obligatorii, inclusiv bonul pentru rândurile incluse, sunt validați strict în `load_sales_dataframe`; `test_load_sales_dataframe_rejects_missing_required_identifier`. |
| M-13 | **Închis în cod** | Duplicatele de header și de rând sunt respinse înainte de staging; `test_load_sales_dataframe_rejects_duplicate_rows` și `test_load_sales_dataframe_rejects_duplicate_raw_excel_headers`. |
| M-14 | **Închis în cod** | Metadatele multiple pentru același `SiteCode` produc eroare în `load_sales_dataframe`; `test_load_sales_dataframe_rejects_conflicting_store_metadata`. |
| M-15 | **Închis în cod pentru aceeași lună** | Lease-ul PostgreSQL și retry-ul concurent sunt verificate în `backend/tests/test_import_reservations.py`; fișierul complet, 90%, o singură firmă, conflictele și duplicatele sunt acoperite în `test_import_master_data_safety.py`; migrarea 026 păstrează auditul coverage. |
| M-16 | **Deschis** | Payloadul de import Excel circulă încă prin mecanismul existent din `backend/services/jobs.py` și `backend/worker.py`; spool/object storage rămâne P1. |
| M-17 | **Deschis** | `backend/worker.py::WorkerSettings.max_jobs` rămâne 1; serializarea protejează resursele, dar este un bottleneck. |
| M-18 | **Deschis** | Pașii derivați din `backend/worker.py::process_sales_import_job` nu au încă outbox/retry durabil complet. |
| M-19 | **Deschis** | Cache-ul local din `backend/services/filter_options.py` rămâne per proces. |
| M-20 | **Deschis** | Semantica indisponibilității ARQ din `backend/services/jobs.py` nu a fost schimbată în `v2.0.1`. |
| M-21 | **Deschis** | `backend/services/exports.py::preview_export` construiește încă raportul înainte de limitarea preview-ului. |
| M-22 | **Deschis** | Workbook-urile sunt construite în memorie în `backend/services/exports.py`; răspunsul nu este streaming incremental real. |
| M-23 | **Deschis** | Calea incentive din `backend/services/exports.py` păstrează modelul de achiziție DB existent. |
| M-24 | **Deschis** | Limitele pentru liste/dimensiuni/luni din `backend/routers/exports.py` nu au fost uniformizate. |
| M-25 | **Deschis** | `backend/services/exports.py` și `backend/services/campaigns.py` importă în continuare helperi privați Dashboard. |
| M-26 | **Deschis** | `backend/routers/visits_report.py::visits_tree` nu impune încă interval/cursor obligatoriu. |
| M-27 | **Închis și verificat live** | Retail folosește repository-ul PostgreSQL `fieldops_visits`; rapoartele lunare martie-iulie, arborele, detaliile, snapshotul și CRM au fost comparate cu arhiva SQLite înainte de cutover. |
| M-28 | **Deschis** | Scope-ul read general din `backend/main.py`/`backend/permissions.py` rămâne tenant-wide pentru modulele non-management. |
| M-29 | **Deschis** | `backend/routers/visits_report.py` validează path-ul fotografiei, dar nu leagă încă fișierul de vizită și scope organizațional. |
| M-30 | **Deschis** | `backend/scripts/provision_runtime_database_role.py` păstrează granturile generale; migrările 026-028 adaugă numai granturile necesare noilor tabele. |
| M-31 | **Închis și verificat live** | `/metrics` rămâne intenționat pentru scrape intern în `backend/main.py`; stansa Retail din proxy răspunde public 404 pentru `/metrics`, `/docs`, `/redoc` și `/openapi.json`, iar health-ul intern rămâne verde. Nu au fost modificate Caddy global, Authentik, DNS, Astra sau Dell. |
| M-32 | **Reformulat; guvernanță deschisă** | `100.74.73.114` este peer Tailscale: traficul overlay este criptat chiar dacă aplicația folosește HTTP intern. Riscul rămas în `backend/scripts/run_ai_forecast_xreg.py` este guvernanța peer-ului, autorizarea, minimizarea payloadului, rotația cheii și contractul procesatorului, nu transport plaintext pe internet. |
| M-33 | **Închis în cod** | PR #99; `backend/session_auth.py` folosește owner timeout 55s sub lease tokenizat 60s, wait bounded, compare-delete pentru lock/sesiune și 503 pe incertitudine; `backend/tests/test_session_auth.py`. |
| M-34 | **Deschis** | `backend/main.py::lifespan` și health-ul păstrează dependența de ARQ la startup. |
| M-35 | **Parțial închis** | `backend/services/visits_sync.py` reconstruiește tranzacțional proiecția din autoritatea PostgreSQL la startup; un refresh incremental separat rămâne o optimizare, nu o contradicție între surse. |
| M-36 | **Deschis** | Validarea lunilor/filtrelor rămâne distribuită între routerele Dashboard, Agents, CRM, Visits și Salarii. |
| M-37 | **Închis în cod** | `backend/repositories/target_calculator.py::update_final_targets` verifică întregul set înainte de `executemany`; testul PostgreSQL `test_postgres_invalid_site_code_rolls_back_entire_target_batch`. |
| M-38 | **Deschis** | `src/components/dashboard/useDashboardData.ts` păstrează fan-out-ul istoric multi-lună. |
| M-39 | **Deschis** | Agregarea multi-lună din `src/components/Dashboard.tsx` nu a primit o remediere dedicată în `v2.0.1`. |
| M-40 | **Deschis** | Read-urile grele din routerele Dashboard/Agents/Visits nu au încă buget de query și rate limit uniform. |
| M-41 | **Închis în cod** | `backend/main.py::spa_fallback_allowed` permite numai GET/HEAD cu `Accept: text/html` și exclude API/auth/health/docs/metrics/salarii/assets; `test_http_surface_security.py`. |
| M-42 | **Deschis** | Politica CSP din `backend/main.py::SecurityHeadersMiddleware` nu a fost reconciliată cu endpointul frontend de telemetrie. |
| M-43 | **Deschis** | `src/components/SalariiSubtab.tsx` păstrează modelul de fetch anterior; nu există test nou pentru răspuns stale sub filtre schimbate. |
| M-44 | **Deschis** | `src/api/client.ts` nu are încă timeout/AbortController global. |
| M-45 | **Deschis** | Bootstrap-ul lunilor din `src/App.tsx` păstrează fallback-ul anterior. |
| M-46 | **Deschis** | `src/components/MainLayout.tsx` continuă să transforme unele erori de opțiuni în stare goală. |
| M-47 | **Închis în redesign** | `src/index.css` aplică safe-area pentru bottom nav și poziționează filtrul deasupra sa; `src/components/MainLayout.tsx` are padding de conținut, iar `e2e/mobile-responsive.spec.ts` verifică viewport 390x844 și overflow zero. |
| M-48 | **Deschis** | Sheet-ul din `src/components/MainLayout.tsx` nu are încă `role=dialog`, `aria-modal`, focus trap și restore focus. |
| M-49 | **Închis** | `e2e/mobile-responsive.spec.ts` rulează explicit la 390x844; gate-ul CI rulează Playwright secvențial și accessibility smoke. |
| M-50 | **Deschis** | `e2e/helpers.ts` mock-uiește încă API-ul; acceptanța full-stack rămâne separată de E2E-ul frontend. |
| M-51 | **Deschis** | `tsconfig.strict.json` rămâne selectiv și politica ESLint permite încă warnings configurate. |
| M-52 | **Corectat factual; risc rezidual deschis** | `.bandit-baseline.json` conține **16** rezultate Medium după eliminarea wrapper-elor experimentale nefolosite (17 înainte de curățenie, nu 111). CI impune praguri critice pe 16 module, dar coverage-ul nu este încă global pentru tot backendul/frontendul. |
| M-53 | **Deschis** | Unitățile systemd rulează încă sub utilizatorul uman configurat; izolarea runnerului nu schimbă identitatea serviciilor. |
| M-54 | **Deschis** | Backendul/workerul rămân single-host/single-process conform unităților systemd. |
| M-55 | **Deschis** | `backend/requirements.txt` nu este un lock cu hash-uri complet reproductibil. |
| M-56 | **Închis și verificat live** | `.github/workflows/deploy.yml` verifică runul `main`, SHA-ul și hashurile artefactului. `ops/approve-retail-release.sh` creează approval root-only, interactiv, valabil 30 de minute și legat de run/SHA/hash; `ops/deploy-retail-artifact.sh` îl consumă atomic și refuză lipsa, expirarea, reutilizarea, duplicatele și mismatch-ul. Runnerul dedicat a executat deployurile `29489754125` și `29489997636`; rollbackul compatibil a fost demonstrat între ele, iar rollbackul către un manifest istoric incompatibil este refuzat înainte de oprirea serviciilor. |
| M-57 | **Deschis** | `backend/services/grile_monthly.py`, exports și componentele mari frontend rămân monoliți, deși integritatea salarială a fost extrasă în `grile_monthly_integrity.py`. |

## Minore

| ID | Stare | Dovadă curentă exactă |
|---|---|---|
| m-01 | **Închis în cod** | `FastAPI(..., docs_url=None, redoc_url=None, openapi_url=None)` și `test_docs_are_disabled_and_api_responses_are_private_no_store`. |
| m-02 | **Deschis** | Handlerul din `backend/main.py` păstrează path-ul requestului în logul de excepție. |
| m-03 | **Deschis** | Exportul salarial din `backend/routers/salarii.py` nu are încă un audit server-side complet independent de client. |
| m-04 | **Deschis** | `backend/services/retail_metrics.py` păstrează luna calendaristică a serverului și refresh-ul rar. |
| m-05 | **Deschis** | `src/components/Settings.tsx` afișează „drag & drop”, dar inputul implementează numai click/selectare. |
| m-06 | **Deschis** | `promoActualsMessage` din `src/components/Settings.tsx` este stilizat succes inclusiv pentru textul de eroare. |
| m-07 | **Deschis** | Polling-ul din `src/components/Settings.tsx` nu are încă anulare explicită la unmount. |
| m-08 | **Deschis** | Barele cu `Cell` din `HistoryDashboard.tsx` nu expun un payload de legendă care să reprezinte distinct real/forecast. |
| m-09 | **Deschis** | Tooltip-ul Recharts din `HistoryDashboard.tsx` rămâne implicit pe mobil. |
| m-10 | **Deschis** | Animațiile Framer Motion din `MainLayout.tsx` nu consultă încă `prefers-reduced-motion`. |
| m-11 | **Deschis** | Filtrele din `src/App.tsx` rămân persistate local fără namespacing per subiect OIDC. |
| m-12 | **Deschis** | Regulile forecast rămân constante în `backend/scripts/run_ai_forecast_xreg.py`. |
| m-13 | **Deschis** | Terminologia `Vanzari`/`Vânzări` și formatarea nu au fost uniformizate complet. |
| m-14 | **Deschis** | Fallback-ul labelului HTTP din middleware poate folosi în continuare path brut. |
| m-15 | **Deschis, impact redus prin izolarea CI** | `pip-audit` și `npm audit --omit=dev` nu acoperă întreg toolchain-ul dev; codul respectiv rulează acum pe VM GitHub-hosted efemer, nu pe producție. |

---

# Constatări Critice

### C-01 — Un import de vânzări incomplet poate închide logic magazine valide
**Severitate:** Critic
**Categorie:** Corectitudine / integritatea datelor / operațional
**Locație exactă:** `backend/services/importer.py:120-128`, `backend/services/importer.py:147-206`

**Ce este greșit**

Importul elimină mai întâi toate rândurile fără ASM valid, apoi tratează lista de
`SiteCode` rămasă drept fotografie completă a structurii curente. Dacă luna
importată este cel puțin la fel de nouă ca ultima lună finalizată, toate magazinele
active care lipsesc din fișier sunt marcate `is_active=false`.

Nu există un contract explicit de „snapshot complet”, o verificare de acoperire
față de master data, prag de variație, etapă de staging, aprobare umană sau
reconciliere înainte de promovarea importului.

**Impact concret**

Un export parțial, un fișier filtrat pe o singură firmă, o extracție întreruptă sau
o eroare în coloana ASM poate dezactiva în masă magazine reale. Efectul se propagă
în filtre, cohortele istorice, forecast, targete, rapoarte salariale, P&L și orice
query care folosește `stores.is_active`. Aplicația poate afișa totaluri „corecte”
matematic pe un univers de magazine deja corupt.

**Fix recomandat**

Rescrie fluxul ca import în două faze:

1. încarcă fișierul într-un staging imutabil;
2. validează schema, totalurile, numărul de magazine și diferențele de master data;
3. afișează explicit magazinele noi, lipsă și realocate;
4. cere o promovare separată, autorizată și auditabilă;
5. nu deduce niciodată închiderea unui magazin doar din absența sa dintr-un fișier
   operațional;
6. mută închiderea într-un workflow dedicat, cu motiv, dată efectivă și rollback.

**Verificare obligatorie**

Test obligatoriu: importă intenționat un fișier care conține 90% din magazine și
dovedește că niciun magazin nu este dezactivat. Promovarea trebuie blocată până la
acceptarea explicită a diferenței. Adaugă un test PostgreSQL de regresie și un
raport de reconciliere înainte/după.

---

### C-02 — Orice utilizator autentificat poate declanșa un „check” Grile care scrie targete
**Severitate:** Critic
**Categorie:** Autorizare / corectitudine / efecte ascunse
**Locație exactă:** `backend/routers/grile.py:37-58`, `backend/worker.py:74-106`

**Ce este greșit**

Endpointul `/api/grile/run` cere doar autentificare și rate limit. Jobul rezultat
rulează `run_grile_check`, după care execută
`sync_agent_targets_from_grile(..., apply=True)`. Operația prezentată ca verificare
read-only produce de fapt o scriere business în `agent_targets`.

Separarea dintre „verifică” și „aplică” nu există la granița de autorizare.

**Impact concret**

Orice cont valid din tenant poate provoca modificarea targetelor agenților, chiar
dacă acel cont nu are voie să administreze Grile sau targete. Auditul de acces
devine înșelător, deoarece mutația este ascunsă într-un job pornit de un endpoint
aparent neprivilegiat.

**Fix recomandat**

Separă fluxurile:

- `/run` trebuie să fie strict read-only și să folosească `apply=False`;
- sincronizarea targetelor trebuie să aibă endpoint/job distinct;
- sincronizarea trebuie protejată cu grup OIDC dedicat sau cu aceeași capabilitate
  privilegiată folosită pentru operațiile lunare;
- persistă subiectul OIDC, tipul operației, diff-ul și rezultatul;
- interzice orice side effect în serviciul de verificare.

**Verificare obligatorie**

Test de autorizare: un utilizator autentificat fără grupul dedicat poate rula
verificarea, dar numărul și valorile din `agent_targets` rămân identice. Același
utilizator primește 403 la sincronizare. Un utilizator privilegiat produce un diff
auditabil.

---

### C-03 — Finalizarea salariilor poate reuși cu date lipsă sau invalide, apoi sursele pot fi resetate
**Severitate:** Critic
**Categorie:** Corectitudine financiară / pierdere de date / operațional
**Locație exactă:** `backend/services/grile_monthly.py:516-534`, `backend/services/grile_monthly.py:541-621`, `backend/services/grile_monthly.py:665-755`, `backend/services/grile_monthly.py:876-943`, `backend/services/grile_monthly.py:1053-1144`

**Ce este greșit**

Conversia numerică transformă valori neparsabile în `0.0`. Citirea unui magazin
prinde orice excepție și întoarce un rând `ERROR`, iar agenții cu celulă goală sunt
pur și simplu omişi. Generatorul workbook-ului exclude rândurile cu eroare din
foile principale, dar scrie totuși fișierul final. Operația `finalize` nu blochează
succesul când există magazine sau agenți lipsă.

La reset, existența unui fișier final nevid este folosită ca dovadă suficientă că
finalizarea este validă. Nu există manifest obligatoriu cu numărul așteptat de
magazine/agenți, hash-uri, totaluri și aprobarea finală.

**Impact concret**

Un salariu invalid poate deveni zero, un agent poate dispărea din export și un
magazin cu eroare poate fi omis, în timp ce operația este raportată ca reușită.
Ulterior, resetul poate șterge intervalele din Google Sheets care reprezentau
sursa operațională. Rezultatul este subplată, export financiar incomplet și
pierderea dovezii necesare pentru reconstrucție.

**Fix recomandat**

Fă fluxul fail-closed:

- orice celulă numerică invalidă trebuie să producă eroare, nu zero;
- definește numărul așteptat de magazine și agenți înainte de citire;
- blochează finalizarea la orice eroare, diferență de acoperire sau rând ambiguu;
- generează un manifest semnat/hash-uit cu surse, număr de rânduri, totaluri,
  erori zero și checksum pentru workbook;
- resetul trebuie să accepte numai un manifest verificat și aprobat;
- păstrează o copie imutabilă a sursei și a rezultatului înainte de reset.

**Verificare obligatorie**

Teste obligatorii: valoare text într-o celulă numerică, agent lipsă, magazin cu
timeout Google, magazin neașteptat și workbook parțial. Toate trebuie să lase
operația în `failed`, să nu creeze un artefact „final” eligibil și să interzică
resetul.

---

### C-04 — CI pentru pull request rulează cod arbitrar pe un runner self-hosted persistent
**Severitate:** Critic
**Categorie:** Supply chain / CI/CD / infrastructură
**Locație exactă:** `.github/workflows/ci.yml:18-43`, `.github/workflows/ci.yml:80-91`, `.github/workflows/ci.yml:147-179`

**Ce este greșit**

Ambele joburi de PR rulează pe `[self-hosted, unihub-server]`. Workflow-ul
instalează dependențe Python și Node controlate de repository și pornește un
container Docker pentru validarea Prometheus. Un pull request poate modifica
scripturile, lockfile-urile și comenzile executate.

Repository-ul nu conține dovada că runnerul este efemer, izolat de producție,
fără acces la Docker socket, fără secrete și fără acces la rețeaua internă.
Denumirea `unihub-server` indică un host persistent; severitatea rămâne Critică
până când izolarea este demonstrată în configurația GitHub și a hostului.

**Impact concret**

Un contributor compromis, un token furat sau un PR malițios poate obține execuție
de cod pe runner. Dacă runnerul este hostul de producție sau are acces la rețeaua,
fișierele ori credențialele producției, compromiterea CI devine compromiterea
aplicației, bazei de date și serviciilor interne.

**Fix recomandat**

Mută PR validation pe GitHub-hosted runners sau pe runneri efemeri creați pentru
un singur job. Runnerii de deploy trebuie separați, protejați prin environment
approvals și fără execuție pe cod de PR neverificat. Elimină accesul la Docker
socket, montează filesystem read-only, blochează egress-ul intern și rotește orice
secret care a fost disponibil runnerului persistent.

**Verificare obligatorie**

Criteriu de acceptare: un job de PR nu poate accesa IP-urile interne, fișierele
producției, metadata cloud, Docker socket sau secretele de deployment. Runnerul se
distruge după job. Un test controlat de izolare trebuie păstrat ca dovadă.

---


# Constatări Majore

### M-01 — Răspunsurile salariale nu primesc antete explicite `no-store`
**Severitate:** Major
**Categorie:** Confidențialitate / cache
**Locație exactă:** `backend/routers/salarii.py:18-21`, `backend/main.py:180-191`

**Ce este greșit**

API-ul salarial este expus sub prefixul `/salarii`, însă middleware-ul aplică
politica `Cache-Control: no-cache, no-store, must-revalidate` numai pentru
`/api/*`, documente HTML și câteva fișiere PWA. Răspunsurile cu nume și valori
salariale nu au o politică explicită de cache.

**Impact concret**

Browserul, BFCache-ul sau un proxy configurat greșit poate păstra date salariale
după logout ori pe un dispozitiv comun. Lipsa unei politici defensive este
inacceptabilă pentru date HR.

**Fix recomandat**

Aplică pentru toate rutele autentificate sensibile:
`Cache-Control: private, no-store, max-age=0`, `Pragma: no-cache`,
`Vary: Cookie, Authorization` și bypass explicit în CDN/reverse proxy. Acoperă
`/salarii`, `/api/store-pnl`, exporturile și fotografiile de vizită.

**Verificare obligatorie**

Test HTTP automat pe fiecare endpoint sensibil: antetul trebuie să existe atât la
200, cât și la 4xx/5xx. Verifică și configurația proxy/CDN.

---

### M-02 — Contul Google pentru Grile are scope-uri prea largi și amestecă citirea cu ștergerea
**Severitate:** Major
**Categorie:** Securitate / least privilege
**Locație exactă:** `backend/services/grile_monthly.py:64-67`, `backend/services/grile_monthly.py:183-207`

**Ce este greșit**

Același service account este folosit pentru citirea salariilor, exportul fișierelor
și resetarea destructivă, cu scope complet pentru Google Sheets și Google Drive.
Codul nu separă identitatea read-only de identitatea care poate modifica foi.

**Impact concret**

Compromiterea credențialului permite citirea, modificarea sau exportul tuturor
resurselor Google partajate cu acel cont, nu doar a foii necesare operației curente.
O eroare de cod în fluxul read-only deține aceeași putere ca resetul.

**Fix recomandat**

Creează service account-uri distincte: unul read-only pentru finalizare/arhivare și
unul de write dedicat resetului. Folosește scope-urile minime, partajează numai
folderele/foile necesare și păstrează credențialele separat. Resetul trebuie să
necesite capabilitate, aprobare și identitate de serviciu distinctă.

**Verificare obligatorie**

Revizuiește lista reală de fișiere accesibile fiecărui cont. Testul read-only
trebuie să demonstreze că nu poate executa `batchClear`.

---

### M-03 — Retry-ul pentru exportul arhivei Grile nu execută niciun retry real
**Severitate:** Major
**Categorie:** Corectitudine / reziliență
**Locație exactă:** `backend/services/grile_monthly.py:758-787`, `backend/services/grile_monthly.py:832-846`

**Ce este greșit**

`export_sheet_xlsx` prinde orice excepție și întoarce un dicționar cu
`status=ERROR`. Funcția este apoi trecută prin `retry_api`, dar wrapperul repetă
numai când funcția aruncă excepție. Deoarece excepția a fost deja absorbită, un
timeout sau un 503 Google este încercat o singură dată.

**Impact concret**

O problemă tranzitorie produce o arhivă incompletă și blochează închiderea lunii,
deși mecanismul pare configurat pentru retry. Operatorul primește o falsă impresie
de reziliență.

**Fix recomandat**

Lasă erorile tranzitorii să se propage către `retry_api` sau modifică wrapperul să
interpreteze rezultatul. Reîncearcă numai codurile tranzitorii, cu jitter, deadline
total și metrici per încercare.

**Verificare obligatorie**

Simulează 503 la primele două apeluri și succes la al treilea; rezultatul final
trebuie să fie OK, iar numărul de apeluri exact trei.

---

### M-04 — Filtrul `only` este substring și poate produce arhive/resetări parțiale sub numele oficial al lunii
**Severitate:** Major
**Categorie:** Corectitudine / operații destructive
**Locație exactă:** `backend/services/grile_monthly.py:291-330`, `backend/services/grile_monthly.py:790-873`, `backend/services/grile_monthly.py:929-1049`

**Ce este greșit**

Filtrarea `only` caută un substring în companie, magazin, cod și manager. O valoare
generică poate selecta mai multe magazine fără ca operatorul să observe. Fluxurile
archive/reset acceptă această selecție, iar artefactele folosesc directoarele și
numele oficiale ale lunii, nu un namespace de test/retry.

**Impact concret**

O operație destinată unui singur magazin poate afecta mai multe foi. O arhivă
parțială poate suprascrie manifestul sau fișierul oficial și poate fi confundată cu
arhiva completă.

**Fix recomandat**

Înlocuiește substringul cu o listă exactă de `site_code`. Afișează și confirmă
numărul/identitatea magazinelor înainte de enqueue. Orice rulare parțială trebuie
scrisă într-un namespace separat și nu poate satisface precondițiile resetului
oficial.

**Verificare obligatorie**

Testează valori ambigue și dovedește că numai codurile exacte sunt selectate.
Artefactele parțiale nu trebuie să modifice manifestul complet.

---

### M-05 — Artefactele salariale Grile nu au retenție, criptare sau streaming real
**Severitate:** Major
**Categorie:** Confidențialitate / operațional / performanță
**Locație exactă:** `backend/services/grile_monthly.py:69-72`, `backend/services/grile_monthly.py:226-251`, `backend/services/grile_monthly.py:1147-1162`

**Ce este greșit**

Workbook-urile finale, fișierele per magazin, ZIP-urile pe manager și manifestele
sunt păstrate în filesystem fără politică de expirare în cod. Downloadul citește
întreg fișierul în memorie înainte de răspuns.

**Impact concret**

Datele salariale rămân pe disc pe termen nedefinit și măresc suprafața de
exfiltrare. Arhivele mari produc spike-uri de memorie în backend și pot bloca
procesul unic.

**Fix recomandat**

Definește retenție explicită, ștergere verificabilă, permisiuni dedicate și
criptare la nivel de storage/backup. Servește prin `FileResponse` sau streaming din
fișier, cu limită de mărime și audit server-side.

**Verificare obligatorie**

Testează expirarea, permisiunile OS, restaurarea controlată și consumul de memorie
la un ZIP mare.

---

### M-06 — Calculele promo/incentive sunt fail-open și pot subraporta promo sau supraevalua plata
**Severitate:** Major
**Categorie:** Corectitudine financiară
**Locație exactă:** `backend/services/campaigns.py:104-125`, `backend/services/campaigns.py:394-413`, `backend/services/campaigns.py:526-547`

**Ce este greșit**

Dacă segmentul de după cutoff eșuează, serviciul returnează doar actualul POS și
ascunde eroarea. Erorile pentru promoțiile suplimentare și pentru intersecțiile
multi-perioadă sunt de asemenea ignorate, iar excluderile lipsă nu mai reduc
cantitatea eligibilă la incentive.

**Impact concret**

Promoția poate fi subraportată, iar incentive-ul poate fi plătit pentru unități care
trebuiau excluse. Rezultatul financiar rămâne aparent valid, fără indicator de
incompletitudine.

**Fix recomandat**

Pentru orice calcul financiar, o sursă lipsă sau un calcul eșuat trebuie să producă
stare `incomplete/error`, nu fallback tăcut. Persistă proveniența și completitudinea
pe promoție/perioadă și interzice exportul/plata când setul de excluderi nu este
complet.

**Verificare obligatorie**

Fault-injection pe fiecare promoție și perioadă: răspunsul trebuie să indice eroare,
iar plata/exportul să fie blocat.

---

### M-07 — Contractul de dată pentru promoții permite 500 și perioade ambigue
**Severitate:** Major
**Categorie:** Validare input / corectitudine
**Locație exactă:** `backend/services/campaigns.py:248-265`, `backend/routers/campaigns.py:44-85`

**Ce este greșit**

`start_date` și `end_date` sunt stringuri transformate direct cu
`date.fromisoformat`. Nu există validare Pydantic comună, verificare `end >= start`
sau contract clar pentru intervale care traversează mai multe luni. Luna de
business este derivată din începutul intervalului.

**Impact concret**

Inputul invalid poate ajunge 500 în loc de 422. Un interval cross-month poate
combina configurația unei luni cu vânzări din altă lună și produce rezultate
contradictorii.

**Fix recomandat**

Folosește tipuri `date` și un model de request cu validator de ordine. Limitează
explicit intervalul la o singură campanie/lună sau implementează agregarea
multi-lună în mod declarat.

**Verificare obligatorie**

Teste 422 pentru format invalid, interval inversat și interval cross-month
neacceptat.

---

### M-08 — Parsarea raportului promo Excel blochează singurul event loop web
**Severitate:** Major
**Categorie:** Performanță / disponibilitate
**Locație exactă:** `backend/services/imports.py:92-124`, `backend/services/imports.py:189-225`, `ops/systemd/unihub-backend.service:16`

**Ce este greșit**

`pandas.read_excel` și procesarea DataFrame rulează sincron în coroutine-ul
FastAPI. Backendul de producție pornește un singur worker Uvicorn.

**Impact concret**

Un fișier mare sau dificil blochează toate requesturile autentificate pe durata
parsării. Un administrator poate produce involuntar indisponibilitate pentru toată
aplicația.

**Fix recomandat**

Mută validarea și importul în worker sau cel puțin în `asyncio.to_thread`, cu
deadline, limite de resurse și stare de job. Backendul web trebuie să facă doar
upload/spooling și enqueue.

**Verificare obligatorie**

Test de încărcare: în timpul parsării unui fișier maxim, `/livez` și un endpoint
read trebuie să rămână responsive.

---

### M-09 — Actualizarea JSON a promoțiilor are lost-update race
**Severitate:** Major
**Categorie:** Race condition / consistență
**Locație exactă:** `backend/services/imports.py:125-171`

**Ce este greșit**

Două importuri concurente citesc același JSON, îl modifică în memorie și îl
înlocuiesc prin același nume temporar. Nu există lock distribuit, versiune, compare
and swap sau tranzacție.

**Impact concret**

Ultimul writer șterge modificările primului, iar fișierul temporar comun poate
produce erori de replace. Configurația promo devine nedeterministă.

**Fix recomandat**

Mută configurația operațională în PostgreSQL, cu revizie și tranzacție. Dacă JSON-ul
rămâne temporar, folosește lock inter-proces, temp file unic, fsync și verificare de
versiune înainte de replace.

**Verificare obligatorie**

Test concurent cu două promoții diferite: ambele modificări trebuie păstrate sau una
trebuie respinsă explicit cu conflict 409.

---

### M-10 — Limita pe bytes comprimați nu protejează importul de ZIP bombs sau workbook-uri patologice
**Severitate:** Major
**Categorie:** Securitate / disponibilitate
**Locație exactă:** `backend/services/imports.py:59-124`

**Ce este greșit**

Validarea uploadului verifică extensia și mărimea fișierului comprimat. XLSX este un
container ZIP; nu sunt limitate numărul de membri, dimensiunea decomprimată,
raportul de compresie, numărul de foi, rânduri, coloane sau shared strings.

**Impact concret**

Un fișier sub 32 MB poate consuma gigabytes de memorie/CPU și poate opri workerul
sau backendul. Extensia poate fi falsificată.

**Fix recomandat**

Verifică magic bytes și structura ZIP înainte de parser. Impune limite pentru
dimensiunea expandată, compresie, membri, foi, rânduri și coloane. Rulează parserul
într-un proces izolat cu limite de memorie/CPU.

**Verificare obligatorie**

Include corpus de ZIP bombs și workbook-uri extreme; toate trebuie respinse înainte
de `pandas/openpyxl`.

---

### M-11 — Importul de vânzări transformă date monetare invalide în zero și acceptă câmpuri critice goale
**Severitate:** Major
**Categorie:** Corectitudine / validare date
**Locație exactă:** `backend/services/importer.py:80-107`

**Ce este greșit**

`Pret` și `Valoare` folosesc `errors='coerce'` urmat de `fillna(0)`.
`Cantitate` este convertită direct la `int`, iar mai multe identificatoare
operaționale sunt golite și trimise mai departe. Datele invalide nu apar într-un
raport de respingere.

**Impact concret**

O valoare text, o celulă coruptă sau un format numeric neașteptat devine vânzare de
zero lei. Cantitățile fracționare pot fi trunchiate sau respinse neuniform.
Totalurile importate nu mai pot fi reconciliate cu fișierul sursă.

**Fix recomandat**

Definește o schemă strictă pe coloană. Respinge rândul sau întreg importul la bani
neparsabili, cantitate neintegrală și identificatori obligatorii goi. Produce raport
de erori cu număr de rând și motiv și compară totalurile sursă cu staging-ul.

**Verificare obligatorie**

Teste cu text în `Valoare`, separator greșit, cantitate 1.5 și identificatori goi.
Niciuna nu trebuie să fie importată ca zero.

---

### M-12 — Bonurile fără număr sunt colapsate într-o singură identitate
**Severitate:** Major
**Categorie:** Corectitudine KPI
**Locație exactă:** `backend/services/importer.py:97-100`, `backend/services/receipt_identity.py:10-27`

**Ce este greșit**

`Nr` gol devine șirul vid. Identitatea canonică a bonului folosește
`(sale_date, site_code, agent, bon_nr)`. Toate rândurile cu `bon_nr=''` pentru
același agent, magazin și zi sunt considerate același bon.

**Impact concret**

Numărul de bonuri, Bon2Acc, retururile și valoarea medie pe bon devin greșite.
Eroarea nu este vizibilă în UI și poate afecta plata/performanța.

**Fix recomandat**

Fă numărul bonului obligatoriu. Dacă sursa nu îl poate furniza, definește o
identitate stabilă documentată din câmpuri sursă și marchează explicit calitatea
redusă; nu folosi șirul gol ca identitate.

**Verificare obligatorie**

Fixture cu două bonuri distincte fără număr trebuie respins sau păstrat distinct,
niciodată agregat.

---

### M-13 — Rândurile duplicate de vânzări sunt importate și numărate de două ori
**Severitate:** Major
**Categorie:** Corectitudine / idempotency
**Locație exactă:** `backend/db/schema_v2.sql:102-120`, `backend/services/importer.py:261-373`

**Ce este greșit**

`sales_transactions` are doar cheia surrogate `id`. Importerul copiază fiecare rând
din DataFrame în tabel, fără hash de rând, cheie de business sau raport de
duplicate. Înlocuirea lunii protejează retry-ul fișierului, nu duplicatele interne
din același fișier.

**Impact concret**

Un export care conține dubluri dublează vânzarea, cantitatea și KPI-urile. După
rebuild, toate rapoartele devin consecvent greșite.

**Fix recomandat**

Definește contractul de unicitate al rândului sursă și persistă un `source_row_hash`
sau un identificator de tranzacție. Detectează duplicate exacte și conflicte,
raportează-le și blochează importul peste un prag aprobat.

**Verificare obligatorie**

Teste cu duplicate exacte și duplicate cu valoare diferită. Primul trebuie
deduplicat/respins explicit; al doilea trebuie tratat drept conflict.

---

### M-14 — Metadatele contradictorii ale aceluiași magazin sunt rezolvate prin ordinea rândurilor
**Severitate:** Major
**Categorie:** Corectitudine master data
**Locație exactă:** `backend/services/importer.py:157-162`

**Ce este greșit**

DataFrame-ul execută `drop_duplicates(subset=['SiteCode'])` și păstrează primul
rând. Dacă același `SiteCode` apare cu două firme, locații sau manageri, rezultatul
depinde de ordinea rândurilor din Excel.

**Impact concret**

Master data poate fi realocat greșit fără eroare, iar istoricul pe manager/firmă se
schimbă nedeterminist.

**Fix recomandat**

Grupează pe `SiteCode`, verifică unicitatea fiecărui câmp de structură și respinge
importul la conflict. Realocările trebuie să fie workflow explicit, cu dată
efectivă și audit.

**Verificare obligatorie**

Fixture cu două ASM-uri pentru același cod trebuie să blocheze importul și să
listeze valorile conflictuale.

---

### M-15 — Protocolul lease al importului nu este sigur pentru execuții lungi sau mai mulți workeri
**Severitate:** Major
**Categorie:** Race condition / jobs
**Locație exactă:** `backend/services/importer.py:58-77`, `backend/services/importer.py:213-254`, `backend/worker.py:58-71`

**Ce este greșit**

La startup, workerul marchează toate importurile `processing` ca eșuate. O
rezervare mai veche de o oră este de asemenea închisă, însă importul nu actualizează
periodic un heartbeat pe durata parsării și rebuild-ului. Nu există owner UUID sau
CAS legat de worker.

**Impact concret**

Un rolling restart ori un al doilea worker poate declara eșuat un import încă activ.
După o oră poate fi permisă o execuție concurentă pentru aceeași lună, cu risc de
înlocuire sau raportare contradictorie.

**Fix recomandat**

Persistă `owner_id`, `lease_until` și heartbeat periodic. Închide o rezervare numai
prin CAS dacă lease-ul este expirat și ownerul nu mai este activ. Folosește advisory
lock per lună și state machine durabilă.

**Verificare obligatorie**

Test PostgreSQL cu doi workeri, restart și job >1h: un singur import poate deține
lease-ul, iar workerul întârziat nu poate suprascrie starea terminală.

---

### M-16 — Fișierul Excel brut este copiat prin Valkey și memorie
**Severitate:** Major
**Categorie:** Confidențialitate / performanță / arhitectură
**Locație exactă:** `backend/services/imports.py:59-84`, `backend/services/jobs.py:86-110`, `backend/worker.py:18-36`

**Ce este greșit**

Backendul citește întreg fișierul în bytes, îl trimite ca argument ARQ în Valkey,
iar workerul îl deserializează din nou și îl transformă în DataFrame. Conținutul
operațional sensibil ajunge în coadă și este copiat de mai multe ori în RAM.

**Impact concret**

La fișiere mari apare amplificare de memorie, latență și presiune pe Valkey.
Backupurile/snapshoturile Redis pot conține date brute de vânzări.

**Fix recomandat**

Scrie uploadul într-un spool protejat sau object storage, calculează hash-ul și pune
în coadă doar ID-ul, calea opacă, hash-ul și metadatele. Workerul verifică hash-ul,
procesează streaming și șterge conform retenției.

**Verificare obligatorie**

Măsoară peak RSS și dimensiunea Valkey la fișier maxim; payloadul cozii trebuie să
rămână de ordinul kilobytes, nu megabytes.

---

### M-17 — Un singur worker serializează importuri, verificări și operații lunare
**Severitate:** Major
**Categorie:** Scalabilitate / disponibilitate
**Locație exactă:** `backend/worker.py:158-169`

**Ce este greșit**

Toate cele trei clase de job rulează în aceeași coadă și același proces cu
`max_jobs=1` și timeout de 30 minute.

**Impact concret**

Un import lung blochează verificarea Grile și închiderea lunii. Un job Google lent
blochează importurile. La 10× trafic, coada devine primul bottleneck și nu există
izolare între workload-uri.

**Fix recomandat**

Separă cozi și unități: import CPU/DB, Grile read, Grile destructive/export. Folosește
limite și timeout-uri distincte, concurență controlată și autoscaling/replicare unde
operația este idempotentă.

**Verificare obligatorie**

Test de coadă: un import de 20 minute nu trebuie să întârzie un check read-only sau
status polling-ul unei operații lunare.

---

### M-18 — Pașii derivați după import sunt best-effort și nu au retry durabil
**Severitate:** Major
**Categorie:** Corectitudine eventuală / operațional
**Locație exactă:** `backend/services/imports.py:33-51`, `backend/worker.py:38-52`

**Ce este greșit**

După import, verificarea Grile este pornită best-effort; orice excepție este doar
logată. Importul rămâne complet chiar dacă Valkey sau serviciul derivat a eșuat.
Nu există outbox, stare `pending_derivations` sau reconciliere.

**Impact concret**

Datele de vânzări sunt noi, dar targetele/derivatele pot rămâne vechi. Operatorul
vede succes și nu are o listă clară a pașilor lipsă.

**Fix recomandat**

Adaugă transactional outbox în aceeași tranzacție logică a importului. Fiecare pas
derivat are stare, retry, deadline, alertă și endpoint de reconciliere. UI-ul
trebuie să distingă „importat” de „complet procesat”.

**Verificare obligatorie**

Oprește Valkey după commitul importului; outbox-ul trebuie să rămână pending și să
fie procesat automat după revenire.

---

### M-19 — Invalidarea cache-ului filtrelor este executată în procesul greșit
**Severitate:** Major
**Categorie:** Corectitudine cache
**Locație exactă:** `backend/worker.py:38-42`, `backend/services/filter_options.py:12-33`

**Ce este greșit**

Workerul apelează `clear_filter_options_cache`, însă cache-ul este un dicționar de
clasă în memoria procesului web. Curățarea workerului nu afectează cache-ul
backendului care servește utilizatorii.

**Impact concret**

După import, lista de magazine/agenți poate rămâne veche până la cinci minute.
Utilizatorul poate selecta un scope inexistent sau nu vede entități noi.

**Fix recomandat**

Folosește cache distribuit/versionat sau publică un eveniment de invalidare consumat
de toate procesele web. Alternativ, include versiunea ultimului import în cheia
cache.

**Verificare obligatorie**

Test multi-proces: după import, primul request web trebuie să vadă imediat noile
opțiuni.

---

### M-20 — Indisponibilitatea cozii este raportată ca job inexistent
**Severitate:** Major
**Categorie:** Error handling / observabilitate
**Locație exactă:** `backend/services/jobs.py:253-274`

**Ce este greșit**

Orice excepție la accesarea Valkey/ARQ este convertită în `JobStatus.NOT_FOUND`.
Nu se diferențiază între ID absent, timeout, conexiune refuzată sau eroare internă.

**Impact concret**

UI-ul spune că jobul nu există când infrastructura este căzută. Incidentul este
ascuns, retry-ul utilizatorului poate dubla acțiuni, iar monitorizarea pierde cauza.

**Fix recomandat**

Returnează 503/`queue_unavailable` pentru erori de infrastructură și `not_found`
numai după un răspuns valid al cozii. Loghează/metricizează separat.

**Verificare obligatorie**

Teste cu Valkey oprit și ID absent; răspunsurile trebuie să fie diferite.

---

### M-21 — Preview-ul exportului construiește raportul complet înainte de a-l tăia
**Severitate:** Major
**Categorie:** Performanță / cost
**Locație exactă:** `backend/services/exports.py:195-205`

**Ce este greșit**

`preview_limit` este aplicat după `build_report`, când toate query-urile, toate
rândurile și toate coloanele au fost deja calculate și materializate în memorie.

**Impact concret**

Un preview de 100 rânduri poate avea același cost ca exportul complet pe 144 luni.
Utilizatorii pot suprasolicita DB și backendul prin simple apăsări repetate pe
„Preview”.

**Fix recomandat**

Creează query separat de preview cu `LIMIT`, count și set minim de calcule. Impune
buget de celule și nu calcula evoluții neafișate.

**Verificare obligatorie**

Măsoară SQL, CPU și memorie pentru preview vs export complet; preview-ul trebuie să
fie proporțional cu limita solicitată.

---

### M-22 — Exporturile sunt construite integral în RAM, iar răspunsul „streaming” conține un singur blob
**Severitate:** Major
**Categorie:** Performanță / disponibilitate
**Locație exactă:** `backend/services/exports.py:476-546`, `backend/services/exports.py:575-633`, `backend/routers/exports.py:69-84`

**Ce este greșit**

OpenPyXL construiește workbookul în memorie, îl salvează într-un `BytesIO`, apoi
`getvalue()` creează bytes. Routerul trimite `StreamingResponse(iter([content]))`,
adică un singur obiect deja materializat. Operația rulează în requestul web.

**Impact concret**

Exporturile mari consumă mult RAM și CPU în procesul Uvicorn unic. Mai multe
exporturi concurente pot produce OOM și indisponibilitate. Clientul nu primește
progres sau job resumabil.

**Fix recomandat**

Mută exportul în job background. Folosește workbook write-only și fișier temporar
securizat/object storage, apoi livrează prin streaming real sau URL semnat cu
expirare. Adaugă limite de rânduri/celule și o singură execuție costisitoare per
utilizator.

**Verificare obligatorie**

Test cu export maxim și trei utilizatori concurenți; backendul web trebuie să rămână
sub un plafon RSS și să servească requesturi read.

---

### M-23 — Exportul incentive poate epuiza pool-ul prin achiziție DB imbricată
**Severitate:** Major
**Categorie:** Race condition / performanță DB
**Locație exactă:** `backend/services/exports.py:322-407`, `backend/services/exports.py:752-852`

**Ce este greșit**

`_build_incentive_products_report` ține o conexiune din pool pe toată bucla lunilor,
apoi apelează `_campaign_exclusions_by_month`, care face o a doua
`pool.acquire()`. Cu pool de 10 conexiuni, zece requesturi concurente pot păstra
fiecare câte o conexiune și aștepta toate o a doua conexiune.

**Impact concret**

Se poate produce starvation sau deadlock practic până la `statement/command
timeout`. Readiness și alte requesturi rămân fără conexiuni.

**Fix recomandat**

Pasează aceeași conexiune helperului sau eliberează conexiunea exterioară înainte
de calcul. Adaugă limită de concurență pentru exporturi și instrumentează timpul de
așteptare la pool.

**Verificare obligatorie**

Test cu pool=2 și două exporturi concurente; ambele trebuie să termine fără așteptare
circulară.

---

### M-24 — Inputul exporturilor este insuficient limitat și permite cost disproporționat
**Severitate:** Major
**Categorie:** Validare / prevenire abuz
**Locație exactă:** `backend/routers/exports.py:17-42`, `backend/services/exports.py:207-270`

**Ce este greșit**

Listele de filtre, dimensiuni și metrici nu au limite coerente pe număr și lungimea
elementelor. Duplicatele sunt validate târziu sau păstrate în unele structuri.
Limita de 144 luni permite un volum foarte mare pentru combinațiile lunare.

**Impact concret**

Un utilizator autorizat poate genera SQL și workbook-uri enorme, cu multe coloane
redundante și valori de filtru supradimensionate.

**Fix recomandat**

Folosește enum-uri și stringuri cu `max_length`, deduplicare la boundary, limite
per listă și un buget calculat de celule/query-cost. Respinge requestul înainte de
orice acces DB.

**Verificare obligatorie**

Fuzz test pentru liste lungi, duplicate și stringuri mari; răspuns 422 bounded.

---

### M-25 — Domeniile Export și Campaigns depind de funcții private din Dashboard
**Severitate:** Major
**Categorie:** Arhitectură / cuplare
**Locație exactă:** `backend/services/exports.py:18-29`, `backend/services/campaigns.py:20-31`

**Ce este greșit**

Serviciile importă funcții cu prefix `_` din `services.dashboard.queries`.
Aceste funcții conțin reguli financiare promo/incentive, dar contractul lor real
este privat și controlat de un alt domeniu.

**Impact concret**

O refactorizare Dashboard poate schimba exporturile sau calculul incentive fără
eroare de tip/contract. Regula financiară nu are un singur owner clar.

**Fix recomandat**

Extrage un serviciu public `campaign_finance`/`incentive_calculation` cu modele
tipizate, contracte stabile și teste de echivalență consumate de Dashboard,
Campaigns și Exports.

**Verificare obligatorie**

Un singur set de fixture-uri financiare trebuie să producă același rezultat în
toate cele trei suprafețe.

---

### M-26 — Arborele de vizite este nelimitat și nu cere interval temporal
**Severitate:** Major
**Categorie:** Performanță / expunere date
**Locație exactă:** `backend/routers/visits_report.py:37-45`, `backend/repositories/visits_report.py:54-82`, `backend/services/visits_report.py:94-156`

**Ce este greșit**

Endpointul `/tree` poate citi toate vizitele non-draft din SQLite, fără lună,
limită sau cursor. Serviciul materializează toate rândurile și construiește o
structură nested completă în memorie.

**Impact concret**

Volumul crește fără limită. La 10× date, requestul consumă memorie și CPU și
transferă istoricul complet al vizitelor. Orice utilizator autentificat poate
declanșa operația.

**Fix recomandat**

Cere interval explicit cu maximum, adaugă cursor/paginare și returnează sumarul
separat de detalii. Impune hard cap server-side.

**Verificare obligatorie**

Test cu milioane de rânduri sintetice: timpul și memoria trebuie să rămână bounded,
iar răspunsul să fie paginat.

---

### M-27 — Filtrul lunar SQLite blochează folosirea unui index normal pe dată
**Severitate:** Major
**Categorie:** Performanță query
**Locație exactă:** `backend/repositories/visits_report.py:119-121`

**Status curent (2026-07-16): închis.** Runtime-ul Retail foloseste repository-ul
PostgreSQL `fieldops_visits`; textul urmator descrie constatarea istorica.

**Ce este greșit**

Query-ul folosește `strftime('%Y-%m', data_raport) = ?`, aplicând o funcție pe
fiecare rând.

**Impact concret**

SQLite scanează mult mai mult decât este necesar pe măsură ce istoricul crește.
Endpointul de raport devine lent chiar dacă există index pe dată.

**Fix recomandat**

Convertește luna în `[month_start, next_month_start)` și filtrează
`data_raport >= ? AND data_raport < ?`. Adaugă/verifică indexul corespunzător.

**Verificare obligatorie**

`EXPLAIN QUERY PLAN` trebuie să arate index search, nu full scan.

---

### M-28 — Autorizarea read este globală pentru aproape orice identitate autentificată
**Severitate:** Major
**Categorie:** Autorizare / privacy by design
**Locație exactă:** `backend/main.py:241-260`, `backend/permissions.py:13-60`

**Ce este greșit**

Hub, Agents, Campaigns, Visits, Tasks, CRM și o parte din Grile sunt protejate doar
de `require_auth`. Codul nu leagă subiectul OIDC de magazine, firmă, regional sau
rol operațional. Filtrele trimise de client sunt preferințe, nu restricții de
securitate.

**Impact concret**

Dacă în tenant intră agenți, TL sau conturi cu scope limitat, aceștia pot cere date
la nivel de rețea, inclusiv note și analize de vizită. Ascunderea meniului în
frontend nu rezolvă problema.

**Fix recomandat**

Introdu mapping server-side subiect/grup -> scope organizațional și aplică-l în
repository, independent de filtrele requestului. Definește matrice explicită de
capabilități read/write/export.

**Verificare obligatorie**

Teste negative pe fiecare rol: un agent nu poate cere alt magazin, iar un manager
nu poate ieși din regiunea sa prin parametri manipulați.

---

### M-29 — Endpointul de fotografii nu verifică legătura fișierului cu vizita sau scope-ul utilizatorului
**Severitate:** Major
**Categorie:** Autorizare obiect / path safety
**Locație exactă:** `backend/routers/visits_report.py:56-73`, `backend/repositories/visits_report.py:95-105`

**Ce este greșit**

Protecția verifică fragmente `..`, separatori și prefixul string al căii rezolvate.
Nu verifică dacă `filename` este unul dintre `foto1..foto4`/fișierele aprobate ale
vizitei și nu aplică scope organizațional. Verificarea `str(path).startswith(...)`
este mai fragilă decât relația reală `Path.is_relative_to`.

**Impact concret**

Un utilizator autentificat care ghicește ID-uri/nume poate accesa alte imagini din
directorul de vizite. Symlink-uri sau coliziuni de prefix complică suplimentar
siguranța.

**Fix recomandat**

Citește vizita, autorizează scope-ul, verifică filename într-o allowlist persistată,
folosește `is_relative_to`, `is_file` și refuză symlink-uri nepermise. Preferă ID
opac de atașament.

**Verificare obligatorie**

Test IDOR între două regiuni și teste de symlink/prefix path.

---

### M-30 — Rolul runtime PostgreSQL are drepturi mult peste necesarul aplicației web
**Severitate:** Major
**Categorie:** Least privilege / impact compromis
**Locație exactă:** `backend/scripts/provision_runtime_database_role.py:65-81`

**Ce este greșit**

Același rol primește SELECT, INSERT, UPDATE și DELETE pe toate tabelele, EXECUTE pe
toate funcțiile și TRUNCATE pe un tabel reporting. Webul, workerul și mai multe
domenii împart practic aceeași putere.

**Impact concret**

O injecție, SSRF cu acces la credențiale sau compromiterea unui proces permite
modificarea aproape întregii baze, inclusiv zone financiare care nu au legătură cu
endpointul compromis.

**Fix recomandat**

Separă roluri: web-read, web-business-write, import-worker, grile-worker și
migration-owner. Acordă granturi explicite pe tabele/funcții, preferabil prin
funcții security-definer pentru mutații sensibile. Configurează
`ALTER DEFAULT PRIVILEGES` controlat.

**Verificare obligatorie**

Testează fiecare serviciu cu credentialul său și dovedește că operațiile din afara
domeniului primesc `permission denied`.

---

### M-31 — Endpointul public `/metrics` poate expune valori comerciale
**Severitate:** Major
**Categorie:** Expunere date / infrastructură
**Locație exactă:** `backend/main.py:263-269`, `backend/services/retail_metrics.py:13-28`

**Ce este greșit**

`/metrics` nu are autentificare la nivelul aplicației, iar registry-ul include
venit curent, număr de agenți, magazine și produse de campanie. Repository-ul nu
conține configurația reverse proxy care să dovedească restricționarea rețelei.

**Impact concret**

Dacă ruta este publicată de proxy, oricine poate extrage indicatori comerciali și
topologia operațională. Chiar fără acces public, amestecarea metricilor de business
cu endpointul tehnic mărește riscul de expunere accidentală.

**Fix recomandat**

Servește Prometheus pe listener/rețea privată sau protejează ruta la proxy prin ACL
și mTLS. Separă metricile comerciale sensibile și documentează explicit politica.

**Verificare obligatorie**

Verificare externă neautentificată trebuie să primească 404/403, iar Prometheus
intern să continue să scrape-uiască.

---

### M-32 — Forecastul trimite date comerciale către un peer privat cu guvernanță insuficient documentată
**Severitate:** Major
**Categorie:** Confidențialitate / guvernanță / supply chain AI
**Locație exactă:** `backend/scripts/run_ai_forecast_xreg.py:25-29`, `backend/scripts/run_ai_forecast_xreg.py:207-355`, `backend/scripts/run_ai_forecast_xreg.py:358-371`

**Ce este greșit**

Endpointul implicit este `http://100.74.73.114:8000/forecast_xreg`, iar IP-ul este
un peer Tailscale. WireGuard/Tailscale asigură criptarea transportului pe overlay;
constatarea inițială că datele circulă plaintext pe internet a fost greșită.
Payloadul conține totuși serii comerciale și ierarhie organizațională, cheia este
trimisă serviciului peer, iar răspunsul este citit integral fără limită explicită.

**Impact concret**

Criptarea transportului nu dovedește autorizarea peer-ului, ownerul și retenția
procesatorului, minimizarea payloadului, rotația cheii sau controlul accesului pe
hostul TimesFM. Compromiterea peer-ului poate expune datele și cheia după decriptare.
Outputurile CSV conțin la rândul lor valori comerciale identificabile.

**Fix recomandat**

Păstrează peer-ul în allowlist Tailscale/ACL, documentează ownerul și contractul de
procesare, minimizează/pseudonimizează payloadul, limitează răspunsul, rotește cheia
și nu o accepta ca argument CLI. Aplică retenție și permisiuni stricte outputurilor.

**Verificare obligatorie**

Testul trebuie să refuze destinații din afara allowlistului Tailscale și răspunsuri
supradimensionate. Documentează data-flow-ul, ACL-ul și ownerul procesatorului AI.

---

### M-33 — Requesturile concurente pot fi delogate în timp ce alt request reîmprospătează sesiunea
**Severitate:** Major
**Categorie:** Race condition auth
**Locație exactă:** `backend/session_auth.py:227-283`

**Ce este greșit**

Câștigătorul lock-ului poate aștepta până la timeout-ul HTTP de 15 secunde.
Requesturile care nu obțin lock-ul așteaptă doar 20 × 100 ms. Dacă refresh-ul nu
termină în două secunde, ele întorc `None`, iar callerul șterge sesiunea. TTL-ul
lock-ului este chiar 15 secunde, fără marjă.

**Impact concret**

În latență normală ridicată la IdP, un singur tab poate reîmprospăta corect tokenul,
în timp ce alt request șterge sesiunea și produce logout aparent aleator.

**Fix recomandat**

Implementează singleflight/notification reală, TTL mai mare decât deadline-ul și o
stare distinctă `refresh_in_progress`. Waiterul nu trebuie să șteargă sesiunea la
timeout local; trebuie să reîncerce controlat sau să răspundă 503.

**Verificare obligatorie**

Test concurent cu refresh de 5-10 secunde și 20 requesturi: toate trebuie să
primească aceeași sesiune reîmprospătată, fără delete.

---

### M-34 — Backendul read-heavy refuză să pornească dacă ARQ este indisponibil
**Severitate:** Major
**Categorie:** Disponibilitate / startup
**Locație exactă:** `backend/main.py:87-109`, `backend/services/health.py:14-23`

**Ce este greșit**

Lifespan-ul inițializează pool-ul ARQ înainte de `yield`. O problemă Valkey/ARQ
oprește complet backendul, deși contractul de readiness afirmă că job queue nu este
necesară pentru requesturile read. Startup-ul mai execută sincronizarea vizitelor
și warmup-uri înainte de a servi.

**Impact concret**

O cădere a cozii oprește Hub, rapoarte și citiri care ar fi putut funcționa. Restartul
devine mai lent și mai fragil.

**Fix recomandat**

Lasă startup-ul să depindă numai de componentele absolut necesare autentificării și
citirii. Inițializează coada lazy/best-effort; endpointurile de job întorc 503
specific. Mută sync/warmup în taskuri observabile după pornire.

**Verificare obligatorie**

Pornește backendul cu ARQ indisponibil: read endpoints și readiness conform
contractului trebuie să funcționeze, iar mutațiile async să răspundă 503.

---

### M-35 — `visits_snapshot` se actualizează numai la restartul backendului
**Severitate:** Major
**Categorie:** Consistență date / operațional
**Locație exactă:** `backend/services/visits_sync.py:8-10`, `backend/services/visits_sync.py:62-101`, `backend/main.py:100-103`

**Ce este greșit**

Proiectia `visits_snapshot` este reconstruita tranzactional la boot din
autoritatea PostgreSQL. Nu exista inca scheduler sau refresh incremental.
Rapoartele HR/management citesc proiectia.

**Impact concret**

Vizitele noi pot intra in scoruri si management abia la urmatorul refresh al
proiectiei. Ecranul Vizite si sursa proiectiei nu se mai contrazic intre baze,
dar proiectia poate ramane in urma autoritatii PostgreSQL.

**Fix recomandat**

Adaugă sincronizare incrementală programată/event-driven, watermark și metrică de
lag. Nu șterge snapshotul complet la fiecare refresh; folosește upsert într-o
tranzacție și alertă de staleness.

**Verificare obligatorie**

Creează o vizită nouă fără restart și dovedește că apare în scoruri în SLA-ul
definit.

---

### M-36 — Validarea lunilor, datelor, filtrelor și stringurilor este inconsistentă la boundary
**Severitate:** Major
**Categorie:** Validare input / corectitudine
**Locație exactă:** `backend/routers/dashboard.py:15-193`, `backend/routers/agents.py:20-87`, `backend/routers/filters.py:24-36`, `backend/routers/crm.py:21-45`, `backend/routers/visits_report.py:25-60`, `backend/routers/salarii.py:45-71`

**Ce este greșit**

Multe rute acceptă stringuri brute pentru lună, agent, magazin, firmă și interval.
Unele domenii au regex, altele fac split/parse în service, iar lungimile listelor
comma-separated nu sunt limitate.

**Impact concret**

Inputurile invalide produc 500 sau query-uri costisitoare, contractele OpenAPI sunt
slabe și fiecare domeniu interpretează diferit aceleași valori.

**Fix recomandat**

Introdu tipuri comune `YearMonth`, `ScopedFilter`, enum-uri și limite de lungime/
număr. Normalizează o singură dată la boundary și păstrează service/repository fără
parsing ad-hoc.

**Verificare obligatorie**

Fuzz tests comune pentru toate rutele; inputul invalid trebuie să dea 422, fără
stacktrace și fără acces DB costisitor.

---

### M-37 — Target Calculator poate comite parțial și apoi răspunde 400
**Severitate:** Major
**Categorie:** Tranzacționalitate / corectitudine financiară
**Locație exactă:** `backend/repositories/target_calculator.py:290-341`, `backend/services/target_calculator.py:767-796`

**Ce este greșit**

Repository-ul numără câte coduri există, actualizează toate rândurile găsite și
incrementează revizia în aceeași tranzacție. După commit, service-ul compară numărul
actualizat cu numărul cerut și aruncă 400 dacă unele coduri nu aparțin scenariului.

**Impact concret**

Clientul vede eșec, dar rândurile valide au fost modificate și revizia a crescut.
Reîncercarea poate produce conflict, iar utilizatorul nu știe ce s-a salvat.

**Fix recomandat**

Validează existența tuturor codurilor înainte de orice update și aruncă în interiorul
tranzacției, astfel încât rollback-ul să fie complet. Verifică și duplicatele la DB
boundary.

**Verificare obligatorie**

Request cu un cod valid și unul invalid trebuie să lase toate valorile și revizia
neschimbate.

---

### M-38 — Istoricul multi-lună lansează un `/dashboard/all` greu pentru fiecare lună, simultan
**Severitate:** Major
**Categorie:** Performanță / scalabilitate
**Locație exactă:** `src/components/dashboard/useDashboardData.ts:99-139`, `src/components/Dashboard.tsx:631-680`

**Ce este greșit**

Selecția de luni nu are cap server/client vizibil, iar query function execută
`Promise.all` peste câte un `getDashboardAll` per lună. Fiecare request Dashboard
are propriul fan-out backend.

**Impact concret**

Selectarea a 35 de luni poate crea 35 requesturi concurente și zeci/sute de query-uri
DB. Un singur utilizator poate epuiza pool-ul și afecta toată aplicația.

**Fix recomandat**

Adaugă endpoint batch/aggregate server-side, limită de luni și concurență bounded.
Agregă direct din tabelele reporting, nu prin repetarea răspunsului complet lunar.

**Verificare obligatorie**

Test cu toate lunile disponibile: numărul requesturilor trebuie să rămână 1, iar
pool usage sub prag.

---

### M-39 — Numărul de agenți agregat pe mai multe luni este calculat greșit
**Severitate:** Major
**Categorie:** Corectitudine KPI
**Locație exactă:** `src/components/Dashboard.tsx:442-516`

**Ce este greșit**

Agregarea regională/ASM/magazin folosește `Math.max` peste `nr_agenti` lunar.
Aceasta nu este cardinalitatea agenților unici din perioada selectată și nu poate
reprezenta intrări/ieșiri între luni.

**Impact concret**

Dashboardul subraportează agenții când populația se schimbă. Analizele de
productivitate și stabilitate pe perioade devin greșite.

**Fix recomandat**

Calculează cardinalitatea pe identificatori de agent server-side sau transmite
seturi/chei necesare agregării. Nu deriva cardinalități din totaluri lunare.

**Verificare obligatorie**

Fixture cu 10 agenți în luna A și 10 complet diferiți în luna B trebuie să raporteze
20 unici, nu 10.

---

### M-40 — Endpointurile read costisitoare nu au rate limit sau buget de query
**Severitate:** Major
**Categorie:** Disponibilitate / abuz intern
**Locație exactă:** `backend/main.py:241-259`, `backend/routers/dashboard.py:38-193`, `backend/routers/agents.py:20-87`, `backend/routers/visits_report.py:25-60`

**Ce este greșit**

Rate limiting-ul acoperă în principal auth, upload, export și mutații. Dashboard,
evaluări, campanii și vizite pot fi apelate nelimitat de orice sesiune validă.

**Impact concret**

Un cont compromis, un bug de polling sau fan-out-ul frontend poate satura DB și
SQLite. Autentificarea nu este protecție suficientă împotriva consumului excesiv.

**Fix recomandat**

Adaugă rate limit per subiect pentru read-uri grele, query-cost caps, timeout-uri și
circuit breaker. Separă limitele pentru requesturi interactive și batch.

**Verificare obligatorie**

Load test cu un singur subiect agresiv: ceilalți utilizatori trebuie să-și păstreze
SLO-ul, iar atacatorul să primească 429.

---

### M-41 — Rutele API/auth necunoscute pot primi HTML-ul SPA cu status 200
**Severitate:** Major
**Categorie:** Corectitudine HTTP / observabilitate
**Locație exactă:** `backend/main.py:272-305`

**Ce este greșit**

Mount-ul static catch-all întoarce `index.html` la orice 404. Nu verifică metoda,
`Accept` sau namespace-ul. Astfel, un path precum `/api/typo`,
`/auth/typo` ori `/salarii/typo` poate primi pagina React.

**Impact concret**

Clienții API încearcă să parseze HTML ca JSON, monitorizarea vede 200 în loc de 404,
iar erorile de routing sunt mascate.

**Fix recomandat**

Aplică fallback SPA numai pentru GET/HEAD cu `Accept: text/html` și numai în afara
namespace-urilor server (`/api`, `/auth`, `/salarii`, `/metrics`, `/docs`,
`/openapi.json`, health). Restul trebuie să păstreze 404.

**Verificare obligatorie**

Teste pentru path API necunoscut, navigation browser și POST necunoscut.

---

### M-42 — CSP-ul blochează telemetria frontend configurată
**Severitate:** Major
**Categorie:** Observabilitate / securitate browser
**Locație exactă:** `src/main.tsx:8-16`, `backend/main.py:164-179`, `.github/workflows/ci.yml:195-206`

**Ce este greșit**

Frontendul inițializează Sentry/GlitchTip, iar CI configurează
`https://errors.unihub.ro`. CSP permite `connect-src` doar `'self'` și
`https://auth.unihub.ro`.

**Impact concret**

Raportarea erorilor, tracing-ul sau uploadurile de evenimente din browser pot fi
blocate de CSP. Aplicația declară observabilitate, dar incidentele client pot
dispărea în tăcere.

**Fix recomandat**

Adaugă exact origin-ul DSN în CSP sau folosește un tunnel same-origin. Include
verificare CSP în E2E și monitorizează rata de evenimente recepționate.

**Verificare obligatorie**

Provoacă o eroare sintetică în browser și dovedește că evenimentul ajunge în
GlitchTip fără violation CSP.

---

### M-43 — Ecranul Salarii poate afișa date vechi sub filtre noi
**Severitate:** Major
**Categorie:** Race condition frontend / confidențialitate
**Locație exactă:** `src/components/SalariiSubtab.tsx:152-222`

**Ce este greșit**

Mai multe requesturi sunt pornite din `useEffect` fără abort, request ID sau query
key. Un request lent pentru filtrul anterior poate termina după requestul nou și
suprascrie state-ul. La eroare se scrie doar în consolă, iar datele anterioare
rămân pe ecran.

**Impact concret**

Utilizatorul poate vedea salariile altei selecții de firmă/magazin, etichetate
vizual cu filtrele curente. Aceasta este atât eroare de corectitudine, cât și risc
de confidențialitate.

**Fix recomandat**

Migrează ecranul la TanStack Query cu key completă pe filtre, `AbortSignal`,
`keepPreviousData` controlat și indicator clar de stale/loading/error. Curăță sau
marchează datele când scope-ul se schimbă.

**Verificare obligatorie**

Test cu răspunsuri deliberate out-of-order: numai ultimul scope poate fi randat.

---

### M-44 — Clientul API nu are timeout sau anulare
**Severitate:** Major
**Categorie:** Reziliență frontend
**Locație exactă:** `src/api/client.ts:161-233`

**Ce este greșit**

Toate operațiile `fetch` rulează fără `AbortController`, deadline sau semnal primit
de la TanStack Query.

**Impact concret**

O conexiune blocată poate ține UI-ul în busy indefinit, poate livra răspuns stale
după schimbarea scope-ului și consumă resurse în browser/server.

**Fix recomandat**

Adaugă timeout bounded, suport `signal`, clasificare timeout/cancel și propagă
semnalul din query/mutație. Uploadurile și downloadurile trebuie să aibă politici
proprii.

**Verificare obligatorie**

Testează endpoint care nu răspunde și schimbarea rapidă a filtrelor.

---

### M-45 — Bootstrap-ul aplicației ascunde eșecul încărcării lunilor și lasă ecranele goale
**Severitate:** Major
**Categorie:** Error handling frontend
**Locație exactă:** `src/App.tsx:184-200`, `src/App.tsx:279-323`

**Ce este greșit**

Excepția din `getAvailableMonths` este ignorată. `currentMonth` rămâne gol, iar Hub,
Focus și Agents nu se mai randază, fără mesaj de eroare sau retry.

**Impact concret**

O problemă API produce o aplicație aparent goală, nu un incident diagnosticabil.
Utilizatorul poate interpreta lipsa UI ca lipsă de date.

**Fix recomandat**

Introdu stare explicită `bootstrap_error`, buton de retry, request ID și telemetry.
Distinge între „nu există luni importate” și „API indisponibil”.

**Verificare obligatorie**

E2E cu `/api/filters/months` 500 și empty array; cele două situații trebuie să aibă
mesaje diferite.

---

### M-46 — Încărcarea opțiunilor de filtru are race și transformă erorile în liste goale
**Severitate:** Major
**Categorie:** Race condition frontend / UX
**Locație exactă:** `src/components/MainLayout.tsx:81-88`

**Ce este greșit**

Requestul nu este anulat când se schimbă luna. Un răspuns vechi poate suprascrie
opțiunile noi. Orice eroare setează `emptyOptions` fără feedback.

**Impact concret**

Filtrele pot dispărea sau pot aparține altei luni. Utilizatorul poate reseta
accidental scope-ul ori interpreta eroarea drept lipsă de date.

**Fix recomandat**

Folosește query key pe lună, abort, keep-previous-data și stare de eroare vizibilă.
Nu înlocui datele valide cu gol la o eroare tranzitorie.

**Verificare obligatorie**

Test out-of-order și test 503 cu opțiuni cache-uite.

---

### M-47 — Bottom navigation și butonul flotant acoperă conținutul pe mobil
**Severitate:** Major
**Categorie:** UI/UX mobil / accesibilitate
**Locație exactă:** `src/components/MainLayout.tsx:169-180`, `src/components/MainLayout.tsx:315-360`; confirmat în capturile mobile atașate

**Ce este greșit**

Layoutul folosește `pb-24`, bottom nav fix cu padding propriu și FAB fix la
`bottom-20`. Nu folosește `env(safe-area-inset-bottom)`, înălțimea măsurată a
navigației sau rezervarea dinamică a spațiului.

**Impact concret**

Ultimele rânduri, grafice și controale sunt acoperite în capturile Hub, Focus,
Agents, Management și Settings. FAB-ul maschează date și reduce zona de tap.

**Fix recomandat**

Construiește un mobile shell cu CSS variable pentru înălțimea nav, safe-area și
padding calculat. Mută filtrul în top action bar/bottom sheet sau rezervă spațiul
real; nu suprapune controale peste date.

**Verificare obligatorie**

Visual regression pe Android/iPhone cu ultimul element focalizabil complet vizibil
și fără overlap la toate modulele.

---

### M-48 — Sheet-ul de filtre nu este un dialog accesibil
**Severitate:** Major
**Categorie:** Accesibilitate / interacțiune
**Locație exactă:** `src/components/MainLayout.tsx:183-310`, `src/components/MainLayout.tsx:363-504`

**Ce este greșit**

Overlay-ul nu are `role=dialog`, `aria-modal`, focus trap, Escape, restaurarea
focusului sau blocare robustă a scrollului. Multi-select-ul custom nu expune
semantică listbox/option și nu gestionează navigarea completă din tastatură.

**Impact concret**

Utilizatorii de tastatură/screen reader pot naviga în spatele sheet-ului, pot pierde
focusul și nu primesc starea selecției.

**Fix recomandat**

Înlocuiește cu primitive Dialog și Listbox testate, cu focus management, Escape,
aria-live pentru număr de selecții și scroll intern bounded.

**Verificare obligatorie**

Teste Playwright keyboard-only și axe pe dialog deschis, inclusiv focus return.

---

### M-49 — CI nu testează viewport mobil, deși produsul este folosit intensiv pe telefon
**Severitate:** Major
**Categorie:** Testare / UX
**Locație exactă:** `playwright.config.ts:21-26`, `e2e/accessibility.spec.ts:14-32`; confirmat de capturi

**Ce este greșit**

Singurul proiect Playwright este Desktop Chrome. Smoke-ul axe verifică doar Hub și
Management. Nu există Android/iPhone, safe-area, bottom nav, FAB, importuri,
Focus, Agents sau Settings.

**Impact concret**

Regresiile mobile evidente din capturi trec CI. Un test desktop verde nu validează
o aplicație mobilă.

**Fix recomandat**

Adaugă proiecte Pixel/iPhone, orientări și viewport-uri mici. Include capturi
comparative, scroll-to-end, tap targets, dialog, tabele, tooltip-uri și toate
modulele.

**Verificare obligatorie**

CI trebuie să eșueze când bottom nav sau FAB se intersectează cu conținutul.

---

### M-50 — E2E mock-uiește întregul API și nu validează integrarea reală
**Severitate:** Major
**Categorie:** Testare / contracte
**Locație exactă:** `e2e/helpers.ts:156-186`

**Ce este greșit**

Un handler generic răspunde `{}` pentru orice `/api/*`, apoi câteva rute sunt
suprascrise cu fixture-uri. Testele nu pornesc FastAPI, PostgreSQL, Valkey sau auth
BFF și fixture-urile pot devia de la contractele reale.

**Impact concret**

CI poate fi verde cu rute rupte, RBAC greșit, migrații incompatibile, query-uri
eronate sau contracte frontend/backend divergente.

**Fix recomandat**

Păstrează mock tests pentru UI rapid, dar adaugă o suită full-stack izolată cu
Postgres/Valkey/FastAPI și sesiune sintetică sigură. Generează fixture-urile din
scheme/OpenAPI și verifică fluxurile import/export/auth.

**Verificare obligatorie**

Cel puțin un smoke per modul trebuie să traverseze browser -> backend -> DB reală
temporară.

---

### M-51 — Gate-ul „strict TypeScript” acoperă o fracțiune din frontend, iar lint permite warnings
**Severitate:** Major
**Categorie:** Calitate cod / testare statică
**Locație exactă:** `tsconfig.strict.json:11-16`, `tsconfig.json:3-25`, `eslint.config.js:36-47`, `.github/workflows/ci.yml:160-170`

**Ce este greșit**

Configurația strictă include doar auth, lib și clientul API. Componentele mari și
majoritatea API-urilor nu sunt verificate strict. ESLint marchează
`no-unused-vars` ca warning, dezactivează `no-explicit-any`, iar CI nu folosește
`--max-warnings=0`.

**Impact concret**

Mesajul de gate strict este mai puternic decât acoperirea reală. Erori de null,
indexare și tipuri `any` rămân în zonele cu cea mai multă logică UI.

**Fix recomandat**

Extinde strict incremental la tot `src`, elimină `allowJs` dacă nu este necesar,
restrânge `any` și fă lint fail la warnings. Folosește proiecte TS pe domenii până
la migrarea completă.

**Verificare obligatorie**

Criteriu final: `tsc --strict` pe tot frontendul și ESLint cu zero warnings.

---

### M-52 — Coverage-ul este selectiv, iar baseline-ul Bandit păstrează 16 constatări Medium
**Severitate:** Major
**Categorie:** Calitate / securitate statică
**Locație exactă:** `backend/critical_coverage_thresholds.json:3-20`, `.github/workflows/ci.yml:102-134`, `.bandit-baseline.json`

**Ce este greșit**

Coverage-ul CI instrumentează o listă explicită de module, nu întreg backendul, iar
frontendul nu are prag de coverage. Bandit rulează cu baseline care conține **16**
constatări Medium după eliminarea a două wrapper-e experimentale nefolosite; erau
17 înainte de curățenie. Valoarea 111 din versiunea inițială a raportului a fost o
eroare de numărare. Gate-ul detectează regresii față de inventarul real.

**Impact concret**

Un build verde nu înseamnă acoperire globală și nici SAST curat. Cod nou din
modulele neincluse poate avea coverage zero, iar finding-urile baseline pot rămâne
reale și netriate.

**Fix recomandat**

Adaugă coverage global + branch/diff coverage, praguri pentru workflow-urile
financiare și frontend. Triază fiecare finding Bandit, documentează fals-pozitivele
punctual și micșorează baseline-ul; nu accepta baseline permanent fără owner.

**Verificare obligatorie**

Publică rapoarte complete în CI și blochează scăderea coverage-ului sau creșterea
datoriei baseline.

---

### M-53 — Backendul și workerul rulează ca același utilizator uman cu acces write larg
**Severitate:** Major
**Categorie:** Hardening host / blast radius
**Locație exactă:** `ops/systemd/unihub-backend.service:11-27`, `unihub-worker.service:10-27`

**Ce este greșit**

Ambele servicii rulează ca `User=andrei` și au `ReadWritePaths=/opt/Mobiup`.
Flagurile systemd sunt bune, dar identitatea și suprafața write rămân foarte largi.

**Impact concret**

Compromiterea backendului permite modificarea codului, datelor și altor resurse din
`/opt/Mobiup`, iar backendul și workerul se pot afecta reciproc.

**Fix recomandat**

Creează utilizatori dedicați fără login, separați pentru web și worker. Montează
codul read-only și permite write numai în directoarele exacte de spool/output.
Folosește credențiale DB/Google distincte.

**Verificare obligatorie**

`systemd-analyze security` și teste de filesystem trebuie să dovedească imposibilitatea
modificării codului și a directoarelor altui serviciu.

---

### M-54 — Un singur proces backend și un singur host sunt punct unic de cădere
**Severitate:** Major
**Categorie:** Scalabilitate / disponibilitate
**Locație exactă:** `ops/systemd/unihub-backend.service:16`, `unihub-worker.service:16`

**Ce este greșit**

Uvicorn pornește cu `--workers 1`, iar arhitectura operațională versionată arată o
singură unitate web și una worker. Mai multe operații CPU/blocking rulează încă în
procesul web.

**Impact concret**

Un crash, OOM, deploy sau parser blocant oprește întreaga aplicație. Nu există
rolling restart sau failover.

**Fix recomandat**

Elimină mai întâi munca blocking din web, apoi rulează cel puțin două instanțe
stateless în spatele unui load balancer, cu sesiuni în Valkey și deploy rolling.
Separă workerii pe clase de workload.

**Verificare obligatorie**

Oprește o instanță în timpul load testului; traficul trebuie să continue fără
eroare vizibilă.

---

### M-55 — Dependențele Python nu sunt complet reproductibile
**Severitate:** Major
**Categorie:** Supply chain / reproducibilitate
**Locație exactă:** `backend/requirements.txt:3-24`

**Ce este greșit**

Mai multe dependențe sunt exprimate ca limite minime (`>=`) fără lock complet și
hash-uri. O instalare nouă poate rezolva versiuni tranzitive diferite de cele
testate ieri.

**Impact concret**

Rollbackul sau rebuildul poate produce alt artefact, inclusiv incompatibilități sau
vulnerabilități noi, deși commitul este identic.

**Fix recomandat**

Generează lock determinist pentru runtime și dev cu hash-uri (`pip-tools`, uv sau
echivalent), construiește wheelhouse/artefact imutabil și promovează același
artefact între medii.

**Verificare obligatorie**

Două builduri curate ale aceluiași commit trebuie să aibă același SBOM și aceleași
hash-uri de pachete.

---

### M-56 — Deploymentul și rollbackul nu sunt automatizate în repository
**Severitate:** Major
**Categorie:** Operațional / release engineering
**Locație exactă:** `.github/workflows/ci.yml:1-207`, `ops/systemd/README.md:3-23`

**Ce este greșit**

Workflow-ul se oprește la validare și source maps. Instalarea unităților, migrarea,
restartul, probele și rollbackul sunt instrucțiuni manuale. Scriptul de backup
menționat în documentație este extern repository-ului și nu a putut fi auditat.

**Impact concret**

Release-ul depinde de pași umani nereproductibili. Un deploy parțial poate lăsa
schema, codul și workerul pe versiuni diferite; rollbackul nu are dovadă automată.

**Fix recomandat**

Construiește artefact imutabil, pipeline cu environment approval, migration
one-shot, canary/health, restart coordonat și rollback automat la versiunea
anterioară. Versionează și testează procedura de restore.

**Verificare obligatorie**

Exercițiu trimestrial: deploy eșuat și restore din backup într-un mediu izolat,
măsurând RTO/RPO.

---

### M-57 — Modulele critice rămân monoliți cu responsabilități amestecate
**Severitate:** Major
**Categorie:** Arhitectură / mentenabilitate
**Locație exactă:** `backend/logging_config.py`, `backend/services/grile_monthly.py`, `backend/repositories/exports.py`, `src/components/Settings.tsx`, `src/components/Dashboard.tsx`

**Ce este greșit**

Fișierele concentrează sute până la peste o mie de linii, I/O, business rules,
state machine, prezentare, filesystem, Google API și serializare. Dimensiunea nu
este doar estetică; granițele de responsabilitate sunt slabe.

**Impact concret**

Review-ul devine superficial, testele trebuie să cunoască detalii interne, iar o
modificare într-un flux poate afecta altul. Zonele financiare și destructive sunt
cele mai greu de izolat.

**Fix recomandat**

Extrage pe use-case și side-effect boundary: calcul pur, repository, Google client,
artifact store, orchestrator, UI view-model. Refactorizează în pași mici cu teste
de caracterizare și hash/echivalență de rezultat.

**Verificare obligatorie**

Niciun modul de orchestrare financiară nu trebuie să combine parsing, calcul,
persistență și livrare în aceeași funcție.

---


# Constatări Minore

### m-01 — Documentația FastAPI/OpenAPI rămâne activă implicit în producție
**Severitate:** Minor
**Categorie:** Hardening
**Locație exactă:** `backend/main.py:129`

**Ce este greșit**

`FastAPI(...)` nu dezactivează `/docs`, `/redoc` și `/openapi.json` în producție.
Vite proxy include explicit rute pentru docs în dezvoltare.

**Impact concret**

Expune inventarul endpointurilor, modelelor și parametrilor dacă proxy-ul le
publică. Nu este o breșă singură, dar ajută enumerarea.

**Fix recomandat**

Dezactivează docs în producție sau protejează-le prin ACL/VPN și autentificare
administrativă.

**Verificare obligatorie**

Request extern neautentificat la docs/OpenAPI trebuie să primească 404/403.

---

### m-02 — Logul excepțiilor folosește path-ul brut, care poate conține identificatori
**Severitate:** Minor
**Categorie:** Privacy logging
**Locație exactă:** `backend/main.py:216-225`

**Ce este greșit**

Handlerul loghează `request.url.path`. Unele rute includ `agent_name`,
`person_id`, `visit_id` sau alte identificatoare în path.

**Impact concret**

Logurile pot reține mai multă informație personală decât este necesar.

**Fix recomandat**

Loghează template-ul rutei și hash-uiește/omite parametrii de identificare.

**Verificare obligatorie**

Test de log pe o rută cu nume de agent: numele nu trebuie să apară.

---

### m-03 — „Auditul” exportului salarial este declarat de client, nu garantat de server
**Severitate:** Minor
**Categorie:** Auditabilitate
**Locație exactă:** `backend/routers/salarii.py:74-89`, `src/components/ExportTableButton.tsx:24-31`

**Ce este greșit**

Frontendul trimite un eveniment înainte de a genera local workbookul. Exportul
poate eșua după log, iar un client custom poate citi datele fără a trimite audit.

**Impact concret**

Jurnalul nu demonstrează că un fișier a fost creat/descărcat și nici că toate
exporturile au fost înregistrate.

**Fix recomandat**

Pentru date sensibile, generează exportul server-side și loghează rezultatul real,
hash-ul și numărul de rânduri după succes.

**Verificare obligatorie**

Auditul trebuie să corespundă 1:1 cu un artefact livrat.

---

### m-04 — Metricile comerciale folosesc luna calendaristică a serverului și se actualizează rar
**Severitate:** Minor
**Categorie:** Observabilitate
**Locație exactă:** `backend/services/retail_metrics.py:31-65`

**Ce este greșit**

Luna este `datetime.now().strftime('%Y-%m')`, iar update-ul se face la startup și
după import. La început de lună sau când ultima lună importată diferă, gauge-urile
pot fi zero/stale.

**Impact concret**

Dashboardurile Prometheus pot semnala greșit că nu există activitate.

**Fix recomandat**

Derivă ultima lună completed și actualizează periodic, cu timestamp de prospețime.

**Verificare obligatorie**

Test la rollover de lună fără import nou.

---

### m-05 — UI promite drag-and-drop fără să îl implementeze
**Severitate:** Minor
**Categorie:** UX
**Locație exactă:** `src/components/Settings.tsx:178-213`

**Ce este greșit**

Textul spune „Click sau drag & drop”, dar componenta nu are `onDrop` sau
`onDragOver`.

**Impact concret**

Utilizatorul încearcă o interacțiune care nu funcționează.

**Fix recomandat**

Implementează dropzone accesibilă sau elimină afirmația și folosește picker nativ.

**Verificare obligatorie**

Test E2E drag-and-drop sau text corectat.

---

### m-06 — Eroarea importului promo este afișată cu stil de succes
**Severitate:** Minor
**Categorie:** UX / error state
**Locație exactă:** `src/components/Settings.tsx:286-289`

**Ce este greșit**

Mesajul promo este randat întotdeauna în card emerald, inclusiv când catch-ul setează
un mesaj de eroare.

**Impact concret**

Utilizatorul poate interpreta un import eșuat drept succes.

**Fix recomandat**

Păstrează tipul mesajului și folosește semantică/culoare/icon distinctă pentru
eroare.

**Verificare obligatorie**

E2E cu răspuns 400 trebuie să afișeze alertă roșie și `role=alert`.

---

### m-07 — Polling-ul importului nu este anulat la unmount și are timeout egal cu jobul
**Severitate:** Minor
**Categorie:** Frontend jobs
**Locație exactă:** `src/components/Settings.tsx:26-29`, `src/components/Settings.tsx:236-254`

**Ce este greșit**

Bucla poate rula până la 1200 × 1,5 secunde, fără AbortController sau cleanup.
Intervalul total este 30 minute, egal cu timeout-ul workerului.

**Impact concret**

Navigarea nu oprește polling-ul, iar jitter-ul de final poate raporta timeout exact
când jobul termină.

**Fix recomandat**

Folosește query polling resumabil, backoff, abort și status durabil; acordă marjă
față de timeoutul jobului.

**Verificare obligatorie**

Test unmount și finalizare la limita timeoutului.

---

### m-08 — Legenda „Vânzări” din grafic folosește culoarea greșită
**Severitate:** Minor
**Categorie:** UI chart
**Locație exactă:** `src/components/dashboard/HistoryDashboard.tsx:250-256`; confirmat în captura „Evoluție lunară”

**Ce este greșit**

Bara nu are `fill` explicit, iar culorile sunt aplicate numai pe `Cell`. Legenda
Recharts folosește culoarea implicită, vizibilă ca pătrat negru în captură.

**Impact concret**

Legenda contrazice datele vizuale și reduce încrederea în grafic.

**Fix recomandat**

Setează `fill` pe Bar sau implementează legendă custom sincronizată cu seriile.

**Verificare obligatorie**

Visual regression pe tema light/dark.

---

### m-09 — Tooltip-ul implicit KPI acoperă graficul pe mobil
**Severitate:** Minor
**Categorie:** UI chart mobil
**Locație exactă:** `src/components/dashboard/HistoryDashboard.tsx:283-310`; confirmat în captura „Trend KPI”

**Ce este greșit**

Tooltip-ul Recharts implicit este prea mare pentru viewportul mobil și maschează o
parte importantă a seriei.

**Impact concret**

Utilizatorul pierde contextul tocmai când inspectează o valoare.

**Fix recomandat**

Folosește tooltip compact, poziționare controlată și un panou de detaliu la tap.

**Verificare obligatorie**

Test vizual la lățime 360-430 px.

---

### m-10 — Animațiile nu respectă `prefers-reduced-motion`
**Severitate:** Minor
**Categorie:** Accesibilitate
**Locație exactă:** `src/components/MainLayout.tsx:183-198`, `src/components/MainLayout.tsx:329-333`

**Ce este greșit**

Sheet-ul folosește spring animation, iar tabul activ folosește layout animation
fără variantă reduced-motion.

**Impact concret**

Poate provoca disconfort utilizatorilor sensibili la mișcare.

**Fix recomandat**

Dezactivează sau simplifică animațiile când media query-ul cere reduced motion.

**Verificare obligatorie**

Test browser cu `reducedMotion: 'reduce'`.

---

### m-11 — Filtrele persistate în localStorage pot trece de la un utilizator la altul pe același device
**Severitate:** Minor
**Categorie:** Privacy UX
**Locație exactă:** `src/App.tsx:35-42`, `src/App.tsx:145-155`, `src/auth/AuthContext.tsx:93-107`

**Ce este greșit**

Cheile nu sunt namespaced după `sub`, iar logoutul nu le șterge.

**Impact concret**

Următorul utilizator vede selecțiile de agent/magazin și poate porni într-un scope
nepotrivit.

**Fix recomandat**

Namespace per subject sau curățare la logout pentru state-ul organizațional.

**Verificare obligatorie**

Test cu două sesiuni succesive pe același profil de browser.

---

### m-12 — Reguli de business ale forecastului sunt hardcodate în script
**Severitate:** Minor
**Categorie:** Datorie tehnică / model governance
**Locație exactă:** `backend/scripts/run_ai_forecast_xreg.py:25-29`, `backend/scripts/run_ai_forecast_xreg.py:73-78`, `backend/scripts/run_ai_forecast_xreg.py:181-192`

**Ce este greșit**

IP-ul implicit, magazinele excluse, data schimbării de preț și lunile „peak” sunt
constante în cod.

**Impact concret**

Regula expiră sau se schimbă fără trasabilitate de model și poate rămâne activă
accidental în rulări viitoare.

**Fix recomandat**

Mută-le într-o configurație versionată per run, salvată în metadata forecastului.

**Verificare obligatorie**

Fiecare run trebuie să poată fi reprodus din config + commit + date.

---

### m-13 — Terminologia și formatarea numerică sunt inconsistente
**Severitate:** Minor
**Categorie:** UX / design system
**Locație exactă:** Capturile mobile și componentele Dashboard/Settings/Salarii

**Ce este greșit**

Apar simultan `AI Forecast`, `Snapshot`, `ProcBon2Acc`, `PRCFOCUS/ACCQTTY`, `k`,
`mil.`, separatori și prescurtări diferite.

**Impact concret**

Compararea valorilor între module este mai grea, iar utilizatorii noi nu înțeleg
acronimele.

**Fix recomandat**

Definește glosar user-facing și formatare centrală pe locale pentru bani, cantități
și procente.

**Verificare obligatorie**

Snapshot tests pe formattere și review UX al nomenclaturii.

---

### m-14 — Fallback-ul etichetei HTTP poate folosi path brut și crește cardinalitatea metricilor
**Severitate:** Minor
**Categorie:** Observabilitate
**Locație exactă:** `backend/main.py:132-155`

**Ce este greșit**

Dacă Starlette nu a rezolvat încă ruta, labelul `handler` cade pe
`request.url.path`.

**Impact concret**

Scanări cu multe path-uri unice pot crește cardinalitatea Prometheus și memoria.

**Fix recomandat**

Normalizează toate rutele necunoscute la o etichetă fixă `unmatched`.

**Verificare obligatorie**

Test cu 10.000 path-uri random: numărul seriilor trebuie să rămână constant.

---

### m-15 — Auditul de dependențe nu acoperă complet toolchain-ul de dezvoltare executat pe runner
**Severitate:** Minor
**Categorie:** Supply chain CI
**Locație exactă:** `.github/workflows/ci.yml:42-43`, `.github/workflows/ci.yml:157-173`

**Ce este greșit**

`pip-audit` verifică requirements runtime, iar `npm audit` folosește `--omit=dev`.
Totuși, dependențele dev sunt instalate și executate pe runnerul self-hosted.

**Impact concret**

O vulnerabilitate/RCE în toolchain-ul de test/build nu este prinsă de gate-ul
runtime.

**Fix recomandat**

Auditează separat dev dependencies, generează SBOM și izolează runnerul astfel încât
compromiterea toolchain-ului să nu atingă producția.

**Verificare obligatorie**

CI trebuie să publice rezultate runtime și dev distincte.

---


# Ce cedează primul la o creștere de 10×

## 1. Integritatea master data la import

Primul incident grav nu va fi un server lent, ci un fișier incomplet care redefinește universul de magazine. C-01 afectează toate modulele din aval. La volum și frecvență mai mare de import, probabilitatea unui fișier parțial crește.

## 2. Coada unică și transportul fișierelor prin Valkey

Un singur worker, `max_jobs=1`, primește importuri, verificări și operații Google. Raw Excel trece prin Valkey. La 10×, backlogul, memoria și timpul de așteptare devin nesustenabile înainte ca PostgreSQL să fie problema principală.

## 3. Exporturile în RAM și achizițiile DB imbricate

Preview-ul calculează tot, workbook-urile sunt materializate integral, iar exportul incentive poate aștepta a doua conexiune din pool. Câteva exporturi concurente pot consuma pool-ul și memoria procesului web.

## 4. Fan-out-ul Dashboard pentru istoricul multi-lună

Frontendul poate lansa câte un `/dashboard/all` per lună, fiecare cu fan-out intern. O selecție mare multiplică rapid numărul de query-uri și timpul de ocupare al pool-ului.

## 5. Procesul web unic și hostul unic

Operațiile blocking încă prezente, exporturile și parser-ele rulează într-un singur worker Uvicorn. Un singur OOM, deploy sau request patologic oprește produsul.

## 6. Vizitele nelimitate și snapshotul stale

Arborele complet SQLite crește fără paginare, în timp ce snapshotul PostgreSQL se actualizează numai la restart. La 10×, apar simultan latență și contradicții între module.

## 7. UI-ul mobil

Capturile arată deja overlap, tooltip-uri prea mari, tabele foarte late și text extrem de mic. La adăugarea de KPI-uri, module și filtre, experiența devine impracticabilă înainte de orice problemă de backend.

---

# Analiza capturilor mobile

## Probleme confirmate vizual și în cod

1. **Bottom navigation acoperă ultimul conținut.** Se vede în Hub, Focus, Agents, Management și Settings. Codul folosește poziționare fixă și padding constant, fără safe-area sau măsurare dinamică.
2. **FAB-ul de filtre maschează carduri și grafice.** Poziția fixă `bottom-20 right-4` nu ține cont de conținut.
3. **Graficul „Evoluție lunară” are legendă neagră pentru bare mov.** Codul colorează `Cell`, nu seria Bar.
4. **Tooltip-ul „Trend KPI” acoperă o parte mare din grafic.** Tooltip-ul implicit Recharts nu este adaptat pentru telefon.
5. **Textul secundar, axele și etichetele de navigație folosesc frecvent 9–11 px.** Lizibilitatea este slabă în lumină puternică și pentru utilizatori cu vedere redusă.
6. **Tabelele de salarii și alte comparații sunt proiectate cu `min-width` mare.** Pe mobil, utilizatorul trebuie să facă scanare orizontală lungă.
7. **Densitatea Hub-ului este de dashboard desktop comprimat.** Sunt prea multe KPI-uri, serii și controale pe aceeași suprafață.
8. **Importul spune „drag & drop”, dar interacțiunea nu există.**
9. **Culoarea este folosită ca semnal principal în mai multe KPI-uri.** Statusul trebuie întărit prin text/iconografie.
10. **Terminologia și formatarea numerelor diferă între ecrane.**

## Direcția corectă

Nu rezolva aceste probleme doar prin micșorarea fonturilor sau ascunderea coloanelor. Mobile trebuie tratat ca structură informațională distinctă: KPI primar, drill-down, carduri verticale, tabele compacte cu coloane selectabile și sheet-uri accesibile.

---

# Controale bune identificate

Menționate scurt, deoarece nu anulează riscurile:

- OIDC/JWKS validează RS256, issuer, audience și claims obligatorii și are cache bounded/fail-closed.
- BFF-ul folosește Authorization Code + PKCE, nonce, sesiuni Valkey criptate, cookie `__Host` HttpOnly și CSRF pentru metode nesigure.
- Accesul la salarii, importuri, P&L și finalizări privilegiate este verificat server-side.
- SQL-ul runtime inspectat folosește în general parametri; fragmentele dinamice sensibile au allowlist/validare.
- Migrațiile au runner separat, advisory lock și manifest cu checksum.
- Logging-ul are redaction pentru tokenuri, DSN și CNP și răspunsurile 500 nu expun stacktrace.
- Exporturile OpenPyXL folosesc o limită centrală pentru formula injection.
- Unitățile systemd activează multe opțiuni de hardening.
- Ultimul CI inspectat a trecut auditul dependențelor runtime configurat.

## Dependențe vulnerabile

Nu am găsit și nu inventez un CVE concret în starea auditată. Ultimul CI verde a trecut:

- `pip-audit -r requirements.txt --strict`;
- `npm audit --omit=dev --audit-level=high`.

Scanările au fost rerulate local și în CI pe merge-ref/main. Riscul rămas este că
`npm audit` exclude dev dependencies, Python nu are lock complet cu hash-uri, iar
un audit verde la un moment dat nu garantează viitorul.

---

# Limite rămase după reconciliere

1. **Nu s-au făcut scrieri business sau reseturi pe producție.** Reconcilierea DB a
   fost read-only; cele trei magazine prezente în iunie și absente în iulie sunt
   inactive și nu au fost reactivate. Orice schimbare de statut cere decizie business.
2. **Nu s-a executat `EXPLAIN ANALYZE` pe producție și nu s-a făcut load test la
   10× volum.** Finding-urile de scalare rămân deschise până la măsurare dedicată.
3. **Suprafața publică Retail este închisă, dar proxy-ul global nu a fost extins în
   scope.** Au fost verificate public 404 pentru `/metrics`, `/docs`, `/redoc` și
   `/openapi.json`; modificarea a rămas strict în stansa Retail.
4. **Planul privat curent nu oferă required environment reviewers.** Workflow-ul
   de deploy rămâne fail-closed prin approval-ul local root-only, interactiv,
   one-time și legat de run/SHA/hash; aceasta este limita explicită a platformei,
   nu o aprobare implicită sau o disciplină informală.
5. **Granturile efective Google Drive/Sheets nu au fost inventariate.** Codul,
   scope-urile, manifestele și efectele au fost auditate, dar separarea identităților
   Google rămâne finding deschis.
6. **Peer-ul TimesFM a fost confirmat ca peer Tailscale, nu ca destinație publică.**
   Nu au fost auditate ACL-ul complet, retenția și contractul procesatorului.
7. **Serviciile, health-ul local/public și starea systemd au fost verificate, dar
   nu s-a făcut o analiză exhaustivă GlitchTip/Prometheus pe perioade lungi.**
8. **Documentele locale inițiale au fost reconciliate în worktree-ul separat.**
   Exemplarele vechi necomise din checkout-ul live au fost eliminate explicit de
   proprietar înainte de rollout. Arhivele și planurile închise redundante au fost
   eliminate din `HEAD`, rămân recuperabile din Git, iar un test de igienă previne
   reintroducerea `docs/archive/`; deployul cere un worktree complet curat.
9. **Redesignul „Ajustări” a fost mapat de la `aba3fa0` la `d08add1`, revizuit și
    trecut prin typecheck/build/unit/Playwright mobil, desktop și accessibility.**
    Acceptanța post-deploy a reconfirmat health-ul și bundle-ul frontend verificat.

Aceste limite păstrează explicit riscurile reziduale; nicio intrare `Deschis` sau
`Parțial` din matrice nu trebuie interpretată drept închisă prin absența unui defect
observat în testele actuale.

---

# Ordinea rămasă după rollout

1. publică această dovadă finală prin PR și confirmă CI verde pe SHA-ul final `main`;
2. redeployează artefactul final dacă SHA-ul se schimbă numai prin documentație;
3. publică tagul și GitHub Release `v2.0.1` fără a muta `v2.0.0`;
4. continuă finding-urile `Deschis` în pachetele P1/P2, în ordinea planului.

**Concluzie:** P0 este închis în cod, CI și producție, iar redesignul dintre
`aba3fa0` și `d08add1` este validat. Rolloutul, verificarea publică și rollbackul
au fost demonstrate; rămân numai publicarea evidenței finale și a release-ului.
