# Management Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adaugă tab-ul `Management` cu patru sub-module (Echipă/ASM, Magazine/CRM, Tasks, HR) vizibil exclusiv pentru rolurile `admin` și `management`.

**Architecture:** Tab nou în navigarea existentă, cu sub-tab-uri interne identice cu pattern-ul `Agents → Salarii`. Backend: 3 routere FastAPI noi cu prefixe `/api/tasks`, `/api/hr`, `/api/crm`, 4 tabele noi în `schema_v2.sql` aplicate automat la restart. ASM performance combină PostgreSQL (vânzări) + SQLite visits.db (vizite) server-side via `run_in_executor`. Frontend: `Management.tsx` ca shell cu 4 sub-tab-uri, patru sub-componente, trei module API.

**Tech Stack:** FastAPI + asyncpg (backend), React 19 + TypeScript + Tailwind (frontend), PostgreSQL 18 (date HR/Tasks/CRM), SQLite via `run_in_executor` (vizite pentru CRM scoring)

---

## File Structure

### Fișiere noi
| Fișier | Responsabilitate |
|--------|-----------------|
| `backend/routers/tasks.py` | CRUD task-uri (`/api/tasks`) |
| `backend/routers/hr.py` | Concedii, pontaj, perf agenți + ASM performance (`/api/hr`) |
| `backend/routers/crm.py` | Scoring magazine, alerte (`/api/crm`) |
| `src/api/tasks.ts` | Client HTTP pentru `/api/tasks` |
| `src/api/hr.ts` | Client HTTP pentru `/api/hr` (incl. ASM performance) |
| `src/api/crm.ts` | Client HTTP pentru `/api/crm` |
| `src/components/Management.tsx` | Shell tab Management + 4 sub-tab-uri |
| `src/components/ASMSubtab.tsx` | UI performanță ASM (vizite + vânzări combinate) |
| `src/components/TasksSubtab.tsx` | UI task-uri |
| `src/components/HRSubtab.tsx` | UI concedii + performanță agenți |
| `src/components/CRMSubtab.tsx` | UI scoruri + alerte magazine |
| `backend/tests/test_tasks.py` | Teste tasks |
| `backend/tests/test_hr.py` | Teste HR (incl. ASM performance) |
| `backend/tests/test_crm.py` | Teste CRM |

### Fișiere modificate
| Fișier | Modificare |
|--------|-----------|
| `backend/db/schema_v2.sql` | Adaugă 4 tabele: `tasks`, `leave_requests`, `attendance_records`, `store_scores` |
| `backend/main.py` | Importă și înregistrează cele 3 routere noi |
| `src/lib/roles.ts` | Adaugă `'management'` ca `TabId`, restricționează la `admin` și `management` |
| `src/App.tsx` | Adaugă tipul `'management'` în `ActiveTab`, randează `<Management />` |
| `src/components/MainLayout.tsx` | Adaugă tab-ul Management în `ALL_TABS` |

---

## Task 1: Schema SQL — 4 tabele noi

**Files:**
- Modify: `backend/db/schema_v2.sql`

- [ ] **Step 1: Adaugă cele 4 tabele la sfârșitul `schema_v2.sql`**

Deschide `backend/db/schema_v2.sql` și adaugă la final:

```sql
-- =====================================================================
-- MANAGEMENT: Tasks
-- =====================================================================
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    assignee TEXT,
    site_code TEXT,
    deadline DATE,
    status TEXT NOT NULL DEFAULT 'deschis',
    source TEXT NOT NULL DEFAULT 'manual',
    source_meta JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- =====================================================================
-- MANAGEMENT: HR — Concedii
-- =====================================================================
CREATE TABLE IF NOT EXISTS leave_requests (
    id SERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    leave_type TEXT NOT NULL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- =====================================================================
-- MANAGEMENT: HR — Pontaj
-- =====================================================================
CREATE TABLE IF NOT EXISTS attendance_records (
    id SERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    record_date DATE NOT NULL,
    status TEXT NOT NULL,
    notes TEXT,
    UNIQUE(agent_name, record_date)
);

-- =====================================================================
-- MANAGEMENT: CRM — Scoruri magazine
-- =====================================================================
CREATE TABLE IF NOT EXISTS store_scores (
    id SERIAL PRIMARY KEY,
    site_code TEXT NOT NULL,
    score_month TEXT NOT NULL,
    score INTEGER NOT NULL,
    breakdown JSONB,
    calculated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(site_code, score_month)
);
```

- [ ] **Step 2: Verifică că schema se aplică la restart**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
python3 -c "
import asyncio
from db.connection import ensure_schema_current, init_db_pool, close_db_pool
async def run():
    await init_db_pool()
    await ensure_schema_current()
    await close_db_pool()
asyncio.run(run())
"
```

Rezultat așteptat: nicio eroare, fără output sau mesaj de confirmare schema applied.

- [ ] **Step 3: Verifică tabelele au fost create**

```bash
psql -h localhost -U unihub -d unihub -c "\dt tasks; \dt leave_requests; \dt attendance_records; \dt store_scores"
```

Rezultat așteptat: 4 tabele listate.

- [ ] **Step 4: Commit**

```bash
cd /opt/Mobiup/unihub
git add backend/db/schema_v2.sql
git commit -m "feat: add tasks/hr/crm tables to schema_v2"
```

---

## Task 2: Router Tasks — backend

**Files:**
- Create: `backend/routers/tasks.py`
- Create: `backend/tests/test_tasks.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Scrie testele**

Creează `backend/tests/test_tasks.py`:

```python
from __future__ import annotations
import pytest
from db.connection import get_pool


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


async def get_admin_token() -> str:
    from services.auth_service import create_access_token
    return create_access_token(user_id=1, username="admin", role="admin")


@pytest.mark.anyio
async def test_create_and_list_task():
    from routers.tasks import create_task, list_tasks
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Creează task
        task = await create_task(conn, {
            "title": "Test task",
            "assignee": None,
            "site_code": None,
            "deadline": None,
            "status": "deschis",
            "source": "manual",
            "source_meta": None,
        })
        assert task["title"] == "Test task"
        assert task["status"] == "deschis"
        task_id = task["id"]

        # Listare
        tasks = await list_tasks(conn, status=None, assignee=None, site_code=None)
        ids = [t["id"] for t in tasks]
        assert task_id in ids

        # Cleanup
        await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)


@pytest.mark.anyio
async def test_update_task_status():
    from routers.tasks import create_task, update_task
    pool = await get_pool()
    async with pool.acquire() as conn:
        task = await create_task(conn, {
            "title": "Update test",
            "assignee": None,
            "site_code": None,
            "deadline": None,
            "status": "deschis",
            "source": "manual",
            "source_meta": None,
        })
        updated = await update_task(conn, task["id"], {"status": "inchis"})
        assert updated["status"] == "inchis"
        await conn.execute("DELETE FROM tasks WHERE id = $1", task["id"])


@pytest.mark.anyio
async def test_delete_task():
    from routers.tasks import create_task, delete_task
    pool = await get_pool()
    async with pool.acquire() as conn:
        task = await create_task(conn, {
            "title": "Delete test",
            "assignee": None,
            "site_code": None,
            "deadline": None,
            "status": "deschis",
            "source": "manual",
            "source_meta": None,
        })
        result = await delete_task(conn, task["id"])
        assert result is True
```

- [ ] **Step 2: Rulează testele să fie roșii**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
pytest tests/test_tasks.py -v
```

Rezultat așteptat: `ImportError` sau `ModuleNotFoundError` pentru `routers.tasks`.

- [ ] **Step 3: Creează `backend/routers/tasks.py`**

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.connection import get_pool
from dependencies import require_role

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

ALLOWED_ROLES = require_role("admin", "management")


class TaskCreate(BaseModel):
    title: str
    assignee: str | None = None
    site_code: str | None = None
    deadline: str | None = None  # ISO date string YYYY-MM-DD
    status: str = "deschis"
    source: str = "manual"
    source_meta: dict | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    assignee: str | None = None
    site_code: str | None = None
    deadline: str | None = None
    status: str | None = None


async def create_task(conn: Any, data: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO tasks (title, assignee, site_code, deadline, status, source, source_meta)
        VALUES ($1, $2, $3, $4::date, $5, $6, $7::jsonb)
        RETURNING id, title, assignee, site_code, deadline::text, status, source, source_meta, created_at::text, updated_at::text
        """,
        data["title"],
        data.get("assignee"),
        data.get("site_code"),
        data.get("deadline"),
        data.get("status", "deschis"),
        data.get("source", "manual"),
        str(data["source_meta"]) if data.get("source_meta") else None,
    )
    return dict(row)


async def list_tasks(conn: Any, status: str | None, assignee: str | None, site_code: str | None) -> list[dict]:
    clauses = []
    params: list[Any] = []
    idx = 1

    if status:
        clauses.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if assignee:
        clauses.append(f"assignee = ${idx}")
        params.append(assignee)
        idx += 1
    if site_code:
        clauses.append(f"site_code = ${idx}")
        params.append(site_code)
        idx += 1

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await conn.fetch(
        f"""
        SELECT id, title, assignee, site_code, deadline::text, status, source, source_meta,
               created_at::text, updated_at::text
        FROM tasks
        {where}
        ORDER BY created_at DESC
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def update_task(conn: Any, task_id: int, data: dict) -> dict:
    sets = []
    params: list[Any] = []
    idx = 1

    if "title" in data and data["title"] is not None:
        sets.append(f"title = ${idx}")
        params.append(data["title"])
        idx += 1
    if "assignee" in data:
        sets.append(f"assignee = ${idx}")
        params.append(data["assignee"])
        idx += 1
    if "site_code" in data:
        sets.append(f"site_code = ${idx}")
        params.append(data["site_code"])
        idx += 1
    if "deadline" in data:
        sets.append(f"deadline = ${idx}::date")
        params.append(data["deadline"])
        idx += 1
    if "status" in data and data["status"] is not None:
        sets.append(f"status = ${idx}")
        params.append(data["status"])
        idx += 1

    if not sets:
        raise HTTPException(status_code=400, detail="Niciun câmp de actualizat")

    sets.append(f"updated_at = now()")
    params.append(task_id)
    row = await conn.fetchrow(
        f"""
        UPDATE tasks SET {', '.join(sets)}
        WHERE id = ${idx}
        RETURNING id, title, assignee, site_code, deadline::text, status, source, source_meta,
                  created_at::text, updated_at::text
        """,
        *params,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Task negăsit")
    return dict(row)


async def delete_task(conn: Any, task_id: int) -> bool:
    result = await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)
    return result == "DELETE 1"


@router.get("")
async def get_tasks(
    status: str | None = Query(None),
    assignee: str | None = Query(None),
    site_code: str | None = Query(None),
    user: dict = Depends(ALLOWED_ROLES),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await list_tasks(conn, status, assignee, site_code)


@router.post("")
async def post_task(body: TaskCreate, user: dict = Depends(ALLOWED_ROLES)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await create_task(conn, body.model_dump())


@router.patch("/{task_id}")
async def patch_task(task_id: int, body: TaskUpdate, user: dict = Depends(ALLOWED_ROLES)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await update_task(conn, task_id, body.model_dump(exclude_none=True))


@router.delete("/{task_id}")
async def remove_task(task_id: int, user: dict = Depends(ALLOWED_ROLES)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        deleted = await delete_task(conn, task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Task negăsit")
        return {"ok": True}
```

- [ ] **Step 4: Înregistrează router-ul în `main.py`**

În `backend/main.py`, linia de import:
```python
from routers import admin, agents, ai, auth, campaigns, dashboard, filters, imports, salarii, stores, visits_report
```
devine:
```python
from routers import admin, agents, ai, auth, campaigns, dashboard, filters, hr, imports, crm, salarii, stores, tasks, visits_report
```

Și după `app.include_router(visits_report.router)` adaugă:
```python
app.include_router(tasks.router)
app.include_router(hr.router)
app.include_router(crm.router)
```

**Notă:** `hr.py` și `crm.py` nu există încă — creează fișiere stub ca să nu crape importul:

`backend/routers/hr.py`:
```python
from __future__ import annotations
from fastapi import APIRouter
router = APIRouter(prefix="/api/hr", tags=["hr"])
```

`backend/routers/crm.py`:
```python
from __future__ import annotations
from fastapi import APIRouter
router = APIRouter(prefix="/api/crm", tags=["crm"])
```

- [ ] **Step 5: Rulează testele tasks**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
pytest tests/test_tasks.py -v
```

Rezultat așteptat: toate 3 teste `PASSED`.

- [ ] **Step 6: Rulează toate testele să nu fi spart nimic**

```bash
pytest -v
```

Rezultat așteptat: 32+ teste `PASSED`, 0 `FAILED`.

- [ ] **Step 7: Commit**

```bash
cd /opt/Mobiup/unihub
git add backend/routers/tasks.py backend/routers/hr.py backend/routers/crm.py backend/main.py backend/tests/test_tasks.py
git commit -m "feat: add tasks router with CRUD endpoints"
```

---

## Task 3: Frontend — shell Management + TasksSubtab

**Files:**
- Modify: `src/lib/roles.ts`
- Modify: `src/App.tsx`
- Modify: `src/components/MainLayout.tsx`
- Create: `src/api/tasks.ts`
- Create: `src/components/TasksSubtab.tsx`
- Create: `src/components/Management.tsx`

- [ ] **Step 1: Adaugă `'management'` ca TabId în `src/lib/roles.ts`**

```typescript
export type Role = 'admin' | 'asm' | 'management' | 'tl';
export type TabId = 'hub' | 'focus' | 'agents' | 'ai' | 'settings' | 'management';

const ROLE_TABS: Record<Role, TabId[]> = {
  tl: ['hub', 'focus', 'agents', 'ai', 'settings'],
  asm: ['hub', 'focus', 'agents', 'ai', 'settings'],
  management: ['hub', 'focus', 'agents', 'ai', 'settings', 'management'],
  admin: ['hub', 'focus', 'agents', 'ai', 'settings', 'management'],
};

const TAB_LABELS: Record<TabId, string> = {
  hub: 'Hub',
  focus: 'Focus',
  agents: 'Agenti',
  ai: 'AI',
  settings: 'Setări',
  management: 'Management',
};

export function canAccessTab(role: Role, tab: TabId): boolean {
  return ROLE_TABS[role]?.includes(tab) ?? false;
}

export function getRoleAccessLabel(role: Role): string {
  const tabs = ROLE_TABS[role];
  if (role === 'tl' || role === 'asm' || role === 'management') {
    const label = tabs.filter((t) => t !== 'settings').map((t) => TAB_LABELS[t]).join(' · ');
    return label + ' · Setări (doar temă)';
  }
  return tabs.map((t) => TAB_LABELS[t]).join(' · ');
}
```

- [ ] **Step 2: Adaugă tab-ul în `src/components/MainLayout.tsx`**

Găsește blocul `ALL_TABS` (în jurul liniei 39) și adaugă Management:

```typescript
const ALL_TABS = [
  { id: 'hub', icon: LayoutDashboard, label: 'Hub' },
  { id: 'focus', icon: Sparkles, label: 'Focus' },
  { id: 'agents', icon: Users, label: 'Agenti' },
  { id: 'management', icon: Briefcase, label: 'Management' },
  { id: 'ai', icon: Bot, label: 'AI' },
  { id: 'settings', icon: Settings, label: 'Setări' },
];
```

Importă `Briefcase` din `lucide-react` în linia de import existentă.

Actualizează și tipul `setActiveTab` în interfața `MainLayoutProps` (linia ~27):
```typescript
setActiveTab: (tab: 'hub' | 'focus' | 'agents' | 'management' | 'ai' | 'settings') => void;
```

- [ ] **Step 3: Actualizează `src/App.tsx`**

Linia 25 — tipul `ActiveTab`:
```typescript
type ActiveTab = 'hub' | 'focus' | 'agents' | 'management' | 'ai' | 'settings';
```

Importează `Management` (după ce îl creezi):
```typescript
import { Management } from './components/Management';
```

În blocul de randare al tab-urilor (după `activeTab === 'agents'`), adaugă:
```typescript
{activeTab === 'management' && (
  <Management />
)}
```

- [ ] **Step 4: Creează `src/api/tasks.ts`**

```typescript
import axios from 'axios';

const api = axios.create({ baseURL: '/api/tasks' });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('unihub_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export interface Task {
  id: number;
  title: string;
  assignee: string | null;
  site_code: string | null;
  deadline: string | null;
  status: 'deschis' | 'in_lucru' | 'inchis';
  source: string;
  source_meta: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface TaskCreate {
  title: string;
  assignee?: string | null;
  site_code?: string | null;
  deadline?: string | null;
  status?: string;
  source?: string;
  source_meta?: Record<string, unknown> | null;
}

export interface TaskUpdate {
  title?: string;
  assignee?: string | null;
  site_code?: string | null;
  deadline?: string | null;
  status?: string;
}

export async function fetchTasks(params?: { status?: string; assignee?: string; site_code?: string }): Promise<Task[]> {
  const { data } = await api.get('', { params });
  return data;
}

export async function createTask(body: TaskCreate): Promise<Task> {
  const { data } = await api.post('', body);
  return data;
}

export async function updateTask(id: number, body: TaskUpdate): Promise<Task> {
  const { data } = await api.patch(`/${id}`, body);
  return data;
}

export async function deleteTask(id: number): Promise<void> {
  await api.delete(`/${id}`);
}
```

- [ ] **Step 5: Creează `src/components/TasksSubtab.tsx`**

```typescript
import { useEffect, useState } from 'react';
import { Plus, Trash2, RefreshCw } from 'lucide-react';
import { fetchTasks, createTask, updateTask, deleteTask, type Task } from '../api/tasks';

const STATUS_LABELS: Record<string, string> = {
  deschis: 'Deschis',
  in_lucru: 'În lucru',
  inchis: 'Închis',
};

const STATUS_COLORS: Record<string, string> = {
  deschis: 'bg-blue-500/20 text-blue-300',
  in_lucru: 'bg-yellow-500/20 text-yellow-300',
  inchis: 'bg-green-500/20 text-green-300',
};

const STATUS_NEXT: Record<string, string> = {
  deschis: 'in_lucru',
  in_lucru: 'inchis',
  inchis: 'deschis',
};

export function TasksSubtab() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('');
  const [showForm, setShowForm] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newAssignee, setNewAssignee] = useState('');
  const [newSiteCode, setNewSiteCode] = useState('');
  const [newDeadline, setNewDeadline] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const data = await fetchTasks(filter ? { status: filter } : undefined);
      setTasks(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filter]);

  const handleCreate = async () => {
    if (!newTitle.trim()) return;
    await createTask({
      title: newTitle.trim(),
      assignee: newAssignee || null,
      site_code: newSiteCode || null,
      deadline: newDeadline || null,
    });
    setNewTitle('');
    setNewAssignee('');
    setNewSiteCode('');
    setNewDeadline('');
    setShowForm(false);
    await load();
  };

  const handleStatusCycle = async (task: Task) => {
    await updateTask(task.id, { status: STATUS_NEXT[task.status] });
    await load();
  };

  const handleDelete = async (id: number) => {
    await deleteTask(id);
    await load();
  };

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {['', 'deschis', 'in_lucru', 'inchis'].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                filter === s ? 'bg-indigo-600 text-white' : 'bg-white/10 text-white/60 hover:bg-white/20'
              }`}
            >
              {s === '' ? 'Toate' : STATUS_LABELS[s]}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="p-1.5 rounded bg-white/10 hover:bg-white/20">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
          >
            <Plus size={14} /> Task nou
          </button>
        </div>
      </div>

      {/* Form creare */}
      {showForm && (
        <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3">
          <input
            className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/40 focus:outline-none focus:border-indigo-500"
            placeholder="Titlu task *"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
          />
          <div className="grid grid-cols-3 gap-2">
            <input
              className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/40 focus:outline-none focus:border-indigo-500"
              placeholder="Responsabil"
              value={newAssignee}
              onChange={(e) => setNewAssignee(e.target.value)}
            />
            <input
              className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/40 focus:outline-none focus:border-indigo-500"
              placeholder="Cod magazin"
              value={newSiteCode}
              onChange={(e) => setNewSiteCode(e.target.value)}
            />
            <input
              type="date"
              className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
              value={newDeadline}
              onChange={(e) => setNewDeadline(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setShowForm(false)}
              className="px-4 py-2 text-sm text-white/60 hover:text-white"
            >
              Anulează
            </button>
            <button
              onClick={handleCreate}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg font-medium"
            >
              Creează
            </button>
          </div>
        </div>
      )}

      {/* Lista task-uri */}
      <div className="space-y-2">
        {tasks.length === 0 && !loading && (
          <div className="text-center text-white/40 py-8 text-sm">Niciun task{filter ? ` cu status "${STATUS_LABELS[filter]}"` : ''}</div>
        )}
        {tasks.map((task) => (
          <div key={task.id} className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 flex items-center gap-3">
            <button
              onClick={() => handleStatusCycle(task)}
              className={`shrink-0 px-2.5 py-1 rounded-full text-xs font-medium cursor-pointer ${STATUS_COLORS[task.status]}`}
            >
              {STATUS_LABELS[task.status]}
            </button>
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium ${task.status === 'inchis' ? 'line-through text-white/40' : 'text-white'}`}>
                {task.title}
              </p>
              <p className="text-xs text-white/40 mt-0.5">
                {[task.assignee, task.site_code, task.deadline].filter(Boolean).join(' · ') || 'Fără detalii'}
              </p>
            </div>
            <button
              onClick={() => handleDelete(task.id)}
              className="shrink-0 p-1.5 rounded text-white/30 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Creează `src/components/Management.tsx`** (shell cu 4 sub-tab-uri)

```typescript
import { useState } from 'react';
import { ASMSubtab } from './ASMSubtab';
import { CRMSubtab } from './CRMSubtab';
import { TasksSubtab } from './TasksSubtab';
import { HRSubtab } from './HRSubtab';

type ManagementTab = 'asm' | 'crm' | 'tasks' | 'hr';

const TABS: { id: ManagementTab; label: string }[] = [
  { id: 'asm', label: 'Echipă' },
  { id: 'crm', label: 'Magazine' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'hr', label: 'HR' },
];

export function Management() {
  const [activeTab, setActiveTab] = useState<ManagementTab>('asm');

  return (
    <div className="flex flex-col h-full">
      {/* Sub-navigare */}
      <div className="flex gap-1 px-4 pt-4 pb-2 border-b border-white/10">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-indigo-600 text-white'
                : 'text-white/60 hover:text-white hover:bg-white/10'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Conținut */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'asm' && <ASMSubtab />}
        {activeTab === 'crm' && <CRMSubtab />}
        {activeTab === 'tasks' && <TasksSubtab />}
        {activeTab === 'hr' && <HRSubtab />}
      </div>
    </div>
  );
}
```

**Notă:** `ASMSubtab`, `HRSubtab` și `CRMSubtab` nu există încă. Creează stub-uri temporare:

`src/components/ASMSubtab.tsx`:
```typescript
export function ASMSubtab() {
  return <div className="p-8 text-center text-white/40 text-sm">Echipă — în curând</div>;
}
```

`src/components/HRSubtab.tsx`:
```typescript
export function HRSubtab() {
  return <div className="p-8 text-center text-white/40 text-sm">HR — în curând</div>;
}
```

`src/components/CRMSubtab.tsx`:
```typescript
export function CRMSubtab() {
  return <div className="p-8 text-center text-white/40 text-sm">CRM — în curând</div>;
}
```

- [ ] **Step 7: Verifică build TypeScript**

```bash
cd /opt/Mobiup/unihub
npm run typecheck
```

Rezultat așteptat: 0 erori.

- [ ] **Step 8: Build complet**

```bash
npm run build
```

Rezultat așteptat: build reușit, nicio eroare.

- [ ] **Step 9: Commit**

```bash
git add src/lib/roles.ts src/App.tsx src/components/MainLayout.tsx \
        src/api/tasks.ts src/components/TasksSubtab.tsx \
        src/components/Management.tsx src/components/HRSubtab.tsx \
        src/components/CRMSubtab.tsx
git commit -m "feat: add Management tab shell with Tasks sub-tab"
```

---

## Task 4: Router HR — backend

**Files:**
- Modify: `backend/routers/hr.py` (înlocuiește stub-ul)
- Create: `backend/tests/test_hr.py`

- [ ] **Step 1: Scrie testele HR**

Creează `backend/tests/test_hr.py`:

```python
from __future__ import annotations
import pytest
from db.connection import get_pool


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_create_leave_request():
    from routers.hr import create_leave_request
    pool = await get_pool()
    async with pool.acquire() as conn:
        req = await create_leave_request(conn, {
            "agent_name": "Test Agent",
            "start_date": "2026-05-01",
            "end_date": "2026-05-05",
            "leave_type": "odihna",
            "notes": None,
        })
        assert req["agent_name"] == "Test Agent"
        assert req["status"] == "pending"
        await conn.execute("DELETE FROM leave_requests WHERE id = $1", req["id"])


@pytest.mark.anyio
async def test_approve_leave_request():
    from routers.hr import create_leave_request, update_leave_status
    pool = await get_pool()
    async with pool.acquire() as conn:
        req = await create_leave_request(conn, {
            "agent_name": "Test Agent",
            "start_date": "2026-05-10",
            "end_date": "2026-05-12",
            "leave_type": "medical",
            "notes": None,
        })
        updated = await update_leave_status(conn, req["id"], "approved")
        assert updated["status"] == "approved"
        await conn.execute("DELETE FROM leave_requests WHERE id = $1", req["id"])


@pytest.mark.anyio
async def test_list_leave_requests():
    from routers.hr import list_leave_requests
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await list_leave_requests(conn, status=None, agent_name=None)
        assert isinstance(rows, list)


@pytest.mark.anyio
async def test_performance_returns_list():
    from routers.hr import get_agent_performance
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await get_agent_performance(conn, "NonexistentAgent")
        assert isinstance(result, list)
```

- [ ] **Step 2: Rulează testele să fie roșii**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
pytest tests/test_hr.py -v
```

Rezultat așteptat: `ImportError` pentru funcțiile din `routers.hr`.

- [ ] **Step 3: Înlocuiește stub-ul `backend/routers/hr.py` cu implementarea completă**

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.connection import get_pool
from dependencies import require_role

router = APIRouter(prefix="/api/hr", tags=["hr"])

ALLOWED_ROLES = require_role("admin", "management")


class LeaveRequestCreate(BaseModel):
    agent_name: str
    start_date: str   # YYYY-MM-DD
    end_date: str     # YYYY-MM-DD
    leave_type: str   # 'odihna' | 'medical' | 'altul'
    notes: str | None = None


class LeaveStatusUpdate(BaseModel):
    status: str       # 'approved' | 'rejected'


async def create_leave_request(conn: Any, data: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO leave_requests (agent_name, start_date, end_date, leave_type, notes)
        VALUES ($1, $2::date, $3::date, $4, $5)
        RETURNING id, agent_name, start_date::text, end_date::text, leave_type, notes,
                  status, created_at::text, updated_at::text
        """,
        data["agent_name"],
        data["start_date"],
        data["end_date"],
        data["leave_type"],
        data.get("notes"),
    )
    return dict(row)


async def update_leave_status(conn: Any, request_id: int, status: str) -> dict:
    row = await conn.fetchrow(
        """
        UPDATE leave_requests
        SET status = $1, updated_at = now()
        WHERE id = $2
        RETURNING id, agent_name, start_date::text, end_date::text, leave_type, notes,
                  status, created_at::text, updated_at::text
        """,
        status,
        request_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Cerere negăsită")
    return dict(row)


async def list_leave_requests(conn: Any, status: str | None, agent_name: str | None) -> list[dict]:
    clauses = []
    params: list[Any] = []
    idx = 1
    if status:
        clauses.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if agent_name:
        clauses.append(f"agent_name ILIKE ${idx}")
        params.append(f"%{agent_name}%")
        idx += 1
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await conn.fetch(
        f"""
        SELECT id, agent_name, start_date::text, end_date::text, leave_type, notes,
               status, created_at::text, updated_at::text
        FROM leave_requests
        {where}
        ORDER BY created_at DESC
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def get_agent_performance(conn: Any, agent_name: str) -> list[dict]:
    """Agregat lunar per agent: vânzări, % target, salarii — ultimele 12 luni."""
    rows = await conn.fetch(
        """
        SELECT
            ram.import_month,
            ram.total_value,
            ram.transaction_count,
            ram.active_days,
            COALESCE(
                ROUND(
                    ram.total_value::numeric /
                    NULLIF(
                        (SELECT SUM(st.target_value)
                         FROM store_targets st
                         JOIN stores s ON s.site_code = st.site_code
                         WHERE st.import_month = ram.import_month
                           AND s.agent = ram.agent),
                        0
                    ) * 100,
                    1
                ),
                0
            ) AS target_pct
        FROM reporting_agent_month ram
        WHERE ram.agent = $1
          AND ram.import_month >= to_char(now() - interval '12 months', 'YYYY-MM')
        ORDER BY ram.import_month
        """,
        agent_name,
    )
    return [dict(r) for r in rows]


@router.get("/leave-requests")
async def get_leave_requests(
    status: str | None = Query(None),
    agent_name: str | None = Query(None),
    user: dict = Depends(ALLOWED_ROLES),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await list_leave_requests(conn, status, agent_name)


@router.post("/leave-requests")
async def post_leave_request(body: LeaveRequestCreate, user: dict = Depends(ALLOWED_ROLES)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await create_leave_request(conn, body.model_dump())


@router.patch("/leave-requests/{request_id}")
async def patch_leave_request(
    request_id: int,
    body: LeaveStatusUpdate,
    user: dict = Depends(ALLOWED_ROLES),
):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Status invalid. Folosește 'approved' sau 'rejected'.")
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await update_leave_status(conn, request_id, body.status)


@router.get("/performance/{agent_name}")
async def get_performance(agent_name: str, user: dict = Depends(ALLOWED_ROLES)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await get_agent_performance(conn, agent_name)
```

- [ ] **Step 4: Rulează testele HR**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
pytest tests/test_hr.py -v
```

Rezultat așteptat: toate 4 teste `PASSED`.

- [ ] **Step 5: Rulează toate testele**

```bash
pytest -v
```

Rezultat așteptat: 36+ teste `PASSED`, 0 `FAILED`.

- [ ] **Step 6: Commit**

```bash
cd /opt/Mobiup/unihub
git add backend/routers/hr.py backend/tests/test_hr.py
git commit -m "feat: add HR router (leave requests + performance)"
```

---

## Task 5: Frontend HRSubtab

**Files:**
- Modify: `src/components/HRSubtab.tsx` (înlocuiește stub-ul)
- Create: `src/api/hr.ts`

- [ ] **Step 1: Creează `src/api/hr.ts`**

```typescript
import axios from 'axios';

const api = axios.create({ baseURL: '/api/hr' });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('unihub_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export interface LeaveRequest {
  id: number;
  agent_name: string;
  start_date: string;
  end_date: string;
  leave_type: string;
  notes: string | null;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
}

export interface PerformancePoint {
  import_month: string;
  total_value: number;
  transaction_count: number;
  active_days: number;
  target_pct: number;
}

export async function fetchLeaveRequests(params?: { status?: string; agent_name?: string }): Promise<LeaveRequest[]> {
  const { data } = await api.get('/leave-requests', { params });
  return data;
}

export async function createLeaveRequest(body: {
  agent_name: string;
  start_date: string;
  end_date: string;
  leave_type: string;
  notes?: string;
}): Promise<LeaveRequest> {
  const { data } = await api.post('/leave-requests', body);
  return data;
}

export async function updateLeaveStatus(id: number, status: 'approved' | 'rejected'): Promise<LeaveRequest> {
  const { data } = await api.patch(`/leave-requests/${id}`, { status });
  return data;
}

export async function fetchAgentPerformance(agentName: string): Promise<PerformancePoint[]> {
  const { data } = await api.get(`/performance/${encodeURIComponent(agentName)}`);
  return data;
}
```

- [ ] **Step 2: Înlocuiește stub-ul `src/components/HRSubtab.tsx`**

```typescript
import { useEffect, useState } from 'react';
import { RefreshCw, CheckCircle, XCircle, Clock, ChevronDown, ChevronUp } from 'lucide-react';
import {
  fetchLeaveRequests,
  createLeaveRequest,
  updateLeaveStatus,
  fetchAgentPerformance,
  type LeaveRequest,
  type PerformancePoint,
} from '../api/hr';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

const STATUS_ICON = {
  pending: <Clock size={14} className="text-yellow-400" />,
  approved: <CheckCircle size={14} className="text-green-400" />,
  rejected: <XCircle size={14} className="text-red-400" />,
};

const STATUS_LABEL = { pending: 'În așteptare', approved: 'Aprobat', rejected: 'Respins' };
const LEAVE_LABELS: Record<string, string> = { odihna: 'Odihnă', medical: 'Medical', altul: 'Alt motiv' };

export function HRSubtab() {
  const [requests, setRequests] = useState<LeaveRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ agent_name: '', start_date: '', end_date: '', leave_type: 'odihna', notes: '' });
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [perfData, setPerfData] = useState<PerformancePoint[]>([]);
  const [perfLoading, setPerfLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await fetchLeaveRequests(filterStatus ? { status: filterStatus } : undefined);
      setRequests(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filterStatus]);

  const handleCreate = async () => {
    if (!form.agent_name || !form.start_date || !form.end_date) return;
    await createLeaveRequest({ ...form, notes: form.notes || undefined });
    setForm({ agent_name: '', start_date: '', end_date: '', leave_type: 'odihna', notes: '' });
    setShowForm(false);
    await load();
  };

  const handleStatus = async (id: number, status: 'approved' | 'rejected') => {
    await updateLeaveStatus(id, status);
    await load();
  };

  const handleSelectAgent = async (name: string) => {
    if (selectedAgent === name) {
      setSelectedAgent(null);
      return;
    }
    setSelectedAgent(name);
    setPerfLoading(true);
    try {
      const data = await fetchAgentPerformance(name);
      setPerfData(data);
    } finally {
      setPerfLoading(false);
    }
  };

  const formatMonth = (m: string) => {
    const [y, mo] = m.split('-');
    const labels = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Noi', 'Dec'];
    return `${labels[parseInt(mo) - 1]} ${y.slice(2)}`;
  };

  return (
    <div className="p-4 space-y-6">
      {/* Secțiunea Concedii */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white/80 uppercase tracking-wide">Cereri concediu</h3>
          <div className="flex gap-2">
            {['', 'pending', 'approved', 'rejected'].map((s) => (
              <button
                key={s}
                onClick={() => setFilterStatus(s)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                  filterStatus === s ? 'bg-indigo-600 text-white' : 'bg-white/10 text-white/50 hover:bg-white/20'
                }`}
              >
                {s === '' ? 'Toate' : STATUS_LABEL[s as keyof typeof STATUS_LABEL]}
              </button>
            ))}
            <button onClick={load} className="p-1.5 rounded bg-white/10 hover:bg-white/20">
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            </button>
            <button
              onClick={() => setShowForm(!showForm)}
              className="px-3 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
            >
              + Cerere nouă
            </button>
          </div>
        </div>

        {showForm && (
          <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <input
                className="col-span-2 bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/40 focus:outline-none focus:border-indigo-500"
                placeholder="Nume agent *"
                value={form.agent_name}
                onChange={(e) => setForm({ ...form, agent_name: e.target.value })}
              />
              <input type="date" className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
              <input type="date" className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
              <select
                className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                value={form.leave_type}
                onChange={(e) => setForm({ ...form, leave_type: e.target.value })}
              >
                <option value="odihna">Odihnă</option>
                <option value="medical">Medical</option>
                <option value="altul">Alt motiv</option>
              </select>
              <input
                className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/40 focus:outline-none focus:border-indigo-500"
                placeholder="Note (opțional)"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-white/60 hover:text-white">Anulează</button>
              <button onClick={handleCreate} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg font-medium">Salvează</button>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {requests.length === 0 && !loading && (
            <div className="text-center text-white/40 py-6 text-sm">Nicio cerere</div>
          )}
          {requests.map((r) => (
            <div key={r.id} className="bg-white/5 border border-white/10 rounded-xl px-4 py-3">
              <div className="flex items-center gap-3">
                {STATUS_ICON[r.status]}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleSelectAgent(r.agent_name)}
                      className="text-sm font-medium text-white hover:text-indigo-400 transition-colors flex items-center gap-1"
                    >
                      {r.agent_name}
                      {selectedAgent === r.agent_name ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    </button>
                    <span className="text-xs text-white/40">{LEAVE_LABELS[r.leave_type] ?? r.leave_type}</span>
                  </div>
                  <p className="text-xs text-white/50 mt-0.5">{r.start_date} → {r.end_date}{r.notes ? ` · ${r.notes}` : ''}</p>
                </div>
                {r.status === 'pending' && (
                  <div className="flex gap-1.5 shrink-0">
                    <button
                      onClick={() => handleStatus(r.id, 'approved')}
                      className="px-2.5 py-1 rounded text-xs bg-green-500/20 text-green-300 hover:bg-green-500/30 font-medium"
                    >
                      Aprobă
                    </button>
                    <button
                      onClick={() => handleStatus(r.id, 'rejected')}
                      className="px-2.5 py-1 rounded text-xs bg-red-500/20 text-red-300 hover:bg-red-500/30 font-medium"
                    >
                      Respinge
                    </button>
                  </div>
                )}
              </div>

              {/* Grafic performanță expandabil */}
              {selectedAgent === r.agent_name && (
                <div className="mt-3 pt-3 border-t border-white/10">
                  {perfLoading ? (
                    <div className="text-center text-white/40 text-xs py-4">Se încarcă...</div>
                  ) : perfData.length === 0 ? (
                    <div className="text-center text-white/40 text-xs py-4">Date indisponibile</div>
                  ) : (
                    <div className="h-40">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={perfData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                          <defs>
                            <linearGradient id="perfGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                              <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                          <XAxis dataKey="import_month" tickFormatter={formatMonth} tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }} />
                          <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }} />
                          <Tooltip
                            contentStyle={{ background: '#1e1e2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }}
                            labelFormatter={formatMonth}
                            formatter={(v: number) => [`${v}%`, '% Target']}
                          />
                          <Area type="monotone" dataKey="target_pct" stroke="#6366f1" fill="url(#perfGrad)" strokeWidth={2} dot={false} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verifică typecheck**

```bash
cd /opt/Mobiup/unihub
npm run typecheck
```

Rezultat așteptat: 0 erori.

- [ ] **Step 4: Build**

```bash
npm run build
```

Rezultat așteptat: build reușit.

- [ ] **Step 5: Commit**

```bash
git add src/api/hr.ts src/components/HRSubtab.tsx
git commit -m "feat: HR sub-tab with leave requests and performance chart"
```

---

## Task 6: Router CRM — backend

**Files:**
- Modify: `backend/routers/crm.py` (înlocuiește stub-ul)
- Create: `backend/tests/test_crm.py`

- [ ] **Step 1: Scrie testele CRM**

Creează `backend/tests/test_crm.py`:

```python
from __future__ import annotations
import pytest
from db.connection import get_pool


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_calculate_scores_returns_list():
    from routers.crm import calculate_scores_for_month
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Folosim o lună pentru care există date
        scores = await calculate_scores_for_month(conn, "2026-03")
        assert isinstance(scores, list)
        if scores:
            score = scores[0]
            assert "site_code" in score
            assert "score" in score
            assert 0 <= score["score"] <= 100
            assert "breakdown" in score


@pytest.mark.anyio
async def test_get_alerts_returns_list():
    from routers.crm import get_store_alerts
    pool = await get_pool()
    async with pool.acquire() as conn:
        alerts = await get_store_alerts(conn, "2026-03")
        assert isinstance(alerts, list)
        for alert in alerts:
            assert "site_code" in alert
            assert "reasons" in alert
            assert isinstance(alert["reasons"], list)


@pytest.mark.anyio
async def test_upsert_scores():
    from routers.crm import calculate_scores_for_month, upsert_scores
    pool = await get_pool()
    async with pool.acquire() as conn:
        scores = await calculate_scores_for_month(conn, "2026-03")
        if scores:
            await upsert_scores(conn, "2026-03", scores)
            # Verifică că au fost salvate
            rows = await conn.fetch(
                "SELECT site_code, score FROM store_scores WHERE score_month = '2026-03' LIMIT 5"
            )
            assert len(rows) > 0
```

- [ ] **Step 2: Rulează testele să fie roșii**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
pytest tests/test_crm.py -v
```

Rezultat așteptat: `ImportError` pentru funcțiile din `routers.crm`.

- [ ] **Step 3: Înlocuiește stub-ul `backend/routers/crm.py`**

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from db.connection import get_pool
from dependencies import require_role

router = APIRouter(prefix="/api/crm", tags=["crm"])

ALLOWED_ROLES = require_role("admin", "management")


async def calculate_scores_for_month(conn: Any, month: str) -> list[dict]:
    """
    Calculează scorul 0-100 per magazin pentru luna dată.
    Formula:
      - % target atins (max 40 pct)
      - trend față de luna anterioară (max 30 pct)
      - zile active (max 20 pct)
      - vizite (max 10 pct) — 0 dacă nu există date
    """
    y, m = map(int, month.split("-"))
    prev_month = f"{y}-{m - 1:02d}" if m > 1 else f"{y - 1}-12"

    rows = await conn.fetch(
        """
        WITH current AS (
            SELECT
                ram.site_code,
                SUM(ram.total_value) AS total_value,
                SUM(ram.active_days) AS active_days,
                COALESCE(
                    (SELECT SUM(st.target_value)
                     FROM store_targets st
                     WHERE st.site_code = ram.site_code
                       AND st.import_month = $1),
                    0
                ) AS target_value
            FROM reporting_agent_month ram
            WHERE ram.import_month = $1
            GROUP BY ram.site_code
        ),
        prev AS (
            SELECT
                site_code,
                SUM(total_value) AS total_value
            FROM reporting_agent_month
            WHERE import_month = $2
            GROUP BY site_code
        )
        SELECT
            c.site_code,
            c.total_value,
            c.active_days,
            c.target_value,
            COALESCE(p.total_value, 0) AS prev_value
        FROM current c
        LEFT JOIN prev p ON p.site_code = c.site_code
        """,
        month,
        prev_month,
    )

    scores = []
    for row in rows:
        total = float(row["total_value"] or 0)
        target = float(row["target_value"] or 0)
        prev = float(row["prev_value"] or 0)
        active_days = int(row["active_days"] or 0)

        # Componentă 1: % target (max 40)
        target_pct = (total / target * 100) if target > 0 else 0
        c1 = min(target_pct / 100 * 40, 40)

        # Componentă 2: trend față de luna anterioară (max 30)
        if prev > 0:
            trend = (total - prev) / prev * 100
            # +20% trend → 30 pct; -20% trend → 0 pct; liniar între ele
            c2 = max(0.0, min(30.0, (trend + 20) / 40 * 30))
        else:
            c2 = 15.0  # neutral dacă nu există date anterioare

        # Componentă 3: zile active (max 20) — 20 zile = maxim
        c3 = min(active_days / 20 * 20, 20)

        # Componentă 4: vizite — 0 (vizitele sunt în SQLite, ignorat în v1)
        c4 = 0.0

        score = round(c1 + c2 + c3 + c4)
        scores.append({
            "site_code": row["site_code"],
            "score": score,
            "breakdown": {
                "target_pct": round(c1, 1),
                "trend_pct": round(c2, 1),
                "active_days_pct": round(c3, 1),
                "visits_pct": round(c4, 1),
                "target_attainment": round(target_pct, 1),
            },
        })

    return scores


async def upsert_scores(conn: Any, month: str, scores: list[dict]) -> None:
    for s in scores:
        import json
        await conn.execute(
            """
            INSERT INTO store_scores (site_code, score_month, score, breakdown)
            VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (site_code, score_month)
            DO UPDATE SET score = EXCLUDED.score, breakdown = EXCLUDED.breakdown,
                          calculated_at = now()
            """,
            s["site_code"],
            month,
            s["score"],
            json.dumps(s["breakdown"]),
        )


async def get_store_alerts(conn: Any, month: str) -> list[dict]:
    """Magazine cu risc: scor < 40, scădere > 20%, sau fără vizită (vizite ignorat în v1)."""
    y, m_int = map(int, month.split("-"))
    prev_month = f"{y}-{m_int - 1:02d}" if m_int > 1 else f"{y - 1}-12"

    rows = await conn.fetch(
        """
        WITH current AS (
            SELECT site_code, SUM(total_value) AS val
            FROM reporting_agent_month WHERE import_month = $1
            GROUP BY site_code
        ),
        prev AS (
            SELECT site_code, SUM(total_value) AS val
            FROM reporting_agent_month WHERE import_month = $2
            GROUP BY site_code
        ),
        scores AS (
            SELECT site_code, score
            FROM store_scores
            WHERE score_month = $1
        )
        SELECT
            c.site_code,
            COALESCE(s.score, -1) AS score,
            c.val AS current_val,
            COALESCE(p.val, 0) AS prev_val
        FROM current c
        LEFT JOIN prev p ON p.site_code = c.site_code
        LEFT JOIN scores s ON s.site_code = c.site_code
        """,
        month,
        prev_month,
    )

    alerts = []
    for row in rows:
        reasons = []
        score = row["score"]
        current_val = float(row["current_val"] or 0)
        prev_val = float(row["prev_val"] or 0)

        if score >= 0 and score < 40:
            reasons.append(f"Scor scăzut ({score}/100)")

        if prev_val > 0:
            trend = (current_val - prev_val) / prev_val * 100
            if trend < -20:
                reasons.append(f"Scădere {abs(round(trend))}% față de luna anterioară")

        if reasons:
            alerts.append({
                "site_code": row["site_code"],
                "score": score,
                "reasons": reasons,
            })

    return sorted(alerts, key=lambda x: x["score"])


@router.get("/scores")
async def get_scores(
    month: str = Query(...),
    user: dict = Depends(ALLOWED_ROLES),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT site_code, score, breakdown, calculated_at::text FROM store_scores WHERE score_month = $1 ORDER BY score",
            month,
        )
        return [dict(r) for r in rows]


@router.post("/scores/recalculate")
async def recalculate_scores(
    month: str = Query(...),
    user: dict = Depends(ALLOWED_ROLES),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        scores = await calculate_scores_for_month(conn, month)
        await upsert_scores(conn, month, scores)
        return {"recalculated": len(scores), "month": month}


@router.get("/alerts")
async def get_alerts(
    month: str = Query(...),
    user: dict = Depends(ALLOWED_ROLES),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await get_store_alerts(conn, month)
```

- [ ] **Step 4: Rulează testele CRM**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
pytest tests/test_crm.py -v
```

Rezultat așteptat: toate 3 teste `PASSED`.

- [ ] **Step 5: Rulează toate testele**

```bash
pytest -v
```

Rezultat așteptat: 39+ teste `PASSED`, 0 `FAILED`.

- [ ] **Step 6: Commit**

```bash
cd /opt/Mobiup/unihub
git add backend/routers/crm.py backend/tests/test_crm.py
git commit -m "feat: add CRM router with store scoring and alerts"
```

---

## Task 7: Frontend CRMSubtab

**Files:**
- Modify: `src/components/CRMSubtab.tsx` (înlocuiește stub-ul)
- Create: `src/api/crm.ts`

- [ ] **Step 1: Creează `src/api/crm.ts`**

```typescript
import axios from 'axios';

const api = axios.create({ baseURL: '/api/crm' });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('unihub_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export interface StoreScore {
  site_code: string;
  score: number;
  breakdown: {
    target_pct: number;
    trend_pct: number;
    active_days_pct: number;
    visits_pct: number;
    target_attainment: number;
  } | null;
  calculated_at: string;
}

export interface StoreAlert {
  site_code: string;
  score: number;
  reasons: string[];
}

export async function fetchScores(month: string): Promise<StoreScore[]> {
  const { data } = await api.get('/scores', { params: { month } });
  return data;
}

export async function recalculateScores(month: string): Promise<{ recalculated: number; month: string }> {
  const { data } = await api.post('/scores/recalculate', null, { params: { month } });
  return data;
}

export async function fetchAlerts(month: string): Promise<StoreAlert[]> {
  const { data } = await api.get('/alerts', { params: { month } });
  return data;
}
```

- [ ] **Step 2: Înlocuiește stub-ul `src/components/CRMSubtab.tsx`**

```typescript
import { useEffect, useState } from 'react';
import { RefreshCw, AlertTriangle, BarChart2 } from 'lucide-react';
import { fetchScores, fetchAlerts, recalculateScores, type StoreScore, type StoreAlert } from '../api/crm';
import { createTask } from '../api/tasks';

const CURRENT_MONTH = new Date().toISOString().slice(0, 7);

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 70 ? 'bg-green-500/20 text-green-300' :
    score >= 40 ? 'bg-yellow-500/20 text-yellow-300' :
    score === -1 ? 'bg-white/10 text-white/40' :
    'bg-red-500/20 text-red-300';
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${color}`}>
      {score === -1 ? '—' : score}
    </span>
  );
}

export function CRMSubtab() {
  const [view, setView] = useState<'scores' | 'alerts'>('alerts');
  const [month, setMonth] = useState(CURRENT_MONTH);
  const [scores, setScores] = useState<StoreScore[]>([]);
  const [alerts, setAlerts] = useState<StoreAlert[]>([]);
  const [loading, setLoading] = useState(false);
  const [recalculating, setRecalculating] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      if (view === 'scores') {
        setScores(await fetchScores(month));
      } else {
        setAlerts(await fetchAlerts(month));
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [view, month]);

  const handleRecalculate = async () => {
    setRecalculating(true);
    try {
      const result = await recalculateScores(month);
      await load();
      alert(`Recalculat ${result.recalculated} magazine pentru ${month}`);
    } finally {
      setRecalculating(false);
    }
  };

  const handleCreateTaskFromAlert = async (alert: StoreAlert) => {
    await createTask({
      title: `${alert.site_code}: ${alert.reasons[0]}`,
      site_code: alert.site_code,
      source: 'crm_alert',
      source_meta: { score: alert.score, reasons: alert.reasons, month },
    });
    alert.site_code && alert; // just to use variable
    window.dispatchEvent(new CustomEvent('unihub:navigate', { detail: { tab: 'management', subtab: 'tasks' } }));
  };

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex gap-1">
          <button
            onClick={() => setView('alerts')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              view === 'alerts' ? 'bg-red-500/20 text-red-300' : 'bg-white/10 text-white/50 hover:bg-white/20'
            }`}
          >
            <AlertTriangle size={12} /> Alerte
          </button>
          <button
            onClick={() => setView('scores')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              view === 'scores' ? 'bg-indigo-600 text-white' : 'bg-white/10 text-white/50 hover:bg-white/20'
            }`}
          >
            <BarChart2 size={12} /> Scoruri
          </button>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="month"
            className="bg-white/10 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
          <button
            onClick={handleRecalculate}
            disabled={recalculating}
            className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white/70 text-xs font-medium disabled:opacity-50"
          >
            {recalculating ? 'Se calculează...' : 'Recalculează'}
          </button>
          <button onClick={load} className="p-1.5 rounded bg-white/10 hover:bg-white/20">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Alerte */}
      {view === 'alerts' && (
        <div className="space-y-2">
          {alerts.length === 0 && !loading && (
            <div className="text-center text-white/40 py-8 text-sm">
              Nicio alertă pentru {month}. Apasă Recalculează dacă nu s-au calculat scorurile.
            </div>
          )}
          {alerts.map((alert) => (
            <div key={alert.site_code} className="bg-red-500/5 border border-red-500/20 rounded-xl px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-white">{alert.site_code}</span>
                    <ScoreBadge score={alert.score} />
                  </div>
                  <ul className="mt-1 space-y-0.5">
                    {alert.reasons.map((r, i) => (
                      <li key={i} className="text-xs text-red-300/80 flex items-center gap-1.5">
                        <span className="w-1 h-1 rounded-full bg-red-400 shrink-0" />
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
                <button
                  onClick={() => handleCreateTaskFromAlert(alert)}
                  className="shrink-0 px-3 py-1.5 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-300 text-xs font-medium"
                >
                  + Task
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Scoruri */}
      {view === 'scores' && (
        <div className="space-y-1.5">
          {scores.length === 0 && !loading && (
            <div className="text-center text-white/40 py-8 text-sm">
              Niciun scor calculat pentru {month}. Apasă Recalculează.
            </div>
          )}
          {scores.map((s) => (
            <div key={s.site_code} className="bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 flex items-center gap-3">
              <ScoreBadge score={s.score} />
              <div className="flex-1 min-w-0">
                <span className="text-sm text-white font-medium">{s.site_code}</span>
                {s.breakdown && (
                  <p className="text-xs text-white/40 mt-0.5">
                    Target {s.breakdown.target_attainment}% · Zile {s.breakdown.active_days_pct.toFixed(0)}/20
                  </p>
                )}
              </div>
              <div className="w-24 bg-white/10 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full ${s.score >= 70 ? 'bg-green-500' : s.score >= 40 ? 'bg-yellow-500' : 'bg-red-500'}`}
                  style={{ width: `${s.score}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verifică typecheck**

```bash
cd /opt/Mobiup/unihub
npm run typecheck
```

Rezultat așteptat: 0 erori.

- [ ] **Step 4: Build final**

```bash
npm run build
```

Rezultat așteptat: build reușit, 0 erori.

- [ ] **Step 5: Rulează toate testele backend**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
pytest -v
```

Rezultat așteptat: 39+ teste `PASSED`, 0 `FAILED`.

- [ ] **Step 6: Commit final**

```bash
cd /opt/Mobiup/unihub
git add src/api/crm.ts src/components/CRMSubtab.tsx
git commit -m "feat: CRM sub-tab with store scoring, alerts, and task creation"
```

---

## Task 8: Backend ASM Performance — endpoint combinat PostgreSQL + SQLite

**Files:**
- Modify: `backend/routers/hr.py` (adaugă 2 endpointuri noi)
- Modify: `backend/tests/test_hr.py` (adaugă 2 teste noi)

**Logică:** Endpoint-ul combină date din PostgreSQL (vânzări, targete, agenți) cu date din SQLite `visits.db` (vizite, completion, checklist). Join-ul se face pe `asm_name`. SQLite e citit sincron într-un `run_in_executor` ca să nu blocheze event loop-ul asyncio.

- [ ] **Step 1: Adaugă testele pentru ASM performance în `backend/tests/test_hr.py`**

Adaugă la sfârșitul fișierului existent:

```python
@pytest.mark.anyio
async def test_asm_performance_returns_list():
    from routers.hr import get_asm_performance
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await get_asm_performance(conn, "2026-03", regional=None)
        assert isinstance(result, list)
        if result:
            row = result[0]
            assert "asm" in row
            assert "total_sales" in row
            assert "total_visits" in row  # poate fi 0 dacă luna nu are vizite în SQLite
            assert "target_pct" in row


@pytest.mark.anyio
async def test_asm_performance_history_returns_list():
    from routers.hr import get_asm_performance_history
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await get_asm_performance_history(conn, "Andreea Vladascau", months=6)
        assert isinstance(result, list)
```

- [ ] **Step 2: Rulează testele să fie roșii**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
pytest tests/test_hr.py::test_asm_performance_returns_list tests/test_hr.py::test_asm_performance_history_returns_list -v
```

Rezultat așteptat: `ImportError` pentru `get_asm_performance`.

- [ ] **Step 3: Adaugă funcțiile și endpointurile în `backend/routers/hr.py`**

Adaugă după ultimul endpoint existent (`get_performance`):

```python
import asyncio
import sqlite3

VISITS_DB_PATH = "/opt/Mobiup/unihub/data/visits/visits.db"


def _query_visits_by_asm(year_month: str) -> list[dict]:
    """Execuție sincronă — apelată din run_in_executor."""
    con = sqlite3.connect(VISITS_DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.execute(
        """
        SELECT
            asm,
            COUNT(*) AS total_visits,
            ROUND(AVG(completion_pct), 1) AS avg_completion,
            ROUND(AVG(durata_vizita_ore), 2) AS avg_duration,
            COUNT(DISTINCT magazin) AS distinct_stores,
            ROUND(AVG(
                (COALESCE(curatenie, 0) + COALESCE(imagine, 0) + COALESCE(uniforma, 0)
                 + COALESCE(afise, 0) + COALESCE(produse_promo, 0)) * 20.0
            ), 1) AS checklist_score,
            ROUND(
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
                1
            ) AS approved_pct
        FROM visits
        WHERE substr(data_raport, 1, 7) = ?
          AND asm IS NOT NULL AND asm != ''
        GROUP BY asm
        """,
        (year_month,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def _query_visits_history(asm_name: str, months: int) -> list[dict]:
    """Execuție sincronă — istoricul vizitelor per ASM."""
    con = sqlite3.connect(VISITS_DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.execute(
        """
        SELECT
            substr(data_raport, 1, 7) AS month,
            COUNT(*) AS total_visits,
            ROUND(AVG(completion_pct), 1) AS avg_completion,
            ROUND(AVG(durata_vizita_ore), 2) AS avg_duration
        FROM visits
        WHERE asm = ?
          AND data_raport >= date('now', ? || ' months')
        GROUP BY substr(data_raport, 1, 7)
        ORDER BY month
        """,
        (asm_name, f"-{months}"),
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


async def get_asm_performance(conn: Any, month: str, regional: str | None) -> list[dict]:
    """Profil combinat per ASM: vânzări din PostgreSQL + vizite din SQLite."""
    pg_rows = await conn.fetch(
        """
        SELECT
            s.asm,
            s.regional,
            SUM(ram.total_sales)                                         AS total_sales,
            COALESCE(SUM(st.target_value), 0)                           AS total_target,
            COUNT(DISTINCT ram.site_code)                                AS active_stores,
            COUNT(DISTINCT ram.agent)                                    AS active_agents,
            ROUND(
                SUM(ram.receipt_2plus_count) * 100.0
                / NULLIF(SUM(ram.receipt_count), 0),
                1
            )                                                            AS pct_bon2acc,
            ROUND(
                SUM(ram.focus_quantity) * 100.0
                / NULLIF(SUM(ram.total_quantity), 0),
                1
            )                                                            AS pct_focus
        FROM reporting_agent_month ram
        JOIN stores s ON s.site_code = ram.site_code
        LEFT JOIN store_targets st
            ON st.site_code = ram.site_code AND st.import_month = ram.import_month
        WHERE ram.import_month = $1
          AND ($2::text IS NULL OR s.regional = $2)
        GROUP BY s.asm, s.regional
        ORDER BY total_sales DESC
        """,
        month,
        regional,
    )

    loop = asyncio.get_event_loop()
    sqlite_rows = await loop.run_in_executor(None, _query_visits_by_asm, month)
    sqlite_map = {r["asm"]: r for r in sqlite_rows}

    result = []
    for pg in pg_rows:
        asm = pg["asm"]
        sq = sqlite_map.get(asm, {})
        total_sales = float(pg["total_sales"] or 0)
        total_target = float(pg["total_target"] or 0)
        result.append({
            "asm": asm,
            "regional": pg["regional"],
            "total_sales": total_sales,
            "total_target": total_target,
            "target_pct": round(total_sales / total_target * 100, 1) if total_target > 0 else None,
            "active_stores": pg["active_stores"],
            "active_agents": pg["active_agents"],
            "pct_bon2acc": float(pg["pct_bon2acc"] or 0),
            "pct_focus": float(pg["pct_focus"] or 0),
            "total_visits": sq.get("total_visits", 0),
            "avg_completion": sq.get("avg_completion"),
            "avg_duration": sq.get("avg_duration"),
            "distinct_stores_visited": sq.get("distinct_stores", 0),
            "checklist_score": sq.get("checklist_score"),
            "approved_pct": sq.get("approved_pct"),
        })
    return result


async def get_asm_performance_history(conn: Any, asm_name: str, months: int = 6) -> list[dict]:
    """Trend lunar per ASM: vânzări (PG) + vizite (SQLite) — ultimele N luni."""
    pg_rows = await conn.fetch(
        """
        SELECT
            ram.import_month,
            SUM(ram.total_sales)              AS total_sales,
            COALESCE(SUM(st.target_value), 0) AS total_target,
            COUNT(DISTINCT ram.site_code)      AS active_stores
        FROM reporting_agent_month ram
        JOIN stores s ON s.site_code = ram.site_code
        LEFT JOIN store_targets st
            ON st.site_code = ram.site_code AND st.import_month = ram.import_month
        WHERE s.asm = $1
          AND ram.import_month >= to_char(now() - ($2 || ' months')::interval, 'YYYY-MM')
        GROUP BY ram.import_month
        ORDER BY ram.import_month
        """,
        asm_name,
        str(months),
    )

    loop = asyncio.get_event_loop()
    sqlite_hist = await loop.run_in_executor(None, _query_visits_history, asm_name, months)
    sqlite_map = {r["month"]: r for r in sqlite_hist}

    result = []
    for pg in pg_rows:
        m = pg["import_month"]
        sq = sqlite_map.get(m, {})
        total_sales = float(pg["total_sales"] or 0)
        total_target = float(pg["total_target"] or 0)
        result.append({
            "month": m,
            "total_sales": total_sales,
            "total_target": total_target,
            "target_pct": round(total_sales / total_target * 100, 1) if total_target > 0 else None,
            "active_stores": pg["active_stores"],
            "total_visits": sq.get("total_visits", 0),
            "avg_completion": sq.get("avg_completion"),
            "avg_duration": sq.get("avg_duration"),
        })
    return result


@router.get("/asm-performance")
async def get_asm_perf(
    month: str = Query(...),
    regional: str | None = Query(None),
    user: dict = Depends(ALLOWED_ROLES),
):
    pool = await get_pool()
    # Dacă rolul e management (nu admin), filtru automat pe regional-ul userului
    effective_regional = regional
    if user.get("role") == "management" and not regional:
        effective_regional = user.get("full_name")
    async with pool.acquire() as conn:
        return await get_asm_performance(conn, month, effective_regional)


@router.get("/asm-performance/{asm_name}/history")
async def get_asm_perf_history(
    asm_name: str,
    months: int = Query(6, ge=1, le=24),
    user: dict = Depends(ALLOWED_ROLES),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await get_asm_performance_history(conn, asm_name, months)
```

- [ ] **Step 4: Rulează testele HR (toate)**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
pytest tests/test_hr.py -v
```

Rezultat așteptat: toate 6 teste `PASSED`.

- [ ] **Step 5: Rulează toate testele**

```bash
pytest -v
```

Rezultat așteptat: 41+ teste `PASSED`, 0 `FAILED`.

- [ ] **Step 6: Commit**

```bash
cd /opt/Mobiup/unihub
git add backend/routers/hr.py backend/tests/test_hr.py
git commit -m "feat: add ASM performance endpoint combining PostgreSQL sales + SQLite visits"
```

---

## Task 9: Frontend ASMSubtab

**Files:**
- Modify: `src/components/ASMSubtab.tsx` (înlocuiește stub-ul)
- Modify: `src/api/hr.ts` (adaugă tipuri și funcții pentru ASM)

- [ ] **Step 1: Extinde `src/api/hr.ts` cu tipurile și funcțiile ASM**

Adaugă la sfârșitul fișierului existent:

```typescript
export interface AsmPerformance {
  asm: string;
  regional: string;
  total_sales: number;
  total_target: number;
  target_pct: number | null;
  active_stores: number;
  active_agents: number;
  pct_bon2acc: number;
  pct_focus: number;
  total_visits: number;
  avg_completion: number | null;
  avg_duration: number | null;
  distinct_stores_visited: number;
  checklist_score: number | null;
  approved_pct: number | null;
}

export interface AsmHistoryPoint {
  month: string;
  total_sales: number;
  total_target: number;
  target_pct: number | null;
  active_stores: number;
  total_visits: number;
  avg_completion: number | null;
  avg_duration: number | null;
}

export async function fetchAsmPerformance(month: string, regional?: string): Promise<AsmPerformance[]> {
  const { data } = await api.get('/asm-performance', { params: { month, regional } });
  return data;
}

export async function fetchAsmHistory(asmName: string, months = 6): Promise<AsmHistoryPoint[]> {
  const { data } = await api.get(`/asm-performance/${encodeURIComponent(asmName)}/history`, { params: { months } });
  return data;
}
```

- [ ] **Step 2: Înlocuiește stub-ul `src/components/ASMSubtab.tsx`**

```typescript
import { useEffect, useState } from 'react';
import { RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';
import {
  fetchAsmPerformance,
  fetchAsmHistory,
  type AsmPerformance,
  type AsmHistoryPoint,
} from '../api/hr';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

const CURRENT_MONTH = new Date().toISOString().slice(0, 7);

function TargetBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-white/30 text-xs">—</span>;
  const color = pct >= 90 ? 'text-green-400' : pct >= 70 ? 'text-yellow-400' : 'text-red-400';
  return <span className={`text-sm font-bold ${color}`}>{pct}%</span>;
}

function ScoreDot({ value, max = 100 }: { value: number | null; max?: number }) {
  if (value === null) return <span className="text-white/30 text-xs">—</span>;
  const pct = value / max;
  const color = pct >= 0.7 ? 'bg-green-500' : pct >= 0.4 ? 'bg-yellow-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-sm text-white/80">{value}</span>
      <div className={`w-2 h-2 rounded-full ${color}`} />
    </div>
  );
}

function formatMonth(m: string) {
  const [y, mo] = m.split('-');
  const labels = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Noi', 'Dec'];
  return `${labels[parseInt(mo) - 1]} ${y.slice(2)}`;
}

function ASMRow({ row }: { row: AsmPerformance }) {
  const [expanded, setExpanded] = useState(false);
  const [history, setHistory] = useState<AsmHistoryPoint[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const handleExpand = async () => {
    if (!expanded && history.length === 0) {
      setLoadingHistory(true);
      try {
        setHistory(await fetchAsmHistory(row.asm, 6));
      } finally {
        setLoadingHistory(false);
      }
    }
    setExpanded(!expanded);
  };

  return (
    <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
      <button
        onClick={handleExpand}
        className="w-full px-4 py-3 flex items-center gap-3 hover:bg-white/5 transition-colors text-left"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-white">{row.asm}</span>
            <span className="text-xs text-white/40">{row.regional}</span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5 text-xs text-white/60">
            <span>Vânzări: <strong className="text-white">{(row.total_sales / 1000).toFixed(1)}k</strong></span>
            <span>Target: <TargetBadge pct={row.target_pct} /></span>
            <span>Magazine: <strong className="text-white">{row.active_stores}</strong></span>
            <span>Agenți: <strong className="text-white">{row.active_agents}</strong></span>
            <span>Bon2+: <strong className="text-white">{row.pct_bon2acc}%</strong></span>
            <span>Focus: <strong className="text-white">{row.pct_focus}%</strong></span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-xs text-white/60">
            <span>Vizite: <strong className="text-white">{row.total_visits}</strong></span>
            {row.avg_completion !== null && <span>Completion: <strong className="text-white">{row.avg_completion}%</strong></span>}
            {row.checklist_score !== null && <span>Checklist: <ScoreDot value={row.checklist_score} /></span>}
            {row.avg_duration !== null && <span>Durată: <strong className="text-white">{row.avg_duration}h</strong></span>}
          </div>
        </div>
        {expanded ? <ChevronUp size={16} className="text-white/40 shrink-0" /> : <ChevronDown size={16} className="text-white/40 shrink-0" />}
      </button>

      {expanded && (
        <div className="border-t border-white/10 px-4 py-3">
          {loadingHistory ? (
            <div className="text-center text-white/40 text-xs py-4">Se încarcă...</div>
          ) : history.length === 0 ? (
            <div className="text-center text-white/40 text-xs py-4">Fără date istorice</div>
          ) : (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={history} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="month" tickFormatter={formatMonth} tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }} />
                  <YAxis yAxisId="left" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: '#1e1e2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }}
                    labelFormatter={formatMonth}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }} />
                  <Bar yAxisId="left" dataKey="total_sales" name="Vânzări" fill="#6366f1" opacity={0.7} radius={[4, 4, 0, 0]} />
                  <Line yAxisId="right" type="monotone" dataKey="target_pct" name="% Target" stroke="#22d3ee" strokeWidth={2} dot={false} />
                  <Line yAxisId="right" type="monotone" dataKey="total_visits" name="Vizite" stroke="#f59e0b" strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ASMSubtab() {
  const [data, setData] = useState<AsmPerformance[]>([]);
  const [loading, setLoading] = useState(true);
  const [month, setMonth] = useState(CURRENT_MONTH);

  const load = async () => {
    setLoading(true);
    try {
      setData(await fetchAsmPerformance(month));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [month]);

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white/80 uppercase tracking-wide">Performanță ASM</h3>
        <div className="flex items-center gap-2">
          <input
            type="month"
            className="bg-white/10 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
          <button onClick={load} className="p-1.5 rounded bg-white/10 hover:bg-white/20">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {data.length === 0 && !loading && (
          <div className="text-center text-white/40 py-8 text-sm">Fără date pentru {month}</div>
        )}
        {data.map((row) => (
          <ASMRow key={row.asm} row={row} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verifică typecheck**

```bash
cd /opt/Mobiup/unihub
npm run typecheck
```

Rezultat așteptat: 0 erori.

- [ ] **Step 4: Build final**

```bash
npm run build
```

Rezultat așteptat: build reușit, 0 erori.

- [ ] **Step 5: Rulează toate testele backend**

```bash
cd /opt/Mobiup/unihub/backend
source venv/bin/activate
pytest -v
```

Rezultat așteptat: 41+ teste `PASSED`, 0 `FAILED`.

- [ ] **Step 6: Commit final**

```bash
cd /opt/Mobiup/unihub
git add src/api/hr.ts src/components/ASMSubtab.tsx
git commit -m "feat: ASM performance sub-tab with combined sales and visit KPIs"
```

---

## Checklist final înainte de deploy

- [ ] `npm run typecheck` — 0 erori
- [ ] `npm run build` — build reușit
- [ ] `pytest -v` — toate testele verzi
- [ ] Deploy:
  ```bash
  cd /opt/Mobiup/unihub
  git pull
  npm run build
  sudo systemctl restart unihub-backend
  ```
- [ ] Verifică în browser: tab Management apare pentru admin/management, NU pentru tl
- [ ] Testează: creare task → apare în listă → schimbă status prin click
- [ ] Testează: cerere concediu → aprobare → statusul se schimbă
- [ ] Testează: Recalculează scoruri pentru luna curentă → apar în Scoruri și Alerte
- [ ] Testează: buton "+ Task" din alertă CRM → task creat cu `source: 'crm_alert'`
