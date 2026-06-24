# Salarii Tab — Global Filter Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the floating filter button (firma, RM, ASM) in the Agents tab actually filter all 5 cards in the Salarii sub-tab.

**Architecture:** Five backend endpoints in `backend/routers/salarii.py` gain `regional` and `asm` query params that conditionally JOIN `salary_records` with `stores`. Frontend removes the internal firma/store selects from the Agenti card and instead propagates `globalFilters.firma/rm/asm` into every API call.

**Tech Stack:** FastAPI + asyncpg + PostgreSQL (backend), React 19 + TypeScript + axios (frontend)

---

## Files

| Action | File | What changes |
|--------|------|-------------|
| Create | `backend/tests/test_salarii_filter.py` | Integration tests for new params |
| Modify | `backend/routers/salarii.py` | 5 endpoints get `regional`/`asm` params + JOIN with `stores` |
| Modify | `src/api/salarii.ts` | `fetchSalariiOverview` gets params; other fns get `regional`/`asm` |
| Modify | `src/components/SalariiSubtab.tsx` | Remove internal filters; wire all loads to `globalFilters` |

---

## Task 1: Write integration tests for new backend params

**Files:**
- Create: `backend/tests/test_salarii_filter.py`

Tests skip automatically if the backend isn't running (port 9898). They verify:
1. New params are accepted without 422/500 errors
2. Response shape is unchanged after filtering

- [ ] **Step 1: Create test file**

```python
# backend/tests/test_salarii_filter.py
from __future__ import annotations
import pytest


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


async def _get_token(client):
    import httpx
    try:
        login = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "9999"},
        )
    except httpx.ConnectError:
        pytest.skip("Backend not running")
    if login.status_code != 200:
        pytest.skip("Backend credentials wrong")
    return login.json()["access_token"]


@pytest.mark.anyio
async def test_salarii_overview_accepts_regional_asm():
    """GET /salarii/overview with regional+asm returns 200 with correct shape."""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:9898") as client:
        token = await _get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        # Baseline — no filter
        r1 = await client.get("/api/salarii/overview", headers=headers)
        assert r1.status_code == 200
        data = r1.json()
        for key in ("total", "by_company", "record_count", "agent_count", "months_span"):
            assert key in data, f"Missing key: {key}"

        # With regional + asm (may return 0-data, must not 500)
        r2 = await client.get(
            "/api/salarii/overview",
            params={"regional": "NonExistentRegion", "asm": "NonExistentAsm"},
            headers=headers,
        )
        assert r2.status_code == 200
        data2 = r2.json()
        for key in ("total", "by_company", "record_count", "agent_count", "months_span"):
            assert key in data2, f"Missing key after filter: {key}"
        # Filtered total must be <= unfiltered total
        assert data2["total"] <= data["total"]


@pytest.mark.anyio
async def test_salarii_agents_summary_accepts_regional_asm():
    """GET /salarii/agents/summary with regional+asm returns 200 with items+total shape."""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:9898") as client:
        token = await _get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        r1 = await client.get("/api/salarii/agents/summary", params={"limit": 1}, headers=headers)
        assert r1.status_code == 200
        assert "total" in r1.json()

        r2 = await client.get(
            "/api/salarii/agents/summary",
            params={"regional": "NonExistentRegion", "limit": 1},
            headers=headers,
        )
        assert r2.status_code == 200
        data2 = r2.json()
        assert "items" in data2 and "total" in data2
        assert data2["total"] <= r1.json()["total"]


@pytest.mark.anyio
async def test_salarii_summary_accepts_regional_asm():
    """GET /salarii/summary with regional+asm returns 200 with month+items shape."""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:9898") as client:
        token = await _get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.get(
            "/api/salarii/summary",
            params={"regional": "NonExistentRegion"},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert "month" in data and "items" in data


@pytest.mark.anyio
async def test_salarii_trend_accepts_regional_asm():
    """GET /salarii/trend with regional+asm returns 200 (list response)."""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:9898") as client:
        token = await _get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.get(
            "/api/salarii/trend",
            params={"regional": "NonExistentRegion"},
            headers=headers,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)


@pytest.mark.anyio
async def test_salarii_evolution_accepts_regional_asm():
    """GET /salarii/evolution with regional+asm returns 200 (list response)."""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:9898") as client:
        token = await _get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.get(
            "/api/salarii/evolution",
            params={"regional": "NonExistentRegion"},
            headers=headers,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)
```

- [ ] **Step 2: Run tests — they should skip (backend not running in CI) or pass shape checks**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
python -m pytest tests/test_salarii_filter.py -v 2>&1 | head -40
```

Expected: tests either SKIP (backend not running) or PASS shape checks. A 500 would FAIL.

---

## Task 2: Backend — update `overview` and `evolution` endpoints

**Files:**
- Modify: `backend/routers/salarii.py` lines 15–93

- [ ] **Step 1: Replace `salarii_overview` function (lines 15–47)**

Replace the entire `salarii_overview` function with:

```python
@router.get("/overview")
async def salarii_overview(
    company_name: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions, params = [], []
        needs_store_join = regional is not None or asm is not None
        join_sql = "LEFT JOIN stores st ON st.site_code = sr.site_code" if needs_store_join else ""

        if company_name:
            params.append(company_name)
            conditions.append(f"sr.company_name = ${len(params)}")
        if regional:
            params.append(regional)
            conditions.append(f"st.regional = ${len(params)}")
        if asm:
            params.append(asm)
            conditions.append(f"st.asm = ${len(params)}")

        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""
        cnp_where = "WHERE " + " AND ".join(conditions + ["sr.cnp IS NOT NULL"]) if conditions else "WHERE sr.cnp IS NOT NULL"

        total = await conn.fetchval(
            f"SELECT COALESCE(SUM(sr.total_salary), 0) FROM salary_records sr {join_sql} {where_sql}",
            *params,
        )
        by_company = await conn.fetch(
            f"SELECT sr.company_name AS name, COALESCE(SUM(sr.total_salary), 0) AS total "
            f"FROM salary_records sr {join_sql} {where_sql} "
            f"GROUP BY sr.company_name ORDER BY total DESC",
            *params,
        )
        record_count = await conn.fetchval(
            f"SELECT COUNT(*) FROM salary_records sr {join_sql} {where_sql}",
            *params,
        )
        agent_count = await conn.fetchval(
            f"SELECT COUNT(DISTINCT sr.cnp) FROM salary_records sr {join_sql} {cnp_where}",
            *params,
        )
        months_row = await conn.fetchrow(
            f"""
            SELECT
                MIN(sr.year * 100 + sr.month) / 100 AS min_year,
                MIN(sr.year * 100 + sr.month) % 100 AS min_month,
                MAX(sr.year * 100 + sr.month) / 100 AS max_year,
                MAX(sr.year * 100 + sr.month) % 100 AS max_month
            FROM salary_records sr {join_sql} {where_sql}
            """,
            *params,
        )
        if not months_row or months_row["min_year"] is None:
            months_span = [0, 0, 0, 0]
        else:
            months_span = [
                int(months_row["min_year"]),
                int(months_row["min_month"]),
                int(months_row["max_year"]),
                int(months_row["max_month"]),
            ]
        return {
            "total": float(total),
            "by_company": [dict(r) for r in by_company],
            "record_count": record_count,
            "agent_count": agent_count,
            "months_span": months_span,
        }
```

- [ ] **Step 2: Replace `salarii_evolution` function (lines 50–93)**

Replace the entire `salarii_evolution` function with:

```python
@router.get("/evolution")
async def salarii_evolution(
    company_name: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions, params = [], []
        needs_store_join = regional is not None or asm is not None
        join_sql = "LEFT JOIN stores st ON st.site_code = sr.site_code" if needs_store_join else ""

        if company_name:
            params.append(company_name)
            conditions.append(f"sr.company_name = ${len(params)}")
        if regional:
            params.append(regional)
            conditions.append(f"st.regional = ${len(params)}")
        if asm:
            params.append(asm)
            conditions.append(f"st.asm = ${len(params)}")

        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

        if company_name:
            rows = await conn.fetch(
                f"""
                SELECT
                    sr.year * 100 + sr.month AS sort_key,
                    TO_CHAR(sr.year, 'FM9999') || '-' || TO_CHAR(sr.month, 'FM00') AS month,
                    SUM(sr.total_salary) AS total
                FROM salary_records sr
                {join_sql}
                {where_sql}
                GROUP BY sr.year, sr.month
                ORDER BY sort_key
                """,
                *params,
            )
            return [
                {"month": r["month"], "total": float(r["total"]), "mobicell": 0.0, "mobiup": 0.0}
                for r in rows
            ]
        rows = await conn.fetch(
            f"""
            SELECT
                sr.year * 100 + sr.month AS sort_key,
                TO_CHAR(sr.year, 'FM9999') || '-' || TO_CHAR(sr.month, 'FM00') AS month,
                COALESCE(SUM(sr.total_salary) FILTER (WHERE sr.company_name = 'Mobicell'), 0) AS mobicell,
                COALESCE(SUM(sr.total_salary) FILTER (WHERE sr.company_name = 'Mobiup'), 0) AS mobiup,
                COALESCE(SUM(sr.total_salary), 0) AS total
            FROM salary_records sr
            {join_sql}
            {where_sql}
            GROUP BY sr.year, sr.month
            ORDER BY sort_key
            """,
            *params,
        )
        return [dict(r) for r in rows]
```

- [ ] **Step 3: Run tests**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
python -m pytest tests/test_salarii_filter.py -v -k "overview or evolution" 2>&1 | head -30
```

Expected: PASS or SKIP (if backend not running).

---

## Task 3: Backend — update `agents/summary`, `summary`, and `trend` endpoints

**Files:**
- Modify: `backend/routers/salarii.py` lines 96–359

- [ ] **Step 1: Replace `agents_summary` function (lines 96–154)**

```python
@router.get("/agents/summary")
async def agents_summary(
    q: str | None = Query(None),
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions, params = [], []
        needs_store_join = regional is not None or asm is not None
        join_sql = "LEFT JOIN stores st ON st.site_code = sr.site_code" if needs_store_join else ""

        if q:
            params.append(f"%{q}%")
            conditions.append(f"sr.full_name ILIKE ${len(params)}")
        if company_name:
            params.append(company_name)
            conditions.append(f"sr.company_name = ${len(params)}")
        if site_code:
            params.append(site_code)
            conditions.append(f"sr.site_code = ${len(params)}")
        if regional:
            params.append(regional)
            conditions.append(f"st.regional = ${len(params)}")
        if asm:
            params.append(asm)
            conditions.append(f"st.asm = ${len(params)}")
        if year is not None:
            params.append(year)
            conditions.append(f"sr.year = ${len(params)}")
        if month is not None:
            params.append(month)
            conditions.append(f"sr.month = ${len(params)}")

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        total = await conn.fetchval(
            f"SELECT COUNT(DISTINCT sr.full_name) FROM salary_records sr {join_sql} {where}",
            *params,
        )

        params.extend([limit, offset])
        rows = await conn.fetch(
            f"""
            SELECT
                sr.full_name,
                sr.cnp,
                sr.company_name,
                sr.locatie,
                COUNT(*) AS month_count,
                SUM(sr.total_salary) AS total_salary,
                AVG(sr.total_salary) AS avg_salary
            FROM salary_records sr
            {join_sql}
            {where}
            GROUP BY sr.full_name, sr.cnp, sr.company_name, sr.locatie
            ORDER BY total_salary DESC
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )
        return {
            "items": [dict(r) for r in rows],
            "total": total,
        }
```

- [ ] **Step 2: Replace `salarii_summary` function (lines 184–260)**

```python
@router.get("/summary")
async def salarii_summary(
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if year is None or month is None:
            latest = await conn.fetchrow(
                "SELECT year, month FROM salary_records ORDER BY year DESC, month DESC LIMIT 1"
            )
            if not latest:
                return {"month": None, "items": []}
            query_year = latest["year"]
            query_month = latest["month"]
        else:
            query_year = year
            query_month = month

        import_month = f"{query_year}-{query_month:02d}"

        needs_store_join = regional is not None or asm is not None
        join_stores = "LEFT JOIN stores st ON st.site_code = s.site_code" if needs_store_join else ""

        conditions = ["s.year = $1", "s.month = $2"]
        params: list = [query_year, query_month]
        if company_name:
            params.append(company_name)
            conditions.append(f"s.company_name = ${len(params)}")
        if site_code:
            params.append(site_code)
            conditions.append(f"s.site_code = ${len(params)}")
        if regional:
            params.append(regional)
            conditions.append(f"st.regional = ${len(params)}")
        if asm:
            params.append(asm)
            conditions.append(f"st.asm = ${len(params)}")

        where_clause = " AND ".join(conditions)

        rows = await conn.fetch(
            f"""
            SELECT
                s.site_code,
                s.locatie,
                s.company_name,
                SUM(s.total_salary) AS total_salary,
                COUNT(DISTINCT s.full_name) AS agent_count,
                COALESCE(SUM(r.total_sales), 0) AS total_sales
            FROM salary_records s
            {join_stores}
            LEFT JOIN reporting_agent_month r
                ON r.import_month = ${len(params) + 1}
                AND r.site_code = s.site_code
                AND LOWER(r.firma) = LOWER(s.company_name)
            WHERE {where_clause}
            GROUP BY s.site_code, s.locatie, s.company_name
            ORDER BY s.locatie ASC NULLS LAST, s.site_code ASC
            """,
            *params,
            import_month,
        )
        return {
            "month": import_month,
            "items": [
                {
                    "site_code": r["site_code"],
                    "locatie": r["locatie"],
                    "company_name": r["company_name"],
                    "total_salary": float(r["total_salary"]),
                    "agent_count": r["agent_count"],
                    "total_sales": float(r["total_sales"]),
                    "ratio": float(r["total_salary"]) / float(r["total_sales"]) * 100
                    if r["total_sales"]
                    else 0,
                }
                for r in rows
            ],
        }
```

- [ ] **Step 3: Replace `salarii_trend` function (lines 263–359)**

```python
@router.get("/trend")
async def salarii_trend(
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions, params = [], []
        needs_store_join = regional is not None or asm is not None

        if company_name:
            params.append(company_name)
            conditions.append(f"sr.company_name = ${len(params)}")
        if site_code:
            params.append(site_code)
            conditions.append(f"sr.site_code = ${len(params)}")
        if regional:
            params.append(regional)
            conditions.append(f"st.regional = ${len(params)}")
        if asm:
            params.append(asm)
            conditions.append(f"st.asm = ${len(params)}")

        if company_name:
            group_by = "sr.year, sr.month, sr.company_name"
            select_company = "sr.company_name,"
            sql_company_group = ", sr.company_name"
        else:
            group_by = "sr.year, sr.month"
            select_company = ""
            sql_company_group = ""

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        join_stores = "LEFT JOIN stores st ON st.site_code = sr.site_code" if needs_store_join else ""

        rows = await conn.fetch(
            f"""
            SELECT
                sr.year,
                sr.month,
                {select_company}
                SUM(sr.total_salary) AS total_salary,
                COUNT(DISTINCT (sr.year, sr.month, sr.site_code, sr.company_name)) AS store_count,
                COALESCE(SUM(r.total_sales), 0) AS total_sales
            FROM (
                SELECT year, month, site_code, company_name, SUM(total_salary) as total_salary
                FROM salary_records
                GROUP BY year, month, site_code, company_name
            ) sr
            {join_stores}
            LEFT JOIN (
                SELECT import_month, site_code, firma, SUM(total_sales) as total_sales
                FROM reporting_agent_month
                GROUP BY import_month, site_code, firma
            ) r
                ON r.import_month = TO_CHAR(sr.year, 'FM9999') || '-' || TO_CHAR(sr.month, 'FM00')
                AND r.site_code = sr.site_code
                AND LOWER(r.firma) = LOWER(sr.company_name)
            {where_clause}
            GROUP BY sr.year, sr.month{sql_company_group}
            ORDER BY sr.year DESC, sr.month DESC{', sr.company_name' if company_name else ''}
            """,
            *params,
        )

        months_map: dict = {}
        for r in rows:
            import_month = f"{r['year']}-{r['month']:02d}"
            if import_month not in months_map:
                months_map[import_month] = {
                    "month": import_month,
                    "total_salary": 0,
                    "total_sales": 0,
                    "agent_count": 0,
                    "by_company": {},
                }
            months_map[import_month]["total_salary"] += float(r["total_salary"])
            months_map[import_month]["total_sales"] += float(r["total_sales"])
            if company_name:
                company = r["company_name"]
                if company not in months_map[import_month]["by_company"]:
                    months_map[import_month]["by_company"][company] = {
                        "total_salary": 0,
                        "total_sales": 0,
                    }
                months_map[import_month]["by_company"][company]["total_salary"] += float(r["total_salary"])
                months_map[import_month]["by_company"][company]["total_sales"] += float(r["total_sales"])

        return sorted(months_map.values(), key=lambda x: x["month"], reverse=True)
```

- [ ] **Step 4: Run all backend tests**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all previously passing tests still pass. New tests PASS or SKIP.

- [ ] **Step 5: Commit backend changes**

```bash
cd /opt/Mobiup/unihub
git add backend/routers/salarii.py backend/tests/test_salarii_filter.py
git commit -m "feat: add regional/asm filter params to salarii endpoints"
```

---

## Task 4: Frontend — update API types

**Files:**
- Modify: `src/api/salarii.ts`

- [ ] **Step 1: Update `fetchSalariiOverview` to accept params**

Replace lines 81–84:
```ts
// OLD:
export async function fetchSalariiOverview(): Promise<SalariiOverview> {
  const res = await client.get<SalariiOverview>('/salarii/overview');
  return res.data;
}
```

With:
```ts
export async function fetchSalariiOverview(params?: {
  company_name?: string;
  regional?: string;
  asm?: string;
}): Promise<SalariiOverview> {
  const res = await client.get<SalariiOverview>('/salarii/overview', { params });
  return res.data;
}
```

- [ ] **Step 2: Update `fetchSalaryEvolution` to accept an object**

Replace lines 86–92:
```ts
// OLD:
export async function fetchSalaryEvolution(
  companyName?: string
): Promise<SalaryEvolutionPoint[]> {
  const params = companyName ? { company_name: companyName } : {};
  const res = await client.get<SalaryEvolutionPoint[]>('/salarii/evolution', { params });
  return res.data;
}
```

With:
```ts
export async function fetchSalaryEvolution(params?: {
  company_name?: string;
  regional?: string;
  asm?: string;
}): Promise<SalaryEvolutionPoint[]> {
  const res = await client.get<SalaryEvolutionPoint[]>('/salarii/evolution', { params });
  return res.data;
}
```

- [ ] **Step 3: Add `regional` and `asm` to `fetchSalaryAgents` params**

In `fetchSalaryAgents` (lines 94–107), add `regional` and `asm` to the params type:
```ts
export async function fetchSalaryAgents(params: {
  q?: string;
  company_name?: string;
  site_code?: string;
  regional?: string;
  asm?: string;
  year?: number;
  month?: number;
  limit?: number;
  offset?: number;
}): Promise<SalaryAgentsSummaryResponse> {
  const res = await client.get<SalaryAgentsSummaryResponse>('/salarii/agents/summary', {
    params,
  });
  return res.data;
}
```

- [ ] **Step 4: Add `regional` and `asm` to `fetchSalarySummary` params**

In `fetchSalarySummary` (lines 120–128), add `regional` and `asm`:
```ts
export async function fetchSalarySummary(params: {
  company_name?: string;
  site_code?: string;
  regional?: string;
  asm?: string;
  year?: number;
  month?: number;
}): Promise<SalarySummaryResponse> {
  const res = await client.get<SalarySummaryResponse>('/salarii/summary', { params });
  return res.data;
}
```

- [ ] **Step 5: Add `regional` and `asm` to `fetchSalaryTrend` params**

In `fetchSalaryTrend` (lines 130–136), add `regional` and `asm`:
```ts
export async function fetchSalaryTrend(params: {
  company_name?: string;
  site_code?: string;
  regional?: string;
  asm?: string;
}): Promise<SalaryTrendMonth[]> {
  const res = await client.get<SalaryTrendMonth[]>('/salarii/trend', { params });
  return res.data;
}
```

- [ ] **Step 6: Verify typecheck passes**

```bash
cd /opt/Mobiup/unihub
npm run typecheck 2>&1 | grep -E "error|warning" | head -20
```

Expected: errors only from `SalariiSubtab.tsx` (calling old signatures) — that's fine, Task 5 fixes them.

---

## Task 5: Frontend — rewire `SalariiSubtab.tsx`

**Files:**
- Modify: `src/components/SalariiSubtab.tsx`

Context: `globalFilters` is `AppFilters` with fields:
- `firma` — default `'Toate'` → send `undefined`
- `rm` — default `'Toti'` → send as `regional`, undefined if `'Toti'`
- `asm` — default `'Toti'` → send `undefined`

- [ ] **Step 1: Remove internal filter states (lines 63–65)**

Remove these three lines:
```ts
// REMOVE:
const [companyFilter, setCompanyFilter] = useState('');
const [storeFilter, setStoreFilter] = useState('');
const [availableStores, setAvailableStores] = useState<SalaryStore[]>([]);
```

- [ ] **Step 2: Also remove the `SalaryStore` import from `../api/salarii`**

In the import at lines 11–18, remove `SalaryStore` from the type imports:
```ts
import type {
  SalariiOverview,
  SalaryAgentSummary,
  SalaryEvolutionPoint,
  SalaryComparisonPoint,
  SalaryTrendMonth,
} from '../api/salarii';
```

Also remove `fetchSalariiStores` from the function imports:
```ts
import {
  fetchSalariiOverview,
  fetchSalaryAgents,
  fetchSalaryEvolution,
  fetchSalarySummary,
  fetchSalaryTrend,
} from '../api/salarii';
```

- [ ] **Step 3: Replace `loadOverview` callback (lines 79–90)**

```ts
const loadOverview = useCallback(async () => {
  try {
    const firma = globalFilters?.firma !== 'Toate' ? globalFilters?.firma : undefined;
    const regional = globalFilters?.rm !== 'Toti' ? globalFilters?.rm : undefined;
    const asm = globalFilters?.asm !== 'Toti' ? globalFilters?.asm : undefined;
    const [ov, ev] = await Promise.all([
      fetchSalariiOverview({ company_name: firma, regional, asm }),
      fetchSalaryEvolution({ company_name: firma, regional, asm }),
    ]);
    setOverview(ov);
    setEvolution(ev);
  } catch (e) {
    console.error('Failed to load overview:', e);
  }
}, [globalFilters]);
```

- [ ] **Step 4: Remove `loadStores` callback entirely (lines 92–99)**

Delete:
```ts
// REMOVE entirely:
const loadStores = useCallback(async (company?: string) => {
  try {
    const stores = await fetchSalariiStores(company || undefined);
    setAvailableStores(stores);
  } catch (e) {
    console.error('Failed to load stores:', e);
  }
}, []);
```

- [ ] **Step 5: Update `loadSummary` to pass `regional` and `asm` (lines 101–119)**

Replace with:
```ts
const loadSummary = useCallback(async () => {
  setLoadingCards(true);
  try {
    const firma = globalFilters?.firma !== 'Toate' ? globalFilters?.firma : undefined;
    const regional = globalFilters?.rm !== 'Toti' ? globalFilters?.rm : undefined;
    const asm = globalFilters?.asm !== 'Toti' ? globalFilters?.asm : undefined;
    let year: number | undefined;
    let month: number | undefined;
    if (selectedSummaryMonth && /^\d{4}-\d{2}$/.test(selectedSummaryMonth)) {
      [year, month] = selectedSummaryMonth.split('-').map(Number);
    }
    const data = await fetchSalarySummary({ company_name: firma, regional, asm, year, month });
    setSummary(data.items || []);
    setSummaryMonth(data.month);
  } catch (e) {
    console.error('Failed to load summary:', e);
  } finally {
    setLoadingCards(false);
  }
}, [globalFilters, selectedSummaryMonth]);
```

- [ ] **Step 6: Update `loadTrend` to pass `regional` and `asm` (lines 121–132)**

Replace with:
```ts
const loadTrend = useCallback(async () => {
  setLoadingCards(true);
  try {
    const firma = globalFilters?.firma !== 'Toate' ? globalFilters?.firma : undefined;
    const regional = globalFilters?.rm !== 'Toti' ? globalFilters?.rm : undefined;
    const asm = globalFilters?.asm !== 'Toti' ? globalFilters?.asm : undefined;
    const data = await fetchSalaryTrend({ company_name: firma, regional, asm });
    setTrend(data || []);
  } catch (e) {
    console.error('Failed to load trend:', e);
  } finally {
    setLoadingCards(false);
  }
}, [globalFilters]);
```

- [ ] **Step 7: Update `loadAgents` — replace internal filters with global filters (lines 134–154)**

Replace with:
```ts
const loadAgents = useCallback(
  async (offset = 0) => {
    setLoading(true);
    try {
      const firma = globalFilters?.firma !== 'Toate' ? globalFilters?.firma : undefined;
      const regional = globalFilters?.rm !== 'Toti' ? globalFilters?.rm : undefined;
      const asm = globalFilters?.asm !== 'Toti' ? globalFilters?.asm : undefined;
      const res = await fetchSalaryAgents({
        q: debouncedSearch || undefined,
        company_name: firma,
        regional,
        asm,
        limit: PAGE_SIZE,
        offset,
      });
      setAgents(offset === 0 ? res?.items || [] : (prev) => [...(prev || []), ...(res?.items || [])]);
      setTotalAgents(res?.total || 0);
    } catch (e) {
      console.error('Failed to load agents:', e);
    } finally {
      setLoading(false);
    }
  },
  [debouncedSearch, globalFilters]
);
```

- [ ] **Step 8: Update useEffect hooks (line 156)**

Replace:
```ts
useEffect(() => { loadOverview(); loadStores(); }, []);
```

With:
```ts
useEffect(() => { loadOverview(); }, [globalFilters]);
```

- [ ] **Step 9: Remove `handleCompanyChange`, `handleStoreChange` (lines 166–175)**

Delete both functions:
```ts
// REMOVE:
function handleCompanyChange(val: string) {
  setCompanyFilter(val);
  setStoreFilter('');
  loadStores(val || undefined);
  setPage(0);
}

function handleStoreChange(val: string) {
  setStoreFilter(val);
  setPage(0);
}
```

- [ ] **Step 10: Simplify `resetFilters` (lines 178–185)**

Replace with:
```ts
function resetFilters() {
  setSearch('');
  setDebouncedSearch('');
  setPage(0);
}
```

- [ ] **Step 11: Remove firma select, store select, and update reset button in the Card 5 UI (lines 374–404)**

Replace the entire block from `{/* Search */}` through the closing `</div>` of `flex flex-wrap items-center gap-2` with:

```tsx
<div className="flex flex-wrap items-center gap-2">
  {/* Search */}
  <div className="relative">
    <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
    <input
      type="text"
      placeholder="Cauta..."
      value={search}
      onChange={(e) => handleSearchChange(e.target.value)}
      className="w-32 rounded-lg border border-slate-200 bg-white/80 py-1.5 pl-7 pr-2 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-200"
    />
  </div>
  {search && (
    <button
      onClick={resetFilters}
      className="rounded-lg border border-slate-200 bg-white/80 py-1.5 px-2 text-xs text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-400"
    >
      Reseteaza
    </button>
  )}
</div>
```

- [ ] **Step 12: Run typecheck**

```bash
cd /opt/Mobiup/unihub
npm run typecheck 2>&1 | grep -E "error TS" | head -20
```

Expected: 0 TypeScript errors.

- [ ] **Step 13: Run full test suite**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all tests pass (or skip).

- [ ] **Step 14: Build frontend**

```bash
cd /opt/Mobiup/unihub
npm run build 2>&1 | tail -10
```

Expected: build succeeds with no errors.

- [ ] **Step 15: Restart backend and commit**

```bash
sudo systemctl restart unihub-backend
sleep 2
cd /opt/Mobiup/unihub
git add src/api/salarii.ts src/components/SalariiSubtab.tsx
git commit -m "feat: wire globalFilters (firma/RM/ASM) to all Salarii sub-tab cards"
```

---

## Self-Review

**Spec coverage:**
- ✅ All 5 endpoints gain `regional`/`asm` params
- ✅ `/salarii/overview` included
- ✅ `/salarii/evolution` included
- ✅ Internal firma/store selects removed from Agenti card
- ✅ Text search kept
- ✅ `loadStores` / `availableStores` removed
- ✅ `resetFilters` simplified

**Type consistency:**
- `fetchSalariiOverview({ company_name, regional, asm })` — defined in Task 4, called in Task 5 ✅
- `fetchSalaryEvolution({ company_name, regional, asm })` — defined in Task 4, called in Task 5 ✅
- `fetchSalaryAgents({ ..., regional, asm })` — defined in Task 4, called in Task 5 ✅
- `fetchSalarySummary({ ..., regional, asm })` — defined in Task 4, called in Task 5 ✅
- `fetchSalaryTrend({ ..., regional, asm })` — defined in Task 4, called in Task 5 ✅
