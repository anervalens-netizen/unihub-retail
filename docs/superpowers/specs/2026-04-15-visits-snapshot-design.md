# Design: visits_snapshot PG table

**Date:** 2026-04-15
**Branch:** `feature/visits-snapshot`
**Status:** Approved

## Problema

`hr.py` citește vizite din SQLite via `run_in_executor` (thread blocker) la fiecare
request `/api/hr/asm-performance` și `/api/hr/asm-performance/{name}/history`.
Nu se poate face JOIN cu date PG, iar fiecare request deschide o conexiune SQLite nouă.

## Soluție

Tabel PG `visits_snapshot` — agregatele din SQLite, upsert la boot + refresh manual.

Volum: ~20 ASMs × 24 luni = max 480 rânduri. Sync durează <500ms.
Platforma-Mobiup citește din același SQLite — nu afectăm sursa de adevăr.

## Schema

```sql
CREATE TABLE IF NOT EXISTS visits_snapshot (
    asm            TEXT NOT NULL,
    month          TEXT NOT NULL,  -- YYYY-MM
    total_visits   INT  NOT NULL DEFAULT 0,
    avg_completion NUMERIC(5,1),
    avg_duration   NUMERIC(6,2),
    distinct_stores INT NOT NULL DEFAULT 0,
    checklist_score NUMERIC(5,1),
    approved_pct    NUMERIC(5,1),
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (asm, month)
);
```

## Fișiere noi / modificate

1. **`backend/db/schema_v2.sql`** — adaugă tabelul
2. **`backend/services/visits_sync.py`** (nou) — `sync_visits_snapshot(conn, sqlite_path)`
   - Citește SQLite cu `run_in_executor` o singură dată la boot
   - Upsert în `visits_snapshot` via `INSERT ... ON CONFLICT DO UPDATE`
3. **`backend/main.py`** — apelează `sync_visits_snapshot` în lifespan după migrations
4. **`backend/routers/hr.py`** — înlocuiește cele 2 funcții `run_in_executor` cu query PG
5. **`backend/routers/admin.py`** — adaugă `POST /api/admin/sync-visits-snapshot`

## Comportament la boot

```
lifespan:
  init_db_pool → ensure_schema_current → apply_pending_migrations
  → ensure_default_users → prewarm_pool
  → sync_visits_snapshot (NOU)  ← upsert din SQLite în PG
  → prewarm_special_cards_cache → yield
```

## Criterii de succes

- [ ] `GET /api/hr/asm-performance` returnează aceleași valori ca înainte
- [ ] Nu mai există `run_in_executor` în hr.py pentru vizite
- [ ] `POST /api/admin/sync-visits-snapshot` returnează 200 + `{"synced": N}`
- [ ] pytest 78/78 trece
- [ ] `visits_snapshot` apare în schema_v2.sql
