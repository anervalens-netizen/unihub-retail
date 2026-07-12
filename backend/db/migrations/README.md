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
4. Instalarile noi aplica baseline-ul inghetat, marcheaza migrations deja
   incorporate, apoi ruleaza toate delta-urile ulterioare.

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
