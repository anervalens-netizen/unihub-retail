"""Create the Retail schema in an explicitly isolated test database."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import asyncpg

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.connection import get_database_url, validate_test_database_url
from db.migration_runner import MAINTENANCE_WINDOW_AUTHORIZATION_ENV, run_migrations

# The isolated cluster replays the whole immutable manifest, which currently
# carries exactly one maintenance-window migration. Authorization is bound to
# that single reviewed filename and to nothing else: when a future
# maintenance-window migration lands, bootstrap keeps failing closed until it is
# reviewed and named here explicitly.
TEST_MAINTENANCE_MIGRATION = "074_v3_reporting_return_receipt_count.sql"


@contextmanager
def authorized_test_maintenance_migration() -> Iterator[None]:
    """Authorize exactly `TEST_MAINTENANCE_MIGRATION`, then restore the env.

    Deliberately parameterless so this helper cannot be reused to authorize an
    arbitrary migration. Production keeps its own out-of-band authorization:
    nothing here changes `run_migrations`, which still refuses every
    maintenance-window migration that is not explicitly named by the caller.
    """

    previous = os.environ.get(MAINTENANCE_WINDOW_AUTHORIZATION_ENV)
    os.environ[MAINTENANCE_WINDOW_AUTHORIZATION_ENV] = TEST_MAINTENANCE_MIGRATION
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(MAINTENANCE_WINDOW_AUTHORIZATION_ENV, None)
        else:
            os.environ[MAINTENANCE_WINDOW_AUTHORIZATION_ENV] = previous


async def run_isolated_migrations(database_url: str | None = None) -> list[str]:
    """Apply pending migrations under the bounded isolated-test authorization.

    Isolated callers (this bootstrap and the PostgreSQL authority tests) need the
    reviewed maintenance-window migration authorized; production callers keep
    calling `run_migrations` directly and stay fail-closed.
    """

    with authorized_test_maintenance_migration():
        return await run_migrations(database_url)


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

    # Migration 066 intentionally requires this process authority to be
    # provisioned out-of-band in production. Isolated clusters create the
    # NOLOGIN role explicitly before replaying the immutable migrations.
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_roles
                    WHERE rolname = 'unihub_salary_export'
                ) THEN
                    CREATE ROLE unihub_salary_export
                        NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                        NOINHERIT NOBYPASSRLS NOREPLICATION;
                END IF;
            END
            $$
            """
        )
    finally:
        await connection.close()

    migrations = await run_isolated_migrations(database_url)

    print(
        "Isolated test database initialized"
        + (f"; migrations: {', '.join(migrations)}" if migrations else "")
    )


if __name__ == "__main__":
    asyncio.run(main())
