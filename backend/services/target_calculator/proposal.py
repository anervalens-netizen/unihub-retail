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
from services.target_calculator.calculations import TargetBudgetInfeasibleError, money
from services.target_calculator.profitability import (
    ProfitabilityConstants,
    forecast_coverage,
    forecast_coverage_error,
    populate_profitability,
    profitability_input_payload,
)
from services.target_calculator.rules import (
    canonical_input_hash,
    realized_for_calculation,
    unique_months,
)
from services.target_calculator.proposal_rows import _calculated_rows
from services.target_calculator.seasonality import (
    build_source_month_configuration,
    seasonality_pair_configuration,
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


@dataclass(frozen=True)
class ProposalParameters:
    total_target: Decimal
    min_floor: Decimal
    floor_pct: Decimal
    cap_pct: Decimal
    trend_weight: Decimal
    seasonality_min: Decimal
    seasonality_max: Decimal
    trend_min: Decimal
    trend_max: Decimal


@dataclass(frozen=True)
class ProposalScope:
    target_month: str
    cohort_month: str
    seasonality_years: int
    source_pairs: list[Any]
    source_months: list[dict[str, Any]]
    cohort: list[Any]
    rule_set: Any
    parameters: ProposalParameters


@dataclass(frozen=True)
class ProposalMetrics:
    months: list[str]
    site_codes: list[str]
    metric_map: dict[tuple[str, str], SourceMetric]
    totals: dict[str, PeriodTotals]
    regional_month_values: dict[tuple[str, str], Decimal]
    forecast_factors: dict[str, Decimal]
    input_sha256: str


def _proposal_parameters(context: ProposalContext, payload: dict[str, Any]) -> ProposalParameters:
    try:
        values = normalize_proposal_parameters(
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
    return ProposalParameters(*values)


async def _proposal_scope(context: ProposalContext, payload: dict[str, Any]) -> ProposalScope:
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
    parameters = _proposal_parameters(context, payload)
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
    return ProposalScope(
        target_month=target_month,
        cohort_month=cohort_month,
        seasonality_years=seasonality_years,
        source_pairs=source_pairs,
        source_months=source_months,
        cohort=list(cohort),
        rule_set=target_rule_set,
        parameters=parameters,
    )


def _metric_aggregates(
    cohort: list[Any],
    metrics: list[Any],
    months: list[str],
    site_codes: list[str],
    forecast_factors: dict[str, Decimal],
) -> tuple[
    dict[tuple[str, str], SourceMetric],
    dict[str, PeriodTotals],
    dict[tuple[str, str], Decimal],
]:
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
    regional_month_values = {
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
    return metric_map, totals, regional_month_values


async def _proposal_metrics(context: ProposalContext, scope: ProposalScope) -> ProposalMetrics:
    months = unique_months([item["month"] for item in scope.source_months])
    cohort = scope.cohort
    site_codes = [row["site_code"] for row in cohort]
    metrics = await context.repo.get_source_metrics(site_codes, months)
    async with context.repo.pool.acquire() as conn:
        forecast_factors = {
            month: Decimal(str(await context.get_forecast_factor(conn, month)))
            for month in months
        }
    input_sha256 = context.canonical_input_hash({
        "target_month": scope.target_month, "cohort_month": scope.cohort_month,
        "source_months": scope.source_months, "cohort": [dict(row) for row in cohort],
        "source_metrics": [dict(row) for row in metrics],
        "forecast_factors": {month: str(forecast_factors[month]) for month in sorted(forecast_factors)},
    })
    metric_map, totals, regional_values = _metric_aggregates(
        cohort, list(metrics), months, site_codes, forecast_factors,
    )
    return ProposalMetrics(
        months=months,
        site_codes=site_codes,
        metric_map=metric_map,
        totals=totals,
        regional_month_values=regional_values,
        forecast_factors=forecast_factors,
        input_sha256=input_sha256,
    )


def _source_warnings(scope: ProposalScope, metrics: ProposalMetrics) -> list[str]:
    warnings: list[str] = []
    for item in scope.source_months:
        total = metrics.totals[item["month"]]
        if total["target"] == 0 and total["realized"] == 0:
            warnings.append(f"Nu exista date pentru perioada de referinta {item['month']}.")
        if metrics.forecast_factors[item["month"]] > Decimal("1"):
            warnings.append(
                f"Perioada {item['month']} este partiala; vanzarile folosite in calcul sunt forecastate "
                f"cu factor {metrics.forecast_factors[item['month']]:.4f}x pe baza importului disponibil."
            )
    if scope.seasonality_years > 1:
        warnings.append(
            f"Formula foloseste sezonalitate multi-year pe pana la {scope.seasonality_years} ani; anii fara date suficiente sunt sariti automat."
        )
    return warnings



def _allocate_rows(
    context: ProposalContext,
    rows: list[dict[str, Any]],
    total_target: Decimal,
    warnings: list[str],
) -> list[str]:
    if sum((row["calculated_weight"] for row in rows), Decimal("0")) == 0:
        equal_weight = Decimal("1") / Decimal(len(rows))
        for row in rows:
            row["calculated_weight"] = equal_weight
            row["flags"].append("LOW_HISTORY")
        warnings.append("Datele istorice nu contin estimari sezoniere utilizabile; targetul a fost distribuit uniform.")
    else:
        raw_total = sum((row["calculated_weight"] for row in rows), Decimal("0"))
        for row in rows:
            row["calculated_weight"] = row["calculated_weight"] / raw_total
    floor_total = sum((row["floor_target"] for row in rows), Decimal("0"))
    cap_total = sum((row["cap_target"] for row in rows), Decimal("0"))
    if total_target < floor_total:
        detail = f"Targetul total {total_target:,.0f} RON este sub suma floor-urilor calculate {floor_total:,.0f} RON. Ajusteaza bugetul sau floor-ul operational; propunerea nu a fost salvata."
        raise HTTPException(status_code=400, detail=detail.replace(",", "."))
    if cap_total < total_target:
        detail = f"Targetul total {total_target:,.0f} RON depaseste cap-ul maxim calculat {cap_total:,.0f} RON. Verifica valoarea bugetului sau mareste cap-ul operational."
        raise HTTPException(status_code=400, detail=detail.replace(",", "."))
    try:
        _, allocation_warnings = context.allocate_with_bounds(rows, total_target)
    except TargetBudgetInfeasibleError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Bugetul Target este infezabil; propunerea nu a fost salvata. {exc}",
        ) from None
    warnings.extend(allocation_warnings)
    for row in rows:
        flags = list(dict.fromkeys(row["flags"]))
        row["calculation_details"].update({
            "flags": flags, "allocation_reason": row["allocation_reason"],
            "is_floor_limited": row["is_floor_limited"], "is_cap_limited": row["is_cap_limited"],
        })
    return unique_warnings(warnings)


async def _apply_profitability(
    context: ProposalContext,
    scope: ProposalScope,
    metrics: ProposalMetrics,
    rows: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    inputs = await context.repo.get_profitability_inputs(
        site_codes=metrics.site_codes, target_month=scope.target_month,
    )
    coverage, _forecast_values = forecast_coverage(rows, inputs)
    inputs["forecast_coverage"] = coverage
    if coverage["mode"] != "uniform":
        raise forecast_coverage_error(coverage)
    input_sha256 = context.canonical_input_hash(profitability_input_payload(inputs))
    summary = populate_profitability(
        {
            "target_month": scope.target_month,
            "rule_set_snapshot": scope.rule_set.snapshot(),
            "calculation_params": {
                "profitability": rule_set_profitability_assumptions(scope.rule_set),
            },
        },
        rows,
        inputs,
        context.profitability_constants,
    )
    summary["input_sha256"] = input_sha256
    for row in rows:
        row["profitability_snapshot"] = row.pop("profitability")
    return input_sha256, summary


async def _save_proposal(
    context: ProposalContext,
    payload: dict[str, Any],
    scope: ProposalScope,
    metrics: ProposalMetrics,
    rows: list[dict[str, Any]],
    warnings: list[str],
    profitability_input_sha256: str,
    profitability_summary: dict[str, Any],
) -> int:
    parameters = scope.parameters
    calculation_params = {
        "seasonality_years": scope.seasonality_years,
        "seasonality_min": float(parameters.seasonality_min),
        "seasonality_max": float(parameters.seasonality_max),
        "trend_weight": float(parameters.trend_weight),
        "trend_adjustment_min": float(parameters.trend_min),
        "trend_adjustment_max": float(parameters.trend_max),
        "previous_month_cap_pct": float(parameters.cap_pct),
        "minimum_seasonality_base": float(context.minimum_seasonality_base),
        "strong_weights": {key: float(value) for key, value in context.strong_seasonality_weights.items()},
        "weak_weights": {key: float(value) for key, value in context.weak_seasonality_weights.items()},
        "new_store_weights": {key: float(value) for key, value in context.new_store_seasonality_weights.items()},
        "profitability": rule_set_profitability_assumptions(scope.rule_set),
        "profitability_summary": profitability_summary,
    }
    scenario = {
        "target_month": scope.target_month, "cohort_month": scope.cohort_month,
        "total_target": parameters.total_target, "min_floor": parameters.min_floor,
        "previous_month_floor_pct": parameters.floor_pct, "calculation_method": context.calculation_method,
        "source_months": scope.source_months, "warnings": warnings,
        "rule_set_id": scope.rule_set.rule_set_id, "rule_set_hash": scope.rule_set.rules_hash,
        "rule_set_snapshot": scope.rule_set.snapshot(), "calculation_input_sha256": metrics.input_sha256,
        "profitability_input_sha256": profitability_input_sha256, "calculation_params": calculation_params,
    }
    try:
        return await context.repo.save_draft_scenario(
            scenario, rows, payload.get("expected_revision"),
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
            detail="Scenariul a fost modificat de alt utilizator. Reincarca datele inainte de recalculare.",
        ) from None


async def calculate_proposal(
    context: ProposalContext, payload: dict[str, Any]
) -> dict[str, Any]:
    scope = await _proposal_scope(context, payload)
    metrics = await _proposal_metrics(context, scope)
    warnings = _source_warnings(scope, metrics)
    rows = _calculated_rows(context, scope, metrics)
    warnings = _allocate_rows(context, rows, scope.parameters.total_target, warnings)
    profitability_hash, profitability_summary = await _apply_profitability(
        context, scope, metrics, rows,
    )
    scenario_id = await _save_proposal(
        context, payload, scope, metrics, rows, warnings,
        profitability_hash, profitability_summary,
    )
    return await context.get_scenario_detail(scenario_id)
