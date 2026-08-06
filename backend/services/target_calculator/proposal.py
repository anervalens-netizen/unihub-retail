"""Typed normalization and validation for Target proposal inputs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Awaitable, Callable, TypedDict

from fastapi import HTTPException

from repositories.target_calculator import (
    TargetScenarioAlgorithmMismatch,
    TargetScenarioFinalizedError,
    TargetScenarioVersionConflict,
)
from services.target_calculator.calculations import (
    MONEY,
    TargetBudgetInfeasibleError,
    money,
)
from services.target_calculator.profitability import (
    ProfitabilityConstants,
    forecast_coverage,
    forecast_coverage_error,
    populate_profitability,
    profitability_input_payload,
)
from services.target_calculator.rules import (
    canonical_input_hash,
    clamp_decimal,
    realized_for_calculation,
    unique_months,
    weighted_available,
)
from services.target_calculator.seasonality import (
    build_source_month_configuration,
    seasonality_pair_configuration,
    shift_month,
    weighted_ratio,
)
from services.target_calculator.warnings import unique_warnings
from services.target_rule_registry import (
    TargetRuleSetValidationError,
    profitability_assumptions as rule_set_profitability_assumptions,
    validate_store_exception_scope,
    validate_target_rule_set,
)


def normalize_proposal_parameters(
    payload: dict[str, Any],
    *,
    default_min_floor: Decimal,
    default_floor_pct: Decimal,
    default_cap_pct: Decimal,
    default_trend_weight: Decimal,
    default_seasonality_min: Decimal,
    default_seasonality_max: Decimal,
    default_trend_min: Decimal,
    default_trend_max: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    total_target = money(payload["total_target"])
    min_floor = money(payload.get("min_floor", default_min_floor))
    floor_pct = Decimal(str(payload.get("previous_month_floor_pct", default_floor_pct)))
    cap_pct = Decimal(str(payload.get("previous_month_cap_pct", default_cap_pct)))
    trend_weight = Decimal(str(payload.get("trend_weight", default_trend_weight)))
    seasonality_min = Decimal(str(payload.get("seasonality_min", default_seasonality_min)))
    seasonality_max = Decimal(str(payload.get("seasonality_max", default_seasonality_max)))
    trend_min = Decimal(str(payload.get("trend_adjustment_min", default_trend_min)))
    trend_max = Decimal(str(payload.get("trend_adjustment_max", default_trend_max)))
    valid = (
        total_target > 0 and min_floor >= 0 and floor_pct >= 0 and cap_pct > 0
        and cap_pct >= floor_pct and trend_weight >= 0 and seasonality_min > 0
        and seasonality_max >= seasonality_min and trend_min > 0 and trend_max >= trend_min
    )
    if not valid:
        raise ValueError("Parametrii de calcul nu sunt valizi.")
    return (
        total_target, min_floor, floor_pct, cap_pct, trend_weight,
        seasonality_min, seasonality_max, trend_min, trend_max,
    )


# The service passes dependencies explicitly so tests can keep patching the
# package facade without proposal code importing the orchestration facade.
class SourceMetric(TypedDict):
    target: Decimal
    actual_realized: Decimal
    realized: Decimal
    forecast_factor: Decimal
    is_forecast: bool


class PeriodTotals(TypedDict):
    target: Decimal
    realized: Decimal


@dataclass(frozen=True)
class ProposalContext:
    repo: Any
    get_forecast_factor: Callable[[Any, str], Awaitable[Any]]
    allocate_with_bounds: Callable[[list[dict[str, Any]], Decimal], tuple[list[dict[str, Any]], list[str]]]
    get_scenario_detail: Callable[[int], Awaitable[dict[str, Any]]]
    calculation_method: str
    default_min_floor: Decimal
    default_floor_pct: Decimal
    default_cap_pct: Decimal
    default_seasonality_years: int
    max_seasonality_years: int
    default_trend_weight: Decimal
    default_trend_min: Decimal
    default_trend_max: Decimal
    default_seasonality_min: Decimal
    default_seasonality_max: Decimal
    minimum_seasonality_base: Decimal
    strong_seasonality_weights: dict[str, Decimal]
    weak_seasonality_weights: dict[str, Decimal]
    new_store_seasonality_weights: dict[str, Decimal]
    profitability_constants: ProfitabilityConstants
    canonical_input_hash: Callable[[Any], str] = canonical_input_hash


async def calculate_proposal(
    context: ProposalContext, payload: dict[str, Any]
) -> dict[str, Any]:
    target_month = payload["target_month"]
    seasonality_years = int(payload.get("seasonality_years") or context.default_seasonality_years)
    seasonality_years = max(1, min(seasonality_years, context.max_seasonality_years))
    source_pairs = seasonality_pair_configuration(target_month, seasonality_years)
    source_months = build_source_month_configuration(target_month, source_pairs)
    latest_before_target = await context.repo.get_latest_sales_month(before_month=target_month)
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

    cohort = await context.repo.get_active_cohort(cohort_month, target_month)
    if not cohort:
        raise HTTPException(status_code=400, detail="Luna de cohorta nu are magazine active.")

    try:
        (
            total_target,
            min_floor,
            floor_pct,
            cap_pct,
            trend_weight,
            seasonality_min,
            seasonality_max,
            trend_min,
            trend_max,
        ) = normalize_proposal_parameters(
            payload,
            default_min_floor=context.default_min_floor,
            default_floor_pct=context.default_floor_pct,
            default_cap_pct=context.default_cap_pct,
            default_trend_weight=context.default_trend_weight,
            default_seasonality_min=context.default_seasonality_min,
            default_seasonality_max=context.default_seasonality_max,
            default_trend_min=context.default_trend_min,
            default_trend_max=context.default_trend_max,
        )
    except (KeyError, ValueError, ArithmeticError):
        raise HTTPException(status_code=400, detail="Parametrii de calcul nu sunt valizi.") from None

    rule_record = await context.repo.get_effective_target_rule_set(target_month)
    if not rule_record:
        raise HTTPException(
            status_code=409,
            detail="Nu exista un rule-set Target efectiv pentru luna ceruta; nu s-a creat nicio propunere.",
        )
    try:
        target_rule_set = validate_target_rule_set(dict(rule_record), target_month)
    except TargetRuleSetValidationError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Rule-set-ul Target este invalid; nu s-a creat nicio propunere. {exc}",
        ) from None
    exception_codes = sorted(target_rule_set.rules["store_exceptions"])
    if exception_codes:
        master_rows = await context.repo.get_target_rule_exception_master(exception_codes)
        try:
            validate_store_exception_scope(
                target_rule_set,
                cohort=[dict(row) for row in cohort],
                master_rows=[dict(row) for row in master_rows],
            )
        except TargetRuleSetValidationError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Rule-set-ul Target nu se reconciliaza cu master/cohort; nu s-a creat nicio propunere. {exc}",
            ) from None

    months = unique_months([item["month"] for item in source_months])
    site_codes = [row["site_code"] for row in cohort]
    metrics = await context.repo.get_source_metrics(site_codes, months)
    async with context.repo.pool.acquire() as conn:
        forecast_factors = {
            month: Decimal(str(await context.get_forecast_factor(conn, month)))
            for month in months
        }
    calculation_input_sha256 = context.canonical_input_hash({
        "target_month": target_month,
        "cohort_month": cohort_month,
        "source_months": source_months,
        "cohort": [dict(row) for row in cohort],
        "source_metrics": [dict(row) for row in metrics],
        "forecast_factors": {month: str(forecast_factors[month]) for month in sorted(forecast_factors)},
    })
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
            minimum_base=context.minimum_seasonality_base,
        )
        zone_factor, zone_years = weighted_ratio(source_pairs, regional_values)
        last_year_store_factor, _ = weighted_ratio(source_pairs[:1], store_values, minimum_base=context.minimum_seasonality_base)
        multiyear_store_factor, _ = weighted_ratio(source_pairs, store_values, minimum_base=context.minimum_seasonality_base)

        weights = context.strong_seasonality_weights
        flags: list[str] = []
        usable_store_years = sum(1 for item in store_years if item["ratio"] is not None)
        store_ratios = [
            Decimal(str(item["ratio"]))
            for item in store_years
            if item["ratio"] is not None
        ]
        if store_factor is None:
            weights = context.new_store_seasonality_weights
            flags.extend(["NEW_STORE", "LOW_HISTORY"])
        elif usable_store_years <= 1 and seasonality_years > 1:
            weights = context.weak_seasonality_weights
            flags.append("LOW_HISTORY")
        elif (
            seasonality_years > 1
            and any(item["year_offset"] == 1 and item["ratio"] is None for item in store_years)
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
        seasonality_factor = clamp_decimal(raw_blended, seasonality_min, seasonality_max)
        if seasonality_factor != raw_blended:
            flags.append("SEASONALITY_CAPPED")

        current_forecast = metric_map[(site_code, current_month)]["realized"]
        trend_base = metric_map[(site_code, source_pairs[0]["base_month"])]["realized"]
        if trend_base > context.minimum_seasonality_base:
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
            "method": context.calculation_method,
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

    floor_total = sum((row["floor_target"] for row in calculated_rows), Decimal("0"))
    cap_total = sum((row["cap_target"] for row in calculated_rows), Decimal("0"))
    if total_target < floor_total:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Targetul total {total_target:,.0f} RON este sub suma floor-urilor calculate "
                f"{floor_total:,.0f} RON. Ajusteaza bugetul sau floor-ul operational; propunerea nu a fost salvata."
            ).replace(",", "."),
        )
    if cap_total < total_target:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Targetul total {total_target:,.0f} RON depaseste cap-ul maxim calculat "
                f"{cap_total:,.0f} RON. Verifica valoarea bugetului sau mareste cap-ul operational."
            ).replace(",", "."),
        )

    try:
        calculated_rows, allocation_warnings = context.allocate_with_bounds(calculated_rows, total_target)
    except TargetBudgetInfeasibleError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Bugetul Target este infezabil; propunerea nu a fost salvata. {exc}",
        ) from None
    warnings.extend(allocation_warnings)
    warnings = unique_warnings(warnings)
    for row in calculated_rows:
        flags = list(dict.fromkeys(row["flags"]))
        row["calculation_details"]["flags"] = flags
        row["calculation_details"]["allocation_reason"] = row["allocation_reason"]
        row["calculation_details"]["is_floor_limited"] = row["is_floor_limited"]
        row["calculation_details"]["is_cap_limited"] = row["is_cap_limited"]

    profitability_inputs = await context.repo.get_profitability_inputs(
        site_codes=site_codes,
        target_month=target_month,
    )
    coverage, _forecast_values = forecast_coverage(
        calculated_rows,
        profitability_inputs,
    )
    profitability_inputs["forecast_coverage"] = coverage
    if coverage["mode"] != "uniform":
        raise forecast_coverage_error(coverage)
    profitability_input_sha256 = context.canonical_input_hash(
        profitability_input_payload(profitability_inputs)
    )
    profitability_summary = populate_profitability(
        {
            "target_month": target_month,
            "rule_set_snapshot": target_rule_set.snapshot(),
            "calculation_params": {
                "profitability": rule_set_profitability_assumptions(target_rule_set),
            },
        },
        calculated_rows,
        profitability_inputs,
        context.profitability_constants,
    )
    profitability_summary["input_sha256"] = profitability_input_sha256
    for row in calculated_rows:
        row["profitability_snapshot"] = row.pop("profitability")
    try:
        scenario_id = await context.repo.save_draft_scenario(
            {
                "target_month": target_month,
                "cohort_month": cohort_month,
                "total_target": total_target,
                "min_floor": min_floor,
                "previous_month_floor_pct": floor_pct,
                "calculation_method": context.calculation_method,
                "source_months": source_months,
                "warnings": warnings,
                "rule_set_id": target_rule_set.rule_set_id,
                "rule_set_hash": target_rule_set.rules_hash,
                "rule_set_snapshot": target_rule_set.snapshot(),
                "calculation_input_sha256": calculation_input_sha256,
                "profitability_input_sha256": profitability_input_sha256,
                "calculation_params": {
                    "seasonality_years": seasonality_years,
                    "seasonality_min": float(seasonality_min),
                    "seasonality_max": float(seasonality_max),
                    "trend_weight": float(trend_weight),
                    "trend_adjustment_min": float(trend_min),
                    "trend_adjustment_max": float(trend_max),
                    "previous_month_cap_pct": float(cap_pct),
                    "minimum_seasonality_base": float(context.minimum_seasonality_base),
                    "strong_weights": {key: float(value) for key, value in context.strong_seasonality_weights.items()},
                    "weak_weights": {key: float(value) for key, value in context.weak_seasonality_weights.items()},
                    "new_store_weights": {key: float(value) for key, value in context.new_store_seasonality_weights.items()},
                    "profitability": rule_set_profitability_assumptions(target_rule_set),
                    "profitability_summary": profitability_summary,
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
    except TargetScenarioAlgorithmMismatch:
        raise HTTPException(
            status_code=409,
            detail="Scenariul draft apartine altei versiuni de algoritm; nu poate fi rescris.",
        ) from None
    except TargetScenarioVersionConflict:
        raise HTTPException(
            status_code=409,
            detail=(
                "Scenariul a fost modificat de alt utilizator. "
                "Reincarca datele inainte de recalculare."
            ),
        ) from None
    return await context.get_scenario_detail(scenario_id)
