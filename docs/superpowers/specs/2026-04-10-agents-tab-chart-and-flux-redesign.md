# Agents Tab — Chart Date Range & Magazine Flux Redesign

**Date:** 2026-04-10  
**Scope:** `src/components/Agents.tsx`, `backend/services/agents.py`, `backend/models.py`, `src/api/agents.ts`

---

## Requirements

1. **Chart "Miscare Personal"** — show only months from 2025-01 to present (months with data). No data before 2025 should render. `2025-01` is the baseline month for agent-level tracking, so it must not be counted as mass hiring.

2. **"Magazine și flux" card** — three changes:
   - Rename "Cu Agent" → "Active"
   - Rename "Fara Agent" → "Cu Modificări" and change its meaning to stores where agent composition changed vs previous month
   - "Inactive" stays unchanged
   - All three boxes become clickable to toggle a list of stores below

3. **Clickable sections** — clicking a box expands/collapses a store list beneath it. Only one section open at a time.

4. **Churn visibility** — agents who left must be visible both in the movement chart and in the agent list. Churn analytics should use the selected snapshot month from the page context.

5. **Store flux ranking** — add a compact card ranking stores by total agent composition changes.

---

## Architecture

### Chart date range and baseline treatment

Filter `movement.history` before rendering and normalize the first tracked month:

```tsx
const points = (movement?.history ?? []).filter((p) => p.month >= '2025-01');
const chartData = points.map((p, index) => {
  const isBaseline = p.is_baseline || p.month === '2025-01';
  const previous = index > 0 ? points[index - 1] : null;
  const newAgents = isBaseline ? 0 : p.new;
  const reactivatedAgents = isBaseline ? 0 : p.reactivated;
  const exited = previous
    ? Math.max(0, previous.active + newAgents + reactivatedAgents - p.active)
    : 0;
  return { ...p, new: newAgents, reactivated: reactivatedAgents, churned: exited };
});
```

The backend also returns `is_baseline` for movement points, but the frontend keeps the explicit month fallback so stale API responses cannot draw `2025-01` as a real intake bar.

---

### "Cu Modificări" definition

A store has changes when:
> The set of distinct agents in `selected_month` differs from the set in `prev_month` (one month prior)

This covers: new agent appeared, existing agent left, or agent replaced. Stores with no activity in either month are excluded from this count.

For stores with changes, the API also exposes:

- `previous_agent_count`
- `added_agents_count`
- `removed_agents_count`
- `change_reason`

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

**`backend/services/agents.py` — `get_agents_movement`**

Movement is computed from distinct scoped active agents per month. `2025-01` is marked as baseline and returns zero for `new`, `reactivated`, `churned`, and `net_growth`.

The response model includes:

```python
class AgentMovementPoint(BaseModel):
    month: str
    active: int
    new: int
    reactivated: int
    churned: int
    net_growth: int = 0
    is_baseline: bool = False
```

**`backend/services/agents.py` — `get_stores_coverage`**

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

Also compute counts for current vs previous composition:

```sql
COALESCE(array_length(prev_a.agents, 1), 0)::INT AS previous_agent_count,
added_agents_count,
removed_agents_count,
change_reason
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
  previous_agent_count: number;
  added_agents_count: number;
  removed_agents_count: number;
  change_reason: string | null;
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
  () => normalizeMovementData(movement?.history ?? []),
  [movement]
);
```

4. The chart uses separate axes:
   - movement axis for `Noi`, `Reactivati`, `Iesiti`, and `Net`
   - active axis for `Total Activi`

5. Add the "Analiza Churn" card with:
   - current snapshot churn rate
   - current net movement
   - 3-month average churn
   - total exits since `2025-02`

6. Add the "Top Magazine dupa Flux" card, sorted by `added_agents_count + removed_agents_count`.

7. Three boxes refactored into clickable buttons with chevron. Each passes its `key` to `toggleSection`.

8. Lists rendered below the grid, conditionally on `expandedSection`:
   - `active`: items where `status === 'covered'` — columns: store name, ASM, agent count badge
   - `modified`: items where `has_changes === true` — columns: store name, ASM, reason, previous/current agent count, added/removed badges
   - `inactive`: items where `status === 'closed'` — existing layout, adapted to toggle

9. Agent list tabs separate `Inactiv` from `Iesiti`, so churned agents are directly visible.

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
| `backend/models.py` | Add movement baseline and store-change detail fields |
| `backend/services/agents.py` | Compute baseline-aware movement, exits, net growth, and store-change reasons |
| `backend/tests/test_agents_coverage.py` | Cover store-change response shape |
| `backend/tests/test_agents_service.py` | Cover movement response fields |
| `src/api/agents.ts` | Update both interfaces |
| `src/components/Agents.tsx` | Baseline-aware chart, churn card, top flux card, label renames, `expandedSection` state, clickable boxes, lists |
