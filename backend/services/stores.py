from __future__ import annotations

from typing import Any

import asyncpg

from models import StoreOption
from repositories.stores import StoresRepository
from services.importer import upsert_store_targets


class StoresService:
    def __init__(self, repo: StoresRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

    async def get_active_stores(self) -> list[StoreOption]:
        rows = await self.repo.get_active_stores()
        return [StoreOption(**dict(row)) for row in rows]

    async def save_targets(self, targets: list[dict[str, Any]]) -> int:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                inserted = await upsert_store_targets(
                    conn,
                    targets,
                    source_file="manual-api",
                )
        return inserted
