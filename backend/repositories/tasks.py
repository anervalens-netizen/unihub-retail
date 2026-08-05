from __future__ import annotations

import json
from typing import Any
import asyncpg


class TasksRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create_task(self, data: dict[str, Any]) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
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

    async def list_tasks(
        self,
        status: str | None,
        assignee: str | None,
        site_code: str | None,
        only_mine: str | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[asyncpg.Record], int]:
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
        async with self.pool.acquire() as conn:
            total = int(
                await conn.fetchval(
                    f"SELECT COUNT(*) FROM tasks {where}",
                    *params,
                )
                or 0
            )
            page_params = [*params, limit, offset]
            rows = await conn.fetch(
                f"""
                SELECT id, title, assignee, site_code, deadline::text, status, source, source_meta,
                       created_at::text, updated_at::text
                FROM tasks
                {where}
                ORDER BY
                    CASE status WHEN 'deschis' THEN 0 WHEN 'in_lucru' THEN 1 ELSE 2 END,
                    deadline ASC NULLS LAST,
                    created_at DESC,
                    id ASC
                LIMIT ${idx} OFFSET ${idx + 1}
                """,
                *page_params,
            )
        return rows, total

    async def update_task(self, task_id: int, data: dict[str, Any]) -> asyncpg.Record | None:
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
            return None

        sets.append("updated_at = now()")
        params.append(task_id)
        
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                f"""
                UPDATE tasks SET {', '.join(sets)}
                WHERE id = ${idx}
                RETURNING id, title, assignee, site_code, deadline::text, status, source, source_meta,
                          created_at::text, updated_at::text
                """,
                *params,
            )

    async def delete_task(self, task_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)
        return result == "DELETE 1"
