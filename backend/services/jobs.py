from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from hashlib import sha256
from contextlib import suppress
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.constants import result_key_prefix
from arq.jobs import Job, JobStatus as ArqJobStatus
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from config import ConfigError, load_runtime_config
from request_context import get_request_id


logger = logging.getLogger(__name__)


class JobQueueUnavailableError(HTTPException):
    """Queue-ul nu este disponibil; endpointurile de enqueue răspund 503."""

    def __init__(self) -> None:
        super().__init__(status_code=503, detail="Job backend unavailable")


class JobPublishUncertainError(HTTPException):
    """Publish-ul poate fi acceptat, dar confirmarea nu a fost posibilă."""

    def __init__(
        self,
        *,
        job_id: str | None = None,
        operation_id: int | None = None,
    ) -> None:
        self.job_id = job_id
        self.operation_id = operation_id
        super().__init__(status_code=503, detail=self._detail())

    def _detail(self) -> dict[str, object | None]:
        return {
            "status": "unknown",
            "job_id": self.job_id,
            "operation_id": self.operation_id,
        }

    def attach_operation_id(self, operation_id: int) -> None:
        self.operation_id = operation_id
        object.__setattr__(self, "detail", self._detail())


ARQ_TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (
    RedisConnectionError,
    RedisTimeoutError,
    ConnectionError,
    TimeoutError,
    OSError,
)


class JobStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    NOT_FOUND = "not_found"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    UNKNOWN = "unknown"


@dataclass
class JobResult:
    job_id: str
    status: JobStatus
    result: Optional[dict] = None
    error: Optional[str] = None


@dataclass
class GrileEnqueueResult:
    status: str
    run_id: int
    job: Job | None = None
    run: dict | None = None


@dataclass
class GrileStoreRefreshEnqueueResult:
    status: str
    operation_id: int
    job: Job | None = None
    operation: dict | None = None


@dataclass
class GrileMonthlyEnqueueResult:
    status: str
    operation_id: int
    job: Job | None = None
    job_id: str | None = None
    operation: dict | None = None


@dataclass
class GrileTargetSyncEnqueueResult:
    status: str
    operation_id: int
    job: Job | None = None
    operation: dict | None = None


_VALKEY_SETTINGS: Optional[RedisSettings] = None
SALES_IMPORT_QUEUE_NAME = "arq:retail:imports"
DEFAULT_SALES_IMPORT_SPOOL_MAX_AGE_SECONDS = 24 * 60 * 60
_SALES_ARTIFACT_DIGEST = re.compile(r"^[0-9a-f]{64}$")
MONTHLY_QUEUE_PUBLISH_FAILED = "monthly_queue_publish_failed"


class SalesImportArtifactError(RuntimeError):
    pass


class SalesImportArtifactConflictError(SalesImportArtifactError):
    pass


def get_sales_import_spool_dir() -> Path:
    configured = os.getenv("SALES_IMPORT_SPOOL_DIR")
    path = (
        Path(configured).expanduser()
        if configured
        else Path(__file__).resolve().parents[2] / "data" / "import_spool"
    )
    return path.resolve()


def _sales_spool_path(path: str | Path) -> Path:
    root = get_sales_import_spool_dir()
    raw = Path(path)
    if raw.is_symlink():
        raise SalesImportArtifactError("Sales import spool symlink is not allowed")
    candidate = raw.resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Sales import spool path escapes the configured directory")
    return candidate


def _artifact_digest_from_path(path: Path) -> str:
    digest = path.name.rsplit(".", 1)[0]
    if not _SALES_ARTIFACT_DIGEST.fullmatch(digest):
        raise SalesImportArtifactError("Sales import artifact name is not content-addressed")
    return digest


def _file_digest_and_size(path: Path) -> tuple[str, int]:
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise SalesImportArtifactError("Sales import artifact is not a regular file")
    digest = sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _fsync_file(path: Path) -> None:
    with path.open("rb") as source:
        os.fsync(source.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def verify_sales_import_artifact(
    path: str | Path,
    expected_digest: str,
    expected_bytes: int | None = None,
) -> int:
    candidate = _sales_spool_path(path)
    digest, size = _file_digest_and_size(candidate)
    if digest != expected_digest or (expected_bytes is not None and size != expected_bytes):
        raise SalesImportArtifactError("Sales import artifact integrity check failed")
    return size


def stage_sales_import_spool_file(content: bytes, digest: str) -> Path:
    if not _SALES_ARTIFACT_DIGEST.fullmatch(digest):
        raise ValueError("Invalid sales import source digest")
    spool_dir = get_sales_import_spool_dir()
    spool_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    spool_dir.chmod(0o700)
    destination = spool_dir / f"{digest}.upload"
    temporary = spool_dir / f".{digest}.{uuid4().hex}.tmp"
    if destination.exists():
        actual_digest, actual_size = _file_digest_and_size(destination)
        if actual_digest != digest or actual_size != len(content):
            raise SalesImportArtifactConflictError("Conflicting content-addressed sales source")
        destination.chmod(0o600)
        _fsync_file(destination)
        _fsync_directory(spool_dir)
        return destination
    try:
        temporary.write_bytes(content)
        temporary.chmod(0o600)
        _fsync_file(temporary)
        actual_digest, actual_size = _file_digest_and_size(temporary)
        if actual_digest != digest or actual_size != len(content):
            raise SalesImportArtifactError("Staged sales source integrity check failed")
        temporary.replace(destination)
        destination.chmod(0o600)
        _fsync_file(destination)
        _fsync_directory(spool_dir)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def remove_sales_import_spool_file(path: str | Path) -> None:
    candidate = _sales_spool_path(path)
    candidate.unlink(missing_ok=True)


def retain_sales_import_spool_file(
    path: str | Path,
    *,
    import_month: str,
    snapshot_id: int,
    expected_digest: str | None = None,
    expected_bytes: int | None = None,
) -> Path:
    candidate = _sales_spool_path(path)
    spool_dir = get_sales_import_spool_dir()
    digest = expected_digest or _artifact_digest_from_path(candidate)
    if not _SALES_ARTIFACT_DIGEST.fullmatch(digest):
        raise ValueError("Invalid sales import artifact digest")
    retained_dir = spool_dir / "retained"
    retained_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    retained_dir.chmod(0o700)
    destination = _sales_spool_path(retained_dir / f"{digest}.source")
    if destination.exists():
        actual_digest, actual_size = _file_digest_and_size(destination)
        if actual_digest != digest or (expected_bytes is not None and actual_size != expected_bytes):
            raise SalesImportArtifactConflictError("Conflicting retained sales artifact")
        destination.chmod(0o600)
        _fsync_file(destination)
        if candidate != destination and candidate.exists():
            candidate.unlink()
            _fsync_directory(candidate.parent)
        _fsync_directory(retained_dir)
        return destination
    if not candidate.exists():
        raise SalesImportArtifactError("Sales source disappeared before retain")
    actual_digest, actual_size = _file_digest_and_size(candidate)
    if actual_digest != digest or (expected_bytes is not None and actual_size != expected_bytes):
        raise SalesImportArtifactError("Sales source integrity check failed before retain")
    candidate.replace(destination)
    destination.chmod(0o600)
    _fsync_file(destination)
    _fsync_directory(retained_dir)
    actual_digest, actual_size = _file_digest_and_size(destination)
    if actual_digest != digest or (expected_bytes is not None and actual_size != expected_bytes):
        raise SalesImportArtifactError("Retained sales artifact readback failed")
    return destination


def cleanup_sales_import_retained_artifacts(keep_paths: set[str]) -> int:
    root = get_sales_import_spool_dir()
    retained_dir = root / "retained"
    if not retained_dir.exists():
        return 0
    keep = {_sales_spool_path(path) for path in keep_paths}
    removed = 0
    for candidate in retained_dir.rglob("*.source"):
        if candidate.resolve() not in keep:
            candidate.unlink(missing_ok=True)
            removed += 1
    if removed:
        _fsync_directory(retained_dir)
    return removed


def read_sales_import_spool_file(path: str, expected_digest: str) -> bytes:
    candidate = _sales_spool_path(path)
    content = candidate.read_bytes()
    if sha256(content).hexdigest() != expected_digest:
        raise ValueError("Sales import spool integrity check failed")
    return content


def cleanup_stale_sales_import_spool_files() -> int:
    spool_dir = get_sales_import_spool_dir()
    if not spool_dir.exists():
        return 0
    max_age = int(
        os.getenv(
            "SALES_IMPORT_SPOOL_MAX_AGE_SECONDS",
            str(DEFAULT_SALES_IMPORT_SPOOL_MAX_AGE_SECONDS),
        )
    )
    if max_age < 3600:
        raise ValueError("SALES_IMPORT_SPOOL_MAX_AGE_SECONDS must be at least one hour")
    cutoff = time.time() - max_age
    removed = 0
    for candidate in spool_dir.glob("*.upload"):
        if candidate.is_file() and candidate.stat().st_mtime < cutoff:
            candidate.unlink(missing_ok=True)
            removed += 1
    for candidate in spool_dir.glob(".*.tmp"):
        if candidate.is_file() and candidate.stat().st_mtime < cutoff:
            candidate.unlink(missing_ok=True)
            removed += 1
    return removed


def get_valkey_settings() -> RedisSettings:
    global _VALKEY_SETTINGS
    if _VALKEY_SETTINGS is None:
        runtime = load_runtime_config()
        if runtime.valkey_url:
            parsed = RedisSettings.from_dsn(runtime.valkey_url)
            _VALKEY_SETTINGS = replace(
                parsed,
                conn_timeout=runtime.valkey_conn_timeout,
                conn_retries=runtime.valkey_conn_retries,
                conn_retry_delay=runtime.valkey_conn_retry_delay,
                max_connections=runtime.valkey_max_connections,
            )
        else:
            _VALKEY_SETTINGS = RedisSettings(
                host=runtime.valkey_host,
                port=runtime.valkey_port,
                database=runtime.valkey_database,
                password=runtime.valkey_password,
                conn_timeout=runtime.valkey_conn_timeout,
                conn_retries=runtime.valkey_conn_retries,
                conn_retry_delay=runtime.valkey_conn_retry_delay,
                max_connections=runtime.valkey_max_connections,
            )
    return _VALKEY_SETTINGS


_arq_pool: Optional[ArqRedis] = None
_arq_pool_attempt: asyncio.Task[ArqRedis | None] | None = None
_arq_last_failure_monotonic = 0.0


async def _create_arq_pool() -> ArqRedis | None:
    global _arq_last_failure_monotonic
    try:
        pool = await create_pool(get_valkey_settings())
    except ConfigError:
        raise
    except ARQ_TRANSPORT_ERRORS as exc:
        _arq_last_failure_monotonic = time.monotonic()
        logger.warning("ARQ queue unavailable; continuing without job backend: %s", exc)
        return None
    if pool is None:
        _arq_last_failure_monotonic = time.monotonic()
        logger.warning("ARQ queue creation returned no pool")
        return None
    return pool


async def _publish_arq_job(
    pool: ArqRedis,
    *args: Any,
    **kwargs: Any,
) -> Job | None:
    """Publish once; transport failure remains explicitly uncertain."""
    try:
        return await pool.enqueue_job(*args, **kwargs)
    except ARQ_TRANSPORT_ERRORS as exc:
        job_id = kwargs.get("_job_id")
        raise JobPublishUncertainError(
            job_id=str(job_id) if job_id is not None else None,
        ) from exc


async def get_arq_pool() -> ArqRedis | None:
    """Best-effort ARQ pool with single-flight creation and cooldown retry."""
    global _arq_pool, _arq_pool_attempt
    if _arq_pool is not None:
        return _arq_pool
    runtime = load_runtime_config()
    if (
        _arq_last_failure_monotonic
        and time.monotonic() - _arq_last_failure_monotonic
        < runtime.arq_failure_cooldown_seconds
    ):
        return None
    attempt = _arq_pool_attempt
    if attempt is None:
        attempt = asyncio.create_task(_create_arq_pool())
        _arq_pool_attempt = attempt
    try:
        result = await asyncio.shield(attempt)
        if result is not None:
            _arq_pool = result
        return result
    finally:
        if attempt.done() and _arq_pool_attempt is attempt:
            _arq_pool_attempt = None


async def _require_arq_pool() -> ArqRedis:
    pool = await get_arq_pool()
    if pool is None:
        raise JobQueueUnavailableError()
    return pool


async def close_arq_pool() -> None:
    global _arq_pool, _arq_pool_attempt
    attempt = _arq_pool_attempt
    _arq_pool_attempt = None
    if attempt is not None and not attempt.done():
        attempt.cancel()
        with suppress(asyncio.CancelledError):
            await attempt
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None


async def enqueue_sales_import(
    file_content: bytes,
    filename: str,
    *,
    cutoff_date: str | None = None,
    requested_by_sub: str = "unknown",
) -> Job:
    pool = await _require_arq_pool()
    digest = sha256(file_content).hexdigest()
    request_digest = sha256(
        f"{digest}:{cutoff_date or 'detected'}".encode("utf-8")
    ).hexdigest()
    job_id = f"sales-import:{request_digest}"
    spool_path = await asyncio.to_thread(
        stage_sales_import_spool_file,
        file_content,
        digest,
    )
    enqueue_args = (
        "import_sales_background",
        str(spool_path),
        digest,
        len(file_content),
        filename,
        get_request_id(),
        cutoff_date,
        requested_by_sub,
    )
    try:
        job = await pool.enqueue_job(
            *enqueue_args,
            _job_id=job_id,
            _queue_name=SALES_IMPORT_QUEUE_NAME,
        )
    except ARQ_TRANSPORT_ERRORS as exc:
        # Publicarea poate fi acceptată de Valkey chiar dacă răspunsul către
        # client se pierde. Nu șterge spoolul până când confirmarea nu este
        # posibilă; un status necunoscut nu declanșează retry orb.
        existing = Job(job_id, pool, _queue_name=SALES_IMPORT_QUEUE_NAME)
        try:
            existing_status = await existing.status()
        except ARQ_TRANSPORT_ERRORS as status_exc:
            raise JobPublishUncertainError(job_id=job_id) from status_exc
        if existing_status in {ArqJobStatus.queued, ArqJobStatus.in_progress}:
            return existing
        await asyncio.to_thread(remove_sales_import_spool_file, spool_path)
        raise exc
    if job is None:
        existing = Job(job_id, pool, _queue_name=SALES_IMPORT_QUEUE_NAME)
        existing_status = await existing.status()
        if existing_status in {ArqJobStatus.queued, ArqJobStatus.in_progress}:
            return existing
        if existing_status == ArqJobStatus.complete:
            info = await existing.result_info()
            if info and info.success:
                # A validated generation is not terminal. Its exact source is
                # retained until promote/rollback confirms a terminal state.
                return existing
            await pool.delete(result_key_prefix + job_id)
            job = await pool.enqueue_job(
                *enqueue_args,
                _job_id=job_id,
                _queue_name=SALES_IMPORT_QUEUE_NAME,
            )
            if job is not None:
                return job
        await asyncio.to_thread(remove_sales_import_spool_file, spool_path)
        raise RuntimeError("Failed to enqueue import job")
    return job


async def enqueue_sales_promotion(
    *,
    snapshot_id: int,
    generation_token: str,
    owner_id: str,
    manifest_sha256: str,
    requested_by_sub: str,
    override_reason: str | None,
) -> Job:
    pool = await _require_arq_pool()
    job_id = f"sales-promote:{snapshot_id}:{manifest_sha256}"
    enqueue_args = (
        "promote_sales_background",
        snapshot_id,
        generation_token,
        owner_id,
        manifest_sha256,
        requested_by_sub,
        override_reason,
        get_request_id(),
    )
    job = await _publish_arq_job(
        pool,
        *enqueue_args,
        _job_id=job_id,
        _queue_name=SALES_IMPORT_QUEUE_NAME,
    )
    if job is not None:
        return job
    existing = Job(job_id, pool, _queue_name=SALES_IMPORT_QUEUE_NAME)
    existing_status = await existing.status()
    if existing_status in {ArqJobStatus.queued, ArqJobStatus.in_progress}:
        return existing
    if existing_status == ArqJobStatus.complete:
        info = await existing.result_info()
        if info and info.success:
            return existing
    await pool.delete(result_key_prefix + job_id)
    replacement = await _publish_arq_job(
        pool,
        *enqueue_args,
        _job_id=job_id,
        _queue_name=SALES_IMPORT_QUEUE_NAME,
    )
    if replacement is None:
        raise RuntimeError("Failed to enqueue sales promotion job")
    return replacement


async def enqueue_grile_check(
    *,
    month: str,
    source: str = "manual",
    source_snapshot_id: int | None = None,
    triggered_by_sub: str | None = None,
    sales_import_authority: bool = False,
) -> GrileEnqueueResult:
    from db.connection import get_pool
    from repositories.grile import GrileRepository

    db_pool = await get_pool()
    repo = GrileRepository(db_pool)
    if sales_import_authority:
        if (
            source != "auto"
            or source_snapshot_id is None
            or triggered_by_sub != "system:sales-import"
        ):
            raise RuntimeError("Invalid sales-import Grile reservation provenance")
        run_id = await repo.reserve_sales_import_run(
            run_month=month,
            source_snapshot_id=source_snapshot_id,
        )
    else:
        run_id = await repo.reserve_run(
            run_month=month,
            source=source,
            source_snapshot_id=source_snapshot_id,
            triggered_by_sub=triggered_by_sub,
        )
    if run_id is None:
        active = await repo.get_running_run(month)
        if active is None:
            raise RuntimeError("Failed to reserve grile check run")
        return GrileEnqueueResult(
            status="already_running",
            run_id=int(active["id"]),
            run=dict(active),
        )

    try:
        pool = await _require_arq_pool()
        job = await _publish_arq_job(
            pool,
            "grile_check_background",
            month,
            source,
            source_snapshot_id,
            triggered_by_sub,
            int(run_id),
            get_request_id(),
        )
        if job is None:
            raise RuntimeError("Failed to enqueue grile check job")
    except JobPublishUncertainError as exc:
        exc.attach_operation_id(int(run_id))
        raise
    except Exception:
        await repo.finalize_run(
            int(run_id),
            status="failed",
            ok_count=0,
            problem_count=0,
            error_count=0,
            duration_ms=0,
            error_message="Jobul nu a putut fi adaugat in coada",
        )
        raise
    return GrileEnqueueResult(
        status="enqueued",
        run_id=int(run_id),
        job=job,
    )


async def enqueue_grile_store_refresh(
    *,
    month: str,
    site_code: str,
    requested_by_sub: str,
) -> GrileStoreRefreshEnqueueResult:
    from db.connection import get_pool
    from repositories.grile import GrileRepository

    db_pool = await get_pool()
    repo = GrileRepository(db_pool)
    if await repo.get_active_sheet(site_code, month) is None:
        raise LookupError("Grila activa nu exista pentru magazin.")
    operation_id = await repo.reserve_store_refresh(
        run_month=month,
        site_code=site_code,
        requested_by_sub=requested_by_sub,
    )
    if operation_id is None:
        active = await repo.get_active_store_refresh(month, site_code)
        if active is None:
            raise RuntimeError("Failed to reserve grile store refresh")
        return GrileStoreRefreshEnqueueResult(
            status="already_running",
            operation_id=int(active["id"]),
            operation=dict(active),
        )
    try:
        pool = await _require_arq_pool()
        job = await _publish_arq_job(
            pool,
            "grile_store_refresh_background",
            int(operation_id),
            get_request_id(),
        )
        if job is None:
            raise RuntimeError("Failed to enqueue grile store refresh job")
    except JobPublishUncertainError as exc:
        exc.attach_operation_id(int(operation_id))
        raise
    except Exception:
        await repo.fail_queued_store_refresh(
            int(operation_id),
            "Jobul refresh nu a putut fi adaugat in coada",
        )
        raise
    return GrileStoreRefreshEnqueueResult(
        status="enqueued",
        operation_id=int(operation_id),
        job=job,
    )


async def enqueue_grile_monthly(
    *,
    op: str,
    month: str,
    only: str | None = None,
    dry_run: bool = True,
    requested_by_sub: str,
    approved_manifest_id: int | None = None,
) -> GrileMonthlyEnqueueResult:
    from db.connection import get_pool
    from services.grile_monthly import (
        attach_monthly_operation_job,
        fail_monthly_operation,
        reserve_monthly_operation,
    )

    db_pool = await get_pool()
    reservation = await reserve_monthly_operation(
        db_pool,
        op=op,
        month=month,
        only=only,
        dry_run=dry_run,
        requested_by_sub=requested_by_sub,
        approved_manifest_id=approved_manifest_id,
    )
    if reservation.status != "enqueued":
        return GrileMonthlyEnqueueResult(
            status=reservation.status,
            operation_id=reservation.operation_id,
            job_id=reservation.job_id,
            operation=reservation.operation,
        )

    # The job identifier is deterministic, so persist it before publishing the
    # job. Otherwise a fast worker can transition queued -> running before the
    # post-enqueue attachment and leave the operation without a recoverable
    # job_id for duplicate API requests and status polling.
    job_id = f"grile-monthly:{reservation.operation_id}"
    attached = await attach_monthly_operation_job(
        db_pool,
        operation_id=reservation.operation_id,
        job_id=job_id,
    )
    if not attached:
        raise RuntimeError(
            "Grile monthly operation is no longer queued before job publication"
        )

    try:
        pool = await _require_arq_pool()
        job = await _publish_arq_job(
            pool,
            "grile_monthly_background",
            reservation.operation_id,
            _job_id=job_id,
        )
        if job is None:
            raise RuntimeError("Failed to enqueue grile monthly job")
    except JobPublishUncertainError as exc:
        exc.attach_operation_id(reservation.operation_id)
        raise
    except Exception:
        # If Valkey accepted the publish but the client lost the response, this
        # compare-and-set moves the row to failed only while it is still queued.
        # A worker that already acquired it remains running and is not clobbered.
        await fail_monthly_operation(
            db_pool,
            reservation.operation_id,
            error_message=MONTHLY_QUEUE_PUBLISH_FAILED,
        )
        raise

    return GrileMonthlyEnqueueResult(
        status="enqueued",
        operation_id=reservation.operation_id,
        job=job,
        job_id=job.job_id,
    )


async def enqueue_grile_target_sync(
    *,
    month: str,
    mode: Literal["dry_run", "sync"],
    requested_by_sub: str,
) -> GrileTargetSyncEnqueueResult:
    from db.connection import get_pool
    from repositories.grile_agent_target_sync import (
        GrileAgentTargetSyncRepository,
    )

    if mode not in {"dry_run", "sync"}:
        raise ValueError("invalid Grile target sync mode")
    db_pool = await get_pool()
    repo = GrileAgentTargetSyncRepository(db_pool)
    reservation_status, operation = await repo.reserve(
        month=month,
        mode=mode,
        requested_by_sub=requested_by_sub,
    )
    operation_id = int(operation["id"])
    if reservation_status != "enqueued":
        return GrileTargetSyncEnqueueResult(
            status=reservation_status,
            operation_id=operation_id,
            operation=operation,
        )

    job_id = f"grile-agent-targets:{operation_id}"
    if not await repo.attach_job(operation_id, job_id):
        raise RuntimeError("Grile target sync operation is no longer queued")
    try:
        pool = await _require_arq_pool()
        job = await _publish_arq_job(
            pool,
            "grile_agent_targets_background",
            operation_id,
            get_request_id(),
            _job_id=job_id,
        )
        if job is None:
            raise RuntimeError("Failed to enqueue Grile target sync job")
    except JobPublishUncertainError as exc:
        exc.attach_operation_id(operation_id)
        raise
    except Exception:
        # A publish can be accepted by Valkey even when the client raises.  If
        # the worker already claimed the operation, leave it running so its
        # transactional finish/fail path remains authoritative.
        await repo.fail_queued(operation_id, "Jobul nu a putut fi adaugat in coada")
        raise
    return GrileTargetSyncEnqueueResult(
        status="enqueued",
        operation_id=operation_id,
        job=job,
    )


async def get_grile_monthly_operation_by_job_id(job_id: str) -> dict | None:
    """Read the durable monthly operation before consulting ephemeral ARQ state."""
    from db.connection import get_pool
    from repositories.grile_monthly_operations import get_by_job_id

    db_pool = await get_pool()
    return await get_by_job_id(db_pool, job_id)


async def get_grile_target_sync_operation(
    operation_id: int,
) -> dict | None:
    from db.connection import get_pool
    from repositories.grile_agent_target_sync import (
        GrileAgentTargetSyncRepository,
    )

    db_pool = await get_pool()
    return await GrileAgentTargetSyncRepository(db_pool).get(operation_id)


async def get_job_status(job_id: str) -> JobResult:
    pool = await get_arq_pool()
    if pool is None:
        return JobResult(
            job_id=job_id,
            status=JobStatus.BACKEND_UNAVAILABLE,
            error="Job backend unavailable",
        )
    try:
        queue_name = (
            SALES_IMPORT_QUEUE_NAME
            if job_id.startswith(("sales-import:", "sales-promote:"))
            else None
        )
        job = Job(job_id, pool, _queue_name=queue_name) if queue_name else Job(job_id, pool)
        arq_status = await job.status()
    except ARQ_TRANSPORT_ERRORS:
        return JobResult(
            job_id=job_id,
            status=JobStatus.UNKNOWN,
            error="Job status could not be determined",
        )

    if arq_status == ArqJobStatus.queued:
        return JobResult(job_id=job_id, status=JobStatus.QUEUED)
    if arq_status == ArqJobStatus.in_progress:
        return JobResult(job_id=job_id, status=JobStatus.IN_PROGRESS)
    if arq_status == ArqJobStatus.complete:
        try:
            result_info = await job.result_info()
        except ARQ_TRANSPORT_ERRORS:
            return JobResult(
                job_id=job_id,
                status=JobStatus.UNKNOWN,
                error="Job result could not be determined",
            )
        if result_info and result_info.success:
            return JobResult(job_id=job_id, status=JobStatus.COMPLETE, result=result_info.result)
        error = str(result_info.result) if result_info else "Unknown error"
        return JobResult(job_id=job_id, status=JobStatus.COMPLETE, error=error)
    if arq_status == ArqJobStatus.not_found:
        return JobResult(job_id=job_id, status=JobStatus.NOT_FOUND)

    return JobResult(
        job_id=job_id,
        status=JobStatus.UNKNOWN,
        error="Unknown job status",
    )
