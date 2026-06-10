from __future__ import annotations

import asyncio
from arq.worker import create_worker

from services.jobs import get_valkey_settings


async def import_sales_background(ctx: dict, file_content: bytes, filename: str) -> dict:
    from dataclasses import asdict
    from services.importer import import_sales_file

    conn = ctx.get("db_conn")
    if conn is None:
        from db.connection import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await import_sales_file(conn, file_content, filename=filename)
    else:
        result = await import_sales_file(conn, file_content, filename=filename)

    # Best-effort: dupa import reusit + reporting rebuild (in tranzactia din
    # import_sales_file), declanseaza verificarea grilelor. Nu propaga erori.
    from services.imports import trigger_grile_check_after_import
    await trigger_grile_check_after_import(result.import_month, result.snapshot_id)
    return asdict(result)


async def startup(ctx: dict) -> None:
    from db.connection import init_db_pool, get_pool
    await init_db_pool()
    pool = await get_pool()
    ctx["db_pool"] = pool


async def grile_check_background(
    ctx: dict,
    month: str,
    source: str = "manual",
    source_snapshot_id: int | None = None,
    triggered_by_email: str | None = None,
) -> dict:
    from services.grile import run_grile_check

    pool = ctx.get("db_pool")
    if pool is None:
        from db.connection import get_pool
        pool = await get_pool()
    run_id = await run_grile_check(
        pool,
        month=month,
        source=source,
        source_snapshot_id=source_snapshot_id,
        triggered_by_email=triggered_by_email,
    )
    agent_targets: dict | None = None
    try:
        from services.grile_agent_targets import sync_agent_targets_from_grile
        result = await sync_agent_targets_from_grile(pool, month=month, apply=True)
        agent_targets = result.as_dict()
    except Exception as exc:  # noqa: BLE001 - sync-ul agentilor nu invalideaza verificarea grilelor
        agent_targets = {"status": "failed", "error": str(exc)[:500]}
    return {"run_id": run_id, "month": month, "agent_targets": agent_targets}


async def grile_monthly_background(
    ctx: dict,
    op: str,
    month: str,
    only: str | None = None,
    dry_run: bool = True,
    triggered_by_email: str | None = None,
) -> dict:
    """Inchidere luna grile: ruleaza operatiile native din Retail.

    Ruleaza in worker fiindca operatia poate dura minute (peste timeout-ul de
    edge Cloudflare). Rezultatul (output + exit_code) e citit din rezultatul
    jobului arq de catre UI (`/api/grile/monthly/job/{id}`).
    """
    from services.grile_monthly import run_monthly_op

    result = await run_monthly_op(op=op, month=month, only=only, dry_run=dry_run)
    result["triggered_by_email"] = triggered_by_email
    return result


async def shutdown(ctx: dict) -> None:
    from db.connection import close_db_pool
    await close_db_pool()



async def main() -> None:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv())

    worker_settings = {
        "redis_settings": get_valkey_settings(),
        "functions": [import_sales_background, grile_check_background, grile_monthly_background],
        "on_startup": startup,
        "on_shutdown": shutdown,
    }
    worker = create_worker(worker_settings)
    await worker.async_run()


if __name__ == "__main__":
    asyncio.run(main())
