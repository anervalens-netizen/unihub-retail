"""Persistence boundary for monthly Grile operation lifecycle transitions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Sequence
from uuid import uuid4

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
    triggered_by_email, requested_by_sub, approved_manifest_id, result,
    error_message, started_at, heartbeat_at, finished_at, created_at,
    execution_owner, execution_epoch, execution_lease_until,
    reconciliation_classification, reconciled_at, alerted_at
"""

_RESET_ITEM_COLUMNS = """
    id, operation_id, closing_month, next_month, site_code, sheet_id,
    company, store, status, ranges, error_message, started_at, completed_at,
    backup_path, backup_sha256, rollback_status, restored_at, updated_at,
    created_at, checkpoint_phase, fence_epoch, destructive_intent_at,
    verified_at, reconciled_at, recovery_code
"""

_MANIFEST_COLUMNS = """
    id, operation_id, closing_month, operation, status,
    expected_store_count, processed_store_count, expected_agent_count,
    processed_agent_count, error_count, control_totals, artifacts,
    source_backups, manifest, manifest_sha256, requested_by_sub,
    approved_by_sub, approved_at, error_code, verified_at, consumed_at,
    updated_at, created_at
"""


@dataclass(frozen=True)
class ResetItemInput:
    site_code: str
    sheet_id: str
    company: str
    store: str
    ranges: Sequence[str]


@dataclass(frozen=True)
class MonthlyExecutionLease:
    operation_id: int
    execution_owner: str
    execution_epoch: int
    execution_lease_until: Any


EXECUTION_LEASE_SECONDS = 300


def operation_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    if data.get("result") and isinstance(data["result"], str):
        data["result"] = json.loads(data["result"])
    return data


def manifest_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key in ("control_totals", "artifacts", "source_backups", "manifest"):
        if data.get(key) is not None and isinstance(data[key], str):
            data[key] = json.loads(data[key])
    return data


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
    normalized_only = only.strip() if only and only.strip() else None
    reservation: MonthlyOperationReservation | None = None
    blocked_message: str | None = None
    operation_id: int | None = None

    if not requested_by_sub or not requested_by_sub.strip():
        raise ValueError("requested_by_sub is required")

    async with pool.acquire() as conn:
        async with conn.transaction():
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
            if stale is not None:
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

                if reservation is None and approved_manifest_id is None:
                    blocked_message = "Resetul live necesita un manifest verificat si aprobat."
                elif reservation is None:
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
                        blocked_message = "Manifestul selectat nu este verificat si aprobat pentru luna ceruta."

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
                    blocked_message = (
                        "Resetul live nu poate fi reluat automat: exista checkpoint "
                        f"uncertain pentru {uncertain['company']}/{uncertain['store']} "
                        f"({uncertain['site_code']}). Verifica manual in Google Sheets."
                    )

                if reservation is None and blocked_message is None:
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
                    if legacy_partial is not None:
                        blocked_message = (
                            "Resetul live nu poate continua automat: exista un efect Google "
                            "partial dintr-o operatie anterioara. Verifica si reconciliaza manual."
                        )

            if reservation is None and blocked_message is None:
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


async def start(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    execution_owner: str | None = None,
    lease_seconds: int = EXECUTION_LEASE_SECONDS,
) -> MonthlyOperationStartResult:
    owner = execution_owner or uuid4().hex
    if not owner.strip():
        raise ValueError("execution_owner is required")
    async with pool.acquire() as conn:
        async with conn.transaction():
            started = await conn.fetchrow(
                f"""
                UPDATE grile_monthly_operations AS operation
                SET status = 'running',
                    started_at = COALESCE(operation.started_at, now()),
                    heartbeat_at = now(),
                    execution_owner = $2,
                    execution_epoch = operation.execution_epoch + 1,
                    execution_lease_until = now() + ($3 * interval '1 second'),
                    reconciliation_classification = NULL,
                    reconciled_at = NULL
                WHERE operation.id = $1
                  AND operation.status = 'queued'
                  AND NULLIF(btrim(operation.requested_by_sub), '') IS NOT NULL
                  AND EXISTS (
                      SELECT 1
                      FROM grile_monthly_manifests AS manifest
                      WHERE manifest.operation_id = operation.id
                        AND manifest.status = 'building'
                        AND manifest.requested_by_sub = operation.requested_by_sub
                  )
                RETURNING {_OPERATION_COLUMNS}
                """,
                operation_id,
                owner,
                lease_seconds,
            )
            if started is not None:
                return operation_start_result(
                    operation_id=operation_id,
                    operation=operation_to_dict(started),
                    transition_claimed=True,
                )

            # Reservations created before the subject/manifest contract cannot
            # be authorized safely. Fail them atomically while still queued so
            # a rolling-deploy delivery cannot remain active until stale cleanup.
            invalid = await conn.fetchrow(
                f"""
                UPDATE grile_monthly_operations AS operation
                SET status = 'failed',
                    error_message = 'legacy_operation_missing_identity_or_manifest',
                    finished_at = now(),
                    heartbeat_at = now()
                WHERE operation.id = $1
                  AND operation.status = 'queued'
                  AND (
                      NULLIF(btrim(operation.requested_by_sub), '') IS NULL
                      OR NOT EXISTS (
                          SELECT 1
                          FROM grile_monthly_manifests AS manifest
                          WHERE manifest.operation_id = operation.id
                            AND manifest.status = 'building'
                            AND manifest.requested_by_sub = operation.requested_by_sub
                      )
                  )
                RETURNING {_OPERATION_COLUMNS}
                """,
                operation_id,
            )
            current = invalid
            if current is None:
                current = await conn.fetchrow(
                    f"SELECT {_OPERATION_COLUMNS} FROM grile_monthly_operations WHERE id = $1",
                    operation_id,
                )

    return operation_start_result(
        operation_id=operation_id,
        operation=operation_to_dict(current),
        transition_claimed=False,
    )


async def heartbeat(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    execution_owner: str | None = None,
    execution_epoch: int | None = None,
    lease_seconds: int = EXECUTION_LEASE_SECONDS,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_operations
            SET heartbeat_at = now(),
                execution_lease_until = now() + ($4 * interval '1 second')
            WHERE id = $1
              AND status = 'running'
              AND ($2::text IS NULL OR execution_owner = $2)
              AND ($3::bigint IS NULL OR execution_epoch = $3)
              AND ($2::text IS NULL OR execution_lease_until IS NULL OR execution_lease_until > now())
            RETURNING id
            """,
            operation_id,
            execution_owner,
            execution_epoch,
            lease_seconds,
        )
    return row is not None


async def finish(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    result: dict[str, Any],
    error_message: str | None = None,
    execution_owner: str | None = None,
    execution_epoch: int | None = None,
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
            WHERE id = $1
              AND status = 'running'
              AND ($5::text IS NULL OR execution_owner = $5)
              AND ($6::bigint IS NULL OR execution_epoch = $6)
              AND ($5::text IS NULL OR execution_lease_until IS NULL OR execution_lease_until > now())
            RETURNING id
            """,
            operation_id,
            status,
            json.dumps(result, ensure_ascii=False),
            error_message,
            execution_owner,
            execution_epoch,
        )
    return row is not None


async def finish_reset_success(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    result: dict[str, Any],
    reset_manifest: dict[str, Any],
    manifest_id: int,
    expected_manifest_sha256: str,
    consumed_manifest: dict[str, Any],
    execution_owner: str | None = None,
    execution_epoch: int | None = None,
) -> dict[str, Any]:
    expected = reset_manifest.get("expected") or {}
    processed = reset_manifest.get("processed") or {}
    async with pool.acquire() as conn:
        async with conn.transaction():
            reset_record = await conn.fetchrow(
                f"""
                UPDATE grile_monthly_manifests
                SET status = $2,
                    expected_store_count = $3,
                    processed_store_count = $4,
                    expected_agent_count = $5,
                    processed_agent_count = $6,
                    error_count = $7,
                    control_totals = $8::jsonb,
                    artifacts = $9::jsonb,
                    source_backups = $10::jsonb,
                    manifest = $11::jsonb,
                    manifest_sha256 = $12,
                    error_code = NULL,
                    verified_at = now(),
                    updated_at = now()
                WHERE operation_id = $1
                  AND operation = 'reset'
                  AND status = 'building'
                RETURNING {_MANIFEST_COLUMNS}
                """,
                operation_id,
                reset_manifest.get("status"),
                int(expected.get("stores", 0)),
                int(processed.get("stores", 0)),
                int(expected.get("agents", 0)),
                int(processed.get("agents", 0)),
                int(reset_manifest.get("error_count", 0)),
                json.dumps(reset_manifest.get("control_totals", {}), ensure_ascii=False),
                json.dumps(reset_manifest.get("artifacts", []), ensure_ascii=False),
                json.dumps(reset_manifest.get("source_backups", []), ensure_ascii=False),
                json.dumps(reset_manifest, ensure_ascii=False),
                reset_manifest.get("manifest_sha256"),
            )
            if reset_record is None:
                raise RuntimeError("Reset manifest lost its building lease")
            operation = await conn.fetchrow(
                """
                UPDATE grile_monthly_operations
                SET status = 'completed',
                    result = $2::jsonb,
                    error_message = NULL,
                    finished_at = now(),
                    heartbeat_at = now()
                WHERE id = $1
                  AND op = 'reset'
                  AND dry_run = false
                  AND status = 'running'
                  AND approved_manifest_id = $3
                  AND ($4::text IS NULL OR execution_owner = $4)
                  AND ($5::bigint IS NULL OR execution_epoch = $5)
                  AND ($4::text IS NULL OR execution_lease_until IS NULL OR execution_lease_until > now())
                RETURNING id
                """,
                operation_id,
                json.dumps(result, ensure_ascii=False),
                manifest_id,
                execution_owner,
                execution_epoch,
            )
            if operation is None:
                raise RuntimeError("Reset operation lost its completion lease")
            consumed = await conn.fetchrow(
                """
                UPDATE grile_monthly_manifests
                SET status = 'consumed',
                    consumed_at = now(),
                    manifest = $4::jsonb,
                    manifest_sha256 = $5,
                    updated_at = now()
                WHERE id = $1
                  AND status = 'approved'
                  AND manifest_sha256 = $2
                  AND closing_month = (
                      SELECT closing_month
                      FROM grile_monthly_operations
                      WHERE id = $3
                  )
                RETURNING id
                """,
                manifest_id,
                expected_manifest_sha256,
                operation_id,
                json.dumps(consumed_manifest, ensure_ascii=False),
                consumed_manifest.get("manifest_sha256"),
            )
            if consumed is None:
                raise RuntimeError("Approved manifest lost its consumption lease")
    converted = manifest_to_dict(reset_record)
    if converted is None:
        raise RuntimeError("Reset manifest disappeared after commit")
    return converted


async def fail(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    error_message: str,
    execution_owner: str | None = None,
    execution_epoch: int | None = None,
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
              AND ($3::text IS NULL OR execution_owner = $3)
              AND ($4::bigint IS NULL OR execution_epoch = $4)
              AND ($3::text IS NULL OR execution_lease_until IS NULL OR execution_lease_until > now())
            RETURNING id
            """,
            operation_id,
            error_message,
            execution_owner,
            execution_epoch,
        )
    return row is not None



async def mark_cancelled_uncertain(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    error_message: str,
    execution_owner: str | None = None,
    execution_epoch: int | None = None,
) -> bool:
    """Fail a cancelled operation and fence every unconfirmed destructive item."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE grile_monthly_reset_items
                SET status = 'uncertain',
                    checkpoint_phase = CASE
                        WHEN checkpoint_phase IN ('clear_intent', 'clear_verified', 'rollback_intent')
                            THEN 'recovery_required'
                        ELSE checkpoint_phase
                    END,
                    recovery_code = 'recovery_required',
                    rollback_status = CASE
                        WHEN rollback_status = 'restored' THEN rollback_status
                        ELSE 'failed'
                    END,
                    error_message = COALESCE(error_message, $2),
                    updated_at = now()
                WHERE operation_id = $1
                  AND EXISTS (
                      SELECT 1
                      FROM grile_monthly_operations operation
                      WHERE operation.id = $1
                        AND ($3::text IS NULL OR operation.execution_owner = $3)
                        AND ($4::bigint IS NULL OR operation.execution_epoch = $4)
                        AND ($3::text IS NULL OR operation.execution_lease_until IS NULL OR operation.execution_lease_until > now())
                  )
                  AND status IN ('running', 'completed')
                  AND rollback_status IS DISTINCT FROM 'restored'
                """,
                operation_id,
                error_message,
                execution_owner,
                execution_epoch,
            )
            row = await conn.fetchrow(
                """
                UPDATE grile_monthly_operations
                SET status = 'failed',
                    error_message = $2,
                    finished_at = now(),
                    heartbeat_at = now()
                WHERE id = $1 AND status IN ('queued', 'running')
                  AND ($3::text IS NULL OR execution_owner = $3)
                  AND ($4::bigint IS NULL OR execution_epoch = $4)
                  AND ($3::text IS NULL OR execution_lease_until IS NULL OR execution_lease_until > now())
                RETURNING id
                """,
                operation_id,
                error_message,
                execution_owner,
                execution_epoch,
            )
    return row is not None

async def get_manifest(
    pool: asyncpg.Pool,
    manifest_id: int,
) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_MANIFEST_COLUMNS} FROM grile_monthly_manifests WHERE id = $1",
            manifest_id,
        )
    return manifest_to_dict(row)


async def get_operation_manifest(
    pool: asyncpg.Pool,
    operation_id: int,
) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_MANIFEST_COLUMNS} FROM grile_monthly_manifests WHERE operation_id = $1",
            operation_id,
        )
    return manifest_to_dict(row)


async def get_latest_manifest(
    pool: asyncpg.Pool,
    *,
    closing_month: str,
    operation: str | None = None,
    statuses: Sequence[str] = ("verified", "approved", "consumed"),
) -> dict[str, Any] | None:
    if not statuses:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT {_MANIFEST_COLUMNS}
            FROM grile_monthly_manifests
            WHERE closing_month = $1
              AND ($2::text IS NULL OR operation = $2)
              AND status = ANY($3::text[])
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            closing_month,
            operation,
            list(statuses),
        )
    return manifest_to_dict(row)


async def persist_manifest_result(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    manifest: dict[str, Any],
    error_code: str | None = None,
    execution_owner: str | None = None,
    execution_epoch: int | None = None,
) -> dict[str, Any]:
    expected = manifest.get("expected") or {}
    processed = manifest.get("processed") or {}
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE grile_monthly_manifests
            SET status = $2,
                expected_store_count = $3,
                processed_store_count = $4,
                expected_agent_count = $5,
                processed_agent_count = $6,
                error_count = $7,
                control_totals = $8::jsonb,
                artifacts = $9::jsonb,
                source_backups = $10::jsonb,
                manifest = $11::jsonb,
                manifest_sha256 = $12,
                error_code = $13,
                verified_at = CASE WHEN $2 IN ('verified', 'approved') THEN now() ELSE NULL END,
                updated_at = now()
            WHERE operation_id = $1
              AND status = 'building'
              AND (
                  $14::text IS NULL
                  OR EXISTS (
                      SELECT 1
                      FROM grile_monthly_operations operation
                      WHERE operation.id = $1
                        AND operation.status = 'running'
                        AND operation.execution_owner = $14
                        AND operation.execution_epoch = $15
                        AND operation.execution_lease_until > now()
                  )
              )
            RETURNING {_MANIFEST_COLUMNS}
            """,
            operation_id,
            manifest.get("status", "failed"),
            int(expected.get("stores", 0)),
            int(processed.get("stores", 0)),
            int(expected.get("agents", 0)),
            int(processed.get("agents", 0)),
            int(manifest.get("error_count", 0)),
            json.dumps(manifest.get("control_totals", {}), ensure_ascii=False),
            json.dumps(manifest.get("artifacts", []), ensure_ascii=False),
            json.dumps(manifest.get("source_backups", []), ensure_ascii=False),
            json.dumps(manifest, ensure_ascii=False),
            manifest.get("manifest_sha256"),
            error_code,
            execution_owner,
            execution_epoch,
        )
    converted = manifest_to_dict(row)
    if converted is None:
        raise RuntimeError("Monthly manifest lost its building lease")
    return converted


async def approve_manifest(
    pool: asyncpg.Pool,
    *,
    manifest_id: int,
    expected_sha256: str,
    approved_by_sub: str,
    approved_manifest: dict[str, Any],
) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE grile_monthly_manifests
            SET status = 'approved',
                approved_by_sub = $3,
                approved_at = now(),
                manifest = $4::jsonb,
                manifest_sha256 = $5,
                updated_at = now()
            WHERE id = $1
              AND operation = 'archive'
              AND status = 'verified'
              AND manifest_sha256 = $2
              AND error_count = 0
              AND processed_store_count = expected_store_count
              AND processed_agent_count = expected_agent_count
            RETURNING {_MANIFEST_COLUMNS}
            """,
            manifest_id,
            expected_sha256,
            approved_by_sub,
            json.dumps(approved_manifest, ensure_ascii=False),
            approved_manifest.get("manifest_sha256"),
        )
    return manifest_to_dict(row)


async def ensure_reset_items(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    closing_month: str,
    next_month: str,
    entries: Sequence[ResetItemInput],
    execution_owner: str | None = None,
    execution_epoch: int | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO grile_monthly_reset_items (
                operation_id, closing_month, next_month, site_code, sheet_id,
                company, store, status, ranges
            )
            SELECT $1, $2, $3, $4, $5, $6, $7, 'pending', $8::jsonb
            WHERE EXISTS (
                SELECT 1
                FROM grile_monthly_operations operation
                WHERE operation.id = $1
                  AND ($9::text IS NULL OR operation.execution_owner = $9)
                  AND ($10::bigint IS NULL OR operation.execution_epoch = $10)
                  AND ($9::text IS NULL OR operation.execution_lease_until IS NULL OR operation.execution_lease_until > now())
            )
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
                    json.dumps(list(entry.ranges), ensure_ascii=False),
                    execution_owner,
                    execution_epoch,
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
    execution_owner: str | None = None,
    execution_epoch: int | None = None,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_reset_items
            SET status = 'running',
                started_at = COALESCE(started_at, now()),
                fence_epoch = fence_epoch + 1,
                updated_at = now()
            WHERE operation_id = $1 AND site_code = $2 AND status = 'pending'
              AND EXISTS (
                  SELECT 1
                  FROM grile_monthly_operations operation
                  WHERE operation.id = $1
                    AND ($3::text IS NULL OR operation.execution_owner = $3)
                    AND ($4::bigint IS NULL OR operation.execution_epoch = $4)
                    AND ($3::text IS NULL OR operation.execution_lease_until IS NULL OR operation.execution_lease_until > now())
              )
            RETURNING id
            """,
            operation_id,
            site_code,
            execution_owner,
            execution_epoch,
        )
    return row is not None


async def record_reset_item_backup(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    backup_path: str,
    backup_sha256: str,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_reset_items
            SET backup_path = $3,
                backup_sha256 = $4,
                checkpoint_phase = 'snapshot_persisted',
                recovery_code = NULL,
                updated_at = now()
            WHERE operation_id = $1
              AND site_code = $2
              AND status = 'pending'
              AND backup_path IS NULL
              AND backup_sha256 IS NULL
            RETURNING id
            """,
            operation_id,
            site_code,
            backup_path,
            backup_sha256,
        )
    return row is not None


async def record_reset_item_rollback(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    restored: bool,
    error_message: str | None = None,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_reset_items
            SET status = CASE WHEN $3 THEN 'error' ELSE 'uncertain' END,
                rollback_status = CASE WHEN $3 THEN 'restored' ELSE 'failed' END,
                restored_at = CASE WHEN $3 THEN now() ELSE NULL END,
                error_message = $4,
                updated_at = now()
            WHERE operation_id = $1
              AND site_code = $2
              AND status IN ('running', 'completed', 'error')
            RETURNING id
            """,
            operation_id,
            site_code,
            restored,
            error_message,
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
                checkpoint_phase = CASE
                    WHEN $3 = 'completed' THEN 'clear_verified'
                    ELSE checkpoint_phase
                END,
                verified_at = CASE WHEN $3 = 'completed' THEN now() ELSE verified_at END,
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


async def prepare_reset_clear(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    execution_owner: str,
    execution_epoch: int,
) -> dict[str, Any] | None:
    """Persist the single-use clear intent and advance the item fence."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE grile_monthly_reset_items AS item
            SET checkpoint_phase = 'clear_intent',
                fence_epoch = item.fence_epoch + 1,
                destructive_intent_at = now(),
                updated_at = now(),
                error_message = NULL
            WHERE item.operation_id = $1
              AND item.site_code = $2
              AND item.status = 'running'
              AND item.checkpoint_phase = 'snapshot_persisted'
              AND item.backup_path IS NOT NULL
              AND item.backup_sha256 ~ '^[0-9a-f]{{64}}$'
              AND EXISTS (
                  SELECT 1
                  FROM grile_monthly_operations operation
                  WHERE operation.id = item.operation_id
                    AND operation.status = 'running'
                    AND operation.execution_owner = $3
                    AND operation.execution_epoch = $4
                    AND operation.execution_lease_until > now()
              )
            RETURNING {_RESET_ITEM_COLUMNS}
            """,
            operation_id,
            site_code,
            execution_owner,
            execution_epoch,
        )
    return dict(row) if row is not None else None


async def confirm_reset_clear(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    execution_owner: str,
    execution_epoch: int,
    fence_epoch: int,
    verified: bool = True,
    error_message: str | None = None,
) -> bool:
    phase = "clear_verified" if verified else "recovery_required"
    status = "completed" if verified else "uncertain"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_reset_items AS item
            SET checkpoint_phase = $7,
                status = $8,
                verified_at = CASE WHEN $6 THEN now() ELSE verified_at END,
                recovery_code = CASE WHEN $6 THEN NULL ELSE 'recovery_required' END,
                error_message = $9,
                updated_at = now()
            WHERE item.operation_id = $1
              AND item.site_code = $2
              AND item.fence_epoch = $5
              AND item.checkpoint_phase = 'clear_intent'
              AND EXISTS (
                  SELECT 1
                  FROM grile_monthly_operations operation
                  WHERE operation.id = item.operation_id
                    AND operation.status = 'running'
                    AND operation.execution_owner = $3
                    AND operation.execution_epoch = $4
                    AND operation.execution_lease_until > now()
              )
            RETURNING id
            """,
            operation_id,
            site_code,
            execution_owner,
            execution_epoch,
            fence_epoch,
            verified,
            phase,
            status,
            error_message,
        )
    return row is not None


async def prepare_reset_rollback(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    execution_owner: str,
    execution_epoch: int,
) -> dict[str, Any] | None:
    """Fence one restore intent; never turns an uncertain item retryable."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE grile_monthly_reset_items AS item
            SET checkpoint_phase = 'rollback_intent',
                fence_epoch = item.fence_epoch + 1,
                destructive_intent_at = now(),
                updated_at = now()
            WHERE item.operation_id = $1
              AND item.site_code = $2
              AND item.checkpoint_phase IN ('clear_intent', 'clear_verified')
              AND item.status IN ('running', 'completed', 'uncertain')
              AND item.backup_path IS NOT NULL
              AND item.backup_sha256 ~ '^[0-9a-f]{{64}}$'
              AND EXISTS (
                  SELECT 1
                  FROM grile_monthly_operations operation
                  WHERE operation.id = item.operation_id
                    AND operation.execution_owner = $3
                    AND operation.execution_epoch = $4
                    AND operation.execution_lease_until > now()
              )
            RETURNING {_RESET_ITEM_COLUMNS}
            """,
            operation_id,
            site_code,
            execution_owner,
            execution_epoch,
        )
    return dict(row) if row is not None else None


async def confirm_reset_rollback(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    execution_owner: str,
    execution_epoch: int,
    fence_epoch: int,
    restored: bool,
    error_message: str | None = None,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_reset_items AS item
            SET checkpoint_phase = CASE WHEN $6 THEN 'rollback_verified' ELSE 'recovery_required' END,
                status = CASE WHEN $6 THEN 'error' ELSE 'uncertain' END,
                rollback_status = CASE WHEN $6 THEN 'restored' ELSE 'failed' END,
                restored_at = CASE WHEN $6 THEN now() ELSE NULL END,
                reconciled_at = CASE WHEN $6 THEN now() ELSE reconciled_at END,
                recovery_code = CASE WHEN $6 THEN NULL ELSE 'recovery_required' END,
                error_message = $7,
                updated_at = now()
            WHERE item.operation_id = $1
              AND item.site_code = $2
              AND item.fence_epoch = $5
              AND item.checkpoint_phase = 'rollback_intent'
              AND EXISTS (
                  SELECT 1
                  FROM grile_monthly_operations operation
                  WHERE operation.id = item.operation_id
                    AND operation.execution_owner = $3
                    AND operation.execution_epoch = $4
                    AND operation.execution_lease_until > now()
              )
            RETURNING id
            """,
            operation_id,
            site_code,
            execution_owner,
            execution_epoch,
            fence_epoch,
            restored,
            error_message,
        )
    return row is not None


async def list_reset_items_for_reconciliation(
    pool: asyncpg.Pool,
    operation_id: int,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT {_RESET_ITEM_COLUMNS}
            FROM grile_monthly_reset_items
            WHERE operation_id = $1
              AND (
                  status = 'uncertain'
                  OR checkpoint_phase IN ('legacy_unknown', 'clear_intent', 'clear_verified', 'rollback_intent')
                  OR recovery_code = 'recovery_required'
              )
            ORDER BY id
            """,
            operation_id,
        )
    return [dict(row) for row in rows]


async def claim_reconciliation_candidates(
    pool: asyncpg.Pool,
    *,
    execution_owner: str,
    lease_seconds: int = EXECUTION_LEASE_SECONDS,
    limit: int = 32,
) -> list[dict[str, Any]]:
    """Claim stale/uncertain operations once using row locks and a new epoch."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                f"""
                WITH candidates AS (
                    SELECT operation.id
                    FROM grile_monthly_operations operation
                    WHERE (
                        operation.status = 'running'
                        AND (
                            operation.execution_lease_until IS NULL
                            OR operation.execution_lease_until <= now()
                        )
                    )
                    OR EXISTS (
                        SELECT 1
                        FROM grile_monthly_reset_items item
                        WHERE item.operation_id = operation.id
                          AND (
                              item.status = 'uncertain'
                              OR item.checkpoint_phase IN ('legacy_unknown', 'clear_intent', 'clear_verified', 'rollback_intent')
                              OR item.recovery_code = 'recovery_required'
                          )
                        AND operation.status <> 'running'
                    )
                    ORDER BY operation.id
                    LIMIT $2
                    FOR UPDATE OF operation SKIP LOCKED
                )
                UPDATE grile_monthly_operations AS operation
                SET execution_owner = $1,
                    execution_epoch = operation.execution_epoch + 1,
                    execution_lease_until = now() + ($3 * interval '1 second'),
                    reconciled_at = NULL
                FROM candidates
                WHERE operation.id = candidates.id
                RETURNING {_OPERATION_COLUMNS}
                """,
                execution_owner,
                limit,
                lease_seconds,
            )
    operations: list[dict[str, Any]] = []
    for row in rows:
        operation = operation_to_dict(row)
        if operation is not None:
            operations.append(operation)
    return operations


async def mark_reconciliation_result(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    execution_owner: str,
    execution_epoch: int,
    classification: Literal["safe_retry", "rolled_back", "recovery_required"],
    error_message: str | None = None,
    alert: bool = False,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_operations
            SET status = CASE
                    WHEN $4 IN ('safe_retry', 'rolled_back') AND status = 'running' THEN 'failed'
                    ELSE status
                END,
                reconciliation_classification = $4,
                reconciled_at = now(),
                alerted_at = CASE WHEN $6 THEN COALESCE(alerted_at, now()) ELSE alerted_at END,
                error_message = COALESCE($5, error_message),
                execution_lease_until = NULL
            WHERE id = $1
              AND execution_owner = $2
              AND execution_epoch = $3
              AND (execution_lease_until IS NULL OR execution_lease_until > now())
            RETURNING id
            """,
            operation_id,
            execution_owner,
            execution_epoch,
            classification,
            error_message,
            alert,
        )
    return row is not None


async def mark_item_recovery_required(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    execution_owner: str,
    execution_epoch: int,
    error_message: str,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_reset_items AS item
            SET status = 'uncertain',
                checkpoint_phase = 'recovery_required',
                recovery_code = 'recovery_required',
                error_message = $5,
                reconciled_at = now(),
                updated_at = now()
            WHERE item.operation_id = $1
              AND item.site_code = $2
              AND item.checkpoint_phase <> 'rollback_verified'
              AND EXISTS (
                  SELECT 1
                  FROM grile_monthly_operations operation
                  WHERE operation.id = item.operation_id
                    AND operation.execution_owner = $3
                    AND operation.execution_epoch = $4
                    AND (operation.execution_lease_until IS NULL OR operation.execution_lease_until > now())
              )
            RETURNING id
            """,
            operation_id,
            site_code,
            execution_owner,
            execution_epoch,
            error_message,
        )
    return row is not None


async def mark_item_safe_retry(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    execution_owner: str,
    execution_epoch: int,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_reset_items AS item
            SET status = 'error',
                reconciled_at = now(),
                recovery_code = NULL,
                error_message = 'safe_retry',
                updated_at = now()
            WHERE item.operation_id = $1
              AND item.site_code = $2
              AND item.checkpoint_phase = 'snapshot_persisted'
              AND EXISTS (
                  SELECT 1
                  FROM grile_monthly_operations operation
                  WHERE operation.id = item.operation_id
                    AND operation.execution_owner = $3
                    AND operation.execution_epoch = $4
                    AND (operation.execution_lease_until IS NULL OR operation.execution_lease_until > now())
              )
            RETURNING id
            """,
            operation_id,
            site_code,
            execution_owner,
            execution_epoch,
        )
    return row is not None
