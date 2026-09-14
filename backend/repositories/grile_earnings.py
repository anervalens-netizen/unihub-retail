"""Read calendar, official targets and published reporting in one DB snapshot."""
from typing import Any

import asyncpg

from repositories.grile_calendar import GrileCalendarRepository
from retail_filters import distribution_location_clause


async def read_earnings_sources(pool: asyncpg.Pool, month: str) -> dict[str, Any]:
    async with pool.acquire() as conn:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            calendar = await GrileCalendarRepository.read_on_connection(conn, month)
            compensation = await conn.fetch('SELECT month,agent_code,salary_base,vouchers,sim_quantity,epay_under_50,epay_over_50,incentive,adjustment,revision FROM grile_calendar_compensation WHERE month=$1 ORDER BY agent_code', month)
            target_settings = await conn.fetch('SELECT month,agent_code,mode,manual_target,revision FROM grile_agent_target_settings WHERE month=$1', month)
            agent_target_rows = await conn.fetch('SELECT * FROM reporting_grile_agent_targets_v2 WHERE import_month=$1', month)
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
            # Cartela category also contains handsets/bags. Owner: all actual SIMs,
            # including SIM 0 and starter credit, excluding recharge/top-ups.
            sim = await conn.fetch(
                f"""SELECT t.site_code,t.sale_date,SUM(t.quantity)::int AS quantity
                    FROM sales_transactions t JOIN stores s USING(site_code)
                    WHERE t.import_month=$1 AND t.is_cartela AND t.site_code <> 'Cartele'
                      AND {distribution_location_clause('s')}
                      AND (t.item_name ~* '^(CARTELA|SIM)[[:space:]]' OR t.item_code ~* '^SIM[0-9]')
                      AND concat_ws(' ',t.item_name,t.item_code) !~* '(RECHARGE|REINCARC|REÎNCĂRC|TOP[ -]?UP)'
                    GROUP BY t.site_code,t.sale_date""", month,
            )
            from repositories.grile_incentives import read_incentives
            incentives, incentives_complete = await read_incentives(conn, month, calendar, source['cutoff_date'] if source else None)
            targets = await conn.fetch(
                f"""SELECT t.site_code, t.target_value FROM store_targets t
                    JOIN stores s USING (site_code)
                    WHERE t.import_month=$1 AND t.site_code <> 'Cartele'
                      AND {distribution_location_clause('s')}
                    ORDER BY t.site_code""", month,
            )
    return {"target_settings": [dict(row) for row in target_settings], "agent_target_rows": [dict(row) for row in agent_target_rows], "sim": [dict(row) for row in sim], "incentives": incentives, "incentives_complete": incentives_complete, "compensation": [dict(row) for row in compensation], "calendar": calendar, "source": dict(source) if source else None,
            "sales": [dict(row) for row in sales], "targets": [dict(row) for row in targets]}
