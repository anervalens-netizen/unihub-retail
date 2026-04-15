# Istoric Breakdowns + Incentive Magazine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add RM/ASM/Magazine/Agenti breakdown tables to Hub > Istoric, and fix the missing `incentive_qty` column in the Magazine table (both current and historic).

**Architecture:** Backend: add two missing fields to `StoreStats` Pydantic model so they survive serialization. Frontend: extend `StoreStat` type + `StoreSortKey` + `STORE_COLUMNS`; add 4 history state vars + sort states + useMemo; extend `loadHistory` to persist breakdown data in cache; render 4 table cards in the history JSX section.

**Tech Stack:** FastAPI + Pydantic (backend), React 19 + TypeScript + Tailwind (frontend), pytest (tests)

---

## Files Modified

| File | Change |
|------|--------|
| `backend/models.py` | Add `promo_qty: int = 0` and `incentive_qty: int = 0` to `StoreStats` |
| `backend/tests/test_models.py` | New: unit tests for `StoreStats` field presence |
| `src/api/types.ts` | Add `promo_qty` and `incentive_qty` to `StoreStat` interface |
| `src/components/Dashboard.tsx` | `StoreSortKey` + `STORE_COLUMNS` + incentive cell in current store table + 4 history states/sorts/memos + loadHistory cache + 4 JSX table cards |

---

### Task 1: Fix StoreStats Pydantic model

**Files:**
- Modify: `backend/models.py:216-232`
- Create: `backend/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models.py
from backend.models import StoreStats
from decimal import Decimal


def test_store_stats_has_promo_qty():
    stat = StoreStats(
        import_month="2026-03",
        site_code="TST01",
        locatie="Test Store",
        firma="Mobiup",
        regional="RM1",
        asm="ASM1",
        total_vanzari=Decimal("1000.00"),
        qty_total=10,
        nr_bonuri=5,
        nr_agenti=2,
        zile_active=20,
        target=Decimal("900.00"),
        proc_realizare_target=Decimal("111.11"),
    )
    assert stat.promo_qty == 0
    assert stat.incentive_qty == 0


def test_store_stats_accepts_incentive_qty():
    stat = StoreStats(
        import_month="2026-03",
        site_code="TST01",
        locatie="Test Store",
        firma="Mobiup",
        regional="RM1",
        asm="ASM1",
        total_vanzari=Decimal("1000.00"),
        qty_total=10,
        nr_bonuri=5,
        nr_agenti=2,
        zile_active=20,
        target=Decimal("900.00"),
        proc_realizare_target=Decimal("111.11"),
        promo_qty=3,
        incentive_qty=7,
    )
    assert stat.promo_qty == 3
    assert stat.incentive_qty == 7
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate && pytest tests/test_models.py -v
```
Expected: `AttributeError` or validation error — `StoreStats` has no `promo_qty` field.

- [ ] **Step 3: Add the two fields to StoreStats**

In `backend/models.py`, find the `StoreStats` class (lines 216–232). After `proc_realizare_target: Decimal | None`, add:

```python
class StoreStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    import_month: str
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str
    total_vanzari: Decimal
    qty_total: int | None
    nr_bonuri: int
    nr_agenti: int
    zile_active: int
    target: Decimal
    proc_realizare_target: Decimal | None
    promo_qty: int = 0
    incentive_qty: int = 0
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate && pytest tests/test_models.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 5: Run full test suite to confirm nothing broke**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate && pytest -v
```
Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
cd /opt/Mobiup/unihub
git add backend/models.py backend/tests/test_models.py
git commit -m "fix: expose promo_qty and incentive_qty in StoreStats Pydantic model"
```

---

### Task 2: Extend TypeScript StoreStat + StoreSortKey + STORE_COLUMNS

**Files:**
- Modify: `src/api/types.ts:156-170`
- Modify: `src/components/Dashboard.tsx:69-79` (StoreSortKey)
- Modify: `src/components/Dashboard.tsx:148-159` (STORE_COLUMNS)

- [ ] **Step 1: Add fields to StoreStat interface**

In `src/api/types.ts`, find the `StoreStat` interface (lines 156–170). Replace with:

```typescript
export interface StoreStat {
  import_month: string;
  site_code: string;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
  total_vanzari: number;
  qty_total: number | null;
  nr_bonuri: number;
  nr_agenti: number;
  zile_active: number;
  target: number;
  proc_realizare_target: number | null;
  promo_qty: number;
  incentive_qty: number;
}
```

- [ ] **Step 2: Add `incentive_qty` to StoreSortKey**

In `src/components/Dashboard.tsx`, find `StoreSortKey` (lines 69–79). Replace with:

```typescript
type StoreSortKey =
  | 'locatie'
  | 'site_code'
  | 'target'
  | 'total_vanzari'
  | 'proc_realizare_target'
  | 'incentive_qty'
  | 'qty_total'
  | 'nr_bonuri'
  | 'nr_agenti'
  | 'zile_active'
  | 'medie_zilnica';
```

- [ ] **Step 3: Add Incentive column to STORE_COLUMNS**

In `src/components/Dashboard.tsx`, find `STORE_COLUMNS` (lines 148–159). Replace with:

```typescript
const STORE_COLUMNS: Array<{ key: StoreSortKey; label: string }> = [
  { key: 'locatie', label: 'Magazin' },
  { key: 'site_code', label: 'Firma' },
  { key: 'target', label: 'Target' },
  { key: 'total_vanzari', label: 'Vanzari' },
  { key: 'proc_realizare_target', label: 'Procent' },
  { key: 'incentive_qty', label: 'Incentive' },
  { key: 'qty_total', label: 'Cantitate' },
  { key: 'nr_bonuri', label: 'Nr bonuri' },
  { key: 'nr_agenti', label: 'Agenti' },
  { key: 'zile_active', label: 'Zile active' },
  { key: 'medie_zilnica', label: 'Medie zilnica' },
];
```

- [ ] **Step 4: Run typecheck**

```bash
cd /opt/Mobiup/unihub && npm run typecheck 2>&1 | head -40
```
Expected: 0 errors (or only pre-existing unrelated errors).

- [ ] **Step 5: Commit**

```bash
cd /opt/Mobiup/unihub
git add src/api/types.ts src/components/Dashboard.tsx
git commit -m "feat: add incentive_qty to StoreStat type, StoreSortKey, and STORE_COLUMNS"
```

---

### Task 3: Add incentive_qty cell to current Magazine table render

**Files:**
- Modify: `src/components/Dashboard.tsx:1300-1322` (store tbody)

The current Magazine tbody renders 10 cells matching STORE_COLUMNS. After adding `incentive_qty` to STORE_COLUMNS (Task 2), the header now has 11 columns. The tbody must gain the matching cell between `proc_realizare_target` and `qty_total`.

- [ ] **Step 1: Insert incentive_qty cell in current store table tbody**

Find this block in `src/components/Dashboard.tsx` (around line 1314):

```tsx
                      <td className="px-3 py-2 font-bold text-indigo-600">{formatPercent(store.proc_realizare_target)}</td>
                      <td className="px-3 py-2">{formatInt(store.qty_total ?? 0)}</td>
```

Replace with:

```tsx
                      <td className="px-3 py-2 font-bold text-indigo-600">{formatPercent(store.proc_realizare_target)}</td>
                      <td className="px-3 py-2">{formatInt(store.incentive_qty ?? 0)}</td>
                      <td className="px-3 py-2">{formatInt(store.qty_total ?? 0)}</td>
```

- [ ] **Step 2: Run typecheck**

```bash
cd /opt/Mobiup/unihub && npm run typecheck 2>&1 | head -40
```
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
cd /opt/Mobiup/unihub
git add src/components/Dashboard.tsx
git commit -m "feat: show incentive_qty in current section Magazine table"
```

---

### Task 4: Add 4 history state vars, sort states, useMemo, and reset effect

**Files:**
- Modify: `src/components/Dashboard.tsx` (state declarations ~line 256, sort states ~line 252, useMemo ~line 784, reset useEffect ~line 483)

- [ ] **Step 1: Add 4 history data state vars**

Find the block of existing history state vars ending with (around line 234):

```typescript
  const [historyPromoIncentive, setHistoryPromoIncentive] = useState<PromoIncentiveSummary>(DEFAULT_PROMO_INCENTIVE);
```

After that line, add:

```typescript
  const [historyRegionals, setHistoryRegionals] = useState<RegionalStat[]>([]);
  const [historyAsms, setHistoryAsms] = useState<AsmStat[]>([]);
  const [historyStores, setHistoryStores] = useState<StoreStat[]>([]);
  const [historyAgents, setHistoryAgents] = useState<AgentStat[]>([]);
```

- [ ] **Step 2: Add 4 history sort states**

Find the block of existing sort states ending with (around line 255):

```typescript
  const [asmSort, setAsmSort] = useState<{ key: AsmSortKey; direction: SortDirection }>({
    key: 'total_vanzari',
    direction: 'desc',
  });
```

After that block, add:

```typescript
  const [historyRegionalSort, setHistoryRegionalSort] = useState<{ key: RegionalSortKey; direction: SortDirection }>({ key: 'total_vanzari', direction: 'desc' });
  const [historyAsmSort, setHistoryAsmSort] = useState<{ key: AsmSortKey; direction: SortDirection }>({ key: 'total_vanzari', direction: 'desc' });
  const [historyStoreSort, setHistoryStoreSort] = useState<{ key: StoreSortKey; direction: SortDirection }>({ key: 'total_vanzari', direction: 'desc' });
  const [historyAgentSort, setHistoryAgentSort] = useState<{ key: AgentSortKey; direction: SortDirection }>({ key: 'total_vanzari', direction: 'desc' });
```

- [ ] **Step 3: Add 4 sorted useMemo for history**

Find the `sortedAsms` useMemo block (around line 828) followed by `handleSortRegionals`. After the closing of `sortedAsms` (line ~837), add:

```typescript
  const sortedHistoryRegionals = useMemo(() => {
    const rows = [...historyRegionals];
    rows.sort((left, right) => {
      const leftValue = getRegionalSortValue(left, historyRegionalSort.key);
      const rightValue = getRegionalSortValue(right, historyRegionalSort.key);
      const result = leftValue - rightValue;
      return historyRegionalSort.direction === 'asc' ? result : -result;
    });
    return rows;
  }, [historyRegionals, historyRegionalSort]);

  const sortedHistoryAsms = useMemo(() => {
    const rows = [...historyAsms];
    rows.sort((left, right) => {
      const leftValue = getAsmSortValue(left, historyAsmSort.key);
      const rightValue = getAsmSortValue(right, historyAsmSort.key);
      const result = leftValue - rightValue;
      return historyAsmSort.direction === 'asc' ? result : -result;
    });
    return rows;
  }, [historyAsms, historyAsmSort]);

  const sortedHistoryStores = useMemo(() => {
    const rows = [...historyStores];
    rows.sort((left, right) => {
      const leftValue = getStoreSortValue(left, historyStoreSort.key);
      const rightValue = getStoreSortValue(right, historyStoreSort.key);
      const result = leftValue - rightValue;
      return historyStoreSort.direction === 'asc' ? result : -result;
    });
    return rows;
  }, [historyStores, historyStoreSort]);

  const sortedHistoryAgents = useMemo(() => {
    const rows = [...historyAgents];
    rows.sort((left, right) => {
      const leftValue = getAgentSortValue(left, historyAgentSort.key);
      const rightValue = getAgentSortValue(right, historyAgentSort.key);
      const result = leftValue - rightValue;
      return historyAgentSort.direction === 'asc' ? result : -result;
    });
    return rows;
  }, [historyAgents, historyAgentSort]);
```

- [ ] **Step 4: Add 4 sort handler callbacks**

Find `handleSortAsms` (around line 847). After its closing `}, []);`, add:

```typescript
  const handleSortHistoryRegionals = useCallback((key: RegionalSortKey) => {
    setHistoryRegionalSort((current) =>
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: key === 'regional' ? 'asc' : 'desc' }
    );
  }, []);

  const handleSortHistoryAsms = useCallback((key: AsmSortKey) => {
    setHistoryAsmSort((current) =>
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: key === 'asm' || key === 'regional' ? 'asc' : 'desc' }
    );
  }, []);

  const handleSortHistoryStores = useCallback((key: StoreSortKey) => {
    setHistoryStoreSort((current) =>
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: key === 'locatie' || key === 'site_code' ? 'asc' : 'desc' }
    );
  }, []);

  const handleSortHistoryAgents = useCallback((key: AgentSortKey) => {
    setHistoryAgentSort((current) =>
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: key === 'locatie' || key === 'agent' ? 'asc' : 'desc' }
    );
  }, []);
```

- [ ] **Step 5: Add history breakdown resets to the reset useEffect**

Find the `useEffect` that resets history state on section/historyMonth change (around line 483). It currently ends with:

```typescript
    setHistoryPromoIncentive(DEFAULT_PROMO_INCENTIVE);
    setHistoryError(null);
```

Add before `setHistoryError(null);`:

```typescript
    setHistoryRegionals([]);
    setHistoryAsms([]);
    setHistoryStores([]);
    setHistoryAgents([]);
```

- [ ] **Step 6: Run typecheck**

```bash
cd /opt/Mobiup/unihub && npm run typecheck 2>&1 | head -40
```
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
cd /opt/Mobiup/unihub
git add src/components/Dashboard.tsx
git commit -m "feat: add history breakdown state, sort, memo for RM/ASM/Magazine/Agenti"
```

---

### Task 5: Extend loadHistory cache to include breakdown data

**Files:**
- Modify: `src/components/Dashboard.tsx:384-461` (loadHistory callback)

The `loadHistory` callback has three touch-points: the cache type declaration, the cache restore block, and the `setCachedView` call.

- [ ] **Step 1: Extend the inline cache type**

Find the `getCachedView<{...}>` call in `loadHistory` (around line 387). The current type ends with `promoIncentive: PromoIncentiveSummary;`. Replace the full generic type argument:

```typescript
    const cachedDetail = getCachedView<{
      summary: DashboardSummary;
      receiptBucketMix: ReceiptBucketItem[];
      focusSubcategoryMix: CategoryMixItem[];
      dailySales: DailySalesPoint[];
      categoryMix: CategoryMixItem[];
      brandMix: BrandMixItem[];
      specialCards: DashboardSpecialCard[];
      periodComparison: PeriodComparisonPayload | null;
      promoIncentive: PromoIncentiveSummary;
      regionals: RegionalStat[];
      asms: AsmStat[];
      stores: StoreStat[];
      agents: AgentStat[];
    }>(historyDetailCacheKey, DASHBOARD_CACHE_TTL_MS);
```

- [ ] **Step 2: Restore breakdown state from cache**

Find the `if (cachedDetail.value)` block (around line 402). It currently ends with:

```typescript
        setHistoryPromoIncentive(cachedDetail.value.promoIncentive);
      }
```

Add before the closing `}`:

```typescript
        setHistoryRegionals(cachedDetail.value.regionals ?? []);
        setHistoryAsms(cachedDetail.value.asms ?? []);
        setHistoryStores(cachedDetail.value.stores ?? []);
        setHistoryAgents(cachedDetail.value.agents ?? []);
```

- [ ] **Step 3: Save breakdown data to cache**

Find the `setCachedView(historyDetailCacheKey, {` call (around line 438). It currently ends with:

```typescript
          promoIncentive: allData.promo_incentive ?? DEFAULT_PROMO_INCENTIVE,
        });
```

Add before the closing `});`:

```typescript
          regionals: allData.regionals ?? [],
          asms: allData.asms ?? [],
          stores: allData.stores,
          agents: allData.agents,
```

- [ ] **Step 4: Save breakdown state from fresh fetch**

Find the block in `.then(([histData, allData]) => {` where `setHistoryPromoIncentive` is called (around line 437). After that call, add:

```typescript
        setHistoryRegionals(allData.regionals ?? []);
        setHistoryAsms(allData.asms ?? []);
        setHistoryStores(allData.stores);
        setHistoryAgents(allData.agents);
```

- [ ] **Step 5: Run typecheck**

```bash
cd /opt/Mobiup/unihub && npm run typecheck 2>&1 | head -40
```
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
cd /opt/Mobiup/unihub
git add src/components/Dashboard.tsx
git commit -m "feat: persist RM/ASM/Magazine/Agenti breakdown data in loadHistory and cache"
```

---

### Task 6: Render 4 breakdown table cards in Istoric section

**Files:**
- Modify: `src/components/Dashboard.tsx:1747` (insert after grid closing div, before fragment close)

The history section's last JSX element is a `<div className="grid gap-3 lg:grid-cols-[1.2fr_1fr]">` (line 1695) that closes at line 1747 `</div>`. The 4 new breakdown cards are appended after that div, before the `</>` at line 1748.

- [ ] **Step 1: Add HIST_* column constants**

Find `const STORE_COLUMNS` (line 148). Just before it (but after ASM_COLUMNS), add the 4 HIST_* constants. In practice, place them right after `ASM_COLUMNS` definition (around line 203), before the `export function Dashboard`:

```typescript
const HIST_REGIONAL_COLUMNS = REGIONAL_COLUMNS.filter((c) => c.key !== 'promo_qty');
const HIST_ASM_COLUMNS = ASM_COLUMNS.filter((c) => c.key !== 'promo_qty');
const HIST_STORE_COLUMNS = STORE_COLUMNS; // promo_qty not in STORE_COLUMNS
const HIST_AGENT_COLUMNS = AGENT_COLUMNS.filter((c) => c.key !== 'promo_qty');
```

- [ ] **Step 2: Insert the 4 table cards after the grid closing div**

Find (around line 1747):

```tsx
              </div>
            </>
          )}
```

Replace with:

```tsx
              </div>

              {/* Breakdown tables — RM / ASM / Magazine / Agenti */}
              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <MapPin size={16} className="text-indigo-500" />
                      <h3 className="text-sm font-bold">RM</h3>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Sortare: {HIST_REGIONAL_COLUMNS.find((c) => c.key === historyRegionalSort.key)?.label} ({historyRegionalSort.direction}) · {historyRegionals.length} regionali
                    </p>
                  </div>
                </div>
                <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
                  <table className="min-w-330 w-full border-collapse text-xs">
                    <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                      <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                        {HIST_REGIONAL_COLUMNS.map((column, i) => (
                          <React.Fragment key={column.key}>
                            <SortableHeader
                              label={column.label}
                              active={historyRegionalSort.key === column.key}
                              direction={historyRegionalSort.direction}
                              onClick={() => handleSortHistoryRegionals(column.key)}
                              className={i === 0 ? 'w-28' : ''}
                            />
                          </React.Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedHistoryRegionals.map((row, index) => (
                        <tr
                          key={row.regional}
                          className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                        >
                          <td className="max-w-0 w-28 truncate px-3 py-2 font-semibold">{row.regional}</td>
                          <td className="px-3 py-2">{formatCurrency(row.target)}</td>
                          <td className="px-3 py-2">{formatCurrency(row.total_vanzari)}</td>
                          <td className="px-3 py-2 font-bold text-indigo-600">{formatPercent(row.proc_realizare_target)}</td>
                          <td className="px-3 py-2">{formatInt(row.incentive_qty)}</td>
                          <td className="px-3 py-2">{formatInt(row.qty_total)}</td>
                          <td className="px-3 py-2">{formatInt(row.nr_bonuri)}</td>
                          <td className="px-3 py-2">{formatCurrency(row.medie_zilnica ?? 0)}</td>
                          <td className="px-3 py-2">{formatPercent(row.proc_bon2acc)}</td>
                          <td className="px-3 py-2">{formatPercent(row.prc_focus_acc_qty)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <Users size={16} className="text-indigo-500" />
                      <h3 className="text-sm font-bold">ASM</h3>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Sortare: {HIST_ASM_COLUMNS.find((c) => c.key === historyAsmSort.key)?.label} ({historyAsmSort.direction}) · {historyAsms.length} ASM
                    </p>
                  </div>
                </div>
                <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
                  <table className="min-w-330 w-full border-collapse text-xs">
                    <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                      <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                        {HIST_ASM_COLUMNS.map((column, i) => (
                          <React.Fragment key={column.key}>
                            <SortableHeader
                              label={column.label}
                              active={historyAsmSort.key === column.key}
                              direction={historyAsmSort.direction}
                              onClick={() => handleSortHistoryAsms(column.key)}
                              className={i === 0 ? 'w-28' : ''}
                            />
                          </React.Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedHistoryAsms.map((row, index) => (
                        <tr
                          key={row.asm}
                          className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                        >
                          <td className="max-w-0 w-28 truncate px-3 py-2 font-semibold">{row.asm}</td>
                          <td className="px-3 py-2">{formatCurrency(row.target)}</td>
                          <td className="px-3 py-2">{formatCurrency(row.total_vanzari)}</td>
                          <td className="px-3 py-2 font-bold text-indigo-600">{formatPercent(row.proc_realizare_target)}</td>
                          <td className="px-3 py-2">{formatInt(row.incentive_qty)}</td>
                          <td className="px-3 py-2">{formatInt(row.qty_total)}</td>
                          <td className="px-3 py-2">{formatInt(row.nr_bonuri)}</td>
                          <td className="px-3 py-2">{formatCurrency(row.medie_zilnica ?? 0)}</td>
                          <td className="px-3 py-2">{formatPercent(row.proc_bon2acc)}</td>
                          <td className="px-3 py-2">{formatPercent(row.prc_focus_acc_qty)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <Building2 size={16} className="text-indigo-500" />
                      <h3 className="text-sm font-bold">Magazine</h3>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Sortare: {HIST_STORE_COLUMNS.find((c) => c.key === historyStoreSort.key)?.label} ({historyStoreSort.direction}) · {historyStores.length} magazine
                    </p>
                  </div>
                </div>
                <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
                  <table className="min-w-330 w-full border-collapse text-xs">
                    <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                      <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                        {HIST_STORE_COLUMNS.map((column, i) => (
                          <React.Fragment key={column.key}>
                            <SortableHeader
                              label={column.label}
                              active={historyStoreSort.key === column.key}
                              direction={historyStoreSort.direction}
                              onClick={() => handleSortHistoryStores(column.key)}
                              className={i === 0 ? 'w-36' : ''}
                            />
                          </React.Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedHistoryStores.map((store, index) => (
                        <tr
                          key={store.site_code}
                          className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                        >
                          <td className="max-w-0 w-36 truncate px-3 py-2 font-semibold">{store.locatie}</td>
                          <td className="px-3 py-2 text-center font-bold">
                            {store.firma?.toLowerCase().includes('mobiup')
                              ? <span className="text-red-500">MU</span>
                              : <span className="text-blue-500">MC</span>
                            }
                          </td>
                          <td className="px-3 py-2">{formatCurrency(store.target)}</td>
                          <td className="px-3 py-2">{formatCurrency(store.total_vanzari)}</td>
                          <td className="px-3 py-2 font-bold text-indigo-600">{formatPercent(store.proc_realizare_target)}</td>
                          <td className="px-3 py-2">{formatInt(store.incentive_qty ?? 0)}</td>
                          <td className="px-3 py-2">{formatInt(store.qty_total ?? 0)}</td>
                          <td className="px-3 py-2">{formatInt(store.nr_bonuri)}</td>
                          <td className="px-3 py-2">{formatInt(store.nr_agenti)}</td>
                          <td className="px-3 py-2">{formatInt(store.zile_active)}</td>
                          <td className="px-3 py-2">{formatCurrency(getStoreDailyAverage(store))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-bold">Agenti</h3>
                    <p className="text-[11px] text-slate-500">
                      Sortare: {HIST_AGENT_COLUMNS.find((c) => c.key === historyAgentSort.key)?.label} ({historyAgentSort.direction}) · {historyAgents.length} agenti
                    </p>
                  </div>
                </div>
                <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
                  <table className="min-w-370 w-full border-collapse text-xs">
                    <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                      <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                        {HIST_AGENT_COLUMNS.map((column, i) => (
                          <React.Fragment key={column.key}>
                            <SortableHeader
                              label={column.label}
                              active={historyAgentSort.key === column.key}
                              direction={historyAgentSort.direction}
                              onClick={() => handleSortHistoryAgents(column.key)}
                              className={i === 0 ? 'w-24' : ''}
                            />
                          </React.Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedHistoryAgents.map((agentRow, index) => (
                        <tr
                          key={`${agentRow.agent}-${agentRow.site_code}`}
                          className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                        >
                          <td className="max-w-0 w-24 truncate px-3 py-2 font-bold">{agentRow.agent}</td>
                          <td className="max-w-[7rem] truncate px-3 py-2 text-slate-500">{agentRow.locatie}</td>
                          <td className="px-3 py-2">{formatCurrency(agentRow.target ?? 0)}</td>
                          <td className="px-3 py-2 font-bold text-indigo-600">{formatCurrency(agentRow.total_vanzari)}</td>
                          <td className="px-3 py-2">{formatPercent(agentRow.proc_realizare_target)}</td>
                          <td className="px-3 py-2">{formatInt(agentRow.incentive_qty ?? 0)}</td>
                          <td className="px-3 py-2">{formatInt(agentRow.acc_qty_realizat)}</td>
                          <td className="px-3 py-2">{formatInt(agentRow.nr_bonuri)}</td>
                          <td className="px-3 py-2">{formatInt(agentRow.zile_lucrate)}</td>
                          <td className="px-3 py-2">{formatCurrency(agentRow.medie_zilnica ?? 0)}</td>
                          <td className="px-3 py-2">{formatPercent(agentRow.proc_bon2acc)}</td>
                          <td className="px-3 py-2">{formatPercent(agentRow.prc_focus_acc_qty)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
```

- [ ] **Step 3: Run typecheck**

```bash
cd /opt/Mobiup/unihub && npm run typecheck 2>&1 | head -40
```
Expected: 0 errors.

- [ ] **Step 4: Run build**

```bash
cd /opt/Mobiup/unihub && npm run build 2>&1 | tail -20
```
Expected: build succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
cd /opt/Mobiup/unihub
git add src/components/Dashboard.tsx
git commit -m "feat: render RM/ASM/Magazine/Agenti breakdown tables in Istoric section"
```

---

### Task 7: Deploy and validate

- [ ] **Step 1: Run full backend test suite**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate && pytest -v
```
Expected: all tests PASS.

- [ ] **Step 2: Deploy**

```bash
cd /opt/Mobiup/unihub && npm run build && sudo systemctl restart unihub-backend
```

- [ ] **Step 3: Manual verification checklist**

Open https://unihub.astancu.eu/ and verify:

1. **Hub > Luna în curs > Magazine**: `Incentive` column appears between `Procent` and `Cantitate`. Values are integers (0 for stores with no incentive).
2. **Hub > Istoric**: Select any luna analizata. After loading, 4 new cards appear below "Top categorii si branduri": RM, ASM, Magazine, Agenti.
3. **RM / ASM tables**: No `Promo` column. `Incentive` column present.
4. **Magazine table in Istoric**: Same columns as current section (including `Incentive`). No `Promo` column (it was never in `STORE_COLUMNS`).
5. **Agenti table in Istoric**: No `Promo` column. `Incentive` column present.
6. **Sorting**: Click any column header in any of the 4 history tables — rows reorder. Click again — direction toggles. Does NOT affect sort state in `Luna în curs`.
7. **Filter change**: Change `luna analizata` — tables reload with new data. Tables clear immediately on month change.

---

## Acceptance Criteria

- [ ] `incentive_qty` shows in Magazine card in "Luna în curs"
- [ ] Istoric section renders 4 breakdown tables under existing cards
- [ ] Tables respond to `luna analizata` filter
- [ ] Sorting per column is independent from "Luna în curs" sort state
- [ ] No `promo_qty` column in any History table
- [ ] TypeScript 0 errors, build passing, all pytest passing
