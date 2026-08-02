from __future__ import annotations

import asyncio
from datetime import date
import json
import logging
import os
from typing import Any

from arq.worker import create_worker, func

from logging_config import setup_logging
from request_context import bind_request_id, reset_request_id
from services.jobs import (
    SALES_IMPORT_QUEUE_NAME,
    cleanup_stale_sales_import_spool_files,
    get_valkey_settings,
    read_sales_import_spool_file,
    remove_sales_import_spool_file,
    retain_sales_import_spool_file,
)


setup_logging()
logger = logging.getLogger(__name__)


async def import_sales_background(
    ctx: dict,
    file_reference: bytes | str,
    digest_or_filename: str,
    filename_or_request_id: str | None = None,
    request_id: str | None = None,
    cutoff_date_iso: str | None = None,
    requested_by_sub: str | None = None,
) -> dict:
    from dataclasses import asdict
    from services.importer import import_sales_file
    from services.sales_generation_flow import attach_sales_generation_source

    spool_path: str | None = None
    staged = False
    if isinstance(file_reference, bytes):
        # Compatibilitate pentru joburile publicate înainte de migrarea la
        # spool: bytes, filename, request_id.
        legacy_content = file_reference
        filename = digest_or_filename
        legacy_request_id = filename_or_request_id
        if request_id is None:
            request_id = legacy_request_id
    else:
        spool_path = file_reference
        if not filename_or_request_id:
            raise ValueError("Sales import filename is missing")
        filename = filename_or_request_id

    token = bind_request_id(request_id) if request_id else None
    cutoff = date.fromisoformat(cutoff_date_iso) if cutoff_date_iso else None
    actor = requested_by_sub or "legacy-direct"
    try:
        if isinstance(file_reference, bytes):
            file_content = legacy_content
        else:
            assert spool_path is not None
            file_content = await asyncio.to_thread(
                read_sales_import_spool_file,
                spool_path,
                digest_or_filename,
            )
        conn = ctx.get("db_conn")
        if conn is None:
            from db.connection import get_pool
            pool = await get_pool()
            async with pool.acquire() as conn:
                result = await import_sales_file(
                    conn,
                    file_content,
                    filename=filename,
                    cutoff_date=cutoff,
                    stage_only=True,
                    requested_by_sub=actor,
                )
                staged = True
                if spool_path is not None:
                    assert result.generation_token is not None
                    assert result.owner_id is not None
                    await attach_sales_generation_source(
                        conn,
                        snapshot_id=result.snapshot_id,
                        generation_token=result.generation_token,
                        owner_id=result.owner_id,
                        source_spool_path=spool_path,
                    )
        else:
            result = await import_sales_file(
                conn,
                file_content,
                filename=filename,
                cutoff_date=cutoff,
                stage_only=True,
                requested_by_sub=actor,
            )
            staged = True
            if spool_path is not None:
                assert result.generation_token is not None
                assert result.owner_id is not None
                await attach_sales_generation_source(
                    conn,
                    snapshot_id=result.snapshot_id,
                    generation_token=result.generation_token,
                    owner_id=result.owner_id,
                    source_spool_path=spool_path,
                )
        return asdict(result)
    finally:
        if spool_path is not None and not staged:
            await asyncio.to_thread(remove_sales_import_spool_file, spool_path)
        if token is not None:
            reset_request_id(token)


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
    from services.sales_generation_flow import promote_sales_generation

    token = bind_request_id(request_id) if request_id else None
    try:
        pool = ctx.get("db_pool")
        if pool is None:
            from db.connection import get_pool
            pool = await get_pool()
        async with pool.acquire() as conn:
            source_spool_path = await conn.fetchval(
                "SELECT source_spool_path FROM import_snapshots WHERE id = $1",
                snapshot_id,
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
            if source_spool_path:
                try:
                    retained_path = await asyncio.to_thread(
                        retain_sales_import_spool_file,
                        str(source_spool_path),
                        import_month=import_month,
                        snapshot_id=snapshot_id,
                    )
                    await conn.execute(
                        """
                        UPDATE import_snapshots
                        SET source_spool_path = $4
                        WHERE id = $1
                          AND generation_token = $2::uuid
                          AND owner_id = $3::uuid
                          AND status = 'completed'
                        """,
                        snapshot_id,
                        generation_token,
                        owner_id,
                        str(retained_path),
                    )
                except Exception:
                    logger.exception("Failed to retain terminal sales source snapshot=%s", snapshot_id)

        from routers.filters import clear_filter_options_cache
        from services.imports import trigger_grile_check_after_import
        from services.retail_metrics import update_business_metrics

        clear_filter_options_cache()
        await update_business_metrics(pool)
        await trigger_grile_check_after_import(import_month, snapshot_id)
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


async def startup(ctx: dict) -> None:
    from db.connection import init_db_pool, get_pool
    from services.importer import reconcile_interrupted_imports

    await init_db_pool()
    worker_role = os.getenv("RETAIL_WORKER_ROLE", "operations").strip().lower()
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
    operation_id: int | str,
    legacy_month: str | None = None,
    legacy_only: str | None = None,
    legacy_dry_run: bool | None = None,
    legacy_triggered_by_email: str | None = None,
    legacy_operation_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    """Inchidere luna grile: ruleaza operatiile native din Retail.

    Ruleaza in worker fiindca operatia poate dura minute (peste timeout-ul de
    edge Cloudflare). Rezultatul (output + exit_code) e citit din rezultatul
    jobului arq de catre UI (`/api/grile/monthly/job/{id}`).
    """
    if isinstance(operation_id, bool):
        raise ValueError("Invalid Grile monthly operation identity")
    if isinstance(operation_id, int):
        if any(
            value is not None
            for value in (
                legacy_month,
                legacy_only,
                legacy_dry_run,
                legacy_triggered_by_email,
                legacy_operation_id,
            )
        ):
            raise ValueError("Unexpected legacy Grile monthly payload")
        persisted_operation_id = operation_id
    else:
        # Jobs published before v2.0.1 carry the full request payload. The DB
        # reservation remains authoritative: normalize only its immutable id
        # and never authorize or execute from the legacy email/op arguments.
        if isinstance(legacy_operation_id, bool) or not isinstance(
            legacy_operation_id, int
        ):
            raise ValueError("Legacy Grile monthly job has no operation identity")
        persisted_operation_id = legacy_operation_id
    if persisted_operation_id <= 0:
        raise ValueError("Invalid Grile monthly operation identity")

    token = bind_request_id(request_id) if request_id else None
    try:
        from services.grile_monthly import (
            fail_monthly_operation,
            mark_monthly_operation_cancelled_uncertain,
            run_monthly_op,
        )

        try:
            return await run_monthly_op(operation_id=persisted_operation_id)
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
                mark_monthly_operation_cancelled_uncertain(
                    pool,
                    persisted_operation_id,
                    error_message=(
                        "Operatia lunara Grile a fost anulata; "
                        "efectele destructive neconfirmate sunt uncertain"
                    ),
                )
            )
            try:
                await asyncio.shield(cleanup_task)
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
                await fail_monthly_operation(
                    pool,
                    persisted_operation_id,
                    error_message="Operatia lunara Grile a esuat neasteptat in worker",
                )
            except Exception:  # noqa: BLE001 - preserve the original worker failure
                logger.exception(
                    "Could not fail unexpected Grile monthly operation operation_id=%s",
                    persisted_operation_id,
                )
            raise
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

    worker_role = os.getenv("RETAIL_WORKER_ROLE", "operations").strip().lower()
    if worker_role not in {"operations", "imports"}:
        raise RuntimeError("RETAIL_WORKER_ROLE must be operations or imports")
    functions = (
        [import_sales_background, promote_sales_background]
        if worker_role == "imports"
        else [
            # Păstrat temporar și aici pentru joburile legacy publicate în
            # coada implicită înainte de separarea cozilor.
            import_sales_background,
            promote_sales_background,
            grile_check_background,
            func(grile_monthly_background, timeout=2400, max_tries=1),
            grile_agent_targets_background,
        ]
    )
    worker_settings: dict[str, Any] = {
        "redis_settings": get_valkey_settings(),
        "functions": functions,
        "on_startup": startup,
        "on_shutdown": shutdown,
        "job_completion_wait": 1800 if worker_role == "imports" else 2400,
        "max_jobs": 1,
        "job_timeout": 1800,
        "keep_result": 3600,
        "health_check_interval": 30,
        "retry_jobs": True,
    }
    if worker_role == "imports":
        worker_settings["queue_name"] = SALES_IMPORT_QUEUE_NAME
    worker = create_worker(worker_settings)
    worker.run()


if __name__ == "__main__":
    main()
