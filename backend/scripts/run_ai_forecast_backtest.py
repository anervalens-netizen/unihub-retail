from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import Any

import asyncpg
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.run_ai_forecast_xreg import (
    DEFAULT_API_URL,
    DEFAULT_EXCLUDED_SITE_CODES,
    DEFAULT_OUTPUT_DIR,
    MIN_CONTEXT,
    HistoricalCohort,
    MetricName,
    StoreInfo,
    add_month,
    build_payload,
    fetch_asof_stores,
    fetch_monthly_sales,
    metric_value,
    month_range,
    pct,
    post_forecast,
    seasonal_last3_fallback,
    write_csv,
)
from services.ai_forecast_contract import (
    CoverageMode,
    ResponseProfile,
    validate_forecast_request,
    validate_forecast_response,
)
from services.ai_forecast_governance import (
    evaluate_governance_fixture,
    load_governance_fixture,
    load_locked_json_contract,
)
from services.ai_forecast_governance_evidence import (
    assert_evaluation_matches_fixture,
    build_model_card,
    build_monitoring_report,
    write_governance_evidence,
)
from services.forecast_http import ForecastTimeoutError


ModelName = str

BASELINE_MODELS = {
    "seasonal_naive",
    "seasonal_moving_average",
    "seasonal_last3",
}
REMOTE_SIMPLE_MODELS = {"timesfm"}
REMOTE_XREG_MODES = {
    "xreg_timesfm": "xreg + timesfm",
    "timesfm_xreg": "timesfm + xreg",
}
DEFAULT_MODELS = [
    "seasonal_naive",
    "seasonal_moving_average",
    "seasonal_last3",
    "timesfm",
    "xreg_timesfm",
    "timesfm_xreg",
]


def as_decimal(value: Any, metric: MetricName) -> Decimal:
    return metric_value(value, metric)


def average(values: list[Decimal], *, scale: str = "0.01") -> Decimal | None:
    if not values:
        return None
    return (sum(values, Decimal("0")) / Decimal(len(values))).quantize(Decimal(scale))


def pinball_loss(actual: Decimal, forecast: Decimal | None, quantile: Decimal) -> Decimal | None:
    if forecast is None:
        return None
    diff = actual - forecast
    return max(quantile * diff, (quantile - Decimal("1")) * diff).quantize(Decimal("0.01"))


def parse_quantile_row(values: Any, *, metric: MetricName) -> dict[str, Decimal | None]:
    if not isinstance(values, list) or not values:
        return {"q10": None, "q20": None, "q50": None, "q80": None, "q90": None}

    if len(values) >= 10:
        indexes = {"q10": 1, "q20": 2, "q50": 5, "q80": 8, "q90": 9}
    elif len(values) >= 9:
        indexes = {"q10": 0, "q20": 1, "q50": 4, "q80": 7, "q90": 8}
    else:
        return {"q10": None, "q20": None, "q50": None, "q80": None, "q90": None}

    return {
        name: as_decimal(values[index], metric)
        for name, index in indexes.items()
    }


def parse_forecast_response(
    response: dict[str, Any],
    *,
    metric: MetricName,
    request_payload: dict[str, Any] | None = None,
    response_profile: ResponseProfile = "point_quantiles_v1",
    coverage_mode: CoverageMode = "fail_closed",
) -> dict[str, list[dict[str, Decimal | None]]]:
    if request_payload is None:
        rows = response.get("series", [])
        horizon = len(rows[0].get("point_forecast", [])) if rows else 0
        request_payload = {
            "horizon": horizon,
            "series_ids": [row.get("series_id") for row in rows],
            "inputs": [[0] for _row in rows],
        }
    request_contract = validate_forecast_request(request_payload)
    contract = validate_forecast_response(
        response,
        request=request_contract,
        metric=metric,
        response_profile=response_profile,
        coverage_mode=coverage_mode,
    )
    predictions: dict[str, list[dict[str, Decimal | None]]] = {}
    for series_id, points in contract.predictions.items():
        predictions[series_id] = [
            {
                "point": point.point,
                **(
                    dict(zip(("q10", "q20", "q50", "q80", "q90"), point.quantiles, strict=True))
                    if point.quantiles is not None
                    else {"q10": None, "q20": None, "q50": None, "q80": None, "q90": None}
                ),
            }
            for point in points
        ]
    return predictions


def context_meta(
    store: StoreInfo,
    *,
    sales: dict[tuple[str, str], Decimal],
    history_start_month: str,
    source_month: str,
    metric: MetricName,
) -> dict[str, Any]:
    months = month_range(history_start_month, source_month)
    first_input_month = ""
    context_months = 0
    for index, month in enumerate(months):
        value = as_decimal(sales.get((store.site_code, month), Decimal("0")), metric)
        if value > 0:
            first_input_month = month
            context_months = len(months) - index
            break
    return {
        "site_code": store.site_code,
        "locatie": store.locatie,
        "firma": store.firma,
        "regional": store.regional,
        "asm": store.asm,
        "first_input_month": first_input_month,
        "source_month": source_month,
        "context_months": context_months,
    }


def make_result_row(
    *,
    model: ModelName,
    method: str,
    meta: dict[str, Any],
    target_month: str,
    actual: Decimal,
    forecast: Decimal,
    metric: MetricName,
    quantiles: dict[str, Decimal | None] | None = None,
) -> dict[str, Any]:
    quantiles = quantiles or {"q10": None, "q20": None, "q50": None, "q80": None, "q90": None}
    error = forecast - actual
    abs_error = abs(error)
    q10 = quantiles.get("q10")
    q20 = quantiles.get("q20")
    q50 = quantiles.get("q50")
    q80 = quantiles.get("q80")
    q90 = quantiles.get("q90")
    coverage_p10_p90 = int(q10 <= actual <= q90) if q10 is not None and q90 is not None else None
    coverage_p20_p80 = int(q20 <= actual <= q80) if q20 is not None and q80 is not None else None
    return {
        **meta,
        "model": model,
        "metric": metric,
        "target_month": target_month,
        "method": method,
        "actual_sales": actual,
        "forecast_sales": forecast,
        "error_sales": error,
        "abs_error_sales": abs_error,
        "error_pct": pct(error, actual),
        "abs_error_pct": pct(abs_error, actual),
        "q10": q10,
        "q20": q20,
        "q50": q50,
        "q80": q80,
        "q90": q90,
        "coverage_p10_p90": coverage_p10_p90,
        "coverage_p20_p80": coverage_p20_p80,
        "pinball_p10": pinball_loss(actual, q10, Decimal("0.10")),
        "pinball_p50": pinball_loss(actual, q50, Decimal("0.50")),
        "pinball_p90": pinball_loss(actual, q90, Decimal("0.90")),
    }


def seasonal_naive_forecast(
    *,
    site_code: str,
    target_month: str,
    sales: dict[tuple[str, str], Decimal],
    metric: MetricName,
) -> tuple[Decimal, str]:
    reference_month = add_month(target_month, -12)
    value = as_decimal(sales.get((site_code, reference_month), Decimal("0")), metric)
    method = "seasonal_naive" if value > 0 else "seasonal_naive_zero"
    return value, method


def seasonal_moving_average_forecast(
    *,
    site_code: str,
    target_month: str,
    sales: dict[tuple[str, str], Decimal],
    metric: MetricName,
    years: int,
) -> tuple[Decimal, str]:
    values = [
        as_decimal(sales.get((site_code, add_month(target_month, -12 * offset)), Decimal("0")), metric)
        for offset in range(1, years + 1)
    ]
    positive_values = [value for value in values if value > 0]
    if not positive_values:
        return Decimal("0"), "seasonal_moving_average_zero"
    forecast = sum(positive_values, Decimal("0")) / Decimal(len(positive_values))
    return as_decimal(forecast, metric), f"seasonal_moving_average_{len(positive_values)}y"


def build_baseline_rows(
    *,
    model: ModelName,
    target_month: str,
    stores: list[StoreInfo],
    sales: dict[tuple[str, str], Decimal],
    metric: MetricName,
    history_start_month: str,
    seasonal_years: int,
) -> list[dict[str, Any]]:
    source_month = add_month(target_month, -1)
    site_codes = [store.site_code for store in stores]
    rows: list[dict[str, Any]] = []
    for store in stores:
        if model == "seasonal_naive":
            forecast, method = seasonal_naive_forecast(
                site_code=store.site_code,
                target_month=target_month,
                sales=sales,
                metric=metric,
            )
        elif model == "seasonal_moving_average":
            forecast, method = seasonal_moving_average_forecast(
                site_code=store.site_code,
                target_month=target_month,
                sales=sales,
                metric=metric,
                years=seasonal_years,
            )
        elif model == "seasonal_last3":
            forecast, method = seasonal_last3_fallback(
                site_code=store.site_code,
                target_month=target_month,
                sales=sales,
                site_codes=site_codes,
                metric=metric,
                max_reference_month=source_month,
            )
        else:
            raise ValueError(f"Model baseline necunoscut: {model}")
        actual = as_decimal(sales.get((store.site_code, target_month), Decimal("0")), metric)
        rows.append(
            make_result_row(
                model=model,
                method=method,
                meta=context_meta(
                    store,
                    sales=sales,
                    history_start_month=history_start_month,
                    source_month=source_month,
                    metric=metric,
                ),
                target_month=target_month,
                actual=actual,
                forecast=forecast,
                metric=metric,
            )
        )
    return rows


def model_result_rows(
    *,
    model: ModelName,
    target_months: list[str],
    meta_rows: list[dict[str, Any]],
    actuals: dict[tuple[str, str], Decimal],
    predictions: dict[str, list[dict[str, Decimal | None]]],
    metric: MetricName,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for meta in meta_rows:
        site_code = str(meta["site_code"])
        site_predictions = predictions.get(site_code)
        if not site_predictions:
            continue
        for index, target_month in enumerate(target_months):
            if index >= len(site_predictions):
                break
            forecast = site_predictions[index].get("point")
            if forecast is None:
                continue
            actual = as_decimal(actuals.get((site_code, target_month), Decimal("0")), metric)
            rows.append(
                make_result_row(
                    model=model,
                    method=f"model_{model}",
                    meta=meta,
                    target_month=target_month,
                    actual=actual,
                    forecast=forecast,
                    metric=metric,
                    quantiles=site_predictions[index],
                )
            )
    return rows


def fallback_rows_for_missing_sites(
    *,
    model: ModelName,
    target_month: str,
    stores: list[StoreInfo],
    existing_site_codes: set[str],
    sales: dict[tuple[str, str], Decimal],
    metric: MetricName,
    history_start_month: str,
    source_month: str,
) -> list[dict[str, Any]]:
    rows = build_baseline_rows(
        model="seasonal_last3",
        target_month=target_month,
        stores=[store for store in stores if store.site_code not in existing_site_codes],
        sales=sales,
        metric=metric,
        history_start_month=history_start_month,
        seasonal_years=3,
    )
    for row in rows:
        row["model"] = model
        row["source_month"] = source_month
        row["method"] = f"fallback_for_{model}:{row['method']}"
    return rows


def aggregate_rows(
    *,
    rows: list[dict[str, Any]],
    model: ModelName,
    metric: MetricName,
    group_level: str,
    group_key: str,
    group_label: str,
    target_month: str | None = None,
) -> dict[str, Any]:
    actual = sum((row["actual_sales"] for row in rows), Decimal("0"))
    forecast = sum((row["forecast_sales"] for row in rows), Decimal("0"))
    error = forecast - actual
    abs_error = sum((row["abs_error_sales"] for row in rows), Decimal("0"))
    abs_pct_values = [row["abs_error_pct"] for row in rows if row["abs_error_pct"] is not None]
    q10_coverage = [Decimal(row["coverage_p10_p90"]) for row in rows if row["coverage_p10_p90"] is not None]
    q20_coverage = [Decimal(row["coverage_p20_p80"]) for row in rows if row["coverage_p20_p80"] is not None]
    stores = {row["site_code"] for row in rows}
    return {
        "metric": metric,
        "model": model,
        "group_level": group_level,
        "group_key": group_key,
        "group_label": group_label,
        "target_month": target_month or "",
        "rows": len(rows),
        "stores": len(stores),
        "stores_model": sum(1 for row in rows if str(row["method"]).startswith("model_")),
        "stores_fallback": sum(1 for row in rows if str(row["method"]).startswith("fallback")),
        "actual_sales": actual,
        "forecast_sales": forecast,
        "error_sales": error,
        "abs_error_sales": abs_error,
        "mae": average([row["abs_error_sales"] for row in rows]),
        "bias_pct": pct(error, actual),
        "wape_pct": pct(abs_error, actual),
        "mape_pct": average(abs_pct_values),
        "coverage_p10_p90_pct": pct(sum(q10_coverage, Decimal("0")), Decimal(len(q10_coverage))) if q10_coverage else None,
        "coverage_p20_p80_pct": pct(sum(q20_coverage, Decimal("0")), Decimal(len(q20_coverage))) if q20_coverage else None,
        "pinball_p10": average([row["pinball_p10"] for row in rows if row["pinball_p10"] is not None]),
        "pinball_p50": average([row["pinball_p50"] for row in rows if row["pinball_p50"] is not None]),
        "pinball_p90": average([row["pinball_p90"] for row in rows if row["pinball_p90"] is not None]),
    }


def model_month_summaries(rows: list[dict[str, Any]], *, metric: MetricName) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["model"], row["target_month"])].append(row)
    return [
        aggregate_rows(
            rows=items,
            model=model,
            metric=metric,
            group_level="network",
            group_key="ALL",
            group_label="Retea",
            target_month=target_month,
        )
        for (model, target_month), items in sorted(grouped.items())
    ]


def model_metrics(rows: list[dict[str, Any]], *, metric: MetricName) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        model = row["model"]
        grouped[(model, "network", "ALL", "Retea")].append(row)
        grouped[(model, "regional", row["regional"], row["regional"])].append(row)
        asm_key = f"{row['regional']} / {row['asm']}"
        grouped[(model, "asm", asm_key, asm_key)].append(row)
        store_label = f"{row['site_code']} - {row['locatie']}"
        grouped[(model, "store", row["site_code"], store_label)].append(row)
    return [
        aggregate_rows(
            rows=items,
            model=model,
            metric=metric,
            group_level=group_level,
            group_key=group_key,
            group_label=group_label,
        )
        for (model, group_level, group_key, group_label), items in sorted(grouped.items())
    ]


def parse_models(raw: str) -> list[ModelName]:
    if raw.strip().lower() == "all":
        return DEFAULT_MODELS.copy()
    models = [item.strip() for item in raw.split(",") if item.strip()]
    allowed = BASELINE_MODELS | REMOTE_SIMPLE_MODELS | set(REMOTE_XREG_MODES)
    unknown = [model for model in models if model not in allowed]
    if unknown:
        raise ValueError(f"Modele necunoscute: {', '.join(unknown)}")
    return models


def simple_api_from_xreg_url(xreg_api_url: str) -> str:
    if xreg_api_url.endswith("/forecast_xreg"):
        return f"{xreg_api_url.removesuffix('/forecast_xreg')}/forecast"
    return xreg_api_url


async def load_historical_backtest_inputs(
    conn: asyncpg.Connection,
    *,
    args: argparse.Namespace,
    target_months: list[str],
) -> tuple[dict[str, HistoricalCohort], dict[tuple[str, str], Decimal]]:
    cohorts: dict[str, HistoricalCohort] = {}
    for target_month in target_months:
        cohorts[target_month] = await fetch_asof_stores(
            conn,
            source_month=add_month(target_month, -1),
            excluded_site_codes=args.exclude_site_code,
        )
    site_codes = sorted(
        {
            store.site_code
            for cohort in cohorts.values()
            for store in cohort.stores
        }
    )
    if not site_codes:
        raise RuntimeError("Nu exista magazine confirmate in cohortele istorice.")
    sales = await fetch_monthly_sales(
        conn,
        site_codes=site_codes,
        start_month=args.history_start_month,
        end_month=args.end_month,
        metric=args.metric,
    )
    return cohorts, sales


def _prepare_backtest_inputs(
    args: argparse.Namespace,
) -> tuple[list[ModelName], list[str], Path, str | None]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL lipseste.")
    models = parse_models(args.models)
    remote_models = [
        model
        for model in models
        if model in REMOTE_SIMPLE_MODELS or model in REMOTE_XREG_MODES
    ]
    api_key = args.api_key or os.environ.get("TIMESFM_API_KEY")
    if remote_models and not api_key:
        raise RuntimeError("TIMESFM_API_KEY lipseste pentru modelele remote.")
    target_months = month_range(args.start_month, args.end_month)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return models, target_months, output_dir, api_key


def _resolve_remote_endpoint(
    args: argparse.Namespace,
    *,
    model: ModelName,
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if model in REMOTE_XREG_MODES:
        payload["xreg_mode"] = REMOTE_XREG_MODES[model]
        return args.xreg_api_url, payload
    simple_payload = {
        "horizon": payload["horizon"],
        "inputs": payload["inputs"],
        "series_ids": payload["series_ids"],
    }
    return args.forecast_api_url, simple_payload


async def _execute_remote_forecast(
    args: argparse.Namespace,
    *,
    api_url: str,
    payload: dict[str, Any],
    api_key: str,
) -> tuple[dict[str, Any], float]:
    started = monotonic()
    try:
        response = post_forecast(api_url, api_key, payload, args.timeout)
    except ForecastTimeoutError:
        if args.coverage_mode != "seasonal_fallback":
            raise
        response = {"series": []}
    latency = monotonic() - started
    return response, latency


def _attach_latency(
    rows: list[dict[str, Any]],
    *,
    latency: float,
) -> list[dict[str, Any]]:
    for row in rows:
        row["latency_sec"] = round(latency, 3)
    return rows


async def _model_request_rows(
    args: argparse.Namespace,
    *,
    model: ModelName,
    target_month: str,
    stores: list[Any],
    sales: dict[tuple[str, str], Decimal],
    source_month: str,
    api_key: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload, meta_rows, skipped = build_payload(
        stores=stores,
        sales=sales,
        target_months=[target_month],
        source_month=source_month,
        history_start_month=args.history_start_month,
        min_context=args.min_context,
        metric=args.metric,
        response_profile=args.response_profile,
    )
    if not payload["inputs"]:
        return [], skipped
    api_url, request_payload = _resolve_remote_endpoint(args, model=model, payload=payload)
    response, latency = await _execute_remote_forecast(
        args,
        api_url=api_url,
        payload=request_payload,
        api_key=api_key,
    )
    predictions = parse_forecast_response(
        response,
        metric=args.metric,
        request_payload=request_payload,
        response_profile=args.response_profile,
        coverage_mode=args.coverage_mode,
    )
    rows = model_result_rows(
        model=model,
        target_months=[target_month],
        meta_rows=meta_rows,
        actuals=sales,
        predictions=predictions,
        metric=args.metric,
    )
    return _attach_latency(rows, latency=latency), skipped


async def _backtest_target_month(
    args: argparse.Namespace,
    *,
    model: ModelName,
    target_month: str,
    stores: list[Any],
    sales: dict[tuple[str, str], Decimal],
    source_month: str,
    api_key: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if model in BASELINE_MODELS:
        month_rows = build_baseline_rows(
            model=model,
            target_month=target_month,
            stores=stores,
            sales=sales,
            metric=args.metric,
            history_start_month=args.history_start_month,
            seasonal_years=args.seasonal_years,
        )
        return month_rows, []
    return await _model_request_rows(
        args,
        model=model,
        target_month=target_month,
        stores=stores,
        sales=sales,
        source_month=source_month,
        api_key=api_key,
    )


def _apply_backtest_fallback(
    args: argparse.Namespace,
    *,
    model: ModelName,
    target_month: str,
    stores: list[Any],
    sales: dict[tuple[str, str], Decimal],
    source_month: str,
    month_rows: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if args.coverage_mode == "seasonal_fallback":
        month_rows = list(month_rows)
        month_rows.extend(
            fallback_rows_for_missing_sites(
                model=model,
                target_month=target_month,
                stores=stores,
                existing_site_codes={row["site_code"] for row in month_rows},
                sales=sales,
                metric=args.metric,
                history_start_month=args.history_start_month,
                source_month=source_month,
            )
        )
    if skipped and args.coverage_mode == "fail_closed":
        print(f"  {target_month}: {len(skipped)} serii sarite fara fallback")
    return month_rows


def _print_target_summary(
    args: argparse.Namespace,
    *,
    target_month: str,
    month_rows: list[dict[str, Any]],
    model: ModelName,
) -> None:
    summary = aggregate_rows(
        rows=month_rows,
        model=model,
        metric=args.metric,
        group_level="network",
        group_key="ALL",
        group_label="Retea",
        target_month=target_month,
    )
    print(
        f"  {target_month}: actual={summary['actual_sales']} "
        f"forecast={summary['forecast_sales']} bias={summary['bias_pct']}% "
        f"wape={summary['wape_pct']}%"
    )


def _backtest_output_paths(
    args: argparse.Namespace,
    *,
    output_dir: Path,
) -> tuple[Path, Path, Path, Path, Path]:
    suffix = f"{args.metric}_{args.start_month}_to_{args.end_month}"
    return (
        output_dir / f"backtest_comparison_store_{suffix}.csv",
        output_dir / f"backtest_comparison_summary_{suffix}.csv",
        output_dir / f"backtest_comparison_model_metrics_{suffix}.csv",
        output_dir / f"backtest_comparison_overall_{suffix}.json",
        output_dir / f"backtest_comparison_cohorts_{suffix}.json",
    )


_BACKTEST_STORE_FIELDS: list[str] = [
    "model",
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
    "q10",
    "q20",
    "q50",
    "q80",
    "q90",
    "coverage_p10_p90",
    "coverage_p20_p80",
    "pinball_p10",
    "pinball_p50",
    "pinball_p90",
    "latency_sec",
]


_BACKTEST_METRIC_FIELDS: list[str] = [
    "metric",
    "model",
    "group_level",
    "group_key",
    "group_label",
    "target_month",
    "rows",
    "stores",
    "stores_model",
    "stores_fallback",
    "actual_sales",
    "forecast_sales",
    "error_sales",
    "abs_error_sales",
    "mae",
    "bias_pct",
    "wape_pct",
    "mape_pct",
    "coverage_p10_p90_pct",
    "coverage_p20_p80_pct",
    "pinball_p10",
    "pinball_p50",
    "pinball_p90",
]


def _cohort_summary(
    cohorts: dict[str, HistoricalCohort],
) -> dict[str, dict[str, Any]]:
    return {
        target_month: {
            "source_month": cohort.source_month,
            "source_generation": cohort.source_generation,
            "source_generation_sha256": cohort.source_generation_sha256,
            "cohort_sha256": cohort.cohort_sha256,
            "store_count": len(cohort.stores),
        }
        for target_month, cohort in sorted(cohorts.items())
    }


def _write_backtest_outputs(
    args: argparse.Namespace,
    *,
    output_dir: Path,
    all_rows: list[dict[str, Any]],
    cohorts: dict[str, HistoricalCohort],
) -> tuple[Path, Path, Path, Path, Path]:
    store_path, summary_path, metrics_path, overall_path, cohort_path = _backtest_output_paths(
        args, output_dir=output_dir,
    )
    write_csv(store_path, all_rows, _BACKTEST_STORE_FIELDS)
    summary_rows = model_month_summaries(all_rows, metric=args.metric)
    metrics_rows = model_metrics(all_rows, metric=args.metric)
    write_csv(summary_path, summary_rows, _BACKTEST_METRIC_FIELDS)
    write_csv(metrics_path, metrics_rows, _BACKTEST_METRIC_FIELDS)
    overall = [row for row in metrics_rows if row["group_level"] == "network"]
    overall_path.write_text(json.dumps(overall, indent=2, default=str), encoding="utf-8")
    cohort_path.write_text(
        json.dumps(_cohort_summary(cohorts), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return store_path, summary_path, metrics_path, overall_path, cohort_path


async def run(args: argparse.Namespace) -> int:
    load_dotenv(args.env_file)
    models, target_months, output_dir, api_key = _prepare_backtest_inputs(args)

    conn = await asyncpg.connect(os.environ.get("DATABASE_URL", ""))
    try:
        cohorts, sales = await load_historical_backtest_inputs(
            conn,
            args=args,
            target_months=target_months,
        )
    finally:
        await conn.close()

    all_rows: list[dict[str, Any]] = []
    for model in models:
        print(f"Model {model}: start")
        for target_month in target_months:
            stores = list(cohorts[target_month].stores)
            source_month = add_month(target_month, -1)
            month_rows, skipped = await _backtest_target_month(
                args,
                model=model,
                target_month=target_month,
                stores=stores,
                sales=sales,
                source_month=source_month,
                api_key=api_key or "",
            )
            month_rows = _apply_backtest_fallback(
                args,
                model=model,
                target_month=target_month,
                stores=stores,
                sales=sales,
                source_month=source_month,
                month_rows=month_rows,
                skipped=skipped,
            )
            all_rows.extend(month_rows)
            _print_target_summary(
                args,
                target_month=target_month,
                month_rows=month_rows,
                model=model,
            )

    paths = _write_backtest_outputs(
        args,
        output_dir=output_dir,
        all_rows=all_rows,
        cohorts=cohorts,
    )
    print(f"Output store: {paths[0].resolve()}")
    print(f"Output summary: {paths[1].resolve()}")
    print(f"Output metrics: {paths[2].resolve()}")
    print(f"Output overall: {paths[3].resolve()}")
    print(f"Output cohorts: {paths[4].resolve()}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compara baseline-uri si modele TimesFM/XReg prin backtesting lunar walk-forward."
    )
    parser.add_argument("--start-month", default=None, help="Prima luna tinta, YYYY-MM.")
    parser.add_argument("--end-month", default=None, help="Ultima luna tinta, YYYY-MM.")
    parser.add_argument("--metric", choices=["sales_value", "units"], default="sales_value")
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
    parser.add_argument("--contract-fixture", type=Path, default=None)
    parser.add_argument("--governance-fixture", type=Path, default=None)
    parser.add_argument("--candidate-only", action="store_true")
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--evidence", type=Path, default=None)
    parser.add_argument("--models", default="all", help="Lista separata prin virgula sau `all`.")
    parser.add_argument("--seasonal-years", type=int, default=3)
    parser.add_argument("--history-start-month", default="2018-01")
    parser.add_argument("--xreg-api-url", default=DEFAULT_API_URL)
    parser.add_argument("--forecast-api-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--env-file", default="/opt/Mobiup/unihub-retail/.env")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-context", type=int, default=MIN_CONTEXT)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--exclude-site-code",
        action="append",
        default=DEFAULT_EXCLUDED_SITE_CODES.copy(),
        help="Exclude un magazin din rularea forecast.",
    )
    args = parser.parse_args()
    if args.governance_fixture is not None:
        if not args.candidate_only or args.contract_fixture is None or args.evidence is None:
            parser.error(
                "governance mode requires --candidate-only, --contract-fixture and --evidence"
            )
        load_locked_json_contract(
            args.contract_fixture,
            contract="business-golden-v2",
            version=2,
        )
        fixture = load_governance_fixture(args.governance_fixture)
        evaluation = evaluate_governance_fixture(
            fixture,
            seed=args.seed,
            response_profile=args.response_profile,
        )
        assert_evaluation_matches_fixture(evaluation, fixture)
        evidence = {
            **evaluation,
            "result": "PASS",
            "mode": "candidate_only",
            "model_card": build_model_card(evaluation, fixture),
            "monitoring": build_monitoring_report(evaluation),
        }
        write_governance_evidence(args.evidence, evidence)
        print(
            json.dumps(
                {
                    "result": "PASS",
                    "decision": evaluation["decision"],
                    "live_promotion_performed": False,
                },
                sort_keys=True,
            )
        )
        return
    if not args.start_month or not args.end_month:
        parser.error("normal backtest mode requires --start-month and --end-month")
    if args.forecast_api_url is None:
        args.forecast_api_url = simple_api_from_xreg_url(args.xreg_api_url)
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
