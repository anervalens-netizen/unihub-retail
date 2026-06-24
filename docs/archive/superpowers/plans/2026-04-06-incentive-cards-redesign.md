# Incentive Cards Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extinde cardurile Top Agenti si Top Magazine din sectiunea Incentive cu coloane noi (%Prev./Cant./Val Inc.), sortare per coloana, scroll intern si badge firma la magazine.

**Architecture:** Backend extinde modelele Pydantic si query-urile sa returneze `qty_sold`, `val_incentive`, `achievement` per agent si `firma` per magazin. Frontend implementeaza o componenta `SortableTable` locala in `Campaigns.tsx` care gestioneaza sort client-side.

**Tech Stack:** FastAPI + Pydantic (backend), React 19 + TypeScript + Tailwind (frontend)

---

## File Map

| Fisier | Modificare |
|--------|-----------|
| `backend/models.py` | Extinde `IncentiveTopAgent`, adauga `firma` in `PromoTopStore` |
| `backend/routers/campaigns.py` | Acumul `agent_qty` + `agent_site`, adauga `firma` in store queries, scot `[:10]` si `LIMIT 10` |
| `backend/tests/test_campaigns.py` | Fisier nou — teste unitare pentru modelele extinse |
| `src/components/Campaigns.tsx` | `SortableTable` + refactored agent/store cards |

---

## Task 1: Extinde modelele Pydantic

**Files:**
- Modify: `backend/models.py`
- Test: `backend/tests/test_campaigns.py` (creat acum)

- [ ] **Step 1: Scrie testele unitare pentru noile modele**

Creeaza `backend/tests/test_campaigns.py`:

```python
"""Unit tests for campaigns models."""
from __future__ import annotations

import pytest
from models import IncentiveTopAgent, PromoTopStore


def test_incentive_top_agent_full_fields():
    agent = IncentiveTopAgent(
        agent_name="POPESCU ION",
        qty_sold=150,
        val_incentive=750.0,
        achievement=1.03,
    )
    assert agent.agent_name == "POPESCU ION"
    assert agent.qty_sold == 150
    assert agent.val_incentive == 750.0
    assert agent.achievement == pytest.approx(1.03)


def test_incentive_top_agent_no_target():
    agent = IncentiveTopAgent(
        agent_name="IONESCU ANA",
        qty_sold=80,
        val_incentive=0.0,
        achievement=None,
    )
    assert agent.achievement is None


def test_promo_top_store_has_firma():
    store = PromoTopStore(
        store_name="S001 - Pitesti Park Lake",
        qty=200,
        total_qty=200,
        category_qty=0,
        incentive_value=1000.0,
        achievement=1.05,
        firma="Mobiup",
    )
    assert store.firma == "Mobiup"


def test_promo_top_store_firma_default_empty():
    store = PromoTopStore(
        store_name="S002 - Ploiesti",
        qty=100,
        total_qty=100,
        category_qty=0,
    )
    assert store.firma == ""
```

- [ ] **Step 2: Ruleaza testele — trebuie sa pice (modelele nu au inca campurile noi)**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate
pytest tests/test_campaigns.py -v
```

Output asteptat: FAILED cu `ValidationError` sau `TypeError` (campurile lipsesc).

- [ ] **Step 3: Modifica `IncentiveTopAgent` si `PromoTopStore` in `backend/models.py`**

Gaseste clasa `IncentiveTopAgent` (linia ~745) si inlocuieste:

```python
# INAINTE:
class IncentiveTopAgent(BaseModel):
    agent_name: str
    qty: int
```

Cu:

```python
class IncentiveTopAgent(BaseModel):
    agent_name: str
    qty_sold: int
    val_incentive: float
    achievement: float | None = None
```

Gaseste clasa `PromoTopStore` (linia ~736) si adauga campul `firma`:

```python
class PromoTopStore(BaseModel):
    store_name: str
    qty: int
    total_qty: int
    category_qty: int
    incentive_value: float = 0.0
    achievement: float | None = None
    firma: str = ""          # <-- adaugat
```

- [ ] **Step 4: Ruleaza testele — trebuie sa treaca**

```bash
pytest tests/test_campaigns.py -v
```

Output asteptat:
```
PASSED tests/test_campaigns.py::test_incentive_top_agent_full_fields
PASSED tests/test_campaigns.py::test_incentive_top_agent_no_target
PASSED tests/test_campaigns.py::test_promo_top_store_has_firma
PASSED tests/test_campaigns.py::test_promo_top_store_firma_default_empty
```

- [ ] **Step 5: Commit**

```bash
cd /opt/Mobiup/unihub
git add backend/models.py backend/tests/test_campaigns.py
git commit -m "feat: extend IncentiveTopAgent with qty_sold/val_incentive/achievement, add firma to PromoTopStore"
```

---

## Task 2: Modifica campaigns.py — agenti

**Files:**
- Modify: `backend/routers/campaigns.py` (liniile ~546–563)

- [ ] **Step 1: Identifica bucla de acumulare agent_bonus**

Deschide `backend/routers/campaigns.py`. Cauta blocul (linia ~546):

```python
agent_bonus: dict[str, float] = {}
tier_qty: dict[float, int] = {}
tier_value: dict[float, float] = {}
for row in agent_item_rows:
    agent_name = row["agent"]
    multiplier = store_multipliers.get(row["site_code"], 0)
    qty = max(0, int(row["qty"]))
    reward = reward_map.get(row["item_code"], 0)
    bonus = qty * reward * multiplier
    agent_bonus[agent_name] = agent_bonus.get(agent_name, 0) + bonus
    # Category = reward tier (regardless of store multiplier for grouping)
    tier_qty[reward] = tier_qty.get(reward, 0) + qty
    tier_value[reward] = tier_value.get(reward, 0) + qty * reward
```

- [ ] **Step 2: Inlocuieste bucla pentru a acumula si `agent_qty` si `agent_site`**

```python
agent_bonus: dict[str, float] = {}
agent_qty: dict[str, int] = {}       # bucati incentive per agent
agent_site: dict[str, str] = {}      # site_code per agent (pentru achievement lookup)
tier_qty: dict[float, int] = {}
tier_value: dict[float, float] = {}
for row in agent_item_rows:
    agent_name = row["agent"]
    site = row["site_code"]
    multiplier = store_multipliers.get(site, 0)
    qty = max(0, int(row["qty"]))
    reward = reward_map.get(row["item_code"], 0)
    bonus = qty * reward * multiplier
    agent_bonus[agent_name] = agent_bonus.get(agent_name, 0) + bonus
    agent_qty[agent_name] = agent_qty.get(agent_name, 0) + qty
    agent_site[agent_name] = site
    tier_qty[reward] = tier_qty.get(reward, 0) + qty
    tier_value[reward] = tier_value.get(reward, 0) + qty * reward
```

- [ ] **Step 3: Inlocuieste constructia `top_agents` (linia ~560)**

Gaseste si inlocuieste:
```python
# INAINTE:
top_agents = [
    IncentiveTopAgent(agent_name=agent, qty=round(bonus))
    for agent, bonus in sorted(agent_bonus.items(), key=lambda x: -x[1])
][:10]
```

Cu:
```python
top_agents = [
    IncentiveTopAgent(
        agent_name=agent,
        qty_sold=agent_qty.get(agent, 0),
        val_incentive=round(bonus, 2),
        achievement=store_achievements.get(agent_site.get(agent, "")),
    )
    for agent, bonus in sorted(agent_bonus.items(), key=lambda x: -x[1])
]
# Fara [:10] — toti agentii
```

- [ ] **Step 4: Verifica typecheck**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate
python -c "import routers.campaigns; print('OK')"
```

Output asteptat: `OK`

- [ ] **Step 5: Commit**

```bash
cd /opt/Mobiup/unihub
git add backend/routers/campaigns.py
git commit -m "feat: accumulate qty_sold and achievement per agent, remove [:10] limit"
```

---

## Task 3: Modifica campaigns.py — magazine (firma + toate magazinele)

**Files:**
- Modify: `backend/routers/campaigns.py` (liniile ~390–495)

Sunt 3 locuri unde se construieste `top_stores`. Le adresam pe rand.

- [ ] **Step 1: Adauga `firma` in query-ul promo `store_rows` (calea `has_active_promotion`)**

Gaseste query-ul `store_rows` (linia ~393, cu `reporting_item_day`):

```python
# INAINTE:
store_rows = await conn.fetch(
    f"""
    SELECT
        agg.site_code,
        MAX(agg.locatie) AS locatie,
        COALESCE(SUM(agg.positive_quantity), 0)::INT AS qty,
        COALESCE(SUM(agg.net_quantity), 0)::INT AS total_qty
    FROM reporting_item_day agg
    WHERE {" AND ".join(promo_clauses)}
    GROUP BY agg.site_code
    ORDER BY qty DESC
    LIMIT 10
    """,
```

Inlocuieste cu:
```python
store_rows = await conn.fetch(
    f"""
    SELECT
        agg.site_code,
        MAX(agg.locatie) AS locatie,
        MAX(agg.firma) AS firma,
        COALESCE(SUM(agg.positive_quantity), 0)::INT AS qty,
        COALESCE(SUM(agg.net_quantity), 0)::INT AS total_qty
    FROM reporting_item_day agg
    WHERE {" AND ".join(promo_clauses)}
    GROUP BY agg.site_code
    ORDER BY qty DESC
    """,
```

(Scos `LIMIT 10`.)

- [ ] **Step 2: Adauga `firma` la constructia `PromoTopStore` din `store_rows`**

Gaseste constructia (imediat dupa query-ul de mai sus):

```python
# INAINTE:
top_stores = [
    PromoTopStore(
        store_name=f"{row['site_code']} - {row['locatie']}",
        qty=row["qty"],
        total_qty=row["total_qty"],
        category_qty=0,
        incentive_value=0.0,
        achievement=store_achievements.get(row["site_code"]),
    )
    for row in store_rows
]
```

Inlocuieste cu:
```python
top_stores = [
    PromoTopStore(
        store_name=f"{row['site_code']} - {row['locatie']}",
        qty=row["qty"],
        total_qty=row["total_qty"],
        category_qty=0,
        incentive_value=0.0,
        achievement=store_achievements.get(row["site_code"]),
        firma=row["firma"] or "",
    )
    for row in store_rows
]
```

- [ ] **Step 3: Adauga `firma` in query-ul `store_item_rows` (folosit in ambele cai)**

Gaseste query-ul `store_item_rows` (linia ~455, cu `reporting_item_month`):

```python
# INAINTE:
store_item_rows = await conn.fetch(
    f"""
    SELECT agg.site_code, MAX(agg.locatie) AS locatie,
           agg.item_code,
           COALESCE(SUM(agg.net_quantity), 0)::INT AS qty
    FROM reporting_item_month agg
    WHERE {" AND ".join(inc_store_clauses)}
    GROUP BY agg.site_code, agg.item_code
    """,
```

Inlocuieste cu:
```python
store_item_rows = await conn.fetch(
    f"""
    SELECT agg.site_code, MAX(agg.locatie) AS locatie,
           MAX(agg.firma) AS firma,
           agg.item_code,
           COALESCE(SUM(agg.net_quantity), 0)::INT AS qty
    FROM reporting_item_month agg
    WHERE {" AND ".join(inc_store_clauses)}
    GROUP BY agg.site_code, agg.item_code
    """,
```

- [ ] **Step 4: Stocheaza `firma` in `store_inc` si foloseste-o la constructia `PromoTopStore`**

Gaseste bucla care construieste `store_inc` (linia ~462):

```python
# INAINTE:
store_inc: dict[str, list] = {}
for row in store_item_rows:
    sc = row["site_code"]
    loc = row["locatie"]
    val = max(0, int(row["qty"])) * reward_map_for_stores.get(row["item_code"], 0) * store_multipliers.get(sc, 0)
    if sc not in store_inc:
        store_inc[sc] = [loc, 0.0]
    store_inc[sc][1] += val
```

Inlocuieste cu:
```python
store_inc: dict[str, list] = {}   # {site_code: [locatie, incentive_value, firma]}
for row in store_item_rows:
    sc = row["site_code"]
    loc = row["locatie"]
    firma_val = row["firma"] or ""
    val = max(0, int(row["qty"])) * reward_map_for_stores.get(row["item_code"], 0) * store_multipliers.get(sc, 0)
    if sc not in store_inc:
        store_inc[sc] = [loc, 0.0, firma_val]
    store_inc[sc][1] += val
```

- [ ] **Step 5: Actualizeaza ambele constructii de `PromoTopStore` care folosesc `store_inc`**

**Calea cu promotie activa** (patch `incentive_value` in `top_stores`):

```python
# INAINTE:
top_stores = [
    PromoTopStore(
        store_name=s.store_name,
        qty=s.qty,
        total_qty=s.total_qty,
        category_qty=s.category_qty,
        incentive_value=round(store_inc.get(s.store_name.split(" - ")[0], [None, 0.0])[1], 2),
        achievement=s.achievement,
    )
    for s in top_stores
]
```

Inlocuieste cu:
```python
top_stores = [
    PromoTopStore(
        store_name=s.store_name,
        qty=s.qty,
        total_qty=s.total_qty,
        category_qty=s.category_qty,
        incentive_value=round(store_inc.get(s.store_name.split(" - ")[0], [None, 0.0, ""])[1], 2),
        achievement=s.achievement,
        firma=s.firma,
    )
    for s in top_stores
]
```

**Calea fara promotie** (build `top_stores` din `store_inc`, cu `[:10]`):

```python
# INAINTE:
top_stores = [
    PromoTopStore(
        store_name=f"{sc} - {data[0]}",
        qty=0,
        total_qty=0,
        category_qty=0,
        incentive_value=round(data[1], 2),
        achievement=store_achievements.get(sc),
    )
    for sc, data in sorted(store_inc.items(), key=lambda x: -x[1][1])
    if data[1] > 0
][:10]
```

Inlocuieste cu:
```python
top_stores = [
    PromoTopStore(
        store_name=f"{sc} - {data[0]}",
        qty=0,
        total_qty=0,
        category_qty=0,
        incentive_value=round(data[1], 2),
        achievement=store_achievements.get(sc),
        firma=data[2],
    )
    for sc, data in sorted(store_inc.items(), key=lambda x: -x[1][1])
    if data[1] > 0
]
# Fara [:10] — toate magazinele
```

- [ ] **Step 6: Verifica typecheck**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate
python -c "import routers.campaigns; print('OK')"
```

Output asteptat: `OK`

- [ ] **Step 7: Ruleaza toate testele backend**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Output asteptat: toate testele existente + cele 4 noi PASSED.

- [ ] **Step 8: Commit**

```bash
cd /opt/Mobiup/unihub
git add backend/routers/campaigns.py
git commit -m "feat: add firma to PromoTopStore query, remove store LIMIT 10, include all stores"
```

---

## Task 4: Frontend — componenta SortableTable

**Files:**
- Modify: `src/components/Campaigns.tsx`

- [ ] **Step 1: Actualizeaza tipurile API in `src/api/types.ts`**

Gaseste `IncentiveTopAgent` si `PromoTopStore` in `src/api/types.ts` si actualizeaza:

```typescript
// INAINTE:
export interface IncentiveTopAgent {
  agent_name: string;
  qty: number;
}
```

Inlocuieste cu:
```typescript
export interface IncentiveTopAgent {
  agent_name: string;
  qty_sold: number;
  val_incentive: number;
  achievement: number | null;
}
```

Gaseste `PromoTopStore` si adauga `firma`:
```typescript
export interface PromoTopStore {
  store_name: string;
  qty: number;
  total_qty: number;
  category_qty: number;
  incentive_value: number;
  achievement: number | null;
  firma: string;           // <-- adaugat
}
```

- [ ] **Step 2: Verifica typecheck dupa schimbare types**

```bash
cd /opt/Mobiup/unihub && npm run typecheck 2>&1 | head -30
```

Output asteptat: erori TypeScript la `Campaigns.tsx` unde se referentiaza `qty` sau campuri vechi — confirma ca trebuie actualizat si frontend-ul.

- [ ] **Step 3: Adauga componenta `SortableTable` in `Campaigns.tsx`**

La sfarsitul fisierului `src/components/Campaigns.tsx`, inainte de ultima linie, adauga:

```typescript
type SortDir = 'asc' | 'desc';

interface ColDef<T> {
  key: keyof T | 'rank';
  label: string;
  align?: 'left' | 'right';
  sortable?: boolean;
  render: (row: T, index: number) => React.ReactNode;
}

function SortableTable<T extends Record<string, unknown>>({
  rows,
  columns,
  defaultSortKey,
  defaultSortDir = 'desc',
  maxHeightClass = 'max-h-[360px]',
}: {
  rows: T[];
  columns: ColDef<T>[];
  defaultSortKey: keyof T;
  defaultSortDir?: SortDir;
  maxHeightClass?: string;
}) {
  const [sortKey, setSortKey] = useState<keyof T>(defaultSortKey);
  const [sortDir, setSortDir] = useState<SortDir>(defaultSortDir);

  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sortKey);
    if (!col || col.key === 'rank') return rows;
    return [...rows].sort((a, b) => {
      const av = a[sortKey as keyof T];
      const bv = b[sortKey as keyof T];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [rows, columns, sortKey, sortDir]);

  function handleSort(key: keyof T | 'rank') {
    if (key === 'rank') return;
    const k = key as keyof T;
    if (k === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(k);
      setSortDir('desc');
    }
  }

  return (
    <div className={`${maxHeightClass} overflow-y-auto rounded-xl`} style={{ scrollbarWidth: 'thin', scrollbarColor: '#c7d2fe transparent' }}>
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={String(col.key)}
                onClick={() => handleSort(col.key)}
                className={`sticky top-0 z-10 bg-indigo-50/80 px-2 py-2 text-[9px] font-bold uppercase tracking-wide text-slate-500 backdrop-blur-sm dark:bg-indigo-950/60 ${
                  col.align === 'right' ? 'text-right' : 'text-left'
                } ${col.sortable !== false && col.key !== 'rank' ? 'cursor-pointer select-none hover:text-indigo-600' : ''}`}
              >
                {col.label}
                {col.sortable !== false && col.key !== 'rank' && (
                  <span className="ml-1 inline-block w-2 text-center">
                    {sortKey === col.key ? (sortDir === 'asc' ? '▲' : '▼') : '⇅'}
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, index) => (
            <tr
              key={index}
              className={index % 2 === 0 ? 'bg-indigo-50/30 dark:bg-indigo-900/10' : ''}
            >
              {columns.map((col) => (
                <td
                  key={String(col.key)}
                  className={`px-2 py-1.5 ${col.align === 'right' ? 'text-right' : 'text-left'}`}
                >
                  {col.render(row, index)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Verifica typecheck**

```bash
npm run typecheck 2>&1 | head -20
```

Output asteptat: fara erori noi legate de `SortableTable`.

---

## Task 5: Frontend — card Top Agenti

**Files:**
- Modify: `src/components/Campaigns.tsx` — inlocuieste cardul "Top 10 Agenti"

- [ ] **Step 1: Helper pentru culoarea achievement**

Adauga aceasta functie helper langa `SortableTable` (sau inainte de ea):

```typescript
function achievementColor(ach: number | null): string {
  if (ach === null || ach === undefined) return 'text-slate-400';
  if (ach >= 0.99) return 'text-emerald-600 font-black';
  if (ach >= 0.89) return 'text-amber-500 font-semibold';
  return 'text-red-500';
}

function achievementLabel(ach: number | null): string {
  if (ach === null || ach === undefined) return '—';
  return `${Math.round(ach * 100)}%`;
}
```

- [ ] **Step 2: Inlocuieste cardul "Top 10 Agenti" din JSX**

Gaseste in JSX (`activeSection === 'campaigns'`) blocul:

```tsx
{/* Top 10 Agenti — card separat */}
{promoData && promoData.top_agents.length > 0 && (
  <div className="glass rounded-4xl border border-indigo-100 bg-linear-to-br from-indigo-50 via-white to-white p-4 dark:border-indigo-900/30 dark:from-indigo-950/20 dark:via-slate-900 dark:to-slate-900">
    <div className="mb-3 flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
      <Sparkles size={16} />
      <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Top 10 Agenti</span>
    </div>
    <div className="space-y-1">
      <div className="grid grid-cols-12 gap-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">
        <div className="col-span-1">#</div>
        <div className="col-span-7">Agent</div>
        <div className="col-span-4 text-right">Bonus RON</div>
      </div>
      {promoData.top_agents.slice(0, 10).map((agent, index) => (
        <div
          key={agent.agent_name}
          className={`grid grid-cols-12 gap-1 rounded-xl p-2 text-xs ${index % 2 === 0 ? 'bg-indigo-50/50 dark:bg-indigo-900/10' : ''}`}
        >
          <div className="col-span-1 flex items-center font-bold text-slate-400">{index + 1}</div>
          <div className="col-span-7 truncate font-semibold">{agent.agent_name}</div>
          <div className="col-span-4 text-right font-black text-indigo-600">{formatCurrency(agent.qty)}</div>
        </div>
      ))}
    </div>
  </div>
)}
```

Inlocuieste cu:

```tsx
{/* Top Agenti — card separat, sortabil, scroll */}
{promoData && promoData.top_agents.length > 0 && (
  <div className="glass rounded-4xl border border-indigo-100 bg-linear-to-br from-indigo-50 via-white to-white p-4 dark:border-indigo-900/30 dark:from-indigo-950/20 dark:via-slate-900 dark:to-slate-900">
    <div className="mb-3 flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
      <Sparkles size={16} />
      <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Top Agenti</span>
    </div>
    <SortableTable
      rows={promoData.top_agents as unknown as Record<string, unknown>[]}
      defaultSortKey={'val_incentive' as never}
      columns={[
        {
          key: 'rank',
          label: '#',
          sortable: false,
          render: (_row, index) => (
            <span className="font-bold text-slate-400">{index + 1}</span>
          ),
        },
        {
          key: 'agent_name' as never,
          label: 'Agent',
          render: (row) => (
            <span className="truncate font-semibold" title={String((row as unknown as IncentiveTopAgent).agent_name)}>
              {String((row as unknown as IncentiveTopAgent).agent_name)}
            </span>
          ),
        },
        {
          key: 'achievement' as never,
          label: '%Prev.',
          align: 'right',
          render: (row) => {
            const ach = (row as unknown as IncentiveTopAgent).achievement;
            return <span className={achievementColor(ach)}>{achievementLabel(ach)}</span>;
          },
        },
        {
          key: 'qty_sold' as never,
          label: 'Cant.',
          align: 'right',
          render: (row) => (
            <span className="text-slate-500">{formatInt((row as unknown as IncentiveTopAgent).qty_sold)}</span>
          ),
        },
        {
          key: 'val_incentive' as never,
          label: 'Val Inc.',
          align: 'right',
          render: (row) => {
            const val = (row as unknown as IncentiveTopAgent).val_incentive;
            return (
              <span className={val > 0 ? 'font-black text-indigo-600' : 'text-slate-400'}>
                {val > 0 ? formatCurrency(val) : '0 RON'}
              </span>
            );
          },
        },
      ]}
    />
  </div>
)}
```

- [ ] **Step 3: Verifica typecheck**

```bash
npm run typecheck 2>&1 | head -20
```

Output asteptat: fara erori.

---

## Task 6: Frontend — card Top Magazine

**Files:**
- Modify: `src/components/Campaigns.tsx` — inlocuieste cardul "Top Magazine Incentive"

- [ ] **Step 1: Helper badge firma**

Adauga langa `achievementColor`:

```typescript
function FirmaBadge({ firma }: { firma: string }) {
  const lower = firma.toLowerCase();
  const color = lower.includes('mobicell') ? '#3b82f6'
              : lower.includes('mobiup')   ? '#ef4444'
              : '#9ca3af';
  return (
    <span
      title={firma}
      style={{ background: color }}
      className="mr-1 inline-flex h-[14px] w-[14px] flex-shrink-0 items-center justify-center rounded-[3px] text-[8px] font-black text-white"
    >
      M
    </span>
  );
}
```

- [ ] **Step 2: Inlocuieste cardul "Top Magazine Incentive" din JSX**

Gaseste blocul:

```tsx
{/* Top Magazine Incentive — card separat, doar fara promotie activa */}
{promoData && !promoData.has_active_promotion && promoData.top_stores.length > 0 && (
  <div className="glass rounded-4xl border border-indigo-100 ...">
    ...
    {promoData.top_stores.slice(0, 10).map(...)}
    ...
  </div>
)}
```

Inlocuieste cu:

```tsx
{/* Top Magazine Incentive — card separat, sortabil, scroll, doar fara promotie activa */}
{promoData && !promoData.has_active_promotion && promoData.top_stores.length > 0 && (
  <div className="glass rounded-4xl border border-indigo-100 bg-linear-to-br from-indigo-50 via-white to-white p-4 dark:border-indigo-900/30 dark:from-indigo-950/20 dark:via-slate-900 dark:to-slate-900">
    <div className="mb-3 flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
      <Building2 size={16} />
      <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Top Magazine</span>
    </div>
    <SortableTable
      rows={promoData.top_stores as unknown as Record<string, unknown>[]}
      defaultSortKey={'incentive_value' as never}
      columns={[
        {
          key: 'rank',
          label: '#',
          sortable: false,
          render: (_row, index) => (
            <span className="font-bold text-slate-400">{index + 1}</span>
          ),
        },
        {
          key: 'store_name' as never,
          label: 'Magazin',
          render: (row) => {
            const store = row as unknown as PromoTopStore;
            const displayName = store.store_name.includes(' - ')
              ? store.store_name.split(' - ').slice(1).join(' - ')
              : store.store_name;
            return (
              <span className="flex items-center">
                <FirmaBadge firma={store.firma} />
                <span
                  className="max-w-[90px] truncate font-semibold"
                  title={store.store_name}
                >
                  {displayName}
                </span>
              </span>
            );
          },
        },
        {
          key: 'achievement' as never,
          label: '%Prev.',
          align: 'right',
          render: (row) => {
            const ach = (row as unknown as PromoTopStore).achievement;
            return <span className={achievementColor(ach)}>{achievementLabel(ach)}</span>;
          },
        },
        {
          key: 'qty' as never,
          label: 'Cant.',
          align: 'right',
          render: (row) => (
            <span className="text-slate-500">{formatInt((row as unknown as PromoTopStore).qty)}</span>
          ),
        },
        {
          key: 'incentive_value' as never,
          label: 'Val Inc.',
          align: 'right',
          render: (row) => {
            const val = (row as unknown as PromoTopStore).incentive_value;
            return (
              <span className={val > 0 ? 'font-black text-indigo-600' : 'text-slate-400'}>
                {val > 0 ? formatCurrency(val) : '—'}
              </span>
            );
          },
        },
      ]}
    />
  </div>
)}
```

- [ ] **Step 3: Verifica typecheck complet**

```bash
cd /opt/Mobiup/unihub && npm run typecheck 2>&1
```

Output asteptat: `Found 0 errors.`

- [ ] **Step 4: Build**

```bash
npm run build 2>&1 | tail -10
```

Output asteptat: `✓ built in X.XXs`

- [ ] **Step 5: Commit**

```bash
git add src/components/Campaigns.tsx src/api/types.ts
git commit -m "feat: SortableTable + Top Agenti/Magazine cu coloane %Prev/Cant/ValInc, badge firma, scroll"
```

---

## Task 7: Deploy si verificare finala

- [ ] **Step 1: Ruleaza toate testele backend**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Output asteptat: toate PASSED (minim 26 + 4 noi = 30).

- [ ] **Step 2: Deploy**

```bash
cd /opt/Mobiup/unihub
sudo systemctl restart unihub-backend
```

Verifica ca serviciul a pornit:
```bash
sudo systemctl status unihub-backend | head -5
```

Output asteptat: `Active: active (running)`

- [ ] **Step 3: Smoke test API**

```bash
curl -s "http://localhost:8000/api/campaigns/promotions-incentives?start_date=2026-04-01&end_date=2026-04-30" \
  -H "Authorization: Bearer $(cd /opt/Mobiup/unihub/backend && source venv/bin/activate && python3 -c 'from services.auth_service import create_access_token; print(create_access_token(1,"admin","admin"))')" \
  | python3 -m json.tool | grep -E "agent_name|qty_sold|val_incentive|achievement|firma" | head -20
```

Output asteptat: JSON cu campurile `qty_sold`, `val_incentive`, `achievement` la agenti si `firma` la magazine.

- [ ] **Step 4: Commit final**

```bash
git add -A
git commit -m "deploy: incentive cards redesign — coloane extinse, sortare, scroll, badge firma"
```

---

## Criterii de acceptanta

- [ ] Toti agentii apar (nu doar 10)
- [ ] Toate magazinele apar (nu doar 10)
- [ ] Cardurile au inaltime fixa si scroll intern
- [ ] Click pe header coloana sorteaza ASC/DESC cu toggle (sageata ▲/▼)
- [ ] `%Prev.` verde ≥99% / portocaliu 89–99% / rosu <89% / dash daca fara target
- [ ] Badge M rosu (Mobiup) / M albastru (Mobicell) la fiecare magazin
- [ ] Agentii cu bonus 0 sunt inclusi si vizibili cu "0 RON"
- [ ] Typecheck curat, build passing, 30+ teste backend PASSED
