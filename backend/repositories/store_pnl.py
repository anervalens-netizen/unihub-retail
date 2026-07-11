from __future__ import annotations

from datetime import date

import asyncpg


class StorePnlRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def available_months(self) -> list[asyncpg.Record]:
        async with self.pool.acquire() as connection:
            return await connection.fetch(
                """
                SELECT period, bool_or(data_kind = 'actual') AS has_actual,
                       bool_or(data_kind = 'estimated') AS has_estimated
                FROM store_pnl_monthly
                GROUP BY period ORDER BY period DESC
                """
            )

    async def rows(self, start: date, end: date, company: str | None) -> list[asyncpg.Record]:
        async with self.pool.acquire() as connection:
            return await connection.fetch(
                """
                SELECT p.company_name, p.period, p.source_site_code,
                       p.source_location_name, p.category_code, p.amount,
                       p.data_kind, l.site_code
                FROM store_pnl_monthly p
                LEFT JOIN store_pnl_site_links l USING (company_name, source_site_code)
                WHERE p.period BETWEEN $1 AND $2
                  AND ($3::text IS NULL OR p.company_name = $3)
                ORDER BY p.period, p.company_name, p.source_location_name, p.category_code
                """,
                start,
                end,
                company,
            )
