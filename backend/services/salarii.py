from __future__ import annotations

from repositories.salarii import MIN_SALARY_FOR_AVERAGE, SalariiRepository
from salary_identity import get_salary_person_id_key, validate_salary_person_id


class InvalidSalaryPersonId(ValueError):
    pass


class UnknownSalaryPerson(LookupError):
    pass


class SalariiService:
    def __init__(self, repo: SalariiRepository, person_id_key: str | None = None):
        self.repo = repo
        self.person_id_key = person_id_key

    def _person_id_key(self) -> str:
        return self.person_id_key or get_salary_person_id_key()

    async def get_overview(
        self,
        company_name: str | None,
        site_code: str | None,
        regional: str | None,
        asm: str | None,
    ) -> dict:
        data = await self.repo.fetch_overview(
            company_name=company_name,
            site_code=site_code,
            regional=regional,
            asm=asm,
        )

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
        self,
        company_name: str | None,
        site_code: str | None,
        regional: str | None,
        asm: str | None,
    ) -> list[dict]:
        if company_name:
            rows = await self.repo.fetch_evolution_single_company(
                company_name=company_name,
                site_code=site_code,
                regional=regional,
                asm=asm,
            )
            return [
                {"month": r["month"], "total": float(r["total"]), "mobicell": 0.0, "mobiup": 0.0}
                for r in rows
            ]

        rows = await self.repo.fetch_evolution_main(
            company_name=company_name,
            site_code=site_code,
            regional=regional,
            asm=asm,
        )
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
        return await self.repo.fetch_agents_summary(
            q=q,
            company_name=company_name,
            site_code=site_code,
            regional=regional,
            asm=asm,
            year=year,
            month=month,
            limit=limit,
            offset=offset,
            person_id_key=self._person_id_key(),
        )

    async def get_agent_history(self, person_id: str) -> dict:
        try:
            validated = validate_salary_person_id(person_id)
        except ValueError as exc:
            raise InvalidSalaryPersonId from exc
        rows = await self.repo.fetch_agent_history_by_person_id(
            validated,
            self._person_id_key(),
        )
        if not rows:
            raise UnknownSalaryPerson
        return self._format_agent_history(rows)

    async def get_agent_history_by_retail_code(
        self,
        *,
        agent_code: str,
        site_code: str,
    ) -> dict:
        link = await self.repo.fetch_agent_salary_link(
            agent_code=agent_code,
            site_code=site_code,
            person_id_key=self._person_id_key(),
        )
        if not link:
            return {
                "link": None,
                "records": [],
                "total": 0.0,
                "avg": 0.0,
                "month_count": 0,
                "avg_month_count": 0,
            }

        is_confirmed_identity = (
            link["match_status"] == "confirmed"
            and bool(link["salary_full_name"])
            and bool(link["person_id"])
        )
        link_payload = {
            "agent_code": link["agent_code"],
            "site_code": link["site_code"],
            "salary_full_name": link["salary_full_name"],
            "person_id": link["person_id"] if is_confirmed_identity else None,
            "match_status": link["match_status"],
            "match_source": link["match_source"],
            "confidence": link["confidence"],
            "effective_from_month": link["effective_from_month"],
            "note": link["note"],
        }
        if not is_confirmed_identity:
            return {
                "link": link_payload,
                "records": [],
                "total": 0.0,
                "avg": 0.0,
                "month_count": 0,
                "avg_month_count": 0,
            }

        rows = await self.repo.fetch_agent_history_by_salary_link(
            person_id=link_payload["person_id"],
            person_id_key=self._person_id_key(),
        )
        result = self._format_agent_history(rows)
        result["link"] = link_payload
        return result

    def _format_agent_history(self, rows) -> dict:
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
            latest = await self.repo.fetch_latest_month(
                company_name=company_name,
                site_code=site_code,
                regional=regional,
                asm=asm,
            )
            if not latest:
                return {"month": None, "items": []}
            query_year = latest["year"]
            query_month = latest["month"]
        else:
            query_year = year
            query_month = month

        import_month = f"{query_year}-{query_month:02d}"
        rows = await self.repo.fetch_summary_by_site(
            company_name=company_name,
            site_code=site_code,
            regional=regional,
            asm=asm,
            year=query_year,
            month=query_month,
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
        rows = await self.repo.fetch_trend(
            company_name=company_name,
            site_code=site_code,
            regional=regional,
            asm=asm,
        )
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
        rows = await self.repo.fetch_stores(company_name=company_name)
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
        rows = await self.repo.fetch_records(
            company_name=company_name,
            year=year,
            month=month,
            site_code=site_code,
            limit=limit,
            offset=offset,
            person_id_key=self._person_id_key(),
        )
        return [dict(r) for r in rows]
