from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
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
    return await pool.enqueue_job("import_sales_background", file_content, filename)


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
