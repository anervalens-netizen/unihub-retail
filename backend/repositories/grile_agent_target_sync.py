from __future__ import annotations

import json
from typing import Any, Literal

import asyncpg


SyncMode = Literal["dry_run", "sync"]


_COLUMNS = """
    id, run_month, mode, status, job_id, requested_by_sub,
    before_sha256, after_sha256, before_count, after_count,
    diff, error_message, started_at, heartbeat_at, finished_at, created_at
"""


def to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    if isinstance(payload.get("diff"), str):
        payload["diff"] = json.loads(payload["diff"])
    return payload


class GrileAgentTargetSyncRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def reserve(
        self,
        *,
        month: str,
        mode: SyncMode,
        requested_by_sub: str,
    ) -> tuple[str, dict[str, Any]]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE grile_agent_target_sync_runs
                    SET status = 'failed',
                        error_message = 'Rezervare expirata inainte de finalizare',
                        heartbeat_at = now(),
                        finished_at = now()
                    WHERE run_month = $1
                      AND status IN ('queued', 'running')
                      AND COALESCE(heartbeat_at, started_at, created_at)
                          < now() - interval '2 hours'
                    """,
                    month,
                )
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO grile_agent_target_sync_runs (
                        run_month, mode, requested_by_sub, heartbeat_at
                    )
                    VALUES ($1, $2, $3, now())
                    ON CONFLICT (run_month, mode)
                        WHERE status IN ('queued', 'running')
                    DO NOTHING
                    RETURNING {_COLUMNS}
                    """,
                    month,
                    mode,
                    requested_by_sub,
                )
                if row is not None:
                    payload = to_dict(row)
                    assert payload is not None
                    return "enqueued", payload
                active = await conn.fetchrow(
                    f"""
                    SELECT {_COLUMNS}
                    FROM grile_agent_target_sync_runs
                    WHERE run_month = $1
                      AND mode = $2
                      AND status IN ('queued', 'running')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    month,
                    mode,
                )
        payload = to_dict(active)
        if payload is None:
            raise RuntimeError("Failed to reserve Grile target sync")
        return "already_running", payload

    async def attach_job(self, operation_id: int, job_id: str) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE grile_agent_target_sync_runs
                SET job_id = $2, heartbeat_at = now()
                WHERE id = $1 AND status = 'queued'
                RETURNING id
                """,
                operation_id,
                job_id,
            )
        return row is not None

    async def start(self, operation_id: int) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE grile_agent_target_sync_runs
                SET status = 'running', started_at = now(), heartbeat_at = now()
                WHERE id = $1 AND status = 'queued'
                RETURNING {_COLUMNS}
                """,
                operation_id,
            )
        return to_dict(row)

    async def finish(
        self,
        operation_id: int,
        *,
        before_sha256: str,
        after_sha256: str,
        before_count: int,
        after_count: int,
        diff: dict[str, Any],
    ) -> bool:
        async with self.pool.acquire() as conn:
            return await self.finish_on_connection(
                conn,
                operation_id,
                before_sha256=before_sha256,
                after_sha256=after_sha256,
                before_count=before_count,
                after_count=after_count,
                diff=diff,
            )

    async def finish_on_connection(
        self,
        conn: asyncpg.Connection,
        operation_id: int,
        *,
        before_sha256: str,
        after_sha256: str,
        before_count: int,
        after_count: int,
        diff: dict[str, Any],
    ) -> bool:
        row = await conn.fetchrow(
            """
            UPDATE grile_agent_target_sync_runs
            SET status = 'completed',
                before_sha256 = $2,
                after_sha256 = $3,
                before_count = $4,
                after_count = $5,
                diff = $6::jsonb,
                heartbeat_at = now(),
                finished_at = now(),
                error_message = NULL
            WHERE id = $1 AND status = 'running'
            RETURNING id
            """,
            operation_id,
            before_sha256,
            after_sha256,
            before_count,
            after_count,
            json.dumps(diff, ensure_ascii=False),
        )
        return row is not None

    async def fail(self, operation_id: int, error_message: str) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE grile_agent_target_sync_runs
                SET status = 'failed',
                    error_message = $2,
                    heartbeat_at = now(),
                    finished_at = now()
                WHERE id = $1 AND status IN ('queued', 'running')
                RETURNING id
                """,
                operation_id,
                error_message,
            )
        return row is not None

    async def fail_queued(self, operation_id: int, error_message: str) -> bool:
        """Fail only a reservation that the worker has not claimed yet."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE grile_agent_target_sync_runs
                SET status = 'failed',
                    error_message = $2,
                    heartbeat_at = now(),
                    finished_at = now()
                WHERE id = $1 AND status = 'queued'
                RETURNING id
                """,
                operation_id,
                error_message,
            )
        return row is not None

    async def get(self, operation_id: int) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM grile_agent_target_sync_runs WHERE id = $1",
                operation_id,
            )
        return to_dict(row)
