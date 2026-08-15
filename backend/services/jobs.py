from __future__ import annotations
import asyncio
import logging
import time
from hashlib import sha256
from contextlib import suppress
from dataclasses import replace
from typing import Any, Optional
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.constants import result_key_prefix
from arq.jobs import DeserializationError, Job, JobStatus as ArqJobStatus
from config import ConfigError, load_runtime_config
from request_context import get_request_id
from services.job_contracts import (
    ARQ_TRANSPORT_ERRORS,
    EXPORT_QUEUE_NAME,
    GRILE_QUEUE_NAME,
    MONTHLY_QUEUE_PUBLISH_FAILED,
    OPERATIONS_QUEUE_NAME,
    SALES_IMPORT_QUEUE_NAME,
    SALARY_EXPORT_QUEUE_NAME,
    GrileEnqueueResult,
    GrileMonthlyEnqueueResult,
    GrileStoreRefreshEnqueueResult,
    GrileTargetSyncEnqueueResult,
    JobPublishUncertainError,
    JobQueueUnavailableError,
    JobResult,
    JobStatus,
)
from services.job_queue_routing import resolve_status_job
from services.sales_artifacts import (
    SalesImportArtifactConflictError,
    SalesImportArtifactError,
    cleanup_sales_import_retained_artifacts,
    cleanup_stale_sales_import_spool_files,
    get_sales_import_spool_dir,
    read_sales_import_spool_file,
    remove_sales_import_spool_file,
    resolve_sales_import_artifact,
    retain_sales_import_spool_file,
    stage_sales_import_spool_file,
    verify_sales_import_artifact,
)
logger = logging.getLogger(__name__)

_VALKEY_SETTINGS: Optional[RedisSettings] = None
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
async def enqueue_promo_actuals_import(
    content: bytes,
    *,
    filename: str,
    import_month: str,
    cutoff_date: str,
) -> Job:
    """Stage a content-addressed promo report and publish one deterministic import job.
    Statusul și rezultatul rămân recuperabile din ARQ minimum 3600s implicit,
    peste fereastra de polling UI de 1800s; nu este necesară o tabelă DB.
    """
    digest = sha256(content).hexdigest()
    job_id = f"promo-actuals:{digest}:{import_month}:{cutoff_date}"
    return await _enqueue_spooled_import_job(
        content=content,
        digest=digest,
        job_id=job_id,
        function_name="import_promo_actuals_background",
        function_args=(filename, import_month, cutoff_date),
    )
async def enqueue_erp_reconciliation(
    content: bytes,
    *,
    filename: str,
    import_month: str,
) -> Job:
    digest = sha256(content).hexdigest()
    job_id = f"erp-reconciliation:{digest}:{import_month}"
    return await _enqueue_spooled_import_job(
        content=content,
        digest=digest,
        job_id=job_id,
        function_name="reconcile_erp_background",
        function_args=(filename, import_month),
    )
async def _enqueue_spooled_import_job(
    *,
    content: bytes,
    digest: str,
    job_id: str,
    function_name: str,
    function_args: tuple[Any, ...],
) -> Job:
    """Publish a verified spool reference and replace only a failed terminal job."""
    pool = await _require_arq_pool()
    # The same bytes may legitimately be reconciled for different months or
    # promo cutoffs.  Namespace the artifact by deterministic job identity so
    # one successful job cannot delete another queued job's source.  A retry
    # of the same job still reuses the exact same content-addressed path.
    spool_namespace = sha256(job_id.encode("utf-8")).hexdigest()
    spool_path = await asyncio.to_thread(
        stage_sales_import_spool_file,
        content,
        digest,
        namespace=spool_namespace,
    )
    enqueue_args = (
        function_name,
        str(spool_path),
        digest,
        len(content),
        *function_args,
    )
    try:
        job = await _publish_arq_job(
            pool,
            *enqueue_args,
            _job_id=job_id,
            _queue_name=SALES_IMPORT_QUEUE_NAME,
        )
    except JobPublishUncertainError:
        # Valkey may have accepted the job; its worker still needs the spool.
        raise
    except Exception:
        await asyncio.to_thread(remove_sales_import_spool_file, spool_path)
        raise
    if job is not None:
        return job
    existing = Job(job_id, pool, _queue_name=SALES_IMPORT_QUEUE_NAME)
    try:
        existing_status = await existing.status()
    except ARQ_TRANSPORT_ERRORS as exc:
        # enqueue_job(None) means the deterministic id already exists. If its
        # status cannot be read, preserve the artifact for a possibly queued job.
        raise JobPublishUncertainError(job_id=job_id) from exc
    if existing_status in {ArqJobStatus.queued, ArqJobStatus.in_progress}:
        return existing
    if existing_status == ArqJobStatus.complete:
        try:
            info = await existing.result_info()
        except ARQ_TRANSPORT_ERRORS as exc:
            raise JobPublishUncertainError(job_id=job_id) from exc
        except DeserializationError:
            info = None
        if info and info.success:
            await asyncio.to_thread(remove_sales_import_spool_file, spool_path)
            return existing
        try:
            await pool.delete(result_key_prefix + job_id)
        except Exception:
            await asyncio.to_thread(remove_sales_import_spool_file, spool_path)
            raise
        try:
            replacement = await _publish_arq_job(
                pool,
                *enqueue_args,
                _job_id=job_id,
                _queue_name=SALES_IMPORT_QUEUE_NAME,
            )
        except JobPublishUncertainError:
            raise
        except Exception:
            await asyncio.to_thread(remove_sales_import_spool_file, spool_path)
            raise
        if replacement is not None:
            return replacement
    await asyncio.to_thread(remove_sales_import_spool_file, spool_path)
    raise RuntimeError(f"Failed to enqueue import job {job_id}")
async def enqueue_campaign_reporting_publication(
    *,
    month: str,
    requested_by_sub: str,
    reason: str,
    generation_hash: str,
    sales_revision: int,
) -> Job:
    from services.job_publication import (
        enqueue_campaign_reporting_publication as enqueue,
    )
    return await enqueue(
        month=month,
        requested_by_sub=requested_by_sub,
        reason=reason,
        generation_hash=generation_hash,
        sales_revision=sales_revision,
        require_pool=_require_arq_pool,
        publish=_publish_arq_job,
    )


async def enqueue_complex_export(operation_id: int) -> Job:
    from services.job_publication import enqueue_complex_export as enqueue
    return await enqueue(
        operation_id,
        require_pool=_require_arq_pool,
        publish=_publish_arq_job,
    )


async def enqueue_salary_export(operation_id: int) -> Job:
    from services.job_publication import enqueue_salary_export as enqueue
    return await enqueue(
        operation_id,
        require_pool=_require_arq_pool,
        publish=_publish_arq_job,
    )

async def enqueue_grile_check(**kwargs: Any) -> GrileEnqueueResult:
    from services.grile_jobs import enqueue_grile_check as enqueue
    return await enqueue(
        **kwargs,
        require_pool=_require_arq_pool,
        publish=_publish_arq_job,
    )


async def enqueue_grile_store_refresh(
    **kwargs: Any,
) -> GrileStoreRefreshEnqueueResult:
    from services.grile_jobs import enqueue_grile_store_refresh as enqueue
    return await enqueue(
        **kwargs,
        require_pool=_require_arq_pool,
        publish=_publish_arq_job,
    )


async def enqueue_grile_monthly(
    **kwargs: Any,
) -> GrileMonthlyEnqueueResult:
    from services.grile_jobs import enqueue_grile_monthly as enqueue
    return await enqueue(
        **kwargs,
        require_pool=_require_arq_pool,
        publish=_publish_arq_job,
    )


async def enqueue_grile_target_sync(
    **kwargs: Any,
) -> GrileTargetSyncEnqueueResult:
    from services.grile_jobs import enqueue_grile_target_sync as enqueue
    return await enqueue(
        **kwargs,
        require_pool=_require_arq_pool,
        publish=_publish_arq_job,
    )


async def get_grile_monthly_operation_by_job_id(
    job_id: str,
) -> dict | None:
    from services.grile_jobs import get_grile_monthly_operation_by_job_id
    return await get_grile_monthly_operation_by_job_id(job_id)


async def get_grile_target_sync_operation(
    operation_id: int,
) -> dict | None:
    from services.grile_jobs import get_grile_target_sync_operation
    return await get_grile_target_sync_operation(operation_id)


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
            if job_id.startswith(("sales-import:", "sales-promote:", "promo-actuals:", "erp-reconciliation:"))
            else EXPORT_QUEUE_NAME
            if job_id.startswith("export-complex:")
            else SALARY_EXPORT_QUEUE_NAME
            if job_id.startswith("salary-export:")
            else GRILE_QUEUE_NAME
            if job_id.startswith(("grile-check:", "grile-store-refresh:", "grile-monthly:", "grile-agent-targets:", "grile-pilot-v2:"))
            else None
        )
        job, arq_status = await resolve_status_job(job_id, pool, queue_name)
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
        except DeserializationError:
            return JobResult(job_id=job_id, status=JobStatus.COMPLETE,
                             error="Job failed; result could not be decoded")
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
