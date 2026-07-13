from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from repositories.store_pnl import StorePnlRepository

REVENUE_CODES = {"v1", "v11", "v2", "v3"}
COGS_CODES = {"c1", "c11", "c2"}
OPERATING_CODES = {"c3", "c4", "c5", "c6"}


def empty_metrics() -> dict[str, Decimal]:
    return {
        "revenue": Decimal("0"),
        "cogs": Decimal("0"),
        "gross_margin": Decimal("0"),
        "operating_costs": Decimal("0"),
        "ebitda": Decimal("0"),
        "depreciation": Decimal("0"),
        "ebit": Decimal("0"),
    }


def finalize_metrics(values: dict[str, Decimal]) -> dict[str, float]:
    values["gross_margin"] = values["revenue"] - values["cogs"]
    values["ebitda"] = values["gross_margin"] - values["operating_costs"]
    values["ebit"] = values["ebitda"] - values["depreciation"]
    return {key: round(float(value), 2) for key, value in values.items()}


def add_amount(values: dict[str, Decimal], category: str, amount: Decimal) -> None:
    if category in REVENUE_CODES:
        values["revenue"] += amount
    elif category in COGS_CODES:
        values["cogs"] += amount
    elif category in OPERATING_CODES:
        values["operating_costs"] += amount
    elif category == "a1":
        values["depreciation"] += amount


class StorePnlService:
    def __init__(self, repository: StorePnlRepository):
        self.repository = repository

    async def overview(
        self,
        start: date,
        end: date,
        company: str | None,
        site_code: str | None = None,
        site_company: str | None = None,
    ) -> dict:
        rows = await self.repository.rows(
            start,
            end,
            company,
            site_code,
            site_company,
        )
        total = empty_metrics()
        monthly: dict[date, dict[str, Decimal]] = defaultdict(empty_metrics)
        stores: dict[tuple[str, str], dict] = {}
        categories: dict[str, Decimal] = defaultdict(Decimal)
        estimate_months: set[date] = set()

        for row in rows:
            amount = row["amount"]
            category = row["category_code"]
            add_amount(total, category, amount)
            add_amount(monthly[row["period"]], category, amount)
            categories[category] += amount
            if row["data_kind"] == "estimated":
                estimate_months.add(row["period"])
            store_key = (row["company_name"], row["source_site_code"])
            if store_key not in stores:
                stores[store_key] = {
                    "company": row["company_name"],
                    "site_code": row["site_code"] or row["source_site_code"],
                    "source_site_code": row["source_site_code"],
                    "location": row["source_location_name"],
                    "metrics": empty_metrics(),
                    "has_estimates": False,
                }
            add_amount(stores[store_key]["metrics"], category, amount)
            stores[store_key]["has_estimates"] |= row["data_kind"] == "estimated"

        store_payload = []
        for store in stores.values():
            metrics = finalize_metrics(store.pop("metrics"))
            store_payload.append({**store, **metrics})
        store_payload.sort(key=lambda item: item["ebit"], reverse=True)

        return {
            "start_month": start.strftime("%Y-%m"),
            "end_month": end.strftime("%Y-%m"),
            "company": company,
            "site_code": site_code,
            "site_company": site_company,
            "summary": finalize_metrics(total),
            "monthly": [
                {
                    "month": period.strftime("%Y-%m"),
                    **finalize_metrics(values),
                    "is_estimated": period in estimate_months,
                }
                for period, values in sorted(monthly.items())
            ],
            "categories": {key: round(float(value), 2) for key, value in sorted(categories.items())},
            "stores": store_payload,
        }

    async def stores(self, company: str | None) -> list[dict]:
        return [dict(row) for row in await self.repository.stores(company)]

    async def annual(
        self,
        company: str | None,
        site_code: str | None,
        site_company: str | None = None,
    ) -> list[dict]:
        yearly: dict[int, dict[str, Decimal]] = defaultdict(empty_metrics)
        estimate_years: set[int] = set()
        for row in await self.repository.annual_rows(company, site_code, site_company):
            year = row["year"]
            add_amount(yearly[year], row["category_code"], row["amount"])
            if row["is_estimated"]:
                estimate_years.add(year)
        return [
            {
                "year": str(year),
                **finalize_metrics(values),
                "is_estimated": year in estimate_years,
            }
            for year, values in sorted(yearly.items())
        ]

    async def months(self) -> list[dict]:
        return [
            {
                "month": row["period"].strftime("%Y-%m"),
                "has_actual": row["has_actual"],
                "has_estimated": row["has_estimated"],
            }
            for row in await self.repository.available_months()
        ]
