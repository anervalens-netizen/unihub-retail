# db/migrations/

Numbered SQL migrations aplicate exclusiv de runnerul separat
`scripts/run_migrations.py`. Web-ul verifica read-only ca DB-ul este curent si
refuza startup-ul daca exista drift sau migrations neaplicate.

## Convenție

- Numele: `NNN_descriere_scurta.sql` (3 cifre obligatorii, lowercase + underscore).
- Exemplu valid: `001_add_store_index.sql`, `042_rename_agent_col.sql`.
- Fiecare fisier ruleaza intr-o tranzactie si este tracked in
  `schema_migrations` impreuna cu checksum-ul SHA-256.
- Migrations sunt **imutabile** după ce au rulat în producție. Dacă greșești,
  adaugi o migration nouă care corectează, nu editezi istoric.
- `manifest.json` este gate-ul Git pentru baseline si toate migrations.

## Când folosești migration vs schema_v2.sql

- **`schema_v2.sql`** = baseline inghetat pentru instalare noua. Nu se mai
  modifica dupa H-02.
- **`migrations/NNN_*.sql`** = delta pentru DB-uri existente (dev & prod).
  Orice `ALTER TABLE`, `CREATE INDEX`, backfill DML merge aici.

Workflow tipic pentru schimbare de schemă:
1. Adaugi migration `NNN_add_column_foo.sql` cu `ALTER TABLE ... ADD COLUMN ...`
2. Actualizezi `manifest.json` cu checksum-ul fisierului nou.
3. Rulezi unitatea `unihub-retail-migrate.service` inainte de restartul web.
   Unitatea citeste exclusiv `.env.migrations`, fisier root-protected care
   contine `MIGRATION_DATABASE_URL`/`DATABASE_URL` pentru owner. Web si worker
   folosesc rolul non-owner din `.env`.
4. Instalarile noi aplica baseline-ul inghetat, marcheaza migrations deja
   incorporate, apoi ruleaza toate delta-urile ulterioare.

## Migrațiile aditive P0–P1.3

Baseline-ul `schema_v2.sql` și migrațiile 001–031 rămân imutabile. Manifestul
release-ului `v2.1.0` include:

| ID | Fișier | SHA-256 | Contract |
| --- | --- | --- | --- |
| 032 | `032_store_pnl_shadow_generations.sql` | `a75f77c1a85fef1b39d5db11b9007d23114943b96554988566bb63e30a4923f5` | shadow generations, candidate/pre-image și pointer CAS; nu este citit de runtime |
| 033 | `033_sales_generation_staging_and_fencing.sql` | `b6e10b7198e01d7893fefe66f28879d8b363956e3a87be11f63e875df9193cb1` | staging, generation head și audit promote/rollback cu fencing |
| 034 | `034_salary_import_batch_provenance.sql` | `93dae9fa15c1b891e6484a8ddecc189e3bc412f2913066619288d0fd8938ec7f` | batch HR, source-line provenance și agregare per person_id |
| 035 | `035_grile_observation_fencing.sql` | `4afd71ef2c8e0f215bb2687d28d07ae5a7b76ebc2625b05fe3c638a315293b5f` | observații Grile append-only, claim/CAS per magazin și proiecție curentă separată |
| 036 | `036_target_rule_registry.sql` | `d722b1ef480b067651c37464c3462565ea2c9b4e5651c869e08932cd0c37b193` | registry Target append-only, snapshot/hash per scenariu și override auditabil |

Aplicarea se face numai prin `unihub-retail-migrate.service`, cu `MIGRATION_DATABASE_URL`, backup/read-only reconciliation și verificarea checksumului. Nu edita 032–036 după aplicare; corecția este o migrare nouă.

Migrațiile nu activează singure TVA live sau importul salarial live. Promotion pointer-ul P&L și batchul salary sunt contracte de audit/recovery; apply-ul financiar și reconcilierea HR rămân explicit blocate la P0.

## Idempotență

Migrations ar trebui să fie idempotente când e posibil (`IF NOT EXISTS`,
`CREATE INDEX CONCURRENTLY IF NOT EXISTS`). Tracking-ul în
`schema_migrations` ne acoperă pentru operațiuni care nu pot fi (DML seed,
UPDATE unic).

## Testare locală

```bash
cd backend
source venv/bin/activate
scripts/run_tests_isolated.sh -v --tb=short tests/test_migrations.py tests/test_migration_runner_db.py
```
