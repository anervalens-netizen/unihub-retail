"""Queue boundary for export artifact removal by the owning worker."""

from __future__ import annotations

from hashlib import sha256
import re

from arq.jobs import Job, JobStatus as ArqJobStatus

from services import jobs


EXPORT_ARTIFACT_KEY = re.compile(r"^(?:salary/)?[0-9a-f]{32}\.xlsx$")


async def enqueue_export_artifact_cleanup(key: str) -> Job:
    if not isinstance(key, str) or not EXPORT_ARTIFACT_KEY.fullmatch(key):
        raise ValueError("Invalid export artifact identity")
    queue_name = (
        jobs.SALARY_EXPORT_QUEUE_NAME
        if key.startswith("salary/")
        else jobs.EXPORT_QUEUE_NAME
    )
    pool = await jobs._require_arq_pool()
    job_id = f"export-artifact-cleanup:{sha256(key.encode('utf-8')).hexdigest()}"
    job = await jobs._publish_arq_job(
        pool,
        "remove_export_artifact_background",
        key,
        _job_id=job_id,
        _queue_name=queue_name,
    )
    if job is not None:
        return job
    existing = Job(job_id, pool, _queue_name=queue_name)
    try:
        existing_status = await existing.status()
    except jobs.ARQ_TRANSPORT_ERRORS as exc:
        raise jobs.JobPublishUncertainError(job_id=job_id) from exc
    if existing_status in {
        ArqJobStatus.queued,
        ArqJobStatus.in_progress,
        ArqJobStatus.complete,
    }:
        return existing
    raise RuntimeError("Failed to enqueue export artifact cleanup")
