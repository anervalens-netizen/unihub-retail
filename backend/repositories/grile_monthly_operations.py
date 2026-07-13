"""Persistence boundary for monthly Grile operation lifecycle transitions."""

from __future__ import annotations

import json
from typing import Any

import asyncpg

from services.grile_monthly_state import (
    MonthlyOperationStartResult,
    operation_start_result,
    terminal_operation_status,
)


def _operation_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    if data.get("result") and isinstance(data["result"], str):
        data["result"] = json.loads(data["result"])
    return data


async def attach_job(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    job_id: str,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_operations
            SET job_id = $2, heartbeat_at = now()
            WHERE id = $1 AND status = 'queued'
            RETURNING id
            """,
            operation_id,
            job_id,
        )
    return row is not None


async def start(
    pool: asyncpg.Pool,
    operation_id: int,
) -> MonthlyOperationStartResult:
    async with pool.acquire() as conn:
        started = await conn.fetchrow(
            """
            UPDATE grile_monthly_operations
            SET status = 'running',
                started_at = COALESCE(started_at, now()),
                heartbeat_at = now()
            WHERE id = $1 AND status = 'queued'
            RETURNING *
            """,
            operation_id,
        )
        if started is not None:
            return operation_start_result(
                operation_id=operation_id,
                operation=_operation_to_dict(started),
                transition_claimed=True,
            )

        current = await conn.fetchrow(
            "SELECT * FROM grile_monthly_operations WHERE id = $1",
            operation_id,
        )

    return operation_start_result(
        operation_id=operation_id,
        operation=_operation_to_dict(current),
        transition_claimed=False,
    )


async def heartbeat(pool: asyncpg.Pool, operation_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE grile_monthly_operations
            SET heartbeat_at = now()
            WHERE id = $1 AND status = 'running'
            """,
            operation_id,
        )


async def finish(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    result: dict[str, Any],
    error_message: str | None = None,
) -> bool:
    status = terminal_operation_status(result)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_operations
            SET status = $2,
                result = $3::jsonb,
                error_message = $4,
                finished_at = now(),
                heartbeat_at = now()
            WHERE id = $1 AND status = 'running'
            RETURNING id
            """,
            operation_id,
            status,
            json.dumps(result, ensure_ascii=False),
            error_message,
        )
    return row is not None


async def fail(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    error_message: str,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_operations
            SET status = 'failed',
                error_message = $2,
                finished_at = now(),
                heartbeat_at = now()
            WHERE id = $1 AND status IN ('queued', 'running')
            RETURNING id
            """,
            operation_id,
            error_message,
        )
    return row is not None
