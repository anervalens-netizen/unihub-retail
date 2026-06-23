"""Create the Retail schema in an explicitly isolated test database."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.connection import (
    apply_pending_migrations,
    close_db_pool,
    ensure_schema_current,
    get_database_url,
    validate_test_database_url,
)


async def main() -> None:
    database_url = get_database_url()
    validate_test_database_url(database_url)

    try:
        await ensure_schema_current(force=True)
        migrations = await apply_pending_migrations()
    finally:
        await close_db_pool()

    print(
        "Isolated test database initialized"
        + (f"; migrations: {', '.join(migrations)}" if migrations else "")
    )


if __name__ == "__main__":
    asyncio.run(main())
