"""Durable orchestration and private artifact lifecycle for complex XLSX exports."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import stat
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, IO, Literal, cast
from uuid import uuid4

import asyncpg

from business_clock import business_now
from models import ExportOperationResponse
from repositories.export_operations import ExportOperationsRepository
from repositories.exports import ExportsRepository
from services.exports import ExportValidationError, ExportsService, XlsxArtifact
from services.exports.artifact import XLSX_STREAM_CHUNK_BYTES
from services.exports.validation import EXPORT_MAX_OUTPUT_BYTES
from services.exports.metrics import (
    EXPORT_CELLS,
    EXPORT_LAST_BUILD_SECONDS,
    EXPORT_OUTPUT_BYTES,
    EXPORT_PEAK_RSS_BYTES,
)
from services.jobs import JobPublishUncertainError, enqueue_complex_export


EXPORT_ARTIFACT_KEY = re.compile(r"^[0-9a-f]{32}\.xlsx$")
EXPORT_ARTIFACT_TTL_DEFAULT_SECONDS = 60 * 60
EXPORT_ARTIFACT_TTL_MIN_SECONDS = 5 * 60
EXPORT_ARTIFACT_TTL_MAX_SECONDS = 24 * 60 * 60
EXPORT_EXECUTION_LEASE_SECONDS = 5 * 60
# Three globally active operations × the configured 7,200s ARQ hard maximum,
# plus a 10-minute scheduling margin. Normal deployments use a much lower
# 1,800s job timeout, but stale recovery must also remain correct at the cap.
EXPORT_QUEUE_STALE_SECONDS = 3 * 7_200 + 10 * 60
EXPORT_ORPHAN_GRACE_SECONDS = 60 * 60


class ExportOperationNotFoundError(LookupError):
    pass


class ExportOperationConflictError(RuntimeError):
    pass


class ExportArtifactExpiredError(RuntimeError):
    pass


class ExportArtifactIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StoredExportArtifact:
    key: str
    sha256: str
    size: int
    filename: str
    peak_rss_bytes: int
    build_seconds: float
    cell_count: int


def _bounded_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def export_artifact_ttl_seconds() -> int:
    return _bounded_env(
        "EXPORT_ARTIFACT_TTL_SECONDS",
        EXPORT_ARTIFACT_TTL_DEFAULT_SECONDS,
        EXPORT_ARTIFACT_TTL_MIN_SECONDS,
        EXPORT_ARTIFACT_TTL_MAX_SECONDS,
    )


def get_export_artifact_dir() -> Path:
    configured = os.getenv("EXPORT_ARTIFACT_DIR")
    root = (
        Path(configured).expanduser()
        if configured
        else Path(__file__).resolve().parents[2] / "data" / "export_artifacts"
    ).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    return root


def _artifact_path(key: str) -> Path:
    if not EXPORT_ARTIFACT_KEY.fullmatch(key):
        raise ExportArtifactIntegrityError("Invalid export artifact identity")
    root = get_export_artifact_dir()
    candidate = root / key
    if candidate.parent != root:
        raise ExportArtifactIntegrityError("Export artifact escapes its private directory")
    return candidate


def remove_export_artifact(key: str) -> None:
    path = _artifact_path(key)
    if path.is_symlink():
        raise ExportArtifactIntegrityError("Export artifact symlink is not allowed")
    path.unlink(missing_ok=True)


def persist_export_artifact(artifact: XlsxArtifact) -> StoredExportArtifact:
    """Copy an attested process result into the private durable artifact root."""
    root = get_export_artifact_dir()
    key = f"{uuid4().hex}.xlsx"
    destination = _artifact_path(key)
    temporary = root / f".{key}.{uuid4().hex}.tmp"
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("xb") as output:
            temporary.chmod(0o600)
            for chunk in artifact.iter_chunks():
                size += len(chunk)
                if size > EXPORT_MAX_OUTPUT_BYTES:
                    raise ExportArtifactIntegrityError("Export artifact exceeded output budget")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        computed_sha256 = digest.hexdigest()
        if size <= 0 or size != artifact.size:
            raise ExportArtifactIntegrityError("Export artifact size changed before persistence")
        if artifact.sha256 is None or computed_sha256 != artifact.sha256:
            raise ExportArtifactIntegrityError("Export artifact digest changed before persistence")
        if (
            artifact.peak_rss_bytes is None
            or artifact.peak_rss_bytes <= 0
            or artifact.build_seconds is None
            or artifact.build_seconds < 0
            or artifact.cell_count is None
            or artifact.cell_count < 0
        ):
            raise ExportArtifactIntegrityError("Export artifact metrics are missing")
        temporary.replace(destination)
        destination.chmod(0o600)
        descriptor = os.open(root, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return StoredExportArtifact(
            key=key,
            sha256=computed_sha256,
            size=size,
            filename=artifact.filename,
            peak_rss_bytes=artifact.peak_rss_bytes,
            build_seconds=artifact.build_seconds,
            cell_count=artifact.cell_count,
        )
    except BaseException:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise


def open_verified_export_artifact(
    *,
    key: str,
    expected_sha256: str,
    expected_size: int,
    filename: str,
) -> XlsxArtifact:
    path = _artifact_path(key)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ExportArtifactIntegrityError("Export artifact is unavailable") from exc
    stream: IO[bytes] = os.fdopen(descriptor, "rb")
    try:
        file_stat = os.fstat(stream.fileno())
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size != expected_size:
            raise ExportArtifactIntegrityError("Export artifact size verification failed")
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(XLSX_STREAM_CHUNK_BYTES), b""):
            digest.update(chunk)
        if digest.hexdigest() != expected_sha256:
            raise ExportArtifactIntegrityError("Export artifact hash verification failed")
        stream.seek(0)
        return XlsxArtifact(stream=stream, filename=filename, size=expected_size)
    except BaseException:
        stream.close()
        raise


async def cleanup_export_operations(repo: ExportOperationsRepository) -> None:
    await repo.reconcile_stale(queued_timeout_seconds=EXPORT_QUEUE_STALE_SECONDS)
    # Expiry is claimed in DB first. A crash after this point can only leave an
    # inaccessible orphan file, which the age-based sweep removes later.
    for candidate in await repo.claim_expired():
        key = str(candidate.get("artifact_key") or "")
        if not key:
            continue
        await asyncio.to_thread(remove_export_artifact, key)


async def sweep_orphan_export_artifacts(repo: ExportOperationsRepository) -> None:
    """Filesystem sweep reserved for operations-worker startup/job boundaries."""
    # Recover private artifacts left between atomic rename and DB completion.
    active_keys = await repo.active_artifact_keys()
    cutoff = time.time() - max(EXPORT_ORPHAN_GRACE_SECONDS, export_artifact_ttl_seconds())
    root = get_export_artifact_dir()
    for path in root.iterdir():
        if not path.is_file() or path.is_symlink() or path.stat().st_mtime >= cutoff:
            continue
        if path.name in active_keys:
            continue
        if EXPORT_ARTIFACT_KEY.fullmatch(path.name) or path.name.startswith("."):
            path.unlink(missing_ok=True)

    # A cancelled ProcessPool call may finish after its caller disappeared.
    temp_root = Path(tempfile.gettempdir())
    for path in temp_root.glob("unihub-export-*.xlsx"):
        if path.is_file() and not path.is_symlink() and path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)


def public_export_operation(operation: dict[str, Any]) -> ExportOperationResponse:
    status = str(operation["status"])
    if status == "completed" and _operation_is_expired(operation):
        status = "expired"
    if status == "completed":
        peak_rss = int(operation.get("peak_rss_bytes") or 0)
        build_seconds = float(operation.get("build_seconds") or 0)
        cell_count = int(operation.get("cell_count") or 0)
        output_bytes = int(operation.get("artifact_size") or 0)
        if peak_rss > 0:
            EXPORT_PEAK_RSS_BYTES.set(peak_rss)
        EXPORT_LAST_BUILD_SECONDS.set(build_seconds)
        EXPORT_CELLS.set(cell_count)
        EXPORT_OUTPUT_BYTES.set(output_bytes)
    return ExportOperationResponse(
        id=int(operation["id"]),
        kind=cast(Literal["daily_metrics", "daily_comparison"], str(operation["kind"])),
        status=cast(
            Literal["queued", "running", "completed", "failed", "cancelled", "expired"],
            status,
        ),
        job_id=str(operation["job_id"]),
        filename=operation.get("download_filename"),
        artifact_size=operation.get("artifact_size"),
        artifact_sha256=operation.get("artifact_sha256"),
        peak_rss_bytes=operation.get("peak_rss_bytes"),
        build_seconds=operation.get("build_seconds"),
        cell_count=operation.get("cell_count"),
        error_code=operation.get("error_code"),
        created_at=operation["created_at"],
        started_at=operation.get("started_at"),
        finished_at=operation.get("finished_at"),
        expires_at=operation.get("expires_at"),
        can_download=status == "completed",
    )


class ExportOperationsService:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.repo = ExportOperationsRepository(pool)

    async def reserve(
        self,
        request: dict[str, Any],
        *,
        requested_by_sub: str,
    ) -> ExportOperationResponse:
        kind = ExportsService(ExportsRepository(self.pool)).validate_complex_request(request)
        encoded = json.dumps(request, sort_keys=True, separators=(",", ":"))
        operation = await self.repo.reserve(
            kind=kind,
            request_payload=request,
            request_sha256=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            requested_by_sub=requested_by_sub,
        )
        operation_id = int(operation["id"])
        try:
            await enqueue_complex_export(operation_id)
        except JobPublishUncertainError as exc:
            exc.attach_operation_id(operation_id)
            raise
        except Exception:
            await self.repo.fail_queued(operation_id, error_code="queue_publish_failed")
            raise
        current = await self.repo.get_owned(operation_id, requested_by_sub=requested_by_sub)
        if current is None:
            raise RuntimeError("Export operation disappeared after enqueue")
        return public_export_operation(current)

    async def status(
        self,
        operation_id: int,
        *,
        requested_by_sub: str,
    ) -> ExportOperationResponse:
        operation = await self.repo.get_owned(operation_id, requested_by_sub=requested_by_sub)
        if operation is None:
            raise ExportOperationNotFoundError()
        return public_export_operation(operation)

    async def resumable(self, *, requested_by_sub: str) -> ExportOperationResponse | None:
        operation = await self.repo.get_resumable_owned(requested_by_sub=requested_by_sub)
        return public_export_operation(operation) if operation is not None else None

    async def cancel(
        self,
        operation_id: int,
        *,
        requested_by_sub: str,
    ) -> ExportOperationResponse:
        operation = await self.repo.cancel_owned(
            operation_id,
            requested_by_sub=requested_by_sub,
        )
        if operation is None:
            current = await self.repo.get_owned(operation_id, requested_by_sub=requested_by_sub)
            if current is None:
                raise ExportOperationNotFoundError()
            raise ExportOperationConflictError("Exportul nu mai poate fi anulat.")
        return public_export_operation(operation)

    async def download(
        self,
        operation_id: int,
        *,
        requested_by_sub: str,
    ) -> XlsxArtifact:
        operation = await self.repo.claim_download_owned(
            operation_id,
            requested_by_sub=requested_by_sub,
        )
        if operation is None:
            current = await self.repo.get_owned(
                operation_id,
                requested_by_sub=requested_by_sub,
            )
            if current is None:
                raise ExportOperationNotFoundError()
            if current["status"] == "expired" or _operation_is_expired(current):
                raise ExportArtifactExpiredError()
            if current["status"] != "completed":
                raise ExportOperationConflictError(
                    "Artifactul exportului nu este finalizat sau a expirat."
                )
            # A claim suppresses generic auto-discovery only. Explicit,
            # owner-bound retries remain available until TTL after a broken
            # browser/transport download.
            operation = current
        key = str(operation.get("artifact_key") or "")
        digest = str(operation.get("artifact_sha256") or "")
        size = int(operation.get("artifact_size") or 0)
        filename = str(operation.get("download_filename") or "export_retail.xlsx")
        try:
            return await asyncio.to_thread(
                open_verified_export_artifact,
                key=key,
                expected_sha256=digest,
                expected_size=size,
                filename=filename,
            )
        except ExportArtifactIntegrityError:
            if await self.repo.mark_corrupt(operation_id, artifact_key=key):
                await asyncio.to_thread(remove_export_artifact, key)
            raise


def _operation_is_expired(operation: dict[str, Any]) -> bool:
    expires_at = operation.get("expires_at")
    if not isinstance(expires_at, datetime):
        return operation.get("status") == "completed"
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        return True
    return expires_at <= business_now().astimezone(expires_at.tzinfo)
