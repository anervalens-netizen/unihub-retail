from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from domain.filter_scope import FilterInput, normalize_filter_values
from repositories.salarii import MIN_SALARY_FOR_AVERAGE, SalariiRepository
from salary_identity import validate_salary_person_id
from schemas.salarii import (
    AgentSalaryLinkPublic,
    SalaryAgentSummaryPublic,
    SalaryAgentsSummaryResponse,
    SalaryHistoryRecordPublic,
    SalaryHistoryResponse,
    SalaryRecordPublic,
)


MONEY_QUANTUM = Decimal("0.01")
PERCENT_QUANTUM = Decimal("0.0001")
MIN_SALARY_FOR_AVERAGE_DECIMAL = Decimal(str(MIN_SALARY_FOR_AVERAGE))


def _decimal(value: object | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: object | None) -> Decimal:
    return _decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _percentage(numerator: object | None, denominator: object | None) -> Decimal:
    denominator_value = _decimal(denominator)
    if not denominator_value:
        return Decimal("0.0000")
    return (
        _decimal(numerator) / denominator_value * Decimal("100")
    ).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


class InvalidSalaryPersonId(ValueError):
    pass


class UnknownSalaryPerson(LookupError):
    pass


class SalariiService:
    def __init__(self, repo: SalariiRepository, person_id_key: str | None = None):
        self.repo = repo
        self.person_id_key = person_id_key

    async def get_overview(
        self,
        company_name: str | None,
        site_code: FilterInput,
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
            "total": _money(data["total"]),
            "by_company": [
                {**dict(row), "total": _money(row["total"])}
                for row in data["by_company"]
            ],
            "record_count": data["record_count"],
            "agent_count": data["agent_count"],
            "agent_month_count": data["agent_month_count"],
            "avg_agent_month_count": data["avg_agent_month_count"],
            "avg_salary": _money(data["avg_salary"]),
            "months_span": months_span,
        }

    async def get_evolution(
        self,
        company_name: str | None,
        site_code: FilterInput,
        regional: str | None,
        asm: str | None,
    ) -> list[dict]:
        if company_name and not normalize_filter_values(site_code):
            rows = await self.repo.fetch_evolution_single_company(
                company_name=company_name,
                site_code=site_code,
                regional=regional,
                asm=asm,
            )
            return [
                {
                    "month": r["month"],
                    "total": _money(r["total"]),
                    "mobicell": _money(0),
                    "mobiup": _money(0),
                }
                for r in rows
            ]

        rows = await self.repo.fetch_evolution_main(
            company_name=company_name,
            site_code=site_code,
            regional=regional,
            asm=asm,
        )
        return [
            {
                "month": r["month"],
                "total": _money(r["total"]),
                "mobicell": _money(r["mobicell"]),
                "mobiup": _money(r["mobiup"]),
            }
            for r in rows
        ]

    async def get_agents_summary(
        self,
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
        data = await self.repo.fetch_agents_summary(
            q=q,
            company_name=company_name,
            site_code=site_code,
            regional=regional,
            asm=asm,
            year=year,
            month=month,
            limit=limit,
            offset=offset,
        )
        return SalaryAgentsSummaryResponse(
            items=[
                SalaryAgentSummaryPublic(
                    person_id=row["person_id"], full_name=row["full_name"],
                    company_name=row["company_name"], locatie=row["locatie"],
                    month_count=row["month_count"], avg_month_count=row["avg_month_count"],
                    total_salary=_money(row["total_salary"]),
                    avg_salary=_money(row["avg_salary"]),
                )
                for row in data["items"]
            ],
            total=int(data["total"]),
        ).model_dump()

    async def get_agent_history(self, person_id: str) -> dict:
        try:
            validated = validate_salary_person_id(person_id)
        except ValueError as exc:
            raise InvalidSalaryPersonId from exc
        rows = await self.repo.fetch_agent_history_by_person_id(validated)
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
        )
        if not link:
            return {
                "link": None,
                "records": [],
                "total": _money(0),
                "avg": _money(0),
                "month_count": 0,
                "avg_month_count": 0,
            }

        is_confirmed_identity = (
            link["match_status"] == "confirmed"
            and bool(link["person_id"])
        )
        link_payload = AgentSalaryLinkPublic(
            agent_code=link["agent_code"],
            site_code=link["site_code"],
            salary_full_name=link["salary_full_name"],
            person_id=link["person_id"] if is_confirmed_identity else None,
            match_status=link["match_status"],
            match_source=link["match_source"],
            confidence=link["confidence"],
            effective_from_month=link["effective_from_month"],
            note=link["note"],
        ).model_dump()
        if not is_confirmed_identity:
            return {
                "link": link_payload,
                "records": [],
                "total": _money(0),
                "avg": _money(0),
                "month_count": 0,
                "avg_month_count": 0,
            }

        rows = await self.repo.fetch_agent_history_by_salary_link(
            person_id=link_payload["person_id"],
        )
        result = self._format_agent_history(rows)
        result["link"] = link_payload
        return result

    def _format_agent_history(self, rows) -> dict:
        if not rows:
            return SalaryHistoryResponse(
                records=[], total=_money(0), avg=_money(0),
                month_count=0, avg_month_count=0,
            ).model_dump()
        total = sum((_decimal(r["total_salary"]) for r in rows), start=Decimal("0"))
        month_count = len({(r["year"], r["month"]) for r in rows})
        monthly_totals: dict[tuple[int, int], Decimal] = {}
        for row in rows:
            period = (row["year"], row["month"])
            monthly_totals[period] = monthly_totals.get(period, Decimal("0")) + _decimal(row["total_salary"])
        eligible_months = [
            salary
            for salary in monthly_totals.values()
            if salary >= MIN_SALARY_FOR_AVERAGE_DECIMAL
        ]
        avg = (
            sum(eligible_months, start=Decimal("0")) / Decimal(len(eligible_months))
            if eligible_months
            else Decimal("0")
        )
        return SalaryHistoryResponse(
            records=[SalaryHistoryRecordPublic(year=int(r["year"]), month=int(r["month"]), company_name=r["company_name"], total_salary=_money(r["total_salary"]), site_code=r["site_code"], locatie=r["locatie"]) for r in rows],
            total=_money(total), avg=_money(avg), month_count=month_count, avg_month_count=len(eligible_months),
        ).model_dump()

    async def get_summary(
        self,
        company_name: str | None,
        site_code: FilterInput,
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
                    "total_salary": _money(r["total_salary"]),
                    "agent_count": r["agent_count"],
                    "avg_agent_count": r["avg_agent_count"],
                    "avg_salary": _money(r["avg_salary"]),
                    "total_sales": _money(r["total_sales"]),
                    "ratio": _percentage(r["total_salary"], r["total_sales"]),
                }
                for r in rows
            ],
        }

    async def get_trend(
        self,
        company_name: str | None,
        site_code: FilterInput,
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
                "total_salary": _money(r["total_salary"]),
                "total_sales": _money(r["total_sales"]),
                "agent_count": r["agent_count"],
                "avg_agent_count": r["avg_agent_count"],
                "avg_salary": _money(r["avg_salary"]),
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
        site_code: FilterInput,
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
        )
        return [SalaryRecordPublic(id=int(r["id"]), year=int(r["year"]), month=int(r["month"]), full_name=r["full_name"], person_id=r["person_id"], total_salary=_money(r["total_salary"]), company_name=r["company_name"], site_code=r["site_code"], locatie=r["locatie"]).model_dump() for r in rows]
