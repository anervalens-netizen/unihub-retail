from __future__ import annotations

from fastapi import APIRouter, Query

from db.connection import get_pool

router = APIRouter(
    prefix="/salarii",
    tags=["salarii"],
)


@router.get("/overview")
async def salarii_overview(
    company_name: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions, params = [], []
        needs_store_join = regional is not None or asm is not None
        join_sql = "LEFT JOIN stores st ON st.site_code = sr.site_code" if needs_store_join else ""

        if company_name:
            params.append(company_name.lower())
            conditions.append(f"LOWER(sr.company_name) = ${len(params)}")
        if regional:
            params.append(regional)
            conditions.append(f"st.regional = ${len(params)}")
        if asm:
            params.append(asm)
            conditions.append(f"st.asm = ${len(params)}")

        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""
        cnp_where = "WHERE " + " AND ".join(conditions + ["sr.cnp IS NOT NULL"]) if conditions else "WHERE sr.cnp IS NOT NULL"

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
        if not months_row or months_row["min_year"] is None:
            months_span = None
        else:
            months_span = [
                int(months_row["min_year"]),
                int(months_row["min_month"]),
                int(months_row["max_year"]),
                int(months_row["max_month"]),
            ]
        return {
            "total": float(total),
            "by_company": [dict(r) for r in by_company],
            "record_count": record_count,
            "agent_count": agent_count,
            "months_span": months_span,
        }


@router.get("/evolution")
async def salarii_evolution(
    company_name: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions, params = [], []
        needs_store_join = regional is not None or asm is not None
        join_sql = "LEFT JOIN stores st ON st.site_code = sr.site_code" if needs_store_join else ""

        if company_name:
            params.append(company_name.lower())
            conditions.append(f"LOWER(sr.company_name) = ${len(params)}")
        if regional:
            params.append(regional)
            conditions.append(f"st.regional = ${len(params)}")
        if asm:
            params.append(asm)
            conditions.append(f"st.asm = ${len(params)}")

        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

        if company_name:
            rows = await conn.fetch(
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
            return [
                {"month": r["month"], "total": float(r["total"]), "mobicell": 0.0, "mobiup": 0.0}
                for r in rows
            ]
        rows = await conn.fetch(
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
        return [dict(r) for r in rows]


@router.get("/agents/summary")
async def agents_summary(
    q: str | None = Query(None),
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions, params = [], []
        needs_store_join = regional is not None or asm is not None
        join_sql = "LEFT JOIN stores st ON st.site_code = sr.site_code" if needs_store_join else ""

        if q:
            params.append(f"%{q}%")
            conditions.append(f"sr.full_name ILIKE ${len(params)}")
        if company_name:
            params.append(company_name.lower())
            conditions.append(f"LOWER(sr.company_name) = ${len(params)}")
        if site_code:
            params.append(site_code)
            conditions.append(f"sr.site_code = ${len(params)}")
        if regional:
            params.append(regional)
            conditions.append(f"st.regional = ${len(params)}")
        if asm:
            params.append(asm)
            conditions.append(f"st.asm = ${len(params)}")
        if year is not None:
            params.append(year)
            conditions.append(f"sr.year = ${len(params)}")
        if month is not None:
            params.append(month)
            conditions.append(f"sr.month = ${len(params)}")

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        total = await conn.fetchval(
            f"SELECT COUNT(DISTINCT sr.full_name) FROM salary_records sr {join_sql} {where}",
            *params,
        )

        params.extend([limit, offset])
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
            {where}
            GROUP BY sr.full_name, sr.cnp, sr.company_name, sr.locatie
            ORDER BY total_salary DESC
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )
        return {
            "items": [dict(r) for r in rows],
            "total": total,
        }


@router.get("/agents/history/{cnp}")
async def agent_history(cnp: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT year, month, company_name, total_salary, site_code, locatie
            FROM salary_records
            WHERE cnp = $1
            ORDER BY year DESC, month DESC
            """,
            cnp,
        )
        if not rows:
            return {"records": [], "total": 0.0, "avg": 0.0, "month_count": 0}

        total = sum(float(r["total_salary"]) for r in rows)
        month_count = len(rows)
        avg = total / month_count
        return {
            "records": [dict(r) for r in rows],
            "total": total,
            "avg": avg,
            "month_count": month_count,
        }


@router.get("/summary")
async def salarii_summary(
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Determine the month to query - default to latest in salary_records (scoped to all active filters)
        if year is None or month is None:
            latest_conds = []
            latest_params: list = []
            latest_needs_join = regional is not None or asm is not None
            latest_join = "LEFT JOIN stores st ON st.site_code = sr.site_code" if latest_needs_join else ""
            if company_name:
                latest_params.append(company_name.lower())
                latest_conds.append(f"LOWER(sr.company_name) = ${len(latest_params)}")
            if regional:
                latest_params.append(regional)
                latest_conds.append(f"st.regional = ${len(latest_params)}")
            if asm:
                latest_params.append(asm)
                latest_conds.append(f"st.asm = ${len(latest_params)}")
            latest_where = "WHERE " + " AND ".join(latest_conds) if latest_conds else ""
            latest = await conn.fetchrow(
                f"SELECT sr.year, sr.month FROM salary_records sr {latest_join} {latest_where} ORDER BY sr.year DESC, sr.month DESC LIMIT 1",
                *latest_params,
            )
            if not latest:
                return {"month": None, "items": []}
            query_year = latest["year"]
            query_month = latest["month"]
        else:
            query_year = year
            query_month = month

        import_month = f"{query_year}-{query_month:02d}"

        needs_store_join = regional is not None or asm is not None
        join_stores = "LEFT JOIN stores st ON st.site_code = s.site_code" if needs_store_join else ""

        # Build conditions - always filter by year/month
        conditions = ["s.year = $1", "s.month = $2"]
        params: list = [query_year, query_month]
        if company_name:
            params.append(company_name.lower())
            conditions.append(f"LOWER(s.company_name) = ${len(params)}")
        if site_code:
            params.append(site_code)
            conditions.append(f"s.site_code = ${len(params)}")
        if regional:
            params.append(regional)
            conditions.append(f"st.regional = ${len(params)}")
        if asm:
            params.append(asm)
            conditions.append(f"st.asm = ${len(params)}")

        where_clause = " AND ".join(conditions)

        rows = await conn.fetch(
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
                ON r.import_month = ${len(params) + 1}
                AND r.site_code = s.site_code
                AND LOWER(r.firma) = LOWER(s.company_name)
            WHERE {where_clause}
            GROUP BY s.site_code, s.locatie, s.company_name
            ORDER BY s.locatie ASC NULLS LAST, s.site_code ASC
            """,
            *params,
            import_month,
        )
        return {
            "month": import_month,
            "items": [
                {
                    "site_code": r["site_code"],
                    "locatie": r["locatie"],
                    "company_name": r["company_name"],
                    "total_salary": float(r["total_salary"]),
                    "agent_count": r["agent_count"],
                    "total_sales": float(r["total_sales"]),
                    "ratio": float(r["total_salary"]) / float(r["total_sales"]) * 100
                    if r["total_sales"]
                    else 0,
                }
                for r in rows
            ],
        }


@router.get("/trend")
async def salarii_trend(
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    regional: str | None = Query(None),
    asm: str | None = Query(None),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions, params = [], []
        needs_store_join = regional is not None or asm is not None

        if company_name:
            params.append(company_name.lower())
            conditions.append(f"LOWER(sr.company_name) = ${len(params)}")
        if site_code:
            params.append(site_code)
            conditions.append(f"sr.site_code = ${len(params)}")
        if regional:
            params.append(regional)
            conditions.append(f"st.regional = ${len(params)}")
        if asm:
            params.append(asm)
            conditions.append(f"st.asm = ${len(params)}")

        if company_name:
            select_company = "sr.company_name,"
            sql_company_group = ", sr.company_name"
        else:
            select_company = ""
            sql_company_group = ""

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        join_stores = "LEFT JOIN stores st ON st.site_code = sr.site_code" if needs_store_join else ""

        rows = await conn.fetch(
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
            {join_stores}
            LEFT JOIN (
                SELECT import_month, site_code, firma, SUM(total_sales) as total_sales
                FROM reporting_agent_month
                GROUP BY import_month, site_code, firma
            ) r
                ON r.import_month = TO_CHAR(sr.year, 'FM9999') || '-' || TO_CHAR(sr.month, 'FM00')
                AND r.site_code = sr.site_code
                AND LOWER(r.firma) = LOWER(sr.company_name)
            {where_clause}
            GROUP BY sr.year, sr.month{sql_company_group}
            ORDER BY sr.year DESC, sr.month DESC{', sr.company_name' if company_name else ''}
            """,
            *params,
        )

        months_map: dict = {}
        for r in rows:
            import_month = f"{r['year']}-{r['month']:02d}"
            if import_month not in months_map:
                months_map[import_month] = {
                    "month": import_month,
                    "total_salary": 0,
                    "total_sales": 0,
                    "agent_count": 0,
                    "by_company": {},
                }
            months_map[import_month]["total_salary"] += float(r["total_salary"])
            months_map[import_month]["total_sales"] += float(r["total_sales"])
            if company_name:
                company = r["company_name"]
                if company not in months_map[import_month]["by_company"]:
                    months_map[import_month]["by_company"][company] = {
                        "total_salary": 0,
                        "total_sales": 0,
                    }
                months_map[import_month]["by_company"][company]["total_salary"] += float(r["total_salary"])
                months_map[import_month]["by_company"][company]["total_sales"] += float(r["total_sales"])

        return sorted(months_map.values(), key=lambda x: x["month"], reverse=True)


@router.get("/stores")
async def salarii_stores(
    company_name: str | None = Query(None),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions, params = [], []
        if company_name:
            params.append(company_name)
            conditions.append(f"company_name = ${len(params)}")
        if conditions:
            where = "WHERE site_code IS NOT NULL AND " + " AND ".join(conditions)
        else:
            where = "WHERE site_code IS NOT NULL"
        rows = await conn.fetch(
            f"""
            SELECT DISTINCT site_code, locatie
            FROM salary_records
            {where}
            ORDER BY locatie ASC NULLS LAST, site_code ASC
            """,
            *params,
        )
        return [{"site_code": r["site_code"], "locatie": r["locatie"]} for r in rows]


@router.get("/records")
async def list_records(
    company_name: str | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None),
    site_code: str | None = Query(None),
    limit: int = Query(100, le=2000),
    offset: int = Query(0),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions, params = [], []
        if company_name:
            params.append(company_name)
            conditions.append(f"company_name = ${len(params)}")
        if year is not None:
            params.append(year)
            conditions.append(f"year = ${len(params)}")
        if month is not None:
            params.append(month)
            conditions.append(f"month = ${len(params)}")
        if site_code:
            params.append(site_code)
            conditions.append(f"site_code = ${len(params)}")

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.extend([limit, offset])
        rows = await conn.fetch(
            f"""
            SELECT id, year, month, full_name, cnp, total_salary,
                   company_name, site_code, locatie
            FROM salary_records
            {where}
            ORDER BY year DESC, month DESC, full_name
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )
        return [dict(r) for r in rows]
