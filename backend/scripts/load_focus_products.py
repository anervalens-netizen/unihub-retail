from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.connection import close_db_pool, ensure_schema_current, get_pool, init_db_pool
from services.product_lists import sync_focus_products
from services.reporting_refresh import rebuild_reporting_all


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sincronizeaza focus products din Excel"
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        default="data/Coduri produse focus.xlsx",
        help="Fisierul Excel cu codurile focus, relativ la /app sau absolut",
    )
    args = parser.parse_args()

    requested = Path(args.input_path)
    if not requested.is_absolute():
        requested = (ROOT_DIR.parent / requested).resolve()
    if not requested.exists():
        raise FileNotFoundError(f"Fisierul nu exista: {requested}")

    await init_db_pool()
    await ensure_schema_current()
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            synced = await sync_focus_products(conn, requested)
            await rebuild_reporting_all(conn)
    print(f"Focus products sincronizate: {synced} coduri din {requested.name}")
    await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
