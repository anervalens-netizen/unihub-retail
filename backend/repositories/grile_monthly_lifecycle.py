"""Lease-fenced lifecycle persistence for monthly Grile operations."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import asyncpg

from grile.domain.monthly_state import (
    MonthlyOperationStartResult,
    operation_start_result,
    terminal_operation_status,
)
from repositories.grile_monthly_repository_types import (
    EXECUTION_LEASE_SECONDS,
    MANIFEST_COLUMNS as _MANIFEST_COLUMNS,
    OPERATION_COLUMNS as _OPERATION_COLUMNS,
    MonthlyExecutionLease,
    manifest_to_dict,
    operation_to_dict,
)


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
    execution_owner: str,
    execution_epoch: int,
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
              AND execution_owner = $2
              AND execution_epoch = $3
              AND execution_lease_until > now()
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
    execution_owner: str,
    execution_epoch: int,
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
              AND execution_owner = $5
              AND execution_epoch = $6
              AND execution_lease_until > now()
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
    execution_owner: str,
    execution_epoch: int,
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
                  AND EXISTS (
                      SELECT 1
                      FROM grile_monthly_operations operation
                      WHERE operation.id = $1
                        AND operation.status = 'running'
                        AND operation.execution_owner = $13
                        AND operation.execution_epoch = $14
                        AND operation.execution_lease_until > now()
                  )
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
                execution_owner,
                execution_epoch,
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
                  AND execution_owner = $4
                  AND execution_epoch = $5
                  AND execution_lease_until > now()
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
    execution_owner: str,
    execution_epoch: int,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_operations
            SET status = 'failed',
                error_message = $2,
                finished_at = now(),
                heartbeat_at = now()
            WHERE id = $1 AND status = 'running'
              AND execution_owner = $3
              AND execution_epoch = $4
              AND execution_lease_until > now()
            RETURNING id
            """,
            operation_id,
            error_message,
            execution_owner,
            execution_epoch,
        )
    return row is not None


async def fail_queued(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    error_message: str,
) -> bool:
    """Fail only an operation that has not acquired an execution lease."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_operations
            SET status = 'failed',
                error_message = $2,
                finished_at = now(),
                heartbeat_at = now()
            WHERE id = $1
              AND status = 'queued'
              AND execution_owner IS NULL
              AND execution_epoch = 0
            RETURNING id
            """,
            operation_id,
            error_message,
        )
    return row is not None


async def mark_cancelled_uncertain(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    error_message: str,
    execution_owner: str,
    execution_epoch: int,
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
                        AND operation.execution_owner = $3
                        AND operation.execution_epoch = $4
                        AND operation.execution_lease_until > now()
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
                  AND execution_owner = $3
                  AND execution_epoch = $4
                  AND execution_lease_until > now()
                RETURNING id
                """,
                operation_id,
                error_message,
                execution_owner,
                execution_epoch,
            )
    return row is not None


async def get_execution_lease(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    execution_owner: str,
) -> MonthlyExecutionLease | None:
    """Read only the caller-owned active lease for terminal fallback writes."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, execution_owner, execution_epoch, execution_lease_until
            FROM grile_monthly_operations
            WHERE id = $1
              AND status = 'running'
              AND execution_owner = $2
              AND execution_lease_until > now()
            """,
            operation_id,
            execution_owner,
        )
    if row is None:
        return None
    return MonthlyExecutionLease(
        operation_id=int(row["id"]),
        execution_owner=str(row["execution_owner"]),
        execution_epoch=int(row["execution_epoch"]),
        execution_lease_until=row["execution_lease_until"],
    )
