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

    async def change_activity(
        self,
        *,
        site_code: str,
        expected_is_active: bool,
        new_is_active: bool,
        reason: str,
        requested_by_sub: str,
    ) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                current = await conn.fetchrow(
                    "SELECT is_active FROM stores WHERE site_code = $1 FOR UPDATE",
                    site_code,
                )
                if current is None:
                    return None
                previous = bool(current["is_active"])
                if previous != expected_is_active:
                    raise RuntimeError("store activity changed concurrently")
                if previous == new_is_active:
                    raise ValueError("store activity is already in the requested state")
                await conn.execute(
                    """
                    UPDATE stores
                    SET is_active = $2, updated_at = now()
                    WHERE site_code = $1
                    """,
                    site_code,
                    new_is_active,
                )
                return await conn.fetchrow(
                    """
                    INSERT INTO store_activity_events (
                        site_code, previous_is_active, new_is_active,
                        reason, requested_by_sub
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id, site_code, previous_is_active, new_is_active
                    """,
                    site_code,
                    previous,
                    new_is_active,
                    reason.strip(),
                    requested_by_sub,
                )
