from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bootstrap import get_default_core_credentials, reset_default_core_users
from db.connection import close_db_pool, ensure_schema_current, get_pool, init_db_pool


async def main() -> None:
    await init_db_pool()
    await ensure_schema_current()
    pool = await get_pool()

    async with pool.acquire() as conn:
        reset_users = await reset_default_core_users(conn)

    credentials = get_default_core_credentials()
    print("Default users reset successfully:")
    for row in reset_users:
        username, password, _ = credentials[row["role"]]
        print(f"- {row['role']}: {username} / {password}")

    await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
