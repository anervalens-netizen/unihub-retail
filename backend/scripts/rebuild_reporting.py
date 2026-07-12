from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.connection import close_db_pool, get_pool, init_db_pool
from db.migration_runner import verify_migrations_current
from services.reporting_refresh import rebuild_reporting_all


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconstruieste agregatele persistente pentru reporting"
    )
    parser.add_argument(
        "--month",
        action="append",
        dest="months",
        help="Reconstruieste doar luna indicata; poate fi repetat",
    )
    args = parser.parse_args()

    await init_db_pool()
    await verify_migrations_current(await get_pool())
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            months = await rebuild_reporting_all(conn, months=args.months)

    if months:
        print("Agregate reporting reconstruite pentru:", ", ".join(months))
    else:
        print("Nu exista luni completed pentru rebuild.")
    await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
