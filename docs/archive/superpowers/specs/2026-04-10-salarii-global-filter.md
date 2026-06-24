# Salarii Tab — Global Filter Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the floating filter button in the Agents tab actually filter all data in the Salarii sub-tab by firma, RM (regional), and ASM.

**Architecture:** All 5 salary cards fetch from separate endpoints. Each backend endpoint gains `regional` and `asm` query params that conditionally JOIN `salary_records` with `stores`. Frontend propagates `globalFilters.firma`, `globalFilters.rm`, `globalFilters.asm` to every fetch call. Internal firma/store selects in the Agenti card are removed; only the text search box remains.

**Tech Stack:** FastAPI + asyncpg + PostgreSQL (backend), React 19 + TypeScript (frontend)

---

## Scope

The following cards are ALL filtered by the global floating filter (firma, RM, ASM):

| Card | Endpoint |
|------|----------|
| Statistici Salarii | `/salarii/overview` |
| Evolutie Salarii Lunara (chart) | `/salarii/evolution` |
| Salarii vs Vânzări | `/salarii/summary` |
| Evolutie Salarii vs Vanzari (trend table) | `/salarii/trend` |
| Agenti (paginated list) | `/salarii/agents/summary` |

The `/salarii/stores` endpoint and its associated state/UI are **removed** (the internal store select is being deleted).

---

## Backend Changes — `backend/routers/salarii.py`

### Common JOIN pattern

When `regional` or `asm` is provided, filter via JOIN with `stores`:

```sql
-- Conditional JOIN (always LEFT JOIN, filter in WHERE)
LEFT JOIN stores st ON st.site_code = sr.site_code
WHERE ...
  AND ($N IS NULL OR st.regional = $N)   -- regional param
  AND ($M IS NULL OR st.asm = $M)        -- asm param
```

When `company_name` is already filtering `salary_records.company_name`, it maps directly (no JOIN needed for firma).

### `/salarii/overview` — new params: `company_name`, `regional`, `asm`

Currently takes no params. Add three optional params. When any is set, add JOIN + WHERE conditions. Return shape unchanged.

### `/salarii/evolution` — new params: `regional`, `asm`

Already accepts `company_name`. Add `regional` and `asm`. When set, JOIN with `stores`.

### `/salarii/agents/summary` — new params: `regional`, `asm`

Already accepts `company_name` and `site_code`. Add `regional` and `asm`. JOIN with `stores` when needed.

### `/salarii/summary` — new params: `regional`, `asm`

Already accepts `company_name` and `site_code`. Add `regional` and `asm`. JOIN with `stores` when needed.

### `/salarii/trend` — new params: `regional`, `asm`

Already accepts `company_name` and `site_code`. Add `regional` and `asm`. JOIN with `stores` when needed.

### `/salarii/stores` — REMOVED from frontend usage

Endpoint stays in backend (no breaking change), but frontend stops calling it.

---

## Frontend Changes

### `src/api/salarii.ts`

Add `regional?: string` and `asm?: string` to:
- A new `SalariiOverviewParams` type (new — overview had no params before)
- `fetchSalaryEvolution` params
- `fetchSalaryAgents` params
- `fetchSalarySummary` params
- `fetchSalaryTrend` params
- Update `fetchSalariiOverview` signature to accept optional params

### `src/components/SalariiSubtab.tsx`

**State removals:**
- Remove `companyFilter` state
- Remove `storeFilter` state
- Remove `availableStores` state
- Remove `loadStores` callback
- Remove `handleCompanyChange`, `handleStoreChange` functions

**Load function changes** — all 5 load functions read from `globalFilters`:
```ts
const firma = globalFilters?.firma !== 'Toate' ? globalFilters.firma : undefined;
const regional = globalFilters?.rm !== 'Toti' ? globalFilters.rm : undefined;
const asm = globalFilters?.asm !== 'Toti' ? globalFilters.asm : undefined;
```

- `loadOverview`: pass `{ company_name: firma, regional, asm }` to `fetchSalariiOverview`
- `loadEvolution`: pass `{ company_name: firma, regional, asm }` to `fetchSalaryEvolution`
- `loadSummary`: pass `regional` and `asm` in addition to existing `firma`
- `loadTrend`: pass `regional` and `asm` in addition to existing `firma`
- `loadAgents`: replace internal `companyFilter`/`storeFilter` with global `firma`/`regional`/`asm`

**useEffect dependency updates:**
- `loadOverview` and `loadEvolution` now depend on `[globalFilters]` (previously no deps)
- All existing `[globalFilters, ...]` deps remain

**UI removals in Card 5 (Agenti):**
- Remove the firma `<select>` element
- Remove the store `<select>` element
- Remove the "Reseteaza" button (or simplify it to only reset search)
- Keep the text search `<input>` unchanged

**`resetFilters` function:** Only resets `search` and `debouncedSearch`. Remove store/company reset lines.

---

## Filter Values Reference

From `AppFilters` in `MainLayout.tsx`:
- `firma` default = `'Toate'` → send `undefined` to backend
- `rm` default = `'Toti'` → send `undefined` to backend  
- `asm` default = `'Toti'` → send `undefined` to backend

---

## Testing

**Model/shape test (sync):** Verify endpoints accept new params without error (existing pytest infra).

**Integration smoke test:** With backend running, call `/salarii/overview?regional=X`, verify response shape matches existing `SalariiOverview` interface.

**Manual verification:** Set ASM filter in Agents tab floating panel → switch to Salarii sub-tab → all 5 cards show filtered data; Agenti card shows only search box, no firma/store selects.
