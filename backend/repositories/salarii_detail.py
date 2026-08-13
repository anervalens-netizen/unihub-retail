"""Salary history, store summary, trend, and detail queries."""
from __future__ import annotations

import asyncpg

from domain.filter_scope import FilterInput
from repositories.salarii_scope import MIN_SALARY_FOR_AVERAGE, _salary_scope


class SalariiDetailQueries:
    pool: asyncpg.Pool

    async def fetch_agent_history_by_person_id(
        self,
        person_id: str,
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT
                    year,
                    month,
                    company_name,
                    SUM(total_salary) AS total_salary,
                    site_code,
                    locatie
                FROM salary_records
                WHERE person_id = $1
                GROUP BY year, month, company_name, site_code, locatie
                ORDER BY year DESC, month DESC, company_name, locatie
                """,
                person_id,
            )

    async def fetch_agent_salary_link(
        self,
        *,
        agent_code: str,
        site_code: str,
    ) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT agent_code, site_code, salary_full_name,
                       CASE WHEN match_status = 'confirmed' THEN person_id ELSE NULL END AS person_id,
                       match_status, match_source, confidence, effective_from_month, note
                FROM agent_salary_links
                WHERE agent_code = $1 AND site_code = $2
                """,
                agent_code,
                site_code,
            )

    async def fetch_agent_history_by_salary_link(
        self,
        *,
        person_id: str,
    ) -> list[asyncpg.Record]:
        return await self.fetch_agent_history_by_person_id(person_id)

    async def fetch_latest_month(
        self,
        *,
        company_name: str | None,
        site_code: FilterInput,
        regional: str | None,
        asm: str | None,
    ) -> asyncpg.Record | None:
        join_block, where_block, params = _salary_scope(
            salary_alias="sr",
            company_name=company_name,
            site_code=site_code,
            regional=regional,
            asm=asm,
        )
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                f"SELECT sr.year, sr.month FROM salary_records sr {join_block} {where_block} ORDER BY sr.year DESC, sr.month DESC LIMIT 1",
                *params,
            )

    async def fetch_summary_by_site(
        self,
        *,
        company_name: str | None,
        site_code: FilterInput,
        regional: str | None,
        asm: str | None,
        year: int,
        month: int,
    ) -> list[asyncpg.Record]:
        join_block, where_block, params = _salary_scope(
            salary_alias="s",
            company_name=company_name,
            site_code=site_code,
            regional=regional,
            asm=asm,
            initial_params=[year, month],
            initial_conditions=["s.year = $1", "s.month = $2"],
        )
        import_month = f"{year}-{month:02d}"
        async with self.pool.acquire() as conn:
            params2 = params + [import_month]
            return await conn.fetch(
                f"""
                WITH salary_rows AS (
                    SELECT
                        s.id AS salary_row_id,
                        s.site_code,
                        s.locatie,
                        s.company_name,
                        s.full_name,
                        s.person_id,
                        s.total_salary
                    FROM salary_records s
                    {join_block}
                    {where_block}
                ),
                salary_agents AS (
                    SELECT
                        MIN(site_code) AS site_code,
                        locatie,
                        company_name,
                        person_id AS agent_key,
                        SUM(total_salary) AS month_salary
                    FROM salary_rows
                    GROUP BY
                        locatie,
                        company_name,
                        person_id
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
                WITH salary_rows AS (
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
                salary_agents AS (
                    SELECT
                        year,
                        month,
                        person_id AS agent_key,
                        SUM(total_salary) AS month_salary
                    FROM salary_rows
                    GROUP BY
                        year,
                        month,
                        person_id
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

    async def fetch_stores(self, *, company_name: str | None) -> list[asyncpg.Record]:
        _join_block, where_block, params = _salary_scope(
            salary_alias="",
            company_name=company_name,
            initial_conditions=["site_code IS NOT NULL"],
            lower_company=False,
        )
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT DISTINCT site_code, locatie
                FROM salary_records
                {where_block}
                ORDER BY locatie ASC NULLS LAST, site_code ASC
                """,
                *params,
            )

    async def fetch_records(
        self,
        *,
        company_name: str | None,
        year: int | None,
        month: int | None,
        site_code: FilterInput,
        limit: int,
        offset: int,
    ) -> list[asyncpg.Record]:
        _join_block, where_block, params = _salary_scope(
            salary_alias="sr",
            company_name=company_name,
            site_code=site_code,
            year=year,
            month=month,
            lower_company=False,
        )
        async with self.pool.acquire() as conn:
            params2 = params + [limit, offset]
            return await conn.fetch(
                f"""
                SELECT id, year, month, full_name,
                       person_id,
                       total_salary, company_name, site_code, locatie
                FROM salary_records sr
                {where_block}
                ORDER BY year DESC, month DESC, full_name
                LIMIT ${len(params2) - 1} OFFSET ${len(params2)}
                """,
                *params2,
            )
