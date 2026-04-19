from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from db.connection import get_pool

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    assignee: str | None = None
    site_code: str | None = None
    deadline: str | None = None
    status: str = "deschis"
    source: str = "manual"
    source_meta: dict | None = None


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    assignee: str | None = None
    site_code: str | None = None
    deadline: str | None = None
    status: str | None = None


async def create_task(conn: Any, data: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO tasks (title, assignee, site_code, deadline, status, source, source_meta)
        VALUES ($1, $2, $3, $4::text::date, $5, $6, $7::jsonb)
        RETURNING id, title, assignee, site_code, deadline::text, status, source, source_meta,
                  created_at::text, updated_at::text
        """,
        data["title"],
        data.get("assignee"),
        data.get("site_code"),
        data.get("deadline"),
        data.get("status", "deschis"),
        data.get("source", "manual"),
        json.dumps(data["source_meta"]) if data.get("source_meta") else None,
    )
    return dict(row)


async def list_tasks(
    conn: Any,
    status: str | None,
    assignee: str | None,
    site_code: str | None,
    only_mine: str | None = None,
) -> list[dict]:
    clauses = []
    params: list[Any] = []
    idx = 1

    if only_mine:
        clauses.append(f"assignee ILIKE ${idx}")
        params.append(only_mine)
        idx += 1
    if status:
        clauses.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if assignee:
        clauses.append(f"assignee ILIKE ${idx}")
        params.append(f"%{assignee}%")
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
        ORDER BY
            CASE status WHEN 'deschis' THEN 0 WHEN 'in_lucru' THEN 1 ELSE 2 END,
            deadline ASC NULLS LAST,
            created_at DESC
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def update_task(conn: Any, task_id: int, data: dict) -> dict:
    sets = []
    params: list[Any] = []
    idx = 1

    if "title" in data and data["title"] is not None:
        sets.append(f"title = ${idx}"); params.append(data["title"]); idx += 1
    if "assignee" in data:
        sets.append(f"assignee = ${idx}"); params.append(data["assignee"]); idx += 1
    if "site_code" in data:
        sets.append(f"site_code = ${idx}"); params.append(data["site_code"]); idx += 1
    if "deadline" in data:
        sets.append(f"deadline = ${idx}::text::date"); params.append(data["deadline"]); idx += 1
    if "status" in data and data["status"] is not None:
        sets.append(f"status = ${idx}"); params.append(data["status"]); idx += 1

    if not sets:
        raise HTTPException(status_code=400, detail="Niciun câmp de actualizat")

    sets.append("updated_at = now()")
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
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await list_tasks(conn, status, assignee, site_code)


@router.post("")
async def post_task(body: TaskCreate):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await create_task(conn, body.model_dump())


@router.patch("/{task_id}")
async def patch_task(task_id: int, body: TaskUpdate):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await update_task(conn, task_id, body.model_dump(exclude_none=True))


@router.delete("/{task_id}")
async def remove_task(task_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        deleted = await delete_task(conn, task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Task negăsit")
        return {"ok": True}
