from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from db.connection import get_pool

router = APIRouter(prefix="/salarii", tags=["salarii"])


@router.get("/overview")
async def salarii_overview():
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COALESCE(SUM(total_salary), 0) FROM salary_records"
        )
        by_company = await conn.fetch(
            "SELECT company_name AS name, COALESCE(SUM(total_salary), 0) AS total "
            "FROM salary_records GROUP BY company_name ORDER BY total DESC"
        )
        record_count = await conn.fetchval("SELECT COUNT(*) FROM salary_records")
        agent_count = await conn.fetchval(
            "SELECT COUNT(DISTINCT cnp) FROM salary_records WHERE cnp IS NOT NULL"
        )
        months = await conn.fetch(
            """
            SELECT 
                (SELECT year FROM salary_records ORDER BY year ASC, month ASC LIMIT 1) as y,
                (SELECT month FROM salary_records ORDER BY year ASC, month ASC LIMIT 1) as m,
                (SELECT year FROM salary_records ORDER BY year DESC, month DESC LIMIT 1) as y2,
                (SELECT month FROM salary_records ORDER BY year DESC, month DESC LIMIT 1) as m2
            """
        )
        row = months[0]
        months_span = [int(row["y"]), int(row["m"]), int(row["y2"]), int(row["m2"])]
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
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if company_name:
            rows = await conn.fetch(
                """
                SELECT
                    year * 100 + month AS sort_key,
                    TO_CHAR(year, 'FM9999') || '-' || TO_CHAR(month, 'FM00') AS month,
                    SUM(total_salary) AS total
                FROM salary_records
                WHERE company_name = $1
                GROUP BY year, month
                ORDER BY sort_key
                """,
                company_name,
            )
            return [
                {
                    "month": r["month"],
                    "total": float(r["total"]),
                    "mobicell": 0.0,
                    "mobiup": 0.0,
                }
                for r in rows
            ]
        # Full evolution: total + per company per month
        rows = await conn.fetch(
            """
            SELECT
                year * 100 + month AS sort_key,
                TO_CHAR(year, 'FM9999') || '-' || TO_CHAR(month, 'FM00') AS month,
                COALESCE(SUM(total_salary) FILTER (WHERE company_name = 'Mobicell'), 0) AS mobicell,
                COALESCE(SUM(total_salary) FILTER (WHERE company_name = 'Mobiup'), 0) AS mobiup,
                COALESCE(SUM(total_salary), 0) AS total
            FROM salary_records
            GROUP BY year, month
            ORDER BY sort_key
            """
        )
        return [dict(r) for r in rows]


@router.get("/agents/summary")
async def agents_summary(
    q: str | None = Query(None),
    company_name: str | None = Query(None),
    site_code: str | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions, params = [], []
        if q:
            params.append(f"%{q}%")
            conditions.append(f"full_name ILIKE ${len(params)}")
        if company_name:
            params.append(company_name)
            conditions.append(f"company_name = ${len(params)}")
        if site_code:
            params.append(site_code)
            conditions.append(f"site_code = ${len(params)}")
        if year is not None:
            params.append(year)
            conditions.append(f"year = ${len(params)}")
        if month is not None:
            params.append(month)
            conditions.append(f"month = ${len(params)}")

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        total = await conn.fetchval(
            f"SELECT COUNT(DISTINCT full_name) FROM salary_records {where}",
            *params,
        )

        params.extend([limit, offset])
        rows = await conn.fetch(
            f"""
            SELECT
                full_name,
                cnp,
                company_name,
                locatie,
                COUNT(*) AS month_count,
                SUM(total_salary) AS total_salary,
                AVG(total_salary) AS avg_salary
            FROM salary_records
            {where}
            GROUP BY full_name, cnp, company_name, locatie
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
    year: int | None = Query(None),
    month: int | None = Query(None),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Determine the month to query - default to latest in salary_records
        if year is None or month is None:
            latest = await conn.fetchrow(
                "SELECT year, month FROM salary_records ORDER BY year DESC, month DESC LIMIT 1"
            )
            if not latest:
                return {"month": None, "items": []}
            query_year = latest["year"]
            query_month = latest["month"]
        else:
            query_year = year
            query_month = month

        import_month = f"{query_year}-{query_month:02d}"

        # Build conditions - always filter by year/month
        conditions = [f"s.year = $1", f"s.month = $2"]
        params = [query_year, query_month]
        if company_name:
            params.append(company_name)
            conditions.append(f"s.company_name = ${len(params)}")
        if site_code:
            params.append(site_code)
            conditions.append(f"s.site_code = ${len(params)}")

        where_clause = " AND ".join(conditions)

        # Query: salary data grouped by store, joined with sales data from reporting_agent_month
        # $1=year, $2=month (WHERE), then optional company_name ($3 or $4), site_code ($4 or $5)
        # import_month is always the LAST param after all filters, so use $3, $4, or $5 based on count
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
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Build conditions
        conditions = []
        params = []
        if company_name:
            params.append(company_name)
            conditions.append(f"sr.company_name = ${len(params)}")
        if site_code:
            params.append(site_code)
            conditions.append(f"sr.site_code = ${len(params)}")

        # Query monthly trend - join salary_records with reporting_agent_month
        # Group by import_month and optionally company_name
        if company_name:
            group_by = "sr.year, sr.month, sr.company_name"
            order_by = "sr.year DESC, sr.month DESC, sr.company_name"
            select_company = "sr.company_name,"
            sql_company_group = ", sr.company_name"
            sql_company_order = ", sr.company_name"
        else:
            group_by = "sr.year, sr.month"
            order_by = "sr.year DESC, sr.month DESC"
            select_company = ""
            sql_company_group = ""
            sql_company_order = ""

        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        else:
            where_clause = ""

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
            ORDER BY sr.year DESC, sr.month DESC{sql_company_order}
            """,
            *params,
        )

        # Group results by month for the response
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
                months_map[import_month]["by_company"][company]["total_salary"] += (
                    float(r["total_salary"])
                )
                months_map[import_month]["by_company"][company]["total_sales"] += float(
                    r["total_sales"]
                )

        # Sort by month descending
        result = sorted(months_map.values(), key=lambda x: x["month"], reverse=True)
        return result


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
