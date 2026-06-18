from __future__ import annotations

from typing import Any
import asyncpg


MIN_SALARY_FOR_AVERAGE = 2000


class SalariiRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def fetch_overview(self, join_sql: str, where_sql: str, params: list[Any]) -> dict:
        salary_base_cte = f"""
            WITH salary_base AS (
                SELECT DISTINCT
                    sr.year,
                    sr.month,
                    sr.full_name,
                    sr.cnp,
                    sr.total_salary,
                    sr.company_name,
                    sr.site_code,
                    sr.locatie
                FROM salary_records sr
                {join_sql}
                {where_sql}
            ),
            salary_identified AS (
                SELECT
                    *,
                    COALESCE(
                        NULLIF(BTRIM(cnp), ''),
                        'name:' || LOWER(BTRIM(full_name))
                    ) AS agent_key
                FROM salary_base
            ),
            agent_months AS (
                SELECT
                    year,
                    month,
                    agent_key,
                    SUM(total_salary) AS month_salary
                FROM salary_identified
                GROUP BY year, month, agent_key
            )
        """
        async with self.pool.acquire() as conn:
            stats = await conn.fetchrow(
                f"""
                {salary_base_cte}
                SELECT
                    COALESCE((SELECT SUM(total_salary) FROM salary_base), 0) AS total,
                    (SELECT COUNT(*) FROM salary_base) AS record_count,
                    (SELECT COUNT(DISTINCT agent_key) FROM salary_identified) AS agent_count,
                    (SELECT COUNT(*) FROM agent_months) AS agent_month_count,
                    (
                        SELECT COUNT(*)
                        FROM agent_months
                        WHERE month_salary >= {MIN_SALARY_FOR_AVERAGE}
                    ) AS avg_agent_month_count,
                    COALESCE((
                        SELECT AVG(month_salary)
                        FROM agent_months
                        WHERE month_salary >= {MIN_SALARY_FOR_AVERAGE}
                    ), 0) AS avg_salary,
                    (SELECT MIN(year * 100 + month) / 100 FROM salary_base) AS min_year,
                    (SELECT MIN(year * 100 + month) % 100 FROM salary_base) AS min_month,
                    (SELECT MAX(year * 100 + month) / 100 FROM salary_base) AS max_year,
                    (SELECT MAX(year * 100 + month) % 100 FROM salary_base) AS max_month
                """,
                *params,
            )
            by_company = await conn.fetch(
                f"""
                {salary_base_cte}
                SELECT company_name AS name, COALESCE(SUM(total_salary), 0) AS total
                FROM salary_base
                GROUP BY company_name
                ORDER BY total DESC
                """,
                *params,
            )
        return {
            "total": float(stats["total"]),
            "by_company": [dict(r) for r in by_company],
            "record_count": stats["record_count"],
            "agent_count": stats["agent_count"],
            "agent_month_count": stats["agent_month_count"],
            "avg_agent_month_count": stats["avg_agent_month_count"],
            "avg_salary": float(stats["avg_salary"]),
            "months_row": stats,
        }

    async def fetch_evolution_main(self, join_sql: str, where_sql: str, params: list[Any]) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH salary_base AS (
                    SELECT DISTINCT
                        sr.year,
                        sr.month,
                        sr.full_name,
                        sr.cnp,
                        sr.total_salary,
                        sr.company_name,
                        sr.site_code,
                        sr.locatie
                    FROM salary_records sr
                    {join_sql}
                    {where_sql}
                )
                SELECT
                    year * 100 + month AS sort_key,
                    TO_CHAR(year, 'FM9999') || '-' || TO_CHAR(month, 'FM00') AS month,
                    COALESCE(SUM(total_salary) FILTER (WHERE company_name = 'Mobicell'), 0) AS mobicell,
                    COALESCE(SUM(total_salary) FILTER (WHERE company_name = 'Mobiup'), 0) AS mobiup,
                    COALESCE(SUM(total_salary), 0) AS total
                FROM salary_base
                GROUP BY year, month
                ORDER BY sort_key
                """,
                *params,
            )

    async def fetch_evolution_single_company(self, join_sql: str, where_sql: str, params: list[Any]) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH salary_base AS (
                    SELECT DISTINCT
                        sr.year,
                        sr.month,
                        sr.full_name,
                        sr.cnp,
                        sr.total_salary,
                        sr.company_name,
                        sr.site_code,
                        sr.locatie
                    FROM salary_records sr
                    {join_sql}
                    {where_sql}
                )
                SELECT
                    year * 100 + month AS sort_key,
                    TO_CHAR(year, 'FM9999') || '-' || TO_CHAR(month, 'FM00') AS month,
                    SUM(total_salary) AS total
                FROM salary_base
                GROUP BY year, month
                ORDER BY sort_key
                """,
                *params,
            )

    async def fetch_agents_summary(
        self,
        join_sql: str,
        where_sql: str,
        params: list[Any],
        limit: int,
        offset: int,
    ) -> dict:
        agent_months_cte = f"""
                WITH salary_dedup AS (
                    SELECT DISTINCT
                        sr.year,
                        sr.month,
                        sr.full_name,
                        sr.cnp,
                        sr.company_name,
                        sr.site_code,
                        sr.locatie,
                        sr.total_salary
                    FROM salary_records sr
                    {join_sql}
                    {where_sql}
                ),
                salary_identified AS (
                    SELECT
                        *,
                        COALESCE(
                            NULLIF(BTRIM(cnp), ''),
                            'name:' || LOWER(BTRIM(full_name))
                        ) AS agent_key
                    FROM salary_dedup
                ),
                agent_months AS (
                    SELECT
                        agent_key,
                        year,
                        month,
                        SUM(total_salary) AS month_salary
                    FROM salary_identified
                    GROUP BY agent_key, year, month
                ),
                agent_totals AS (
                    SELECT
                        agent_key,
                        COUNT(*) AS month_count,
                        COUNT(*) FILTER (
                            WHERE month_salary >= {MIN_SALARY_FOR_AVERAGE}
                        ) AS avg_month_count,
                        SUM(month_salary) AS total_salary,
                        COALESCE(AVG(month_salary) FILTER (
                            WHERE month_salary >= {MIN_SALARY_FOR_AVERAGE}
                        ), 0) AS avg_salary
                    FROM agent_months
                    GROUP BY agent_key
                ),
                latest_period AS (
                    SELECT
                        agent_key,
                        MAX(year * 100 + month) AS latest_month
                    FROM salary_identified
                    GROUP BY agent_key
                ),
                latest_details AS (
                    SELECT
                        si.agent_key,
                        (ARRAY_AGG(si.full_name ORDER BY si.total_salary DESC, si.full_name))[1] AS full_name,
                        MAX(NULLIF(BTRIM(si.cnp), '')) AS cnp,
                        STRING_AGG(DISTINCT si.company_name, ' + ' ORDER BY si.company_name) AS company_name,
                        STRING_AGG(
                            DISTINCT COALESCE(NULLIF(BTRIM(si.locatie), ''), si.site_code),
                            ' + '
                            ORDER BY COALESCE(NULLIF(BTRIM(si.locatie), ''), si.site_code)
                        ) FILTER (
                            WHERE COALESCE(NULLIF(BTRIM(si.locatie), ''), si.site_code) IS NOT NULL
                        ) AS locatie
                    FROM salary_identified si
                    JOIN latest_period lp
                      ON lp.agent_key = si.agent_key
                     AND lp.latest_month = si.year * 100 + si.month
                    GROUP BY si.agent_key
                )
                """
        async with self.pool.acquire() as conn:
            total = await conn.fetchval(
                f"""
                {agent_months_cte}
                SELECT COUNT(*) FROM agent_totals
                """,
                *params,
            )
            params2 = params + [limit, offset]
            rows = await conn.fetch(
                f"""
                {agent_months_cte}
                SELECT
                    ld.full_name,
                    ld.cnp,
                    ld.company_name,
                    ld.locatie,
                    at.month_count,
                    at.avg_month_count,
                    at.total_salary,
                    at.avg_salary
                FROM agent_totals at
                JOIN latest_details ld USING (agent_key)
                ORDER BY at.total_salary DESC NULLS LAST,
                         ld.full_name ASC NULLS LAST,
                         ld.cnp ASC NULLS LAST
                LIMIT ${len(params2) - 1} OFFSET ${len(params2)}
                """,
                *params2,
            )
        return {"items": [dict(r) for r in rows], "total": total}

    async def fetch_agent_history(self, cnp: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                WITH salary_dedup AS (
                    SELECT DISTINCT
                        year, month, company_name, site_code, locatie, total_salary
                    FROM salary_records
                    WHERE cnp = $1
                )
                SELECT
                    year,
                    month,
                    company_name,
                    SUM(total_salary) AS total_salary,
                    site_code,
                    locatie
                FROM salary_dedup
                GROUP BY year, month, company_name, site_code, locatie
                ORDER BY year DESC, month DESC, company_name, locatie
                """,
                cnp,
            )

    async def fetch_latest_month(self, join_sql: str, where_sql: str, params: list[Any]) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                f"SELECT sr.year, sr.month FROM salary_records sr {join_sql} {where_sql} ORDER BY sr.year DESC, sr.month DESC LIMIT 1",
                *params,
            )

    async def fetch_summary_by_site(self, join_stores: str, where_clause: str, params: list[Any], import_month: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            params2 = params + [import_month]
            return await conn.fetch(
                f"""
                WITH salary_rows AS (
                    SELECT DISTINCT
                        s.site_code,
                        s.locatie,
                        s.company_name,
                        s.full_name,
                        s.cnp,
                        s.total_salary
                    FROM salary_records s
                    {join_stores}
                    WHERE {where_clause}
                ),
                salary_agents AS (
                    SELECT
                        MIN(site_code) AS site_code,
                        locatie,
                        company_name,
                        COALESCE(
                            NULLIF(BTRIM(cnp), ''),
                            'name:' || LOWER(BTRIM(full_name))
                        ) AS agent_key,
                        SUM(total_salary) AS month_salary
                    FROM salary_rows
                    GROUP BY
                        locatie,
                        company_name,
                        COALESCE(
                            NULLIF(BTRIM(cnp), ''),
                            'name:' || LOWER(BTRIM(full_name))
                        )
                ),
                salary_display AS (
                    SELECT
                        MIN(site_code) AS site_code,
                        locatie,
                        company_name,
                        SUM(month_salary) AS total_salary,
                        COUNT(*) AS agent_count,
                        COUNT(*) FILTER (
                            WHERE month_salary >= {MIN_SALARY_FOR_AVERAGE}
                        ) AS avg_agent_count,
                        COALESCE(AVG(month_salary) FILTER (
                            WHERE month_salary >= {MIN_SALARY_FOR_AVERAGE}
                        ), 0) AS avg_salary
                    FROM salary_agents
                    GROUP BY locatie, company_name
                ),
                salary_sites AS (
                    SELECT DISTINCT site_code, locatie, company_name
                    FROM salary_rows
                    WHERE site_code IS NOT NULL
                ),
                sales_site AS (
                    SELECT
                        site_code,
                        LOWER(firma) AS company_key,
                        SUM(total_sales) AS total_sales
                    FROM reporting_agent_month
                    WHERE import_month = ${len(params2)}
                    GROUP BY site_code, LOWER(firma)
                ),
                sales_display AS (
                    SELECT
                        ss.locatie,
                        ss.company_name,
                        COALESCE(SUM(sales_site.total_sales), 0) AS total_sales
                    FROM salary_sites ss
                    LEFT JOIN sales_site
                        ON sales_site.site_code = ss.site_code
                        AND sales_site.company_key = LOWER(ss.company_name)
                    GROUP BY ss.locatie, ss.company_name
                )
                SELECT
                    sd.site_code,
                    sd.locatie,
                    sd.company_name,
                    sd.total_salary,
                    sd.agent_count,
                    sd.avg_agent_count,
                    sd.avg_salary,
                    COALESCE(vd.total_sales, 0) AS total_sales
                FROM salary_display sd
                LEFT JOIN sales_display vd
                    ON vd.locatie IS NOT DISTINCT FROM sd.locatie
                    AND vd.company_name = sd.company_name
                ORDER BY sd.locatie ASC NULLS LAST, sd.site_code ASC
                """,
                *params2,
            )

    async def fetch_trend(
        self,
        join_sql: str,
        where_sql: str,
        params: list[Any],
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH salary_rows AS (
                    SELECT DISTINCT
                        sr.year,
                        sr.month,
                        sr.full_name,
                        sr.cnp,
                        sr.total_salary,
                        sr.company_name,
                        sr.site_code,
                        sr.locatie
                    FROM salary_records sr
                    {join_sql}
                    {where_sql}
                ),
                salary_agents AS (
                    SELECT
                        year,
                        month,
                        COALESCE(
                            NULLIF(BTRIM(cnp), ''),
                            'name:' || LOWER(BTRIM(full_name))
                        ) AS agent_key,
                        SUM(total_salary) AS month_salary
                    FROM salary_rows
                    GROUP BY
                        year,
                        month,
                        COALESCE(
                            NULLIF(BTRIM(cnp), ''),
                            'name:' || LOWER(BTRIM(full_name))
                        )
                ),
                salary_months AS (
                    SELECT
                        year,
                        month,
                        SUM(month_salary) AS total_salary,
                        COUNT(*) AS agent_count,
                        COUNT(*) FILTER (
                            WHERE month_salary >= {MIN_SALARY_FOR_AVERAGE}
                        ) AS avg_agent_count,
                        COALESCE(AVG(month_salary) FILTER (
                            WHERE month_salary >= {MIN_SALARY_FOR_AVERAGE}
                        ), 0) AS avg_salary
                    FROM salary_agents
                    GROUP BY year, month
                ),
                salary_sites AS (
                    SELECT DISTINCT year, month, site_code, company_name
                    FROM salary_rows
                    WHERE site_code IS NOT NULL
                ),
                sales_site AS (
                    SELECT import_month, site_code, LOWER(firma) AS company_key, SUM(total_sales) AS total_sales
                    FROM reporting_agent_month
                    GROUP BY import_month, site_code, LOWER(firma)
                ),
                sales_months AS (
                    SELECT
                        ss.year,
                        ss.month,
                        COALESCE(SUM(sales_site.total_sales), 0) AS total_sales
                    FROM salary_sites ss
                    LEFT JOIN sales_site
                      ON sales_site.import_month = TO_CHAR(ss.year, 'FM9999') || '-' || TO_CHAR(ss.month, 'FM00')
                     AND sales_site.site_code = ss.site_code
                     AND sales_site.company_key = LOWER(ss.company_name)
                    GROUP BY ss.year, ss.month
                )
                SELECT
                    sm.year,
                    sm.month,
                    sm.total_salary,
                    sm.agent_count,
                    sm.avg_agent_count,
                    sm.avg_salary,
                    COALESCE(vm.total_sales, 0) AS total_sales
                FROM salary_months sm
                LEFT JOIN sales_months vm USING (year, month)
                ORDER BY sm.year DESC, sm.month DESC
                """,
                *params,
            )

    async def fetch_stores(self, where: str, params: list[Any]) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT DISTINCT site_code, locatie
                FROM salary_records
                {where}
                ORDER BY locatie ASC NULLS LAST, site_code ASC
                """,
                *params,
            )

    async def fetch_records(self, where: str, params: list[Any], limit: int, offset: int) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            params2 = params + [limit, offset]
            return await conn.fetch(
                f"""
                SELECT id, year, month, full_name, cnp, total_salary,
                       company_name, site_code, locatie
                FROM salary_records
                {where}
                ORDER BY year DESC, month DESC, full_name
                LIMIT ${len(params2) - 1} OFFSET ${len(params2)}
                """,
                *params2,
            )
