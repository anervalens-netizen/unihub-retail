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
    return {"run_id": run_id, "month": month}


async def shutdown(ctx: dict) -> None:
    from db.connection import close_db_pool
    await close_db_pool()



async def main() -> None:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv())

    worker_settings = {
        "redis_settings": get_valkey_settings(),
        "functions": [import_sales_background, grile_check_background],
        "on_startup": startup,
        "on_shutdown": shutdown,
    }
    worker = create_worker(worker_settings)
    await worker.async_run()


if __name__ == "__main__":
    asyncio.run(main())
