"""Reservation and enqueue persistence for monthly Grile operations."""

from __future__ import annotations

from typing import Any

import asyncpg

from grile.domain.monthly_state import (
    GrileMonthlyRetryBlockedError,
    MonthlyOperationReservation,
)
from repositories.grile_monthly_repository_types import (
    OPERATION_COLUMNS as _OPERATION_COLUMNS,
    operation_to_dict,
)


async def reserve(
    pool: asyncpg.Pool,
    *,
    op: str,
    month: str,
    only: str | None,
    dry_run: bool,
    requested_by_sub: str,
    approved_manifest_id: int | None = None,
) -> MonthlyOperationReservation:
    if not requested_by_sub or not requested_by_sub.strip():
        raise ValueError("requested_by_sub is required")
    normalized_only = only.strip() if only and only.strip() else None
    reservation: MonthlyOperationReservation | None = None
    blocked_message: str | None = None
    operation_id: int | None = None
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _fence_stale_operation(conn, month)
            reservation = await _active_reservation(conn, month)
            if reservation is None and op == "reset" and not dry_run:
                reservation, blocked_message = await _live_reset_gate(
                    conn,
                    month,
                    normalized_only,
                    approved_manifest_id,
                )
            if reservation is None and blocked_message is None:
                operation_id, reservation = await _insert_reservation(
                    conn,
                    op=op,
                    month=month,
                    normalized_only=normalized_only,
                    dry_run=dry_run,
                    requested_by_sub=requested_by_sub,
                    approved_manifest_id=approved_manifest_id,
                )
    if blocked_message is not None:
        raise GrileMonthlyRetryBlockedError(blocked_message)
    if reservation is not None:
        return reservation
    if operation_id is None:
        raise RuntimeError("Failed to reserve grile monthly operation")
    return MonthlyOperationReservation(status="enqueued", operation_id=int(operation_id))


async def _fence_stale_operation(conn: asyncpg.Connection, month: str) -> None:
    stale = await conn.fetchrow(
        """
        SELECT id
        FROM grile_monthly_operations
        WHERE closing_month = $1
          AND status = 'running'
          AND (
              execution_lease_until <= now()
              OR (
                  execution_lease_until IS NULL
                  AND heartbeat_at < now() - interval '2 hours'
              )
          )
        ORDER BY created_at DESC
        LIMIT 1
        FOR UPDATE
        """,
        month,
    )
    if stale is None:
        return
    stale_id = int(stale["id"])
    await conn.execute(
        """
        UPDATE grile_monthly_reset_items
        SET status = 'uncertain',
            checkpoint_phase = 'recovery_required',
            recovery_code = 'recovery_required',
            rollback_status = CASE
                WHEN rollback_status = 'restored' THEN rollback_status
                ELSE 'failed'
            END,
            error_message = COALESCE(error_message, 'stale_operation_recovery_required'),
            updated_at = now()
        WHERE operation_id = $1
          AND status IN ('running', 'completed', 'uncertain')
          AND rollback_status IS DISTINCT FROM 'restored'
        """,
        stale_id,
    )
    await conn.execute(
        """
        UPDATE grile_monthly_operations
        SET status = 'failed',
            error_message = 'stale_operation_recovery_required',
            reconciliation_classification = 'recovery_required',
            reconciled_at = now(),
            finished_at = now(),
            heartbeat_at = now(),
            execution_lease_until = NULL
        WHERE id = $1 AND status = 'running'
        """,
        stale_id,
    )


async def _active_reservation(
    conn: asyncpg.Connection,
    month: str,
) -> MonthlyOperationReservation | None:
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
    return _reservation_from_row(active, "already_running")


async def _live_reset_gate(
    conn: asyncpg.Connection,
    month: str,
    normalized_only: str | None,
    approved_manifest_id: int | None,
) -> tuple[MonthlyOperationReservation | None, str | None]:
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
    reservation = _reservation_from_row(completed, "already_completed")
    blocked = await _approved_manifest_error(
        conn,
        month,
        approved_manifest_id,
        reservation is not None,
    )
    uncertain = await conn.fetchrow(
        """
        SELECT site_code, company, store
        FROM grile_monthly_reset_items
        WHERE closing_month = $1
          AND (
              status = 'uncertain'
              OR rollback_status = 'failed'
              OR checkpoint_phase = 'legacy_unknown'
              OR recovery_code = 'recovery_required'
          )
        ORDER BY company, store
        LIMIT 1
        """,
        month,
    )
    if reservation is None and uncertain is not None:
        blocked = (
            "Resetul live nu poate fi reluat automat: exista checkpoint "
            f"uncertain pentru {uncertain['company']}/{uncertain['store']} "
            f"({uncertain['site_code']}). Verifica manual in Google Sheets."
        )
    if reservation is None and blocked is None:
        blocked = await _legacy_partial_error(conn, month)
    return reservation, blocked


async def _approved_manifest_error(
    conn: asyncpg.Connection,
    month: str,
    approved_manifest_id: int | None,
    already_completed: bool,
) -> str | None:
    if already_completed:
        return None
    if approved_manifest_id is None:
        return "Resetul live necesita un manifest verificat si aprobat."
    approved = await conn.fetchrow(
        """
        SELECT id
        FROM grile_monthly_manifests
        WHERE id = $1
          AND closing_month = $2
          AND operation = 'archive'
          AND status = 'approved'
          AND error_count = 0
          AND processed_store_count = expected_store_count
          AND processed_agent_count = expected_agent_count
        FOR SHARE
        """,
        approved_manifest_id,
        month,
    )
    if approved is None:
        return "Manifestul selectat nu este verificat si aprobat pentru luna ceruta."
    return None


async def _legacy_partial_error(
    conn: asyncpg.Connection,
    month: str,
) -> str | None:
    legacy_partial = await conn.fetchrow(
        """
        SELECT i.site_code
        FROM grile_monthly_reset_items i
        JOIN grile_monthly_operations o ON o.id = i.operation_id
        WHERE i.closing_month = $1
          AND i.status = 'completed'
          AND o.status <> 'completed'
        ORDER BY i.id
        LIMIT 1
        """,
        month,
    )
    if legacy_partial is None:
        return None
    return (
        "Resetul live nu poate continua automat: exista un efect Google "
        "partial dintr-o operatie anterioara. Verifica si reconciliaza manual."
    )


async def _insert_reservation(
    conn: asyncpg.Connection,
    *,
    op: str,
    month: str,
    normalized_only: str | None,
    dry_run: bool,
    requested_by_sub: str,
    approved_manifest_id: int | None,
) -> tuple[int | None, MonthlyOperationReservation | None]:
    operation_id = await conn.fetchval(
        """
        INSERT INTO grile_monthly_operations (
            op, closing_month, only_filter, dry_run,
            status, requested_by_sub, approved_manifest_id, heartbeat_at
        )
        VALUES ($1, $2, $3, $4, 'queued', $5, $6, now())
        ON CONFLICT (closing_month)
            WHERE status IN ('queued', 'running')
        DO NOTHING
        RETURNING id
        """,
        op,
        month,
        normalized_only,
        dry_run,
        requested_by_sub,
        approved_manifest_id if op == "reset" and not dry_run else None,
    )
    if operation_id is not None:
        await conn.execute(
            """
            INSERT INTO grile_monthly_manifests (
                operation_id, closing_month, operation, status,
                requested_by_sub
            )
            VALUES ($1, $2, $3, 'building', $4)
            """,
            operation_id,
            month,
            op,
            requested_by_sub,
        )
        return int(operation_id), None
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
    reservation = _reservation_from_row(active, "already_running")
    if reservation is None:
        raise RuntimeError("Failed to reserve grile monthly operation")
    return None, reservation


def _reservation_from_row(
    row: asyncpg.Record | None,
    status: str,
) -> MonthlyOperationReservation | None:
    if row is None:
        return None
    return MonthlyOperationReservation(
        status=status,  # type: ignore[arg-type]
        operation_id=int(row["id"]),
        job_id=row["job_id"],
        operation=operation_to_dict(row),
    )


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


async def get_by_job_id(
    pool: asyncpg.Pool,
    job_id: str,
) -> dict[str, Any] | None:
    """Return the durable operation used to reconcile ephemeral ARQ state."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, status, result, error_message
            FROM grile_monthly_operations
            WHERE job_id = $1
            LIMIT 1
            """,
            job_id,
        )
    return operation_to_dict(row)
