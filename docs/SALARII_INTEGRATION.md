# Integrare Salarii — Documentație Detaliată

## 1. Ce a cerut utilizatorul

Utilizatorul a furnizat o bază de date SQLite cu salarii:
- **Fișier**: `C:\Users\andre\Desktop\Workspace\unihub\salarii_simplu.db`
- **Tabel**: `salary_records` (3005 rows)
- **Coloane**: `id`, `year`, `month`, `full_name`, `cnp`, `total_salary`, `company_name`, `site_code`, `locatie`

Cerințe:
1. Integrare în baza de date PostgreSQL existentă a aplicației UniHub
2. Adăugarea unui subtab **"Salarii"** în tabul existent **"Agenti"** (alături de Activi, Miscari, Inactiv/Risc, Toti)
3. Subtabul Salarii conține:
   - Carduri overview (total + pe companie)
   - Grafic area cu evoluția lunară (3 linii: Total, Mobicell, Mobiup)
   - Listă de agenți cu search + filtre (companie, lună)
   - **Drawer panel** (slide din dreapta) care se deschide la click pe un agent, arătând istoricul salariilor acelui agent (bar chart + tabel lunar)

---

## 2. Arhitectura / Planul ales

### 2.1 Schema PostgreSQL

S-a adăugat în `backend/db/schema_v2.sql` tabelul `salary_records`:

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

### 2.2 Import SQLite → PostgreSQL

Script `backend/scripts/import_salarii.py`:
- Conectează la `salarii_simplu.db` via `sqlite3`
- Conectează la PostgreSQL via `asyncpg`
- Inserează cu `ON CONFLICT DO UPDATE` (nu șterge datele existente)
- **Important**: `sqlite3.Row` folosește acces prin paranteze `row["key"]`, NU `row.get("key")`

### 2.3 Backend API — 5 endpointuri

Fișier: `backend/routers/salarii.py`

| Endpoint | Metodă | Descriere |
|---|---|---|
| `/salarii/overview` | GET | Total salarii, total per companie, număr agenți, perioadă |
| `/salarii/evolution` | GET | Date lunare agregate (total + per companie) |
| `/salarii/agents/summary` | GET | Listă agenți paginată cu search + filtre (company, year, month) |
| `/salarii/agents/history/{cnp}` | GET | Istoric salarii pentru un agent (bar chart + tabel) |
| `/salarii/records` | GET | Toate înregistrările ( folosit pentru debugging) |

### 2.4 Frontend — Componente noi

| Fișier | Responsabilitate |
|---|---|
| `src/api/salarii.ts` | Hook-uri API (axios calls) |
| `src/components/SalaryAreaChart.tsx` | AreaChart (3 linii: Total/Mobicell/Mobiup) |
| `src/components/SalaryAgentBarChart.tsx` | BarChart per agent, colorat pe companie |
| `src/components/SalaryDrawer.tsx` | Drawer panel slide-din-dreapta |
| `src/components/SalariiSubtab.tsx` | Componenta principală a subtabului |

### 2.5 Integrare în Agents.tsx

Modificări în `src/components/Agents.tsx`:

1. **Import nou** (linia 15):
   ```tsx
   import { SalariiSubtab } from './SalariiSubtab';
   ```

2. **State extins** (linia 235):
   ```tsx
   const [activeTab, setActiveTab] = useState<'active' | 'movement' | 'inactive' | 'all' | 'salarii'>('active');
   ```

3. **Randare Salarii** (liniile 390–396) — BEFORE `selectedAgent` check:
   ```tsx
   if (activeTab === 'salarii') {
     return (
       <div className="p-3 pb-24 pt-2">
         <SalariiSubtab />
       </div>
     );
   }
   ```

4. **Buton tab Salarii** (linia 646):
   ```tsx
   { key: 'salarii' as const, label: 'Salarii' },
   ```

---

## 3. Ce s-a implementat efectiv

### 3.1 Backend

**`backend/db/schema_v2.sql`** — adăugat tabelul `salary_records` + 4 indici

**`backend/scripts/import_salarii.py`** — creat, rulează cu:
```bash
cd backend
python scripts/import_salarii.py
```

**`backend/routers/salarii.py`** — creat cu toate 5 endpointurile

**`backend/models.py`** — adăugate la final:
- `SalaryRecordResponse`
- `SalaryAgentSummary`
- `SalaryAgentHistoryRecord`
- `SalaryAgentHistoryResponse`
- `SalariiOverviewResponse`
- `SalaryEvolutionPoint`
- `SalaryAgentsSummaryResponse`

**`backend/routers/__init__.py`** — adăugat `salarii` la import și `__all__`

**`backend/main.py`** — adăugat `salarii.router` la include_router

### 3.2 Frontend

**`src/api/salarii.ts`** — creat cu funcțiile:
- `fetchSalariiOverview()`
- `fetchSalaryEvolution()`
- `fetchSalaryAgents(params)`
- `fetchSalaryAgentHistory(cnp)`
- `fetchSalaryRecords(params)`

**`src/components/SalaryAreaChart.tsx`** — creat, folosește recharts `<AreaChart>` cu gradient fills

**`src/components/SalaryAgentBarChart.tsx`** — creat, folosește recharts `<BarChart>` cu celule colorate per companie

**`src/components/SalaryDrawer.tsx`** — creat:
- Overlay `fixed inset-0 z-50` cu `bg-black/30 backdrop-blur-sm`
- Panel `max-w-md` cu animație `slideInRight 300ms`
- Fetch agent history când se deschide (`useEffect` pe `isOpen` + `cnp`)
- Afișează: CNP mascat, companie colorată, 3 carduri statistice, BarChart, tabel lunar
- Loading spinner, error state cu Retry

**`src/components/SalariiSubtab.tsx`** — creat:
- 4 carduri statice (Total, Mobicell, Mobiup, Perioada)
- `<SalaryAreaChart>` sub carduri
- Search input + dropdown Companie + dropdown Lună + buton Resetează
- Tabel cu coloane: Nume, Companie, Nr Luni, Total — randuri clickabile
- Paginare (50 pe pagină, Inainte/Inapoi)
- `<SalaryDrawer>` când un agent e selectat

**`src/components/Agents.tsx`** — modificat cu cele 4 editări de mai sus

---

## 4. Erori întâmpinate și fix-uri

### Eroare 1: `sqlite3.Row` nu are metoda `.get()`
- **Problema**: codul folosea inițial `row.get("key")` pe `sqlite3.Row`
- **Fix**: `sqlite3.Row` suportă doar acces prin bracket `row["key"]`
- **Fișier**: `backend/scripts/import_salarii.py`

### Eroare 2: TypeScript — `React` namespace not found în `SalaryDrawer.tsx`
- **Problema**: foloseam `useEffect` din 'react' dar nu aveam `import React`
- **Fix**: adăugat `import React` la linia 1 din `SalaryDrawer.tsx`

### Eroare 3: Vite server returna răspunsuri goale după restart
- **Problema**: procesul Vite rămăsese blocat în memorie
- **Fix**: ucis toate procesele asociate (PID-uri 3092, 2384, 41640, 38548, 11640) și repornit backend + vite

---

## 5. Verificări făcute

```bash
# TypeScript compilează fără erori
npx tsc --noEmit

# Build reușit
npm run build

# Backend API funcționează
curl http://localhost:8000/salarii/overview
# → {"total":8845683.51,"by_company":[{"name":"Mobiup","total":4587823.28},{"name":"Mobicell","total":4257860.23}],"record_count":3005,"agent_count":334,"months_span":[2025,1,2026,12]}

# Bundle-ul conține codul SalariiSubtab
grep "SalariiSubtab" dist/assets/Agents-Cy3-iNzU.js
# → găsit
```

---

## 6. Fluxul de rulare (dacă e nevoie de repornire)

```bash
# Terminal 1 — Backend
cd C:\Users\andre\Desktop\Workspace\unihub\backend
python -m uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd C:\Users\andre\Desktop\Workspace\unihub
npm run dev
```

---

## 7. Posibile probleme de debugging

### Butonul "Salarii" nu apare în browser
**Cauză**: cache-ul browserului servește vechea versiune JavaScript

**Soluții**:
1. `Ctrl+Shift+R` în Chrome (hard refresh cu bypass cache)
2. Deschide `http://localhost:3000` într-un tab nou **incognito/privat**
3. Verifică în DevTools → Network că `Agents-*.js` se încarcă (și nu e `304 Not Modified` din cache)

### Salarii data nu se încarcă
1. Verifică că backend-ul rulează: `curl http://localhost:8000/salarii/overview`
2. Verifică că tabelul are date în PostgreSQL:
   ```bash
   psql $DATABASE_URL -c "SELECT COUNT(*) FROM salary_records;"
   ```

### Vite returnează pagină goală
1. Verifică ce procese rulează pe port 3000: `netstat -ano | findstr :3000`
2. Oprește procesul și restart: `npm run dev`

---

## 8. Structura finală a fișierelor modificate/crea

```
backend/
  db/schema_v2.sql              [MODIFICAT — adăugat salary_records]
  scripts/import_salarii.py     [CREAT]
  routers/salarii.py           [CREAT]
  models.py                     [MODIFICAT — adăugat Pydantic models]
  routers/__init__.py           [MODIFICAT — adăugat salarii]
  main.py                       [MODIFICAT — adăugat salarii router]

src/
  api/salarii.ts                [CREAT]
  components/SalaryAreaChart.tsx [CREAT]
  components/SalaryAgentBarChart.tsx [CREAT]
  components/SalaryDrawer.tsx   [CREAT]
  components/SalariiSubtab.tsx  [CREAT]
  components/Agents.tsx        [MODIFICAT — 4 editări]
```
