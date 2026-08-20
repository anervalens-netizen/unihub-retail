"""Frozen and live profitability calculations for Target scenarios.

This module owns the rule-snapshot boundary.  The service only coordinates
repository calls; it never re-implements the profitability formulas.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from fastapi import HTTPException

from services.fiscal_rules import (
    STANDARD_VAT_RULESET_ID,
    net_to_gross,
    standard_vat_rule,
    standard_vat_ruleset_hash,
)
from services.target_calculator.calculations import money
from services.target_rule_registry import (
    TargetRuleSet,
    TargetRuleSetValidationError,
    profitability_assumptions as rule_set_profitability_assumptions,
    store_salary_parameters,
    target_rule_set_from_snapshot,
)


PROFITABILITY_REQUIRED_CATEGORIES = frozenset({"v11", "c11", "c4", "c5", "c6"})


@dataclass(frozen=True)
class ProfitabilityConstants:
    salary_pnl_factor: Decimal
    meal_vouchers_per_agent: Decimal
    sales_commission_rate: Decimal
    salary_assumed_attainment: Decimal
    default_store_agent_count: int
    sun_plaza_agent_count: int
    base_salary_default: Decimal
    base_salary_high: Decimal
    base_salary_high_site_codes: frozenset[str]


@dataclass(frozen=True)
class _ProfitabilityRowResult:
    salary_cost: Decimal
    operating_costs: Decimal | None
    break_even: Decimal | None
    forecast: Decimal | None
    target_below_break_even: bool
    forecast_below_break_even: bool


class ProfitabilityRepository(Protocol):
    async def get_profitability_inputs(
        self, *, site_codes: list[str], target_month: str
    ) -> dict[str, Any]: ...


def profitability_assumptions(
    target_month: str, constants: ProfitabilityConstants
) -> dict[str, Any]:
    vat_rule = standard_vat_rule(target_month)
    return {
        "vat_ruleset_id": STANDARD_VAT_RULESET_ID,
        "vat_ruleset_hash": standard_vat_ruleset_hash(),
        "vat_rule_id": vat_rule.rule_id,
        "vat_effective_from": vat_rule.effective_from.isoformat(),
        "vat_multiplier": float(vat_rule.multiplier),
        "vat_rate": float(vat_rule.rate),
        "salary_pnl_factor": float(constants.salary_pnl_factor),
        "meal_vouchers_per_agent": float(constants.meal_vouchers_per_agent),
        "sales_commission_rate": float(constants.sales_commission_rate),
        "salary_assumed_attainment": float(constants.salary_assumed_attainment),
        "default_store_agent_count": constants.default_store_agent_count,
        "sun_plaza_agent_count": constants.sun_plaza_agent_count,
        "base_salary_default": float(constants.base_salary_default),
        "base_salary_high": float(constants.base_salary_high),
    }


def fallback_profitability_assumptions(constants: ProfitabilityConstants) -> dict[str, Any]:
    assumptions = profitability_assumptions("2025-08", constants)
    assumptions.update(
        {
            "vat_ruleset_id": "legacy-unversioned",
            "vat_ruleset_hash": None,
            "vat_rule_id": "legacy-unversioned",
            "vat_effective_from": None,
        }
    )
    return assumptions


def saved_profitability_assumptions(
    scenario: dict[str, Any], constants: ProfitabilityConstants
) -> dict[str, Any]:
    """Normalize legacy snapshots without silently inventing persisted data."""
    legacy = fallback_profitability_assumptions(constants)
    raw = (scenario.get("calculation_params") or {}).get("profitability")
    if not isinstance(raw, dict):
        return legacy
    assumptions = {**legacy, **raw}
    if "vat_multiplier" not in raw:
        saved_rate = raw.get("vat_rate")
        assumptions["vat_multiplier"] = float(
            Decimal("1") + Decimal(str(saved_rate))
        ) if saved_rate is not None else legacy["vat_multiplier"]
    if not raw.get("vat_rule_id"):
        assumptions["vat_rule_id"] = "legacy-unversioned"
    if not raw.get("vat_ruleset_id"):
        assumptions["vat_ruleset_id"] = "legacy-unversioned"
    return assumptions


def saved_target_rule_set(scenario: dict[str, Any]) -> TargetRuleSet | None:
    snapshot = scenario.get("rule_set_snapshot")
    if snapshot is None:
        return None
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=409, detail="Snapshotul Target nu este JSON valid.") from exc
    try:
        rule_set = target_rule_set_from_snapshot(snapshot, scenario["target_month"])
    except TargetRuleSetValidationError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Snapshotul rule-set-ului Target este invalid: {exc}",
        ) from None
    if rule_set is None:
        raise HTTPException(status_code=409, detail="Snapshotul rule-set-ului Target este incomplet.")
    return rule_set


def profitability_input_payload(inputs: dict[str, Any]) -> dict[str, Any]:
    forecast_run = inputs.get("forecast_run")
    return {
        "pnl_months": list(inputs.get("pnl_months") or []),
        "pnl_rows": [dict(record) for record in inputs.get("pnl_rows") or []],
        "forecast_run": dict(forecast_run) if forecast_run else None,
        "forecast_rows": [dict(record) for record in inputs.get("forecast_rows") or []],
        "forecast_coverage": inputs.get("forecast_coverage"),
    }


def forecast_coverage(
    rows: list[dict[str, Any]], inputs: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Decimal]]:
    expected_site_codes = sorted({str(row["site_code"]) for row in rows})
    records_by_site = {
        str(record["site_code"]): record for record in inputs.get("forecast_rows") or []
    }
    forecast_values: dict[str, Decimal] = {}
    covered_site_codes: list[str] = []
    missing_site_codes: list[str] = []
    cutoff_values: list[str] = []
    for site_code in expected_site_codes:
        record = records_by_site.get(site_code)
        forecast_present = bool(record and record.get("forecast_present"))
        realized_present = bool(record and record.get("realized_present"))
        forecast_sales = record.get("forecast_sales") if record else None
        cutoff_date = record.get("cutoff_date") if record else None
        if not forecast_present or not realized_present or forecast_sales is None or cutoff_date is None:
            missing_site_codes.append(site_code)
            continue
        forecast_values[site_code] = money(Decimal(forecast_sales))
        covered_site_codes.append(site_code)
        cutoff_values.append(str(cutoff_date))
    distinct_cutoffs = sorted(set(cutoff_values))
    uniform = (
        inputs.get("forecast_run") is not None
        and len(covered_site_codes) == len(expected_site_codes)
        and len(distinct_cutoffs) == 1
    )
    return (
        {
            "mode": "uniform" if uniform else "nonuniform",
            "cutoff": distinct_cutoffs[0] if uniform else None,
            "cutoff_min": min(cutoff_values) if cutoff_values else None,
            "cutoff_max": max(cutoff_values) if cutoff_values else None,
            "expected_store_count": len(expected_site_codes),
            "covered_store_count": len(covered_site_codes),
            "missing_site_codes": missing_site_codes,
        },
        forecast_values,
    )


def forecast_coverage_error(coverage: dict[str, Any]) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "message": "Forecastul curent nu are coverage uniform complet; propunerea nu a fost salvată.",
            "forecast_coverage": coverage,
        },
    )


def _normalize_weights(rows: list[dict[str, Any]]) -> None:
    weight_total = sum(
        (Decimal(str(row["calculated_weight"])) for row in rows),
        Decimal("0"),
    )
    for row in rows:
        weight = Decimal(str(row["calculated_weight"]))
        row["normalized_weight"] = float(weight / weight_total) if weight_total > 0 else 0.0


def _salary_rule_values(
    target_rule_set: TargetRuleSet | None,
    constants: ProfitabilityConstants,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    if target_rule_set is not None:
        salary_rules = target_rule_set.rules["salary"]
        return (
            Decimal(str(salary_rules["pnl_factor"])),
            Decimal(str(salary_rules["meal_vouchers_per_agent"])),
            Decimal(str(salary_rules["sales_commission_rate"])),
            Decimal(str(salary_rules["assumed_attainment"])),
        )
    return (
        constants.salary_pnl_factor,
        constants.meal_vouchers_per_agent,
        constants.sales_commission_rate,
        constants.salary_assumed_attainment,
    )


def _store_salary_values(
    site_code: str,
    target_rule_set: TargetRuleSet | None,
    constants: ProfitabilityConstants,
) -> tuple[int, Decimal]:
    if target_rule_set is not None:
        return store_salary_parameters(target_rule_set, site_code)
    agents = (
        constants.sun_plaza_agent_count
        if site_code == "SUNPLZ"
        else constants.default_store_agent_count
    )
    base_salary = (
        constants.base_salary_high
        if site_code in constants.base_salary_high_site_codes
        else constants.base_salary_default
    )
    return agents, base_salary


def _pnl_metrics(
    *,
    site_code: str,
    pnl_months: list[str],
    pnl_values: dict[tuple[str, str], Decimal],
    salary_cost: Decimal,
    target_month: str,
    vat_multiplier: Decimal,
) -> tuple[bool, Decimal | None, Decimal | None, Decimal | None]:
    categories = {
        category: pnl_values.get((site_code, category))
        for category in PROFITABILITY_REQUIRED_CATEGORIES
    }
    pnl_complete = len(pnl_months) == 3 and all(
        value is not None for value in categories.values()
    )
    accessory_margin: Decimal | None = None
    opex: Decimal | None = None
    break_even: Decimal | None = None
    if pnl_complete:
        accessory_revenue = categories["v11"] or Decimal("0")
        accessory_cogs = categories["c11"] or Decimal("0")
        if accessory_revenue > 0:
            accessory_margin = (
                accessory_revenue - accessory_cogs
            ) / accessory_revenue
        if accessory_margin is not None and accessory_margin > 0:
            opex = money(
                (
                    (categories["c4"] or Decimal("0"))
                    + (categories["c5"] or Decimal("0"))
                    + (categories["c6"] or Decimal("0"))
                )
                / Decimal(len(pnl_months))
            )
            net_break_even = (salary_cost + opex) / accessory_margin
            break_even = net_to_gross(net_break_even, target_month)
            if vat_multiplier != standard_vat_rule(target_month).multiplier:
                break_even = money(net_break_even * vat_multiplier)
    return pnl_complete, accessory_margin, opex, break_even


def _anomaly_flags(
    *,
    pnl_complete: bool,
    break_even: Decimal | None,
    forecast: Decimal | None,
    calculated_target: Decimal,
) -> tuple[list[str], bool, bool]:
    anomaly_flags: list[str] = []
    target_below_break_even = False
    forecast_below_break_even = False
    if not pnl_complete or break_even is None:
        anomaly_flags.append("PNL_INCOMPLETE")
    if forecast is None:
        anomaly_flags.append("FORECAST_MISSING")
    if break_even is not None and calculated_target < break_even:
        anomaly_flags.append("TARGET_BELOW_BREAK_EVEN")
        target_below_break_even = True
    if break_even is not None and forecast is not None and forecast < break_even:
        anomaly_flags.append("FORECAST_BELOW_BREAK_EVEN")
        forecast_below_break_even = True
    elif forecast is not None and forecast < calculated_target:
        anomaly_flags.append("FORECAST_BELOW_TARGET")
    return anomaly_flags, target_below_break_even, forecast_below_break_even


def _populate_profitability_row(
    *,
    row: dict[str, Any],
    scenario: dict[str, Any],
    pnl_months: list[str],
    pnl_values: dict[tuple[str, str], Decimal],
    forecast_values: dict[str, Decimal],
    target_rule_set: TargetRuleSet | None,
    constants: ProfitabilityConstants,
    salary_pnl_factor: Decimal,
    meal_vouchers: Decimal,
    commission_rate: Decimal,
    assumed_attainment: Decimal,
    vat_multiplier: Decimal,
) -> _ProfitabilityRowResult:
    site_code = row["site_code"]
    agents, base_salary = _store_salary_values(site_code, target_rule_set, constants)
    calculated_target = money(row["proposed_target"])
    salary_source = Decimal(agents) * (base_salary + meal_vouchers) + (
        calculated_target * assumed_attainment * commission_rate
    )
    salary_cost = money(salary_source * salary_pnl_factor)
    pnl_complete, accessory_margin, opex, break_even = _pnl_metrics(
        site_code=site_code,
        pnl_months=pnl_months,
        pnl_values=pnl_values,
        salary_cost=salary_cost,
        target_month=scenario["target_month"],
        vat_multiplier=vat_multiplier,
    )
    forecast = forecast_values.get(site_code)
    anomaly_flags, target_below_break_even, forecast_below_break_even = _anomaly_flags(
        pnl_complete=pnl_complete,
        break_even=break_even,
        forecast=forecast,
        calculated_target=calculated_target,
    )
    row["profitability"] = {
        "agent_count": agents,
        "base_salary_per_agent": float(base_salary),
        "salary_cost_at_90_pct": float(salary_cost),
        "operating_costs": float(opex) if opex is not None else None,
        "accessory_margin_pct": (
            float(accessory_margin * Decimal("100"))
            if accessory_margin is not None
            else None
        ),
        "break_even_gross_sales": float(break_even) if break_even is not None else None,
        "forecast_sales": float(forecast) if forecast is not None else None,
        "anomaly_flags": anomaly_flags,
    }
    return _ProfitabilityRowResult(
        salary_cost=salary_cost,
        operating_costs=opex,
        break_even=break_even,
        forecast=forecast,
        target_below_break_even=target_below_break_even,
        forecast_below_break_even=forecast_below_break_even,
    )


def _forecast_run_summary(forecast_run: dict[str, Any] | None) -> dict[str, Any] | None:
    if forecast_run is None:
        return None
    return {
        "id": int(forecast_run["id"]),
        "model_name": forecast_run["model_name"],
        "model_mode": forecast_run["model_mode"],
        "variant": forecast_run["variant"],
        "generated_at": forecast_run["generated_at"],
        "source_month": forecast_run["source_month"],
    }


def populate_profitability(
    scenario: dict[str, Any],
    rows: list[dict[str, Any]],
    inputs: dict[str, Any],
    constants: ProfitabilityConstants,
) -> dict[str, Any]:
    _normalize_weights(rows)
    pnl_months = list(inputs.get("pnl_months") or [])
    pnl_values: dict[tuple[str, str], Decimal] = {
        (record["site_code"], record["category_code"]): Decimal(record["amount"] or 0)
        for record in inputs.get("pnl_rows") or []
    }
    coverage_contract, forecast_values = forecast_coverage(rows, inputs)
    forecast_run_record = inputs.get("forecast_run")
    forecast_run = dict(forecast_run_record) if forecast_run_record else None
    target_rule_set = saved_target_rule_set(scenario)
    saved_profitability = (
        rule_set_profitability_assumptions(target_rule_set)
        if target_rule_set is not None
        else saved_profitability_assumptions(scenario, constants)
    )
    vat_multiplier = Decimal(str(saved_profitability["vat_multiplier"]))
    (
        salary_pnl_factor,
        meal_vouchers,
        commission_rate,
        assumed_attainment,
    ) = _salary_rule_values(target_rule_set, constants)

    salary_total = opex_total = break_even_total = forecast_total = Decimal("0")
    forecast_below_break_even_count = target_below_break_even_count = complete_pnl_count = 0
    for row in rows:
        result = _populate_profitability_row(
            row=row,
            scenario=scenario,
            pnl_months=pnl_months,
            pnl_values=pnl_values,
            forecast_values=forecast_values,
            target_rule_set=target_rule_set,
            constants=constants,
            salary_pnl_factor=salary_pnl_factor,
            meal_vouchers=meal_vouchers,
            commission_rate=commission_rate,
            assumed_attainment=assumed_attainment,
            vat_multiplier=vat_multiplier,
        )
        salary_total += result.salary_cost
        if result.break_even is not None:
            complete_pnl_count += 1
            opex_total += result.operating_costs or Decimal("0")
            break_even_total += result.break_even
        if result.forecast is not None:
            forecast_total += result.forecast
        target_below_break_even_count += int(result.target_below_break_even)
        forecast_below_break_even_count += int(result.forecast_below_break_even)

    forecast_complete = coverage_contract["mode"] == "uniform"
    return {
        "status": "ready" if complete_pnl_count == len(rows) and forecast_complete else "partial",
        "pnl_months": pnl_months,
        "pnl_store_count": complete_pnl_count,
        "forecast_store_count": int(coverage_contract["covered_store_count"]),
        "forecast_run": _forecast_run_summary(forecast_run),
        "forecast_coverage": coverage_contract,
        "assumptions": saved_profitability,
        "salary_total": float(money(salary_total)),
        "operating_costs_total": float(money(opex_total)) if complete_pnl_count else None,
        "break_even_total": float(money(break_even_total)) if complete_pnl_count else None,
        "forecast_total": float(money(forecast_total)) if forecast_complete else None,
        "forecast_below_break_even_count": forecast_below_break_even_count,
        "target_below_break_even_count": target_below_break_even_count,
    }


def frozen_profitability(
    scenario: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    rule_set = saved_target_rule_set(scenario)
    if (
        rule_set is None
        or scenario.get("rule_set_id") != rule_set.rule_set_id
        or scenario.get("rule_set_hash") != rule_set.rules_hash
    ):
        raise HTTPException(status_code=409, detail="Snapshotul rule-set-ului Target nu corespunde antetului salvat.")
    summary = (scenario.get("calculation_params") or {}).get("profitability_summary")
    expected_hash = scenario.get("profitability_input_sha256")
    if not isinstance(summary, dict) or not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise HTTPException(status_code=409, detail="Snapshotul de profitabilitate Target este incomplet.")
    if summary.get("input_sha256") != expected_hash:
        raise HTTPException(status_code=409, detail="Hashul snapshotului de profitabilitate Target nu corespunde.")
    for row in rows:
        snapshot = row.get("profitability_snapshot")
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=409, detail="Snapshotul per magazin Target nu este JSON valid.") from exc
        if not isinstance(snapshot, dict):
            raise HTTPException(status_code=409, detail="Snapshotul per magazin Target lipseste.")
        row["profitability"] = snapshot
        row.pop("profitability_snapshot", None)
    return summary


async def attach_profitability(
    repo: ProfitabilityRepository,
    scenario: dict[str, Any],
    rows: list[dict[str, Any]],
    constants: ProfitabilityConstants,
) -> dict[str, Any]:
    if scenario.get("rule_set_snapshot") is not None:
        return frozen_profitability(scenario, rows)
    inputs = await repo.get_profitability_inputs(
        site_codes=[row["site_code"] for row in rows],
        target_month=scenario["target_month"],
    )
    return populate_profitability(scenario, rows, inputs, constants)
