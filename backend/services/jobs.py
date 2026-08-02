from __future__ import annotations

import asyncio
import os
import time
from hashlib import sha256
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.constants import result_key_prefix
from arq.jobs import Job, JobStatus as ArqJobStatus
from request_context import get_request_id


class JobStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    NOT_FOUND = "not_found"


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


def get_sales_import_spool_dir() -> Path:
    configured = os.getenv("SALES_IMPORT_SPOOL_DIR")
    path = (
        Path(configured).expanduser()
        if configured
        else Path(__file__).resolve().parents[2] / "data" / "import_spool"
    )
    return path.resolve()


def _stage_sales_import(content: bytes, digest: str) -> Path:
    spool_dir = get_sales_import_spool_dir()
    spool_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = spool_dir / f"{digest}.upload"
    temporary = spool_dir / f".{digest}.{uuid4().hex}.tmp"
    try:
        temporary.write_bytes(content)
        temporary.chmod(0o600)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def remove_sales_import_spool_file(path: str | Path) -> None:
    candidate = Path(path).resolve()
    spool_dir = get_sales_import_spool_dir()
    if not candidate.is_relative_to(spool_dir):
        raise ValueError("Sales import spool path escapes the configured directory")
    candidate.unlink(missing_ok=True)


def retain_sales_import_spool_file(
    path: str | Path,
    *,
    import_month: str,
    snapshot_id: int,
) -> Path:
    candidate = Path(path).resolve()
    spool_dir = get_sales_import_spool_dir()
    if not candidate.is_relative_to(spool_dir):
        raise ValueError("Sales import spool path escapes the configured directory")
    retained_dir = spool_dir / "retained" / import_month
    retained_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = retained_dir / f"{snapshot_id}-{candidate.stem}.source"
    candidate.replace(destination)
    destination.chmod(0o600)
    retained = sorted(
        (item for item in retained_dir.glob("*.source") if item.is_file()),
        key=lambda item: item.stat().st_mtime_ns,
        reverse=True,
    )
    for expired in retained[2:]:
        expired.unlink(missing_ok=True)
    return destination


def read_sales_import_spool_file(path: str, expected_digest: str) -> bytes:
    candidate = Path(path).resolve()
    spool_dir = get_sales_import_spool_dir()
    if not candidate.is_relative_to(spool_dir):
        raise ValueError("Sales import spool path escapes the configured directory")
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
        host = os.getenv("VALKEY_HOST", "127.0.0.1")
        port = int(os.getenv("VALKEY_PORT", "6379"))
        password = os.getenv("VALKEY_PASSWORD", "")
        valkey_url = os.getenv("VALKEY_URL", "")
        if valkey_url:
            _VALKEY_SETTINGS = RedisSettings.from_dsn(valkey_url)
        elif password:
            _VALKEY_SETTINGS = RedisSettings(host=host, port=port, password=password)
        else:
            _VALKEY_SETTINGS = RedisSettings(host=host, port=port)
    return _VALKEY_SETTINGS


_arq_pool: Optional[ArqRedis] = None


async def get_arq_pool() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(get_valkey_settings())
    return _arq_pool


async def close_arq_pool() -> None:
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None


async def enqueue_sales_import(
    file_content: bytes,
    filename: str,
    *,
    cutoff_date: str | None = None,
    requested_by_sub: str = "legacy-direct",
) -> Job:
    pool = await get_arq_pool()
    digest = sha256(file_content).hexdigest()
    request_digest = sha256(
        f"{digest}:{cutoff_date or 'detected'}".encode("utf-8")
    ).hexdigest()
    job_id = f"sales-import:{request_digest}"
    spool_path = await asyncio.to_thread(_stage_sales_import, file_content, digest)
    enqueue_args = (
        "import_sales_background",
        str(spool_path),
        digest,
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
    except Exception:
        # Publicarea poate fi acceptată de Valkey chiar dacă răspunsul către
        # client se pierde. Nu șterge spoolul unui job deja vizibil în coadă.
        existing = Job(job_id, pool, _queue_name=SALES_IMPORT_QUEUE_NAME)
        try:
            existing_status = await existing.status()
        except Exception:
            existing_status = ArqJobStatus.not_found
        if existing_status in {ArqJobStatus.queued, ArqJobStatus.in_progress}:
            return existing
        await asyncio.to_thread(remove_sales_import_spool_file, spool_path)
        raise
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
    pool = await get_arq_pool()
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
    job = await pool.enqueue_job(
        *enqueue_args,
        _job_id=job_id,
        _queue_name=SALES_IMPORT_QUEUE_NAME,
    )
    if job is not None:
        return job
    existing = Job(job_id, pool, _queue_name=SALES_IMPORT_QUEUE_NAME)
    existing_status = await existing.status()
    if existing_status in {
        ArqJobStatus.queued,
        ArqJobStatus.in_progress,
        ArqJobStatus.complete,
    }:
        return existing
    await pool.delete(result_key_prefix + job_id)
    replacement = await pool.enqueue_job(
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
) -> GrileEnqueueResult:
    from db.connection import get_pool
    from repositories.grile import GrileRepository

    db_pool = await get_pool()
    repo = GrileRepository(db_pool)
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
        pool = await get_arq_pool()
        job = await pool.enqueue_job(
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
        pool = await get_arq_pool()
        job = await pool.enqueue_job(
            "grile_monthly_background",
            reservation.operation_id,
            request_id=get_request_id(),
            _job_id=job_id,
        )
        if job is None:
            raise RuntimeError("Failed to enqueue grile monthly job")
    except Exception:
        # If Valkey accepted the publish but the client lost the response, this
        # compare-and-set moves the row to failed only while it is still queued.
        # A worker that already acquired it remains running and is not clobbered.
        await fail_monthly_operation(
            db_pool,
            reservation.operation_id,
            error_message="Jobul lunar Grile nu a putut fi adaugat in coada",
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
        pool = await get_arq_pool()
        job = await pool.enqueue_job(
            "grile_agent_targets_background",
            operation_id,
            get_request_id(),
            _job_id=job_id,
        )
        if job is None:
            raise RuntimeError("Failed to enqueue Grile target sync job")
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
    try:
        queue_name = SALES_IMPORT_QUEUE_NAME if job_id.startswith("sales-import:") else None
        job = Job(job_id, pool, _queue_name=queue_name) if queue_name else Job(job_id, pool)
        status = await job.status()
    except Exception:
        return JobResult(job_id=job_id, status=JobStatus.NOT_FOUND)

    if status == ArqJobStatus.queued:
        return JobResult(job_id=job_id, status=JobStatus.QUEUED)
    if status == ArqJobStatus.in_progress:
        return JobResult(job_id=job_id, status=JobStatus.IN_PROGRESS)
    if status == ArqJobStatus.complete:
        result_info = await job.result_info()
        if result_info and result_info.success:
            return JobResult(job_id=job_id, status=JobStatus.COMPLETE, result=result_info.result)
        error = str(result_info.result) if result_info else "Unknown error"
        return JobResult(job_id=job_id, status=JobStatus.COMPLETE, error=error)
    if status == ArqJobStatus.not_found:
        return JobResult(job_id=job_id, status=JobStatus.NOT_FOUND)

    return JobResult(job_id=job_id, status=JobStatus.QUEUED)
