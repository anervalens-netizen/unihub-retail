"""Database fencing for the retained source artifact of a sales generation."""

from __future__ import annotations

from datetime import date
from typing import Any

import asyncpg

from services.sales_generation import SalesGenerationConflictError


async def mark_sales_generation_artifact_retained(
    conn: asyncpg.Connection,
    *,
    snapshot_id: int,
    generation_token: str,
    owner_id: str,
    retained_path: str,
    source_sha256: str,
    source_byte_size: int,
) -> None:
    updated = await conn.fetchval(
        """
        UPDATE import_snapshots
        SET source_spool_path = $4,
            source_artifact_retained_path = $4,
            source_artifact_state = 'artifact_retained',
            source_artifact_sha256 = $5,
            source_artifact_bytes = $6,
            source_artifact_retained_at = COALESCE(source_artifact_retained_at, now()),
            heartbeat_at = now()
        WHERE id = $1
          AND generation_token = $2::uuid
          AND owner_id = $3::uuid
          AND status = 'processing'
          AND (
                source_artifact_state = 'artifact_retaining'
                OR (
                    source_artifact_state = 'artifact_retained'
                    AND source_artifact_retained_path = $4
                    AND source_artifact_sha256 = $5
                    AND source_artifact_bytes = $6
                )
          )
        RETURNING id
        """,
        snapshot_id,
        generation_token,
        owner_id,
        retained_path,
        source_sha256,
        source_byte_size,
    )
    if updated is None:
        raise SalesGenerationConflictError("Sales artifact retain fence was lost")


async def find_recoverable_sales_generation_for_artifact_retain(
    conn: asyncpg.Connection,
    *,
    queued_path: str,
    retained_path: str,
    source_sha256: str,
    source_byte_size: int,
    cutoff_date: date | None,
) -> dict[str, Any] | None:
    """Find one exact validated generation still completing artifact retain."""
    rows = await conn.fetch(
        """
        SELECT id, import_month, filename, is_month_final, rows_in_file,
               rows_imported, coverage_report, generation_token, owner_id,
               manifest_sha256, manifest, source_artifact_state
        FROM import_snapshots
        WHERE status = 'processing'
          AND manifest->>'generation_state' = 'validated'
          AND source_artifact_required = true
          AND source_sha256 = $1
          AND source_artifact_sha256 = $1
          AND source_artifact_bytes = $2
          AND source_artifact_state IN ('artifact_retaining', 'artifact_retained')
          AND (
                source_spool_path IN ($3, $4)
                OR source_artifact_retained_path = $4
          )
          AND cutoff_date IS NOT DISTINCT FROM $5::date
        ORDER BY created_at DESC
        LIMIT 2
        """,
        source_sha256,
        source_byte_size,
        queued_path,
        retained_path,
        cutoff_date,
    )
    if not rows:
        return None
    if len(rows) != 1:
        raise SalesGenerationConflictError(
            "Multiple validated sales generations match the retained artifact"
        )
    return dict(rows[0])
