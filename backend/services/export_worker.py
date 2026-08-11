from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Literal
from uuid import uuid4

if TYPE_CHECKING:
    from services.export_operations import StoredExportArtifact
    from services.exports import XlsxArtifact


logger = logging.getLogger(__name__)

ExportHeartbeat = Callable[..., Coroutine[Any, Any, None]]


@dataclass
class _ExportExecution:
    repo: Any
    pool: Any
    operation_id: int
    execution_owner: str
    execution_epoch: int
    salary_export: bool
    xlsx: XlsxArtifact | None = None
    stored: StoredExportArtifact | None = None

    @property
    def namespace(self) -> Literal["generic", "salary"]:
        return "salary" if self.salary_export else "generic"


async def remove_export_artifact_background(
    ctx: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    """Remove one artifact only inside the queue's filesystem authority."""
    salary_namespace = key.startswith("salary/")
    expected_role = "salary_exports" if salary_namespace else "exports"
    if ctx.get("worker_role") != expected_role:
        raise RuntimeError("Export artifact cleanup reached the wrong worker authority")
    from services.export_operations import remove_export_artifact

    await asyncio.to_thread(remove_export_artifact, key)
    return {
        "artifact_removed": True,
        "namespace": "salary" if salary_namespace else "generic",
    }


async def export_heartbeat_loop(
    repo: Any,
    *,
    operation_id: int,
    execution_owner: str,
    execution_epoch: int,
    worker_task: asyncio.Task[Any],
) -> None:
    from services.export_operations import EXPORT_EXECUTION_LEASE_SECONDS

    try:
        while True:
            await asyncio.sleep(20)
            retained = await repo.heartbeat(
                operation_id,
                execution_owner=execution_owner,
                execution_epoch=execution_epoch,
                lease_seconds=EXPORT_EXECUTION_LEASE_SECONDS,
            )
            if not retained:
                worker_task.cancel()
                return
    except asyncio.CancelledError:
        return


async def _build_artifact(
    execution: _ExportExecution,
    *,
    request_payload: dict[str, Any],
    persisted_kind: str,
) -> XlsxArtifact:
    from repositories.exports import ExportsRepository
    from services import exports as exports_package

    if execution.salary_export:
        from services.salary_exports import SalaryExportsService

        salary_service = SalaryExportsService(execution.pool)
        normalized_request, validated_kind = salary_service.validate_request(request_payload)
        if validated_kind != persisted_kind:
            raise exports_package.ExportValidationError(
                "Tipul exportului nu corespunde cererii persistate."
            )
        return await salary_service.build_xlsx_artifact(normalized_request)
    export_service = exports_package.ExportsService(ExportsRepository(execution.pool))
    if export_service.validate_complex_request(request_payload) != persisted_kind:
        raise exports_package.ExportValidationError(
            "Tipul exportului nu corespunde cererii persistate."
        )
    return await export_service.build_xlsx_artifact(request_payload)


async def _persist_and_complete(
    execution: _ExportExecution,
    *,
    request_payload: dict[str, Any],
    persisted_kind: str,
) -> dict[str, Any]:
    import services.export_operations as operations

    xlsx = await _build_artifact(
        execution,
        request_payload=request_payload,
        persisted_kind=persisted_kind,
    )
    execution.xlsx = xlsx
    stored = await asyncio.to_thread(
        operations.persist_export_artifact,
        xlsx,
        namespace=execution.namespace,
    )
    execution.stored = stored
    xlsx.close()
    execution.xlsx = None
    completed = await execution.repo.complete(
        execution.operation_id,
        execution_owner=execution.execution_owner,
        execution_epoch=execution.execution_epoch,
        artifact_key=stored.key,
        artifact_sha256=stored.sha256,
        artifact_size=stored.size,
        peak_rss_bytes=stored.peak_rss_bytes,
        build_seconds=stored.build_seconds,
        cell_count=stored.cell_count,
        row_count=stored.row_count,
        download_filename=stored.filename,
        ttl_seconds=operations.export_artifact_ttl_seconds(),
    )
    if not completed:
        await asyncio.to_thread(operations.remove_export_artifact, stored.key)
        current = await execution.repo.get(execution.operation_id)
        return {
            "operation_id": execution.operation_id,
            "status": str(current.get("status")) if current else "not_found",
        }
    return {
        "operation_id": execution.operation_id,
        "status": "completed",
        "artifact_sha256": stored.sha256,
        "artifact_size": stored.size,
        "row_count": stored.row_count,
    }


async def _fail_execution(
    execution: _ExportExecution,
    *,
    error_code: str,
    cancelled: bool = False,
) -> None:
    import services.export_operations as operations

    stored = execution.stored
    if stored is not None:
        await asyncio.to_thread(
            operations.remove_export_artifact,
            stored.key,
        )
    await execution.repo.fail_running(
        execution.operation_id,
        execution_owner=execution.execution_owner,
        execution_epoch=execution.execution_epoch,
        error_code=error_code,
        cancelled=cancelled,
    )


async def _finish_execution(
    execution: _ExportExecution,
    heartbeat_task: asyncio.Task[None],
) -> None:
    import services.export_operations as operations

    heartbeat_task.cancel()
    await asyncio.gather(heartbeat_task, return_exceptions=True)
    if execution.xlsx is not None:
        execution.xlsx.close()
    try:
        await operations.sweep_orphan_export_artifacts(
            execution.repo,
            namespace=execution.namespace,
        )
    except Exception:
        logger.exception(
            "Export orphan sweep failed operation_id=%s",
            execution.operation_id,
        )


async def run_durable_export_job(
    ctx: dict[str, Any],
    operation_id: int,
    *,
    salary_export: bool,
    heartbeat: ExportHeartbeat = export_heartbeat_loop,
) -> dict[str, Any]:
    if isinstance(operation_id, bool) or not isinstance(operation_id, int) or operation_id <= 0:
        raise ValueError("Invalid durable export operation id")
    import repositories.export_operations as repository_module
    from services.export_operations import EXPORT_EXECUTION_LEASE_SECONDS

    pool = ctx.get("db_pool")
    if pool is None:
        from db.connection import get_pool

        pool = await get_pool()
    repo = repository_module.ExportOperationsRepository(pool)
    execution_owner = uuid4().hex
    operation = await repo.claim(
        operation_id,
        execution_owner=execution_owner,
        lease_seconds=EXPORT_EXECUTION_LEASE_SECONDS,
        allowed_kinds=(
            ("salary_store_summary", "salary_monthly_trend", "salary_agents")
            if salary_export
            else ("daily_metrics", "daily_comparison")
        ),
    )
    if operation is None:
        current = await repo.get(operation_id)
        return {
            "operation_id": operation_id,
            "status": str(current.get("status")) if current else "not_found",
        }
    execution = _ExportExecution(
        repo=repo,
        pool=pool,
        operation_id=operation_id,
        execution_owner=execution_owner,
        execution_epoch=int(operation["execution_epoch"]),
        salary_export=salary_export,
    )
    request_payload = operation.get("request_payload")
    if not isinstance(request_payload, dict):
        await _fail_execution(execution, error_code="invalid_persisted_request")
        raise RuntimeError("Complex export has an invalid persisted request")
    worker_task = asyncio.current_task()
    if worker_task is None:
        raise RuntimeError("Complex export worker task is unavailable")
    heartbeat_task = asyncio.create_task(
        heartbeat(
            repo,
            operation_id=operation_id,
            execution_owner=execution_owner,
            execution_epoch=execution.execution_epoch,
            worker_task=worker_task,
        ),
        name=f"export-heartbeat:{operation_id}",
    )
    try:
        return await _persist_and_complete(
            execution,
            request_payload=request_payload,
            persisted_kind=str(operation["kind"]),
        )
    except asyncio.CancelledError:
        while worker_task.cancelling():
            worker_task.uncancel()
        await asyncio.shield(
            asyncio.create_task(
                _fail_execution(
                    execution,
                    error_code="worker_cancelled",
                    cancelled=True,
                )
            )
        )
        raise
    except Exception:
        await _fail_execution(
            execution,
            error_code=(
                "salary_export_worker_failed"
                if salary_export
                else "export_worker_failed"
            ),
        )
        raise RuntimeError("Complex export worker failed") from None
    finally:
        await _finish_execution(execution, heartbeat_task)
