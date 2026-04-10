# Agents Tab — Chart Date Range & Magazine Flux Redesign

**Date:** 2026-04-10  
**Scope:** `src/components/Agents.tsx`, `backend/routers/agents.py`, `backend/models.py`, `src/api/agents.ts`

---

## Requirements

1. **Chart "Miscare Personal"** — show only months from 2025-01 to present (months with data). No data before 2025 should render.

2. **"Magazine și flux" card** — three changes:
   - Rename "Cu Agent" → "Active"
   - Rename "Fara Agent" → "Cu Modificări" and change its meaning to stores where agent composition changed vs previous month
   - "Inactive" stays unchanged
   - All three boxes become clickable to toggle a list of stores below

3. **Clickable sections** — clicking a box expands/collapses a store list beneath it. Only one section open at a time.

---

## Architecture

### Chart date range (frontend-only)

Filter `movement.history` before rendering:

```tsx
const chartData = useMemo(
  () => (movement?.history ?? []).filter(p => p.month >= '2025-01'),
  [movement]
);
```

No backend change. The data arrives as usual; we slice it at render time.

---

### "Cu Modificări" definition

A store has changes when:
> The set of distinct agents in `selected_month` differs from the set in `prev_month` (one month prior)

This covers: new agent appeared, existing agent left, or agent replaced. Stores with no activity in either month are excluded from this count.

---

### Backend changes

**`backend/models.py`**

Add `has_changes: bool = False` to `StoreCoverageItem`:

```python
class StoreCoverageItem(BaseModel):
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str
    status: str
    agent_count: int
    has_changes: bool = False
```

Add `modified_stores_count: int = 0` to `StoreCoverageResponse`:

```python
class StoreCoverageResponse(BaseModel):
    active_stores_count: int
    uncovered_stores_count: int
    closed_stores_count: int
    modified_stores_count: int = 0
    items: list[StoreCoverageItem]
```

**`backend/routers/agents.py` — `get_stores_coverage`**

Add two CTEs to the existing query:

```sql
prev_agents AS (
    SELECT site_code, array_agg(DISTINCT agent ORDER BY agent) AS agents
    FROM reporting_agent_month
    WHERE import_month = to_char(
        (TO_DATE($1, 'YYYY-MM') - INTERVAL '1 month'), 'YYYY-MM'
    )
    GROUP BY site_code
),
curr_agents AS (
    SELECT site_code, array_agg(DISTINCT agent ORDER BY agent) AS agents
    FROM reporting_agent_month
    WHERE import_month = $1
    GROUP BY site_code
)
```

In `store_status` SELECT, add:

```sql
curr_a.agents IS DISTINCT FROM prev_a.agents AS has_changes
```

Join with:

```sql
LEFT JOIN curr_agents curr_a ON curr_a.site_code = s.site_code
LEFT JOIN prev_agents prev_a ON prev_a.site_code = s.site_code
```

In Python, after building `items`:

```python
modified_stores_count = sum(1 for i in items if i.has_changes)
```

Include in the `StoreCoverageResponse` return.

---

### Frontend changes

**`src/api/agents.ts`**

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

**`src/components/Agents.tsx`**

1. Add state: `const [expandedSection, setExpandedSection] = useState<'active' | 'modified' | 'inactive' | null>(null)`

2. Toggle handler:
```tsx
const toggleSection = (key: 'active' | 'modified' | 'inactive') =>
  setExpandedSection(prev => (prev === key ? null : key));
```

3. Chart data filtered:
```tsx
const chartData = useMemo(
  () => (movement?.history ?? []).filter(p => p.month >= '2025-01'),
  [movement]
);
```

4. Three boxes refactored into clickable buttons with chevron. Each passes its `key` to `toggleSection`.

5. Lists rendered below the grid, conditionally on `expandedSection`:
   - `active`: items where `status === 'covered'` — columns: store name, ASM, agent count badge
   - `modified`: items where `has_changes === true` — columns: store name, ASM, change badge
   - `inactive`: items where `status === 'closed'` — existing layout, adapted to toggle

---

## Scope notes

- `uncovered_stores_count` remains in the API response for backward compatibility (not removed).
- Stores with `status === 'covered'` AND `has_changes === true` appear in BOTH the "Active" count and the "Cu Modificări" count. This is intentional — the two dimensions are orthogonal.
- The "Active" list shows all `covered` stores (with and without changes).
- The "Cu Modificări" list shows only stores with `has_changes === true` (regardless of covered/uncovered).

---

## Files touched

| File | Change |
|------|--------|
| `backend/models.py` | Add `has_changes` to `StoreCoverageItem`, `modified_stores_count` to `StoreCoverageResponse` |
| `backend/routers/agents.py` | Extend `stores-coverage` query with prev/curr agent CTEs; compute `modified_stores_count` |
| `src/api/agents.ts` | Update both interfaces |
| `src/components/Agents.tsx` | Chart filter, label renames, `expandedSection` state, clickable boxes, three lists |
