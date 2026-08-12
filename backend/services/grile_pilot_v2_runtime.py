"""Queue and worker lifecycle for the isolated Grile V2 projection."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from arq.constants import result_key_prefix
from arq.jobs import Job, JobStatus as ArqJobStatus

from request_context import bind_request_id, get_request_id, reset_request_id
import services.jobs as jobs_service
from services.grile_pilot_v2_registry import PILOT_V2_MONTH


logger = logging.getLogger(__name__)
async def enqueue_grile_pilot_v2_sync(*, month: str, trigger: str) -> Job:
    """Queue one idempotent sync for the isolated Grile V2 pilot."""
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise ValueError("Grile V2 month is invalid")
    normalized_trigger = trigger.strip()[:128]
    if not normalized_trigger:
        raise ValueError("Grile V2 trigger is required")
    pool = await jobs_service._require_arq_pool()
    job_id = f"grile-pilot-v2:{month}"
    enqueue_args = (
        "grile_pilot_v2_sync_background",
        month,
        normalized_trigger,
        get_request_id(),
    )
    job = await jobs_service._publish_arq_job(
        pool,
        *enqueue_args,
        _job_id=job_id,
        _queue_name=jobs_service.GRILE_QUEUE_NAME,
    )
    if job is not None:
        return job
    existing = Job(job_id, pool, _queue_name=jobs_service.GRILE_QUEUE_NAME)
    existing_status = await existing.status()
    if existing_status in {ArqJobStatus.queued, ArqJobStatus.in_progress}:
        return existing
    if existing_status == ArqJobStatus.complete:
        await pool.delete(result_key_prefix + job_id)
        replacement = await jobs_service._publish_arq_job(
            pool,
            *enqueue_args,
            _job_id=job_id,
            _queue_name=jobs_service.GRILE_QUEUE_NAME,
        )
        if replacement is not None:
            return replacement
    raise RuntimeError("Failed to enqueue Grile V2 sync")


async def trigger_grile_pilot_v2_sync(import_month: str, *, trigger: str) -> None:
    """Best-effort hook; source promotion stays valid and hourly self-heal retries."""
    if import_month != PILOT_V2_MONTH:
        return
    try:
        job = await enqueue_grile_pilot_v2_sync(month=import_month, trigger=trigger)
        logger.info("Grile V2 sync queued month=%s job=%s", import_month, job.job_id)
    except Exception:  # noqa: BLE001 -- projection retries through worker self-heal
        logger.exception("enqueue Grile V2 sync esuat pentru %s", import_month)


async def sync_grile_pilot_v2_once(ctx: dict, *, trigger: str) -> dict[str, Any]:
    from services.grile_pilot_v2_sync import sync_pilot_v2_sheets

    logger.info("Starting Grile V2 sync trigger=%s", trigger)
    lock = ctx.setdefault("grile_pilot_v2_sync_lock", asyncio.Lock())
    async with lock:
        return await sync_pilot_v2_sheets(
            ctx["db_pool"],
            ctx["grile_monthly_google"],
        )


async def run_grile_pilot_v2_sync_loop(ctx: dict) -> None:
    stop = ctx["grile_pilot_v2_sync_stop"]
    try:
        try:
            await sync_grile_pilot_v2_once(ctx, trigger="startup-recovery")
        except Exception:
            logger.exception("Startup Grile V2 recovery failed; last good snapshot retained")
        await stop.wait()
    except asyncio.CancelledError:
        return


def start_grile_pilot_v2_sync(ctx: dict) -> None:
    ctx["grile_pilot_v2_sync_stop"] = asyncio.Event()
    ctx["grile_pilot_v2_sync_task"] = asyncio.create_task(
        run_grile_pilot_v2_sync_loop(ctx),
        name="grile-pilot-v2-sync",
    )


async def stop_grile_pilot_v2_sync(ctx: dict) -> None:
    task = ctx.get("grile_pilot_v2_sync_task")
    stop = ctx.get("grile_pilot_v2_sync_stop")
    if stop is not None:
        stop.set()
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def grile_pilot_v2_sync_background(
    ctx: dict,
    month: str,
    trigger: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    if month != PILOT_V2_MONTH:
        raise ValueError("Grile V2 sync is limited to the August 2026 pilot")
    token = bind_request_id(request_id) if request_id else None
    try:
        return await sync_grile_pilot_v2_once(ctx, trigger=trigger)
    finally:
        if token is not None:
            reset_request_id(token)
