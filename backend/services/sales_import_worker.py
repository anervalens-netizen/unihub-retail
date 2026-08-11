from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import date
import json
from typing import Any

from request_context import bind_request_id, reset_request_id
from services.sales_artifacts import (
    read_sales_import_spool_file,
    resolve_sales_import_artifact,
    retain_sales_import_spool_file,
    verify_sales_import_artifact,
)


def _validate_request(
    spool_path: str,
    source_digest: str,
    source_byte_size: int,
    filename: str,
) -> None:
    if not isinstance(spool_path, str) or not spool_path:
        raise ValueError("Sales import worker requires a durable spool path")
    if not isinstance(source_digest, str) or not source_digest:
        raise ValueError("Sales import worker requires a source digest")
    if (
        isinstance(source_byte_size, bool)
        or not isinstance(source_byte_size, int)
        or source_byte_size < 0
    ):
        raise ValueError("Sales import worker requires a valid source size")
    if not filename:
        raise ValueError("Sales import filename is missing")


def _recovered_import_result(recovered: dict[str, Any]) -> Any:
    from services.importer import ImportResult

    manifest = recovered.get("manifest")
    if isinstance(manifest, str):
        manifest = json.loads(manifest)
    coverage_report = recovered.get("coverage_report")
    if isinstance(coverage_report, str):
        coverage_report = json.loads(coverage_report)
    normalized_manifest = dict(manifest or {})
    return ImportResult(
        import_month=str(recovered["import_month"]),
        rows_in_file=int(recovered.get("rows_in_file") or 0),
        rows_imported=int(recovered.get("rows_imported") or 0),
        rows_filtered=int(normalized_manifest.get("rows_filtered", 0)),
        store_count=int(normalized_manifest.get("store_count", 0)),
        agent_count=int(normalized_manifest.get("agent_count", 0)),
        snapshot_id=int(recovered["id"]),
        filename=str(recovered["filename"]),
        is_month_final=bool(recovered["is_month_final"]),
        coverage_report=dict(coverage_report or {}),
        generation_state="validated",
        generation_token=str(recovered["generation_token"]),
        owner_id=str(recovered["owner_id"]),
        manifest_sha256=str(recovered["manifest_sha256"]),
        manifest=normalized_manifest,
    )


async def _recover_validated_generation(
    conn: Any,
    *,
    queued_path: str,
    artifact_path: Any,
    source_digest: str,
    source_byte_size: int,
    cutoff: date | None,
) -> Any | None:
    import services.sales_generation_flow as generation_flow

    recovered = await generation_flow.find_recoverable_sales_generation_for_artifact_retain(
        conn,
        queued_path=queued_path,
        retained_path=str(artifact_path),
        source_sha256=source_digest,
        source_byte_size=source_byte_size,
        cutoff_date=cutoff,
    )
    if recovered is None:
        return None
    retained_path = await asyncio.to_thread(
        retain_sales_import_spool_file,
        artifact_path,
        import_month=str(recovered["import_month"]),
        snapshot_id=int(recovered["id"]),
        expected_digest=source_digest,
        expected_bytes=source_byte_size,
    )
    await generation_flow.mark_sales_generation_artifact_retained(
        conn,
        snapshot_id=int(recovered["id"]),
        generation_token=str(recovered["generation_token"]),
        owner_id=str(recovered["owner_id"]),
        retained_path=str(retained_path),
        source_sha256=source_digest,
        source_byte_size=source_byte_size,
    )
    return _recovered_import_result(dict(recovered))


async def _stage_and_retain(
    conn: Any,
    *,
    artifact_path: Any,
    source_digest: str,
    source_byte_size: int,
    filename: str,
    cutoff: date | None,
    actor: str,
) -> Any:
    import services.importer as importer
    import services.sales_generation_flow as generation_flow

    verified_size = await asyncio.to_thread(
        verify_sales_import_artifact,
        artifact_path,
        source_digest,
        source_byte_size,
    )
    file_content = await asyncio.to_thread(
        read_sales_import_spool_file,
        str(artifact_path),
        source_digest,
    )
    result = await importer.import_sales_file(
        conn,
        file_content,
        filename=filename,
        cutoff_date=cutoff,
        stage_only=True,
        requested_by_sub=actor,
        source_artifact_required=True,
        source_artifact_path=str(artifact_path),
        source_artifact_bytes=verified_size,
    )
    assert result.generation_token is not None
    assert result.owner_id is not None
    retained_path = await asyncio.to_thread(
        retain_sales_import_spool_file,
        artifact_path,
        import_month=result.import_month,
        snapshot_id=result.snapshot_id,
        expected_digest=source_digest,
        expected_bytes=verified_size,
    )
    await generation_flow.mark_sales_generation_artifact_retained(
        conn,
        snapshot_id=result.snapshot_id,
        generation_token=result.generation_token,
        owner_id=result.owner_id,
        retained_path=str(retained_path),
        source_sha256=source_digest,
        source_byte_size=verified_size,
    )
    return result


async def _execute_import(
    conn: Any,
    *,
    spool_path: str,
    artifact_path: Any,
    source_digest: str,
    source_byte_size: int,
    filename: str,
    cutoff: date | None,
    actor: str,
) -> Any:
    recovered = await _recover_validated_generation(
        conn,
        queued_path=spool_path,
        artifact_path=artifact_path,
        source_digest=source_digest,
        source_byte_size=source_byte_size,
        cutoff=cutoff,
    )
    if recovered is not None:
        return recovered
    return await _stage_and_retain(
        conn,
        artifact_path=artifact_path,
        source_digest=source_digest,
        source_byte_size=source_byte_size,
        filename=filename,
        cutoff=cutoff,
        actor=actor,
    )


async def run_sales_import_job(
    ctx: dict[str, Any],
    spool_path: str,
    source_digest: str,
    source_byte_size: int,
    filename: str,
    request_id: str | None = None,
    cutoff_date_iso: str | None = None,
    requested_by_sub: str | None = None,
) -> dict[str, Any]:
    _validate_request(spool_path, source_digest, source_byte_size, filename)
    token = bind_request_id(request_id) if request_id else None
    cutoff = date.fromisoformat(cutoff_date_iso) if cutoff_date_iso else None
    try:
        artifact_path = await asyncio.to_thread(
            resolve_sales_import_artifact,
            spool_path,
            source_digest,
            source_byte_size,
        )
        async def execute(conn: Any) -> Any:
            return await _execute_import(
                conn,
                spool_path=spool_path,
                artifact_path=artifact_path,
                source_digest=source_digest,
                source_byte_size=source_byte_size,
                filename=filename,
                cutoff=cutoff,
                actor=requested_by_sub or "unknown",
            )

        conn = ctx.get("db_conn")
        if conn is not None:
            result = await execute(conn)
        else:
            from db.connection import get_pool

            pool = await get_pool()
            async with pool.acquire() as pooled_conn:
                result = await execute(pooled_conn)
        return asdict(result)
    finally:
        # A failed ARQ attempt must retain the exact queued bytes for retry.
        # Success atomically moves them into the retained content-addressed
        # namespace; bounded startup cleanup removes abandoned failed spools.
        if token is not None:
            reset_request_id(token)
