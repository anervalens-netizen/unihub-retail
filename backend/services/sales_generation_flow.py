from __future__ import annotations

import asyncio
from decimal import Decimal
import json
from typing import Any

import asyncpg

from services.reporting_refresh import (
    rebuild_agent_lifecycle_reporting,
    rebuild_reporting_month,
)
from services.sales_generation import (
    SalesGenerationConflictError,
    SalesGenerationValidationError,
    copy_staged_generation_to_live,
    manifest_requires_override,
)
from services.sales_generation_artifacts import (
    find_recoverable_sales_generation_for_artifact_retain,
    mark_sales_generation_artifact_retained,
)


async def load_current_sales_manifest(
    conn: asyncpg.Connection,
    import_month: str,
) -> tuple[int | None, dict[str, Any] | None]:
    row = await conn.fetchrow(
        """
        SELECT snap.id, snap.manifest
        FROM sales_generation_heads head
        JOIN import_snapshots snap ON snap.id = head.snapshot_id
        WHERE head.import_month = $1
        """,
        import_month,
    )
    if row is None:
        row = await conn.fetchrow(
            """
            SELECT id, manifest
            FROM import_snapshots
            WHERE import_month = $1
              AND status = 'completed'
              AND manifest IS NOT NULL
            ORDER BY promoted_at DESC NULLS LAST, created_at DESC
            LIMIT 1
            """,
            import_month,
        )
    if row is None:
        return None, None
    manifest = row["manifest"]
    if isinstance(manifest, str):
        manifest = json.loads(manifest)
    return int(row["id"]), dict(manifest) if manifest else None


async def persist_validated_sales_generation(
    conn: asyncpg.Connection,
    *,
    snapshot_id: int,
    generation_token: str,
    owner_id: str,
    manifest: dict[str, Any],
    manifest_sha256: str,
    coverage_report: dict[str, Any],
) -> None:
    updated = await conn.fetchval(
        """
        UPDATE import_snapshots
        SET manifest = $4::jsonb,
            manifest_sha256 = $5,
            coverage_report = $6::jsonb,
            rows_imported = $7,
            heartbeat_at = now()
        WHERE id = $1
          AND generation_token = $2::uuid
          AND owner_id = $3::uuid
          AND status = 'processing'
          AND lease_until > now()
        RETURNING id
        """,
        snapshot_id,
        generation_token,
        owner_id,
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        manifest_sha256,
        json.dumps(coverage_report, ensure_ascii=False, sort_keys=True),
        int(manifest["rows_imported"]),
    )
    if updated is None:
        raise SalesGenerationConflictError("Sales generation lease was lost before validation")


async def attach_sales_generation_source(
    conn: asyncpg.Connection,
    *,
    snapshot_id: int,
    generation_token: str,
    owner_id: str,
    source_spool_path: str,
    source_sha256: str | None = None,
    source_byte_size: int | None = None,
) -> None:
    updated = await conn.fetchval(
        """
        UPDATE import_snapshots
        SET source_spool_path = $4,
            source_artifact_state = 'artifact_retaining',
            source_artifact_sha256 = COALESCE($5, source_sha256),
            source_artifact_bytes = COALESCE($6, source_artifact_bytes),
            heartbeat_at = now()
        WHERE id = $1
          AND generation_token = $2::uuid
          AND owner_id = $3::uuid
          AND status = 'processing'
          AND manifest->>'generation_state' = 'validated'
        RETURNING id
        """,
        snapshot_id,
        generation_token,
        owner_id,
        source_spool_path,
        source_sha256,
        source_byte_size,
    )
    if updated is None:
        raise SalesGenerationConflictError("Sales source cannot be attached by a stale worker")


async def claim_validated_sales_generation(
    conn: asyncpg.Connection,
    *,
    snapshot_id: int,
    generation_token: str,
    expected_manifest_sha256: str,
    new_owner_id: str,
    lease_seconds: int = 2 * 60 * 60,
) -> str:
    if lease_seconds < 60:
        raise ValueError("Sales generation lease must be at least 60 seconds")
    previous_owner = await conn.fetchval(
        """
        WITH candidate AS (
            SELECT id, owner_id::text AS previous_owner_id
            FROM import_snapshots
            WHERE id = $1
              AND generation_token = $2::uuid
              AND manifest_sha256 = $3
              AND status = 'processing'
              AND manifest->>'generation_state' = 'validated'
              AND (
                    NOT source_artifact_required
                    OR source_artifact_state = 'artifact_retained'
              )
            FOR UPDATE
        ), updated AS (
            UPDATE import_snapshots snap
            SET owner_id = $4::uuid,
                heartbeat_at = now(),
                lease_until = now() + make_interval(secs => $5),
                manifest = jsonb_set(snap.manifest, '{generation_state}', '"promoting"'::jsonb, true)
            FROM candidate
            WHERE snap.id = candidate.id
            RETURNING candidate.previous_owner_id
        )
        SELECT previous_owner_id FROM updated
        """,
        snapshot_id,
        generation_token,
        expected_manifest_sha256,
        new_owner_id,
        lease_seconds,
    )
    if previous_owner is None:
        raise SalesGenerationConflictError("Validated sales generation cannot be claimed")
    return str(previous_owner)


async def restore_sales_generation_claim(
    conn: asyncpg.Connection,
    *,
    snapshot_id: int,
    generation_token: str,
    current_owner_id: str,
    previous_owner_id: str,
) -> None:
    updated = await conn.fetchval(
        """
        UPDATE import_snapshots
        SET owner_id = $4::uuid, heartbeat_at = now(),
            manifest = jsonb_set(manifest, '{generation_state}', '"validated"'::jsonb, true)
        WHERE id = $1
          AND generation_token = $2::uuid
          AND owner_id = $3::uuid
          AND status = 'processing'
          AND manifest->>'generation_state' = 'promoting'
        RETURNING id
        """,
        snapshot_id,
        generation_token,
        current_owner_id,
        previous_owner_id,
    )
    if updated is None:
        raise SalesGenerationConflictError("Sales generation claim changed concurrently")


async def fail_sales_generation(
    conn: asyncpg.Connection,
    *,
    snapshot_id: int,
    generation_token: str,
    owner_id: str,
    error: str,
) -> None:
    updated = await conn.fetchval(
        """
        UPDATE import_snapshots
        SET status = 'failed',
            rows_imported = 0,
            error_message = $4,
            heartbeat_at = now(),
            finished_at = now(),
            lease_until = now()
        WHERE id = $1
          AND generation_token = $2::uuid
          AND owner_id = $3::uuid
          AND status = 'processing'
          AND lease_until > now()
        RETURNING id
        """,
        snapshot_id,
        generation_token,
        owner_id,
        error[:500],
    )
    if updated is None:
        raise SalesGenerationConflictError("Stale worker cannot finalize sales generation")


async def _upsert_stores_from_stage(
    conn: asyncpg.Connection,
    *,
    snapshot_id: int,
    import_month: str,
) -> None:
    latest_completed_month = await conn.fetchval(
        "SELECT MAX(import_month) FROM import_snapshots WHERE status = 'completed'"
    )
    updates_current_structure = (
        latest_completed_month is None or import_month >= str(latest_completed_month)
    )
    await conn.execute(
        """
        WITH source AS (
            SELECT DISTINCT ON (site_code)
                   site_code, locatie, firma, regional, asm
            FROM sales_import_stage_rows
            WHERE snapshot_id = $1
            ORDER BY site_code, row_number
        )
        INSERT INTO stores (
            site_code, locatie, firma, regional, asm,
            first_seen_month, last_seen_month, is_active
        )
        SELECT site_code, locatie, firma, regional, asm, $2, $2, $3
        FROM source
        ON CONFLICT (site_code) DO UPDATE
        SET locatie = CASE WHEN $3 THEN EXCLUDED.locatie ELSE stores.locatie END,
            firma = CASE WHEN $3 THEN EXCLUDED.firma ELSE stores.firma END,
            regional = CASE WHEN $3 THEN EXCLUDED.regional ELSE stores.regional END,
            asm = CASE WHEN $3 THEN EXCLUDED.asm ELSE stores.asm END,
            is_active = stores.is_active,
            first_seen_month = LEAST(stores.first_seen_month, EXCLUDED.first_seen_month),
            last_seen_month = GREATEST(stores.last_seen_month, EXCLUDED.last_seen_month),
            updated_at = now()
        """,
        snapshot_id,
        import_month,
        updates_current_structure,
    )


async def _advance_sales_head(
    conn: asyncpg.Connection,
    *,
    import_month: str,
    snapshot_id: int,
    generation_token: str,
    owner_id: str,
    expected_revision: int,
) -> tuple[int | None, int]:
    try:
        head = await conn.fetchrow(
            """
            SELECT previous_snapshot_id, revision
            FROM advance_sales_generation_head($1, $2, $3::uuid, $4::uuid, $5)
            """,
            import_month,
            snapshot_id,
            generation_token,
            owner_id,
            expected_revision,
        )
    except asyncpg.PostgresError as exc:
        raise SalesGenerationConflictError("Sales generation head CAS failed") from exc
    if head is None:
        raise SalesGenerationConflictError("Sales generation head CAS returned no result")
    previous_snapshot_id = head["previous_snapshot_id"]
    return (
        int(previous_snapshot_id) if previous_snapshot_id is not None else None,
        int(head["revision"]),
    )


async def _verify_stage_controls(
    conn: asyncpg.Connection,
    *,
    snapshot_id: int,
    manifest: dict[str, Any],
) -> None:
    controls = await conn.fetchrow(
        """
        SELECT COUNT(*)::integer AS row_count,
               COUNT(DISTINCT site_code)::integer AS store_count,
               COALESCE(SUM(quantity), 0)::bigint AS total_quantity,
               COALESCE(SUM(total_value), 0)::numeric AS total_value,
               MAX(sale_date) AS max_sale_date
        FROM sales_import_stage_rows
        WHERE snapshot_id = $1
        """,
        snapshot_id,
    )
    if controls is None:
        raise SalesGenerationValidationError("Sales staging controls are missing")
    expected = (
        int(manifest["rows_imported"]),
        int(manifest["store_count"]),
        int(manifest["total_quantity"]),
        Decimal(str(manifest["total_value"])),
        str(manifest["max_sale_date"]),
    )
    actual = (
        int(controls["row_count"]),
        int(controls["store_count"]),
        int(controls["total_quantity"]),
        Decimal(controls["total_value"]),
        controls["max_sale_date"].isoformat() if controls["max_sale_date"] else None,
    )
    if actual != expected:
        raise SalesGenerationValidationError(
            f"Sales staging control totals mismatch: expected={expected}, actual={actual}"
        )


_PROMOTION_SQL_1 = """
            SELECT id, import_month, manifest, manifest_sha256, source_sha256,
                   expected_head_revision, is_month_final,
                   source_artifact_required, source_artifact_state,
                   source_artifact_sha256, source_artifact_bytes,
                   source_artifact_retained_path
            FROM import_snapshots
            WHERE id = $1
              AND generation_token = $2::uuid
              AND owner_id = $3::uuid
              AND status = 'processing'
              AND lease_until > now()
            FOR UPDATE
            """

_PROMOTION_SQL_2 = """
            UPDATE import_snapshots
            SET status = 'completed',
                rows_imported = $4,
                previous_snapshot_id = $5,
                approved_by_sub = $6,
                override_reason = $7,
                promoted_at = now(),
                heartbeat_at = now(),
                finished_at = now(),
                lease_until = now(),
                error_message = NULL,
                manifest = jsonb_set(manifest, '{generation_state}', '"promoted"'::jsonb, true)
            WHERE id = $1
              AND generation_token = $2::uuid
              AND owner_id = $3::uuid
              AND status = 'processing'
              AND lease_until > now()
            RETURNING id
            """

_PROMOTION_SQL_3 = """
            SELECT record_sales_generation_promotion(
                $1, $2, $3, $4, $5, $6, $7
            )
            """


async def promote_sales_generation(
    conn: asyncpg.Connection,
    *,
    snapshot_id: int,
    generation_token: str,
    owner_id: str,
    expected_manifest_sha256: str,
    requested_by_sub: str,
    override_reason: str | None = None,
    action: str = "promote",
) -> tuple[int, int]:
    actor = requested_by_sub.strip()
    if not actor:
        raise ValueError("requested_by_sub is required")
    if action not in {"promote", "rollback"}:
        raise ValueError("Invalid sales generation action")
    reason = override_reason.strip() if override_reason else None
    async with conn.transaction():
        row = await conn.fetchrow(
            _PROMOTION_SQL_1,
            snapshot_id,
            generation_token,
            owner_id,
        )
        if row is None:
            raise SalesGenerationConflictError("Sales generation lease was lost before promote")
        if row["manifest_sha256"] != expected_manifest_sha256:
            raise SalesGenerationConflictError("Approved sales manifest does not match staged generation")
        manifest = row["manifest"]
        if isinstance(manifest, str):
            manifest = json.loads(manifest)
        manifest = dict(manifest or {})
        if row["source_artifact_required"]:
            if (
                row["source_artifact_state"] != "artifact_retained"
                or row["source_artifact_sha256"] != row["source_sha256"]
                or row["source_artifact_bytes"] is None
                or not row["source_artifact_retained_path"]
            ):
                raise SalesGenerationValidationError(
                    "Promovarea cere un artefact sales reținut și verificat"
                )
            from services.jobs import verify_sales_import_artifact

            await asyncio.to_thread(
                verify_sales_import_artifact,
                str(row["source_artifact_retained_path"]),
                str(row["source_sha256"]),
                int(row["source_artifact_bytes"]),
            )
        if manifest_requires_override(manifest):
            raise SalesGenerationValidationError(
                "Promovarea este blocată de contradicții structurale ale generației"
            )
        await _verify_stage_controls(conn, snapshot_id=snapshot_id, manifest=manifest)
        import_month = str(row["import_month"])
        previous_snapshot_id, revision = await _advance_sales_head(
            conn,
            import_month=import_month,
            snapshot_id=snapshot_id,
            generation_token=generation_token,
            owner_id=owner_id,
            expected_revision=int(row["expected_head_revision"]),
        )
        await _upsert_stores_from_stage(
            conn,
            snapshot_id=snapshot_id,
            import_month=import_month,
        )
        await conn.execute(
            "DELETE FROM sales_transactions WHERE import_month = $1",
            import_month,
        )
        rows_imported = await copy_staged_generation_to_live(
            conn,
            snapshot_id=snapshot_id,
            import_month=import_month,
        )
        if rows_imported != int(manifest["rows_imported"]):
            raise SalesGenerationValidationError("Promoted row count differs from approved manifest")
        await rebuild_reporting_month(conn, import_month)
        await rebuild_agent_lifecycle_reporting(conn)
        updated = await conn.fetchval(
            _PROMOTION_SQL_2,
            snapshot_id,
            generation_token,
            owner_id,
            rows_imported,
            previous_snapshot_id,
            actor,
            reason,
        )
        if updated is None:
            raise SalesGenerationConflictError("Stale worker cannot finalize promoted generation")
        await conn.fetchval(
            _PROMOTION_SQL_3,
            import_month,
            previous_snapshot_id,
            snapshot_id,
            revision,
            action,
            actor,
            reason,
        )
    return rows_imported, revision


async def rollback_sales_generation(
    conn: asyncpg.Connection,
    *,
    current_snapshot_id: int,
    current_generation_token: str,
    expected_manifest_sha256: str,
    requested_by_sub: str,
    reason: str,
) -> tuple[int, int, int]:
    from services.sales_generation_rollback import rollback_sales_generation as execute

    return await execute(
        conn,
        current_snapshot_id=current_snapshot_id,
        current_generation_token=current_generation_token,
        expected_manifest_sha256=expected_manifest_sha256,
        requested_by_sub=requested_by_sub,
        reason=reason,
        promote=promote_sales_generation,
    )
