from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import sys
from calendar import monthrange
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import Any, Literal

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg
from dotenv import load_dotenv
from services.forecast_http import ForecastTimeoutError, post_forecast
from services.ai_forecast_contract import (
    CoverageMode,
    ResponseProfile,
    validate_forecast_request,
    validate_forecast_response,
)
from services.ai_forecast_cohort import (
    CohortAuthorityError,
    CohortResolution,
    authority_generation,
    fetch_asof_evidence,
    resolution_sha256,
    resolve_asof_cohort,
    source_month_cutoff,
)
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


@dataclass(frozen=True)
class HistoricalCohort:
    source_month: str
    stores: tuple[StoreInfo, ...]
    resolution: CohortResolution
    source_generation: str
    source_generation_sha256: str
    cohort_sha256: str


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


async def fetch_asof_stores(
    conn: asyncpg.Connection,
    *,
    source_month: str,
    excluded_site_codes: list[str],
) -> HistoricalCohort:
    """Resolve forecast stores only from historical, cutoff-bounded authority."""
    cutoff_at = source_month_cutoff(source_month)
    reporting, targets, events, assignments = await fetch_asof_evidence(
        conn,
        source_month=source_month,
        cutoff_at=cutoff_at,
    )
    manually_excluded = set(excluded_site_codes)
    transfer_sites = {
        row.site_code
        for row in reporting
        if row.month == source_month and row.locatie.upper().startswith("TR ")
    }
    excluded = manually_excluded | transfer_sites
    reporting = [row for row in reporting if row.site_code not in excluded]
    targets = [row for row in targets if row.site_code not in excluded]
    events = [row for row in events if row.site_code not in excluded]
    assignments = [row for row in assignments if row.site_code not in excluded]
    source_generation, source_generation_sha256 = authority_generation(
        source_month=source_month,
        reporting=reporting,
        targets=targets,
        activity_events=events,
        org_assignments=assignments,
    )
    resolution = resolve_asof_cohort(
        source_month=source_month,
        cutoff_at=cutoff_at,
        source_generation=source_generation,
        reporting=reporting,
        targets=targets,
        activity_events=events,
        org_assignments=assignments,
    )
    if resolution.decision != "READY":
        blocked = ",".join(resolution.blocked_site_codes)
        raise CohortAuthorityError(f"historical cohort BLOCKED for {source_month}: {blocked}")
    locations = {
        row.site_code: row.locatie
        for row in reporting
        if row.month == source_month and row.locatie.strip()
    }
    stores = tuple(
        StoreInfo(
            site_code=row.site_code,
            locatie=locations.get(row.site_code, row.site_code),
            firma=row.firma or "",
            regional=row.regional or "",
            asm=row.asm or "",
        )
        for row in resolution.rows
        if row.is_operating is True
    )
    return HistoricalCohort(
        source_month=source_month,
        stores=stores,
        resolution=resolution,
        source_generation=source_generation,
        source_generation_sha256=source_generation_sha256,
        cohort_sha256=resolution_sha256(resolution),
    )


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
    response_profile: ResponseProfile = "point_quantiles_v1",
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
        "response_profile": response_profile,
    }
    return payload, rows_meta, skipped


def parse_predictions(
    response: dict[str, Any],
    *,
    request_payload: dict[str, Any],
    metric: MetricName,
    response_profile: ResponseProfile,
    coverage_mode: CoverageMode,
) -> dict[str, list[Decimal]]:
    request_contract = validate_forecast_request(request_payload)
    response_contract = validate_forecast_response(
        response,
        request=request_contract,
        metric=metric,
        response_profile=response_profile,
        coverage_mode=coverage_mode,
    )
    return {
        series_id: [point.point for point in points]
        for series_id, points in response_contract.predictions.items()
    }


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


async def load_historical_forecast_inputs(
    conn: asyncpg.Connection,
    *,
    args: argparse.Namespace,
    target_months: list[str],
) -> tuple[dict[str, HistoricalCohort], dict[tuple[str, str], Decimal]]:
    cohorts: dict[str, HistoricalCohort] = {}
    if args.operational:
        source_month = args.source_month or add_month(args.start_month, -1)
        cohort = await fetch_asof_stores(
            conn,
            source_month=source_month,
            excluded_site_codes=args.exclude_site_code,
        )
        cohorts = {target_month: cohort for target_month in target_months}
    else:
        for target_month in target_months:
            cohorts[target_month] = await fetch_asof_stores(
                conn,
                source_month=add_month(target_month, -1),
                excluded_site_codes=args.exclude_site_code,
            )
    site_codes = sorted(
        {store.site_code for cohort in cohorts.values() for store in cohort.stores}
    )
    if not site_codes:
        raise RuntimeError("Nu exista magazine confirmate in cohorta istorica.")
    sales = await fetch_monthly_sales(
        conn,
        site_codes=site_codes,
        start_month=args.history_start_month,
        end_month=args.end_month,
        metric=args.metric,
    )
    return cohorts, sales


def _prepare_xreg_inputs(
    args: argparse.Namespace,
) -> tuple[list[str], Path, str]:
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL lipseste.")
    api_key = args.api_key or os.environ.get("TIMESFM_API_KEY")
    if not api_key:
        raise RuntimeError("TIMESFM_API_KEY lipseste.")
    target_months = month_range(args.start_month, args.end_month)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return target_months, output_dir, api_key


async def _post_xreg_forecast(
    args: argparse.Namespace,
    *,
    api_key: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], float]:
    started = monotonic()
    try:
        response = post_forecast(args.api_url, api_key, payload, args.timeout)
    except ForecastTimeoutError:
        if args.coverage_mode != "seasonal_fallback":
            raise
        response = {"series": []}
    latency = monotonic() - started
    return response, latency


def _attach_latency_xreg(
    rows: list[dict[str, Any]],
    *,
    latency: float,
) -> list[dict[str, Any]]:
    for row in rows:
        row["latency_sec"] = round(latency, 3)
    return rows


async def _append_operational_fallback(
    args: argparse.Namespace,
    *,
    result_rows: list[dict[str, Any]],
    stores: list[Any],
    sales: dict[tuple[str, str], Decimal],
    source_month: str,
    target_months: list[str],
) -> list[dict[str, Any]]:
    if args.coverage_mode != "seasonal_fallback":
        return result_rows
    predicted_sites = {row["site_code"] for row in result_rows}
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
    return result_rows


def _append_per_month_fallback(
    args: argparse.Namespace,
    *,
    result_rows: list[dict[str, Any]],
    stores: list[Any],
    sales: dict[tuple[str, str], Decimal],
    target_month: str,
) -> list[dict[str, Any]]:
    if args.coverage_mode != "seasonal_fallback":
        return result_rows
    predicted_sites = {row["site_code"] for row in result_rows}
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
    return result_rows


def _record_skipped(
    skipped_rows: list[dict[str, Any]],
    *,
    skipped: list[dict[str, Any]],
    target_months: list[str],
) -> None:
    for skipped_row in skipped:
        skipped_rows.append({"target_month": ",".join(target_months), **skipped_row})


def _record_per_month_skipped(
    skipped_rows: list[dict[str, Any]],
    *,
    skipped: list[dict[str, Any]],
    target_month: str,
) -> None:
    for skipped_row in skipped:
        skipped_rows.append({"target_month": target_month, **skipped_row})


def _record_operational_summary_rows(
    args: argparse.Namespace,
    *,
    target_months: list[str],
    result_rows: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    latency: float,
    summary_rows: list[dict[str, Any]],
) -> None:
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


def _record_per_month_summary_row(
    args: argparse.Namespace,
    *,
    target_month: str,
    result_rows: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    latency: float,
    summary_rows: list[dict[str, Any]],
) -> None:
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


async def _run_operational_pipeline(
    args: argparse.Namespace,
    *,
    conn: asyncpg.Connection,
    target_months: list[str],
    cohorts: dict[str, HistoricalCohort],
    sales: dict[tuple[str, str], Decimal],
    api_key: str,
    all_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    skipped_rows: list[dict[str, Any]],
) -> None:
    cohort = cohorts[target_months[0]]
    stores = list(cohort.stores)
    source_month = cohort.source_month
    payload, meta_rows, skipped = build_payload(
        stores=stores,
        sales=sales,
        target_months=target_months,
        source_month=source_month,
        history_start_month=args.history_start_month,
        min_context=args.min_context,
        metric=args.metric,
        feature_profile=args.feature_profile,
        response_profile=args.response_profile,
    )
    if not payload["inputs"]:
        raise RuntimeError("Nicio serie eligibila pentru rularea operationala.")
    response, latency = await _post_xreg_forecast(args, api_key=api_key, payload=payload)
    predictions = parse_predictions(
        response,
        request_payload=payload,
        metric=args.metric,
        response_profile=args.response_profile,
        coverage_mode=args.coverage_mode,
    )
    result_rows = build_result_rows(
        target_months=target_months,
        meta_rows=meta_rows,
        actuals=sales,
        predictions=predictions,
        metric=args.metric,
    )
    result_rows = _attach_latency_xreg(result_rows, latency=latency)
    result_rows = await _append_operational_fallback(
        args,
        result_rows=result_rows,
        stores=stores,
        sales=sales,
        source_month=source_month,
        target_months=target_months,
    )
    all_rows.extend(result_rows)
    _record_skipped(skipped_rows, skipped=skipped, target_months=target_months)
    _record_operational_summary_rows(
        args,
        target_months=target_months,
        result_rows=result_rows,
        skipped=skipped,
        latency=latency,
        summary_rows=summary_rows,
    )


async def _run_per_month_pipeline(
    args: argparse.Namespace,
    *,
    conn: asyncpg.Connection,
    target_months: list[str],
    cohorts: dict[str, HistoricalCohort],
    sales: dict[tuple[str, str], Decimal],
    api_key: str,
    all_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    skipped_rows: list[dict[str, Any]],
) -> None:
    for target_month in target_months:
        cohort = cohorts[target_month]
        stores = list(cohort.stores)
        payload, meta_rows, skipped = build_payload(
            stores=stores,
            sales=sales,
            target_months=[target_month],
            source_month=add_month(target_month, -1),
            history_start_month=args.history_start_month,
            min_context=args.min_context,
            metric=args.metric,
            feature_profile=args.feature_profile,
            response_profile=args.response_profile,
        )
        if not payload["inputs"]:
            raise RuntimeError(f"Nicio serie eligibila pentru {target_month}.")
        response, latency = await _post_xreg_forecast(args, api_key=api_key, payload=payload)
        predictions = parse_predictions(
            response,
            request_payload=payload,
            metric=args.metric,
            response_profile=args.response_profile,
            coverage_mode=args.coverage_mode,
        )
        result_rows = build_result_rows(
            target_months=[target_month],
            meta_rows=meta_rows,
            actuals=sales,
            predictions=predictions,
            metric=args.metric,
        )
        result_rows = _attach_latency_xreg(result_rows, latency=latency)
        result_rows = _append_per_month_fallback(
            args,
            result_rows=result_rows,
            stores=stores,
            sales=sales,
            target_month=target_month,
        )
        all_rows.extend(result_rows)
        _record_per_month_skipped(skipped_rows, skipped=skipped, target_month=target_month)
        _record_per_month_summary_row(
            args,
            target_month=target_month,
            result_rows=result_rows,
            skipped=skipped,
            latency=latency,
            summary_rows=summary_rows,
        )


async def _execute_xreg_pipelines(
    args: argparse.Namespace,
    *,
    conn: asyncpg.Connection,
    target_months: list[str],
    cohorts: dict[str, HistoricalCohort],
    sales: dict[tuple[str, str], Decimal],
    api_key: str,
    all_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    skipped_rows: list[dict[str, Any]],
) -> None:
    if args.operational:
        await _run_operational_pipeline(
            args,
            conn=conn,
            target_months=target_months,
            cohorts=cohorts,
            sales=sales,
            api_key=api_key,
            all_rows=all_rows,
            summary_rows=summary_rows,
            skipped_rows=skipped_rows,
        )
        return
    await _run_per_month_pipeline(
        args,
        conn=conn,
        target_months=target_months,
        cohorts=cohorts,
        sales=sales,
        api_key=api_key,
        all_rows=all_rows,
        summary_rows=summary_rows,
        skipped_rows=skipped_rows,
    )


def _xreg_output_suffix(args: argparse.Namespace) -> str:
    profile_prefix = "" if args.feature_profile == "v1" else f"{args.feature_profile}_"
    return f"{args.metric}_{profile_prefix}{args.start_month}_to_{args.end_month}"


_XREG_SUMMARY_FIELDS: list[str] = [
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
]


_XREG_STORE_FIELDS: list[str] = [
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
]


_XREG_SKIPPED_FIELDS: list[str] = [
    "target_month",
    "site_code",
    "reason",
    "context_months",
]


def _write_xreg_csvs(
    args: argparse.Namespace,
    *,
    output_dir: Path,
    suffix: str,
    summary_rows: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    skipped_rows: list[dict[str, Any]],
) -> None:
    write_csv(
        output_dir / f"xreg_backtest_summary_{suffix}.csv",
        summary_rows,
        _XREG_SUMMARY_FIELDS,
    )
    write_csv(
        output_dir / f"xreg_backtest_store_{suffix}.csv",
        all_rows,
        _XREG_STORE_FIELDS,
    )
    if skipped_rows:
        write_csv(
            output_dir / f"xreg_backtest_skipped_{suffix}.csv",
            skipped_rows,
            _XREG_SKIPPED_FIELDS,
        )


def _build_xreg_overall(
    args: argparse.Namespace,
    *,
    target_months: list[str],
    all_rows: list[dict[str, Any]],
    cohorts: dict[str, HistoricalCohort],
) -> dict[str, Any]:
    overall_actual = sum((row["actual_sales"] for row in all_rows), Decimal("0"))
    overall_forecast = sum((row["forecast_sales"] for row in all_rows), Decimal("0"))
    overall_abs_error = sum((row["abs_error_sales"] for row in all_rows), Decimal("0"))
    return {
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
        "cohorts": {
            target_month: {
                "source_month": cohort.source_month,
                "source_generation": cohort.source_generation,
                "source_generation_sha256": cohort.source_generation_sha256,
                "cohort_sha256": cohort.cohort_sha256,
                "store_count": len(cohort.stores),
            }
            for target_month, cohort in sorted(cohorts.items())
        },
    }


async def run(args: argparse.Namespace) -> int:
    load_dotenv(args.env_file)
    target_months, output_dir, api_key = _prepare_xreg_inputs(args)

    conn = await asyncpg.connect(os.environ.get("DATABASE_URL", ""))
    all_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    cohorts: dict[str, HistoricalCohort] = {}
    try:
        cohorts, sales = await load_historical_forecast_inputs(
            conn,
            args=args,
            target_months=target_months,
        )
        await _execute_xreg_pipelines(
            args,
            conn=conn,
            target_months=target_months,
            cohorts=cohorts,
            sales=sales,
            api_key=api_key,
            all_rows=all_rows,
            summary_rows=summary_rows,
            skipped_rows=skipped_rows,
        )
    finally:
        await conn.close()

    suffix = _xreg_output_suffix(args)
    _write_xreg_csvs(
        args,
        output_dir=output_dir,
        suffix=suffix,
        summary_rows=summary_rows,
        all_rows=all_rows,
        skipped_rows=skipped_rows,
    )
    overall = _build_xreg_overall(
        args,
        target_months=target_months,
        all_rows=all_rows,
        cohorts=cohorts,
    )
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
    parser.add_argument(
        "--response-profile",
        choices=["point_only_v1", "point_quantiles_v1"],
        default="point_quantiles_v1",
    )
    parser.add_argument(
        "--coverage-mode",
        choices=["fail_closed", "seasonal_fallback"],
        default="fail_closed",
    )
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
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
