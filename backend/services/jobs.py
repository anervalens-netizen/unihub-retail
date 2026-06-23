from __future__ import annotations

import os
from hashlib import sha256
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.constants import result_key_prefix
from arq.jobs import Job, JobStatus as ArqJobStatus


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


_VALKEY_SETTINGS: Optional[RedisSettings] = None


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


async def enqueue_sales_import(file_content: bytes, filename: str) -> Job:
    pool = await get_arq_pool()
    job_id = f"sales-import:{sha256(file_content).hexdigest()}"
    enqueue_args = (
        "import_sales_background",
        file_content,
        filename,
    )
    job = await pool.enqueue_job(*enqueue_args, _job_id=job_id)
    if job is None:
        existing = Job(job_id, pool)
        existing_status = await existing.status()
        if existing_status in {ArqJobStatus.queued, ArqJobStatus.in_progress}:
            return existing
        if existing_status == ArqJobStatus.complete:
            info = await existing.result_info()
            if info and info.success:
                return existing
            await pool.delete(result_key_prefix + job_id)
            job = await pool.enqueue_job(*enqueue_args, _job_id=job_id)
            if job is not None:
                return job
        raise RuntimeError("Failed to enqueue import job")
    return job


async def enqueue_grile_check(
    *,
    month: str,
    source: str = "manual",
    source_snapshot_id: int | None = None,
    triggered_by_email: str | None = None,
) -> GrileEnqueueResult:
    from db.connection import get_pool
    from repositories.grile import GrileRepository

    db_pool = await get_pool()
    repo = GrileRepository(db_pool)
    run_id = await repo.reserve_run(
        run_month=month,
        source=source,
        source_snapshot_id=source_snapshot_id,
        triggered_by_email=triggered_by_email,
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
            triggered_by_email,
            int(run_id),
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
    triggered_by_email: str | None = None,
) -> GrileMonthlyEnqueueResult:
    from db.connection import get_pool
    from services.grile_monthly import (
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
        triggered_by_email=triggered_by_email,
    )
    if reservation.status != "enqueued":
        return GrileMonthlyEnqueueResult(
            status=reservation.status,
            operation_id=reservation.operation_id,
            job_id=reservation.job_id,
            operation=reservation.operation,
        )

    pool = await get_arq_pool()
    job_id = f"grile-monthly:{reservation.operation_id}"
    job = await pool.enqueue_job(
        "grile_monthly_background",
        op,
        month,
        only,
        dry_run,
        triggered_by_email,
        reservation.operation_id,
        _job_id=job_id,
    )
    if job is None:
        await fail_monthly_operation(
            db_pool,
            reservation.operation_id,
            error_message="Jobul lunar Grile nu a putut fi adaugat in coada",
        )
        raise RuntimeError("Failed to enqueue grile monthly job")

    from services.grile_monthly import attach_monthly_operation_job

    await attach_monthly_operation_job(
        db_pool,
        operation_id=reservation.operation_id,
        job_id=job.job_id,
    )
    return GrileMonthlyEnqueueResult(
        status="enqueued",
        operation_id=reservation.operation_id,
        job=job,
        job_id=job.job_id,
    )


async def get_job_status(job_id: str) -> JobResult:
    pool = await get_arq_pool()
    try:
        job = Job(job_id, pool)
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
