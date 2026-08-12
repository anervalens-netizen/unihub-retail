from __future__ import annotations
import asyncio
from datetime import date
import json
import logging
import os
from typing import Any, Awaitable, TypeVar
from uuid import uuid4
from arq.worker import create_worker, func
from fastapi import HTTPException
from config import load_runtime_config
from logging_config import setup_logging
from request_context import bind_request_id, reset_request_id
import services.grile_reconciliation_supervisor as grile_supervisor
import services.grile_pilot_v2_runtime as grile_pilot_v2_runtime
from services.grile_pilot_v2_runtime import grile_pilot_v2_sync_background
from services.export_worker import export_heartbeat_loop as _export_heartbeat_loop, remove_export_artifact_background
from services.jobs import (
    EXPORT_QUEUE_NAME,
    GRILE_QUEUE_NAME,
    OPERATIONS_QUEUE_NAME,
    SALES_IMPORT_QUEUE_NAME,
    SALARY_EXPORT_QUEUE_NAME,
    cleanup_stale_sales_import_spool_files,
    get_valkey_settings,
    read_sales_import_spool_file,
    remove_sales_import_spool_file,
    resolve_sales_import_artifact,
    retain_sales_import_spool_file,
    verify_sales_import_artifact,
)
setup_logging()
logger = logging.getLogger(__name__)
VISITS_SNAPSHOT_REFRESH_SECONDS = 15 * 60
EXPORT_CLEANUP_SECONDS = 5 * 60
QUEUE_METRICS_SECONDS = 15
_ResultT = TypeVar("_ResultT")
async def _await_pickle_safe(awaitable: Awaitable[_ResultT]) -> _ResultT:
    try:
        return await awaitable
    except HTTPException as exc:
        raise RuntimeError(str(exc.detail)) from exc
async def _refresh_visits_snapshot_once(pool: Any) -> int:
    from services.visits_sync import sync_visits_snapshot
    async with pool.acquire() as conn:
        async with conn.transaction():
            claimed = await conn.fetchval(
                "SELECT pg_try_advisory_xact_lock(hashtextextended($1, 0))",
                "unihub:visits-snapshot-refresh",
            )
            if not claimed:
                return 0
            refreshed = await sync_visits_snapshot(conn)
    logger.info("Refreshed %d visits snapshot rows", refreshed)
    return refreshed
async def refresh_visits_snapshot_background(ctx: dict) -> dict[str, int]:
    """Explicit operations-queue entrypoint; periodic refresh uses the same fence."""
    return {"rows": await _refresh_visits_snapshot_once(ctx["db_pool"])}
async def _visits_snapshot_refresh_loop(ctx: dict) -> None:
    stop = ctx["visits_snapshot_refresh_stop"]
    pool = ctx["db_pool"]
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=VISITS_SNAPSHOT_REFRESH_SECONDS,
                )
            except TimeoutError:
                pass
            if stop.is_set():
                break
            try:
                await _refresh_visits_snapshot_once(pool)
            except Exception:
                logger.exception("Periodic visits snapshot refresh failed; last good projection retained")
    except asyncio.CancelledError:
        return
async def _export_cleanup_loop(ctx: dict) -> None:
    from repositories.export_operations import ExportOperationsRepository
    from services.export_operations import cleanup_export_operations, sweep_orphan_export_artifacts
    stop = ctx["export_cleanup_stop"]
    namespace = ctx.get("export_artifact_namespace", "generic")
    repo = ExportOperationsRepository(ctx["db_pool"])
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=EXPORT_CLEANUP_SECONDS)
            except TimeoutError:
                pass
            if not stop.is_set():
                try:
                    await cleanup_export_operations(repo)
                except Exception:
                    logger.exception("Durable export DB cleanup failed")
                try:
                    await sweep_orphan_export_artifacts(repo, namespace=namespace)
                except Exception:
                    logger.exception("Durable export orphan sweep failed")
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Durable export cleanup loop stopped unexpectedly")
async def _queue_metrics_loop(ctx: dict) -> None:
    from observability.worker_metrics import observe_queue
    stop = ctx["queue_metrics_stop"]
    while not stop.is_set():
        try:
            await observe_queue(
                ctx["redis"],
                role=ctx["worker_role"],
                queue_name=ctx["queue_name"],
            )
        except Exception:
            logger.exception("Worker queue metrics refresh failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=QUEUE_METRICS_SECONDS)
        except TimeoutError:
            pass
async def import_sales_background(
    ctx: dict,
    spool_path: str,
    source_digest: str,
    source_byte_size: int,
    filename: str,
    request_id: str | None = None,
    cutoff_date_iso: str | None = None,
    requested_by_sub: str | None = None,
) -> dict:
    from services.sales_import_worker import run_sales_import_job

    return await run_sales_import_job(
        ctx,
        spool_path,
        source_digest,
        source_byte_size,
        filename,
        request_id=request_id,
        cutoff_date_iso=cutoff_date_iso,
        requested_by_sub=requested_by_sub,
    )
async def import_promo_actuals_background(
    ctx: dict,
    spool_path: str,
    source_digest: str,
    source_byte_size: int,
    filename: str,
    import_month: str,
    cutoff_date_iso: str,
) -> dict:
    from repositories.imports import ImportsRepository
    from services.imports import ImportsService
    succeeded = False
    try:
        await asyncio.to_thread(
            verify_sales_import_artifact,
            spool_path,
            source_digest,
            source_byte_size,
        )
        content = await asyncio.to_thread(read_sales_import_spool_file, spool_path, source_digest)
        pool = ctx.get("db_pool")
        if pool is None:
            from db.connection import get_pool
            pool = await get_pool()
        service = ImportsService(ImportsRepository(pool), pool)
        result = await _await_pickle_safe(service.process_promo_actuals(
            content=content, filename=filename, import_month=import_month,
            cutoff_date=date.fromisoformat(cutoff_date_iso),
        ))
        payload = result.model_dump(mode="json")
        succeeded = True
        return payload
    finally:
        # Keep the verified, private artifact after a failed attempt so the
        # deterministic job retry reuses the exact same bytes/path. Startup
        # cleanup removes abandoned failures after the bounded retention TTL.
        if succeeded:
            await asyncio.to_thread(remove_sales_import_spool_file, spool_path)
async def reconcile_erp_background(
    ctx: dict,
    spool_path: str,
    source_digest: str,
    source_byte_size: int,
    filename: str,
    import_month: str,
) -> dict:
    from repositories.erp_reconciliation import ErpReconciliationRepository
    from services.erp_reconciliation import ErpReconciliationService
    succeeded = False
    try:
        await asyncio.to_thread(verify_sales_import_artifact, spool_path, source_digest, source_byte_size)
        content = await asyncio.to_thread(read_sales_import_spool_file, spool_path, source_digest)
        pool = ctx.get("db_pool")
        if pool is None:
            from db.connection import get_pool
            pool = await get_pool()
        service = ErpReconciliationService(ErpReconciliationRepository(pool), pool)
        result = await _await_pickle_safe(service.process(
            content=content, filename=filename, import_month=import_month,
        ))
        payload = result.model_dump(mode="json")
        succeeded = True
        return payload
    finally:
        if succeeded:
            await asyncio.to_thread(remove_sales_import_spool_file, spool_path)
async def promote_sales_background(
    ctx: dict,
    snapshot_id: int,
    generation_token: str,
    owner_id: str,
    manifest_sha256: str,
    requested_by_sub: str,
    override_reason: str | None = None,
    request_id: str | None = None,
) -> dict:
    from services.sales_generation_flow import (
        claim_validated_sales_generation,
        promote_sales_generation,
        restore_sales_generation_claim,
    )
    token = bind_request_id(request_id) if request_id else None
    try:
        pool = ctx.get("db_pool")
        if pool is None:
            from db.connection import get_pool
            pool = await get_pool()
        promotion_finished = False
        previous_owner_id: str | None = None
        async with pool.acquire() as conn:
            try:
                async with conn.transaction():
                    previous_owner_id = await claim_validated_sales_generation(
                        conn,
                        snapshot_id=snapshot_id,
                        generation_token=generation_token,
                        expected_manifest_sha256=manifest_sha256,
                        new_owner_id=owner_id,
                    )
                rows_imported, _ = await promote_sales_generation(
                    conn,
                    snapshot_id=snapshot_id,
                    generation_token=generation_token,
                    owner_id=owner_id,
                    expected_manifest_sha256=manifest_sha256,
                    requested_by_sub=requested_by_sub,
                    override_reason=override_reason,
                )
                promotion_finished = True
            except Exception:
                if previous_owner_id is not None and not promotion_finished:
                    try:
                        async with conn.transaction():
                            await restore_sales_generation_claim(
                                conn,
                                snapshot_id=snapshot_id,
                                generation_token=generation_token,
                                current_owner_id=owner_id,
                                previous_owner_id=previous_owner_id,
                            )
                    except Exception:
                        logger.exception(
                            "Failed to restore sales generation claim snapshot=%s",
                            snapshot_id,
                        )
                raise
            row = await conn.fetchrow(
                """
                SELECT import_month, filename, rows_in_file, rows_imported,
                       is_month_final, coverage_report, manifest
                FROM import_snapshots
                WHERE id = $1 AND status = 'completed'
                """,
                snapshot_id,
            )
            if row is None:
                raise RuntimeError("Promoted sales generation cannot be read back")
            import_month = str(row["import_month"])
        from routers.filters import clear_filter_options_cache
        from services.imports import (
            trigger_campaign_reporting_publication,
            trigger_grile_check_after_import,
        )
        from services.retail_metrics import update_business_metrics
        clear_filter_options_cache()
        await update_business_metrics(pool)
        await trigger_grile_check_after_import(import_month, snapshot_id)
        await trigger_campaign_reporting_publication(
            import_month,
            requested_by_sub="system:sales-promotion",
            reason=f"sales_generation:{snapshot_id}",
        )
        manifest_value = row["manifest"]
        if isinstance(manifest_value, str):
            manifest_value = json.loads(manifest_value)
        coverage_value = row["coverage_report"]
        if isinstance(coverage_value, str):
            coverage_value = json.loads(coverage_value)
        manifest = dict(manifest_value or {})
        return {
            "import_month": import_month,
            "rows_in_file": int(row["rows_in_file"] or 0),
            "rows_imported": rows_imported,
            "rows_filtered": int(manifest.get("rows_filtered", 0)),
            "store_count": int(manifest.get("store_count", 0)),
            "agent_count": int(manifest.get("agent_count", 0)),
            "snapshot_id": snapshot_id,
            "filename": str(row["filename"]),
            "is_month_final": bool(row["is_month_final"]),
            "coverage_report": dict(coverage_value or {}),
            "generation_state": "promoted",
            "generation_token": generation_token,
            "manifest_sha256": manifest_sha256,
            "manifest": manifest,
        }
    finally:
        if token is not None:
            reset_request_id(token)
async def publish_campaign_reporting_background(
    *args: Any,
    **kwargs: Any,
) -> dict:
    from services.campaign_reporting_worker import (
        publish_campaign_reporting_background as run,
    )
    return await run(*args, **kwargs)


async def startup(ctx: dict) -> None:
    raw_worker_role = os.getenv("RETAIL_WORKER_ROLE", "operations").strip().lower()
    runtime = load_runtime_config("import" if raw_worker_role == "imports" else "worker")
    worker_role = runtime.worker_role or "operations"
    ctx["worker_role"] = worker_role
    try:
        from observability.worker_metrics import start_worker_metrics
        ctx["worker_metrics_server"] = start_worker_metrics(worker_role)
        if "redis" in ctx and "queue_name" in ctx:
            ctx["queue_metrics_stop"] = asyncio.Event()
            ctx["queue_metrics_task"] = asyncio.create_task(
                _queue_metrics_loop(ctx), name=f"{worker_role}-queue-metrics"
            )
        await _startup_runtime(ctx, worker_role=worker_role)
    except BaseException:
        logger.exception("Worker startup failed; cleaning partially started resources")
        await shutdown(ctx)
        raise
async def _startup_runtime(ctx: dict, *, worker_role: str) -> None:
    from db.connection import init_db_pool, get_pool
    from services.importer import reconcile_interrupted_imports
    await init_db_pool()
    if worker_role == "imports":
        removed = await asyncio.to_thread(cleanup_stale_sales_import_spool_files)
        if removed:
            logger.info("Removed %d stale sales import spool files", removed)
    pool = await get_pool()
    if worker_role == "imports":
        interrupted = await reconcile_interrupted_imports(pool)
        if interrupted:
            logger.warning(
                "Closed %d interrupted sales import reservations before retry: %s",
                len(interrupted),
                interrupted,
            )
    ctx["db_pool"] = pool
    ctx.setdefault("grile_monthly_sessions", {})
    if worker_role == "imports":
        return
    if worker_role in {"exports", "salary_exports"}:
        from repositories.export_operations import ExportOperationsRepository
        from services.export_operations import (
            ExportArtifactNamespace,
            cleanup_export_operations,
            sweep_orphan_export_artifacts,
        )
        export_repo = ExportOperationsRepository(pool)
        namespace: ExportArtifactNamespace = (
            "salary" if worker_role == "salary_exports" else "generic"
        )
        ctx["export_artifact_namespace"] = namespace
        await cleanup_export_operations(export_repo)
        await sweep_orphan_export_artifacts(export_repo, namespace=namespace)
        ctx["export_cleanup_stop"] = asyncio.Event()
        ctx["export_cleanup_task"] = asyncio.create_task(
            _export_cleanup_loop(ctx), name="durable-export-cleanup"
        )
        return
    if worker_role == "operations":
        try:
            await _refresh_visits_snapshot_once(pool)
        except Exception:
            logger.exception("Initial visits snapshot refresh failed; last good projection retained")
        ctx["visits_snapshot_refresh_stop"] = asyncio.Event()
        ctx["visits_snapshot_refresh_task"] = asyncio.create_task(
            _visits_snapshot_refresh_loop(ctx), name="visits-snapshot-refresh"
        )
        return
    from repositories.grile import GrileRepository
    from services.grile_monthly_google import GoogleSyncAdapter
    grile_run_repo = GrileRepository(pool)
    reconciled_runs = await grile_run_repo.reconcile_stale_runs()
    reconciled_refreshes = await grile_run_repo.reconcile_store_refreshes()
    if reconciled_runs:
        logger.warning("Closed stale Grile runs at worker startup: %s", reconciled_runs)
    if reconciled_refreshes:
        logger.warning(
            "Closed stale Grile store refreshes at worker startup: %s",
            reconciled_refreshes,
        )
    adapter = GoogleSyncAdapter()
    ctx["grile_monthly_google"] = adapter
    await adapter.start()
    await grile_supervisor.reconcile_once(pool, adapter)
    ctx["grile_monthly_reconcile_stop"] = asyncio.Event()
    ctx["grile_monthly_reconcile_task"] = asyncio.create_task(
        grile_supervisor.run_monthly_reconciliation_loop(ctx),
        name="grile-monthly-reconciler",
    )
    grile_supervisor.attach_invariant_restart(
        ctx["grile_monthly_reconcile_task"],
        stop=ctx["grile_monthly_reconcile_stop"],
        name="grile-monthly-reconciler",
    )
    ctx["grile_run_reconcile_stop"] = asyncio.Event()
    ctx["grile_run_reconcile_task"] = asyncio.create_task(
        grile_supervisor.run_stale_run_reconciliation_loop(ctx),
        name="grile-run-reconciler",
    )
    grile_supervisor.attach_invariant_restart(
        ctx["grile_run_reconcile_task"],
        stop=ctx["grile_run_reconcile_stop"],
        name="grile-run-reconciler",
    )
    grile_pilot_v2_runtime.start_grile_pilot_v2_sync(ctx)


async def build_complex_export_background(
    ctx: dict,
    operation_id: int,
) -> dict[str, Any]:
    from services.export_worker import run_durable_export_job

    return await run_durable_export_job(
        ctx,
        operation_id,
        salary_export=False,
        heartbeat=_export_heartbeat_loop,
    )

async def build_salary_export_background(
    ctx: dict,
    operation_id: int,
) -> dict[str, Any]:
    from services.export_worker import run_durable_export_job

    return await run_durable_export_job(
        ctx,
        operation_id,
        salary_export=True,
        heartbeat=_export_heartbeat_loop,
    )
async def grile_check_background(*args: Any, **kwargs: Any) -> dict:
    from services.grile_worker_jobs import grile_check_background as run
    return await run(*args, **kwargs)


async def grile_store_refresh_background(*args: Any, **kwargs: Any) -> dict:
    from services.grile_worker_jobs import grile_store_refresh_background as run
    return await run(*args, **kwargs)


async def grile_monthly_background(*args: Any, **kwargs: Any) -> dict:
    from services.grile_worker_jobs import grile_monthly_background as run
    return await run(*args, **kwargs)


async def grile_agent_targets_background(*args: Any, **kwargs: Any) -> dict:
    from services.grile_worker_jobs import grile_agent_targets_background as run
    return await run(*args, **kwargs)


async def shutdown(ctx: dict) -> None:
    from db.connection import close_db_pool
    from services.jobs import close_arq_pool
    queue_metrics_stop = ctx.get("queue_metrics_stop")
    queue_metrics_task = ctx.get("queue_metrics_task")
    if queue_metrics_stop is not None:
        queue_metrics_stop.set()
    if queue_metrics_task is not None:
        queue_metrics_task.cancel()
        await asyncio.gather(queue_metrics_task, return_exceptions=True)
    export_cleanup_task = ctx.get("export_cleanup_task")
    export_cleanup_stop = ctx.get("export_cleanup_stop")
    if export_cleanup_stop is not None:
        export_cleanup_stop.set()
    if export_cleanup_task is not None:
        export_cleanup_task.cancel()
        await asyncio.gather(export_cleanup_task, return_exceptions=True)
    reconcile_task = ctx.get("grile_monthly_reconcile_task")
    stop = ctx.get("grile_monthly_reconcile_stop")
    if stop is not None:
        stop.set()
    if reconcile_task is not None:
        reconcile_task.cancel()
        await asyncio.gather(reconcile_task, return_exceptions=True)
    run_reconcile_task = ctx.get("grile_run_reconcile_task")
    run_reconcile_stop = ctx.get("grile_run_reconcile_stop")
    if run_reconcile_stop is not None:
        run_reconcile_stop.set()
    if run_reconcile_task is not None:
        run_reconcile_task.cancel()
        await asyncio.gather(run_reconcile_task, return_exceptions=True)
    await grile_pilot_v2_runtime.stop_grile_pilot_v2_sync(ctx)
    visits_task = ctx.get("visits_snapshot_refresh_task")
    visits_stop = ctx.get("visits_snapshot_refresh_stop")
    if visits_stop is not None:
        visits_stop.set()
    if visits_task is not None:
        visits_task.cancel()
        await asyncio.gather(visits_task, return_exceptions=True)
    sessions = ctx.get("grile_monthly_sessions", {})
    active = [task for task in sessions if task is not asyncio.current_task() and not task.done()]
    for task in active:
        task.cancel()
    if active:
        await asyncio.gather(*active, return_exceptions=True)
    adapter = ctx.get("grile_monthly_google")
    if adapter is not None:
        await adapter.close(timeout=30)
    await close_arq_pool()
    await close_db_pool()
    metrics_server = ctx.get("worker_metrics_server")
    if metrics_server is not None:
        await asyncio.to_thread(metrics_server.close)
def main() -> None:
    from env_loader import load_repository_env
    load_repository_env()
    raw_worker_role = os.getenv("RETAIL_WORKER_ROLE", "operations").strip().lower()
    runtime = load_runtime_config("import" if raw_worker_role == "imports" else "worker")
    worker_role = runtime.worker_role or "operations"
    functions_by_role = {
        "imports": [
            import_sales_background,
            import_promo_actuals_background,
            reconcile_erp_background,
            promote_sales_background,
            publish_campaign_reporting_background,
        ],
        "grile": [
            grile_check_background,
            func(grile_store_refresh_background, max_tries=1),
            func(grile_monthly_background, timeout=runtime.arq_job_timeout_seconds, max_tries=1),
            grile_agent_targets_background,
            grile_pilot_v2_sync_background,
        ],
        "exports": [func(build_complex_export_background, max_tries=1), func(remove_export_artifact_background, max_tries=3)],
        "salary_exports": [func(build_salary_export_background, max_tries=1), func(remove_export_artifact_background, max_tries=3)],
        "operations": [func(refresh_visits_snapshot_background, max_tries=1)],
    }
    functions = functions_by_role[worker_role]
    queue_name = {
        "imports": SALES_IMPORT_QUEUE_NAME,
        "grile": GRILE_QUEUE_NAME,
        "exports": EXPORT_QUEUE_NAME,
        "salary_exports": SALARY_EXPORT_QUEUE_NAME,
        "operations": OPERATIONS_QUEUE_NAME,
    }[worker_role]
    from observability.worker_metrics import observe_job_end, observe_job_start
    worker_settings: dict[str, Any] = {
        "redis_settings": get_valkey_settings(),
        "functions": functions,
        "on_startup": startup,
        "on_shutdown": shutdown,
        "on_job_start": observe_job_start,
        "after_job_end": observe_job_end,
        "job_completion_wait": runtime.arq_completion_wait_seconds,
        "max_jobs": runtime.arq_max_jobs,
        "job_timeout": runtime.arq_job_timeout_seconds,
        "keep_result": runtime.arq_keep_result_seconds,
        "health_check_interval": 30,
        "retry_jobs": True,
        "ctx": {"worker_role": worker_role, "queue_name": queue_name},
    }
    worker_settings["queue_name"] = queue_name
    worker = create_worker(worker_settings)
    worker.run()
if __name__ == "__main__":
    main()
