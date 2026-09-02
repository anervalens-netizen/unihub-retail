"""Stale and uncertain monthly Grile reconciliation persistence."""

from __future__ import annotations

from typing import Any, Literal

import asyncpg

from repositories.grile_monthly_repository_types import (
    EXECUTION_LEASE_SECONDS,
    RESET_ITEM_COLUMNS as _RESET_ITEM_COLUMNS,
    operation_to_dict,
)


async def list_reset_items_for_reconciliation(
    pool: asyncpg.Pool,
    operation_id: int,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT {_RESET_ITEM_COLUMNS}
            FROM grile_monthly_reset_items AS item
            JOIN grile_monthly_operations AS operation
              ON operation.id = item.operation_id
            WHERE item.operation_id = $1
              AND (
                  item.status = 'uncertain'
                  OR item.checkpoint_phase IN ('legacy_unknown', 'clear_intent', 'rollback_intent')
                  OR item.recovery_code = 'recovery_required'
                  OR (
                      item.checkpoint_phase = 'clear_verified'
                      AND (item.status <> 'completed' OR operation.status = 'running')
                  )
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
                              OR item.checkpoint_phase IN ('legacy_unknown', 'clear_intent', 'rollback_intent')
                              OR item.recovery_code = 'recovery_required'
                              OR (
                                  item.checkpoint_phase = 'clear_verified'
                                  AND (item.status <> 'completed' OR operation.status = 'running')
                              )
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
                RETURNING
                    operation.id, operation.op, operation.closing_month,
                    operation.only_filter, operation.dry_run, operation.status,
                    operation.job_id, operation.triggered_by_email,
                    operation.requested_by_sub, operation.approved_manifest_id,
                    operation.result, operation.error_message,
                    operation.started_at, operation.heartbeat_at,
                    operation.finished_at, operation.created_at,
                    operation.execution_owner, operation.execution_epoch,
                    operation.execution_lease_until,
                    operation.reconciliation_classification,
                    operation.reconciled_at, operation.alerted_at
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
              AND execution_lease_until > now()
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
                    AND operation.execution_lease_until > now()
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
                    AND operation.execution_lease_until > now()
              )
            RETURNING id
            """,
            operation_id,
            site_code,
            execution_owner,
            execution_epoch,
        )
    return row is not None
