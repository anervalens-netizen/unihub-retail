# Salarii DB Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import salary records from `salarii_simplu.db` (SQLite) into the UniHub PostgreSQL database as a new `salary_records` table, expose read-only endpoints, and add Pydantic models.

**Architecture:** SQLite file (`C:\Users\andre\Desktop\Workspace\unihub\salarii_simplu.db`) is read-only source-of-truth. We mirror `salary_records` into PostgreSQL using our existing migration system. The `company_name` field is stored as plain text (two values: 'Mobicell' / 'Mobiup') with an optional lightweight `companies` reference table for display names if needed later.

**Source schema (salarii_simplu.db → salary_records):**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | SQLite rowid |
| year | INTEGER | 2025 / 2026 |
| month | INTEGER | 1–12 |
| full_name | TEXT | Employee name |
| cnp | TEXT | CNP (PII) |
| total_salary | REAL | Total salary paid |
| company_name | TEXT | 'Mobicell' / 'Mobiup' |
| site_code | TEXT | ERP store code (links to existing stores table) |
| locatie | TEXT | Store location name |

**Source row count:** 3005 rows

---

## File Map

| File | Role |
|------|------|
| `backend/db/schema_v2.sql` | MODIFY — add `salary_records` table + indexes |
| `backend/models.py` | MODIFY — add Pydantic models |
| `backend/scripts/import_salarii.py` | CREATE — reads SQLite, populates PostgreSQL |
| `backend/routers/salarii.py` | CREATE — FastAPI read-only router |
| `backend/main.py` | MODIFY — include new router |

---

## Schema Changes — `schema_v2.sql`

Add after the `visits` table block (before `CREATE INDEX` section):

```sql
-- ============================================================
-- SALARII DB INTEGRATION
-- Source: C:\Users\andre\Desktop\Workspace\unihub\salarii_simplu.db (SQLite)
-- ============================================================

CREATE TABLE IF NOT EXISTS salary_records (
    id SERIAL PRIMARY KEY,
    year SMALLINT NOT NULL CHECK (year BETWEEN 2020 AND 2100),
    month SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    full_name TEXT NOT NULL,
    cnp TEXT,
    total_salary NUMERIC(12, 2) NOT NULL DEFAULT 0,
    company_name TEXT NOT NULL,          -- 'Mobicell' / 'Mobiup'
    site_code TEXT,                       -- links to stores.site_code (ERP side)
    locatie TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (year, month, cnp, full_name, company_name)
);

CREATE INDEX IF NOT EXISTS idx_salary_records_year_month
    ON salary_records (year, month);

CREATE INDEX IF NOT EXISTS idx_salary_records_company
    ON salary_records (company_name);

CREATE INDEX IF NOT EXISTS idx_salary_records_site_code
    ON salary_records (site_code);

CREATE INDEX IF NOT EXISTS idx_salary_records_cnp
    ON salary_records (cnp) WHERE cnp IS NOT NULL;
```

---

## Task Decomposition

### Task 1: Update `schema_v2.sql` — add salary_records table

**Files:**
- Modify: `backend/db/schema_v2.sql`

- [ ] **Step 1: Append salary_records table and indexes to `backend/db/schema_v2.sql`**

Insert the SQL block above after the `visits` table definition (around line 130) and before the existing `CREATE INDEX` section.

---

### Task 2: Create Pydantic models

**Files:**
- Modify: `backend/models.py`
- Add after line 534 (end of file):

```python
# ---- Salarii DB Integration Models ----

class SalaryRecordResponse(BaseModel):
    id: int
    year: int
    month: int
    full_name: str
    cnp: str | None
    total_salary: Decimal
    company_name: str
    site_code: str | None
    locatie: str | None


class SalariiOverviewResponse(BaseModel):
    record_count: int
    company_count: int
    agent_count: int  -- distinct CNP count
    months_span: list[tuple[int, int]]  # [(year, month), ...]
    total_spent: Decimal


class SalaryAgentSummary(BaseModel):
    """Per-agent salary summary across all months."""
    full_name: str
    cnp: str | None
    company_name: str
    month_count: int
    total_salary: Decimal
    avg_salary: Decimal
    last_year: int
    last_month: int
```

- [ ] **Step 1: Add Pydantic models to `backend/models.py`**

---

### Task 3: Create import script `backend/scripts/import_salarii.py`

**Files:**
- Create: `backend/scripts/import_salarii.py`

```python
"""
Import script: reads salaries_simplu.db (SQLite) and populates PostgreSQL.

Usage:
    python -m scripts.import_salarii

Idempotent — uses ON CONFLICT DO UPDATE so re-runs are safe.
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import asyncpg
from db.connection import get_pool

SALARII_DB = Path(r"C:\Users\andre\Desktop\Workspace\unihub\salarii_simplu.db")


async def run_import() -> None:
    print(f"Starting import from {SALARII_DB}")
    if not SALARII_DB.exists():
        print(f"ERROR: salaries_simplu.db not found")
        return

    con = sqlite3.connect(SALARII_DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = cur.execute("SELECT * FROM salary_records").fetchall()
    con.close()

    pool = await get_pool()
    async with pool.acquire() as conn:
        inserted = 0
        updated = 0
        for row in rows:
            try:
                row_id = await conn.execute("""
                    INSERT INTO salary_records (
                        year, month, full_name, cnp, total_salary,
                        company_name, site_code, locatie
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (year, month, cnp, full_name, company_name)
                    DO UPDATE SET
                        total_salary = EXCLUDED.total_salary,
                        site_code = EXCLUDED.site_code,
                        locatie = EXCLUDED.locatie
                    RETURNING (xmax = 0)
                """, row["year"], row["month"], row["full_name"], row.get("cnp"),
                    row["total_salary"], row["company_name"],
                    row.get("site_code"), row.get("locatie"))
                if row_id:
                    inserted += 1
                else:
                    updated += 1
            except Exception as e:
                print(f"  Warning: failed to import row id={row['id']}: {e}")

    print(f"Import complete: {inserted} inserted, {updated} updated.")


if __name__ == "__main__":
    asyncio.run(run_import())
```

- [ ] **Step 1: Create `backend/scripts/import_salarii.py`**

---

### Task 4: Create FastAPI router `backend/routers/salarii.py`

**Files:**
- Create: `backend/routers/salarii.py`

```python
from __future__ import annotations

from decimal import Decimal
from fastapi import APIRouter, Query
from pydantic import BaseModel
from db.connection import get_pool
from models import SalaryRecordResponse, SalariiOverviewResponse, SalaryAgentSummary

router = APIRouter(prefix="/salarii", tags=["salarii"])


@router.get("/overview", response_model=SalariiOverviewResponse)
async def salarii_overview():
    pool = await get_pool()
    async with pool.acquire() as conn:
        record_count = await conn.fetchval("SELECT COUNT(*) FROM salary_records")
        company_count = await conn.fetchval(
            "SELECT COUNT(DISTINCT company_name) FROM salary_records"
        )
        agent_count = await conn.fetchval(
            "SELECT COUNT(DISTINCT cnp) FROM salary_records WHERE cnp IS NOT NULL"
        )
        total_spent = await conn.fetchval(
            "SELECT COALESCE(SUM(total_salary), 0) FROM salary_records"
        )
        months = await conn.fetch(
            "SELECT DISTINCT year, month FROM salary_records ORDER BY year DESC, month DESC"
        )
        return SalariiOverviewResponse(
            record_count=record_count,
            company_count=company_count,
            agent_count=agent_count,
            months_span=[(r["year"], r["month"]) for r in months],
            total_spent=Decimal(str(total_spent)),
        )


@router.get("/records", response_model=list[SalaryRecordResponse])
async def list_salary_records(
    company: str | None = Query(None, alias="company_name"),
    year: int | None = Query(None),
    month: int | None = Query(None),
    site_code: str | None = Query(None),
    limit: int = Query(100, le=2000),
    offset: int = Query(0),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions, params = [], []
        if company:
            params.append(company)
            conditions.append(f"company_name = ${len(params)}")
        if year is not None:
            params.append(year)
            conditions.append(f"year = ${len(params)}")
        if month is not None:
            params.append(month)
            conditions.append(f"month = ${len(params)}")
        if site_code:
            params.append(site_code)
            conditions.append(f"site_code = ${len(params)}")

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.extend([limit, offset])
        query = f"""
            SELECT * FROM salary_records
            {where}
            ORDER BY year DESC, month DESC, full_name
            LIMIT ${len(params)-1} OFFSET ${len(params)}
        """
        rows = await conn.fetch(query, *params)
        return [SalaryRecordResponse(**dict(r)) for r in rows]


@router.get("/agents/summary", response_model=list[SalaryAgentSummary])
async def agent_salary_summary(
    company: str | None = Query(None, alias="company_name"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    """Per-agent salary aggregates across all months."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        where = "WHERE company_name = $1" if company else ""
        params = ([company] if company else [])
        params.extend([limit, offset])
        query = f"""
            SELECT
                full_name,
                cnp,
                company_name,
                COUNT(*) AS month_count,
                SUM(total_salary) AS total_salary,
                AVG(total_salary) AS avg_salary,
                MAX(year) AS last_year,
                MAX(month) AS last_month
            FROM salary_records
            {where}
            GROUP BY full_name, cnp, company_name
            ORDER BY total_salary DESC
            LIMIT ${len(params)-1} OFFSET ${len(params)}
        """
        rows = await conn.fetch(query, *params)
        return [SalaryAgentSummary(
            full_name=r["full_name"],
            cnp=r["cnp"],
            company_name=r["company_name"],
            month_count=r["month_count"],
            total_salary=Decimal(str(r["total_salary"])),
            avg_salary=Decimal(str(r["avg_salary"])),
            last_year=r["last_year"],
            last_month=r["last_month"],
        ) for r in rows]
```

- [ ] **Step 1: Create `backend/routers/salarii.py`**

---

### Task 5: Register router in `main.py`

**Files:**
- Modify: `backend/main.py`

```diff
- from routers import admin, agents, auth, campaigns, dashboard, filters, imports, stores, visits
+ from routers import admin, agents, auth, campaigns, dashboard, filters, imports, salarii, stores, visits
```

```diff
  app.include_router(stores.router)
+ app.include_router(salarii.router)
  app.include_router(visits.router)
```

- [ ] **Step 1: Update imports in `main.py`**
- [ ] **Step 2: Register `salarii.router` after `stores.router`**

---

### Task 6: Run migration + import

- [ ] **Step 1: Apply schema to PostgreSQL**

```bash
cd C:\Users\andre\Desktop\Workspace\unihub\backend
python -c "import asyncio; from db.connection import ensure_schema_current; asyncio.run(ensure_schema_current(force=True))"
```

- [ ] **Step 2: Run import script**

```bash
python -m scripts.import_salarii
```

- [ ] **Step 3: Verify API**

```bash
curl http://localhost:8000/salarii/overview
curl "http://localhost:8000/salarii/records?limit=5"
curl "http://localhost:8000/salarii/agents/summary?limit=5"
```

---

### Task 7: Commit

- [ ] **Step 1: Commit all changes**

```bash
git add backend/db/schema_v2.sql backend/models.py backend/scripts/import_salarii.py backend/routers/salarii.py backend/main.py
git commit -m "feat: import salary records from salarii_simplu.db

- Add salary_records table to schema_v2.sql
- Add import_salarii.py script (reads SQLite, populates PostgreSQL)
- Add /salarii REST endpoints (overview, records, agents/summary)
- Add Pydantic models for salary records

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```
