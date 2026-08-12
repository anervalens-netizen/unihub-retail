from __future__ import annotations

import asyncio
from dataclasses import replace
import logging
from uuid import uuid4

from request_context import bind_request_id, reset_request_id


logger = logging.getLogger(__name__)


async def grile_check_background(
    ctx: dict,
    month: str,
    source: str = "manual",
    source_snapshot_id: int | None = None,
    triggered_by_sub: str | None = None,
    run_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    from services.grile import run_grile_check
    token = bind_request_id(request_id) if request_id else None
    try:
        pool = ctx.get("db_pool")
        if pool is None:
            from db.connection import get_pool
            pool = await get_pool()
        from services.grile_agent_targets import (
            read_agent_targets_state,
            sync_agent_targets_from_grile,
        )
        before = await read_agent_targets_state(pool, month)
        try:
            run_id = await run_grile_check(
                pool,
                month=month,
                source=source,
                source_snapshot_id=source_snapshot_id,
                triggered_by_sub=triggered_by_sub,
                run_id=run_id,
            )
            agent_targets: dict | None = None
            try:
                result = await sync_agent_targets_from_grile(pool, month=month)
                agent_targets = result.as_dict()
            except Exception:  # noqa: BLE001 - diff-ul agentilor nu invalideaza verificarea grilelor
                agent_targets = {"status": "failed", "error": "Grile target diff failed"}
        finally:
            after = await read_agent_targets_state(pool, month)
            if before != after:
                raise RuntimeError("Grile check modified agent_targets")
        return {
            "run_id": run_id,
            "month": month,
            "agent_targets": agent_targets,
            "agent_targets_before_sha256": before.sha256,
            "agent_targets_after_sha256": after.sha256,
        }
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current is not None:
            while current.cancelling():
                current.uncancel()
        await asyncio.shield(
            asyncio.create_task(
                _terminalize_grile_run_after_worker_exit(
                    ctx,
                    run_id=run_id,
                    error_message="grile_run_worker_cancelled",
                )
            )
        )
        raise
    except TimeoutError:
        await _terminalize_grile_run_after_worker_exit(
            ctx,
            run_id=run_id,
            error_message="grile_run_worker_timeout",
        )
        raise
    except Exception:
        await _terminalize_grile_run_after_worker_exit(
            ctx,
            run_id=run_id,
            error_message="grile_run_worker_failed",
        )
        raise
    finally:
        if token is not None:
            reset_request_id(token)
async def _terminalize_grile_run_after_worker_exit(
    ctx: dict,
    *,
    run_id: int | None,
    error_message: str,
) -> None:
    if run_id is None:
        return
    try:
        pool = ctx.get("db_pool")
        if pool is None:
            from db.connection import get_pool
            pool = await get_pool()
        from repositories.grile import GrileRepository
        await GrileRepository(pool).fail_run(
            int(run_id),
            error_message=error_message,
        )
    except Exception:  # noqa: BLE001 - preserve the original ARQ terminal event
        logger.exception(
            "Could not terminalize Grile run after worker exit run_id=%s",
            run_id,
        )
async def grile_store_refresh_background(
    ctx: dict,
    refresh_id: int,
    request_id: str | None = None,
) -> dict:
    from services.grile import run_grile_store_refresh
    token = bind_request_id(request_id) if request_id else None
    try:
        pool = ctx.get("db_pool")
        if pool is None:
            from db.connection import get_pool
            pool = await get_pool()
        return await run_grile_store_refresh(pool, refresh_id=refresh_id)
    finally:
        if token is not None:
            reset_request_id(token)


async def grile_monthly_background(ctx: dict, operation_id: int) -> dict:
    """Inchidere luna grile: ruleaza operatiile native din Retail.
    Ruleaza in worker fiindca operatia poate dura minute (peste timeout-ul de
    edge Cloudflare). Rezultatul (output + exit_code) e citit din rezultatul
    jobului arq de catre UI (`/api/grile/monthly/job/{id}`).
    """
    if isinstance(operation_id, bool) or not isinstance(operation_id, int) or operation_id <= 0:
        raise ValueError("Invalid persisted Grile monthly operation identity")
    persisted_operation_id = operation_id
    token = bind_request_id(f"grile-monthly:{persisted_operation_id}")
    session_task = asyncio.current_task()
    sessions = ctx.setdefault("grile_monthly_sessions", {})
    sessions[session_task] = persisted_operation_id
    try:
        from services.grile_monthly import (
            fail_monthly_operation,
            get_monthly_execution_lease,
            mark_monthly_operation_cancelled_uncertain,
            run_monthly_op,
        )
        execution_owner = uuid4().hex
        try:
            adapter = ctx.get("grile_monthly_google")
            if adapter is None:
                return await run_monthly_op(
                    operation_id=persisted_operation_id,
                    execution_owner_hint=execution_owner,
                )
            return await run_monthly_op(
                operation_id=persisted_operation_id,
                execution_owner_hint=execution_owner,
                google_adapter=adapter,
            )
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None:
                while current.cancelling():
                    current.uncancel()
            pool = ctx.get("db_pool")
            if pool is None:
                from db.connection import get_pool
                pool = await get_pool()
            cleanup_task = asyncio.create_task(
                get_monthly_execution_lease(
                    pool,
                    persisted_operation_id,
                    execution_owner=execution_owner,
                )
            )
            try:
                lease = await asyncio.shield(cleanup_task)
                if lease is not None:
                    await asyncio.shield(
                        asyncio.create_task(
                            mark_monthly_operation_cancelled_uncertain(
                                pool,
                                persisted_operation_id,
                                error_message="monthly_operation_cancelled_uncertain",
                                execution_owner=lease.execution_owner,
                                execution_epoch=lease.execution_epoch,
                            )
                        )
                    )
            except BaseException:  # process shutdown may interrupt even the fallback checkpoint
                logger.exception(
                    "Could not persist cancelled Grile operation operation_id=%s",
                    persisted_operation_id,
                )
            raise
        except Exception:
            pool = ctx.get("db_pool")
            if pool is None:
                from db.connection import get_pool
                pool = await get_pool()
            try:
                lease = await get_monthly_execution_lease(
                    pool,
                    persisted_operation_id,
                    execution_owner=execution_owner,
                )
                if lease is not None:
                    await fail_monthly_operation(
                        pool,
                        persisted_operation_id,
                        error_message="monthly_operation_worker_failed",
                        execution_owner=lease.execution_owner,
                        execution_epoch=lease.execution_epoch,
                    )
            except Exception:  # noqa: BLE001 - preserve the original worker failure
                logger.exception(
                    "Could not fail unexpected Grile monthly operation operation_id=%s",
                    persisted_operation_id,
                )
            raise
    finally:
        sessions.pop(session_task, None)
        reset_request_id(token)
async def grile_agent_targets_background(
    ctx: dict,
    operation_id: int,
    request_id: str | None = None,
) -> dict:
    token = bind_request_id(request_id) if request_id else None
    try:
        from repositories.grile_agent_target_sync import (
            GrileAgentTargetSyncRepository,
        )
        from services.grile_agent_targets import (
            apply_agent_target_sync_on_connection,
            read_agent_targets_state,
            read_agent_targets_state_on_connection,
            require_applicable_agent_target_sync,
            sync_agent_targets_from_grile,
        )
        from dataclasses import replace
        pool = ctx.get("db_pool")
        if pool is None:
            from db.connection import get_pool
            pool = await get_pool()
        repo = GrileAgentTargetSyncRepository(pool)
        operation = await repo.start(operation_id)
        if operation is None:
            current = await repo.get(operation_id)
            return {
                "operation_id": operation_id,
                "status": current.get("status") if current is not None else "not_found",
                "mode": current.get("mode") if current is not None else None,
            }
        try:
            month = str(operation["run_month"])
            mode = str(operation["mode"])
            if mode not in {"dry_run", "sync"}:
                raise RuntimeError("Invalid persisted Grile target operation mode")
            before = await read_agent_targets_state(pool, month)
            result = await sync_agent_targets_from_grile(pool, month=month)
            if mode == "sync":
                require_applicable_agent_target_sync(result)
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute(
                            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                            f"unihub:grile-agent-targets:{month}",
                        )
                        locked_before = await read_agent_targets_state_on_connection(
                            conn, month
                        )
                        if locked_before != before:
                            raise RuntimeError(
                                "Agent targets changed while the sync diff was prepared"
                            )
                        await apply_agent_target_sync_on_connection(conn, result)
                        result = replace(result, apply=True)
                        after = await read_agent_targets_state_on_connection(conn, month)
                        completed = await repo.finish_on_connection(
                            conn,
                            operation_id,
                            before_sha256=before.sha256,
                            after_sha256=after.sha256,
                            before_count=before.row_count,
                            after_count=after.row_count,
                            diff=result.as_dict(),
                        )
                        if not completed:
                            raise RuntimeError("Target sync operation lost its DB lease")
            else:
                after = await read_agent_targets_state(pool, month)
                if before != after:
                    raise RuntimeError("Dry-run modified agent_targets")
                completed = await repo.finish(
                    operation_id,
                    before_sha256=before.sha256,
                    after_sha256=after.sha256,
                    before_count=before.row_count,
                    after_count=after.row_count,
                    diff=result.as_dict(),
                )
                if not completed:
                    raise RuntimeError("Target diff operation lost its DB lease")
            return {
                "operation_id": operation_id,
                "mode": mode,
                "before_sha256": before.sha256,
                "after_sha256": after.sha256,
                "before_count": before.row_count,
                "after_count": after.row_count,
                "diff": result.as_dict(),
            }
        except Exception:
            await repo.fail(operation_id, "Operatia Grile targete a esuat")
            raise RuntimeError("Grile agent target operation failed") from None
    finally:
        if token is not None:
            reset_request_id(token)

