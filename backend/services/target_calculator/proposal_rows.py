"""Pure row projection helpers for Target proposal calculation."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from services.target_calculator.calculations import MONEY, money
from services.target_calculator.rules import clamp_decimal, weighted_available
from services.target_calculator.seasonality import shift_month, weighted_ratio


def _store_history(
    site_code: str,
    source_months: list[dict[str, Any]],
    metrics: Any,
) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for item in source_months:
        metric = metrics.metric_map[(site_code, item["month"])]
        total = metrics.totals[item["month"]]
        shares: list[Decimal] = []
        if total["target"] > 0:
            shares.append(metric["target"] / total["target"])
        if total["realized"] > 0:
            shares.append(metric["realized"] / total["realized"])
        period_weight = sum(shares, Decimal("0")) / Decimal(len(shares)) if shares else Decimal("0")
        attainment = metric["realized"] / metric["target"] * Decimal("100") if metric["target"] > 0 else None
        history.append({
            "month": item["month"], "label": item["label"], "role": item["role"],
            "target": float(money(metric["target"])), "realized": float(money(metric["realized"])),
            "actual_realized": float(money(metric["actual_realized"])), "is_forecast": metric["is_forecast"],
            "forecast_factor": float(metric["forecast_factor"]),
            "attainment_pct": float(attainment.quantize(MONEY)) if attainment is not None else None,
            "weight": float(period_weight),
        })
    return history


def _seasonality_result(
    context: Any,
    scope: Any,
    metrics: Any,
    site_code: str,
    regional: str,
    network_factor: Decimal,
) -> dict[str, Any]:
    store_values = {month: metrics.metric_map[(site_code, month)]["realized"] for month in metrics.months}
    regional_values = {month: metrics.regional_month_values[(regional, month)] for month in metrics.months}
    store_factor, store_years = weighted_ratio(
        scope.source_pairs, store_values, minimum_base=context.minimum_seasonality_base,
    )
    zone_factor, zone_years = weighted_ratio(scope.source_pairs, regional_values)
    last_year_store_factor, _ = weighted_ratio(
        scope.source_pairs[:1], store_values, minimum_base=context.minimum_seasonality_base,
    )
    multiyear_store_factor, _ = weighted_ratio(
        scope.source_pairs, store_values, minimum_base=context.minimum_seasonality_base,
    )
    weights = context.strong_seasonality_weights
    flags: list[str] = []
    usable_store_years = sum(1 for item in store_years if item["ratio"] is not None)
    store_ratios = [Decimal(str(item["ratio"])) for item in store_years if item["ratio"] is not None]
    if store_factor is None:
        weights = context.new_store_seasonality_weights
        flags.extend(["NEW_STORE", "LOW_HISTORY"])
    elif usable_store_years <= 1 and scope.seasonality_years > 1:
        weights = context.weak_seasonality_weights
        flags.append("LOW_HISTORY")
    elif scope.seasonality_years > 1 and any(
        item["year_offset"] == 1 and item["ratio"] is None for item in store_years
    ):
        weights = context.weak_seasonality_weights
        flags.append("LOW_RECENT_HISTORY")
    if store_ratios and (min(store_ratios) < Decimal("0.50") or max(store_ratios) > Decimal("2.00")):
        weights = context.weak_seasonality_weights
        flags.append("EXTREME_SEASONALITY")
    blended = weighted_available({
        "store": (store_factor, weights["store"]),
        "zone": (zone_factor, weights["zone"]),
        "network": (network_factor, weights["network"]),
    })
    raw_blended = blended if blended is not None else Decimal("1")
    factor = clamp_decimal(raw_blended, scope.parameters.seasonality_min, scope.parameters.seasonality_max)
    if factor != raw_blended:
        flags.append("SEASONALITY_CAPPED")
    return {
        "store_factor": store_factor, "zone_factor": zone_factor, "store_years": store_years,
        "zone_years": zone_years, "last_year_store_factor": last_year_store_factor,
        "multiyear_store_factor": multiyear_store_factor, "weights": weights, "flags": flags,
        "raw_blended": raw_blended, "factor": factor,
    }


def _calculated_store_row(
    context: Any,
    scope: Any,
    metrics: Any,
    cohort_row: Any,
    network_factor: Decimal,
    network_years: list[dict[str, Any]],
) -> dict[str, Any]:
    site_code = cohort_row["site_code"]
    regional = cohort_row["regional"]
    result = _seasonality_result(context, scope, metrics, site_code, regional, network_factor)
    current_month = shift_month(scope.target_month, -1)
    current_forecast = metrics.metric_map[(site_code, current_month)]["realized"]
    trend_base = metrics.metric_map[(site_code, scope.source_pairs[0]["base_month"])]["realized"]
    if trend_base > context.minimum_seasonality_base:
        trend_ratio = current_forecast / trend_base
        trend_raw = Decimal("1") + ((trend_ratio - Decimal("1")) * scope.parameters.trend_weight)
    else:
        trend_ratio = None
        trend_raw = Decimal("1")
    trend_adjustment = clamp_decimal(trend_raw, scope.parameters.trend_min, scope.parameters.trend_max)
    if trend_adjustment != trend_raw:
        result["flags"].append("TREND_ADJUSTMENT_CAPPED")
    raw_estimate = money(current_forecast * result["factor"] * trend_adjustment)
    floor_target = max(scope.parameters.min_floor, money(current_forecast * scope.parameters.floor_pct))
    cap_target = max(floor_target, money(current_forecast * scope.parameters.cap_pct))
    details = {
        "method": context.calculation_method, "seasonality_years": scope.seasonality_years,
        "current_month": current_month, "current_forecast": float(money(current_forecast)),
        "seasonality": {
            "store_factor": float(result["store_factor"].quantize(Decimal("0.0001"))) if result["store_factor"] is not None else None,
            "zone_factor": float(result["zone_factor"].quantize(Decimal("0.0001"))) if result["zone_factor"] is not None else None,
            "network_factor": float(network_factor.quantize(Decimal("0.0001"))),
            "blended_factor": float(result["raw_blended"].quantize(Decimal("0.0001"))),
            "used_factor": float(result["factor"].quantize(Decimal("0.0001"))),
            "last_year_store_factor": float(result["last_year_store_factor"].quantize(Decimal("0.0001"))) if result["last_year_store_factor"] is not None else None,
            "multiyear_store_factor": float(result["multiyear_store_factor"].quantize(Decimal("0.0001"))) if result["multiyear_store_factor"] is not None else None,
            "weights": {key: float(value) for key, value in result["weights"].items()},
            "store_years": result["store_years"], "zone_years": result["zone_years"],
            "network_years": network_years, "min": float(scope.parameters.seasonality_min),
            "max": float(scope.parameters.seasonality_max),
        },
        "trend": {
            "base_month": scope.source_pairs[0]["base_month"],
            "ratio": float(trend_ratio.quantize(Decimal("0.0001"))) if trend_ratio is not None else None,
            "weight": float(scope.parameters.trend_weight),
            "raw_adjustment": float(trend_raw.quantize(Decimal("0.0001"))),
            "used_adjustment": float(trend_adjustment.quantize(Decimal("0.0001"))),
            "min": float(scope.parameters.trend_min), "max": float(scope.parameters.trend_max),
        },
        "raw_estimate": float(raw_estimate), "floor_target": float(floor_target),
        "cap_target": float(cap_target), "flags": [], "allocation_reason": "proportional",
    }
    return {
        "site_code": site_code, "locatie": cohort_row["locatie"], "firma": cohort_row["firma"],
        "regional": regional, "asm": cohort_row["asm"], "calculated_weight": raw_estimate,
        "floor_target": floor_target, "cap_target": cap_target, "proposed_target": Decimal("0"),
        "is_floor_limited": False, "is_cap_limited": False, "allocation_reason": "proportional",
        "flags": result["flags"], "history": _store_history(site_code, scope.source_months, metrics),
        "calculation_details": details,
    }


def _calculated_rows(
    context: Any, scope: Any, metrics: Any,
) -> list[dict[str, Any]]:
    network_values = {month: metrics.totals[month]["realized"] for month in metrics.months}
    network_factor, network_years = weighted_ratio(scope.source_pairs, network_values)
    network_factor = network_factor if network_factor is not None else Decimal("1")
    return [
        _calculated_store_row(context, scope, metrics, row, network_factor, network_years)
        for row in scope.cohort
    ]
