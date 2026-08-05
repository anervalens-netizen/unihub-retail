# Retail systemd units

This directory plus repository-root `unihub-worker.service` are the versioned
source of truth for the Retail web, operations worker, dedicated import worker
and one-shot migration services. Production copies live under
`/etc/systemd/system`.

Install a reviewed unit with `sudo install -m 0644`, run
`sudo systemctl daemon-reload`, then restart only the affected service. The
migration unit remains one-shot and must never be enabled as a long-running
daemon.

Before installation:

```bash
systemd-analyze verify \
  ops/systemd/unihub-backend.service \
  unihub-worker.service \
  ops/systemd/unihub-import-worker.service \
  ops/systemd/unihub-retail-migrate.service
```

After a backend restart, `/livez` proves that the process responds and
`/readyz` proves that PostgreSQL and the BFF session backend are usable.
`/health` remains a compatibility alias for `/readyz`.

## P0 lifecycle și evidence

`unihub-retail-migrate.service` este one-shot și citește `.env.migrations`; web/worker nu execută DDL. Baseline-ul P0 `f9c0b1efe15686bcda532d22528e6e2644925aec` a introdus 032–034; release-ul `v2.1.0` verifică prin manifest întregul lanț aditiv 032–036 înaintea oricărui restart.

Workerul operațional are `TimeoutStopSec=2460`, import workerul `1860`, backendul `75`, iar migration runnerul `TimeoutStartSec=300`. Aceste valori aliniază shutdown-ul controlat, dar nu închid benchmarkul P0.5 și nu justifică ridicarea limitelor de memorie ca substitut pentru remediere.

Recovery-ul P0 păstrează ultima generație bună: sales folosește generation head/CAS și rollback auditabil, P&L folosește pointer/pre-image shadow fără apply runtime, iar salary batch revine tranzacțional. Dacă health sau manifestul nu se reconciliază, oprește promovarea și marchează `recovery_required`.

## P1-A — identități DB per proces

Unitățile declară fail-closed `UNIHUB_DB_PROCESS_AUTHORITY`: backend `web`,
workerul normal `operations`, import workerul `sales_import`, iar one-shotul
`migrate`. Fișierele root-protected sunt separate: `.env`, `.env.worker`,
`.env.import-worker`, `.env.migrations`. Fiecare conține DSN-ul unui singur
LOGIN: `unihub_web`, `unihub_operations_worker`, `unihub_import_worker`,
respectiv `unihub_migration_runner`. Orice proces production fără autoritate
explicită refuză startupul. Nu copia același DSN între procese și nu
introduce `DATABASE_URL` ca fallback în fișierul de migrare.

Ordinea de cutover este: oprește backendul și cei doi workeri; backup și business hashes;
aplică 040/041 cu identitatea administrativă existentă și flagul one-shot
`UNIHUB_DB_AUTHORITY_CUTOVER_BOOTSTRAP=1`, fără autoritate de proces; creează cele patru
LOGIN-uri în boundary-ul operațional separat; atașează contractele exacte cu
provisionerul; verifică zero sesiuni/membri și setează `unihub_runtime NOLOGIN`
cu scriptul controlat; scrie DSN-urile fără a le afișa; instalează unitățile și rulează
`daemon-reload`; execută deployul formal care repornește toate procesele. Orice
principal/flag/membership diferit oprește startupul.

Flagul de bootstrap nu se persistă în niciun `.env` sau unit. Runnerul îl
acceptă doar când exact 040/041 sunt restante pe baza existentă, sub
superuserul autentificat direct; după 041 devine automat inutilizabil.

Nu porni workerii între migrare și finalizarea cutoverului. După 040/041,
rollbackul la sursă cu manifest vechi este deliberat refuzat; deployul păstrează
handle-ul și candidatul la `recovery_required`, apoi cere roll-forward verificat.

## P1.4 availability și config

ARQ este opțional numai pentru procesul web; PostgreSQL și sesiunea/rate-limit
Valkey rămân obligatorii. Cu portul cozii închis, `/readyz` trebuie să rămână
200 și citirile autentificate funcționale, în timp ce enqueue răspunde bounded
503. Recovery-ul cozii este lazy, single-flight și fără restart; publish-ul
incert se reconciliază prin job ID și rezervarea PostgreSQL, fără retry orb.

Configul este validat separat pentru web/operations/import. Relațiile minime
sunt `DB_POOL_MIN_SIZE <= DB_POOL_MAX_SIZE`, minimum două conexiuni web,
`DB_LOCK_TIMEOUT_MS < DB_STATEMENT_TIMEOUT_MS`, buget ARQ de conectare <=3s,
`ARQ_MAX_CONNECTIONS >= ARQ_MAX_JOBS`, completion wait >= job timeout și
retention >= cea mai lungă fereastră. Valorile versionate `2460/2400` pentru
operations și `1860/1800` pentru import păstrează marja de shutdown de 60s.

Web validează la startup și `DASHBOARD_REQUEST_DEADLINE_MS` (implicit 2500,
maximum 3000) plus `DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY <=
DB_POOL_MAX_SIZE - 2`. Config invalid oprește procesul înainte de trafic; nu se
ridică deadline-ul pentru a masca un query lent.
