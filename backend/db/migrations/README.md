# db/migrations/

Numbered SQL migrations aplicate la boot de `apply_pending_migrations()`
din `db/connection.py`.

## Convenție

- Numele: `NNN_descriere_scurta.sql` (3 cifre obligatorii, lowercase + underscore).
- Exemplu valid: `001_add_store_index.sql`, `042_rename_agent_col.sql`.
- Fiecare fișier rulează într-o tranzacție; tracked în tabela `schema_migrations`.
- Migrations sunt **imutabile** după ce au rulat în producție. Dacă greșești,
  adaugi o migration nouă care corectează, nu editezi istoric.

## Când folosești migration vs schema_v2.sql

- **`schema_v2.sql`** = baseline pentru instalare nouă (fresh install).
  Fiecare `CREATE TABLE IF NOT EXISTS` trebuie actualizat aici ca să reflecte
  starea curentă completă.
- **`migrations/NNN_*.sql`** = delta pentru DB-uri existente (dev & prod).
  Orice `ALTER TABLE`, `CREATE INDEX`, backfill DML merge aici.

Workflow tipic pentru schimbare de schemă:
1. Adaugi migration `NNN_add_column_foo.sql` cu `ALTER TABLE ... ADD COLUMN ...`
2. Actualizezi `schema_v2.sql` să includă coloana direct în `CREATE TABLE`
3. La boot, DB-urile existente aplică doar migration-ul; instalările noi
   iau forma completă direct din `schema_v2.sql`.

## Idempotență

Migrations ar trebui să fie idempotente când e posibil (`IF NOT EXISTS`,
`CREATE INDEX CONCURRENTLY IF NOT EXISTS`). Tracking-ul în
`schema_migrations` ne acoperă pentru operațiuni care nu pot fi (DML seed,
UPDATE unic).

## Testare locală

```bash
cd backend
source venv/bin/activate
pytest tests/test_migrations.py -v
```
