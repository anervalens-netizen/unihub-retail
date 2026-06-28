from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from typing import Any, TypedDict

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from repositories.target_calculator import (
    TargetCalculatorRepository,
    TargetScenarioFinalizedError,
    TargetScenarioVersionConflict,
)
from services.forecast import get_forecast_factor

MONEY = Decimal("0.01")
DEFAULT_MIN_FLOOR = Decimal("35000")
DEFAULT_PREVIOUS_MONTH_FLOOR_PCT = Decimal("0.90")
DEFAULT_PREVIOUS_MONTH_CAP_PCT = Decimal("1.70")
DEFAULT_SEASONALITY_YEARS = 3
MAX_SEASONALITY_YEARS = 3
DEFAULT_TREND_WEIGHT = Decimal("0.10")
DEFAULT_TREND_ADJUSTMENT_MIN = Decimal("0.95")
DEFAULT_TREND_ADJUSTMENT_MAX = Decimal("1.10")
DEFAULT_SEASONALITY_MIN = Decimal("0.70")
DEFAULT_SEASONALITY_MAX = Decimal("1.70")
MIN_SEASONALITY_BASE = Decimal("10000")
CALCULATION_METHOD = "seasonal_blended_multiyear_v1"

STRONG_SEASONALITY_WEIGHTS = {
    "store": Decimal("0.50"),
    "zone": Decimal("0.30"),
    "network": Decimal("0.20"),
}
WEAK_SEASONALITY_WEIGHTS = {
    "store": Decimal("0.30"),
    "zone": Decimal("0.40"),
    "network": Decimal("0.30"),
}
NEW_STORE_SEASONALITY_WEIGHTS = {
    "store": Decimal("0"),
    "zone": Decimal("0.60"),
    "network": Decimal("0.40"),
}


class SourceMetric(TypedDict):
    target: Decimal
    actual_realized: Decimal
    realized: Decimal
    forecast_factor: Decimal
    is_forecast: bool


class PeriodTotals(TypedDict):
    target: Decimal
    realized: Decimal


class SeasonalityPair(TypedDict):
    year_offset: int
    base_month: str
    target_month: str


def money(value: Decimal | int | str | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def percent_change(new_value: float, base_value: float) -> float | None:
    if base_value <= 0:
        return None
    return round((new_value - base_value) * 100 / base_value, 2)


def realized_for_calculation(actual_realized: Decimal, forecast_factor: Decimal) -> Decimal:
    return money(actual_realized * forecast_factor)


def shift_month(month: str, offset: int) -> str:
    try:
        year, month_number = (int(value) for value in month.split("-"))
        if month_number < 1 or month_number > 12:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Luna trebuie sa fie in format YYYY-MM") from exc
    index = year * 12 + month_number - 1 + offset
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def source_month_configuration(target_month: str) -> list[dict[str, str]]:
    pairs = seasonality_pair_configuration(target_month, DEFAULT_SEASONALITY_YEARS)
    return build_source_month_configuration(target_month, pairs)


def seasonality_pair_configuration(target_month: str, years: int) -> list[SeasonalityPair]:
    years = max(1, min(int(years), MAX_SEASONALITY_YEARS))
    return [
        {
            "year_offset": year_offset,
            "base_month": shift_month(target_month, -1 - 12 * year_offset),
            "target_month": shift_month(target_month, -12 * year_offset),
        }
        for year_offset in range(1, years + 1)
    ]


def build_source_month_configuration(target_month: str, pairs: list[SeasonalityPair]) -> list[dict[str, str]]:
    source_months: list[dict[str, str]] = []
    for pair in sorted(pairs, key=lambda item: item["base_month"]):
        source_months.extend([
            {
                "month": pair["base_month"],
                "label": f"Baza sezoniera Y-{pair['year_offset']}",
                "role": f"seasonality_base_y{pair['year_offset']}",
            },
            {
                "month": pair["target_month"],
                "label": f"Luna target Y-{pair['year_offset']}",
                "role": f"seasonality_target_y{pair['year_offset']}",
            },
        ])
    source_months.append({
        "month": shift_month(target_month, -1),
        "label": "Forecast luna curenta",
        "role": "floor_reference",
    })
    return source_months


def unique_months(months: list[str]) -> list[str]:
    return list(dict.fromkeys(months))


def clamp_decimal(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    return min(max(value, minimum), maximum)


def seasonal_year_weights(count: int) -> list[Decimal]:
    if count <= 1:
        return [Decimal("1")]
    if count == 2:
        return [Decimal("0.70"), Decimal("0.30")]
    return [Decimal("0.50"), Decimal("0.30"), Decimal("0.20")]


def weighted_ratio(
    pairs: list[SeasonalityPair],
    value_by_month: dict[str, Decimal],
    *,
    minimum_base: Decimal = Decimal("0"),
) -> tuple[Decimal | None, list[dict[str, Any]]]:
    usable: list[tuple[SeasonalityPair, Decimal]] = []
    details: list[dict[str, Any]] = []
    for pair in pairs:
        base_value = money(value_by_month.get(pair["base_month"], Decimal("0")))
        target_value = money(value_by_month.get(pair["target_month"], Decimal("0")))
        ratio = target_value / base_value if base_value > minimum_base and target_value > 0 else None
        details.append({
            "year_offset": pair["year_offset"],
            "base_month": pair["base_month"],
            "target_month": pair["target_month"],
            "base_value": float(base_value),
            "target_value": float(target_value),
            "ratio": float(ratio.quantize(Decimal("0.0001"))) if ratio is not None else None,
        })
        if ratio is not None:
            usable.append((pair, ratio))

    if not usable:
        return None, details

    weights = seasonal_year_weights(len(usable))
    factor = sum((ratio * weights[index] for index, (_, ratio) in enumerate(usable)), Decimal("0"))
    return factor, details


def weighted_available(components: dict[str, tuple[Decimal | None, Decimal]]) -> Decimal | None:
    total_weight = sum(weight for value, weight in components.values() if value is not None and weight > 0)
    if total_weight <= 0:
        return None
    return sum(
        (
            value * weight / total_weight
            for value, weight in components.values()
            if value is not None and weight > 0
        ),
        Decimal("0"),
    )


def allocate_with_floors(
    rows: list[dict[str, Any]],
    requested_total: Decimal,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Allocate a budget proportionally while honoring store minimums."""
    warnings: list[str] = []
    if not rows:
        return rows, warnings

    requested_total = money(requested_total)
    floor_total = sum((row["floor_target"] for row in rows), Decimal("0"))
    if floor_total > requested_total:
        for row in rows:
            row["proposed_target"] = money(row["floor_target"])
            row["is_floor_limited"] = True
        warnings.append(
            "Bugetul total este mai mic decat suma pragurilor minime; propunerea depaseste bugetul pentru a respecta floor-ul."
        )
        return rows, warnings

    remaining = set(range(len(rows)))
    assigned: dict[int, Decimal] = {}
    remaining_budget = requested_total

    while remaining:
        weight_total = sum((rows[index]["calculated_weight"] for index in remaining), Decimal("0"))
        allocations: dict[int, Decimal] = {}
        for index in remaining:
            if weight_total > 0:
                allocations[index] = remaining_budget * rows[index]["calculated_weight"] / weight_total
            else:
                allocations[index] = remaining_budget / Decimal(len(remaining))

        below_floor = {
            index for index in remaining
            if allocations[index] < rows[index]["floor_target"]
        }
        if not below_floor:
            assigned.update(allocations)
            break

        for index in below_floor:
            assigned[index] = rows[index]["floor_target"]
            remaining_budget -= rows[index]["floor_target"]
            rows[index]["is_floor_limited"] = True
        remaining -= below_floor

    for index, row in enumerate(rows):
        row["proposed_target"] = money(assigned[index])

    rounded_total = sum((row["proposed_target"] for row in rows), Decimal("0"))
    difference = requested_total - rounded_total
    if difference:
        adjustable = [
            row for row in rows
            if row["proposed_target"] + difference >= row["floor_target"]
        ]
        target_row = max(adjustable or rows, key=lambda row: row["proposed_target"])
        target_row["proposed_target"] = money(target_row["proposed_target"] + difference)

    return rows, warnings


def allocate_with_bounds(
    rows: list[dict[str, Any]],
    requested_total: Decimal,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Allocate proportionally while respecting lower and upper proposal bounds."""
    warnings: list[str] = []
    if not rows:
        return rows, warnings

    requested_total = money(requested_total)
    floor_total = sum((row["floor_target"] for row in rows), Decimal("0"))
    cap_total = sum((row["cap_target"] for row in rows), Decimal("0"))
    if floor_total > requested_total:
        for row in rows:
            row["proposed_target"] = money(row["floor_target"])
            row["is_floor_limited"] = True
            row["allocation_reason"] = "floor"
            row["flags"].append("FLOOR_APPLIED")
        warnings.append(
            "Bugetul total este mai mic decat suma pragurilor minime; propunerea depaseste bugetul pentru a respecta floor-ul."
        )
        return rows, warnings
    if cap_total < requested_total:
        for row in rows:
            row["proposed_target"] = money(row["cap_target"])
            row["is_cap_limited"] = True
            row["allocation_reason"] = "cap"
            row["flags"].append("CAP_APPLIED")
        warnings.append(
            "Bugetul total depaseste suma cap-urilor configurate; propunerea ramane sub buget pana la ajustare manageriala."
        )
        return rows, warnings

    remaining = set(range(len(rows)))
    assigned: dict[int, Decimal] = {}
    remaining_budget = requested_total

    while remaining:
        weight_total = sum((rows[index]["calculated_weight"] for index in remaining), Decimal("0"))
        allocations: dict[int, Decimal] = {}
        for index in remaining:
            if weight_total > 0:
                allocations[index] = remaining_budget * rows[index]["calculated_weight"] / weight_total
            else:
                allocations[index] = remaining_budget / Decimal(len(remaining))

        fixed = False
        for index in list(remaining):
            row = rows[index]
            if allocations[index] < row["floor_target"]:
                assigned[index] = row["floor_target"]
                remaining_budget -= row["floor_target"]
                remaining.remove(index)
                row["is_floor_limited"] = True
                row["allocation_reason"] = "floor"
                row["flags"].append("FLOOR_APPLIED")
                fixed = True
            elif allocations[index] > row["cap_target"]:
                assigned[index] = row["cap_target"]
                remaining_budget -= row["cap_target"]
                remaining.remove(index)
                row["is_cap_limited"] = True
                row["allocation_reason"] = "cap"
                row["flags"].append("CAP_APPLIED")
                fixed = True

        if not fixed:
            assigned.update(allocations)
            break

    for index, row in enumerate(rows):
        row["proposed_target"] = money(assigned[index])

    rounded_total = sum((row["proposed_target"] for row in rows), Decimal("0"))
    difference = requested_total - rounded_total
    if difference:
        if difference > 0:
            adjustable = [
                row for row in rows
                if row["proposed_target"] + difference <= row["cap_target"]
            ]
            target_row = max(adjustable or rows, key=lambda row: row["cap_target"] - row["proposed_target"])
        else:
            adjustable = [
                row for row in rows
                if row["proposed_target"] + difference >= row["floor_target"]
            ]
            target_row = max(adjustable or rows, key=lambda row: row["proposed_target"] - row["floor_target"])
        target_row["proposed_target"] = money(target_row["proposed_target"] + difference)
        if target_row["proposed_target"] > target_row["cap_target"]:
            target_row["is_cap_limited"] = True
            target_row["flags"].append("CAP_APPLIED")
        if target_row["proposed_target"] < target_row["floor_target"]:
            target_row["is_floor_limited"] = True
            target_row["flags"].append("FLOOR_APPLIED")

    final_total = sum((row["proposed_target"] for row in rows), Decimal("0"))
    if final_total != requested_total:  # pragma: no cover - defensive guard after cent-level correction
        warnings.append(
            "Rotunjirea sau limitarile floor/cap au lasat propunerea diferita de bugetul total; verifica ajustarile finale."
        )

    return rows, warnings


class TargetCalculatorService:
    def __init__(self, repo: TargetCalculatorRepository):
        self.repo = repo

    async def get_context(self) -> dict[str, Any]:
        latest_month = await self.repo.get_latest_sales_month()
        if not latest_month:
            raise HTTPException(status_code=404, detail="Nu exista date de vanzari pentru calculator.")
        suggested_month = shift_month(latest_month, 1)
        target_total = await self.repo.get_target_total(suggested_month)
        if target_total == 0:
            target_total = await self.repo.get_target_total(latest_month)
        cohort = await self.repo.get_active_cohort(latest_month, suggested_month)
        return {
            "latest_sales_month": latest_month,
            "suggested_target_month": suggested_month,
            "suggested_cohort_month": latest_month,
            "suggested_total_target": float(target_total),
            "default_min_floor": float(DEFAULT_MIN_FLOOR),
            "default_previous_month_floor_pct": float(DEFAULT_PREVIOUS_MONTH_FLOOR_PCT),
            "default_previous_month_cap_pct": float(DEFAULT_PREVIOUS_MONTH_CAP_PCT),
            "default_seasonality_years": DEFAULT_SEASONALITY_YEARS,
            "active_store_count": len(cohort),
            "regionals": sorted({row["regional"] for row in cohort}),
        }

    async def calculate(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_month = payload["target_month"]
        seasonality_years = int(payload.get("seasonality_years") or DEFAULT_SEASONALITY_YEARS)
        seasonality_years = max(1, min(seasonality_years, MAX_SEASONALITY_YEARS))
        source_pairs = seasonality_pair_configuration(target_month, seasonality_years)
        source_months = build_source_month_configuration(target_month, source_pairs)
        latest_before_target = await self.repo.get_latest_sales_month(before_month=target_month)
        cohort_month = payload.get("cohort_month") or latest_before_target
        if not cohort_month:
            raise HTTPException(
                status_code=400,
                detail="Nu exista o luna cu vanzari anterioara lunii pentru care se calculeaza targetul.",
            )
        if cohort_month >= target_month:
            raise HTTPException(
                status_code=400,
                detail="Cohorta activa trebuie sa provina dintr-o luna anterioara lunii de target.",
            )

        cohort = await self.repo.get_active_cohort(cohort_month, target_month)
        if not cohort:
            raise HTTPException(status_code=400, detail="Luna de cohorta nu are magazine active.")

        total_target = money(payload["total_target"])
        min_floor = money(payload.get("min_floor", DEFAULT_MIN_FLOOR))
        floor_pct = Decimal(str(payload.get("previous_month_floor_pct", DEFAULT_PREVIOUS_MONTH_FLOOR_PCT)))
        cap_pct = Decimal(str(payload.get("previous_month_cap_pct", DEFAULT_PREVIOUS_MONTH_CAP_PCT)))
        trend_weight = Decimal(str(payload.get("trend_weight", DEFAULT_TREND_WEIGHT)))
        seasonality_min = Decimal(str(payload.get("seasonality_min", DEFAULT_SEASONALITY_MIN)))
        seasonality_max = Decimal(str(payload.get("seasonality_max", DEFAULT_SEASONALITY_MAX)))
        trend_min = Decimal(str(payload.get("trend_adjustment_min", DEFAULT_TREND_ADJUSTMENT_MIN)))
        trend_max = Decimal(str(payload.get("trend_adjustment_max", DEFAULT_TREND_ADJUSTMENT_MAX)))
        if (
            total_target <= 0
            or min_floor < 0
            or floor_pct < 0
            or cap_pct <= 0
            or cap_pct < floor_pct
            or trend_weight < 0
            or seasonality_min <= 0
            or seasonality_max < seasonality_min
            or trend_min <= 0
            or trend_max < trend_min
        ):
            raise HTTPException(status_code=400, detail="Parametrii de calcul nu sunt valizi.")

        months = unique_months([item["month"] for item in source_months])
        site_codes = [row["site_code"] for row in cohort]
        metrics = await self.repo.get_source_metrics(site_codes, months)
        async with self.repo.pool.acquire() as conn:
            forecast_factors = {
                month: Decimal(str(await get_forecast_factor(conn, month)))
                for month in months
            }
        metric_map: dict[tuple[str, str], SourceMetric] = {
            (row["site_code"], row["import_month"]): {
                "target": Decimal(row["target"] or 0),
                "actual_realized": money(Decimal(row["realized"] or 0)),
                "realized": realized_for_calculation(
                    Decimal(row["realized"] or 0),
                    forecast_factors[row["import_month"]],
                ),
                "forecast_factor": forecast_factors[row["import_month"]],
                "is_forecast": forecast_factors[row["import_month"]] > Decimal("1"),
            }
            for row in metrics
        }
        for site_code in site_codes:
            for month in months:
                metric_map.setdefault((site_code, month), {
                    "target": Decimal("0"),
                    "actual_realized": Decimal("0"),
                    "realized": Decimal("0"),
                    "forecast_factor": forecast_factors[month],
                    "is_forecast": forecast_factors[month] > Decimal("1"),
                })
        totals: dict[str, PeriodTotals] = {
            month: {
                "target": sum((metric_map[(site_code, month)]["target"] for site_code in site_codes), Decimal("0")),
                "realized": sum((metric_map[(site_code, month)]["realized"] for site_code in site_codes), Decimal("0")),
            }
            for month in months
        }
        regionals = sorted({row["regional"] for row in cohort})
        site_regional = {row["site_code"]: row["regional"] for row in cohort}
        regional_month_values: dict[tuple[str, str], Decimal] = {
            (regional, month): sum(
                (
                    metric_map[(site_code, month)]["realized"]
                    for site_code in site_codes
                    if site_regional[site_code] == regional
                ),
                Decimal("0"),
            )
            for regional in regionals
            for month in months
        }

        warnings: list[str] = []
        for item in source_months:
            total = totals[item["month"]]
            if total["target"] == 0 and total["realized"] == 0:
                warnings.append(f"Nu exista date pentru perioada de referinta {item['month']}.")
            if forecast_factors[item["month"]] > Decimal("1"):
                warnings.append(
                    f"Perioada {item['month']} este partiala; vanzarile folosite in calcul sunt forecastate "
                    f"cu factor {forecast_factors[item['month']]:.4f}x pe baza importului disponibil."
                )
        if seasonality_years > 1:
            warnings.append(
                f"Formula foloseste sezonalitate multi-year pe pana la {seasonality_years} ani; anii fara date suficiente sunt sariti automat."
            )

        calculated_rows: list[dict[str, Any]] = []
        current_month = shift_month(target_month, -1)
        network_values = {month: totals[month]["realized"] for month in months}
        network_factor, network_years = weighted_ratio(source_pairs, network_values)
        if network_factor is None:
            network_factor = Decimal("1")
        for cohort_row in cohort:
            site_code = cohort_row["site_code"]
            regional = cohort_row["regional"]
            history: list[dict[str, Any]] = []
            for item in source_months:
                metric = metric_map[(site_code, item["month"])]
                total = totals[item["month"]]
                shares: list[Decimal] = []
                if total["target"] > 0:
                    shares.append(metric["target"] / total["target"])
                if total["realized"] > 0:
                    shares.append(metric["realized"] / total["realized"])
                period_weight = sum(shares, Decimal("0")) / Decimal(len(shares)) if shares else Decimal("0")
                attainment = (
                    metric["realized"] / metric["target"] * Decimal("100")
                    if metric["target"] > 0 else None
                )
                history.append({
                    "month": item["month"],
                    "label": item["label"],
                    "role": item["role"],
                    "target": float(money(metric["target"])),
                    "realized": float(money(metric["realized"])),
                    "actual_realized": float(money(metric["actual_realized"])),
                    "is_forecast": metric["is_forecast"],
                    "forecast_factor": float(metric["forecast_factor"]),
                    "attainment_pct": float(attainment.quantize(MONEY)) if attainment is not None else None,
                    "weight": float(period_weight),
                })

            store_values = {month: metric_map[(site_code, month)]["realized"] for month in months}
            regional_values = {month: regional_month_values[(regional, month)] for month in months}
            store_factor, store_years = weighted_ratio(
                source_pairs,
                store_values,
                minimum_base=MIN_SEASONALITY_BASE,
            )
            zone_factor, zone_years = weighted_ratio(source_pairs, regional_values)
            last_year_store_factor, _ = weighted_ratio(source_pairs[:1], store_values, minimum_base=MIN_SEASONALITY_BASE)
            multiyear_store_factor, _ = weighted_ratio(source_pairs, store_values, minimum_base=MIN_SEASONALITY_BASE)

            weights = STRONG_SEASONALITY_WEIGHTS
            flags: list[str] = []
            usable_store_years = sum(1 for item in store_years if item["ratio"] is not None)
            store_ratios = [
                Decimal(str(item["ratio"]))
                for item in store_years
                if item["ratio"] is not None
            ]
            if store_factor is None:
                weights = NEW_STORE_SEASONALITY_WEIGHTS
                flags.extend(["NEW_STORE", "LOW_HISTORY"])
            elif usable_store_years <= 1 and seasonality_years > 1:
                weights = WEAK_SEASONALITY_WEIGHTS
                flags.append("LOW_HISTORY")
            elif (
                seasonality_years > 1
                and any(item["year_offset"] == 1 and item["ratio"] is None for item in store_years)
            ):
                weights = WEAK_SEASONALITY_WEIGHTS
                flags.append("LOW_RECENT_HISTORY")
            if store_ratios and (min(store_ratios) < Decimal("0.50") or max(store_ratios) > Decimal("2.00")):
                weights = WEAK_SEASONALITY_WEIGHTS
                flags.append("EXTREME_SEASONALITY")

            blended = weighted_available({
                "store": (store_factor, weights["store"]),
                "zone": (zone_factor, weights["zone"]),
                "network": (network_factor, weights["network"]),
            })
            raw_blended = blended if blended is not None else Decimal("1")
            seasonality_factor = clamp_decimal(raw_blended, seasonality_min, seasonality_max)
            if seasonality_factor != raw_blended:
                flags.append("SEASONALITY_CAPPED")

            current_forecast = metric_map[(site_code, current_month)]["realized"]
            trend_base = metric_map[(site_code, source_pairs[0]["base_month"])]["realized"]
            if trend_base > MIN_SEASONALITY_BASE:
                trend_ratio = current_forecast / trend_base
                trend_adjustment_raw = Decimal("1") + ((trend_ratio - Decimal("1")) * trend_weight)
            else:
                trend_ratio = None
                trend_adjustment_raw = Decimal("1")
            trend_adjustment = clamp_decimal(trend_adjustment_raw, trend_min, trend_max)
            if trend_adjustment != trend_adjustment_raw:
                flags.append("TREND_ADJUSTMENT_CAPPED")

            raw_estimate = money(current_forecast * seasonality_factor * trend_adjustment)
            floor_target = max(min_floor, money(current_forecast * floor_pct))
            cap_target = max(floor_target, money(current_forecast * cap_pct))
            calculation_details = {
                "method": CALCULATION_METHOD,
                "seasonality_years": seasonality_years,
                "current_month": current_month,
                "current_forecast": float(money(current_forecast)),
                "seasonality": {
                    "store_factor": float(store_factor.quantize(Decimal("0.0001"))) if store_factor is not None else None,
                    "zone_factor": float(zone_factor.quantize(Decimal("0.0001"))) if zone_factor is not None else None,
                    "network_factor": float(network_factor.quantize(Decimal("0.0001"))),
                    "blended_factor": float(raw_blended.quantize(Decimal("0.0001"))),
                    "used_factor": float(seasonality_factor.quantize(Decimal("0.0001"))),
                    "last_year_store_factor": (
                        float(last_year_store_factor.quantize(Decimal("0.0001")))
                        if last_year_store_factor is not None else None
                    ),
                    "multiyear_store_factor": (
                        float(multiyear_store_factor.quantize(Decimal("0.0001")))
                        if multiyear_store_factor is not None else None
                    ),
                    "weights": {key: float(value) for key, value in weights.items()},
                    "store_years": store_years,
                    "zone_years": zone_years,
                    "network_years": network_years,
                    "min": float(seasonality_min),
                    "max": float(seasonality_max),
                },
                "trend": {
                    "base_month": source_pairs[0]["base_month"],
                    "ratio": float(trend_ratio.quantize(Decimal("0.0001"))) if trend_ratio is not None else None,
                    "weight": float(trend_weight),
                    "raw_adjustment": float(trend_adjustment_raw.quantize(Decimal("0.0001"))),
                    "used_adjustment": float(trend_adjustment.quantize(Decimal("0.0001"))),
                    "min": float(trend_min),
                    "max": float(trend_max),
                },
                "raw_estimate": float(raw_estimate),
                "floor_target": float(floor_target),
                "cap_target": float(cap_target),
                "flags": [],
                "allocation_reason": "proportional",
            }
            calculated_rows.append({
                "site_code": site_code,
                "locatie": cohort_row["locatie"],
                "firma": cohort_row["firma"],
                "regional": regional,
                "asm": cohort_row["asm"],
                "calculated_weight": raw_estimate,
                "floor_target": floor_target,
                "cap_target": cap_target,
                "proposed_target": Decimal("0"),
                "is_floor_limited": False,
                "is_cap_limited": False,
                "allocation_reason": "proportional",
                "flags": flags,
                "history": history,
                "calculation_details": calculation_details,
            })

        if sum((row["calculated_weight"] for row in calculated_rows), Decimal("0")) == 0:
            equal_weight = Decimal("1") / Decimal(len(calculated_rows))
            for row in calculated_rows:
                row["calculated_weight"] = equal_weight
                row["flags"].append("LOW_HISTORY")
            warnings.append("Datele istorice nu contin estimari sezoniere utilizabile; targetul a fost distribuit uniform.")
        else:
            raw_total = sum((row["calculated_weight"] for row in calculated_rows), Decimal("0"))
            for row in calculated_rows:
                row["calculated_weight"] = row["calculated_weight"] / raw_total

        calculated_rows, allocation_warnings = allocate_with_bounds(calculated_rows, total_target)
        warnings.extend(allocation_warnings)
        for row in calculated_rows:
            flags = list(dict.fromkeys(row["flags"]))
            row["calculation_details"]["flags"] = flags
            row["calculation_details"]["allocation_reason"] = row["allocation_reason"]
            row["calculation_details"]["is_floor_limited"] = row["is_floor_limited"]
            row["calculation_details"]["is_cap_limited"] = row["is_cap_limited"]
        try:
            scenario_id = await self.repo.save_draft_scenario(
                {
                    "target_month": target_month,
                    "cohort_month": cohort_month,
                    "total_target": total_target,
                    "min_floor": min_floor,
                    "previous_month_floor_pct": floor_pct,
                    "calculation_method": CALCULATION_METHOD,
                    "source_months": source_months,
                    "warnings": warnings,
                    "calculation_params": {
                        "seasonality_years": seasonality_years,
                        "seasonality_min": float(seasonality_min),
                        "seasonality_max": float(seasonality_max),
                        "trend_weight": float(trend_weight),
                        "trend_adjustment_min": float(trend_min),
                        "trend_adjustment_max": float(trend_max),
                        "previous_month_cap_pct": float(cap_pct),
                        "minimum_seasonality_base": float(MIN_SEASONALITY_BASE),
                        "strong_weights": {key: float(value) for key, value in STRONG_SEASONALITY_WEIGHTS.items()},
                        "weak_weights": {key: float(value) for key, value in WEAK_SEASONALITY_WEIGHTS.items()},
                        "new_store_weights": {key: float(value) for key, value in NEW_STORE_SEASONALITY_WEIGHTS.items()},
                    },
                },
                calculated_rows,
                payload.get("expected_revision"),
            )
        except TargetScenarioFinalizedError:
            raise HTTPException(
                status_code=409,
                detail="Targetul acestei luni a fost deja finalizat si nu mai poate fi recalculat.",
            ) from None
        except TargetScenarioVersionConflict:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Scenariul a fost modificat de alt utilizator. "
                    "Reincarca datele inainte de recalculare."
                ),
            ) from None
        return await self.get_scenario_detail(scenario_id)

    async def list_scenarios(self) -> list[dict[str, Any]]:
        rows = await self.repo.list_scenarios()
        return [self._serialize_header(dict(row)) for row in rows]

    async def get_scenario_detail(self, scenario_id: int) -> dict[str, Any]:
        scenario = await self.repo.get_scenario(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenariul de target nu exista.")
        rows = await self.repo.get_scenario_rows(scenario_id)
        header = self._serialize_header(dict(scenario))
        serialized_rows = [self._serialize_row(dict(row)) for row in rows]
        proposed_total = sum(row["proposed_target"] for row in serialized_rows)
        final_total = sum((row["final_target"] or 0) for row in serialized_rows)
        pending_final_count = sum(1 for row in serialized_rows if row["final_target"] is None)
        return {
            **header,
            "store_count": len(serialized_rows),
            "proposed_total": proposed_total,
            "final_total": final_total,
            "remaining_difference": header["total_target"] - final_total,
            "pending_final_count": pending_final_count,
            "floor_limited_count": sum(1 for row in serialized_rows if row["is_floor_limited"]),
            "manual_adjustments_count": sum(
                1 for row in serialized_rows
                if row["final_target"] is not None and abs(row["final_target"] - row["proposed_target"]) > 0.01
            ),
            "rows": serialized_rows,
            "regional_summary": self._regional_summary(serialized_rows),
            "source_summary": self._source_summary(serialized_rows),
        }

    async def save_final_targets(
        self,
        scenario_id: int,
        rows: list[dict[str, Any]],
        expected_revision: int,
    ) -> dict[str, Any]:
        if len({row["site_code"] for row in rows}) != len(rows):
            raise HTTPException(status_code=400, detail="Aceeasi locatie apare de mai multe ori in salvare.")
        try:
            updated = await self.repo.update_final_targets(
                scenario_id,
                rows,
                expected_revision,
            )
        except TargetScenarioVersionConflict:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Scenariul a fost modificat de alt utilizator. "
                    "Reincarca datele inainte de salvare."
                ),
            ) from None
        if updated != len(rows):
            scenario = await self.repo.get_scenario(scenario_id)
            if not scenario:
                raise HTTPException(status_code=404, detail="Scenariul de target nu exista.")
            if scenario["status"] != "draft":
                raise HTTPException(status_code=409, detail="Un scenariu finalizat nu mai poate fi editat.")
            raise HTTPException(status_code=400, detail="Una sau mai multe locatii nu apartin scenariului.")
        return await self.get_scenario_detail(scenario_id)

    async def finalize(self, scenario_id: int, expected_revision: int) -> dict[str, Any]:
        scenario = await self.get_scenario_detail(scenario_id)
        if scenario["calculation_method"] != CALCULATION_METHOD:
            raise HTTPException(
                status_code=409,
                detail="Scenariul a fost calculat cu o formula veche. Genereaza o propunere noua inainte de finalizare.",
            )
        if scenario["pending_final_count"] > 0:
            raise HTTPException(
                status_code=400,
                detail="Toate locatiile trebuie sa aiba target final completat inainte de finalizare.",
            )
        if money(scenario["final_total"]) != money(scenario["total_target"]):
            raise HTTPException(
                status_code=400,
                detail="Totalul targetelor finale trebuie sa fie egal cu bugetul scenariului inainte de finalizare.",
            )
        try:
            finalized = await self.repo.finalize_scenario(
                scenario_id,
                expected_revision,
            )
        except TargetScenarioVersionConflict:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Scenariul a fost modificat de alt utilizator. "
                    "Reincarca datele inainte de finalizare."
                ),
            ) from None
        if not finalized:
            raise HTTPException(status_code=409, detail="Scenariul nu poate fi finalizat.")
        return await self.get_scenario_detail(scenario_id)

    async def export_excel(self, scenario_id: int) -> tuple[BytesIO, str]:
        scenario = await self.get_scenario_detail(scenario_id)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Targete finale"
        source_months = scenario["source_months"]
        forecast_by_month = {
            period["month"]: any(
                history["month"] == period["month"] and history.get("is_forecast", False)
                for row in scenario["rows"]
                for history in row["history"]
            )
            for period in source_months
        }
        headers = ["Firma", "Regional", "ASM", "Nume locatie", "Cod locatie"]
        for period in source_months:
            headers.extend([
                f"Target {period['month']}",
                f"{'Forecast folosit' if forecast_by_month[period['month']] else 'Realizat folosit'} {period['month']}",
                f"Realizat importat {period['month']}",
                f"% Realizare {period['month']}",
            ])
        headers.extend([
            "Forecast luna curenta", "Sezonalitate magazin LY", "Sezonalitate magazin multi-year",
            "Sezonalitate zona", "Sezonalitate retea", "Sezonalitate folosita",
            "Ajustare trend", "Estimare bruta", "Floor", "Cap", "Pondere calcul",
            "Target propus", "Target final", "Diferenta final-propus", "Ajustat manual",
            "Flag-uri", "Observatii",
        ])
        sheet.append(headers)
        history_by_month: dict[str, dict[str, Any]]
        for row in scenario["rows"]:
            history_by_month = {period["month"]: period for period in row["history"]}
            values: list[Any] = [
                row["firma"], row["regional"], row["asm"], row["locatie"], row["site_code"],
            ]
            for period in source_months:
                history = history_by_month[period["month"]]
                values.extend([
                    history["target"],
                    history["realized"],
                    history.get("actual_realized", history["realized"]),
                    history["attainment_pct"],
                ])
            details = row.get("calculation_details") or {}
            seasonality = details.get("seasonality") or {}
            trend = details.get("trend") or {}
            values.extend([
                details.get("current_forecast"),
                seasonality.get("last_year_store_factor"),
                seasonality.get("multiyear_store_factor"),
                seasonality.get("zone_factor"),
                seasonality.get("network_factor"),
                seasonality.get("used_factor"),
                trend.get("used_adjustment"),
                details.get("raw_estimate"),
                row["floor_target"],
                details.get("cap_target"),
                row["calculated_weight"],
                row["proposed_target"],
                row["final_target"],
                None if row["final_target"] is None else row["final_target"] - row["proposed_target"],
                "Necompletat" if row["final_target"] is None
                else "Da" if abs(row["final_target"] - row["proposed_target"]) > 0.01 else "Nu",
                ", ".join(details.get("flags") or []),
                row["note"] or "",
            ])
            sheet.append(values)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions

        summary = workbook.create_sheet("Rezumat manageri")
        summary.append([
            "Regional", "Magazine", "Floor", "Target propus", "Target final", "Diferenta",
            "Luna curenta", "Forecast luna curenta", "% crestere propus vs luna curenta",
            "Baza anul trecut", "Target anul trecut", "Realizat baza anul trecut",
            "Realizat target anul trecut", "% crestere anul trecut",
        ])
        for row in scenario["regional_summary"]:
            summary.append([
                row["regional"], row["store_count"], row["floor_total"],
                row["proposed_total"], row["final_total"], row["final_total"] - row["proposed_total"],
                row.get("current_month"), row.get("current_forecast_total"), row.get("proposed_growth_vs_current_pct"),
                row.get("last_year_base_month"), row.get("last_year_target_month"),
                row.get("last_year_base_total"), row.get("last_year_target_total"),
                row.get("last_year_growth_pct"),
            ])

        parameters = workbook.create_sheet("Parametri")
        parameters.append(["Parametru", "Valoare"])
        parameters.append(["Scenariu", scenario["id"]])
        parameters.append(["Status", scenario["status"]])
        parameters.append(["Luna target", scenario["target_month"]])
        parameters.append(["Luna cohorta magazine active", scenario["cohort_month"]])
        parameters.append(["Target total", scenario["total_target"]])
        parameters.append(["Prag minim absolut", scenario["min_floor"]])
        parameters.append(["Floor fata de luna precedenta", scenario["previous_month_floor_pct"]])
        parameters.append(["Metoda", scenario["calculation_method"]])
        for key, value in (scenario.get("calculation_params") or {}).items():
            parameters.append([f"Parametru {key}", json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value])
        for item in scenario["source_months"]:
            parameters.append([item["label"], item["month"]])
        for item in scenario["source_summary"]:
            if item["is_forecast"]:
                parameters.append([
                    f"Forecast {item['month']}",
                    f"{item['forecast_factor']:.4f}x; importat {item['actual_realized']:.2f}; folosit {item['realized']:.2f}",
                ])
        for warning in scenario["warnings"]:
            parameters.append(["Atentionare", warning])

        for worksheet in workbook.worksheets:
            header_fill = PatternFill("solid", fgColor="4F46E5")
            for cell in worksheet[1]:
                cell.font = Font(color="FFFFFF", bold=True)
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")
            for column in worksheet.columns:
                letter = get_column_letter(column[0].column)
                max_length = max(len(str(cell.value or "")) for cell in column)
                worksheet.column_dimensions[letter].width = min(max(max_length + 2, 12), 34)

        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        stamp = datetime.now().strftime("%Y%m%d")
        return output, f"targete_{scenario['target_month']}_scenariu_{scenario_id}_{stamp}.xlsx"

    async def get_store_detail(self, scenario_id: int, site_code: str) -> dict[str, Any]:
        data = await self.repo.get_store_detail(scenario_id, site_code)
        if not data:
            raise HTTPException(status_code=404, detail="Locatia nu exista in documentul de target.")

        scenario = dict(data["scenario"])
        history = [self._serialize_store_history(dict(row)) for row in data["history"]]
        agents = [self._serialize_store_agent(dict(row)) for row in data["agents"]]
        latest = next((row for row in reversed(history) if row["total_sales"] > 0 or row["target_value"] > 0), None)
        sales_values = [row["total_sales"] for row in history]
        best_month = max(history, key=lambda row: row["total_sales"]) if history else None
        avg_sales = sum(sales_values) / len(sales_values) if sales_values else 0

        return {
            "site_code": scenario["site_code"],
            "locatie": scenario["locatie"],
            "firma": scenario["firma"],
            "regional": scenario["regional"],
            "asm": scenario["asm"],
            "target_month": scenario["target_month"],
            "cohort_month": scenario["cohort_month"],
            "proposed_target": float(scenario["proposed_target"] or 0),
            "final_target": float(scenario["final_target"]) if scenario["final_target"] is not None else None,
            "history": history,
            "latest": latest,
            "best_month": best_month,
            "avg_sales_16m": round(avg_sales, 2),
            "agents": agents,
        }

    def _serialize_header(self, row: dict[str, Any]) -> dict[str, Any]:
        for key in ("total_target", "min_floor", "previous_month_floor_pct", "proposed_total", "final_total"):
            if key in row:
                row[key] = float(row[key] or 0)
        for key in ("source_months", "warnings", "calculation_params"):
            if key in row and isinstance(row[key], str):
                row[key] = json.loads(row[key])
        row.setdefault("source_months", [])
        row.setdefault("warnings", [])
        row.setdefault("calculation_params", {})
        if "store_count" in row:
            row["store_count"] = int(row["store_count"])
        row["pending_final_count"] = int(row.get("pending_final_count") or 0)
        return row

    def _serialize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        for key in ("calculated_weight", "floor_target", "proposed_target"):
            row[key] = float(row[key] or 0)
        row["final_target"] = float(row["final_target"]) if row.get("final_target") is not None else None
        if isinstance(row.get("history"), str):
            row["history"] = json.loads(row["history"])
        if isinstance(row.get("calculation_details"), str):
            row["calculation_details"] = json.loads(row["calculation_details"])
        row.setdefault("calculation_details", {})
        return row

    def _regional_summary(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summary: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "store_count": 0,
                "floor_total": 0.0,
                "proposed_total": 0.0,
                "final_total": 0.0,
                "current_month": None,
                "current_forecast_total": 0.0,
                "last_year_base_month": None,
                "last_year_target_month": None,
                "last_year_base_total": 0.0,
                "last_year_target_total": 0.0,
            }
        )
        for row in rows:
            data = summary[row["regional"]]
            data["store_count"] += 1
            data["floor_total"] += row["floor_target"]
            data["proposed_total"] += row["proposed_target"]
            data["final_total"] += row["final_target"] or 0
            details = row.get("calculation_details") or {}
            if isinstance(details, str):
                details = json.loads(details)
            history = row.get("history") or []
            if isinstance(history, str):
                history = json.loads(history)

            current_month = details.get("current_month")
            current_forecast = details.get("current_forecast")
            if current_forecast is None:
                current_period = next((item for item in history if item.get("role") == "floor_reference"), None)
                current_month = current_month or (current_period or {}).get("month")
                current_forecast = (current_period or {}).get("realized")
            if current_month:
                data["current_month"] = current_month
            data["current_forecast_total"] += float(current_forecast or 0)

            seasonality = details.get("seasonality") or {}
            last_year = next(
                (item for item in seasonality.get("store_years") or [] if item.get("year_offset") == 1),
                None,
            )
            if last_year is None:
                base_period = next((item for item in history if item.get("role") == "seasonality_base_y1"), None)
                target_period = next((item for item in history if item.get("role") == "seasonality_target_y1"), None)
                last_year = {
                    "base_month": (base_period or {}).get("month"),
                    "target_month": (target_period or {}).get("month"),
                    "base_value": (base_period or {}).get("realized"),
                    "target_value": (target_period or {}).get("realized"),
                }
            if last_year.get("base_month"):
                data["last_year_base_month"] = last_year["base_month"]
            if last_year.get("target_month"):
                data["last_year_target_month"] = last_year["target_month"]
            data["last_year_base_total"] += float(last_year.get("base_value") or 0)
            data["last_year_target_total"] += float(last_year.get("target_value") or 0)
        return [
            {
                "regional": regional,
                **values,
                "proposed_growth_vs_current_pct": percent_change(
                    values["proposed_total"],
                    values["current_forecast_total"],
                ),
                "final_growth_vs_current_pct": percent_change(
                    values["final_total"],
                    values["current_forecast_total"],
                ),
                "last_year_growth_pct": percent_change(
                    values["last_year_target_total"],
                    values["last_year_base_total"],
                ),
            }
            for regional, values in sorted(summary.items())
        ]

    def _source_summary(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summary: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "target": 0.0,
                "realized": 0.0,
                "actual_realized": 0.0,
                "is_forecast": False,
                "forecast_factor": 1.0,
                "label": "",
            }
        )
        for row in rows:
            for period in row["history"]:
                values = summary[period["month"]]
                values["label"] = period["label"]
                values["target"] += period["target"]
                values["realized"] += period["realized"]
                values["actual_realized"] += period.get("actual_realized", period["realized"])
                if period.get("is_forecast", False):
                    values["is_forecast"] = True
                    values["forecast_factor"] = period.get("forecast_factor", 1.0)
        return [
            {
                "month": month,
                **values,
                "attainment_pct": values["realized"] / values["target"] * 100 if values["target"] else None,
            }
            for month, values in summary.items()
        ]

    def _serialize_store_history(self, row: dict[str, Any]) -> dict[str, Any]:
        total_sales = float(row["total_sales"] or 0)
        target = float(row["target_value"] or 0)
        total_quantity = int(row["total_quantity"] or 0)
        receipt_count = int(row["receipt_count"] or 0)
        receipt_2plus = int(row["receipt_2plus_count"] or 0)
        focus_quantity = int(row["focus_quantity"] or 0)
        return {
            "month": row["import_month"],
            "total_sales": total_sales,
            "target_value": target,
            "target_pct": total_sales / target * 100 if target else None,
            "total_quantity": total_quantity,
            "receipt_count": receipt_count,
            "cartele_qty": int(row["cartele_qty"] or 0),
            "avg_receipt": total_sales / receipt_count if receipt_count else None,
            "bon2acc_pct": receipt_2plus / receipt_count * 100 if receipt_count else None,
            "focus_pct": focus_quantity / total_quantity * 100 if total_quantity else None,
            "active_agents": int(row["active_agents"] or 0),
            "working_days": int(row["working_days"] or 0),
        }

    def _serialize_store_agent(self, row: dict[str, Any]) -> dict[str, Any]:
        total_sales = float(row["total_sales"] or 0)
        total_quantity = int(row["total_quantity"] or 0)
        receipt_count = int(row["receipt_count"] or 0)
        receipt_2plus = int(row["receipt_2plus_count"] or 0)
        focus_quantity = int(row["focus_quantity"] or 0)
        return {
            "agent": row["agent"],
            "total_sales": total_sales,
            "sales_share_pct": float(row["sales_share_pct"] or 0),
            "total_quantity": total_quantity,
            "receipt_count": receipt_count,
            "avg_receipt": total_sales / receipt_count if receipt_count else None,
            "bon2acc_pct": receipt_2plus / receipt_count * 100 if receipt_count else None,
            "focus_pct": focus_quantity / total_quantity * 100 if total_quantity else None,
            "active_months_16": int(row["active_months_16"] or 0),
            "sales_16m": float(row["sales_16m"] or 0),
        }
