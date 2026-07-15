#!/usr/bin/env python3
"""Reconstruieste lunile P&L lipsa, fara a modifica vanzarile Retail.

Vanzarile din ``historical_monthly_sales`` si ``reporting_agent_month`` sunt
citite exclusiv ca semnal pentru model. Ele sunt stocate cu TVA, iar modelul
lucreaza cu valoarea fara TVA (standard 19%), pentru a nu compara venituri P&L
cu vanzari brute. Valorile Finance ``actual`` au intotdeauna prioritate.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable

import asyncpg
from dotenv import load_dotenv

REPO_DIR = Path(__file__).resolve().parents[2]
MODEL_VERSION = "store-pnl-estimator-v2"
VAT_DIVISOR = 1.19
VARIABLE_CODES = {"v1", "v11", "v2", "v3", "c1", "c11", "c2"}
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


def money(value: float) -> Decimal:
    return Decimal(str(max(0.0, value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def median(values: Iterable[float]) -> float | None:
    items = list(values)
    return statistics.median(items) if items else None


def relevant_history(
    history: list[tuple[date, float]], target: date, *, causal: bool, limit: int = 12,
) -> list[tuple[date, float]]:
    eligible = [item for item in history if not causal or item[0] < target]
    return sorted(eligible, key=lambda item: abs((item[0] - target).days))[:limit]


def ratio_history(
    values: list[tuple[date, float]], bases: dict[date, float], target: date, *, causal: bool,
) -> list[tuple[date, float]]:
    return [
        (period, amount / bases[period])
        for period, amount in relevant_history(values, target, causal=causal)
        if bases.get(period, 0) > 0
    ]


def predict_amount(
    category: str,
    target: date,
    history: list[tuple[date, float]],
    sales_history: dict[date, float],
    salary_history: dict[date, float],
    target_sales: float,
    target_salary: float,
    *,
    causal: bool = False,
) -> float | None:
    """Estimate a value from one store history; kept small and unit-testable."""
    nearest = relevant_history(history, target, causal=causal)
    if not nearest:
        return None
    if category == "c3" and target_salary > 0:
        salary_ratios = ratio_history(history, salary_history, target, causal=causal)
        if salary_ratios:
            return median(ratio for _, ratio in salary_ratios) * target_salary
    if category in VARIABLE_CODES or category == "c3":
        sales_ratios = ratio_history(history, sales_history, target, causal=causal)
        if sales_ratios and target_sales > 0:
            return median(ratio for _, ratio in sales_ratios) * target_sales
    if category in FIXED_CODES:
        same_month = [amount for period, amount in nearest if period.month == target.month]
        return median(same_month) if same_month else median(amount for _, amount in nearest[:3])
    return median(amount for _, amount in nearest)


def aggregate_ratios(
    entries: list[tuple[date, float]],
) -> list[tuple[date, float]]:
    by_period: dict[date, list[float]] = defaultdict(list)
    for period, value in entries:
        by_period[period].append(value)
    return [(period, statistics.median(values)) for period, values in by_period.items()]


def choose_ratio(
    store_ratios: list[tuple[date, float]],
    company_ratios: list[tuple[date, float]],
    target: date,
    *,
    causal: bool,
) -> float | None:
    nearby_store = relevant_history(store_ratios, target, causal=causal)
    nearby_company = relevant_history(company_ratios, target, causal=causal)
    chosen = nearby_store if len(nearby_store) >= 2 else nearby_company
    return median(value for _, value in chosen)


async def load_data(connection: asyncpg.Connection):
    actual = await connection.fetch(
        """
        SELECT p.company_name, p.period, p.source_site_code, p.source_location_name,
               p.category_code, p.category_name, p.amount,
               COALESCE(l.site_code, p.source_site_code) AS site_code
        FROM store_pnl_monthly p
        LEFT JOIN store_pnl_site_links l USING (company_name, source_site_code)
        WHERE p.data_kind = 'actual'
        """
    )
    sales = await connection.fetch(
        """
        WITH sources AS (
            SELECT CASE WHEN firma ILIKE 'mobicell%' THEN 'Mobicell' ELSE 'Mobiup' END AS company_name,
                   to_date(import_month || '-01', 'YYYY-MM-DD') AS period,
                   site_code, (total_value / 1.19)::float8 AS amount_without_vat, 1 AS priority
            FROM historical_monthly_sales
            UNION ALL
            SELECT CASE WHEN firma ILIKE 'mobicell%' THEN 'Mobicell' ELSE 'Mobiup' END,
                   to_date(import_month || '-01', 'YYYY-MM-DD'), site_code,
                   (SUM(total_sales) / 1.19)::float8, 2
            FROM reporting_agent_month GROUP BY firma, import_month, site_code
        ), preferred AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY company_name, period, site_code ORDER BY priority DESC
            ) AS preference_rank FROM sources
        )
        SELECT company_name, period, site_code, amount_without_vat AS amount
        FROM preferred WHERE preference_rank = 1
        """
    )
    salaries = await connection.fetch(
        """
        SELECT CASE WHEN company_name ILIKE 'mobicell%' THEN 'Mobicell' ELSE 'Mobiup' END AS company_name,
               make_date(year, month, 1) AS period, site_code, SUM(total_salary)::float8 AS amount
        FROM salary_records WHERE site_code IS NOT NULL GROUP BY company_name, year, month, site_code
        """
    )
    stores = await connection.fetch("SELECT site_code, locatie, firma FROM stores")
    return actual, sales, salaries, stores


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
    sales = {(row["company_name"], row["period"], row["site_code"]): float(row["amount"]) for row in sales_rows}
    salaries = {(row["company_name"], row["period"], row["site_code"]): float(row["amount"]) for row in salary_rows}
    store_lookup = {row["site_code"]: row for row in stores}
    actual_index = {(row["company_name"], row["period"], row["site_code"], row["category_code"]) for row in actual}
    store_history: dict[tuple[str, str, str], list[tuple[date, float]]] = defaultdict(list)
    company_values: dict[tuple[str, str], list[tuple[date, float]]] = defaultdict(list)
    store_sales_ratios: dict[tuple[str, str, str], list[tuple[date, float]]] = defaultdict(list)
    company_sales_ratios: dict[tuple[str, str], list[tuple[date, float]]] = defaultdict(list)
    store_salary_ratios: dict[tuple[str, str, str], list[tuple[date, float]]] = defaultdict(list)
    company_salary_ratios: dict[tuple[str, str], list[tuple[date, float]]] = defaultdict(list)
    metadata: dict[tuple[str, str], tuple[date, str, str]] = {}
    category_names = dict(CATEGORY_NAMES)

    for row in actual:
        company, period, site_code, category = row["company_name"], row["period"], row["site_code"], row["category_code"]
        amount = float(row["amount"])
        key = (company, site_code, category)
        store_history[key].append((period, amount))
        company_values[(company, category)].append((period, amount))
        sales_value = sales.get((company, period, site_code), 0)
        if sales_value > 0:
            store_sales_ratios[key].append((period, amount / sales_value))
            company_sales_ratios[(company, category)].append((period, amount / sales_value))
        salary_value = salaries.get((company, period, site_code), 0)
        if salary_value > 0:
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
        _, source_code, location = metadata.get((company, site_code), (target, site_code, store["locatie"]))
        target_sales = sales.get((company, target, site_code), 0.0)
        target_salary = salaries.get((company, target, site_code), 0.0)
        if target_sales <= 0:
            continue
        for category in sorted(VALID_CODES):
            if not include_actual_targets and (company, target, site_code, category) in actual_index:
                continue
            key = (company, site_code, category)
            store_values = store_history.get(key, [])
            if category == "c3" and target_salary > 0:
                ratio = choose_ratio(store_salary_ratios.get(key, []), company_salary_ratios.get((company, category), []), target, causal=causal)
                amount = ratio * target_salary if ratio is not None else None
            elif category in VARIABLE_CODES or category == "c3":
                ratio = choose_ratio(store_sales_ratios.get(key, []), company_sales_ratios.get((company, category), []), target, causal=causal)
                amount = ratio * target_sales if ratio is not None else None
            else:
                values = relevant_history(store_values, target, causal=causal)
                fallback = relevant_history(company_values.get((company, category), []), target, causal=causal)
                chosen = values if len(values) >= 2 else fallback
                same_month = [value for period, value in chosen if period.month == target.month]
                amount = median(same_month) if same_month else median(value for _, value in chosen[:3])
            if amount is not None:
                estimates.append(Estimate(company, target, site_code, source_code, location, category, category_names[category], money(amount)))
    return estimates


def all_missing_targets(sales_rows) -> set[tuple[str, date, str]]:
    today = date.today().replace(day=1)
    return {
        (row["company_name"], row["period"], row["site_code"])
        for row in sales_rows
        if date(2018, 1, 1) <= row["period"] < today and float(row["amount"]) > 0
    }


def backtest(actual, sales_rows, salary_rows, stores) -> None:
    actual_lookup = {(row["company_name"], row["period"], row["site_code"], row["category_code"]): float(row["amount"]) for row in actual}
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
    totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in predicted:
        actual_amount = actual_lookup.get((row.company_name, row.period, row.site_code, row.category_code))
        if actual_amount is None:
            continue
        totals[row.category_code][0] += abs(float(row.amount) - actual_amount)
        totals[row.category_code][1] += abs(actual_amount)
    overall_error = sum(error for error, _ in totals.values())
    overall_actual = sum(total for _, total in totals.values())
    print("Backtest cauzal 2025-01..2026-04 (WAPE):")
    for category in sorted(totals):
        error, total = totals[category]
        print(f"  {category}: {100 * error / total:.1f}%" if total else f"  {category}: n/a")
    print(f"  TOTAL categorii: {100 * overall_error / overall_actual:.1f}%" if overall_actual else "  TOTAL categorii: n/a")


async def run(months: list[date] | None, apply: bool) -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL lipseste din .env")
    connection = await asyncpg.connect(database_url)
    try:
        actual, sales_rows, salary_rows, stores = await load_data(connection)
        print(f"Vanzari Retail citite read-only, normalizate fara TVA (impartire la {VAT_DIVISOR:.2f}).")
        backtest(actual, sales_rows, salary_rows, stores)
        targets = all_missing_targets(sales_rows)
        if months is not None:
            targets = {target for target in targets if target[1] in months}
        estimates = build_estimates(actual, sales_rows, salary_rows, stores, targets, causal=False)
        periods = sorted({period for _, period, _ in targets})
        print(f"Estimari generate: {len(estimates)} valori pentru {len(periods)} luni ({periods[0]:%Y-%m}..{periods[-1]:%Y-%m})" if periods else "Nu exista luni de estimat.")
        if apply and periods:
            digest = hashlib.sha256(MODEL_VERSION.encode()).hexdigest()
            async with connection.transaction():
                await connection.execute("DELETE FROM store_pnl_monthly WHERE data_kind = 'estimated' AND period = ANY($1::date[])", periods)
                if estimates:
                    await connection.executemany(
                        """
                        INSERT INTO store_pnl_monthly (company_name, period, source_site_code, source_location_name,
                            category_code, category_name, amount, data_kind, source_file, source_sha256)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,'estimated',$8,$9)
                        """,
                        [(x.company_name, x.period, x.source_site_code, x.source_location_name, x.category_code,
                          x.category_name, x.amount, f"model:{MODEL_VERSION}:historical-reconstruction", digest) for x in estimates],
                    )
            print("Au fost scrise numai randuri P&L estimate; tabelele de vanzari nu au fost modificate.")
        return 0
    finally:
        await connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconstruieste P&L-ul lipsa din istoricul Retail.")
    parser.add_argument("--months", nargs="+", help="Optional: numai lunile YYYY-MM cerute.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(REPO_DIR / ".env")
    return asyncio.run(run([month_date(value) for value in args.months] if args.months else None, args.apply))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"EROARE: {exc}", file=sys.stderr)
        raise SystemExit(1)
