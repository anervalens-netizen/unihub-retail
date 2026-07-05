from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
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
    MetricName,
    StoreInfo,
    add_month,
    build_payload,
    fetch_active_stores,
    fetch_monthly_sales,
    metric_value,
    month_range,
    pct,
    post_forecast,
    seasonal_last3_fallback,
    write_csv,
)


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
) -> dict[str, list[dict[str, Decimal | None]]]:
    predictions: dict[str, list[dict[str, Decimal | None]]] = {}
    for row in response.get("series", []):
        series_id = str(row["series_id"])
        point_values = row.get("point_forecast") or []
        quantile_rows = row.get("quantile_forecast") or []
        parsed: list[dict[str, Decimal | None]] = []
        for index, value in enumerate(point_values):
            quantiles = parse_quantile_row(
                quantile_rows[index] if index < len(quantile_rows) else None,
                metric=metric,
            )
            parsed.append({"point": as_decimal(value, metric), **quantiles})
        if parsed:
            predictions[series_id] = parsed
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


async def run(args: argparse.Namespace) -> int:
    load_dotenv(args.env_file)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL lipseste.")

    models = parse_models(args.models)
    remote_models = [model for model in models if model in REMOTE_SIMPLE_MODELS or model in REMOTE_XREG_MODES]
    api_key = args.api_key or os.environ.get("TIMESFM_API_KEY")
    if remote_models and not api_key:
        raise RuntimeError("TIMESFM_API_KEY lipseste pentru modelele remote.")

    target_months = month_range(args.start_month, args.end_month)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    conn = await asyncpg.connect(database_url)
    all_rows: list[dict[str, Any]] = []
    try:
        stores = await fetch_active_stores(conn, excluded_site_codes=args.exclude_site_code)
        if not stores:
            raise RuntimeError("Nu exista magazine active pentru backtest.")
        sales = await fetch_monthly_sales(
            conn,
            site_codes=[store.site_code for store in stores],
            start_month=args.history_start_month,
            end_month=args.end_month,
            metric=args.metric,
        )
    finally:
        await conn.close()

    for model in models:
        print(f"Model {model}: start")
        for target_month in target_months:
            source_month = add_month(target_month, -1)
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
            else:
                payload, meta_rows, skipped = build_payload(
                    stores=stores,
                    sales=sales,
                    target_months=[target_month],
                    source_month=source_month,
                    history_start_month=args.history_start_month,
                    min_context=args.min_context,
                    metric=args.metric,
                )
                if not payload["inputs"]:
                    month_rows = []
                else:
                    if model in REMOTE_XREG_MODES:
                        payload["xreg_mode"] = REMOTE_XREG_MODES[model]
                        api_url = args.xreg_api_url
                    else:
                        payload = {
                            "horizon": payload["horizon"],
                            "inputs": payload["inputs"],
                            "series_ids": payload["series_ids"],
                        }
                        api_url = args.forecast_api_url
                    started = datetime.now()
                    response = post_forecast(api_url, api_key or "", payload, args.timeout)
                    latency = (datetime.now() - started).total_seconds()
                    predictions = parse_forecast_response(response, metric=args.metric)
                    month_rows = model_result_rows(
                        model=model,
                        target_months=[target_month],
                        meta_rows=meta_rows,
                        actuals=sales,
                        predictions=predictions,
                        metric=args.metric,
                    )
                    for row in month_rows:
                        row["latency_sec"] = round(latency, 3)
                if args.include_fallback:
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
                if skipped and not args.include_fallback:
                    print(f"  {target_month}: {len(skipped)} serii sarite fara fallback")
            all_rows.extend(month_rows)
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

    suffix = f"{args.metric}_{args.start_month}_to_{args.end_month}"
    store_path = output_dir / f"backtest_comparison_store_{suffix}.csv"
    summary_path = output_dir / f"backtest_comparison_summary_{suffix}.csv"
    metrics_path = output_dir / f"backtest_comparison_model_metrics_{suffix}.csv"
    overall_path = output_dir / f"backtest_comparison_overall_{suffix}.json"

    store_fields = [
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
    metric_fields = [
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
    write_csv(store_path, all_rows, store_fields)
    summary_rows = model_month_summaries(all_rows, metric=args.metric)
    metrics_rows = model_metrics(all_rows, metric=args.metric)
    write_csv(summary_path, summary_rows, metric_fields)
    write_csv(metrics_path, metrics_rows, metric_fields)
    overall = [
        row
        for row in metrics_rows
        if row["group_level"] == "network"
    ]
    overall_path.write_text(json.dumps(overall, indent=2, default=str), encoding="utf-8")

    print(f"Output store: {store_path.resolve()}")
    print(f"Output summary: {summary_path.resolve()}")
    print(f"Output metrics: {metrics_path.resolve()}")
    print(f"Output overall: {overall_path.resolve()}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compara baseline-uri si modele TimesFM/XReg prin backtesting lunar walk-forward."
    )
    parser.add_argument("--start-month", required=True, help="Prima luna tinta, YYYY-MM.")
    parser.add_argument("--end-month", required=True, help="Ultima luna tinta, YYYY-MM.")
    parser.add_argument("--metric", choices=["sales_value", "units"], default="sales_value")
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
    parser.add_argument("--no-fallback", action="store_false", dest="include_fallback")
    parser.set_defaults(include_fallback=True)
    args = parser.parse_args()
    if args.forecast_api_url is None:
        args.forecast_api_url = simple_api_from_xreg_url(args.xreg_api_url)
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
