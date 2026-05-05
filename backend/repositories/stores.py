from __future__ import annotations

import asyncpg

class StoresRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_active_stores(self) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT site_code, locatie, firma, regional, asm
                FROM stores
                WHERE is_active = true
                ORDER BY locatie
                """,
            )
