from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

from db.connection import get_pool

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
    extra: dict[str, Any] | None = None


# ── Service functions (testabile direct) ─────────────────────────────────────

async def insert_error_log(conn: Any, data: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO error_logs
            (source, level, message, traceback, path, extra)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, ts::text, source, level, message, traceback, path,
                  extra::text, seen
        """,
        data["source"],
        data["level"],
        data["message"][:2000],
        (data.get("traceback") or "")[:4000] or None,
        data.get("path"),
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
               extra::text, seen
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
    parts = result.split()
    return int(parts[1]) if len(parts) == 2 else 0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/api/errors")
async def ingest_frontend_error(
    request: Request,
    payload: FrontendErrorPayload,
) -> Response:
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
            "extra": payload.extra,
        })
    return Response(status_code=204)


@router.get("/api/admin/error-logs")
async def get_error_logs(
    source: str | None = None,
    level: str | None = None,
    seen: bool | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await list_error_logs(conn, source, level, seen, from_date, to_date, page, page_size)


@router.get("/api/admin/error-logs/unseen-count")
async def unseen_count() -> dict[str, int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return {"count": await get_unseen_count(conn)}


@router.post("/api/admin/error-logs/mark-seen")
async def mark_seen() -> Response:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await mark_all_seen(conn)
    return Response(status_code=204)


@router.delete("/api/admin/error-logs/old")
async def delete_old(
    days: int = 30,
) -> dict[str, int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        deleted = await delete_old_logs(conn, days)
    return {"deleted": deleted}
