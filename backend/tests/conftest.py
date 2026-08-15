from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["UNIHUB_RUNNING_TESTS"] = "1"
os.environ["SENTRY_DSN"] = ""
os.environ["VITE_GLITCHTIP_DSN"] = ""


def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="function", autouse=True)
def reset_db_pool():
    """Reset the asyncpg pool before each test so async tests get a fresh pool
    bound to their own event loop. Safe for sync tests too."""
    import db.connection as _conn
    _conn.pool = None
    yield
    _conn.pool = None


@pytest.fixture(scope="function", autouse=True)
def reset_outbox_table():
    """Clear retail_outbox_events between DB tests so emit paths activated by
    one test cannot leak into count/claim assertions of another test."""
    yield
    if os.environ.get("UNIHUB_TEST_DATABASE") != "1":
        return
    url = os.environ.get("DATABASE_URL")
    if not url:
        return
    import asyncio

    import asyncpg

    async def _clean() -> None:
        connection = await asyncpg.connect(url)
        try:
            await connection.execute(
                "TRUNCATE TABLE retail_outbox_events, "
                "ai_forecast_cohort_snapshots, ai_forecast_runs, "
                "planning_forecast_heads RESTART IDENTITY CASCADE"
            )
        finally:
            await connection.close()

    asyncio.run(_clean())
