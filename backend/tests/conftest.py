from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["UNIHUB_RUNNING_TESTS"] = "1"


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
