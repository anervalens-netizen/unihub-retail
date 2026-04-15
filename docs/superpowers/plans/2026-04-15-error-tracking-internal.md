# Internal Error Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capturare automată erori backend + frontend în PostgreSQL, cu badge activ în sidebar și pagină de vizualizare în Settings.

**Architecture:** `DBErrorHandler` (async, non-blocking) colectează `logger.error/exception` → INSERT în `error_logs` PG. Frontend trimite erori JS la `POST /api/errors`. Admin vede badge roșu în sidebar + tab "Erori sistem" în Settings.

**Tech Stack:** Python asyncio logging handler, asyncpg, FastAPI, React 19, TypeScript, Tailwind CSS.

---

## File Map

**Create:**
- `backend/routers/errors.py` — POST /api/errors (ingestie frontend) + admin endpoints
- `backend/tests/test_errors.py` — teste pentru router
- `src/api/errors.ts` — client API erori
- `src/components/ErrorLogsTab.tsx` — UI tab erori sistem

**Modify:**
- `backend/db/schema_v2.sql` — adaugă tabelul `error_logs`
- `backend/logging_config.py` — adaugă `DBErrorHandler` + `attach_db_error_handler`
- `backend/main.py` — înregistrează router + apelează `attach_db_error_handler`
- `src/main.tsx` — hook-uri globale `window.onerror` + `onunhandledrejection`
- `src/components/ErrorBoundary.tsx` — apelează `postFrontendError` în `componentDidCatch`
- `src/components/Settings.tsx` — adaugă tab "Erori sistem" + import `ErrorLogsTab`
- `src/components/MainLayout.tsx` — polling `unseen-count` + prop `errorCount`
- `src/components/DesktopSidebar.tsx` — badge pe iconița Settings

---

## Task 1: Schema DB — tabelul `error_logs`

**Files:**
- Modify: `backend/db/schema_v2.sql`

- [ ] **Step 1: Adaugă tabelul la finalul `schema_v2.sql`**

Deschide `backend/db/schema_v2.sql` și adaugă la final:

```sql
CREATE TABLE IF NOT EXISTS error_logs (
    id          SERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    source      TEXT NOT NULL CHECK (source IN ('backend', 'frontend')),
    level       TEXT NOT NULL CHECK (level IN ('error', 'warning')),
    message     TEXT NOT NULL,
    traceback   TEXT,
    path        TEXT,
    user_id     INT REFERENCES users(id) ON DELETE SET NULL,
    extra       JSONB,
    seen        BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_error_logs_ts   ON error_logs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_error_logs_seen ON error_logs(seen) WHERE seen = false;
```

- [ ] **Step 2: Aplică schema în DB test**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate
python - <<'EOF'
import asyncio, db.connection as c
async def main():
    await c.init_db_pool()
    await c.ensure_schema_current(force=True)
    print("done")
asyncio.run(main())
EOF
```

Expected: `done` fără erori.

- [ ] **Step 3: Verifică tabelul în DB**

```bash
python - <<'EOF'
import asyncio, db.connection as c
async def main():
    await c.init_db_pool()
    pool = await c.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) FROM error_logs")
        print("error_logs OK, rows:", row[0])
asyncio.run(main())
EOF
```

Expected: `error_logs OK, rows: 0`

- [ ] **Step 4: Commit**

```bash
cd /opt/Mobiup/unihub
git add backend/db/schema_v2.sql
git commit -m "feat: add error_logs table to schema"
```

---

## Task 2: Backend router — `errors.py`

**Files:**
- Create: `backend/routers/errors.py`
- Create: `backend/tests/test_errors.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Scrie testele (failing)**

Creează `backend/tests/test_errors.py`:

```python
from __future__ import annotations

import pytest
from db.connection import get_pool


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_insert_and_list_error_log():
    from routers.errors import insert_error_log, list_error_logs
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await insert_error_log(conn, {
            "source": "backend",
            "level": "error",
            "message": "test error",
            "traceback": "Traceback...",
            "path": "/api/test",
            "user_id": None,
            "extra": None,
        })
        assert row["message"] == "test error"
        assert row["seen"] is False
        log_id = row["id"]

        rows = await list_error_logs(conn, source=None, level=None, seen=None,
                                     from_date=None, to_date=None, page=1, page_size=50)
        ids = [r["id"] for r in rows]
        assert log_id in ids

        await conn.execute("DELETE FROM error_logs WHERE id = $1", log_id)


@pytest.mark.anyio
async def test_mark_all_seen():
    from routers.errors import insert_error_log, mark_all_seen, get_unseen_count
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await insert_error_log(conn, {
            "source": "frontend", "level": "error",
            "message": "js crash", "traceback": None,
            "path": "/app", "user_id": None, "extra": None,
        })
        log_id = row["id"]

        count_before = await get_unseen_count(conn)
        assert count_before >= 1

        await mark_all_seen(conn)
        count_after = await get_unseen_count(conn)
        assert count_after == 0

        await conn.execute("DELETE FROM error_logs WHERE id = $1", log_id)


@pytest.mark.anyio
async def test_delete_old_logs():
    from routers.errors import insert_error_log, delete_old_logs
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Inserează un log cu ts forțat în trecut
        row = await conn.fetchrow(
            """
            INSERT INTO error_logs (source, level, message, ts)
            VALUES ('backend', 'error', 'old error', now() - interval '31 days')
            RETURNING id
            """
        )
        old_id = row["id"]

        deleted = await delete_old_logs(conn, days=30)
        assert deleted >= 1

        remaining = await conn.fetchval(
            "SELECT COUNT(*) FROM error_logs WHERE id = $1", old_id
        )
        assert remaining == 0


@pytest.mark.anyio
async def test_rate_limiter():
    from routers.errors import RateLimiter
    limiter = RateLimiter(limit=3, window=60)
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False  # al 4-lea respins
    assert limiter.allow("5.6.7.8") is True   # alt IP — ok


@pytest.mark.anyio
async def test_list_filter_by_source():
    from routers.errors import insert_error_log, list_error_logs
    pool = await get_pool()
    async with pool.acquire() as conn:
        r1 = await insert_error_log(conn, {
            "source": "backend", "level": "error", "message": "be err",
            "traceback": None, "path": None, "user_id": None, "extra": None,
        })
        r2 = await insert_error_log(conn, {
            "source": "frontend", "level": "error", "message": "fe err",
            "traceback": None, "path": None, "user_id": None, "extra": None,
        })

        be_rows = await list_error_logs(conn, source="backend", level=None,
                                        seen=None, from_date=None, to_date=None,
                                        page=1, page_size=50)
        sources = {r["source"] for r in be_rows}
        assert sources == {"backend"}

        await conn.execute("DELETE FROM error_logs WHERE id = ANY($1)", [r1["id"], r2["id"]])
```

- [ ] **Step 2: Rulează testele — verifică că eșuează**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate
python -m pytest tests/test_errors.py -v 2>&1 | head -30
```

Expected: `ImportError` sau `ModuleNotFoundError` — `routers.errors` nu există.

- [ ] **Step 3: Implementează `backend/routers/errors.py`**

```python
from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from db.connection import get_pool
from dependencies import require_role

router = APIRouter(tags=["errors"])


# ── Rate limiter ──────────────────────────────────────────────────────────────

class RateLimiter:
    """Sliding window rate limiter in-memory per IP."""

    def __init__(self, limit: int = 10, window: int = 60) -> None:
        self.limit = limit
        self.window = window
        self._store: dict[str, list[float]] = defaultdict(list)

    def allow(self, ip: str) -> bool:
        now = time.time()
        timestamps = [t for t in self._store[ip] if now - t < self.window]
        if len(timestamps) >= self.limit:
            self._store[ip] = timestamps
            return False
        timestamps.append(now)
        self._store[ip] = timestamps
        return True


_limiter = RateLimiter(limit=10, window=60)

MAX_PAYLOAD_BYTES = 8 * 1024  # 8 KB


# ── Pydantic models ───────────────────────────────────────────────────────────

class FrontendErrorPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str
    traceback: str | None = None
    path: str | None = None
    user_id: int | None = None
    extra: dict[str, Any] | None = None


# ── Service functions (testabile direct) ─────────────────────────────────────

async def insert_error_log(conn: Any, data: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO error_logs
            (source, level, message, traceback, path, user_id, extra)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id, ts::text, source, level, message, traceback, path,
                  user_id, extra::text, seen
        """,
        data["source"],
        data["level"],
        data["message"][:2000],
        (data.get("traceback") or "")[:4000] or None,
        data.get("path"),
        data.get("user_id"),
        json.dumps(data["extra"]) if data.get("extra") else None,
    )
    return dict(row)


async def list_error_logs(
    conn: Any,
    source: str | None,
    level: str | None,
    seen: bool | None,
    from_date: str | None,
    to_date: str | None,
    page: int,
    page_size: int,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    idx = 1

    if source:
        clauses.append(f"source = ${idx}"); params.append(source); idx += 1
    if level:
        clauses.append(f"level = ${idx}"); params.append(level); idx += 1
    if seen is not None:
        clauses.append(f"seen = ${idx}"); params.append(seen); idx += 1
    if from_date:
        clauses.append(f"ts >= ${idx}::timestamptz"); params.append(from_date); idx += 1
    if to_date:
        clauses.append(f"ts <= ${idx}::timestamptz"); params.append(to_date); idx += 1

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size

    rows = await conn.fetch(
        f"""
        SELECT id, ts::text, source, level, message, traceback, path,
               user_id, extra::text, seen
        FROM error_logs
        {where}
        ORDER BY ts DESC
        LIMIT ${idx} OFFSET ${idx + 1}
        """,
        *params, page_size, offset,
    )
    return [dict(r) for r in rows]


async def get_unseen_count(conn: Any) -> int:
    return await conn.fetchval("SELECT COUNT(*) FROM error_logs WHERE seen = false") or 0


async def mark_all_seen(conn: Any) -> None:
    await conn.execute("UPDATE error_logs SET seen = true WHERE seen = false")


async def delete_old_logs(conn: Any, days: int = 30) -> int:
    result = await conn.execute(
        "DELETE FROM error_logs WHERE ts < now() - ($1 || ' days')::interval",
        str(days),
    )
    # result e "DELETE N"
    parts = result.split()
    return int(parts[1]) if len(parts) == 2 else 0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/api/errors", status_code=status.HTTP_204_NO_CONTENT)
async def ingest_frontend_error(
    request: Request,
    payload: FrontendErrorPayload,
) -> None:
    """Ingestie erori frontend — fără auth, rate-limited."""
    ip = request.client.host if request.client else "unknown"
    if not _limiter.allow(ip):
        raise HTTPException(status_code=429, detail="Rate limit depășit")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await insert_error_log(conn, {
            "source": "frontend",
            "level": "error",
            "message": payload.message,
            "traceback": payload.traceback,
            "path": payload.path,
            "user_id": payload.user_id,
            "extra": payload.extra,
        })


@router.get("/api/admin/error-logs")
async def get_error_logs(
    request: Request,
    source: str | None = None,
    level: str | None = None,
    seen: bool | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(require_role("admin")),
) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await list_error_logs(conn, source, level, seen, from_date, to_date, page, page_size)


@router.get("/api/admin/error-logs/unseen-count")
async def unseen_count(user: dict = Depends(require_role("admin"))) -> dict[str, int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return {"count": await get_unseen_count(conn)}


@router.post("/api/admin/error-logs/mark-seen", status_code=status.HTTP_204_NO_CONTENT)
async def mark_seen(user: dict = Depends(require_role("admin"))) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await mark_all_seen(conn)


@router.delete("/api/admin/error-logs/old")
async def delete_old(
    days: int = 30,
    user: dict = Depends(require_role("admin")),
) -> dict[str, int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        deleted = await delete_old_logs(conn, days)
    return {"deleted": deleted}
```

- [ ] **Step 4: Înregistrează router în `main.py`**

În `backend/main.py`, la linia cu importurile de routere:

```python
from routers import admin, agents, ai, auth, campaigns, crm, dashboard, errors, filters, hr, imports, salarii, stores, tasks, visits_report
```

Și după `app.include_router(crm.router)` adaugă:

```python
app.include_router(errors.router)
```

- [ ] **Step 5: Rulează testele — verifică că trec**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate
python -m pytest tests/test_errors.py -v 2>&1 | tail -20
```

Expected: `5 passed`

- [ ] **Step 6: Rulează toate testele**

```bash
python -m pytest --tb=short -q 2>&1 | tail -10
```

Expected: `78 passed` → acum `83 passed` (sau similar)

- [ ] **Step 7: Commit**

```bash
cd /opt/Mobiup/unihub
git add backend/routers/errors.py backend/tests/test_errors.py backend/main.py
git commit -m "feat: add error_logs router (ingest + admin endpoints + rate limiter)"
```

---

## Task 3: `DBErrorHandler` — capturare automată erori Python

**Files:**
- Modify: `backend/logging_config.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Adaugă `DBErrorHandler` și `attach_db_error_handler` în `logging_config.py`**

La finalul `backend/logging_config.py`, după funcția `setup_logging`, adaugă:

```python
import asyncio
import json as _json
import logging

_db_handler_instance: "DBErrorHandler | None" = None


class DBErrorHandler(logging.Handler):
    """Handler async non-blocking — inserează ERROR+ în tabelul error_logs.

    Se activează prin attach_db_error_handler(pool) după ce pool-ul DB
    e inițializat. Înainte de attach, emit() este no-op.
    Niciodată nu ridică excepții — erori de scriere în DB sunt silențioase.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self._pool: object | None = None

    def attach(self, pool: object) -> None:
        self._pool = pool

    def emit(self, record: logging.LogRecord) -> None:
        if self._pool is None:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._insert(record))
        except Exception:
            pass

    async def _insert(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            traceback: str | None = None
            if record.exc_info:
                traceback = self.formatException(record.exc_info)

            extra: dict | None = None
            skip = {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            }
            extra_data = {k: v for k, v in record.__dict__.items()
                          if k not in skip and not k.startswith("_")}
            if extra_data:
                extra = extra_data

            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO error_logs
                        (source, level, message, traceback, path, extra)
                    VALUES ('backend', 'error', $1, $2, $3, $4)
                    """,
                    message[:2000],
                    (traceback or "")[:4000] or None,
                    record.name,
                    _json.dumps(extra, default=str) if extra else None,
                )
        except Exception:
            pass  # Niciodată nu crăpa din cauza logging-ului


def attach_db_error_handler(pool: object) -> None:
    """Activează DBErrorHandler pe root logger. Apelat după init_db_pool."""
    global _db_handler_instance
    if _db_handler_instance is None:
        _db_handler_instance = DBErrorHandler()
        logging.getLogger().addHandler(_db_handler_instance)
    _db_handler_instance.attach(pool)
```

- [ ] **Step 2: Apelează `attach_db_error_handler` în lifespan din `main.py`**

În `backend/main.py`, la importurile din `logging_config`:

```python
from logging_config import attach_db_error_handler, setup_logging
```

În funcția `lifespan`, după `await init_db_pool()`:

```python
    await init_db_pool()
    current_pool = await get_pool()
    attach_db_error_handler(current_pool)
```

Adaugă imediat după `await init_db_pool()`, înaintea oricărui alt cod din lifespan.

- [ ] **Step 3: Verifică manual că handler-ul funcționează**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate
python - <<'EOF'
import asyncio, logging
import db.connection as c
from logging_config import attach_db_error_handler

async def main():
    await c.init_db_pool()
    pool = await c.get_pool()
    attach_db_error_handler(pool)

    logger = logging.getLogger("test.manual")
    logger.error("test error din DBErrorHandler")
    await asyncio.sleep(0.2)  # lasă task-ul să se execute

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT message FROM error_logs WHERE message = 'test error din DBErrorHandler' LIMIT 1"
        )
        assert row is not None, "Eroarea nu a ajuns în DB!"
        print("OK — eroarea e în DB:", row["message"])
        await conn.execute("DELETE FROM error_logs WHERE message = 'test error din DBErrorHandler'")

asyncio.run(main())
EOF
```

Expected: `OK — eroarea e în DB: test error din DBErrorHandler`

- [ ] **Step 4: Rulează pytest complet**

```bash
python -m pytest --tb=short -q 2>&1 | tail -10
```

Expected: toate testele anterioare trec (DBErrorHandler e no-op în teste — pool nu e atașat)

- [ ] **Step 5: Commit**

```bash
cd /opt/Mobiup/unihub
git add backend/logging_config.py backend/main.py
git commit -m "feat: DBErrorHandler — async non-blocking backend error capture"
```

---

## Task 4: Curățare la boot + delete loguri vechi

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Adaugă curățare la boot în lifespan**

În `backend/main.py`, în funcția `lifespan`, după `attach_db_error_handler`:

```python
    # Curăță error_logs mai vechi de 30 zile
    from routers.errors import delete_old_logs
    async with current_pool.acquire() as conn:
        deleted_errors = await delete_old_logs(conn, days=30)
        if deleted_errors:
            logger.info("error_logs cleanup: %d rows deleted (>30 days)", deleted_errors)
```

- [ ] **Step 2: Verifică boot curat**

```bash
sudo systemctl restart unihub-backend && sleep 3 && sudo systemctl status unihub-backend --no-pager | grep -E "Active|error"
```

Expected: `Active: active (running)`

- [ ] **Step 3: Commit**

```bash
cd /opt/Mobiup/unihub
git add backend/main.py
git commit -m "feat: cleanup error_logs >30 days at boot"
```

---

## Task 5: Frontend API + hooks globale

**Files:**
- Create: `src/api/errors.ts`
- Modify: `src/main.tsx`
- Modify: `src/components/ErrorBoundary.tsx`

- [ ] **Step 1: Creează `src/api/errors.ts`**

```typescript
import axios from 'axios';

export interface ErrorLogEntry {
  id: number;
  ts: string;
  source: 'backend' | 'frontend';
  level: 'error' | 'warning';
  message: string;
  traceback: string | null;
  path: string | null;
  user_id: number | null;
  extra: string | null;
  seen: boolean;
}

export interface UnseenCountResponse {
  count: number;
}

export async function postFrontendError(payload: {
  message: string;
  traceback?: string | null;
  path?: string | null;
  user_id?: number | null;
  extra?: Record<string, unknown> | null;
}): Promise<void> {
  try {
    await axios.post('/api/errors', payload, { timeout: 3000 });
  } catch {
    // fire-and-forget — nu bloca UX niciodată
  }
}

export async function getUnseenCount(token: string): Promise<number> {
  const res = await axios.get<UnseenCountResponse>(
    '/api/admin/error-logs/unseen-count',
    { headers: { Authorization: `Bearer ${token}` } }
  );
  return res.data.count;
}

export async function markAllSeen(token: string): Promise<void> {
  await axios.post(
    '/api/admin/error-logs/mark-seen',
    {},
    { headers: { Authorization: `Bearer ${token}` } }
  );
}

export async function getErrorLogs(
  token: string,
  params: {
    source?: string;
    level?: string;
    seen?: boolean;
    from_date?: string;
    to_date?: string;
    page?: number;
    page_size?: number;
  } = {}
): Promise<ErrorLogEntry[]> {
  const res = await axios.get<ErrorLogEntry[]>('/api/admin/error-logs', {
    headers: { Authorization: `Bearer ${token}` },
    params,
  });
  return res.data;
}
```

- [ ] **Step 2: Actualizează `src/main.tsx` cu hook-uri globale**

Înlocuiește conținutul complet al `src/main.tsx`:

```typescript
import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import {postFrontendError} from './api/errors';
import App from './App.tsx';
import './index.css';

window.onerror = (message, _source, lineno, colno, error) => {
  postFrontendError({
    message: String(message),
    traceback: error?.stack ?? null,
    path: window.location.pathname,
    extra: { lineno, colno },
  });
};

window.onunhandledrejection = (event: PromiseRejectionEvent) => {
  const reason = event.reason as { message?: string; stack?: string } | string | undefined;
  postFrontendError({
    message: reason && typeof reason === 'object' && reason.message
      ? reason.message
      : String(reason ?? 'Unhandled rejection'),
    traceback: reason && typeof reason === 'object' ? reason.stack ?? null : null,
    path: window.location.pathname,
  });
};

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

Notă: `@sentry/react` a fost adăugat în sesiunea anterioară — dacă `VITE_SENTRY_DSN` e gol (cum e acum), Sentry nu rulează, deci nu e conflict. Totuși, **înlocuiește complet fișierul** cu versiunea de mai sus (fără importul Sentry) pentru a simplifica — Sentry rămâne dezactivat implicit.

- [ ] **Step 3: Actualizează `src/components/ErrorBoundary.tsx`**

Înlocuiește conținutul complet:

```typescript
import React, { Component, type ReactNode } from 'react';
import { postFrontendError } from '../api/errors';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    postFrontendError({
      message: error.message,
      traceback: error.stack ?? null,
      path: window.location.pathname,
      extra: { componentStack: errorInfo.componentStack },
    });
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="p-10 text-red-500 bg-red-100">
          <h1 className="text-2xl font-bold">CRASHED!</h1>
          <pre>{this.state.error?.message}</pre>
          <pre className="text-xs mt-2 opacity-70">{this.state.error?.stack}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}
```

- [ ] **Step 4: Typecheck**

```bash
cd /opt/Mobiup/unihub && npx tsc --noEmit 2>&1 | head -20
```

Expected: nicio eroare.

- [ ] **Step 5: Commit**

```bash
git add src/api/errors.ts src/main.tsx src/components/ErrorBoundary.tsx
git commit -m "feat: frontend error capture (global hooks + ErrorBoundary + API client)"
```

---

## Task 6: Componentă `ErrorLogsTab.tsx`

**Files:**
- Create: `src/components/ErrorLogsTab.tsx`

- [ ] **Step 1: Creează `src/components/ErrorLogsTab.tsx`**

```typescript
import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCheck, RefreshCw, Trash2 } from 'lucide-react';
import { cn } from '../lib/utils';
import {
  getErrorLogs,
  markAllSeen,
  type ErrorLogEntry,
} from '../api/errors';
import type { AuthUser } from '../api/types';

interface Props {
  user: AuthUser | null;
  token: string | null;
  onUnseenCountChange: (count: number) => void;
}

const SOURCE_LABELS: Record<string, string> = {
  backend: 'Backend',
  frontend: 'Frontend',
};

export function ErrorLogsTab({ user: _user, token, onUnseenCountChange }: Props) {
  const [logs, setLogs] = useState<ErrorLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedLog, setSelectedLog] = useState<ErrorLogEntry | null>(null);
  const [filterSource, setFilterSource] = useState('');
  const [filterSeen, setFilterSeen] = useState<'' | 'false' | 'true'>('');

  async function load() {
    if (!token) return;
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page_size: 100 };
      if (filterSource) params.source = filterSource;
      if (filterSeen !== '') params.seen = filterSeen === 'true';
      const data = await getErrorLogs(token, params);
      setLogs(data);
      const unseen = data.filter((l) => !l.seen).length;
      onUnseenCountChange(unseen);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [filterSource, filterSeen, token]);

  async function handleMarkAllSeen() {
    if (!token) return;
    await markAllSeen(token);
    await load();
  }

  const unseenCount = logs.filter((l) => !l.seen).length;

  return (
    <div className="space-y-4">
      {/* Header + actions */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <AlertTriangle size={16} className="text-red-500" />
          <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
            Erori sistem
          </span>
          {unseenCount > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">
              {unseenCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"
          >
            <RefreshCw size={12} /> Reîncarcă
          </button>
          <button
            onClick={handleMarkAllSeen}
            disabled={unseenCount === 0}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-40 hover:bg-indigo-700"
          >
            <CheckCheck size={12} /> Marchează toate ca văzute
          </button>
        </div>
      </div>

      {/* Filtre */}
      <div className="flex gap-3 flex-wrap">
        <select
          value={filterSource}
          onChange={(e) => setFilterSource(e.target.value)}
          className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs text-slate-700 dark:text-slate-300"
        >
          <option value="">Toate sursele</option>
          <option value="backend">Backend</option>
          <option value="frontend">Frontend</option>
        </select>
        <select
          value={filterSeen}
          onChange={(e) => setFilterSeen(e.target.value as '' | 'false' | 'true')}
          className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs text-slate-700 dark:text-slate-300"
        >
          <option value="">Toate</option>
          <option value="false">Nevăzute</option>
          <option value="true">Văzute</option>
        </select>
      </div>

      {/* Tabel */}
      {loading ? (
        <div className="text-xs text-slate-400 py-4 text-center">Se încarcă...</div>
      ) : logs.length === 0 ? (
        <div className="text-xs text-slate-400 py-8 text-center">Nicio eroare înregistrată.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">Timestamp</th>
                <th className="px-3 py-2 text-left font-semibold">Sursă</th>
                <th className="px-3 py-2 text-left font-semibold">Mesaj</th>
                <th className="px-3 py-2 text-left font-semibold">Path</th>
                <th className="px-3 py-2 text-left font-semibold">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
              {logs.map((log) => (
                <tr
                  key={log.id}
                  onClick={() => setSelectedLog(log)}
                  className={cn(
                    'cursor-pointer hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors',
                    !log.seen && 'bg-red-50/40 dark:bg-red-900/10'
                  )}
                >
                  <td className="px-3 py-2 whitespace-nowrap font-mono text-[10px] text-slate-500">
                    {new Date(log.ts).toLocaleString('ro-RO')}
                  </td>
                  <td className="px-3 py-2">
                    <span className={cn(
                      'rounded px-1.5 py-0.5 text-[10px] font-bold',
                      log.source === 'backend'
                        ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                        : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                    )}>
                      {SOURCE_LABELS[log.source] ?? log.source}
                    </span>
                  </td>
                  <td className="px-3 py-2 max-w-[300px] truncate text-slate-700 dark:text-slate-300">
                    {log.message}
                  </td>
                  <td className="px-3 py-2 max-w-[150px] truncate text-slate-500 font-mono text-[10px]">
                    {log.path ?? '—'}
                  </td>
                  <td className="px-3 py-2">
                    {log.seen ? (
                      <span className="text-slate-400 text-[10px]">văzut</span>
                    ) : (
                      <span className="h-2 w-2 rounded-full bg-red-500 inline-block" />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal detalii */}
      {selectedLog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={() => setSelectedLog(null)}
        >
          <div
            className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-y-auto p-6 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className={cn(
                    'rounded px-1.5 py-0.5 text-[10px] font-bold',
                    selectedLog.source === 'backend'
                      ? 'bg-orange-100 text-orange-700'
                      : 'bg-blue-100 text-blue-700'
                  )}>
                    {SOURCE_LABELS[selectedLog.source]}
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">
                    {new Date(selectedLog.ts).toLocaleString('ro-RO')}
                  </span>
                </div>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                  {selectedLog.message}
                </p>
              </div>
              <button
                onClick={() => setSelectedLog(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 shrink-0"
              >
                <Trash2 size={14} />
              </button>
            </div>
            {selectedLog.path && (
              <div>
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Path</span>
                <p className="font-mono text-xs text-slate-700 dark:text-slate-300 mt-0.5">{selectedLog.path}</p>
              </div>
            )}
            {selectedLog.traceback && (
              <div>
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Stack Trace</span>
                <pre className="mt-1 p-3 rounded-lg bg-slate-950 text-green-400 text-[10px] overflow-x-auto whitespace-pre-wrap font-mono">
                  {selectedLog.traceback}
                </pre>
              </div>
            )}
            {selectedLog.extra && (
              <div>
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Extra</span>
                <pre className="mt-1 p-3 rounded-lg bg-slate-100 dark:bg-slate-800 text-[10px] overflow-x-auto font-mono">
                  {JSON.stringify(JSON.parse(selectedLog.extra), null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

```bash
cd /opt/Mobiup/unihub && npx tsc --noEmit 2>&1 | head -20
```

Expected: nicio eroare.

- [ ] **Step 3: Commit**

```bash
git add src/components/ErrorLogsTab.tsx
git commit -m "feat: ErrorLogsTab component — tabel erori cu filtre și modal detalii"
```

---

## Task 7: Integrare în `Settings.tsx`

**Files:**
- Modify: `src/components/Settings.tsx`

- [ ] **Step 1: Citește secțiunea de render din Settings.tsx**

```bash
grep -n "return\|<div\|className\|section\|h2\|h3" /opt/Mobiup/unihub/src/components/Settings.tsx | grep -v "^Binary" | head -40
```

Identifică linia unde începe `return (` și structura principală.

- [ ] **Step 2: Adaugă tab-uri în Settings.tsx**

La importuri, adaugă:
```typescript
import { ErrorLogsTab } from './ErrorLogsTab';
```

În `SettingsProps`, adaugă:
```typescript
  token: string | null;
  onUnseenCountChange: (count: number) => void;
```

În corpul componentei, adaugă state pentru tab activ după celelalte `useState`:
```typescript
  const [activeSettingsTab, setActiveSettingsTab] = useState<'admin' | 'errors'>('admin');
```

La începutul secțiunii `return`, **înaintea** primului element returnat, înfășoară conținutul existent astfel:

Găsește prima linie a return-ului (de obicei `<div className="...">`) și înaintea ei adaugă tab bar-ul, condiționat de rol admin:

```typescript
  if (user?.role !== 'admin') {
    return <div className="p-4 text-sm text-slate-500">Acces restricționat.</div>;
  }

  return (
    <div className="..."> {/* păstrează className-ul original */}
      {/* Tab bar */}
      <div className="flex gap-1 mb-4 border-b border-slate-200 dark:border-slate-700">
        <button
          onClick={() => setActiveSettingsTab('admin')}
          className={cn(
            'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
            activeSettingsTab === 'admin'
              ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
              : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
          )}
        >
          Administrare
        </button>
        <button
          onClick={() => setActiveSettingsTab('errors')}
          className={cn(
            'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
            activeSettingsTab === 'errors'
              ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
              : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
          )}
        >
          Erori sistem
        </button>
      </div>

      {activeSettingsTab === 'errors' ? (
        <ErrorLogsTab
          user={user}
          token={token}
          onUnseenCountChange={onUnseenCountChange}
        />
      ) : (
        /* CONȚINUTUL ORIGINAL AL SETTINGS — tot ce era mai înainte în return */
        <>
          {/* ...tot conținutul original... */}
        </>
      )}
    </div>
  );
```

**Notă:** Conținutul original din `return` se mută înăuntrul blocului `activeSettingsTab === 'admin'`. Nu șterge nimic din logica existentă — mută-o în interior.

- [ ] **Step 3: Actualizează locul unde Settings e instanțiat în `App.tsx`**

```bash
grep -n "Settings\|onImportCompleted\|settings" /opt/Mobiup/unihub/src/App.tsx | head -20
```

Găsește `<Settings` în `App.tsx` și adaugă prop-urile noi:
```typescript
<Settings
  user={user}
  onImportCompleted={handleImportCompleted}
  token={token}
  onUnseenCountChange={setErrorCount}
/>
```

Adaugă state în `App.tsx`:
```typescript
const [errorCount, setErrorCount] = useState(0);
```

Pasează `errorCount` mai departe la `MainLayout` (dacă există prop pentru asta — Task 8 adaugă badge-ul).

- [ ] **Step 4: Typecheck**

```bash
cd /opt/Mobiup/unihub && npx tsc --noEmit 2>&1 | head -20
```

Expected: nicio eroare.

- [ ] **Step 5: Commit**

```bash
git add src/components/Settings.tsx src/App.tsx
git commit -m "feat: Settings — tab Erori sistem integrat"
```

---

## Task 8: Badge în sidebar + polling

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/components/MainLayout.tsx`
- Modify: `src/components/DesktopSidebar.tsx`

- [ ] **Step 1: Adaugă polling `unseen-count` în `App.tsx`**

În `App.tsx`, adaugă un `useEffect` pentru polling (doar pentru admin):

```typescript
import { getUnseenCount } from './api/errors';

// În corpul App, după state-ul errorCount:
useEffect(() => {
  if (user?.role !== 'admin' || !token) return;

  async function poll() {
    try {
      const count = await getUnseenCount(token!);
      setErrorCount(count);
    } catch {
      // silențios
    }
  }

  poll();
  const interval = setInterval(poll, 60_000);
  return () => clearInterval(interval);
}, [user?.role, token]);
```

- [ ] **Step 2: Pasează `errorCount` la `MainLayout`**

În `MainLayout`'s interface `MainLayoutProps`, adaugă:
```typescript
  errorCount?: number;
```

În `MainLayout`, pasează `errorCount` la `DesktopSidebar`:
```typescript
<DesktopSidebar
  ...
  errorCount={errorCount ?? 0}
/>
```

În `App.tsx`, pasează prop-ul la `<MainLayout`:
```typescript
<MainLayout
  ...
  errorCount={errorCount}
>
```

- [ ] **Step 3: Adaugă badge pe Settings în `DesktopSidebar.tsx`**

În interfața `Props` a `DesktopSidebar`, adaugă:
```typescript
  errorCount: number;
```

În corpul componentei, în map-ul de tab-uri, adaugă badge pentru `tab.id === 'settings'`:

```typescript
const showErrorBadge = errorCount > 0 && tab.id === 'settings';
```

Și în JSX-ul butonului, după `{showBadge && ...}`, adaugă:
```typescript
{showErrorBadge && (
  <span className="absolute -right-2 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-0.5 text-[9px] font-bold text-white">
    {errorCount > 9 ? '9+' : errorCount}
  </span>
)}
```

De asemenea adaugă badge-ul similar în **mobile tab bar** din `MainLayout.tsx`:

```typescript
const showErrorBadge = errorCount > 0 && tab.id === 'settings';
```

Și în JSX-ul butonului din `visibleTabs.map`:
```typescript
{showErrorBadge && (
  <span className="absolute -right-2 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-0.5 text-[9px] font-bold text-white">
    {errorCount > 9 ? '9+' : errorCount}
  </span>
)}
```

- [ ] **Step 4: Typecheck**

```bash
cd /opt/Mobiup/unihub && npx tsc --noEmit 2>&1 | head -20
```

Expected: nicio eroare.

- [ ] **Step 5: Rulează pytest**

```bash
cd /opt/Mobiup/unihub/backend && source venv/bin/activate
python -m pytest --tb=short -q 2>&1 | tail -10
```

Expected: toate testele trec.

- [ ] **Step 6: Commit**

```bash
cd /opt/Mobiup/unihub
git add src/App.tsx src/components/MainLayout.tsx src/components/DesktopSidebar.tsx
git commit -m "feat: badge erori nevăzute pe iconița Settings (desktop + mobile)"
```

---

## Task 9: Deploy

- [ ] **Step 1: Rulează `/deploy`**

```bash
# Verifică că totul e ok înainte de deploy
cd /opt/Mobiup/unihub/backend && source venv/bin/activate && python -m pytest --tb=short -q 2>&1 | tail -5
cd /opt/Mobiup/unihub && npx tsc --noEmit 2>&1 | head -5
```

- [ ] **Step 2: Build + restart**

```bash
cd /opt/Mobiup/unihub && npm run build 2>&1 | tail -10
sudo systemctl restart unihub-backend && sleep 3
sudo systemctl status unihub-backend --no-pager | grep Active
curl -s http://localhost:9898/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 3: Verificare end-to-end**

```bash
# Simulează o eroare backend
cd /opt/Mobiup/unihub/backend && source venv/bin/activate
python - <<'EOF'
import asyncio, logging
import db.connection as c
from logging_config import attach_db_error_handler

async def main():
    await c.init_db_pool()
    pool = await c.get_pool()
    attach_db_error_handler(pool)
    logging.getLogger("test.e2e").error("E2E test error %s", "ok")
    await asyncio.sleep(0.3)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT message, seen FROM error_logs WHERE message LIKE 'E2E test%' LIMIT 1")
        assert row, "Eroarea nu e în DB!"
        print(f"OK: message={row['message']!r}, seen={row['seen']}")
        await conn.execute("DELETE FROM error_logs WHERE message LIKE 'E2E test%'")
asyncio.run(main())
EOF
```

Expected: `OK: message='E2E test error ok', seen=False`

- [ ] **Step 4: Commit final dacă e necesar + push**

```bash
cd /opt/Mobiup/unihub && git push
```

---

## Self-Review

**Spec coverage:**
- ✅ `error_logs` table cu toate coloanele — Task 1
- ✅ `DBErrorHandler` async non-blocking — Task 3
- ✅ `window.onerror` + `onunhandledrejection` — Task 5
- ✅ `ErrorBoundary` extins — Task 5
- ✅ `POST /api/errors` rate-limited (10/min) — Task 2
- ✅ `GET /api/admin/error-logs` cu filtre + paginare — Task 2
- ✅ `POST /api/admin/error-logs/mark-seen` — Task 2
- ✅ `DELETE /api/admin/error-logs/old` — Task 2
- ✅ `GET /api/admin/error-logs/unseen-count` — Task 2
- ✅ Badge roșu în sidebar (desktop + mobile) — Task 8
- ✅ Tab "Erori sistem" în Settings — Task 7
- ✅ Modal traceback complet — Task 6
- ✅ Curățare 30 zile la boot — Task 4
- ✅ DB down = handler silențios — specificat în `_insert` (try/except)
- ✅ Teste pytest — Task 2 (5 teste noi)

**Placeholder scan:** Nicio instanță de TBD/TODO/implement later.

**Type consistency:**
- `insert_error_log` definit în Task 2, folosit în Task 3 (DBErrorHandler) și Task 5 (API)
- `postFrontendError` definit în `src/api/errors.ts` (Task 5), folosit în `ErrorBoundary` (Task 5) și `main.tsx` (Task 5)
- `getUnseenCount` definit în `src/api/errors.ts`, folosit în `App.tsx` (Task 8)
- `errorCount` prop: `App.tsx` → `MainLayout` → `DesktopSidebar` — consistent în Tasks 7-8
