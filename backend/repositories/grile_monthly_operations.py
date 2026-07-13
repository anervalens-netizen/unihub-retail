"""Persistence boundary for monthly Grile operation lifecycle transitions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Sequence

import asyncpg

from services.grile_monthly_state import (
    GrileMonthlyRetryBlockedError,
    MonthlyOperationReservation,
    MonthlyOperationStartResult,
    operation_start_result,
    terminal_operation_status,
)


_OPERATION_COLUMNS = """
    id, op, closing_month, only_filter, dry_run, status, job_id,
    triggered_by_email, result, error_message, started_at, heartbeat_at,
    finished_at, created_at
"""

_RESET_ITEM_COLUMNS = """
    id, operation_id, closing_month, next_month, site_code, sheet_id,
    company, store, status, ranges, error_message, started_at, completed_at,
    updated_at, created_at
"""


@dataclass(frozen=True)
class ResetItemInput:
    site_code: str
    sheet_id: str
    company: str
    store: str


def operation_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    if data.get("result") and isinstance(data["result"], str):
        data["result"] = json.loads(data["result"])
    return data


async def reserve(
    pool: asyncpg.Pool,
    *,
    op: str,
    month: str,
    only: str | None,
    dry_run: bool,
    triggered_by_email: str | None,
) -> MonthlyOperationReservation:
    normalized_only = only.strip() if only and only.strip() else None
    reservation: MonthlyOperationReservation | None = None
    blocked_message: str | None = None
    operation_id: int | None = None

    async with pool.acquire() as conn:
        async with conn.transaction():
            stale_ops = await conn.fetch(
                """
                SELECT id
                FROM grile_monthly_operations
                WHERE closing_month = $1
                  AND status IN ('queued', 'running')
                  AND COALESCE(heartbeat_at, started_at, created_at)
                      < now() - interval '2 hours'
                """,
                month,
            )
            stale_ids = [int(row["id"]) for row in stale_ops]
            if stale_ids:
                await conn.execute(
                    """
                    UPDATE grile_monthly_reset_items
                    SET status = 'uncertain',
                        error_message = COALESCE(
                            error_message,
                            'Operatia a expirat inainte de confirmarea efectului Google; verifica manual grila.'
                        ),
                        updated_at = now()
                    WHERE operation_id = ANY($1::int[])
                      AND status IN ('pending', 'running')
                    """,
                    stale_ids,
                )
                await conn.execute(
                    """
                    UPDATE grile_monthly_operations
                    SET status = 'failed',
                        error_message = 'Rezervare expirata inainte de finalizare',
                        finished_at = now(),
                        heartbeat_at = now()
                    WHERE id = ANY($1::int[])
                    """,
                    stale_ids,
                )

            active = await conn.fetchrow(
                f"""
                SELECT {_OPERATION_COLUMNS}
                FROM grile_monthly_operations
                WHERE closing_month = $1 AND status IN ('queued', 'running')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                month,
            )
            if active is not None:
                reservation = MonthlyOperationReservation(
                    status="already_running",
                    operation_id=int(active["id"]),
                    job_id=active["job_id"],
                    operation=operation_to_dict(active),
                )

            if reservation is None and op == "reset" and not dry_run:
                uncertain = await conn.fetchrow(
                    """
                    SELECT site_code, company, store
                    FROM grile_monthly_reset_items
                    WHERE closing_month = $1 AND status = 'uncertain'
                    ORDER BY company, store
                    LIMIT 1
                    """,
                    month,
                )
                if uncertain is not None:
                    blocked_message = (
                        "Resetul live nu poate fi reluat automat: exista checkpoint "
                        f"uncertain pentru {uncertain['company']}/{uncertain['store']} "
                        f"({uncertain['site_code']}). Verifica manual in Google Sheets."
                    )

                if blocked_message is None:
                    completed = await conn.fetchrow(
                        f"""
                        SELECT {_OPERATION_COLUMNS}
                        FROM grile_monthly_operations
                        WHERE closing_month = $1
                          AND op = 'reset'
                          AND dry_run = false
                          AND status = 'completed'
                          AND COALESCE(only_filter, '') = COALESCE($2, '')
                        ORDER BY finished_at DESC NULLS LAST, created_at DESC
                        LIMIT 1
                        """,
                        month,
                        normalized_only,
                    )
                    if completed is not None:
                        reservation = MonthlyOperationReservation(
                            status="already_completed",
                            operation_id=int(completed["id"]),
                            job_id=completed["job_id"],
                            operation=operation_to_dict(completed),
                        )

            if reservation is None and blocked_message is None:
                operation_id = await conn.fetchval(
                    """
                    INSERT INTO grile_monthly_operations (
                        op, closing_month, only_filter, dry_run,
                        status, triggered_by_email, heartbeat_at
                    )
                    VALUES ($1, $2, $3, $4, 'queued', $5, now())
                    ON CONFLICT (closing_month)
                        WHERE status IN ('queued', 'running')
                    DO NOTHING
                    RETURNING id
                    """,
                    op,
                    month,
                    normalized_only,
                    dry_run,
                    triggered_by_email,
                )
                if operation_id is None:
                    active = await conn.fetchrow(
                        f"""
                        SELECT {_OPERATION_COLUMNS}
                        FROM grile_monthly_operations
                        WHERE closing_month = $1 AND status IN ('queued', 'running')
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        month,
                    )
                    if active is None:
                        raise RuntimeError("Failed to reserve grile monthly operation")
                    reservation = MonthlyOperationReservation(
                        status="already_running",
                        operation_id=int(active["id"]),
                        job_id=active["job_id"],
                        operation=operation_to_dict(active),
                    )

    if blocked_message is not None:
        raise GrileMonthlyRetryBlockedError(blocked_message)
    if reservation is not None:
        return reservation
    if operation_id is None:
        raise RuntimeError("Failed to reserve grile monthly operation")
    return MonthlyOperationReservation(status="enqueued", operation_id=int(operation_id))


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
            f"""
            UPDATE grile_monthly_operations
            SET status = 'running',
                started_at = COALESCE(started_at, now()),
                heartbeat_at = now()
            WHERE id = $1 AND status = 'queued'
            RETURNING {_OPERATION_COLUMNS}
            """,
            operation_id,
        )
        if started is not None:
            return operation_start_result(
                operation_id=operation_id,
                operation=operation_to_dict(started),
                transition_claimed=True,
            )

        current = await conn.fetchrow(
            f"SELECT {_OPERATION_COLUMNS} FROM grile_monthly_operations WHERE id = $1",
            operation_id,
        )

    return operation_start_result(
        operation_id=operation_id,
        operation=operation_to_dict(current),
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


async def ensure_reset_items(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    closing_month: str,
    next_month: str,
    entries: Sequence[ResetItemInput],
    ranges: Sequence[str],
) -> None:
    encoded_ranges = json.dumps(list(ranges), ensure_ascii=False)
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO grile_monthly_reset_items (
                operation_id, closing_month, next_month, site_code, sheet_id,
                company, store, status, ranges
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', $8::jsonb)
            ON CONFLICT (operation_id, site_code) DO NOTHING
            """,
            [
                (
                    operation_id,
                    closing_month,
                    next_month,
                    entry.site_code,
                    entry.sheet_id,
                    entry.company,
                    entry.store,
                    encoded_ranges,
                )
                for entry in entries
            ],
        )


async def get_previous_completed_reset_item(
    pool: asyncpg.Pool,
    *,
    closing_month: str,
    site_code: str,
) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            f"""
            SELECT {_RESET_ITEM_COLUMNS}
            FROM grile_monthly_reset_items
            WHERE closing_month = $1
              AND site_code = $2
              AND status = 'completed'
            ORDER BY completed_at DESC NULLS LAST, updated_at DESC
            LIMIT 1
            """,
            closing_month,
            site_code,
        )


async def claim_reset_item(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_reset_items
            SET status = 'running',
                started_at = COALESCE(started_at, now()),
                updated_at = now()
            WHERE operation_id = $1 AND site_code = $2 AND status = 'pending'
            RETURNING id
            """,
            operation_id,
            site_code,
        )
    return row is not None


async def finish_reset_item(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    status: Literal["completed", "error", "skipped"],
    error_message: str | None = None,
) -> bool:
    expected_status = "pending" if status == "skipped" else "running"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_reset_items
            SET status = $3,
                error_message = $4,
                completed_at = CASE WHEN $3 IN ('completed', 'skipped') THEN now() ELSE completed_at END,
                updated_at = now()
            WHERE operation_id = $1 AND site_code = $2 AND status = $5
            RETURNING id
            """,
            operation_id,
            site_code,
            status,
            error_message,
            expected_status,
        )
    return row is not None
