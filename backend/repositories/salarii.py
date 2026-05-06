from __future__ import annotations

from typing import Any
import asyncpg


class SalariiRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def fetch_overview(self, join_sql: str, where_sql: str, cnp_where: str, params: list[Any]) -> dict:
        async with self.pool.acquire() as conn:
            total = await conn.fetchval(
                f"SELECT COALESCE(SUM(sr.total_salary), 0) FROM salary_records sr {join_sql} {where_sql}",
                *params,
            )
            by_company = await conn.fetch(
                f"SELECT sr.company_name AS name, COALESCE(SUM(sr.total_salary), 0) AS total "
                f"FROM salary_records sr {join_sql} {where_sql} "
                f"GROUP BY sr.company_name ORDER BY total DESC",
                *params,
            )
            record_count = await conn.fetchval(
                f"SELECT COUNT(*) FROM salary_records sr {join_sql} {where_sql}",
                *params,
            )
            agent_count = await conn.fetchval(
                f"SELECT COUNT(DISTINCT sr.cnp) FROM salary_records sr {join_sql} {cnp_where}",
                *params,
            )
            months_row = await conn.fetchrow(
                f"""
                SELECT
                    MIN(sr.year * 100 + sr.month) / 100 AS min_year,
                    MIN(sr.year * 100 + sr.month) % 100 AS min_month,
                    MAX(sr.year * 100 + sr.month) / 100 AS max_year,
                    MAX(sr.year * 100 + sr.month) % 100 AS max_month
                FROM salary_records sr {join_sql} {where_sql}
                """,
                *params,
            )
        return {
            "total": float(total),
            "by_company": [dict(r) for r in by_company],
            "record_count": record_count,
            "agent_count": agent_count,
            "months_row": months_row,
        }

    async def fetch_evolution_main(self, join_sql: str, where_sql: str, params: list[Any]) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT
                    sr.year * 100 + sr.month AS sort_key,
                    TO_CHAR(sr.year, 'FM9999') || '-' || TO_CHAR(sr.month, 'FM00') AS month,
                    COALESCE(SUM(sr.total_salary) FILTER (WHERE sr.company_name = 'Mobicell'), 0) AS mobicell,
                    COALESCE(SUM(sr.total_salary) FILTER (WHERE sr.company_name = 'Mobiup'), 0) AS mobiup,
                    COALESCE(SUM(sr.total_salary), 0) AS total
                FROM salary_records sr
                {join_sql}
                {where_sql}
                GROUP BY sr.year, sr.month
                ORDER BY sort_key
                """,
                *params,
            )

    async def fetch_evolution_single_company(self, join_sql: str, where_sql: str, params: list[Any]) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT
                    sr.year * 100 + sr.month AS sort_key,
                    TO_CHAR(sr.year, 'FM9999') || '-' || TO_CHAR(sr.month, 'FM00') AS month,
                    SUM(sr.total_salary) AS total
                FROM salary_records sr
                {join_sql}
                {where_sql}
                GROUP BY sr.year, sr.month
                ORDER BY sort_key
                """,
                *params,
            )

    async def fetch_agents_summary(self, join_sql: str, where_sql: str, params: list[Any], limit: int, offset: int) -> dict:
        async with self.pool.acquire() as conn:
            total = await conn.fetchval(
                f"SELECT COUNT(DISTINCT sr.full_name) FROM salary_records sr {join_sql} {where_sql}",
                *params,
            )
            params2 = params + [limit, offset]
            rows = await conn.fetch(
                f"""
                SELECT
                    sr.full_name,
                    sr.cnp,
                    sr.company_name,
                    sr.locatie,
                    COUNT(*) AS month_count,
                    SUM(sr.total_salary) AS total_salary,
                    AVG(sr.total_salary) AS avg_salary
                FROM salary_records sr
                {join_sql}
                {where_sql}
                GROUP BY sr.full_name, sr.cnp, sr.company_name, sr.locatie
                ORDER BY total_salary DESC
                LIMIT ${len(params2) - 1} OFFSET ${len(params2)}
                """,
                *params2,
            )
        return {"items": [dict(r) for r in rows], "total": total}

    async def fetch_agent_history(self, cnp: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT year, month, company_name, total_salary, site_code, locatie
                FROM salary_records
                WHERE cnp = $1
                ORDER BY year DESC, month DESC
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
                SELECT
                    s.site_code,
                    s.locatie,
                    s.company_name,
                    SUM(s.total_salary) AS total_salary,
                    COUNT(DISTINCT s.full_name) AS agent_count,
                    COALESCE(SUM(r.total_sales), 0) AS total_sales
                FROM salary_records s
                {join_stores}
                LEFT JOIN reporting_agent_month r
                    ON r.import_month = ${len(params2)}
                    AND r.site_code = s.site_code
                    AND LOWER(r.firma) = LOWER(s.company_name)
                WHERE {where_clause}
                GROUP BY s.site_code, s.locatie, s.company_name
                ORDER BY s.locatie ASC NULLS LAST, s.site_code ASC
                """,
                *params2,
            )

    async def fetch_trend(self, join_sql: str, select_company: str, sql_company_group: str, where_sql: str, params: list[Any], company_name: str | None = None) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT
                    sr.year,
                    sr.month,
                    {select_company}
                    SUM(sr.total_salary) AS total_salary,
                    COUNT(DISTINCT (sr.year, sr.month, sr.site_code, sr.company_name)) AS store_count,
                    COALESCE(SUM(r.total_sales), 0) AS total_sales
                FROM (
                    SELECT year, month, site_code, company_name, SUM(total_salary) as total_salary
                    FROM salary_records
                    GROUP BY year, month, site_code, company_name
                ) sr
                {join_sql}
                LEFT JOIN (
                    SELECT import_month, site_code, firma, SUM(total_sales) as total_sales
                    FROM reporting_agent_month
                    GROUP BY import_month, site_code, firma
                ) r
                    ON r.import_month = TO_CHAR(sr.year, 'FM9999') || '-' || TO_CHAR(sr.month, 'FM00')
                    AND r.site_code = sr.site_code
                    AND LOWER(r.firma) = LOWER(sr.company_name)
                {where_sql}
                GROUP BY sr.year, sr.month{sql_company_group}
                ORDER BY sr.year DESC, sr.month DESC{', sr.company_name' if company_name else ''}
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
