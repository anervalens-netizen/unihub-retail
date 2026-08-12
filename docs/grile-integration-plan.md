# Integrarea Grile în UniHub Retail

Acesta este contractul canonic curent pentru integrarea Grile. Planul istoric de
cutover a fost închis; implementarea activă rulează nativ în Retail, fără proxy
către aplicația Grile veche și fără schimbarea linkurilor permanente Google.

## Surse de adevăr

- arhitectură și boundary-uri: `APP_ARCHITECTURE.md`;
- idempotency, manifest și reset: `docs/engineering/h11-grile-monthly-idempotency.md`;
- siguranța formulelor: `docs/engineering/h12-spreadsheet-formula-safety.md`;
- schema curentă: migrările din `backend/db/migrations/` și manifestul lor;
- runtime: `backend/routers/grile.py` → servicii → repositories;
- UI: `src/components/GrileSubtab.tsx` și `src/components/GrileMonthlyPanel.tsx`.

`backend/db/schema_v2.sql` este un baseline înghețat pentru instalări noi. Orice
evoluție de schemă se face prin migrare expand/migrate/switch/contract, fără
rescrierea baseline-ului sau a migrărilor aplicate.

## Contractul verificării

Pilotul V2 din `Agenti -> Grile` rămâne separat de cohorta oficială
`grile_sheets`. Cohorta August 2026 are 21 de foi active în registrul canonic
`backend/services/grile_pilot_v2_registry.py`; foile Delia și copiile cu program
neconfirmat nu fac parte din registrul activ. Endpointul read-only
`/api/grile/pilot-v2` citește snapshotul JSON atomic produs de worker după o
sincronizare completă, îl grupează după managerul curent din Retail și compară
targetul și realizatul cu raportarea Retail și cu ultima proiecție V1. Nu
apelează Google Sheets, nu rezervă runuri, nu persistă observații și nu
participă la finalizare, arhivare sau reset.

Writerul izolat `grile_pilot_v2_sync` proiectează în foi numai date
autoritative Retail: vânzări zilnice pe cod agent, target, forecast, SIM și
incentive. Citirea PostgreSQL este repeatable-read, iar o eroare de sursă sau
Google păstrează ultima proiecție bună. Writerul actualizează exclusiv `Liste`,
headerul din `Rezumat & Program` și tabul `Vânzări & Incentive`; programul,
concediile și selecțiile manuale de zile suplimentare nu sunt rescrise.
Reviziile sales/Campaigns și revizia schemei writerului fac actualizarea
idempotentă; o versiune nouă de writer forțează o primă reproiectare completă.
După succesul tuturor celor 21 de foi, workerul persistă atomic snapshotul
`backend/outputs/grile/pilot-v2-overview-2026-08.json`; un eșec păstrează ultima
versiune bună. Workerul încearcă o recuperare la startup. În fluxul normal,
promovarea raportului de vânzări solicită publicarea Campaigns, iar publicarea
reușită solicită exact o sincronizare V2; nu există polling orar sau trigger V2
duplicat direct după import. Toate apelurile Google de scriere sunt serializate
prin adapterul thread-affine; V1 rămâne neatins.

`POST /api/grile/run` rezervă și pune în coadă exclusiv o verificare read-only.
Jobul citește valorile și metadatele Google necesare, compară cu starea Retail și
persistă rezultatul verificării; nu modifică `agent_targets` și nu scrie în
Google Sheets.

Pentru fiecare lună poate exista cel mult un run `queued` sau `running`.
Rezervarea PostgreSQL precedă enqueue-ul. Heartbeat-ul rulează independent la
30s cât timp jobul este viu, iar progresul este salvat după fiecare magazin.
Orice excepție, timeout sau anulare ARQ încearcă terminalizarea CAS în `failed`.
Startupul workerului închide runurile `running` moștenite; reconcilierea
periodică și citirile overview/status expiră un `running` fără heartbeat după
5 minute și un `queued` după două ore. Rândul runului și observațiile deja
valide rămân auditabile; nu se face `DELETE`. UI blochează retry numai când
backendul returnează `run.active=true` după reconciliere.

Scope-urile clientului de verificare V1 sunt strict read-only:

- `spreadsheets.readonly` pentru valorile grilei;
- `drive.metadata.readonly` pentru metadatele necesare monitorizării.

Endpointul V2 nu construiește niciun client Google. Writerul V2 folosește
separat clientul operațional cu drept de scriere `spreadsheets`/`drive`; acest
client nu este folosit de endpointurile read-only.
Credentialul operațional rămâne `0640`, cu grupul
`unihub-grile-artifacts`: identitățile `unihub-grile` și `unihub-web` îl pot
citi, iar workerii de export rămân în afara grupului.

Transportul Google are timeout HTTP implicit 30s, configurabil prin
`GRILE_GOOGLE_HTTP_TIMEOUT_SECONDS` între 1 și 120s. La failure/cancellation,
taskurile async de persistență sunt anulate și așteptate înainte de întoarcerea
jobului; executorul oprește coada bounded, iar fiecare thread își închide
propriile servicii Google în `finally`.

Contractul UX activ din `2026-07-17` are `15` rânduri în tabelul
`Suplimentar`. Verificarea citește `Grila!B32:G46` și include toate datele din
`D32:D46` în acoperirea zilelor. Acest interval trebuie să rămână sincronizat
cu modelul și grilele permanente din `/opt/Mobiup/grile-salarii`.

## P1.1 — observații, proiecție curentă și refresh

`035_grile_observation_fencing.sql` păstrează fiecare citire în
`grile_store_observations`, append-only. O observație este legată exact de un
full run sau de un refresh per magazin; runtime-ul are drepturi `SELECT/INSERT`
pe tabel, nu `UPDATE/DELETE`.

Full run-ul și `POST /api/grile/stores/{site_code}/refresh` rezervă mai întâi o
generație monotonă per `(run_month, site_code)`. Endpointul de refresh returnează
rapid `operation_id`/`job_id`; Google este citit numai de workerul operațional.
O singură operație refresh poate fi `queued|running` per magazin-lună, iar workerul
face CAS `queued -> running`. Eșecul publicării cozii marchează reservation-ul
`failed`, nu îl lasă suspendat.

`grile_store_current_status` este doar proiecție. O observație reușită o poate
actualiza numai dacă `(generation, checked_at)` este strict mai nou decât cel
proiectat. Astfel un full run care a citit înaintea refresh-ului, dar termină după,
rămâne auditabil fără să rescrie ecranul. Generațiile pot avea goluri după o cursă
pierdută; nu pot regresa.

Ultima observație reușită (`last_success_*`) rămâne afișabilă. Ultima eroare
(`last_error_*`) și `stale_age_seconds` sunt metadate separate: o eroare Google
sau structurală nu șterge ultimul rezultat bun. Nu se face retry automat pentru
o observație deja claim-uită.

Pentru șabloanele `v3`, răspunsul `batchGet` se validează înainte de analiză:
exact șase range-uri, în ordinea canonică `K5,L5,P5:P35,U5:U35,Z5:Z35,B46:G60`,
cu cardinalitatea/formele maxime ale fiecăruia. Răspunsul lipsă, reordonat sau
malformat devine `STRUCTURAL_INVALID` fail-closed și este păstrat ca observație.

## P2.1 — latență observabilă

Workerul expune histograma Prometheus
`grile_store_refresh_phase_seconds{phase=...}`, cu faze fixe:

- `queue_wait`: rezervare DB până la claimul workerului;
- `provider`: credentials + Google Sheets/Drive I/O;
- `db`: claim, citiri Retail și persistența observației/proiecției;
- `total`: rezervare până la finalul jobului, inclusiv queue wait.

Metricul nu are label de lună, magazin, utilizator sau job, deci cardinalitatea
rămâne bounded. Enqueue p95 se măsoară separat din histograma HTTP a endpointului.
Gate-ul de performanță nu se declară acceptat înainte de șapte zile curate și
minimum 100 de requesturi pe rută.

## Targete agent: diff și sincronizare

Citirea targetelor agent este separată în două operații:

1. dry-run/diff calculează schimbările propuse și dovedește prin hash că starea
   completă `agent_targets` a rămas identică;
2. sync rulează numai în worker și necesită grupul OIDC dedicat, CSRF, rate
   limit, audit și identitatea stabilă OIDC `sub`.

Un utilizator autentificat obișnuit poate verifica Grile, dar primește 403 la
sync. Apply este fail-closed dacă un sheet activ nu poate fi citit complet,
există target invalid sau mapping ambiguu, ori starea s-a schimbat față de
diff-ul aprobat. Retry-ul concurent este rezervat în DB și nu poate dubla apply.

## Finalizare, arhivare și reset

Operațiile lunare sunt joburi distincte, rezervate în PostgreSQL înainte de
enqueue. Finalizarea validează strict toate valorile numerice, registry-ul,
magazinele și agenții așteptați. Orice eroare, timeout, răspuns Google incomplet,
agent lipsă sau coverage incomplet marchează operația `failed`; componentele
opționale de comision goale sunt zero. O grilă asociată unei locații marcate
`INCHIS`, fără ore, comisioane sau plăți suplimentare, poate avea zero agenți,
chiar dacă șablonul păstrează salariul de bază și bonurile implicite. Un artefact
parțial nu primește calea oficială.

Manifestul persistent conține luna și operația, coverage așteptat/procesat,
totaluri de control, zero erori, hashurile SHA-256 ale artefactelor,
`requested_by_sub`, `approved_by_sub` și statusul verificabil. Arhivarea aprobă
numai cea mai nouă finalizare verificată.

Resetul live acceptă numai cel mai nou manifest de arhivă verificat și aprobat.
Înainte de orice clear păstrează sursa recuperabilă și checkpointul per magazin.
Un checkpoint `uncertain` blochează retry-ul automat până la reconcilierea
manuală. La eșec, valorile sunt restaurate și verificate; zero efecte destructive
neconfirmate este condiție de succes.

Resetul curent golește `Grila!B32:F46`, nu vechiul interval `B32:F37`, astfel
încât niciunul dintre cele 15 rânduri suplimentare nu poate trece accidental în
luna următoare. Coloana `G32:G46` rămâne formulă și nu este ștearsă.

## Date și identitate

- cheia magazinului este `site_code`; linkul Google permanent nu se recreează;
- cohorta Grile cere simultan `grile_sheets.is_active = true` și
  `stores.is_active = true`; un reseed preia starea magazinului și nu poate
  reactiva grilele locațiilor închise;
- Overview proiectează ultima verificare pe cohorta Grile activă curentă, fără
  să rescrie rezultatul istoric persistent;
- ierarhia și valorile expected provin din Retail DB;
- lunile API/DB folosesc `YYYY-MM`;
- auditul de autorizare persistă OIDC `sub`, nu emailul;
- logurile nu includ nume de agenți, salarii, identificatori personali sau date
  comerciale;
- verificările live sunt read-only în afara unui rollout autorizat explicit în
  conversația operațională.

## Operare și verificare

Workerul Retail serializează joburile grele. După o schimbare Grile se rulează
secvențial testele API, worker, autorizare, efect DB, fail-closed și retry din
suitele `backend/tests/test_grile_*`, urmate de gate-urile complete din
`AGENTS.md`.

Deployul urmează calea proporțională cu riscul din ADR-005. Calea formală cu
artefact CI și approval one-time rămâne disponibilă pentru operații cu risc
mare; cererea explicită din conversație autorizează agentul să o ducă până la
capăt. Înaintea unei migrări sau operații destructive se verifică backupul și
rollbackul. Nu se folosesc date live pentru testare.

## Evidență rollout writer V2 2026-08-12

- candidatul exact `59dc1523965c7d51aa49b7ccd895f6a30064a8e2` a trecut
  runul exact-main `31621037976`; artefactul și manifestul au fost verificate
  prin SHA-256 înainte de approval;
- deployul unic `31623615626` a promovat același SHA, cu health/readiness și
  toate cele șase servicii Retail active;
- un singur sync post-fix, sub identitatea `unihub-grile`, a actualizat 21/21
  foi active; toate raportează `Sincronizat · raport oficial`, revizia writer
  `1`, aceeași revizie sales și aceeași revizie Campaigns;
- foile Delia și copiile neconfirmate au rămas în afara cohortei active.
- hotfixul live-first a mutat citirea UI pe snapshotul workerului și a eliminat
  pollingul Google orar, triggerul duplicat și rate-limitul de job de pe GET;
  autentificarea a rămas obligatorie;
- verificarea live a măsurat aproximativ `50.58 ms` în backend, `40–72 ms` până
  la headers și aproximativ `414 ms` pentru ecranul complet; redeschiderea
  tabului a refolosit starea fără alt request V2, iar refreshul manual a răspuns
  `200` fără alertă. Acceptanța finală a fost confirmată de utilizator.

## Evidență rollout UX 2026-07-17

- grilele permanente și modelul oficial au fost actualizate in-place prin
  commitul `grile-salarii@5c5e3ed789bf5df6ea920f4191253202c2b5f546`;
- contractul Retail `B32:G46` / `B32:F46` a fost introdus prin
  `unihub-retail@0b85fc3d47084e0845ea3a3dd759fbe9131e7a2b`;
- CI Grile Salarii `29569631485` și CI Retail `29569636906` au trecut;
- verificarea locală Retail a trecut `1267` teste backend izolate, `228` teste
  frontend, typecheck, mypy, lint, build și probele publice `/readyz` și `/`.
