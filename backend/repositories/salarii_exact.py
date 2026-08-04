from __future__ import annotations

import asyncpg

from repositories.salarii import (
    MIN_SALARY_FOR_AVERAGE,
    SalariiRepository,
    _salary_scope,
)


class SalariiExactRepository(SalariiRepository):
    """Salary reporting that preserves every imported source component.

    Raw HR rows are uniquely identified by import provenance, not by their
    business values. Two source rows with the same person, month, location and
    amount are therefore both legitimate and must both contribute to totals.
    """

    async def fetch_overview(
        self,
        *,
        company_name: str | None,
        site_code: str | None,
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
                SELECT *, person_id AS agent_key
                FROM salary_base
            ),
            agent_months AS (
                SELECT year, month, agent_key,
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
                        SELECT COUNT(*) FROM agent_months
                        WHERE month_salary >= {MIN_SALARY_FOR_AVERAGE}
                    ) AS avg_agent_month_count,
                    COALESCE((
                        SELECT AVG(month_salary) FROM agent_months
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
            "by_company": [dict(row) for row in by_company],
            "record_count": stats["record_count"],
            "agent_count": stats["agent_count"],
            "agent_month_count": stats["agent_month_count"],
            "avg_agent_month_count": stats["avg_agent_month_count"],
            "avg_salary": float(stats["avg_salary"]),
            "months_row": stats,
        }

    async def fetch_evolution_main(
        self,
        *,
        company_name: str | None,
        site_code: str | None,
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
                    SELECT sr.id AS salary_row_id,
                           sr.year, sr.month, sr.full_name, sr.person_id,
                           sr.total_salary, sr.company_name, sr.site_code, sr.locatie
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
        site_code: str | None,
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
                    SELECT sr.id AS salary_row_id,
                           sr.year, sr.month, sr.full_name, sr.person_id,
                           sr.total_salary, sr.company_name, sr.site_code, sr.locatie
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
        site_code: str | None,
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
        agent_months_cte = f"""
            WITH salary_rows AS (
                SELECT sr.id AS salary_row_id,
                       sr.year, sr.month, sr.full_name, sr.person_id,
                       sr.company_name, sr.site_code, sr.locatie, sr.total_salary
                FROM salary_records sr
                {join_block}
                {where_block}
            ),
            salary_identified AS (
                SELECT *, person_id AS agent_key
                FROM salary_rows
            ),
            agent_months AS (
                SELECT agent_key, year, month,
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
                SELECT agent_key, MAX(year * 100 + month) AS latest_month
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
                        ' + ' ORDER BY COALESCE(NULLIF(BTRIM(si.locatie), ''), si.site_code)
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
                f"""{agent_months_cte}
                SELECT COUNT(*) FROM agent_totals
                """,
                *params,
            )
            params2 = params + [limit, offset]
            rows = await conn.fetch(
                f"""
                {agent_months_cte}
                SELECT ld.person_id, ld.full_name, ld.company_name, ld.locatie,
                       at.month_count, at.avg_month_count,
                       at.total_salary, at.avg_salary
                FROM agent_totals at
                JOIN latest_details ld USING (agent_key)
                ORDER BY at.total_salary DESC NULLS LAST,
                         ld.full_name ASC NULLS LAST,
                         ld.person_id ASC
                LIMIT ${len(params2) - 1} OFFSET ${len(params2)}
                """,
                *params2,
            )
        return {"items": [dict(row) for row in rows], "total": total}

    async def fetch_agent_history_by_person_id(
        self,
        person_id: str,
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT year, month, company_name,
                       SUM(total_salary) AS total_salary,
                       site_code, locatie
                FROM salary_records
                WHERE person_id = $1
                GROUP BY year, month, company_name, site_code, locatie
                ORDER BY year DESC, month DESC, company_name, locatie
                """,
                person_id,
            )

    async def fetch_summary_by_site(
        self,
        *,
        company_name: str | None,
        site_code: str | None,
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
                    SELECT s.id AS salary_row_id,
                           s.site_code, s.locatie, s.company_name,
                           s.full_name, s.person_id, s.total_salary
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
                    GROUP BY locatie, company_name, person_id
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
                    SELECT site_code, LOWER(firma) AS company_key,
                           SUM(total_sales) AS total_sales
                    FROM reporting_agent_month
                    WHERE import_month = ${len(params2)}
                    GROUP BY site_code, LOWER(firma)
                ),
                sales_display AS (
                    SELECT ss.locatie, ss.company_name,
                           COALESCE(SUM(sales_site.total_sales), 0) AS total_sales
                    FROM salary_sites ss
                    LEFT JOIN sales_site
                      ON sales_site.site_code = ss.site_code
                     AND sales_site.company_key = LOWER(ss.company_name)
                    GROUP BY ss.locatie, ss.company_name
                )
                SELECT sd.site_code, sd.locatie, sd.company_name,
                       sd.total_salary, sd.agent_count, sd.avg_agent_count,
                       sd.avg_salary, COALESCE(vd.total_sales, 0) AS total_sales
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
        site_code: str | None,
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
                    SELECT sr.id AS salary_row_id,
                           sr.year, sr.month, sr.full_name, sr.person_id,
                           sr.total_salary, sr.company_name, sr.site_code, sr.locatie
                    FROM salary_records sr
                    {join_block}
                    {where_block}
                ),
                salary_agents AS (
                    SELECT year, month, person_id AS agent_key,
                           SUM(total_salary) AS month_salary
                    FROM salary_rows
                    GROUP BY year, month, person_id
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
                    SELECT import_month, site_code, LOWER(firma) AS company_key,
                           SUM(total_sales) AS total_sales
                    FROM reporting_agent_month
                    GROUP BY import_month, site_code, LOWER(firma)
                ),
                sales_months AS (
                    SELECT ss.year, ss.month,
                           COALESCE(SUM(sales_site.total_sales), 0) AS total_sales
                    FROM salary_sites ss
                    LEFT JOIN sales_site
                      ON sales_site.import_month = TO_CHAR(ss.year, 'FM9999') || '-' || TO_CHAR(ss.month, 'FM00')
                     AND sales_site.site_code = ss.site_code
                     AND sales_site.company_key = LOWER(ss.company_name)
                    GROUP BY ss.year, ss.month
                )
                SELECT sm.year, sm.month, sm.total_salary,
                       sm.agent_count, sm.avg_agent_count, sm.avg_salary,
                       COALESCE(vm.total_sales, 0) AS total_sales
                FROM salary_months sm
                LEFT JOIN sales_months vm USING (year, month)
                ORDER BY sm.year DESC, sm.month DESC
                """,
                *params,
            )
