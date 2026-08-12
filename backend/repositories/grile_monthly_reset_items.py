"""Fenced per-store reset checkpoint persistence for monthly Grile."""

from __future__ import annotations

import json
from typing import Any, Literal, Sequence

import asyncpg

from repositories.grile_monthly_repository_types import (
    RESET_ITEM_COLUMNS as _RESET_ITEM_COLUMNS,
    ResetItemInput,
)


async def ensure_reset_items(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    closing_month: str,
    next_month: str,
    entries: Sequence[ResetItemInput],
    execution_owner: str,
    execution_epoch: int,
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
                  AND operation.status = 'running'
                  AND operation.execution_owner = $9
                  AND operation.execution_epoch = $10
                  AND operation.execution_lease_until > now()
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
    execution_owner: str,
    execution_epoch: int,
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
        )
    return row is not None


async def record_reset_item_backup(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    backup_path: str,
    backup_sha256: str,
    execution_owner: str,
    execution_epoch: int,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_reset_items AS item
            SET backup_path = $3,
                backup_sha256 = $4,
                checkpoint_phase = 'snapshot_persisted',
                recovery_code = NULL,
                updated_at = now()
            WHERE item.operation_id = $1
              AND item.site_code = $2
              AND item.status = 'pending'
              AND item.backup_path IS NULL
              AND item.backup_sha256 IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM grile_monthly_operations operation
                  WHERE operation.id = item.operation_id
                    AND operation.status = 'running'
                    AND operation.execution_owner = $5
                    AND operation.execution_epoch = $6
                    AND operation.execution_lease_until > now()
              )
            RETURNING id
            """,
            operation_id,
            site_code,
            backup_path,
            backup_sha256,
            execution_owner,
            execution_epoch,
        )
    return row is not None


async def record_reset_item_rollback(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    restored: bool,
    execution_owner: str,
    execution_epoch: int,
    error_message: str | None = None,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_reset_items AS item
            SET status = CASE WHEN $3 THEN 'error' ELSE 'uncertain' END,
                rollback_status = CASE WHEN $3 THEN 'restored' ELSE 'failed' END,
                restored_at = CASE WHEN $3 THEN now() ELSE NULL END,
                error_message = $4,
                updated_at = now()
            WHERE item.operation_id = $1
              AND item.site_code = $2
              AND item.status IN ('running', 'completed', 'error')
              AND EXISTS (
                  SELECT 1
                  FROM grile_monthly_operations operation
                  WHERE operation.id = item.operation_id
                    AND operation.execution_owner = $5
                    AND operation.execution_epoch = $6
                    AND operation.execution_lease_until > now()
              )
            RETURNING id
            """,
            operation_id,
            site_code,
            restored,
            error_message,
            execution_owner,
            execution_epoch,
        )
    return row is not None


async def finish_reset_item(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    status: Literal["completed", "error", "skipped"],
    execution_owner: str,
    execution_epoch: int,
    error_message: str | None = None,
) -> bool:
    expected_status = "pending" if status == "skipped" else "running"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE grile_monthly_reset_items AS item
            SET status = $3,
                checkpoint_phase = CASE
                    WHEN $3 = 'completed' THEN 'clear_verified'
                    ELSE checkpoint_phase
                END,
                verified_at = CASE WHEN $3 = 'completed' THEN now() ELSE verified_at END,
                error_message = $4,
                completed_at = CASE WHEN $3 IN ('completed', 'skipped') THEN now() ELSE completed_at END,
                updated_at = now()
            WHERE item.operation_id = $1 AND item.site_code = $2 AND item.status = $5
              AND EXISTS (
                  SELECT 1
                  FROM grile_monthly_operations operation
                  WHERE operation.id = item.operation_id
                    AND operation.status = 'running'
                    AND operation.execution_owner = $6
                    AND operation.execution_epoch = $7
                    AND operation.execution_lease_until > now()
              )
            RETURNING id
            """,
            operation_id,
            site_code,
            status,
            error_message,
            expected_status,
            execution_owner,
            execution_epoch,
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
