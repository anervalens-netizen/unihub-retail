from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import urllib.error
import urllib.request
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import asyncpg
from dotenv import load_dotenv
from services.spreadsheet_safety import csv_cell_value


DEFAULT_API_URL = "http://100.74.73.114:8000/forecast_xreg"
DEFAULT_OUTPUT_DIR = Path("backend/outputs/ai_forecast")
MIN_CONTEXT = 33
DEFAULT_EXCLUDED_SITE_CODES = ["CRFVUL", "CRFARENA"]
MetricName = Literal["sales_value", "units"]
FeatureProfile = Literal["v1", "v2", "v3"]


@dataclass(frozen=True)
class StoreInfo:
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str


def add_month(month: str, offset: int) -> str:
    year, month_number = map(int, month.split("-"))
    month_index = year * 12 + (month_number - 1) + offset
    return f"{month_index // 12:04d}-{month_index % 12 + 1:02d}"


def month_range(start: str, end: str) -> list[str]:
    months: list[str] = []
    current = start
    while current <= end:
        months.append(current)
        current = add_month(current, 1)
    return months


def month_distance(start: str, end: str) -> int:
    start_year, start_month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    return (end_year - start_year) * 12 + (end_month - start_month)


def season_name(month_number: int) -> str:
    if month_number in (12, 1, 2):
        return "winter"
    if month_number in (3, 4, 5):
        return "spring"
    if month_number in (6, 7, 8):
        return "summer"
    return "autumn"


def price_regime(month: str) -> str:
    if month == "2025-08":
        return "price_transition"
    if month >= "2025-09":
        return "post_price_change"
    return "pre_price_change"


def store_age_bucket(context_months: int) -> str:
    if context_months < 12:
        return "lt_12m"
    if context_months < 24:
        return "12_23m"
    if context_months < 48:
        return "24_47m"
    return "48m_plus"


def covariate_schema(profile: FeatureProfile) -> tuple[list[str], list[str], list[str]]:
    if profile == "v1":
        return (
            ["month", "quarter", "year"],
            ["year_index", "month_number", "quarter_number", "days_in_month", "month_sin", "month_cos"],
            ["firma", "regional", "asm"],
        )
    if profile == "v3":
        return (
            ["month", "quarter", "year", "season"],
            [
                "year_index",
                "month_number",
                "quarter_number",
                "days_in_month",
                "month_sin",
                "month_cos",
                "is_summer",
                "is_december",
                "is_january",
                "is_q4",
                "is_peak_season",
                "month_in_quarter",
                "months_since_opening",
            ],
            ["firma", "regional", "asm", "store_age_bucket"],
        )
    return (
        ["month", "quarter", "season", "price_regime"],
        [
            "year_index",
            "month_number",
            "quarter_number",
            "days_in_month",
            "month_sin",
            "month_cos",
            "is_summer",
            "is_december",
            "is_january",
            "is_q4",
            "is_peak_season",
            "month_in_quarter",
            "months_since_opening",
            "is_post_price_change",
        ],
        ["firma", "regional", "asm", "store_age_bucket"],
    )


def month_features(
    months: list[str],
    base_year: int,
    *,
    first_input_month: str | None = None,
) -> dict[str, list[Any]]:
    features: dict[str, list[Any]] = {
        "month": [],
        "quarter": [],
        "year": [],
        "year_index": [],
        "month_number": [],
        "quarter_number": [],
        "days_in_month": [],
        "month_sin": [],
        "month_cos": [],
        "season": [],
        "price_regime": [],
        "is_summer": [],
        "is_december": [],
        "is_january": [],
        "is_q4": [],
        "is_peak_season": [],
        "month_in_quarter": [],
        "months_since_opening": [],
        "is_post_price_change": [],
    }
    for month in months:
        year, month_number = map(int, month.split("-"))
        quarter = (month_number - 1) // 3 + 1
        days = monthrange(year, month_number)[1]
        angle = 2 * math.pi * (month_number - 1) / 12
        features["month"].append(f"M{month_number:02d}")
        features["quarter"].append(f"Q{quarter}")
        features["year"].append(str(year))
        features["year_index"].append(float(year - base_year))
        features["month_number"].append(float(month_number))
        features["quarter_number"].append(float(quarter))
        features["days_in_month"].append(float(days))
        features["month_sin"].append(math.sin(angle))
        features["month_cos"].append(math.cos(angle))
        features["season"].append(season_name(month_number))
        features["price_regime"].append(price_regime(month))
        features["is_summer"].append(float(month_number in (6, 7, 8)))
        features["is_december"].append(float(month_number == 12))
        features["is_january"].append(float(month_number == 1))
        features["is_q4"].append(float(quarter == 4))
        features["is_peak_season"].append(float(month_number in (7, 8, 12)))
        features["month_in_quarter"].append(float((month_number - 1) % 3 + 1))
        features["months_since_opening"].append(
            float(month_distance(first_input_month, month) + 1) if first_input_month else 0.0
        )
        features["is_post_price_change"].append(float(price_regime(month) == "post_price_change"))
    return features


def metric_value(value: Any, metric: MetricName) -> Decimal:
    quantizer = Decimal("1") if metric == "units" else Decimal("0.01")
    return Decimal(str(value)).quantize(quantizer)


def pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (numerator / denominator * Decimal("100")).quantize(Decimal("0.01"))


async def fetch_active_stores(conn: asyncpg.Connection, *, excluded_site_codes: list[str]) -> list[StoreInfo]:
    rows = await conn.fetch(
        """
        SELECT site_code, locatie, firma, regional, asm
        FROM stores
        WHERE is_active = true
          AND locatie NOT ILIKE 'TR %'
          AND NOT (site_code = ANY($1::TEXT[]))
        ORDER BY regional, locatie, site_code
        """,
        excluded_site_codes,
    )
    return [
        StoreInfo(
            site_code=row["site_code"],
            locatie=row["locatie"],
            firma=row["firma"],
            regional=row["regional"],
            asm=row["asm"],
        )
        for row in rows
    ]


async def fetch_monthly_sales(
    conn: asyncpg.Connection,
    *,
    site_codes: list[str],
    start_month: str,
    end_month: str,
    metric: MetricName,
) -> dict[tuple[str, str], Decimal]:
    reporting_column = "total_quantity" if metric == "units" else "total_sales"
    historical_column = "total_qty" if metric == "units" else "total_value"
    rows = await conn.fetch(
        f"""
        WITH sales AS (
            SELECT import_month, site_code, SUM({reporting_column})::NUMERIC(14, 2) AS total_metric
            FROM reporting_agent_month
            WHERE site_code = ANY($1::TEXT[])
              AND import_month BETWEEN $2 AND $3
            GROUP BY import_month, site_code
        ),
        historical AS (
            SELECT hms.import_month, hms.site_code, SUM(hms.{historical_column})::NUMERIC(14, 2) AS total_metric
            FROM historical_monthly_sales hms
            WHERE hms.site_code = ANY($1::TEXT[])
              AND hms.import_month BETWEEN $2 AND $3
              AND NOT EXISTS (
                  SELECT 1
                  FROM sales s
                  WHERE s.import_month = hms.import_month
                    AND s.site_code = hms.site_code
              )
            GROUP BY hms.import_month, hms.site_code
        )
        SELECT import_month, site_code, total_metric
        FROM sales
        UNION ALL
        SELECT import_month, site_code, total_metric
        FROM historical
        """,
        site_codes,
        start_month,
        end_month,
    )
    return {(row["site_code"], row["import_month"]): row["total_metric"] for row in rows}


def build_payload(
    *,
    stores: list[StoreInfo],
    sales: dict[tuple[str, str], Decimal],
    target_months: list[str],
    source_month: str,
    history_start_month: str,
    min_context: int,
    metric: MetricName,
    feature_profile: FeatureProfile = "v1",
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    full_history = month_range(history_start_month, source_month)
    base_year = int(history_start_month[:4])
    dynamic_categorical_names, dynamic_numerical_names, static_categorical_names = covariate_schema(feature_profile)

    inputs: list[list[float]] = []
    series_ids: list[str] = []
    dynamic_categorical: dict[str, list[list[Any]]] = {name: [] for name in dynamic_categorical_names}
    dynamic_numerical: dict[str, list[list[float]]] = {name: [] for name in dynamic_numerical_names}
    static_categorical: dict[str, list[str]] = {name: [] for name in static_categorical_names}
    rows_meta: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for store in stores:
        values = [metric_value(sales.get((store.site_code, month), Decimal("0")), metric) for month in full_history]
        first_non_zero = next((idx for idx, value in enumerate(values) if value > 0), None)
        if first_non_zero is None:
            skipped.append({"site_code": store.site_code, "reason": "no_history"})
            continue

        context_months = full_history[first_non_zero:]
        context_values = values[first_non_zero:]
        if len(context_values) < min_context:
            skipped.append(
                {
                    "site_code": store.site_code,
                    "reason": f"context_lt_{min_context}",
                    "context_months": str(len(context_values)),
                }
            )
            continue

        covariate_months = context_months + target_months
        features = month_features(covariate_months, base_year, first_input_month=context_months[0])

        series_ids.append(store.site_code)
        inputs.append([float(value) for value in context_values])
        for name in dynamic_categorical_names:
            dynamic_categorical[name].append(features[name])
        for name in dynamic_numerical_names:
            dynamic_numerical[name].append([float(value) for value in features[name]])
        static_categorical["firma"].append(store.firma)
        static_categorical["regional"].append(store.regional)
        static_categorical["asm"].append(store.asm)
        if "store_age_bucket" in static_categorical:
            static_categorical["store_age_bucket"].append(store_age_bucket(len(context_values)))
        rows_meta.append(
            {
                "site_code": store.site_code,
                "locatie": store.locatie,
                "firma": store.firma,
                "regional": store.regional,
                "asm": store.asm,
                "first_input_month": context_months[0],
                "source_month": source_month,
                "context_months": len(context_values),
            }
        )

    payload = {
        "horizon": len(target_months),
        "inputs": inputs,
        "series_ids": series_ids,
        "dynamic_categorical_covariates": dynamic_categorical,
        "dynamic_numerical_covariates": dynamic_numerical,
        "static_categorical_covariates": static_categorical,
        "xreg_mode": "xreg + timesfm",
        "feature_profile": feature_profile,
    }
    return payload, rows_meta, skipped


def post_forecast(api_url: str, api_key: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"TimesFM HTTP {exc.code}: {detail}") from exc


def parse_predictions(response: dict[str, Any], *, metric: MetricName) -> dict[str, list[Decimal]]:
    predictions: dict[str, list[Decimal]] = {}
    for row in response.get("series", []):
        values = row.get("point_forecast") or []
        if values:
            predictions[str(row["series_id"])] = [metric_value(value, metric) for value in values]
    return predictions


def build_result_rows(
    *,
    target_months: list[str],
    meta_rows: list[dict[str, Any]],
    actuals: dict[tuple[str, str], Decimal],
    predictions: dict[str, list[Decimal]],
    metric: MetricName,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for meta in meta_rows:
        site_code = meta["site_code"]
        site_predictions = predictions.get(site_code)
        if not site_predictions:
            continue
        for index, target_month in enumerate(target_months):
            if index >= len(site_predictions):
                break
            forecast = site_predictions[index]
            actual = metric_value(actuals.get((site_code, target_month), Decimal("0")), metric)
            error = forecast - actual
            abs_error = abs(error)
            rows.append(
                {
                    **meta,
                    "metric": metric,
                    "target_month": target_month,
                    "method": "model_xreg",
                    "actual_sales": actual,
                    "forecast_sales": forecast,
                    "error_sales": error,
                    "abs_error_sales": abs_error,
                    "error_pct": pct(error, actual),
                    "abs_error_pct": pct(abs_error, actual),
                }
            )
    return rows


def seasonal_last3_fallback(
    *,
    site_code: str,
    target_month: str,
    sales: dict[tuple[str, str], Decimal],
    site_codes: list[str],
    metric: MetricName,
    known_values: dict[tuple[str, str], Decimal] | None = None,
    max_reference_month: str | None = None,
) -> tuple[Decimal, str]:
    known_values = known_values or {}

    def get_value(code: str, month: str) -> Decimal:
        return metric_value(known_values.get((code, month), sales.get((code, month), Decimal("0"))), metric)

    prior_months = [add_month(target_month, offset) for offset in (-3, -2, -1)]
    store_values = [get_value(site_code, month) for month in prior_months]
    positive_values = [value for value in store_values if value > 0]
    if not positive_values:
        return Decimal("0"), "fallback_zero_history"

    reference_month = add_month(target_month, -12)
    while max_reference_month is not None and reference_month > max_reference_month:
        reference_month = add_month(reference_month, -12)
    reference_prior_months = [add_month(reference_month, offset) for offset in (-3, -2, -1)]
    reference_total = sum(
        (metric_value(sales.get((code, reference_month), Decimal("0")), metric) for code in site_codes),
        Decimal("0"),
    )
    reference_prior_total = sum(
        (
            metric_value(sales.get((code, month), Decimal("0")), metric)
            for code in site_codes
            for month in reference_prior_months
        ),
        Decimal("0"),
    )
    reference_prior_average = reference_prior_total / Decimal(len(reference_prior_months))
    seasonal_multiplier = Decimal("1")
    if reference_total > 0 and reference_prior_average > 0:
        seasonal_multiplier = reference_total / reference_prior_average

    store_average = sum(positive_values, Decimal("0")) / Decimal(len(positive_values))
    return metric_value(store_average * seasonal_multiplier, metric), "fallback_seasonal_last3"


def build_fallback_rows(
    *,
    target_month: str,
    stores: list[StoreInfo],
    existing_site_codes: set[str],
    sales: dict[tuple[str, str], Decimal],
    metric: MetricName,
    known_values: dict[tuple[str, str], Decimal] | None = None,
    source_month: str | None = None,
    max_reference_month: str | None = None,
) -> list[dict[str, Any]]:
    site_codes = [store.site_code for store in stores]
    rows: list[dict[str, Any]] = []
    for store in stores:
        if store.site_code in existing_site_codes:
            continue
        forecast, method = seasonal_last3_fallback(
            site_code=store.site_code,
            target_month=target_month,
            sales=sales,
            site_codes=site_codes,
            metric=metric,
            known_values=known_values,
            max_reference_month=max_reference_month,
        )
        actual = metric_value(sales.get((store.site_code, target_month), Decimal("0")), metric)
        error = forecast - actual
        abs_error = abs(error)
        rows.append(
            {
                "metric": metric,
                "target_month": target_month,
                "source_month": source_month or add_month(target_month, -1),
                "site_code": store.site_code,
                "locatie": store.locatie,
                "firma": store.firma,
                "regional": store.regional,
                "asm": store.asm,
                "first_input_month": "",
                "context_months": 0,
                "method": method,
                "actual_sales": actual,
                "forecast_sales": forecast,
                "error_sales": error,
                "abs_error_sales": abs_error,
                "error_pct": pct(error, actual),
                "abs_error_pct": pct(abs_error, actual),
            }
        )
    return rows


def summarize_month(target_month: str, rows: list[dict[str, Any]], model_skipped_count: int) -> dict[str, Any]:
    actual = sum((row["actual_sales"] for row in rows), Decimal("0"))
    forecast = sum((row["forecast_sales"] for row in rows), Decimal("0"))
    error = forecast - actual
    abs_error = sum((row["abs_error_sales"] for row in rows), Decimal("0"))
    model_rows = sum(1 for row in rows if row["method"] == "model_xreg")
    fallback_rows = len(rows) - model_rows
    return {
        "target_month": target_month,
        "stores_forecasted": len(rows),
        "stores_model": model_rows,
        "stores_fallback": fallback_rows,
        "stores_model_skipped": model_skipped_count,
        "actual_sales": actual,
        "forecast_sales": forecast,
        "error_sales": error,
        "bias_pct": pct(error, actual),
        "wape_pct": pct(abs_error, actual),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_cell_value(row.get(key)) for key in fieldnames})


async def run(args: argparse.Namespace) -> int:
    load_dotenv(args.env_file)
    database_url = os.environ.get("DATABASE_URL")
    api_key = args.api_key or os.environ.get("TIMESFM_API_KEY")
    if not database_url:
        raise RuntimeError("DATABASE_URL lipseste.")
    if not api_key:
        raise RuntimeError("TIMESFM_API_KEY lipseste.")

    target_months = month_range(args.start_month, args.end_month)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    conn = await asyncpg.connect(database_url)
    all_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    try:
        stores = await fetch_active_stores(conn, excluded_site_codes=args.exclude_site_code)
        if not stores:
            raise RuntimeError("Nu exista magazine active pentru forecast.")
        site_codes = [store.site_code for store in stores]
        sales = await fetch_monthly_sales(
            conn,
            site_codes=site_codes,
            start_month=args.history_start_month,
            end_month=args.end_month,
            metric=args.metric,
        )

        if args.operational:
            source_month = args.source_month or add_month(args.start_month, -1)
            payload, meta_rows, skipped = build_payload(
                stores=stores,
                sales=sales,
                target_months=target_months,
                source_month=source_month,
                history_start_month=args.history_start_month,
                min_context=args.min_context,
                metric=args.metric,
                feature_profile=args.feature_profile,
            )
            if not payload["inputs"]:
                raise RuntimeError("Nicio serie eligibila pentru rularea operationala.")
            started = datetime.now()
            response = post_forecast(args.api_url, api_key, payload, args.timeout)
            latency = (datetime.now() - started).total_seconds()
            predictions = parse_predictions(response, metric=args.metric)
            result_rows = build_result_rows(
                target_months=target_months,
                meta_rows=meta_rows,
                actuals=sales,
                predictions=predictions,
                metric=args.metric,
            )
            predicted_sites = {row["site_code"] for row in result_rows}
            if args.include_fallback:
                known_values: dict[tuple[str, str], Decimal] = {}
                for target_month in target_months:
                    fallback_rows = build_fallback_rows(
                        target_month=target_month,
                        stores=stores,
                        existing_site_codes=predicted_sites,
                        sales=sales,
                        metric=args.metric,
                        known_values=known_values,
                        source_month=source_month,
                        max_reference_month=source_month,
                    )
                    for row in fallback_rows:
                        known_values[(row["site_code"], target_month)] = row["forecast_sales"]
                    result_rows.extend(fallback_rows)
            all_rows.extend(result_rows)
            for skipped_row in skipped:
                skipped_rows.append({"target_month": ",".join(target_months), **skipped_row})
            for target_month in target_months:
                month_rows = [row for row in result_rows if row["target_month"] == target_month]
                summary = summarize_month(target_month, month_rows, len(skipped))
                summary["metric"] = args.metric
                summary["latency_sec"] = round(latency, 3)
                summary_rows.append(summary)
                print(
                    f"{target_month}: stores={summary['stores_forecasted']} "
                    f"model={summary['stores_model']} fallback={summary['stores_fallback']} "
                    f"actual={summary['actual_sales']} forecast={summary['forecast_sales']} "
                    f"bias={summary['bias_pct']}% wape={summary['wape_pct']}% latency={summary['latency_sec']}s"
                )
        else:
            for target_month in target_months:
                payload, meta_rows, skipped = build_payload(
                    stores=stores,
                    sales=sales,
                    target_months=[target_month],
                    source_month=add_month(target_month, -1),
                    history_start_month=args.history_start_month,
                    min_context=args.min_context,
                    metric=args.metric,
                    feature_profile=args.feature_profile,
                )
                if not payload["inputs"]:
                    raise RuntimeError(f"Nicio serie eligibila pentru {target_month}.")
                started = datetime.now()
                response = post_forecast(args.api_url, api_key, payload, args.timeout)
                latency = (datetime.now() - started).total_seconds()
                predictions = parse_predictions(response, metric=args.metric)
                result_rows = build_result_rows(
                    target_months=[target_month],
                    meta_rows=meta_rows,
                    actuals=sales,
                    predictions=predictions,
                    metric=args.metric,
                )
                predicted_sites = {row["site_code"] for row in result_rows}
                if args.include_fallback:
                    result_rows.extend(
                        build_fallback_rows(
                            target_month=target_month,
                            stores=stores,
                            existing_site_codes=predicted_sites,
                            sales=sales,
                            metric=args.metric,
                            source_month=add_month(target_month, -1),
                            max_reference_month=add_month(target_month, -1),
                        )
                    )
                all_rows.extend(result_rows)
                for skipped_row in skipped:
                    skipped_rows.append({"target_month": target_month, **skipped_row})
                summary = summarize_month(target_month, result_rows, len(skipped))
                summary["metric"] = args.metric
                summary["latency_sec"] = round(latency, 3)
                summary_rows.append(summary)
                print(
                    f"{target_month}: stores={summary['stores_forecasted']} "
                    f"model={summary['stores_model']} fallback={summary['stores_fallback']} "
                    f"actual={summary['actual_sales']} forecast={summary['forecast_sales']} "
                    f"bias={summary['bias_pct']}% wape={summary['wape_pct']}% latency={summary['latency_sec']}s"
                )
    finally:
        await conn.close()

    profile_prefix = "" if args.feature_profile == "v1" else f"{args.feature_profile}_"
    suffix = f"{args.metric}_{profile_prefix}{args.start_month}_to_{args.end_month}"
    write_csv(
        output_dir / f"xreg_backtest_summary_{suffix}.csv",
        summary_rows,
        [
            "metric",
            "target_month",
            "stores_forecasted",
            "stores_model",
            "stores_fallback",
            "stores_model_skipped",
            "actual_sales",
            "forecast_sales",
            "error_sales",
            "bias_pct",
            "wape_pct",
            "latency_sec",
        ],
    )
    write_csv(
        output_dir / f"xreg_backtest_store_{suffix}.csv",
        all_rows,
        [
            "metric",
            "target_month",
            "source_month",
            "site_code",
            "locatie",
            "firma",
            "regional",
            "asm",
            "first_input_month",
            "context_months",
            "method",
            "actual_sales",
            "forecast_sales",
            "error_sales",
            "abs_error_sales",
            "error_pct",
            "abs_error_pct",
        ],
    )
    if skipped_rows:
        write_csv(
            output_dir / f"xreg_backtest_skipped_{suffix}.csv",
            skipped_rows,
            ["target_month", "site_code", "reason", "context_months"],
        )

    overall_actual = sum((row["actual_sales"] for row in all_rows), Decimal("0"))
    overall_forecast = sum((row["forecast_sales"] for row in all_rows), Decimal("0"))
    overall_abs_error = sum((row["abs_error_sales"] for row in all_rows), Decimal("0"))
    overall = {
        "metric": args.metric,
        "feature_profile": args.feature_profile,
        "start_month": args.start_month,
        "end_month": args.end_month,
        "target_months": len(target_months),
        "store_rows": len(all_rows),
        "actual_sales": str(overall_actual),
        "forecast_sales": str(overall_forecast),
        "bias_pct": str(pct(overall_forecast - overall_actual, overall_actual)),
        "wape_pct": str(pct(overall_abs_error, overall_actual)),
    }
    (output_dir / f"xreg_backtest_overall_{suffix}.json").write_text(
        json.dumps(overall, indent=2),
        encoding="utf-8",
    )
    print(f"Output: {output_dir.resolve()}")
    print(f"Overall: bias={overall['bias_pct']}% wape={overall['wape_pct']}% rows={overall['store_rows']}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Ruleaza TimesFM/XReg lunar si evalueaza backtestul pe magazine active.")
    parser.add_argument("--start-month", required=True, help="Prima luna tinta, YYYY-MM.")
    parser.add_argument("--end-month", required=True, help="Ultima luna tinta, YYYY-MM.")
    parser.add_argument("--metric", choices=["sales_value", "units"], default="sales_value")
    parser.add_argument(
        "--operational",
        action="store_true",
        help="Ruleaza o singura prognoza multi-step pentru intervalul cerut.",
    )
    parser.add_argument(
        "--source-month",
        default=None,
        help="Ultima luna istorica folosita in modul --operational. Implicit luna anterioara startului.",
    )
    parser.add_argument("--history-start-month", default="2018-01")
    parser.add_argument("--feature-profile", choices=["v1", "v2", "v3"], default="v1")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--env-file", default="/opt/Mobiup/unihub-retail/.env")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-context", type=int, default=MIN_CONTEXT)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--exclude-site-code",
        action="append",
        default=DEFAULT_EXCLUDED_SITE_CODES.copy(),
        help="Exclude un magazin din rularea forecast. Implicit exclude magazinele inchise in iunie 2026.",
    )
    parser.add_argument("--no-fallback", action="store_false", dest="include_fallback")
    parser.set_defaults(include_fallback=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
