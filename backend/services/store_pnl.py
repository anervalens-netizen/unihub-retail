from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from repositories.store_pnl import StorePnlRepository
from services.fiscal_rules import runtime_gross_to_net

REVENUE_CODES = {"v1", "v11", "v2", "v3"}
COGS_CODES = {"c1", "c11", "c2"}
OPERATING_CODES = {"c3", "c4", "c5", "c6"}
UNALLOCATED_SOURCE = "__FINANCE_UNALLOCATED__"
_MONEY = Decimal("0.01")
_PERCENT = Decimal("0.01")


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


def money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def percent(value: Decimal) -> Decimal:
    return value.quantize(_PERCENT, rounding=ROUND_HALF_UP)


def finalize_metrics(values: dict[str, Decimal]) -> dict[str, Decimal]:
    values["gross_margin"] = values["revenue"] - values["cogs"]
    values["ebitda"] = values["gross_margin"] - values["operating_costs"]
    values["ebit"] = values["ebitda"] - values["depreciation"]
    return {key: money(value) for key, value in values.items()}


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
        regional: str | None = None,
    ) -> dict:
        rows = await self.repository.rows(
            start,
            end,
            company,
            site_code,
            site_company,
            regional,
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
            if row["source_site_code"] == UNALLOCATED_SOURCE:
                continue
            store_key = (row["company_name"], row["site_code"])
            if store_key not in stores:
                stores[store_key] = {
                    "company": row["company_name"],
                    "site_code": row["site_code"] or row["source_site_code"],
                    "source_site_code": row["source_site_code"],
                    "location": row["source_location_name"],
                    "regional": row["regional"],
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

        sales_by_month = {}
        for row in await self.repository.sales_rows(
            start,
            end,
            company,
            site_code,
            site_company,
            regional,
        ):
            gross_amount = Decimal(row["gross_amount"] or 0)
            sales_by_month[row["period"]] = (
                gross_amount,
                runtime_gross_to_net(gross_amount, row["period"]),
            )
        reconciliation = []
        for period, values in sorted(monthly.items()):
            metrics = finalize_metrics(values.copy())
            gross_sales, net_sales = sales_by_month.get(period, (Decimal("0"), Decimal("0")))
            reconciliation.append({
                "month": period.strftime("%Y-%m"),
                "pnl_revenue": metrics["revenue"],
                "retail_sales_gross": money(gross_sales),
                "retail_sales_net": money(net_sales),
                "difference_to_net": money(metrics["revenue"] - net_sales),
                "pnl_to_net_sales_pct": (
                    percent(metrics["revenue"] / net_sales * Decimal("100"))
                    if net_sales
                    else None
                ),
            })

        return {
            "start_month": start.strftime("%Y-%m"),
            "end_month": end.strftime("%Y-%m"),
            "company": company,
            "site_code": site_code,
            "site_company": site_company,
            "regional": regional,
            "summary": finalize_metrics(total),
            "monthly": [
                {
                    "month": period.strftime("%Y-%m"),
                    **finalize_metrics(values),
                    "is_estimated": period in estimate_months,
                }
                for period, values in sorted(monthly.items())
            ],
            "categories": {key: money(value) for key, value in sorted(categories.items())},
            "stores": store_payload,
            "reconciliation": reconciliation,
        }

    async def stores(self, company: str | None, regional: str | None = None) -> list[dict]:
        return [dict(row) for row in await self.repository.stores(company, regional)]

    async def regions(self, company: str | None) -> list[str]:
        return await self.repository.regions(company)

    async def annual(
        self,
        company: str | None,
        site_code: str | None,
        site_company: str | None = None,
        regional: str | None = None,
    ) -> list[dict]:
        yearly: dict[int, dict[str, Decimal]] = defaultdict(empty_metrics)
        estimate_years: set[int] = set()
        store_counts: dict[int, int] = defaultdict(int)
        month_counts: dict[int, int] = defaultdict(int)
        for row in await self.repository.annual_rows(company, site_code, site_company, regional):
            year = row["year"]
            add_amount(yearly[year], row["category_code"], row["amount"])
            store_counts[year] = max(store_counts[year], row["store_count"])
            month_counts[year] = max(month_counts[year], row["month_count"])
            if row["is_estimated"]:
                estimate_years.add(year)
        return [
            {
                "year": str(year),
                "store_count": store_counts[year],
                "month_count": month_counts[year],
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
