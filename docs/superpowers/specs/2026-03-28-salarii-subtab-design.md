# Salarii Subtab — Agenti Tab Integration

## 1. Concept & Vision

Adaugăm un subtab nou "Salarii" în tabul Agenti care expune datele din `salarii_simplu.db`. Subtab-ul oferă o vedere de ansamblu asupra cheltuielilor cu salariile, evoluția lunară, și permite explorarea detaliată a salariului per agent printr-un drawer panel. Designul urmează același glass-card stil deja utilizat în aplicație.

## 2. Design Language

- **Aesthetic:** Glass-card, consistent cu restul aplicației (Tailwind `glass-card` class)
- **Color palette:**
  - Mobicell: `indigo-500`
  - Mobiup: `emerald-500`
  - Total: `slate-400`
  - Background card: `bg-white/10` backdrop-blur
- **Typography:** System fonts, weight 400/600/700
- **Spacing:** Standard 4-unit grid (16px base)
- **Motion:** Drawer slide-in 300ms ease-out; chart entrance fade 200ms

## 3. Layout & Structure

### Tab routing
- `Agents.tsx` primește un subtab suplimentar: `const [activeTab, setActiveTab] = useState<'active' | 'movement' | 'inactive' | 'all' | 'salarii'>('active')`
- Tab buttons devin 5, "Salarii" apare ultimul
- Când `activeTab === 'salarii'`, se renderează `<SalariiSubtab />`
- Când se revine pe alt subtab, drawer-ul se închide

### SalariiSubtab layout (top → bottom)
```
┌──────────────────────────────────────────────┐
│ Stat cards row (4 cards, responsive grid)     │
│ Total | Mobicell | Mobiup | Luni active      │
├──────────────────────────────────────────────┤
│ Area chart (full width, 240px înălțime)       │
│ 3 linii: Total, Mobicell, Mobiup            │
├──────────────────────────────────────────────┤
│ Search + Filter bar                           │
│ [🔍 Search input] [Companie ▼] [Luna ▼]      │
├──────────────────────────────────────────────┤
│ Agent list (scrollable, fixed header)         │
│ Nume | Companie | Nr Luni | Total | Medie   │
└──────────────────────────────────────────────┘
```

### SalaryDrawer
- Slide din dreapta, lățime 420px
- Overlay întunecat pe restul paginii
- Click outside închide drawer-ul
- Buton X în colțul sus-dreapta
- Conținut: header (nume, CNP), stat row, bar chart lunar, tabel detalii

## 4. Features & Interactions

### Overview stat cards
- **Total:** suma tuturor salariilor din DB
- **Mobicell:** suma salariilor Mobicell
- **Mobiup:** suma salariilor Mobiup
- **Luni active:** perioada acoperită (e.g. "ian-2025 → feb-2026")

### Area chart
- 3 linii: Total (slate), Mobicell (indigo), Mobiup (emerald)
- X-axis: luni (YYYY-MM format)
- Y-axis: sumă salarii (RON)
- Tooltip arată toate cele 3 valori la hover
- Empty state: mesaj dacă nu sunt date

### Search + Filter bar
- **Search:** input cu debounce 300ms, caută în `full_name`
- **Filtru Companie:** dropdown — "Toate", "Mobicell", "Mobiup"
- **Filtru Luna:** dropdown cu lunile disponibile din DB
- Reset filters la golire search

### Agent list
- Sortare default: `total_salary DESC`
- Colțuni: Nume Agent | Companie | Nr Luni | Total | Media
- Click pe rând → deschide `SalaryDrawer` pentru respectivul agent
- Paginare: next/prev buttons, 50 per page

### SalaryDrawer — per agent
- **Header:** nume complet, CNP (parțial mascat: `19**********`), companie, ultimul magazin
- **Stat row:** Total plătit | Luni active | Media lunară
- **BarChart lunar:** bare verticale, câte una per lună în care a avut salariu
- **Tabel detalii:** luna | companie | salariu (ultimele 12 luni, cele mai recente)

### Error states
- Dacă API-ul nu răspunde: mesaj "Nu s-au putut încărca datele" cu buton Retry
- Empty list: "Nu s-au găsit agenți"

## 5. Component Inventory

### SalariiSubtab
- Fetch overview + agents list on mount
- Manage filter state (search q, company, month)
- Pass data down to children

### SalaryDrawer
- Receives `cnp` and `fullName` as props
- Open/close managed via `isOpen` prop + `onClose` callback
- Fetches agent history on open; shows loading skeleton (reuse existing `LoadingSkeleton` pattern) while fetching
- `z-50` fixed overlay + `translate-x` animation

### StatCard
- Props: `label`, `value`, `color` (optional), `icon`
- Reuse the same card-building pattern already used in `Agents.tsx` zone A (StatCard component inline — do not create a separate file)

### SalaryAreaChart
- Props: `data: {month, total, mobicell, mobiup}[]`
- Uses recharts `<AreaChart>`

### SalaryAgentBarChart
- Props: `data: {month, total_salary}[]`
- Uses recharts `<BarChart>`

### AgentList
- Props: `agents: SalaryAgentSummary[]`, `onSelect: (cnp, fullName) => void`
- Own pagination state; rendered inline in `SalariiSubtab` (not a separate file)

## 6. Technical Approach

### Backend — schema change

**File:** `backend/db/schema_v2.sql`

```sql
CREATE TABLE IF NOT EXISTS salary_records (
    id SERIAL PRIMARY KEY,
    year SMALLINT NOT NULL CHECK (year BETWEEN 2020 AND 2100),
    month SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    full_name TEXT NOT NULL,
    cnp TEXT,
    total_salary NUMERIC(12, 2) NOT NULL DEFAULT 0,
    company_name TEXT NOT NULL CHECK (company_name IN ('Mobicell', 'Mobiup')),
    site_code TEXT,
    locatie TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (year, month, cnp, full_name, company_name)
);

CREATE INDEX IF NOT EXISTS idx_salary_records_year_month ON salary_records (year, month);
CREATE INDEX IF NOT EXISTS idx_salary_records_company ON salary_records (company_name);
CREATE INDEX IF NOT EXISTS idx_salary_records_site_code ON salary_records (site_code);
CREATE INDEX IF NOT EXISTS idx_salary_records_cnp ON salary_records (cnp) WHERE cnp IS NOT NULL;
```

### Backend — API

**Files:**
- `backend/scripts/import_salarii.py` — importă din SQLite în PostgreSQL
- `backend/routers/salarii.py` — 5 endpoints

| Method | Path | Response |
|--------|------|---------|
| GET | `/salarii/overview` | `{total: number, by_company: [{name:string,total:number}], record_count: number, agent_count: number, months_span: [number,number]}` |
| GET | `/salarii/evolution` | `[{month:string,total:number,mobicell:number,mobiup:number}]` — serie lunară |
| GET | `/salarii/agents/summary` | `{items: [{full_name,cnp,company_name,month_count,total_salary,avg_salary}], total: number}` — paginated, `?q=&company_name=&year=&month=&limit=&offset=` |
| GET | `/salarii/agents/history/{cnp}` | `{records:[{year,month,company_name,total_salary,site_code,locatie}],total:number,avg:number,month_count:number}` |
| GET | `/salarii/records` | `[{id,year,month,full_name,cnp,total_salary,company_name,site_code,locatie}]` — detail records; used internally for drill-down if needed |

### Frontend — files

| File | Purpose |
|------|---------|
| `src/api/salarii.ts` | API hooks: `useSalariiOverview`, `useSalaryEvolution`, `useSalaryAgents`, `useSalaryAgentHistory` |
| `src/components/SalariiSubtab.tsx` | Main container |
| `src/components/SalaryDrawer.tsx` | Drawer panel |
| `src/components/SalaryAreaChart.tsx` | Evolution area chart |
| `src/components/SalaryAgentBarChart.tsx` | Per-agent bar chart |
| `src/components/Agents.tsx` | Adaugă subtab + routing |

### Frontend — API hooks shape

```typescript
// useSalariiOverview
{ total: number; by_company: {name: string; total: number}[];
  record_count: number; agent_count: number; months_span: [number,number] }

// useSalaryEvolution
[{ month: string; total: number; mobicell: number; mobiup: number }]

// useSalaryAgents(params)
// params: { q?: string; company_name?: string; year?: number; month?: number; limit?: number; offset?: number }
// Returns: { items: SalaryAgentSummary[]; total: number }
type SalaryAgentSummary = {
  full_name: string; cnp: string; company_name: string;
  month_count: number; total_salary: number; avg_salary: number
}

// useSalaryAgentHistory(cnp)
// Returns: { records: [{year,month,company_name,total_salary,site_code,locatie}]; total: number; avg: number; month_count: number }
```

## 7. File changes summary

| File | Action |
|------|--------|
| `backend/db/schema_v2.sql` | Append `salary_records` table + indexes |
| `backend/scripts/import_salarii.py` | Create — SQLite → PostgreSQL import |
| `backend/routers/salarii.py` | Create — REST endpoints |
| `backend/routers/__init__.py` | Add `salarii` to `__all__` tuple |
| `backend/models.py` | Add Pydantic models |
| `backend/main.py` | Add `salarii` to router import + register |
| `src/api/salarii.ts` | Create — API hooks |
| `src/components/SalariiSubtab.tsx` | Create — main subtab component |
| `src/components/SalaryDrawer.tsx` | Create — drawer panel |
| `src/components/SalaryAreaChart.tsx` | Create — evolution chart |
| `src/components/SalaryAgentBarChart.tsx` | Create — per-agent bar chart |
| `src/components/Agents.tsx` | Modify — add `salarii` subtab |
