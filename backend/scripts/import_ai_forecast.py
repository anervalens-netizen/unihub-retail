from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Literal

import asyncpg
from dotenv import find_dotenv, load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from business_clock import business_now


MetricName = Literal["sales_value", "units"]


def month_dates(month: str) -> list[date]:
    year, month_number = map(int, month.split("-"))
    start = date(year, month_number, 1)
    if month_number == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month_number + 1, 1)
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days)]


def metric_value(value: Decimal, metric: MetricName) -> Decimal:
    quantizer = Decimal("1") if metric == "units" else Decimal("0.01")
    return value.quantize(quantizer, rounding=ROUND_HALF_UP)


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
    metric: MetricName,
) -> dict[str, list[tuple[date, Decimal]]]:
    forecast_dates = month_dates(forecast_month)
    metric_column = "total_quantity" if metric == "units" else "total_sales"
    rows = await conn.fetch(
        f"""
        SELECT site_code, sale_date, COALESCE(SUM({metric_column}), 0)::NUMERIC(14, 2) AS total_metric
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
        by_site_day[row["site_code"]][row["sale_date"]] = row["total_metric"]

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


def load_forecast_rows(args: argparse.Namespace) -> list[dict[str, str]]:
    forecast_rows: list[dict[str, str]] = []
    with Path(args.csv).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            row_metric = row.get("metric")
            if row_metric and row_metric != args.metric:
                continue
            if row.get("target_month"):
                target_month = row["target_month"]
                if args.start_month and target_month < args.start_month:
                    continue
                if args.end_month and target_month > args.end_month:
                    continue
                forecast_value = row.get("forecast") or row.get("forecast_sales")
                if forecast_value is None:
                    continue
                forecast_rows.append(
                    {
                        **row,
                        "target_month": target_month,
                        "forecast": forecast_value,
                    }
                )
            elif row.get("scenario") == args.scenario and row.get("mode") == args.mode:
                if not args.forecast_month:
                    raise RuntimeError("--forecast-month este necesar pentru CSV-ul legacy fara target_month")
                forecast_rows.append(
                    {
                        **row,
                        "target_month": args.forecast_month,
                        "forecast": row["forecast"],
                    }
                )
    if not forecast_rows:
        raise RuntimeError("Nu am gasit randuri de forecast pentru filtrele cerute.")
    return forecast_rows


async def import_forecast(args: argparse.Namespace) -> int:
    load_dotenv(find_dotenv())
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL lipseste din .env")

    forecast_rows = load_forecast_rows(args)
    rows_by_month: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in forecast_rows:
        rows_by_month[row["target_month"]].append(row)

    conn = await asyncpg.connect(database_url)
    imported_run_ids: list[int] = []
    try:
        async with conn.transaction():
            for target_month in sorted(rows_by_month):
                month_rows = rows_by_month[target_month]
                site_codes = [row["site_code"] for row in month_rows]
                existing = await conn.fetchval(
                    """
                    SELECT id
                    FROM ai_forecast_runs
                    WHERE forecast_month = $1
                      AND model_name = $2
                      AND model_mode = $3
                      AND variant = $4
                      AND metric = $5
                      AND horizon = $6
                      AND status = 'completed'
                    ORDER BY generated_at DESC, id DESC
                    LIMIT 1
                    """,
                    target_month,
                    args.model_name,
                    args.mode,
                    args.variant,
                    args.metric,
                    args.horizon,
                )
                if existing and not args.replace:
                    print(f"Forecast existent pentru {target_month}: run_id={existing}. Foloseste --replace pentru reimport.")
                    imported_run_ids.append(int(existing))
                    continue
                if existing and args.replace:
                    await conn.execute("DELETE FROM ai_forecast_runs WHERE id = $1", existing)

                weights: dict[str, list[tuple[date, Decimal]]] = {}
                if args.horizon == "current_month":
                    weights = await fetch_daily_weights(
                        conn,
                        reference_month=args.daily_profile_month,
                        forecast_month=target_month,
                        site_codes=site_codes,
                        metric=args.metric,
                    )

                metadata: dict[str, Any] = {
                    "imported_from": str(Path(args.csv).resolve()),
                    "scenario": args.scenario,
                    "metric": args.metric,
                    "horizon": args.horizon,
                }
                if args.anchor_month:
                    metadata["anchor_month"] = args.anchor_month
                if args.horizon == "current_month":
                    metadata["daily_profile_month"] = args.daily_profile_month
                    metadata["daily_profile_method"] = "weekday_occurrence_share"

                source_month = args.source_month or month_rows[0].get("source_month") or ""
                if not source_month:
                    raise RuntimeError("--source-month lipseste si CSV-ul nu contine source_month")

                run_id = await conn.fetchval(
                    """
                    INSERT INTO ai_forecast_runs (
                        forecast_month, source_month, metric, horizon, model_name, model_mode,
                        variant, status, generated_at, metadata
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'completed', $8, $9::JSONB)
                    RETURNING id
                    """,
                    target_month,
                    source_month,
                    args.metric,
                    args.horizon,
                    args.model_name,
                    args.mode,
                    args.variant,
                    business_now(),
                    json.dumps(metadata),
                )
                for row in month_rows:
                    site_code = row["site_code"]
                    forecast_sales = metric_value(parse_decimal(row["forecast"]), args.metric)
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
                    if args.horizon == "current_month":
                        daily_allocations: list[tuple[date, Decimal]] = []
                        running = Decimal("0")
                        site_weights = weights[site_code]
                        for forecast_date, weight in site_weights[:-1]:
                            value = metric_value(forecast_sales * weight, args.metric)
                            running += value
                            daily_allocations.append((forecast_date, value))
                        daily_allocations.append((site_weights[-1][0], metric_value(forecast_sales - running, args.metric)))
                        await conn.executemany(
                            """
                            INSERT INTO ai_forecast_store_day (run_id, forecast_date, site_code, forecast_sales)
                            VALUES ($1, $2, $3, $4)
                            """,
                            [(run_id, forecast_date, site_code, value) for forecast_date, value in daily_allocations],
                        )
                imported_run_ids.append(int(run_id))
    finally:
        await conn.close()

    print(f"Importat forecast AI run_ids={imported_run_ids}, randuri={len(forecast_rows)}")
    return imported_run_ids[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa un forecast AI lunar in tabelele Retail.")
    parser.add_argument("--csv", required=True, help="CSV-ul cu randuri per magazin")
    parser.add_argument("--forecast-month", default=None)
    parser.add_argument("--start-month", default=None)
    parser.add_argument("--end-month", default=None)
    parser.add_argument("--source-month", default=None)
    parser.add_argument("--anchor-month", default=None)
    parser.add_argument("--metric", choices=["sales_value", "units"], default="sales_value")
    parser.add_argument("--horizon", choices=["current_month", "rolling_12m"], default="current_month")
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
