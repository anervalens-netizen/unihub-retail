"""Salary overview, evolution, and agent-summary queries."""
from __future__ import annotations

import asyncpg

from domain.filter_scope import FilterInput
from repositories.salarii_scope import MIN_SALARY_FOR_AVERAGE, _salary_scope


def _agent_months_cte(join_block: str, where_block: str) -> str:
    return f"""
                WITH salary_rows AS (
                    SELECT
                        sr.id AS salary_row_id,
                        sr.year,
                        sr.month,
                        sr.full_name,
                        sr.person_id,
                        sr.company_name,
                        sr.site_code,
                        sr.locatie,
                        sr.total_salary
                    FROM salary_records sr
                    {join_block}
                    {where_block}
                ),
                salary_identified AS (
                    SELECT
                        sr.*,
                        sr.person_id AS agent_key
                    FROM salary_rows sr
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
                        si.agent_key AS person_id,
                        (ARRAY_AGG(si.full_name ORDER BY si.total_salary DESC, si.full_name))[1] AS full_name,
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

class SalariiSummaryQueries:
    pool: asyncpg.Pool

    async def fetch_overview(
        self,
        *,
        company_name: str | None,
        site_code: FilterInput,
        regional: str | None,
        asm: str | None,
    ) -> dict:
        join_block, where_block, params = _salary_scope(
            salary_alias="sr",
            company_name=company_name,
            site_code=site_code,
            regional=regional,
            asm=asm,
        )
        salary_base_cte = f"""
            WITH salary_base AS (
                SELECT
                    sr.id AS salary_row_id,
                    sr.year,
                    sr.month,
                    sr.full_name,
                    sr.person_id,
                    sr.total_salary,
                    sr.company_name,
                    sr.site_code,
                    sr.locatie
                FROM salary_records sr
                {join_block}
                {where_block}
            ),
            salary_identified AS (
                SELECT
                    *,
                    person_id AS agent_key
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
            "total": stats["total"],
            "by_company": [dict(r) for r in by_company],
            "record_count": stats["record_count"],
            "agent_count": stats["agent_count"],
            "agent_month_count": stats["agent_month_count"],
            "avg_agent_month_count": stats["avg_agent_month_count"],
            "avg_salary": stats["avg_salary"],
            "months_row": stats,
        }

    async def fetch_evolution_main(
        self,
        *,
        company_name: str | None,
        site_code: FilterInput,
        regional: str | None,
        asm: str | None,
    ) -> list[asyncpg.Record]:
        join_block, where_block, params = _salary_scope(
            salary_alias="sr",
            company_name=company_name,
            site_code=site_code,
            regional=regional,
            asm=asm,
        )
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH salary_base AS (
                    SELECT
                        sr.id AS salary_row_id,
                        sr.year,
                        sr.month,
                        sr.full_name,
                        sr.person_id,
                        sr.total_salary,
                        sr.company_name,
                        sr.site_code,
                        sr.locatie
                    FROM salary_records sr
                    {join_block}
                    {where_block}
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

    async def fetch_evolution_single_company(
        self,
        *,
        company_name: str,
        site_code: FilterInput,
        regional: str | None,
        asm: str | None,
    ) -> list[asyncpg.Record]:
        join_block, where_block, params = _salary_scope(
            salary_alias="sr",
            company_name=company_name,
            site_code=site_code,
            regional=regional,
            asm=asm,
        )
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                WITH salary_base AS (
                    SELECT
                        sr.id AS salary_row_id,
                        sr.year,
                        sr.month,
                        sr.full_name,
                        sr.person_id,
                        sr.total_salary,
                        sr.company_name,
                        sr.site_code,
                        sr.locatie
                    FROM salary_records sr
                    {join_block}
                    {where_block}
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
        *,
        q: str | None,
        company_name: str | None,
        site_code: FilterInput,
        regional: str | None,
        asm: str | None,
        year: int | None,
        month: int | None,
        limit: int,
        offset: int,
    ) -> dict:
        join_block, where_block, params = _salary_scope(
            salary_alias="sr",
            q=q,
            company_name=company_name,
            site_code=site_code,
            regional=regional,
            asm=asm,
            year=year,
            month=month,
        )
        agent_months_cte = _agent_months_cte(join_block, where_block)
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
                    ld.person_id,
                    ld.full_name,
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
                         ld.person_id ASC
                LIMIT ${len(params2) - 1} OFFSET ${len(params2)}
                """,
                *params2,
            )
        return {"items": [dict(r) for r in rows], "total": total}
