from __future__ import annotations

import logging

from arq.worker import create_worker

from logging_config import setup_logging
from request_context import bind_request_id, reset_request_id
from services.jobs import get_valkey_settings


setup_logging()
logger = logging.getLogger(__name__)


async def import_sales_background(
    ctx: dict,
    file_content: bytes,
    filename: str,
    request_id: str | None = None,
) -> dict:
    from dataclasses import asdict
    from services.importer import import_sales_file

    token = bind_request_id(request_id) if request_id else None
    try:
        conn = ctx.get("db_conn")
        if conn is None:
            from db.connection import get_pool
            pool = await get_pool()
            async with pool.acquire() as conn:
                result = await import_sales_file(conn, file_content, filename=filename)
        else:
            result = await import_sales_file(conn, file_content, filename=filename)

        from routers.filters import clear_filter_options_cache
        from services.retail_metrics import update_business_metrics

        clear_filter_options_cache()
        pool = ctx.get("db_pool")
        if pool is None:
            from db.connection import get_pool
            pool = await get_pool()
        await update_business_metrics(pool)

        # Best-effort: dupa import reusit + reporting rebuild (in tranzactia din
        # import_sales_file), declanseaza verificarea grilelor. Nu propaga erori.
        from services.imports import trigger_grile_check_after_import
        await trigger_grile_check_after_import(result.import_month, result.snapshot_id)
        return asdict(result)
    finally:
        if token is not None:
            reset_request_id(token)


async def startup(ctx: dict) -> None:
    from db.connection import init_db_pool, get_pool
    from services.importer import reconcile_interrupted_imports

    await init_db_pool()
    pool = await get_pool()
    interrupted = await reconcile_interrupted_imports(pool)
    if interrupted:
        logger.warning(
            "Closed %d interrupted sales import reservations before retry: %s",
            len(interrupted),
            interrupted,
        )
    ctx["db_pool"] = pool


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
    finally:
        if token is not None:
            reset_request_id(token)


async def grile_monthly_background(
    ctx: dict,
    operation_id: int,
    request_id: str | None = None,
) -> dict:
    """Inchidere luna grile: ruleaza operatiile native din Retail.

    Ruleaza in worker fiindca operatia poate dura minute (peste timeout-ul de
    edge Cloudflare). Rezultatul (output + exit_code) e citit din rezultatul
    jobului arq de catre UI (`/api/grile/monthly/job/{id}`).
    """
    token = bind_request_id(request_id) if request_id else None
    try:
        from services.grile_monthly import run_monthly_op

        return await run_monthly_op(operation_id=operation_id)
    finally:
        if token is not None:
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


async def shutdown(ctx: dict) -> None:
    from db.connection import close_db_pool
    from services.jobs import close_arq_pool

    await close_arq_pool()
    await close_db_pool()


def main() -> None:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv())

    worker_settings = {
        "redis_settings": get_valkey_settings(),
        "functions": [
            import_sales_background,
            grile_check_background,
            grile_monthly_background,
            grile_agent_targets_background,
        ],
        "on_startup": startup,
        "on_shutdown": shutdown,
        "job_completion_wait": 60,
        "max_jobs": 1,
        "job_timeout": 1800,
        "keep_result": 3600,
        "health_check_interval": 30,
        "retry_jobs": True,
    }
    worker = create_worker(worker_settings)
    worker.run()


if __name__ == "__main__":
    main()
