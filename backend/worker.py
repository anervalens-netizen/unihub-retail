from __future__ import annotations

import os
import asyncio
from arq.worker import create_worker

from services.jobs import get_valkey_settings


async def import_sales_background(ctx: dict, file_content: bytes, filename: str) -> dict:
    conn = ctx.get("db_conn")
    if conn is None:
        from db.connection import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            from services.importer import import_sales_file
            from dataclasses import asdict
            result = await import_sales_file(conn, file_content, filename=filename)
            return asdict(result)
    else:
        from services.importer import import_sales_file
        from dataclasses import asdict
        result = await import_sales_file(conn, file_content, filename=filename)
        return asdict(result)


async def startup(ctx: dict) -> None:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv())
    from db.connection import init_db_pool, get_pool
    await init_db_pool()
    pool = await get_pool()
    ctx["db_pool"] = pool


async def shutdown(ctx: dict) -> None:
    from db.connection import close_db_pool
    await close_db_pool()


async def main() -> None:
    worker = create_worker(
        get_valkey_settings(),
        functions=[import_sales_background],
        on_startup=startup,
        on_shutdown=shutdown,
    )
    await worker.async_run()


if __name__ == "__main__":
    asyncio.run(main())
