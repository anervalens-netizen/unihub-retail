from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import asyncpg
from dotenv import find_dotenv, load_dotenv


def month_dates(month: str) -> list[date]:
    year, month_number = map(int, month.split("-"))
    start = date(year, month_number, 1)
    if month_number == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month_number + 1, 1)
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days)]


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_decimal(value: str | None) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def weekday_occurrence(day: date) -> int:
    occurrence = 0
    for month_day in month_dates(day.strftime("%Y-%m")):
        if month_day > day:
            break
        if month_day.weekday() == day.weekday():
            occurrence += 1
    return occurrence


async def fetch_daily_weights(
    conn: asyncpg.Connection,
    *,
    reference_month: str,
    forecast_month: str,
    site_codes: list[str],
) -> dict[str, list[tuple[date, Decimal]]]:
    forecast_dates = month_dates(forecast_month)
    rows = await conn.fetch(
        """
        SELECT site_code, sale_date, COALESCE(SUM(total_sales), 0)::NUMERIC(14, 2) AS total_sales
        FROM reporting_agent_day
        WHERE import_month = $1
          AND site_code = ANY($2::TEXT[])
        GROUP BY site_code, sale_date
        """,
        reference_month,
        site_codes,
    )
    by_site_day: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for row in rows:
        by_site_day[row["site_code"]][row["sale_date"]] = row["total_sales"]

    weights: dict[str, list[tuple[date, Decimal]]] = {}
    uniform = Decimal("1") / Decimal(len(forecast_dates))
    for site_code in site_codes:
        reference_values = by_site_day.get(site_code, {})
        if sum(reference_values.values(), Decimal("0")) <= 0:
            weights[site_code] = [(day, uniform) for day in forecast_dates]
            continue

        by_weekday_occurrence: dict[tuple[int, int], Decimal] = {}
        weekday_totals: dict[int, Decimal] = defaultdict(Decimal)
        weekday_counts: dict[int, int] = defaultdict(int)
        for reference_date, value in reference_values.items():
            weekday = reference_date.weekday()
            by_weekday_occurrence[(weekday, weekday_occurrence(reference_date))] = value
            weekday_totals[weekday] += value
            weekday_counts[weekday] += 1

        projected_values: list[tuple[date, Decimal]] = []
        for forecast_date in forecast_dates:
            weekday = forecast_date.weekday()
            occurrence = weekday_occurrence(forecast_date)
            projected = by_weekday_occurrence.get((weekday, occurrence))
            if projected is None and weekday_counts[weekday] > 0:
                projected = weekday_totals[weekday] / Decimal(weekday_counts[weekday])
            projected_values.append((forecast_date, projected or Decimal("0")))

        projected_total = sum((value for _, value in projected_values), Decimal("0"))
        if projected_total <= 0:
            weights[site_code] = [(day, uniform) for day in forecast_dates]
            continue

        site_weights: list[tuple[date, Decimal]] = []
        for forecast_date, value in projected_values:
            site_weights.append((forecast_date, value / projected_total))
        weights[site_code] = site_weights
    return weights


async def import_forecast(args: argparse.Namespace) -> int:
    load_dotenv(find_dotenv())
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL lipseste din .env")

    forecast_rows: list[dict[str, str]] = []
    with Path(args.csv).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("scenario") == args.scenario and row.get("mode") == args.mode:
                forecast_rows.append(row)
    if not forecast_rows:
        raise RuntimeError(f"Nu am gasit randuri pentru scenario={args.scenario!r}, mode={args.mode!r}")

    site_codes = [row["site_code"] for row in forecast_rows]
    conn = await asyncpg.connect(database_url)
    try:
        existing = await conn.fetchval(
            """
            SELECT id
            FROM ai_forecast_runs
            WHERE forecast_month = $1
              AND model_name = $2
              AND model_mode = $3
              AND variant = $4
              AND status = 'completed'
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            args.forecast_month,
            args.model_name,
            args.mode,
            args.variant,
        )
        if existing and not args.replace:
            print(f"Forecast existent: run_id={existing}. Foloseste --replace pentru reimport.")
            return int(existing)
        if existing and args.replace:
            await conn.execute("DELETE FROM ai_forecast_runs WHERE id = $1", existing)

        weights = await fetch_daily_weights(
            conn,
            reference_month=args.daily_profile_month,
            forecast_month=args.forecast_month,
            site_codes=site_codes,
        )
        async with conn.transaction():
            run_id = await conn.fetchval(
                """
                INSERT INTO ai_forecast_runs (
                    forecast_month, source_month, model_name, model_mode,
                    variant, status, generated_at, metadata
                )
                VALUES ($1, $2, $3, $4, $5, 'completed', $6, $7::JSONB)
                RETURNING id
                """,
                args.forecast_month,
                args.source_month,
                args.model_name,
                args.mode,
                args.variant,
                datetime.now(),
                json.dumps(
                    {
                        "imported_from": str(Path(args.csv).resolve()),
                        "scenario": args.scenario,
                        "daily_profile_month": args.daily_profile_month,
                        "daily_profile_method": "weekday_occurrence_share",
                    }
                ),
            )
            for row in forecast_rows:
                site_code = row["site_code"]
                forecast_sales = money(parse_decimal(row["forecast"]))
                await conn.execute(
                    """
                    INSERT INTO ai_forecast_store_month (run_id, site_code, forecast_sales, metadata)
                    VALUES ($1, $2, $3, $4::JSONB)
                    """,
                    run_id,
                    site_code,
                    forecast_sales,
                    json.dumps({"locatie": row.get("locatie"), "firma": row.get("firma")}),
                )
                daily_allocations: list[tuple[date, Decimal]] = []
                running = Decimal("0")
                site_weights = weights[site_code]
                for forecast_date, weight in site_weights[:-1]:
                    value = money(forecast_sales * weight)
                    running += value
                    daily_allocations.append((forecast_date, value))
                daily_allocations.append((site_weights[-1][0], money(forecast_sales - running)))
                await conn.executemany(
                    """
                    INSERT INTO ai_forecast_store_day (run_id, forecast_date, site_code, forecast_sales)
                    VALUES ($1, $2, $3, $4)
                    """,
                    [(run_id, forecast_date, site_code, value) for forecast_date, value in daily_allocations],
                )
    finally:
        await conn.close()

    print(f"Importat forecast AI run_id={run_id}, magazine={len(forecast_rows)}")
    return int(run_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa un forecast AI lunar in tabelele Retail.")
    parser.add_argument("--csv", required=True, help="CSV-ul cu randuri per magazin")
    parser.add_argument("--forecast-month", required=True)
    parser.add_argument("--source-month", required=True)
    parser.add_argument("--scenario", default="forecast_2026_07_june_scaled")
    parser.add_argument("--mode", default="xreg + timesfm")
    parser.add_argument("--variant", default="monthly_xreg_june_scaled")
    parser.add_argument("--model-name", default="timesfm-2.5-200m-pytorch")
    parser.add_argument("--daily-profile-month", default="2025-07")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    asyncio.run(import_forecast(args))


if __name__ == "__main__":
    main()
