"""Current projection read methods for the Grile repository."""
from __future__ import annotations

import asyncpg

from repositories.grile_persistence import (
    _CURRENT_STATUS_COLUMNS,
    _RUN_COLUMNS,
    _STORE_STATUS_COLUMNS,
)


class GrileReadQueries:
    pool: asyncpg.Pool

    async def get_current_status(self, month: str, site_code: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(f"SELECT {_CURRENT_STATUS_COLUMNS} FROM grile_store_current_status WHERE run_month = $1 AND site_code = $2", month, site_code)

    async def get_current_statuses(self, month: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(f"SELECT {_CURRENT_STATUS_COLUMNS} FROM grile_store_current_status WHERE run_month = $1", month)

    async def get_latest_run(self, month: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(f"SELECT {_RUN_COLUMNS} FROM grile_runs WHERE run_month = $1 ORDER BY created_at DESC LIMIT 1", month)

    async def get_run(self, run_id: int) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(f"SELECT {_RUN_COLUMNS} FROM grile_runs WHERE id = $1", run_id)

    async def get_running_run(self, month: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(f"SELECT {_RUN_COLUMNS} FROM grile_runs WHERE run_month = $1 AND status IN ('queued', 'running') ORDER BY created_at DESC LIMIT 1", month)

    async def get_run_statuses(self, run_id: int) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(f"SELECT {_STORE_STATUS_COLUMNS} FROM grile_store_status WHERE run_id = $1", run_id)
