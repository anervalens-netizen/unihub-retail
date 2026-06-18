from __future__ import annotations

from typing import Any

from repositories.salarii import MIN_SALARY_FOR_AVERAGE, SalariiRepository


class SalariiService:
    def __init__(self, repo: SalariiRepository):
        self.repo = repo

    async def get_overview(
        self, company_name: str | None, regional: str | None, asm: str | None
    ) -> dict:
        conditions: list[str] = []; params: list[Any] = []
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
        data = await self.repo.fetch_overview(join_sql, where_sql, params)

        months_row = data["months_row"]
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
            "total": data["total"],
            "by_company": data["by_company"],
            "record_count": data["record_count"],
            "agent_count": data["agent_count"],
            "agent_month_count": data["agent_month_count"],
            "avg_agent_month_count": data["avg_agent_month_count"],
            "avg_salary": data["avg_salary"],
            "months_span": months_span,
        }

    async def get_evolution(
        self, company_name: str | None, regional: str | None, asm: str | None
    ) -> list[dict]:
        conditions: list[str] = []; params: list[Any] = []
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
            rows = await self.repo.fetch_evolution_single_company(join_sql, where_sql, params)
            return [
                {"month": r["month"], "total": float(r["total"]), "mobicell": 0.0, "mobiup": 0.0}
                for r in rows
            ]

        rows = await self.repo.fetch_evolution_main(join_sql, where_sql, params)
        return [dict(r) for r in rows]

    async def get_agents_summary(
        self,
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
        conditions: list[str] = []; params: list[Any] = []
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

        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""
        return await self.repo.fetch_agents_summary(join_sql, where_sql, params, limit, offset)

    async def get_agent_history(self, cnp: str) -> dict:
        rows = await self.repo.fetch_agent_history(cnp)
        if not rows:
            return {
                "records": [],
                "total": 0.0,
                "avg": 0.0,
                "month_count": 0,
                "avg_month_count": 0,
            }
        total = sum(float(r["total_salary"]) for r in rows)
        month_count = len({(r["year"], r["month"]) for r in rows})
        monthly_totals: dict[tuple[int, int], float] = {}
        for row in rows:
            period = (row["year"], row["month"])
            monthly_totals[period] = monthly_totals.get(period, 0.0) + float(row["total_salary"])
        eligible_months = [
            salary
            for salary in monthly_totals.values()
            if salary >= MIN_SALARY_FOR_AVERAGE
        ]
        avg = sum(eligible_months) / len(eligible_months) if eligible_months else 0.0
        return {
            "records": [dict(r) for r in rows],
            "total": total,
            "avg": avg,
            "month_count": month_count,
            "avg_month_count": len(eligible_months),
        }

    async def get_summary(
        self,
        company_name: str | None,
        site_code: str | None,
        regional: str | None,
        asm: str | None,
        year: int | None,
        month: int | None,
    ) -> dict:
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
            latest = await self.repo.fetch_latest_month(latest_join, latest_where, latest_params)
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
        rows = await self.repo.fetch_summary_by_site(join_stores, where_clause, params, import_month)

        return {
            "month": import_month,
            "items": [
                {
                    "site_code": r["site_code"],
                    "locatie": r["locatie"],
                    "company_name": r["company_name"],
                    "total_salary": float(r["total_salary"]),
                    "agent_count": r["agent_count"],
                    "avg_agent_count": r["avg_agent_count"],
                    "avg_salary": float(r["avg_salary"]),
                    "total_sales": float(r["total_sales"]),
                    "ratio": float(r["total_salary"]) / float(r["total_sales"]) * 100
                    if r["total_sales"]
                    else 0,
                }
                for r in rows
            ],
        }

    async def get_trend(
        self,
        company_name: str | None,
        site_code: str | None,
        regional: str | None,
        asm: str | None,
    ) -> list[dict]:
        conditions: list[str] = []; params: list[Any] = []
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

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        join_stores = "LEFT JOIN stores st ON st.site_code = sr.site_code" if needs_store_join else ""

        rows = await self.repo.fetch_trend(join_stores, where_clause, params)
        return [
            {
                "month": f"{r['year']}-{r['month']:02d}",
                "total_salary": float(r["total_salary"]),
                "total_sales": float(r["total_sales"]),
                "agent_count": r["agent_count"],
                "avg_agent_count": r["avg_agent_count"],
                "avg_salary": float(r["avg_salary"]),
                "by_company": {},
            }
            for r in rows
        ]

    async def get_stores(self, company_name: str | None) -> list[dict]:
        conditions: list[str] = []; params: list[Any] = []
        if company_name:
            params.append(company_name)
            conditions.append(f"company_name = ${len(params)}")
        if conditions:
            where = "WHERE site_code IS NOT NULL AND " + " AND ".join(conditions)
        else:
            where = "WHERE site_code IS NOT NULL"
        rows = await self.repo.fetch_stores(where, params)
        return [{"site_code": r["site_code"], "locatie": r["locatie"]} for r in rows]

    async def get_records(
        self,
        company_name: str | None,
        year: int | None,
        month: int | None,
        site_code: str | None,
        limit: int,
        offset: int,
    ) -> list[dict]:
        conditions: list[str] = []; params: list[Any] = []
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
        rows = await self.repo.fetch_records(where, params, limit, offset)
        return [dict(r) for r in rows]
