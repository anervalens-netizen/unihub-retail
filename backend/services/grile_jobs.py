from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from arq.connections import ArqRedis
from arq.jobs import Job

from request_context import get_request_id
from services.job_contracts import (
    GRILE_QUEUE_NAME,
    MONTHLY_QUEUE_PUBLISH_FAILED,
    GrileEnqueueResult,
    GrileMonthlyEnqueueResult,
    GrileStoreRefreshEnqueueResult,
    GrileTargetSyncEnqueueResult,
    JobPublishUncertainError,
)

RequirePool = Callable[[], Awaitable[ArqRedis]]
PublishJob = Callable[..., Awaitable[Job | None]]

async def enqueue_grile_check(
    *,
    month: str,
    source: str = "manual",
    source_snapshot_id: int | None = None,
    triggered_by_sub: str | None = None,
    sales_import_authority: bool = False,
    require_pool: RequirePool,
    publish: PublishJob,
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
        pool = await require_pool()
        job = await publish(
            pool,
            "grile_check_background",
            month,
            source,
            source_snapshot_id,
            triggered_by_sub,
            int(run_id),
            get_request_id(),
            _job_id=f"grile-check:{run_id}",
            _queue_name=GRILE_QUEUE_NAME,
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
    require_pool: RequirePool,
    publish: PublishJob,
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
        pool = await require_pool()
        job = await publish(
            pool,
            "grile_store_refresh_background",
            int(operation_id),
            get_request_id(),
            _job_id=f"grile-store-refresh:{operation_id}",
            _queue_name=GRILE_QUEUE_NAME,
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
    require_pool: RequirePool,
    publish: PublishJob,
) -> GrileMonthlyEnqueueResult:
    from db.connection import get_pool
    from services.grile_monthly import (
        attach_monthly_operation_job,
        fail_queued_monthly_operation,
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
        pool = await require_pool()
        job = await publish(
            pool,
            "grile_monthly_background",
            reservation.operation_id,
            _job_id=job_id,
            _queue_name=GRILE_QUEUE_NAME,
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
        await fail_queued_monthly_operation(
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
    require_pool: RequirePool,
    publish: PublishJob,
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
        pool = await require_pool()
        job = await publish(
            pool,
            "grile_agent_targets_background",
            operation_id,
            get_request_id(),
            _job_id=job_id,
            _queue_name=GRILE_QUEUE_NAME,
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
