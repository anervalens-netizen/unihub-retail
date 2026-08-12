"""Manifest persistence for monthly Grile closeout operations."""

from __future__ import annotations

import json
from typing import Any, Sequence

import asyncpg

from repositories.grile_monthly_repository_types import (
    MANIFEST_COLUMNS as _MANIFEST_COLUMNS,
    manifest_to_dict,
)


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
    execution_owner: str,
    execution_epoch: int,
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
            WHERE operation_id = $1
              AND status = 'building'
              AND EXISTS (
                  SELECT 1
                  FROM grile_monthly_operations operation
                  WHERE operation.id = $1
                    AND operation.status = 'running'
                    AND operation.execution_owner = $14
                    AND operation.execution_epoch = $15
                    AND operation.execution_lease_until > now()
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
