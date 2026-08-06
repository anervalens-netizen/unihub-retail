"""Durable, owner-bound lifecycle for complex XLSX export operations."""

from __future__ import annotations

import json
from typing import Any

import asyncpg


MAX_ACTIVE_EXPORT_OPERATIONS = 3


class ExportOperationCapacityError(RuntimeError):
    pass


EXPORT_OPERATION_COLUMNS = """
    id, kind, status, job_id, request_payload, request_sha256,
    requested_by_sub, execution_owner, execution_epoch,
    execution_lease_until, artifact_key, artifact_sha256, artifact_size,
    peak_rss_bytes, build_seconds, cell_count, download_filename,
    error_code, created_at, updated_at, started_at,
    finished_at, expires_at, download_claimed_at
"""


def export_operation_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    value = dict(row)
    payload = value.get("request_payload")
    if isinstance(payload, str):
        value["request_payload"] = json.loads(payload)
    return value


class ExportOperationsRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def reserve(
        self,
        *,
        kind: str,
        request_payload: dict[str, Any],
        request_sha256: str,
        requested_by_sub: str,
    ) -> dict[str, Any]:
        if not requested_by_sub.strip():
            raise ValueError("requested_by_sub is required")
        encoded = json.dumps(request_payload, sort_keys=True, separators=(",", ":"))
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    "unihub:exports:active-capacity",
                )
                owner_active = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM export_operations
                        WHERE requested_by_sub = $1 AND status IN ('queued', 'running')
                    )
                    """,
                    requested_by_sub,
                )
                active_count = int(
                    await conn.fetchval(
                        "SELECT COUNT(*) FROM export_operations WHERE status IN ('queued', 'running')"
                    )
                    or 0
                )
                if owner_active:
                    raise ExportOperationCapacityError("Requester already has an active export")
                if active_count >= MAX_ACTIVE_EXPORT_OPERATIONS:
                    raise ExportOperationCapacityError("Export queue reached its active capacity")
                row = await conn.fetchrow(
                    f"""
                    WITH identity AS (
                        SELECT nextval('export_operations_id_seq')::BIGINT AS id
                    )
                    INSERT INTO export_operations (
                        id, kind, status, job_id, request_payload,
                        request_sha256, requested_by_sub
                    )
                    SELECT id, $1, 'queued', 'export-complex:' || id::TEXT,
                           $2::JSONB, $3, $4
                    FROM identity
                    RETURNING {EXPORT_OPERATION_COLUMNS}
                    """,
                    kind,
                    encoded,
                    request_sha256,
                    requested_by_sub,
                )
        operation = export_operation_to_dict(row)
        if operation is None:
            raise RuntimeError("Failed to reserve export operation")
        return operation

    async def get(self, operation_id: int) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {EXPORT_OPERATION_COLUMNS} FROM export_operations WHERE id = $1",
                operation_id,
            )
        return export_operation_to_dict(row)

    async def get_owned(
        self,
        operation_id: int,
        *,
        requested_by_sub: str,
    ) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {EXPORT_OPERATION_COLUMNS}
                FROM export_operations
                WHERE id = $1 AND requested_by_sub = $2
                """,
                operation_id,
                requested_by_sub,
            )
        return export_operation_to_dict(row)

    async def get_resumable_owned(self, *, requested_by_sub: str) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {EXPORT_OPERATION_COLUMNS}
                FROM export_operations
                WHERE requested_by_sub = $1
                  AND (
                      status IN ('queued', 'running')
                      OR (status = 'completed'
                          AND expires_at > now()
                          AND download_claimed_at IS NULL)
                  )
                ORDER BY CASE WHEN status IN ('queued', 'running') THEN 0 ELSE 1 END,
                         created_at DESC
                LIMIT 1
                """,
                requested_by_sub,
            )
        return export_operation_to_dict(row)

    async def claim_download_owned(
        self,
        operation_id: int,
        *,
        requested_by_sub: str,
    ) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE export_operations
                SET download_claimed_at = now(), updated_at = now()
                WHERE id = $1
                  AND requested_by_sub = $2
                  AND status = 'completed'
                  AND expires_at > now()
                  AND download_claimed_at IS NULL
                RETURNING {EXPORT_OPERATION_COLUMNS}
                """,
                operation_id,
                requested_by_sub,
            )
        return export_operation_to_dict(row)

    async def claim(
        self,
        operation_id: int,
        *,
        execution_owner: str,
        lease_seconds: int,
    ) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE export_operations
                SET status = 'running',
                    execution_owner = $2,
                    execution_epoch = execution_epoch + 1,
                    execution_lease_until = now() + ($3 * interval '1 second'),
                    started_at = now(),
                    updated_at = now()
                WHERE id = $1 AND status = 'queued'
                RETURNING {EXPORT_OPERATION_COLUMNS}
                """,
                operation_id,
                execution_owner,
                lease_seconds,
            )
        return export_operation_to_dict(row)

    async def heartbeat(
        self,
        operation_id: int,
        *,
        execution_owner: str,
        execution_epoch: int,
        lease_seconds: int,
    ) -> bool:
        async with self.pool.acquire() as conn:
            updated = await conn.fetchval(
                """
                UPDATE export_operations
                SET execution_lease_until = now() + ($4 * interval '1 second'),
                    updated_at = now()
                WHERE id = $1
                  AND status = 'running'
                  AND execution_owner = $2
                  AND execution_epoch = $3
                RETURNING id
                """,
                operation_id,
                execution_owner,
                execution_epoch,
                lease_seconds,
            )
        return updated is not None

    async def complete(
        self,
        operation_id: int,
        *,
        execution_owner: str,
        execution_epoch: int,
        artifact_key: str,
        artifact_sha256: str,
        artifact_size: int,
        peak_rss_bytes: int,
        build_seconds: float,
        cell_count: int,
        download_filename: str,
        ttl_seconds: int,
    ) -> bool:
        async with self.pool.acquire() as conn:
            updated = await conn.fetchval(
                """
                UPDATE export_operations
                SET status = 'completed',
                    artifact_key = $4,
                    artifact_sha256 = $5,
                    artifact_size = $6,
                    peak_rss_bytes = $7,
                    build_seconds = $8,
                    cell_count = $9,
                    download_filename = $10,
                    error_code = NULL,
                    execution_lease_until = NULL,
                    finished_at = now(),
                    expires_at = now() + ($11 * interval '1 second'),
                    updated_at = now()
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
                artifact_key,
                artifact_sha256,
                artifact_size,
                peak_rss_bytes,
                build_seconds,
                cell_count,
                download_filename,
                ttl_seconds,
            )
        return updated is not None

    async def fail_queued(self, operation_id: int, *, error_code: str) -> bool:
        async with self.pool.acquire() as conn:
            updated = await conn.fetchval(
                """
                UPDATE export_operations
                SET status = 'failed', error_code = $2,
                    execution_lease_until = NULL,
                    finished_at = now(), updated_at = now()
                WHERE id = $1 AND status = 'queued'
                RETURNING id
                """,
                operation_id,
                error_code,
            )
        return updated is not None

    async def fail_running(
        self,
        operation_id: int,
        *,
        execution_owner: str,
        execution_epoch: int,
        error_code: str,
        cancelled: bool = False,
    ) -> bool:
        async with self.pool.acquire() as conn:
            updated = await conn.fetchval(
                """
                UPDATE export_operations
                SET status = CASE WHEN $5::BOOLEAN THEN 'cancelled' ELSE 'failed' END,
                    error_code = $4,
                    artifact_key = NULL,
                    execution_lease_until = NULL,
                    finished_at = now(), updated_at = now()
                WHERE id = $1
                  AND status = 'running'
                  AND execution_owner = $2
                  AND execution_epoch = $3
                RETURNING id
                """,
                operation_id,
                execution_owner,
                execution_epoch,
                error_code,
                cancelled,
            )
        return updated is not None

    async def cancel_owned(
        self,
        operation_id: int,
        *,
        requested_by_sub: str,
    ) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE export_operations
                SET status = 'cancelled',
                    error_code = 'cancelled_by_user',
                    execution_lease_until = NULL,
                    finished_at = now(), updated_at = now()
                WHERE id = $1
                  AND requested_by_sub = $2
                  AND status IN ('queued', 'running')
                RETURNING {EXPORT_OPERATION_COLUMNS}
                """,
                operation_id,
                requested_by_sub,
            )
        return export_operation_to_dict(row)

    async def reconcile_stale(
        self,
        *,
        queued_timeout_seconds: int,
    ) -> list[int]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                UPDATE export_operations
                SET status = 'failed',
                    error_code = CASE
                        WHEN status = 'queued' THEN 'queue_stale'
                        ELSE 'worker_lease_expired'
                    END,
                    artifact_key = NULL,
                    execution_lease_until = NULL,
                    finished_at = now(), updated_at = now()
                WHERE (status = 'queued'
                       AND created_at < now() - ($1 * interval '1 second'))
                   OR (status = 'running'
                       AND execution_lease_until <= now())
                RETURNING id
                """,
                queued_timeout_seconds,
            )
        return [int(row["id"]) for row in rows]

    async def claim_expired(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH due AS (
                    SELECT id, artifact_key
                    FROM export_operations
                    WHERE status = 'completed' AND expires_at <= now()
                    ORDER BY expires_at
                    LIMIT 500
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE export_operations AS operation
                SET status = 'expired', artifact_key = NULL,
                    execution_lease_until = NULL, updated_at = now()
                FROM due
                WHERE operation.id = due.id
                  AND operation.status = 'completed'
                RETURNING operation.id, due.artifact_key
                """
            )
        return [dict(row) for row in rows]

    async def mark_corrupt(self, operation_id: int, *, artifact_key: str) -> bool:
        async with self.pool.acquire() as conn:
            updated = await conn.fetchval(
                """
                UPDATE export_operations
                SET status = 'failed', artifact_key = NULL,
                    error_code = 'artifact_integrity_failed',
                    execution_lease_until = NULL, updated_at = now()
                WHERE id = $1
                  AND status = 'completed'
                  AND artifact_key = $2
                RETURNING id
                """,
                operation_id,
                artifact_key,
            )
        return updated is not None

    async def active_artifact_keys(self) -> set[str]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT artifact_key
                FROM export_operations
                WHERE status = 'completed'
                  AND expires_at > now()
                  AND artifact_key IS NOT NULL
                """
            )
        return {str(row["artifact_key"]) for row in rows}
