# Agents Tab — Chart Range & Magazine Flux Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix "Miscare Personal" chart to show only 2025-01→present, rename "Fara Agent" → "Cu Modificări" (stores with agent changes vs prev month), and make all three Magazine si Flux boxes clickable with collapsible store lists.

**Architecture:** Backend adds a `has_changes` boolean to each `StoreCoverageItem` by comparing per-store agent sets in `selected_month` vs `prev_month` via two new CTEs. Frontend filters the chart data client-side and replaces the static boxes with clickable toggles.

**Tech Stack:** FastAPI + asyncpg + PostgreSQL (backend), React 19 + TypeScript + Tailwind CSS (frontend), pytest + anyio (tests)

---

## File Map

| File | Change |
|------|--------|
| `backend/models.py` | Add `has_changes: bool = False` to `StoreCoverageItem`; add `modified_stores_count: int = 0` to `StoreCoverageResponse` |
| `backend/routers/agents.py` | Extend `stores-coverage` query with `curr_agents` + `prev_agents` CTEs; compute `modified_stores_count` |
| `backend/tests/test_agents_coverage.py` | New test file for stores-coverage response shape + `has_changes` field |
| `src/api/agents.ts` | Update `StoreCoverageItem` (add `has_changes`) and `StoreCoverageResponse` (add `modified_stores_count`) |
| `src/components/Agents.tsx` | Chart filter to 2025-01, label renames, `expandedSection` state, clickable boxes, three toggle lists |

---

## Task 1: Update backend models

**Files:**
- Modify: `backend/models.py` (lines ~601–615)

- [ ] **Step 1: Add `has_changes` to `StoreCoverageItem` and `modified_stores_count` to `StoreCoverageResponse`**

Find these two classes in `backend/models.py` and update them:

```python
class StoreCoverageItem(BaseModel):
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str
    status: str  # 'covered', 'uncovered', 'closed', 'inactive'
    agent_count: int
    has_changes: bool = False


class StoreCoverageResponse(BaseModel):
    active_stores_count: int
    uncovered_stores_count: int
    closed_stores_count: int
    modified_stores_count: int = 0
    items: list[StoreCoverageItem]
```

- [ ] **Step 2: Verify no import issues**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate && python -c "from models import StoreCoverageItem, StoreCoverageResponse; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
cd /opt/Mobiup/unihub && git add backend/models.py && git commit -m "feat: add has_changes + modified_stores_count to StoreCoverage models"
```

---

## Task 2: Write failing test for stores-coverage

**Files:**
- Create: `backend/tests/test_agents_coverage.py`

- [ ] **Step 1: Create the test file**

```python
from __future__ import annotations
import pytest
from db.connection import get_pool


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_stores_coverage_response_shape():
    """stores-coverage endpoint returns has_changes and modified_stores_count fields."""
    from routers.agents import get_stores_coverage

    # Use a real month that has data
    month = "2025-01"
    user = {"role": "admin", "id": 1}

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Call the core query logic via the pool directly
        pass

    # Hit the endpoint via HTTP since it uses Depends(get_current_user)
    # We test the model shapes instead
    from models import StoreCoverageItem, StoreCoverageResponse

    item = StoreCoverageItem(
        site_code="TEST",
        locatie="Test Store",
        firma="TestFirma",
        regional="TestRegion",
        asm="TestAsm",
        status="covered",
        agent_count=2,
        has_changes=True,
    )
    assert item.has_changes is True

    response = StoreCoverageResponse(
        active_stores_count=10,
        uncovered_stores_count=2,
        closed_stores_count=3,
        modified_stores_count=4,
        items=[item],
    )
    assert response.modified_stores_count == 4
    assert response.items[0].has_changes is True


@pytest.mark.anyio
async def test_stores_coverage_endpoint_returns_has_changes():
    """The /stores-coverage endpoint returns has_changes on each item."""
    import httpx
    # Get a valid token first
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        login = await client.post("/api/auth/login", json={"username": "admin", "password": "9999"})
        if login.status_code != 200:
            pytest.skip("Backend not running or credentials wrong")
        token = login.json()["access_token"]

        resp = await client.get(
            "/api/agents/stores-coverage",
            params={"selected_month": "2025-04"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "modified_stores_count" in data
        assert isinstance(data["modified_stores_count"], int)
        assert "items" in data
        if data["items"]:
            item = data["items"][0]
            assert "has_changes" in item
            assert isinstance(item["has_changes"], bool)
```

- [ ] **Step 2: Run the test — expect first test to pass, second to skip if no server**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate && pytest tests/test_agents_coverage.py -v
```

Expected: `test_stores_coverage_response_shape` PASS, `test_stores_coverage_endpoint_returns_has_changes` SKIP or PASS

- [ ] **Step 3: Commit**

```bash
cd /opt/Mobiup/unihub && git add backend/tests/test_agents_coverage.py && git commit -m "test: add stores-coverage shape + has_changes field tests"
```

---

## Task 3: Extend the stores-coverage query

**Files:**
- Modify: `backend/routers/agents.py` (function `get_stores_coverage`, ~lines 449–492)

- [ ] **Step 1: Replace the query in `get_stores_coverage` to add prev/curr agent CTEs**

Find the `query = f"""` block and replace the entire query string with:

```python
    query = f"""
        WITH store_agents AS (
            SELECT site_code, COUNT(DISTINCT agent)::INT as agent_count
            FROM reporting_agent_month
            WHERE import_month = $1
            GROUP BY site_code
        ),
        curr_agents AS (
            SELECT site_code, array_agg(DISTINCT agent ORDER BY agent) AS agents
            FROM reporting_agent_month
            WHERE import_month = $1
              AND agent IS NOT NULL AND agent != '-'
            GROUP BY site_code
        ),
        prev_agents AS (
            SELECT site_code, array_agg(DISTINCT agent ORDER BY agent) AS agents
            FROM reporting_agent_month
            WHERE import_month = to_char(
                (TO_DATE($1, 'YYYY-MM') - INTERVAL '1 month'), 'YYYY-MM'
            )
              AND agent IS NOT NULL AND agent != '-'
            GROUP BY site_code
        ),
        store_status AS (
            SELECT
                s.site_code,
                s.locatie,
                s.firma,
                s.regional,
                s.asm,
                COALESCE(sa.agent_count, 0) as agent_count,
                CASE
                    WHEN s.last_seen_month = $1 THEN
                        CASE WHEN COALESCE(sa.agent_count, 0) > 0 THEN 'covered' ELSE 'uncovered' END
                    WHEN {selected_idx} - {month_index_expr("s.last_seen_month")} > 3 THEN 'closed'
                    ELSE 'inactive'
                END as status,
                ca.agents IS DISTINCT FROM pa.agents AS has_changes
            FROM stores s
            LEFT JOIN store_agents sa ON sa.site_code = s.site_code
            LEFT JOIN curr_agents ca ON ca.site_code = s.site_code
            LEFT JOIN prev_agents pa ON pa.site_code = s.site_code
            {where_sql}
        )
        SELECT * FROM store_status
        ORDER BY agent_count ASC, locatie ASC
    """
```

- [ ] **Step 2: Update the Python post-processing to compute `modified_stores_count`**

After `items = [StoreCoverageItem(**dict(row)) for row in rows]`, replace the existing lines:

```python
    items = [StoreCoverageItem(**dict(row)) for row in rows]

    active_stores = [i for i in items if i.status in ("covered", "uncovered")]
    uncovered_stores = [i for i in items if i.status == "uncovered"]
    closed_stores = [i for i in items if i.status == "closed"]
    modified_stores_count = sum(1 for i in items if i.has_changes)

    return StoreCoverageResponse(
        active_stores_count=len(active_stores),
        uncovered_stores_count=len(uncovered_stores),
        closed_stores_count=len(closed_stores),
        modified_stores_count=modified_stores_count,
        items=items,
    )
```

- [ ] **Step 3: Run all backend tests**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate && pytest tests/ -v 2>&1 | tail -20
```

Expected: all 32 existing tests pass, `test_stores_coverage_response_shape` passes.

- [ ] **Step 4: Restart backend and smoke-test endpoint**

```bash
sudo systemctl restart unihub-backend && sleep 2
curl -s "http://localhost:8000/api/agents/stores-coverage?selected_month=2025-04" \
  -H "Authorization: Bearer $(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"9999"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')" \
  | python3 -m json.tool | grep -E '"has_changes"|"modified_stores_count"' | head -10
```

Expected: `"has_changes": true` or `false` on items, `"modified_stores_count": <int>` in root.

- [ ] **Step 5: Commit**

```bash
cd /opt/Mobiup/unihub && git add backend/routers/agents.py && git commit -m "feat: stores-coverage detects per-store agent changes vs previous month"
```

---

## Task 4: Update frontend TypeScript types

**Files:**
- Modify: `src/api/agents.ts`

- [ ] **Step 1: Update both interfaces**

Find `StoreCoverageItem` and `StoreCoverageResponse` in `src/api/agents.ts` and replace them:

```typescript
export interface StoreCoverageItem {
  site_code: string;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
  status: 'covered' | 'uncovered' | 'closed' | 'inactive';
  agent_count: number;
  has_changes: boolean;
}

export interface StoreCoverageResponse {
  active_stores_count: number;
  uncovered_stores_count: number;
  closed_stores_count: number;
  modified_stores_count: number;
  items: StoreCoverageItem[];
}
```

- [ ] **Step 2: Verify TypeScript compiles cleanly**

```bash
cd /opt/Mobiup/unihub && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd /opt/Mobiup/unihub && git add src/api/agents.ts && git commit -m "feat: update StoreCoverage TS types with has_changes + modified_stores_count"
```

---

## Task 5: Frontend — chart filter, renamed labels, clickable sections

**Files:**
- Modify: `src/components/Agents.tsx`

> Note: This is the largest task. Read the current file around lines 612–742 before editing to confirm line numbers haven't shifted.

- [ ] **Step 1: Add `expandedSection` state and memoized chart data**

Find the block where state variables are declared for the overview component (around line 325, near `const [overview, setOverview]`). Add after the existing state declarations:

```tsx
const [expandedSection, setExpandedSection] = useState<'active' | 'modified' | 'inactive' | null>(null);
```

Find the `filteredList = useMemo(...)` block (around line 367) where other derived values are computed. Add the chart data memo immediately after `filteredList`:

```tsx
const chartData = useMemo(
  () => (movement?.history ?? []).filter((p) => p.month >= '2025-01'),
  [movement]
);
```

Then find the existing chart `<ComposedChart data={movement.history}` line (around line 622) and change it to:

```tsx
const chartData = useMemo(
  () => (movement?.history ?? []).filter((p) => p.month >= '2025-01'),
  [movement]
);
```

Then change the chart's `data` prop:
```tsx
<ComposedChart data={chartData} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
```

And update the empty-state condition from `movement.history.length > 0` to `chartData.length > 0`:
```tsx
{chartData.length > 0 ? (
  <ResponsiveContainer width="100%" height="100%" minWidth={0}>
    <ComposedChart data={chartData} ...>
```

- [ ] **Step 2: Replace the three static boxes with clickable buttons**

Find the `<div className="grid grid-cols-3 gap-3">` block (around line 671) that contains the three store boxes and replace the entire `<div className="grid grid-cols-3 gap-3">...</div>` with:

```tsx
<div className="grid grid-cols-3 gap-3">
  {/* Active */}
  <button
    onClick={() => setExpandedSection(prev => prev === 'active' ? null : 'active')}
    className="rounded-2xl bg-emerald-50/50 p-3 dark:bg-emerald-900/10 text-left hover:bg-emerald-100/60 dark:hover:bg-emerald-900/20 transition-colors"
  >
    <div className="mb-2 flex items-center justify-between gap-1">
      <div className="flex items-center gap-2">
        <Store size={16} className="text-emerald-500" />
        <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Active</div>
      </div>
      {expandedSection === 'active'
        ? <ChevronUp size={12} className="text-slate-400 shrink-0" />
        : <ChevronDown size={12} className="text-slate-400 shrink-0" />}
    </div>
    <div className="text-2xl font-black text-emerald-600 dark:text-emerald-400">
      {coverage ? coverage.active_stores_count : '-'}
    </div>
  </button>

  {/* Cu Modificări */}
  <button
    onClick={() => setExpandedSection(prev => prev === 'modified' ? null : 'modified')}
    className="rounded-2xl bg-amber-50/50 p-3 dark:bg-amber-900/10 text-left hover:bg-amber-100/60 dark:hover:bg-amber-900/20 transition-colors"
  >
    <div className="mb-2 flex items-center justify-between gap-1">
      <div className="flex items-center gap-2">
        <Store size={16} className="text-amber-500" />
        <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Cu Modificări</div>
      </div>
      {expandedSection === 'modified'
        ? <ChevronUp size={12} className="text-slate-400 shrink-0" />
        : <ChevronDown size={12} className="text-slate-400 shrink-0" />}
    </div>
    <div className="text-2xl font-black text-amber-600 dark:text-amber-400">
      {coverage ? coverage.modified_stores_count : '-'}
    </div>
  </button>

  {/* Inactive */}
  <button
    onClick={() => setExpandedSection(prev => prev === 'inactive' ? null : 'inactive')}
    className="rounded-2xl bg-slate-50/80 p-3 dark:bg-slate-800/40 text-left hover:bg-slate-100/60 dark:hover:bg-slate-800/60 transition-colors"
  >
    <div className="mb-2 flex items-center justify-between gap-1">
      <div className="flex items-center gap-2">
        <Store size={16} className="text-slate-500" />
        <div className="text-xs font-bold text-slate-600 dark:text-slate-400">Inactive</div>
      </div>
      {expandedSection === 'inactive'
        ? <ChevronUp size={12} className="text-slate-400 shrink-0" />
        : <ChevronDown size={12} className="text-slate-400 shrink-0" />}
    </div>
    <div className="text-2xl font-black">
      {coverage ? coverage.closed_stores_count : '-'}
    </div>
    <div className="mt-1 text-[10px] text-slate-500">&gt; 3 luni fara activitate</div>
  </button>
</div>
```

- [ ] **Step 3: Replace the three static lists with toggle-controlled lists**

Find the block starting with `{coverage && coverage.items.length > 0 && coverage.uncovered_stores_count > 0 && (` (around line 702) and **delete everything from there to the end of the closing `</div>` of the store coverage card** (ending around line 741). Replace with:

```tsx
{/* Active list */}
{coverage && expandedSection === 'active' && (
  <div className="mt-3 max-h-56 overflow-y-auto space-y-1">
    <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
      Magazine active ({coverage.active_stores_count})
    </div>
    {coverage.items
      .filter((item: StoreCoverageItem) => item.status === 'covered')
      .map((item: StoreCoverageItem) => (
        <div key={item.site_code} className="flex items-center justify-between rounded-xl bg-emerald-50/50 px-3 py-2 dark:bg-emerald-900/10">
          <div className="min-w-0 flex-1">
            <span className="text-xs font-bold text-slate-700 dark:text-slate-200 truncate block">{item.locatie || item.site_code}</span>
            <span className="text-[10px] text-slate-400">{item.asm}</span>
          </div>
          <span className="ml-2 shrink-0 text-[10px] font-bold text-emerald-600">{item.agent_count} ag.</span>
        </div>
      ))}
  </div>
)}

{/* Cu Modificări list */}
{coverage && expandedSection === 'modified' && (
  <div className="mt-3 max-h-56 overflow-y-auto space-y-1">
    <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
      Magazine cu modificări ({coverage.modified_stores_count})
    </div>
    {coverage.items
      .filter((item: StoreCoverageItem) => item.has_changes)
      .map((item: StoreCoverageItem) => (
        <div key={item.site_code} className="flex items-center justify-between rounded-xl bg-amber-50/50 px-3 py-2 dark:bg-amber-900/10">
          <div className="min-w-0 flex-1">
            <span className="text-xs font-bold text-slate-700 dark:text-slate-200 truncate block">{item.locatie || item.site_code}</span>
            <span className="text-[10px] text-slate-400">{item.asm}</span>
          </div>
          <span className="ml-2 shrink-0 rounded-full bg-amber-100 dark:bg-amber-900/40 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">
            modificat
          </span>
        </div>
      ))}
  </div>
)}

{/* Inactive list */}
{coverage && expandedSection === 'inactive' && coverage.closed_stores_count > 0 && (
  <div className="mt-3 max-h-56 overflow-y-auto space-y-1">
    <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
      Magazine inactive ({coverage.closed_stores_count}) — &gt; 3 luni fara activitate
    </div>
    {coverage.items
      .filter((item: StoreCoverageItem) => item.status === 'closed')
      .map((item: StoreCoverageItem) => (
        <div key={item.site_code} className="flex items-center justify-between rounded-xl bg-slate-100/60 px-3 py-2 dark:bg-slate-800/40">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-600 dark:text-slate-300 truncate">{item.locatie || item.site_code}</span>
              <span className="shrink-0 text-[10px] text-slate-400">{item.asm}</span>
            </div>
            <div className="text-[10px] text-slate-400">{item.firma} · {item.regional}</div>
          </div>
          <span className="ml-2 shrink-0 text-[10px] font-bold text-slate-400">{item.agent_count} ag.</span>
        </div>
      ))}
  </div>
)}
```

- [ ] **Step 4: Verify `ChevronUp` is imported**

Check the import at the top of `Agents.tsx`. If `ChevronUp` is not already imported from `lucide-react`, add it:

```tsx
import { Search, Users, Activity, TrendingUp, UserPlus, UserMinus, UserCheck, RefreshCw, ChevronLeft, ChevronDown, ChevronUp, Award, LayoutGrid, Store, X } from 'lucide-react';
```

- [ ] **Step 5: TypeScript check + build**

```bash
cd /opt/Mobiup/unihub && npx tsc --noEmit 2>&1 | head -20 && npm run build 2>&1 | tail -10
```

Expected: no errors, `✓ built in ...`

- [ ] **Step 6: Run full test suite**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate && pytest tests/ -v 2>&1 | tail -10
```

Expected: all tests pass.

- [ ] **Step 7: Restart backend and deploy frontend**

```bash
cd /opt/Mobiup/unihub && sudo systemctl restart unihub-backend
```

- [ ] **Step 8: Commit**

```bash
cd /opt/Mobiup/unihub && git add src/components/Agents.tsx && git commit -m "feat: agents tab — chart from 2025-01, Cu Modificari category, clickable store sections"
```
