from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from uuid import uuid4

import asyncpg

from services.sales_generation import (
    SalesGenerationConflictError,
    SalesGenerationValidationError,
    canonical_json_sha256,
)
PromoteGeneration = Callable[..., Awaitable[tuple[int, int]]]

_ROLLBACK_SQL_1 = """
            SELECT head.import_month, head.revision,
                   snap.generation_token::text AS generation_token,
                   snap.manifest_sha256, snap.previous_snapshot_id
            FROM sales_generation_heads head
            JOIN import_snapshots snap ON snap.id = head.snapshot_id
            WHERE head.snapshot_id = $1
            FOR UPDATE OF head
            """

_ROLLBACK_SQL_2 = """
            SELECT filename, rows_in_file, is_month_final, source_sha256,
                   cutoff_date, coverage_report, manifest, source_spool_path,
                   stage_rows_sha256, source_artifact_required,
                   source_artifact_state, source_artifact_sha256,
                   source_artifact_bytes, source_artifact_retained_path,
                   source_artifact_retained_at
            FROM import_snapshots
            WHERE id = $1
              AND import_month = $2
              AND status = 'completed'
              AND EXISTS (
                  SELECT 1 FROM sales_import_stage_rows staged
                  WHERE staged.snapshot_id = import_snapshots.id
              )
            """

_ROLLBACK_SQL_3 = """
            INSERT INTO import_snapshots (
                import_month, filename, rows_in_file, rows_imported, status,
                is_month_final, source_sha256, cutoff_date, manifest,
                manifest_sha256, generation_token, owner_id, lease_until,
                expected_head_revision, previous_snapshot_id, coverage_report,
                source_spool_path, heartbeat_at, source_artifact_required,
                source_artifact_state, source_artifact_sha256,
                source_artifact_bytes, source_artifact_retained_path,
                source_artifact_retained_at
            ) VALUES (
                $1, $2, $3, $4, 'processing', $5, $6, $7, $8::jsonb,
                $9, $10::uuid, $11::uuid, now() + interval '2 hours',
                $12, $13, $14::jsonb, $15, now(), $16,
                $17, $18, $19, $20, $21
            )
            RETURNING id
            """

_ROLLBACK_SQL_4 = """
            INSERT INTO sales_import_stage_rows (
                snapshot_id, row_number, import_month, sale_date, site_code,
                locatie, firma, regional, asm, bon_nr, item_code, item_name,
                brand, category, subcategory, quantity, unit_price, total_value,
                agent, is_cartela, is_return
            )
            SELECT $1, row_number, import_month, sale_date, site_code,
                   locatie, firma, regional, asm, bon_nr, item_code, item_name,
                   brand, category, subcategory, quantity, unit_price, total_value,
                   agent, is_cartela, is_return
            FROM sales_import_stage_rows
            WHERE snapshot_id = $2
            ORDER BY row_number
            """

_ROLLBACK_SQL_5 = """
            UPDATE import_snapshots
            SET stage_rows_sha256 = $2
            WHERE id = $1 AND stage_rows_sha256 IS NULL
            """


async def rollback_sales_generation(
    conn: asyncpg.Connection,
    *,
    current_snapshot_id: int,
    current_generation_token: str,
    expected_manifest_sha256: str,
    requested_by_sub: str,
    reason: str,
    promote: PromoteGeneration,
) -> tuple[int, int, int]:
    """Clone the retained previous generation and promote it as a new head."""
    actor = requested_by_sub.strip()
    rollback_reason = reason.strip()
    if not actor:
        raise ValueError("requested_by_sub is required")
    if len(rollback_reason) < 10:
        raise ValueError("Rollback reason must contain at least 10 characters")

    async with conn.transaction():
        current = await conn.fetchrow(
            _ROLLBACK_SQL_1,
            current_snapshot_id,
        )
        if current is None:
            raise SalesGenerationConflictError("Rollback source is no longer the current head")
        if current["generation_token"] != current_generation_token:
            raise SalesGenerationConflictError("Rollback generation token does not match current head")
        if current["manifest_sha256"] != expected_manifest_sha256:
            raise SalesGenerationConflictError("Rollback manifest hash does not match current head")
        target_snapshot_id = current["previous_snapshot_id"]
        if target_snapshot_id is None:
            raise SalesGenerationValidationError("Current generation has no retained rollback predecessor")

        source = await conn.fetchrow(
            _ROLLBACK_SQL_2,
            int(target_snapshot_id),
            str(current["import_month"]),
        )
        if source is None:
            raise SalesGenerationValidationError("Retained rollback generation is unavailable")
        manifest = source["manifest"]
        if isinstance(manifest, str):
            manifest = json.loads(manifest)
        coverage_report = source["coverage_report"]
        if isinstance(coverage_report, str):
            coverage_report = json.loads(coverage_report)
        rollback_manifest = dict(manifest or {})
        rollback_manifest["generation_state"] = "validated"
        source_stage_digest = source["stage_rows_sha256"]
        if not isinstance(source_stage_digest, str) or len(source_stage_digest) != 64:
            raise SalesGenerationValidationError(
                "Retained rollback generation has no verified stage digest"
            )
        rollback_manifest["stage_rows_sha256"] = source_stage_digest
        rollback_manifest["rollback_of_snapshot_id"] = current_snapshot_id
        rollback_manifest["rollback_source_snapshot_id"] = int(target_snapshot_id)
        rollback_manifest["anomalies"] = [
            {
                "code": "operator_rollback",
                "classification": "informational",
                "blocking": False,
                "message": "Generație recreată din predecesorul reținut pentru rollback.",
            }
        ]
        manifest_sha256 = canonical_json_sha256(rollback_manifest)
        generation_token = str(uuid4())
        owner_id = str(uuid4())
        new_snapshot_id = await conn.fetchval(
            _ROLLBACK_SQL_3,
            str(current["import_month"]),
            f"rollback:{current_snapshot_id}->{int(target_snapshot_id)}:{source['filename']}",
            int(source["rows_in_file"] or rollback_manifest["rows_imported"]),
            int(rollback_manifest["rows_imported"]),
            bool(source["is_month_final"]),
            source["source_sha256"],
            source["cutoff_date"],
            json.dumps(rollback_manifest, ensure_ascii=False, sort_keys=True),
            manifest_sha256,
            generation_token,
            owner_id,
            int(current["revision"]),
            current_snapshot_id,
            json.dumps(dict(coverage_report or {}), ensure_ascii=False, sort_keys=True),
            source["source_spool_path"],
            bool(source["source_artifact_required"]),
            source["source_artifact_state"],
            source["source_artifact_sha256"],
            source["source_artifact_bytes"],
            source["source_artifact_retained_path"],
            source["source_artifact_retained_at"],
        )
        if new_snapshot_id is None:
            raise SalesGenerationConflictError("Rollback generation could not be reserved")
        await conn.execute(
            _ROLLBACK_SQL_4,
            int(new_snapshot_id),
            int(target_snapshot_id),
        )
        await conn.execute(
            _ROLLBACK_SQL_5,
            int(new_snapshot_id),
            source_stage_digest,
        )
        rows_imported, revision = await promote(
            conn,
            snapshot_id=int(new_snapshot_id),
            generation_token=generation_token,
            owner_id=owner_id,
            expected_manifest_sha256=manifest_sha256,
            requested_by_sub=actor,
            override_reason=rollback_reason,
            action="rollback",
        )
    return int(new_snapshot_id), rows_imported, revision
