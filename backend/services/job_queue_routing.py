"""Queue-aware ARQ job lookup, including the bounded 9.5 cutover window."""
from __future__ import annotations

from typing import Any

from arq.jobs import Job, JobStatus as ArqJobStatus


LEGACY_QUEUE_STATUS_PREFIXES = (
    "export-complex:",
    "grile-check:",
    "grile-store-refresh:",
    "grile-monthly:",
    "grile-agent-targets:",
)


async def resolve_status_job(
    job_id: str,
    pool: Any,
    queue_name: str | None,
) -> tuple[Job, ArqJobStatus]:
    job = Job(job_id, pool, _queue_name=queue_name) if queue_name else Job(job_id, pool)
    arq_status = await job.status()
    if arq_status == ArqJobStatus.not_found and job_id.startswith(
        LEGACY_QUEUE_STATUS_PREFIXES
    ):
        legacy_job = Job(job_id, pool)
        legacy_status = await legacy_job.status()
        if legacy_status != ArqJobStatus.not_found:
            return legacy_job, legacy_status
    return job, arq_status
