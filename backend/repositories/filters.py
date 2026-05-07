from __future__ import annotations

import asyncpg

class FiltersRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_raw_options(self, month: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT DISTINCT agg.firma, agg.regional, agg.asm, agg.site_code, agg.locatie, agg.agent
                FROM reporting_agent_month agg
                WHERE agg.import_month = $1
                  AND agg.locatie NOT ILIKE 'TR %'
                ORDER BY agg.firma, agg.regional, agg.asm, agg.locatie, agg.agent
                """,
                month,
            )

    async def get_available_months(self) -> list[str]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT snap.import_month
                FROM import_snapshots snap
                WHERE snap.status = 'completed'
                ORDER BY snap.import_month DESC
                """,
            )
        return [row["import_month"] for row in rows]
