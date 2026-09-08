"""Read calendar, official targets and published reporting in one DB snapshot."""
from typing import Any

import asyncpg

from repositories.grile_calendar import GrileCalendarRepository
from retail_filters import distribution_location_clause


async def read_earnings_sources(pool: asyncpg.Pool, month: str) -> dict[str, Any]:
    async with pool.acquire() as conn:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            calendar = await GrileCalendarRepository.read_on_connection(conn, month)
            source = await conn.fetchrow(
                """SELECT cutoff_date FROM reporting_sales_cutoff_v1
                   WHERE import_month=$1""", month,
            )
            sales = await conn.fetch(
                f"""SELECT r.site_code, r.sale_date, SUM(r.total_sales) AS sales
                    FROM reporting_agent_day r JOIN stores s USING (site_code)
                    WHERE r.import_month=$1 AND r.site_code <> 'Cartele'
                      AND {distribution_location_clause('s')}
                    GROUP BY r.site_code, r.sale_date ORDER BY r.site_code, r.sale_date""", month,
            )
            targets = await conn.fetch(
                f"""SELECT t.site_code, t.target_value FROM store_targets t
                    JOIN stores s USING (site_code)
                    WHERE t.import_month=$1 AND t.site_code <> 'Cartele'
                      AND {distribution_location_clause('s')}
                    ORDER BY t.site_code""", month,
            )
    return {"calendar": calendar, "source": dict(source) if source else None,
            "sales": [dict(row) for row in sales], "targets": [dict(row) for row in targets]}
