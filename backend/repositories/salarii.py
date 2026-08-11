from __future__ import annotations

from typing import Any
import asyncpg

from domain.filter_scope import FilterInput, normalize_filter_values

MIN_SALARY_FOR_AVERAGE = 2000


def _salary_scope(
    *,
    salary_alias: str,
    company_name: str | None = None,
    site_code: FilterInput = None,
    regional: str | None = None,
    asm: str | None = None,
    year: int | None = None,
    month: int | None = None,
    q: str | None = None,
    initial_params: list[Any] | None = None,
    initial_conditions: list[str] | None = None,
    lower_company: bool = True,
    where_prefix: bool = True,
) -> tuple[str, str, list[Any]]:
    params = list(initial_params or [])
    conditions = list(initial_conditions or [])
    # Organizational scope is a semi-join: it filters salary components but
    # never changes their cardinality. A report component is identified by its
    # persisted salary row/provenance, not its business-valued columns.
    join_block = ""

    def col(name: str) -> str:
        return f"{salary_alias}.{name}" if salary_alias else name

    def add(condition: str, value: Any) -> None:
        params.append(value)
        conditions.append(condition.format(position=len(params)))

    if q:
        add(f"{col('full_name')} ILIKE ${{position}}", f"%{q}%")
    site_codes = normalize_filter_values(site_code)
    if company_name and not site_codes:
        if lower_company:
            add(f"LOWER({col('company_name')}) = ${{position}}", company_name.lower())
        else:
            add(f"{col('company_name')} = ${{position}}", company_name)
    if site_codes:
        add(f"{col('site_code')} = ANY(${{position}}::TEXT[])", site_codes)
    store_conditions: list[str] = []
    if regional and not site_codes:
        params.append(regional)
        store_conditions.append(f"st.regional = ${len(params)}")
    if asm and not site_codes:
        params.append(asm)
        store_conditions.append(f"st.asm = ${len(params)}")
    if store_conditions:
        conditions.append(
            "EXISTS (SELECT 1 FROM stores st "
            f"WHERE st.site_code = {col('site_code')} AND "
            + " AND ".join(store_conditions)
            + ")"
        )
    if year is not None:
        add(f"{col('year')} = ${{position}}", year)
    if month is not None:
        add(f"{col('month')} = ${{position}}", month)

    if not conditions:
        return join_block, "", params
    operator = "WHERE " if where_prefix else ""
    return join_block, operator + " AND ".join(conditions), params


class SalariiRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

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
        agent_months_cte = f"""
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
