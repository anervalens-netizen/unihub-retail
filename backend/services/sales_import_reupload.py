from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, status

from models import (
    ImportCoverageReport,
    ImportJobStatus,
    ImportResponse,
    SalesGenerationManifest,
)


VerifyArtifact = Callable[[str, str, int | None], int]
StageArtifact = Callable[[bytes, str], Path]
RemoveArtifact = Callable[[str | Path], None]
RetainArtifact = Callable[..., Path]
AttachSource = Callable[..., Awaitable[None]]
MarkRetained = Callable[..., Awaitable[None]]


def _validated_response(recovered: Any) -> ImportJobStatus:
    manifest = recovered["manifest"]
    if isinstance(manifest, str):
        manifest = json.loads(manifest)
    coverage = recovered["coverage_report"]
    if isinstance(coverage, str):
        coverage = json.loads(coverage)
    manifest = dict(manifest or {})
    return ImportJobStatus(
        job_id=f"sales-staged:{int(recovered['id'])}",
        status="complete",
        result=ImportResponse(
            import_month=str(recovered["import_month"]),
            rows_in_file=int(recovered["rows_in_file"] or 0),
            rows_imported=int(recovered["rows_imported"] or 0),
            rows_filtered=int(manifest.get("rows_filtered", 0)),
            store_count=int(manifest.get("store_count", 0)),
            agent_count=int(manifest.get("agent_count", 0)),
            snapshot_id=int(recovered["id"]),
            filename=str(recovered["filename"]),
            is_month_final=bool(recovered["is_month_final"]),
            coverage_report=ImportCoverageReport.model_validate(
                coverage or {}
            ),
            generation_state="validated",
            generation_token=str(recovered["generation_token"]),
            manifest_sha256=str(recovered["manifest_sha256"]),
            manifest=SalesGenerationManifest.model_validate(manifest),
        ),
    )


async def _retain_recovered_source(
    recovered: Any,
    *,
    pool: Any,
    content: bytes,
    source_sha256: str,
    spool_path: Path,
    retain: RetainArtifact,
    attach: AttachSource,
    mark_retained: MarkRetained,
) -> None:
    generation_token = str(recovered["generation_token"])
    owner_id = str(recovered["owner_id"])
    async with pool.acquire() as conn:
        await attach(
            conn,
            snapshot_id=int(recovered["id"]),
            generation_token=generation_token,
            owner_id=owner_id,
            source_spool_path=str(spool_path),
            source_sha256=source_sha256,
            source_byte_size=len(content),
        )
    retained_path = await asyncio.to_thread(
        retain,
        spool_path,
        import_month=str(recovered["import_month"]),
        snapshot_id=int(recovered["id"]),
        expected_digest=source_sha256,
        expected_bytes=len(content),
    )
    async with pool.acquire() as conn:
        await mark_retained(
            conn,
            snapshot_id=int(recovered["id"]),
            generation_token=generation_token,
            owner_id=owner_id,
            retained_path=str(retained_path),
            source_sha256=source_sha256,
            source_byte_size=len(content),
        )


async def recover_validated_sales_import(
    recovered: Any,
    *,
    pool: Any,
    content: bytes,
    source_sha256: str,
    verify: VerifyArtifact,
    stage: StageArtifact,
    remove: RemoveArtifact,
    retain: RetainArtifact,
    attach: AttachSource,
    mark_retained: MarkRetained,
) -> ImportJobStatus:
    expected_path = str(recovered["source_spool_path"])
    artifact_required = bool(recovered["source_artifact_required"])
    artifact_state = recovered["source_artifact_state"]
    if artifact_required and artifact_state == "artifact_retained":
        await asyncio.to_thread(
            verify,
            expected_path,
            source_sha256,
            len(content),
        )
        return _validated_response(recovered)
    spool_path = await asyncio.to_thread(
        stage,
        content,
        source_sha256,
    )
    retained_path = spool_path.parent / "retained" / f"{source_sha256}.source"
    allowed_paths = (
        {str(spool_path), str(retained_path)}
        if artifact_required
        else {str(spool_path)}
    )
    if expected_path not in allowed_paths:
        await asyncio.to_thread(remove, spool_path)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Generatia validata foloseste alta cale de sursa; "
                "recovery automat refuzat"
            ),
        )
    if artifact_required:
        await _retain_recovered_source(
            recovered,
            pool=pool,
            content=content,
            source_sha256=source_sha256,
            spool_path=spool_path,
            retain=retain,
            attach=attach,
            mark_retained=mark_retained,
        )
    return _validated_response(recovered)

