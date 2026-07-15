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
    triggered_by_email, requested_by_sub, approved_manifest_id, result,
    error_message, started_at, heartbeat_at, finished_at, created_at
"""

_RESET_ITEM_COLUMNS = """
    id, operation_id, closing_month, next_month, site_code, sheet_id,
    company, store, status, ranges, error_message, started_at, completed_at,
    backup_path, backup_sha256, rollback_status, restored_at, updated_at,
    created_at
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
                      AND (status = 'uncertain' OR rollback_status = 'failed')
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


async def start(
    pool: asyncpg.Pool,
    operation_id: int,
) -> MonthlyOperationStartResult:
    async with pool.acquire() as conn:
        async with conn.transaction():
            started = await conn.fetchrow(
                f"""
                UPDATE grile_monthly_operations AS operation
                SET status = 'running',
                    started_at = COALESCE(operation.started_at, now()),
                    heartbeat_at = now()
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


async def finish_reset_success(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    result: dict[str, Any],
    reset_manifest: dict[str, Any],
    manifest_id: int,
    expected_manifest_sha256: str,
    consumed_manifest: dict[str, Any],
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
                RETURNING id
                """,
                operation_id,
                json.dumps(result, ensure_ascii=False),
                manifest_id,
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
            WHERE operation_id = $1 AND status = 'building'
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
