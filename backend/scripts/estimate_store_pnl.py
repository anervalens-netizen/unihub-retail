#!/usr/bin/env python3
"""Reconstruieste lunile P&L lipsa, fara a modifica vanzarile Retail.

Vanzarile din ``historical_monthly_sales`` si ``reporting_agent_month`` sunt
citite exclusiv ca semnal pentru model. Ele sunt stocate cu TVA, iar modelul
foloseste registrul fiscal effective-dated pentru a nu compara venituri P&L cu
vanzari brute. Un magazin-luna care exista in Finance ramane exclusiv
Finance; estimarile se creeaza numai pentru magazine-luni complet absente.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import asyncpg
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.fiscal_rules import (
    LEGACY_VAT_RULESET_ID,
    STANDARD_VAT_RULESET_ID,
    gross_to_net,
    legacy_gross_to_net,
    standard_vat_ruleset_hash,
)
from business_clock import business_today

REPO_DIR = BACKEND_DIR.parent
LEGACY_MODEL_VERSION = "store-pnl-estimator-v2"
EFFECTIVE_MODEL_VERSION = "store-pnl-estimator-v3-effective-vat"
VARIABLE_CODES = {"v1", "v11", "v2", "v3", "c1", "c11", "c2"}
REVENUE_CODES = {"v1", "v11", "v2", "v3"}
FIXED_CODES = {"c4", "c5", "c6", "a1"}
VALID_CODES = VARIABLE_CODES | FIXED_CODES | {"c3"}
CATEGORY_NAMES = {
    "v1": "Venituri din vanzari cartele", "v11": "Venituri din accesorii",
    "v2": "Venituri din incarcare electronica", "v3": "Alte venituri",
    "c1": "Cheltuieli cu marfa cartele", "c11": "Cheltuieli cu marfa accesorii",
    "c2": "Cheltuieli cu incarcare electronica", "c3": "Cost salarii",
    "c4": "Chirii", "c5": "Utilitati", "c6": "Alte costuri directe", "a1": "Amortizare",
}


@dataclass(frozen=True)
class Estimate:
    company_name: str
    period: date
    site_code: str
    source_site_code: str
    source_location_name: str
    category_code: str
    category_name: str
    amount: Decimal


def month_date(value: str) -> date:
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


ZERO = Decimal("0")
MONEY = Decimal("0.01")
Numeric = Decimal | int | float | str


def as_decimal(value: Numeric) -> Decimal:
    """Normalize external numeric values before any P&L arithmetic."""
    return value if isinstance(value, Decimal) else Decimal(str(value))


def money(value: Numeric) -> Decimal:
    return max(ZERO, as_decimal(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def median(values: Iterable[Numeric]) -> Decimal | None:
    items = sorted(as_decimal(value) for value in values)
    if not items:
        return None
    middle = len(items) // 2
    if len(items) % 2:
        return items[middle]
    return (items[middle - 1] + items[middle]) / Decimal("2")


def relevant_history(
    history: Sequence[tuple[date, Numeric]],
    target: date,
    *,
    causal: bool,
    limit: int = 12,
) -> list[tuple[date, Numeric]]:
    eligible = [item for item in history if not causal or item[0] < target]
    return sorted(eligible, key=lambda item: abs((item[0] - target).days))[:limit]


def ratio_history(
    values: Sequence[tuple[date, Numeric]],
    bases: Mapping[date, Numeric],
    target: date,
    *,
    causal: bool,
) -> list[tuple[date, Decimal]]:
    return [
        (period, as_decimal(amount) / as_decimal(bases[period]))
        for period, amount in relevant_history(values, target, causal=causal)
        if as_decimal(bases.get(period, ZERO)) > ZERO
    ]


def predict_amount(
    category: str,
    target: date,
    history: Sequence[tuple[date, Numeric]],
    sales_history: Mapping[date, Numeric],
    salary_history: Mapping[date, Numeric],
    target_sales: Numeric,
    target_salary: Numeric,
    *,
    causal: bool = False,
) -> Decimal | None:
    """Estimate a value from one store history; kept small and unit-testable."""
    target_sales_decimal = as_decimal(target_sales)
    target_salary_decimal = as_decimal(target_salary)
    nearest = relevant_history(history, target, causal=causal)
    if not nearest:
        return None
    if category == "c3" and target_salary_decimal > ZERO:
        salary_ratios = ratio_history(history, salary_history, target, causal=causal)
        if salary_ratios:
            median_ratio = median(ratio for _, ratio in salary_ratios)
            if median_ratio is not None:
                return median_ratio * target_salary_decimal
    if category in VARIABLE_CODES or category == "c3":
        sales_ratios = ratio_history(history, sales_history, target, causal=causal)
        if sales_ratios and target_sales_decimal > ZERO:
            median_ratio = median(ratio for _, ratio in sales_ratios)
            if median_ratio is not None:
                return median_ratio * target_sales_decimal
    if category in FIXED_CODES:
        same_month = [amount for period, amount in nearest if period.month == target.month]
        return median(same_month) if same_month else median(amount for _, amount in nearest[:3])
    return median(amount for _, amount in nearest)


def aggregate_ratios(
    entries: Sequence[tuple[date, Numeric]],
) -> list[tuple[date, Decimal]]:
    by_period: dict[date, list[Decimal]] = defaultdict(list)
    for period, value in entries:
        by_period[period].append(as_decimal(value))
    aggregated: list[tuple[date, Decimal]] = []
    for period, values in by_period.items():
        median_value = median(values)
        if median_value is not None:
            aggregated.append((period, median_value))
    return aggregated


def choose_ratio(
    store_ratios: Sequence[tuple[date, Numeric]],
    company_ratios: Sequence[tuple[date, Numeric]],
    target: date,
    *,
    causal: bool,
) -> Decimal | None:
    nearby_store = relevant_history(store_ratios, target, causal=causal)
    nearby_company = relevant_history(company_ratios, target, causal=causal)
    chosen = nearby_store if len(nearby_store) >= 2 else nearby_company
    return median(value for _, value in chosen)


async def load_inputs(
    connection: asyncpg.Connection,
    *,
    input_cutoff: date | None = None,
):
    """Read raw estimator inputs without selecting a VAT interpretation.

    Shadow generations invoke this inside repeatable-read.  Gross sales remain
    raw here so legacy-v2 and effective-v3 are comparable from one snapshot.
    """
    cutoff = input_cutoff or date.max
    actual = await connection.fetch(
        """
        SELECT p.company_name, p.period,
               MIN(p.source_site_code) AS source_site_code,
               MIN(p.source_location_name) AS source_location_name,
               p.category_code, MAX(p.category_name) AS category_name,
               SUM(p.amount) AS amount,
               COALESCE(l.site_code, p.source_site_code) AS site_code
        FROM store_pnl_monthly p
        LEFT JOIN store_pnl_site_links l USING (company_name, source_site_code)
        WHERE p.data_kind = 'actual'
          AND p.source_site_code <> '__FINANCE_UNALLOCATED__'
          AND p.period <= $1
        GROUP BY p.company_name, p.period,
                 COALESCE(l.site_code, p.source_site_code), p.category_code
        """,
        cutoff,
    )
    gross_sales = await connection.fetch(
        """
        WITH sources AS (
            SELECT CASE WHEN firma ILIKE 'mobicell%' THEN 'Mobicell' ELSE 'Mobiup' END AS company_name,
                   to_date(import_month || '-01', 'YYYY-MM-DD') AS period,
                   site_code, total_value::numeric AS gross_amount, 1 AS priority
            FROM historical_monthly_sales
            UNION ALL
            SELECT CASE WHEN firma ILIKE 'mobicell%' THEN 'Mobicell' ELSE 'Mobiup' END,
                   to_date(import_month || '-01', 'YYYY-MM-DD'), site_code,
                   SUM(total_sales)::numeric, 2
            FROM reporting_agent_month GROUP BY firma, import_month, site_code
        ), preferred AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY company_name, period, site_code ORDER BY priority DESC
            ) AS preference_rank FROM sources
        )
        SELECT company_name, period, site_code, gross_amount
        FROM preferred
        WHERE preference_rank = 1
          AND period <= $1
        """,
        cutoff,
    )
    salaries = await connection.fetch(
        """
        SELECT CASE WHEN company_name ILIKE 'mobicell%' THEN 'Mobicell' ELSE 'Mobiup' END AS company_name,
               make_date(year, month, 1) AS period, site_code, SUM(total_salary)::numeric AS amount
        FROM salary_records
        WHERE site_code IS NOT NULL
          AND make_date(year, month, 1) <= $1
        GROUP BY company_name, year, month, site_code
        """,
        cutoff,
    )
    stores = await connection.fetch("SELECT site_code, locatie, firma FROM stores")
    return actual, gross_sales, salaries, stores


def normalize_sales(gross_sales, *, effective_vat: bool = False):
    """Normalize a previously captured gross-sales input snapshot."""
    net_converter = gross_to_net if effective_vat else legacy_gross_to_net
    return [
        {
            "company_name": row["company_name"],
            "period": row["period"],
            "site_code": row["site_code"],
            "amount": net_converter(row["gross_amount"], row["period"]),
        }
        for row in gross_sales
    ]


async def load_data(
    connection: asyncpg.Connection,
    *,
    effective_vat: bool = False,
    input_cutoff: date | None = None,
):
    """Compatibility wrapper for legacy estimator callers."""
    actual, gross_sales, salaries, stores = await load_inputs(
        connection,
        input_cutoff=input_cutoff,
    )
    return actual, normalize_sales(gross_sales, effective_vat=effective_vat), salaries, stores


def build_estimates(
    actual,
    sales_rows,
    salary_rows,
    stores,
    targets: set[tuple[str, date, str]],
    *,
    causal: bool,
    include_actual_targets: bool = False,
) -> list[Estimate]:
    # Sales in this dictionary are deliberately *net of TVA*. No sales table is written.
    sales = {(row["company_name"], row["period"], row["site_code"]): as_decimal(row["amount"]) for row in sales_rows}
    salaries = {(row["company_name"], row["period"], row["site_code"]): as_decimal(row["amount"]) for row in salary_rows}
    store_lookup = {row["site_code"]: row for row in stores}
    actual_store_months = {(row["company_name"], row["period"], row["site_code"]) for row in actual}
    store_history: dict[tuple[str, str, str], list[tuple[date, Decimal]]] = defaultdict(list)
    company_values: dict[tuple[str, str], list[tuple[date, Decimal]]] = defaultdict(list)
    store_sales_ratios: dict[tuple[str, str, str], list[tuple[date, Decimal]]] = defaultdict(list)
    company_sales_ratios: dict[tuple[str, str], list[tuple[date, Decimal]]] = defaultdict(list)
    store_salary_ratios: dict[tuple[str, str, str], list[tuple[date, Decimal]]] = defaultdict(list)
    company_salary_ratios: dict[tuple[str, str], list[tuple[date, Decimal]]] = defaultdict(list)
    metadata: dict[tuple[str, str], tuple[date, str, str]] = {}
    category_names = dict(CATEGORY_NAMES)

    for row in actual:
        company, period, site_code, category = row["company_name"], row["period"], row["site_code"], row["category_code"]
        amount = as_decimal(row["amount"])
        key = (company, site_code, category)
        store_history[key].append((period, amount))
        company_values[(company, category)].append((period, amount))
        sales_value = sales.get((company, period, site_code), ZERO)
        if sales_value > ZERO:
            store_sales_ratios[key].append((period, amount / sales_value))
            company_sales_ratios[(company, category)].append((period, amount / sales_value))
        salary_value = salaries.get((company, period, site_code), ZERO)
        if salary_value > ZERO:
            store_salary_ratios[key].append((period, amount / salary_value))
            company_salary_ratios[(company, category)].append((period, amount / salary_value))
        category_names[category] = row["category_name"] or category_names.get(category, category)
        meta_key = (company, site_code)
        previous = metadata.get(meta_key)
        if previous is None or period >= previous[0]:
            metadata[meta_key] = (period, row["source_site_code"], row["source_location_name"])

    company_values = {key: aggregate_ratios(values) for key, values in company_values.items()}
    company_sales_ratios = {key: aggregate_ratios(values) for key, values in company_sales_ratios.items()}
    company_salary_ratios = {key: aggregate_ratios(values) for key, values in company_salary_ratios.items()}
    estimates: list[Estimate] = []
    for company, target, site_code in sorted(targets):
        store = store_lookup.get(site_code)
        if not store:
            continue
        # Finance is authoritative at store-month level. Never alter or
        # supplement a source that exists in the imported P&L workbook.
        if not include_actual_targets and (company, target, site_code) in actual_store_months:
            continue
        _, source_code, location = metadata.get((company, site_code), (target, site_code, store["locatie"]))
        target_sales = sales.get((company, target, site_code), ZERO)
        target_salary = salaries.get((company, target, site_code), ZERO)
        if target_sales <= ZERO:
            continue
        estimated_amounts: dict[str, Decimal] = {}
        for category in sorted(VALID_CODES):
            key = (company, site_code, category)
            store_values = store_history.get(key, [])
            estimate_amount: Decimal | None
            if category == "c3" and target_salary > ZERO:
                ratio = choose_ratio(store_salary_ratios.get(key, []), company_salary_ratios.get((company, category), []), target, causal=causal)
                estimate_amount = ratio * target_salary if ratio is not None else None
            elif category in VARIABLE_CODES or category == "c3":
                ratio = choose_ratio(store_sales_ratios.get(key, []), company_sales_ratios.get((company, category), []), target, causal=causal)
                estimate_amount = ratio * target_sales if ratio is not None else None
            else:
                values = relevant_history(store_values, target, causal=causal)
                fallback = relevant_history(company_values.get((company, category), []), target, causal=causal)
                chosen = values if len(values) >= 2 else fallback
                same_month = [value for period, value in chosen if period.month == target.month]
                estimate_amount = (
                    median(same_month)
                    if same_month
                    else median(value for _, value in chosen[:3])
                )
            if estimate_amount is not None:
                estimated_amounts[category] = estimate_amount

        # For a completely missing P&L store-month, the estimated P&L revenue
        # must equal the Retail sale without TVA. Retain the observed revenue
        # category mix only as an allocation detail.
        revenue_amount = sum((estimated_amounts.get(category, ZERO) for category in REVENUE_CODES), ZERO)
        if revenue_amount > ZERO:
            scale = target_sales / revenue_amount
            for category in REVENUE_CODES:
                if category in estimated_amounts:
                    estimated_amounts[category] *= scale
        for category, amount in estimated_amounts.items():
            estimates.append(Estimate(company, target, site_code, source_code, location, category, category_names[category], money(amount)))
    return estimates


def all_missing_targets(
    actual,
    sales_rows,
    *,
    input_cutoff: date | None = None,
) -> set[tuple[str, date, str]]:
    today = (input_cutoff or business_today()).replace(day=1)
    actual_store_months = {
        (row["company_name"], row["period"], row["site_code"])
        for row in actual
    }
    return {
        (row["company_name"], row["period"], row["site_code"])
        for row in sales_rows
        if date(2018, 1, 1) <= row["period"] < today and as_decimal(row["amount"]) > ZERO
        and (row["company_name"], row["period"], row["site_code"])
        not in actual_store_months
    }


def estimate_replacement_scopes(
    targets: set[tuple[str, date, str]],
) -> list[tuple[str, date]]:
    return sorted({(company, period) for company, period, _ in targets})


def backtest(actual, sales_rows, salary_rows, stores) -> None:
    actual_lookup = {
        (row["company_name"], row["period"], row["site_code"], row["category_code"]): as_decimal(row["amount"])
        for row in actual
    }
    targets = {(company, period, site) for company, period, site, _ in actual_lookup if date(2025, 1, 1) <= period <= date(2026, 4, 1)}
    predicted = build_estimates(
        actual,
        sales_rows,
        salary_rows,
        stores,
        targets,
        causal=True,
        include_actual_targets=True,
    )
    totals: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for row in predicted:
        actual_amount = actual_lookup.get((row.company_name, row.period, row.site_code, row.category_code))
        if actual_amount is None:
            continue
        totals[row.category_code][0] += abs(row.amount - actual_amount)
        totals[row.category_code][1] += abs(actual_amount)
    overall_error = sum((error for error, _ in totals.values()), ZERO)
    overall_actual = sum((total for _, total in totals.values()), ZERO)
    print("Backtest cauzal 2025-01..2026-04 (WAPE):")
    for category in sorted(totals):
        error, total = totals[category]
        print(f"  {category}: {100 * error / total:.1f}%" if total else f"  {category}: n/a")
    print(f"  TOTAL categorii: {100 * overall_error / overall_actual:.1f}%" if overall_actual else "  TOTAL categorii: n/a")


async def run(
    months: list[date] | None,
    apply: bool,
    *,
    effective_vat: bool = False,
) -> int:
    if apply and effective_vat:
        raise RuntimeError(
            "Promovarea TVA effective-dated este blocata; genereaza si verifica shadow provenance."
        )
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL lipseste din .env")
    connection = await asyncpg.connect(database_url)
    try:
        actual, sales_rows, salary_rows, stores = await load_data(
            connection,
            effective_vat=effective_vat,
        )
        ruleset_id = STANDARD_VAT_RULESET_ID if effective_vat else LEGACY_VAT_RULESET_ID
        model_version = EFFECTIVE_MODEL_VERSION if effective_vat else LEGACY_MODEL_VERSION
        print(f"Vanzari Retail normalizate read-only cu registrul {ruleset_id}.")
        backtest(actual, sales_rows, salary_rows, stores)
        targets = all_missing_targets(actual, sales_rows)
        if months is not None:
            targets = {target for target in targets if target[1] in months}
        estimates = build_estimates(actual, sales_rows, salary_rows, stores, targets, causal=False)
        scopes = estimate_replacement_scopes(targets)
        periods = sorted({period for _, period, _ in targets})
        print(f"Estimari generate: {len(estimates)} valori pentru {len(periods)} luni ({periods[0]:%Y-%m}..{periods[-1]:%Y-%m})" if periods else "Nu exista luni de estimat.")
        if apply and scopes:
            if effective_vat:
                digest = hashlib.sha256(
                    f"{model_version}:{standard_vat_ruleset_hash()}".encode()
                ).hexdigest()
            else:
                digest = hashlib.sha256(model_version.encode()).hexdigest()
            async with connection.transaction():
                for company, period in scopes:
                    await connection.execute(
                        """
                        DELETE FROM store_pnl_monthly
                        WHERE data_kind = 'estimated'
                          AND company_name = $1
                          AND period = $2
                        """,
                        company,
                        period,
                    )
                if estimates:
                    await connection.executemany(
                        """
                        INSERT INTO store_pnl_monthly (company_name, period, source_site_code, source_location_name,
                            category_code, category_name, amount, data_kind, source_file, source_sha256)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,'estimated',$8,$9)
                        """,
                        [(x.company_name, x.period, x.source_site_code, x.source_location_name, x.category_code,
                          x.category_name, x.amount,
                          f"model:{model_version}:{ruleset_id}:historical-reconstruction",
                          digest) for x in estimates],
                    )
            print("Au fost scrise numai randuri P&L estimate; tabelele de vanzari nu au fost modificate.")
        return 0
    finally:
        await connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconstruieste P&L-ul lipsa din istoricul Retail.")
    parser.add_argument("--months", nargs="+", help="Optional: numai lunile YYYY-MM cerute.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--effective-vat", action="store_true", help="Genereaza candidatul shadow cu registry-ul TVA effective-dated.")
    args = parser.parse_args()
    load_dotenv(REPO_DIR / ".env")
    return asyncio.run(
        run(
            [month_date(value) for value in args.months] if args.months else None,
            args.apply,
            effective_vat=args.effective_vat,
        )
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"EROARE: {exc}", file=sys.stderr)
        raise SystemExit(1)
