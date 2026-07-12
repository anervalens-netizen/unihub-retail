"""Create the Retail schema in an explicitly isolated test database."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import asyncpg

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.connection import get_database_url, validate_test_database_url
from db.migration_runner import run_migrations


async def wait_for_database(database_url: str) -> None:
    last_error: Exception | None = None
    for _ in range(60):
        try:
            connection = await asyncpg.connect(database_url, timeout=2)
            try:
                await connection.fetchval("SELECT 1")
            finally:
                await connection.close()
            return
        except (OSError, asyncpg.PostgresError) as exc:
            last_error = exc
            await asyncio.sleep(1)
    raise RuntimeError("Isolated PostgreSQL did not become ready") from last_error


async def main() -> None:
    database_url = get_database_url()
    validate_test_database_url(database_url)
    await wait_for_database(database_url)

    migrations = await run_migrations(database_url)

    print(
        "Isolated test database initialized"
        + (f"; migrations: {', '.join(migrations)}" if migrations else "")
    )


if __name__ == "__main__":
    asyncio.run(main())
