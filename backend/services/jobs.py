from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobResult:
    job_id: str
    status: JobStatus
    result: Optional[dict] = None
    error: Optional[str] = None


def get_valkey_settings() -> RedisSettings:
    valkey_url = os.getenv("VALKEY_URL", "redis://localhost:6379")
    return RedisSettings.from_dsn(valkey_url)


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


async def enqueue_sales_import(file_content: bytes, filename: str) -> str:
    pool = await get_arq_pool()
    job = await pool.enqueue_job("import_sales_background", file_content, filename)
    return job.job_id


async def get_job_status(job_id: str) -> JobResult:
    pool = await get_arq_pool()
    job_info = await pool.get_job_result(job_id)
    if job_info is None:
        return JobResult(job_id=job_id, status=JobStatus.QUEUED)
    if job_info.success:
        return JobResult(job_id=job_id, status=JobStatus.COMPLETED, result=job_info.result)
    return JobResult(job_id=job_id, status=JobStatus.FAILED, error=str(job_info.result))
