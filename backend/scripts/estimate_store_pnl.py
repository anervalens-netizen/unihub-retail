#!/usr/bin/env python3
"""Backtest si estimare P&L pentru lunile fara fisier Finance.

Modelul foloseste raporturi istorice per magazin fata de vanzarile Retail,
raportul cost salarial P&L / salariu net si mediane recente pentru costurile fixe.
Estimarea nu inlocuieste niciodata randurile ``actual``.
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

import asyncpg
from dotenv import load_dotenv

REPO_DIR = Path(__file__).resolve().parents[2]
MODEL_VERSION = "store-pnl-estimator-v1"
VARIABLE_CODES = {"v1", "v11", "v2", "v3", "c1", "c11", "c2"}
FIXED_CODES = {"c4", "c5", "c6", "a1"}
VALID_CODES = VARIABLE_CODES | FIXED_CODES | {"c3"}


@dataclass(frozen=True)
class Estimate:
    company_name: str
    period: date
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


def recent(values: list[tuple[date, float]], target: date, limit: int = 12) -> list[float]:
    return [value for period, value in sorted((x for x in values if x[0] < target), reverse=True)[:limit]]


def predict_amount(
    category: str,
    target: date,
    history: list[tuple[date, float]],
    sales_history: dict[date, float],
    salary_history: dict[date, float],
    target_sales: float,
    target_salary: float,
) -> float | None:
    prior = recent(history, target)
    if not prior:
        return None
    if category in VARIABLE_CODES:
        ratios = [amount / sales_history[period] for period, amount in history if period < target and sales_history.get(period, 0) > 0]
        ratios = ratios[-12:]
        return statistics.median(ratios) * target_sales if ratios and target_sales > 0 else statistics.median(prior[:3])
    if category == "c3":
        ratios = [amount / salary_history[period] for period, amount in history if period < target and salary_history.get(period, 0) > 0]
        ratios = ratios[-12:]
        if ratios and target_salary > 0:
            return statistics.median(ratios) * target_salary
        return statistics.median(prior[:3])
    if category in FIXED_CODES:
        prior_year = next((amount for period, amount in history if period.year == target.year - 1 and period.month == target.month), None)
        recent_median = statistics.median(prior[:3])
        return (prior_year + recent_median) / 2 if prior_year is not None else recent_median
    return None


async def load_data(connection: asyncpg.Connection):
    actual = await connection.fetch(
        """
        SELECT p.company_name, p.period, p.source_site_code, p.source_location_name,
               p.category_code, p.category_name, p.amount, l.site_code
        FROM store_pnl_monthly p
        JOIN store_pnl_site_links l USING (company_name, source_site_code)
        WHERE p.data_kind = 'actual'
        ORDER BY p.period
        """
    )
    sales_rows = await connection.fetch(
        """
        SELECT to_date(import_month || '-01', 'YYYY-MM-DD') AS period, site_code,
               sum(total_sales)::float8 AS amount
        FROM reporting_agent_month GROUP BY import_month, site_code
        """
    )
    salary_rows = await connection.fetch(
        """
        SELECT make_date(year, month, 1) AS period, site_code,
               sum(total_salary)::float8 AS amount
        FROM salary_records WHERE site_code IS NOT NULL GROUP BY year, month, site_code
        """
    )
    return actual, sales_rows, salary_rows


def build_estimates(actual, sales_rows, salary_rows, targets: list[date]) -> list[Estimate]:
    sales = {(row["period"], row["site_code"]): float(row["amount"]) for row in sales_rows}
    salaries = {(row["period"], row["site_code"]): float(row["amount"]) for row in salary_rows}
    histories: dict[tuple[str, str, str], list[tuple[date, float]]] = defaultdict(list)
    metadata: dict[tuple[str, str], tuple[str, str, str, date]] = {}
    for row in actual:
        key = (row["company_name"], row["site_code"], row["category_code"])
        histories[key].append((row["period"], float(row["amount"])))
        meta_key = (row["company_name"], row["site_code"])
        previous = metadata.get(meta_key)
        if previous is None or row["period"] >= previous[3]:
            metadata[meta_key] = (row["source_site_code"], row["source_location_name"], row["category_name"], row["period"])

    estimates: list[Estimate] = []
    for target in targets:
        target_sites = {site for period, site in sales if period == target and sales[(period, site)] > 0}
        for company, site_code in sorted(metadata):
            if site_code not in target_sites:
                continue
            source_code, location, _, _ = metadata[(company, site_code)]
            sales_history = {period: amount for (period, site), amount in sales.items() if site == site_code}
            salary_history = {period: amount for (period, site), amount in salaries.items() if site == site_code}
            for category in sorted(VALID_CODES):
                history = histories.get((company, site_code, category), [])
                if not history:
                    continue
                category_name = next(row["category_name"] for row in reversed(actual) if row["company_name"] == company and row["site_code"] == site_code and row["category_code"] == category)
                amount = predict_amount(
                    category, target, history, sales_history, salary_history,
                    sales.get((target, site_code), 0.0), salaries.get((target, site_code), 0.0),
                )
                if amount is not None:
                    estimates.append(Estimate(company, target, source_code, location, category, category_name, money(amount)))
    return estimates


def backtest(actual, sales_rows, salary_rows) -> None:
    actual_lookup = {
        (row["company_name"], row["period"], row["source_site_code"], row["category_code"]): float(row["amount"])
        for row in actual
    }
    periods = sorted({row["period"] for row in actual if date(2025, 1, 1) <= row["period"] <= date(2026, 4, 1)})
    predicted = build_estimates(actual, sales_rows, salary_rows, periods)
    totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in predicted:
        key = (row.company_name, row.period, row.source_site_code, row.category_code)
        if key not in actual_lookup:
            continue
        actual_amount = actual_lookup[key]
        totals[row.category_code][0] += abs(float(row.amount) - actual_amount)
        totals[row.category_code][1] += abs(actual_amount)
    print("Backtest 2025-01..2026-04 (WAPE):")
    overall_error = overall_actual = 0.0
    for category in sorted(totals):
        error, actual_total = totals[category]
        overall_error += error
        overall_actual += actual_total
        print(f"  {category}: {100 * error / actual_total:.1f}%" if actual_total else f"  {category}: n/a")
    print(f"  TOTAL categorii: {100 * overall_error / overall_actual:.1f}%")


async def run(targets: list[date], apply: bool) -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL lipseste din .env")
    connection = await asyncpg.connect(database_url)
    try:
        actual, sales_rows, salary_rows = await load_data(connection)
        backtest(actual, sales_rows, salary_rows)
        estimates = build_estimates(actual, sales_rows, salary_rows, targets)
        print(f"Estimari generate: {len(estimates)} pentru {', '.join(f'{x:%Y-%m}' for x in targets)}")
        for target in targets:
            target_rows = [row for row in estimates if row.period == target]
            print(f"  {target:%Y-%m}: {len(target_rows)} valori, {len({(x.company_name, x.source_site_code) for x in target_rows})} magazine")
        if apply:
            digest = hashlib.sha256(MODEL_VERSION.encode()).hexdigest()
            async with connection.transaction():
                await connection.execute("DELETE FROM store_pnl_monthly WHERE data_kind = 'estimated' AND period = ANY($1::date[])", targets)
                await connection.executemany(
                    """
                    INSERT INTO store_pnl_monthly (
                        company_name, period, source_site_code, source_location_name,
                        category_code, category_name, amount, data_kind, source_file, source_sha256
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,'estimated',$8,$9)
                    """,
                    [(x.company_name, x.period, x.source_site_code, x.source_location_name, x.category_code, x.category_name, x.amount, f"model:{MODEL_VERSION}", digest) for x in estimates],
                )
            print("Estimarile au fost salvate separat de valorile actuale.")
        else:
            print("Dry-run: estimarile nu au fost scrise.")
        return 0
    finally:
        await connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest si estimare P&L.")
    parser.add_argument("--months", nargs="+", default=["2025-11", "2025-12", "2026-05"])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(REPO_DIR / ".env")
    return asyncio.run(run([month_date(value) for value in args.months], args.apply))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"EROARE: {exc}", file=sys.stderr)
        raise SystemExit(1)