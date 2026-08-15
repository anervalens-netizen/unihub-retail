from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from arq.connections import ArqRedis
from arq.constants import result_key_prefix
from arq.jobs import Job, JobStatus as ArqJobStatus

from request_context import get_request_id
from services.job_contracts import (
    ARQ_TRANSPORT_ERRORS,
    EXPORT_QUEUE_NAME,
    SALES_IMPORT_QUEUE_NAME,
    SALARY_EXPORT_QUEUE_NAME,
    JobPublishUncertainError,
)

RequirePool = Callable[[], Awaitable[ArqRedis]]
PublishJob = Callable[..., Awaitable[Job | None]]
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


async def enqueue_campaign_reporting_publication(
    *,
    month: str,
    requested_by_sub: str,
    reason: str,
    generation_hash: str,
    sales_revision: int,
    require_pool: RequirePool,
    publish: PublishJob,
) -> Job:
    """Queue one idempotent Campaigns publication per sales generation."""
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise ValueError("Campaign reporting month is invalid")
    if not _SHA256_RE.fullmatch(generation_hash):
        raise ValueError("Campaign reporting generation hash is invalid")
    if (
        isinstance(sales_revision, bool)
        or not isinstance(sales_revision, int)
        or sales_revision < 1
    ):
        raise ValueError("Campaign reporting sales revision is invalid")
    pool = await require_pool()
    job_id = (
        f"campaign-reporting:{month}:{generation_hash}:{sales_revision}"
    )
    enqueue_args = (
        "publish_campaign_reporting_background",
        month,
        requested_by_sub,
        reason,
        generation_hash,
        sales_revision,
        get_request_id(),
    )
    job = await publish(
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
        await pool.delete(result_key_prefix + job_id)
        replacement = await publish(
            pool,
            *enqueue_args,
            _job_id=job_id,
            _queue_name=SALES_IMPORT_QUEUE_NAME,
        )
        if replacement is not None:
            return replacement
    raise RuntimeError("Failed to enqueue campaign reporting publication")


async def _enqueue_durable_export(
    operation_id: int,
    *,
    job_prefix: str,
    function_name: str,
    queue_name: str,
    require_pool: RequirePool,
    publish: PublishJob,
) -> Job:
    if isinstance(operation_id, bool) or not isinstance(operation_id, int) or operation_id <= 0:
        raise ValueError("Invalid export operation id")
    pool = await require_pool()
    job_id = f"{job_prefix}:{operation_id}"
    job = await publish(
        pool,
        function_name,
        operation_id,
        _job_id=job_id,
        _queue_name=queue_name,
    )
    if job is not None:
        return job
    existing = Job(job_id, pool, _queue_name=queue_name)
    try:
        existing_status = await existing.status()
    except ARQ_TRANSPORT_ERRORS as exc:
        raise JobPublishUncertainError(job_id=job_id, operation_id=operation_id) from exc
    if existing_status in {
        ArqJobStatus.queued,
        ArqJobStatus.in_progress,
        ArqJobStatus.complete,
    }:
        return existing
    raise RuntimeError("Failed to enqueue complex export operation")


async def enqueue_complex_export(
    operation_id: int,
    *,
    require_pool: RequirePool,
    publish: PublishJob,
) -> Job:
    """Publish one non-salary export to its isolated worker."""
    return await _enqueue_durable_export(
        operation_id,
        job_prefix="export-complex",
        function_name="build_complex_export_background",
        queue_name=EXPORT_QUEUE_NAME,
        require_pool=require_pool,
        publish=publish,
    )


async def enqueue_salary_export(
    operation_id: int,
    *,
    require_pool: RequirePool,
    publish: PublishJob,
) -> Job:
    """Publish one salary export only to the salary-authority worker."""
    return await _enqueue_durable_export(
        operation_id,
        job_prefix="salary-export",
        function_name="build_salary_export_background",
        queue_name=SALARY_EXPORT_QUEUE_NAME,
        require_pool=require_pool,
        publish=publish,
    )
