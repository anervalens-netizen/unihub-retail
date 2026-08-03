from __future__ import annotations

import json
from decimal import Decimal
from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

import services.target_calculator as target
from repositories.target_calculator import TargetScenarioAlgorithmMismatch
from services.target_calculator import (
    CALCULATION_METHOD,
    TargetBudgetInfeasibleError,
    TargetCalculatorService,
    allocate_with_bounds,
    allocate_with_floors,
)
from services.target_rule_registry import canonical_rules_hash, validate_target_rule_set


def rule_record() -> dict[str, Any]:
    rules: dict[str, Any] = {
        "vat": {
            "ruleset_id": "ro-standard-vat-v1",
            "rule_id": "ro-standard-vat-21",
            "rate": "0.21",
            "multiplier": "1.21",
        },
        "salary": {
            "pnl_factor": "1.6955",
            "meal_vouchers_per_agent": "480",
            "sales_commission_rate": "0.03",
            "assumed_attainment": "0.90",
            "default_agent_count": 2,
            "base_salary": "2400",
        },
        "store_exceptions": {},
    }
    return {
        "id": "target-finance-coverage-v1",
        "version": 1,
        "effective_from_month": "1900-01",
        "effective_to_month": None,
        "rules": rules,
        "rules_sha256": canonical_rules_hash(rules),
    }


def bounded_row(weight: str = "1", floor: str = "0", cap: str = "100") -> dict[str, Any]:
    return {
        "calculated_weight": Decimal(weight),
        "floor_target": Decimal(floor),
        "cap_target": Decimal(cap),
        "proposed_target": Decimal("0"),
        "is_floor_limited": False,
        "is_cap_limited": False,
        "allocation_reason": "proportional",
        "flags": [],
    }


def make_calculation_service() -> tuple[TargetCalculatorService, MagicMock]:
    repo = MagicMock()
    repo.get_latest_sales_month = AsyncMock(return_value="2026-05")
    repo.get_active_cohort = AsyncMock(return_value=[
        {
            "site_code": "SITE01",
            "locatie": "Magazin 1",
            "firma": "Mobiup",
            "regional": "Regional A",
            "asm": "ASM",
        }
    ])
    repo.get_effective_target_rule_set = AsyncMock(return_value=rule_record())
    repo.get_target_rule_exception_master = AsyncMock(return_value=[])
    repo.get_source_metrics = AsyncMock(return_value=[])
    repo.save_draft_scenario = AsyncMock(return_value=9)
    repo.get_profitability_inputs = AsyncMock(return_value={
        "pnl_months": [],
        "pnl_rows": [],
        "forecast_run": {
            "id": 1,
            "model_name": "coverage-test",
            "model_mode": "test",
            "variant": "test",
            "generated_at": "2026-08-01T00:00:00",
            "source_month": "2026-05",
        },
        "forecast_rows": [{
            "site_code": "SITE01",
            "forecast_sales": Decimal("0"),
            "forecast_present": True,
            "realized_present": True,
            "cutoff_date": "2026-05-31",
        }],
    })
    connection = MagicMock()
    repo.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=connection)
    repo.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return TargetCalculatorService(repo), repo


def calculation_payload() -> dict[str, Any]:
    return {
        "target_month": "2026-06",
        "total_target": 35000,
        "min_floor": 35000,
        "previous_month_floor_pct": 0,
        "previous_month_cap_pct": 1.7,
        "expected_revision": 2,
    }


def profitability_inputs() -> dict[str, Any]:
    return {
        "pnl_months": ["2026-02", "2026-03", "2026-04"],
        "pnl_rows": [
            {"site_code": "SITE01", "category_code": "v11", "amount": Decimal("30000")},
            {"site_code": "SITE01", "category_code": "c11", "amount": Decimal("12000")},
            {"site_code": "SITE01", "category_code": "c4", "amount": Decimal("3000")},
            {"site_code": "SITE01", "category_code": "c5", "amount": Decimal("6000")},
            {"site_code": "SITE01", "category_code": "c6", "amount": Decimal("9000")},
        ],
        "forecast_run": None,
        "forecast_rows": [],
    }


def export_history(previous: float, previous_year_target: float) -> list[dict[str, Any]]:
    return [
        {"month": "2025-05", "target": 100, "realized": 100, "attainment_pct": 100},
        {"month": "2025-06", "target": 100, "realized": previous_year_target, "attainment_pct": previous_year_target},
        {"month": "2026-05", "target": 100, "realized": previous, "attainment_pct": previous},
    ]


def export_row(
    manager: str,
    site_code: str,
    proposed_target: float,
    previous: float,
    previous_year_target: float,
    forecast: float | None,
) -> dict[str, Any]:
    return {
        "firma": "Mobiup",
        "regional": manager,
        "locatie": f"{manager} Store",
        "site_code": site_code,
        "calculated_weight": 1.0,
        "proposed_target": proposed_target,
        "final_target": proposed_target,
        "history": export_history(previous, previous_year_target),
        "profitability": {
            "forecast_sales": forecast,
            "salary_cost_at_90_pct": 1000.0,
            "operating_costs": 500.0,
            "break_even_gross_sales": 2000.0,
        },
    }


def export_scenario() -> dict[str, Any]:
    return {
        "id": 9,
        "status": "draft",
        "target_month": "2026-06",
        "cohort_month": "2026-05",
        "total_target": 315,
        "min_floor": 0,
        "previous_month_floor_pct": 0,
        "calculation_method": CALCULATION_METHOD,
        "source_months": [],
        "warnings": [],
        "calculation_params": {},
        "source_summary": [],
        "profitability_summary": {},
        "regional_summary": [],
        "rows": [
            export_row("AI Manager", "SITE-AI", 110, 100, 100, 100),
            export_row("Season Manager", "SITE-SEASON", 115, 100, 110, None),
            export_row("Balanced Manager", "SITE-BALANCED", 90, 100, 100, 100),
        ],
    }


def test_uncovered_allocator_guards_and_bound_marking() -> None:
    assert target.month_label_ro("not-a-month") == "not-a-month"

    with pytest.raises(ValueError, match="sub floor"):
        target._normalize_bounds([bounded_row(floor="10", cap="9")], include_caps=True)

    no_capacity = bounded_row(floor="0", cap="10")
    no_capacity["proposed_target"] = Decimal("10")
    with pytest.raises(TargetBudgetInfeasibleError):
        target._apply_rounding_difference([no_capacity], Decimal("11"), include_caps=True)

    floor_row = bounded_row(floor="9", cap="20")
    floor_row["proposed_target"] = Decimal("10")
    target._apply_rounding_difference([floor_row], Decimal("9"), include_caps=True)
    assert floor_row["is_floor_limited"] is True


def test_allocators_detect_unreconciled_rounding_totals(monkeypatch: pytest.MonkeyPatch) -> None:
    def skip_rounding(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(target, "_apply_rounding_difference", skip_rounding)
    floor_rows = [
        {"calculated_weight": Decimal("1"), "floor_target": Decimal("0")},
        {"calculated_weight": Decimal("1"), "floor_target": Decimal("0")},
        {"calculated_weight": Decimal("1"), "floor_target": Decimal("0")},
    ]
    with pytest.raises(TargetBudgetInfeasibleError):
        allocate_with_floors(floor_rows, Decimal("100"))

    bound_rows = [bounded_row(floor="0", cap="100") for _ in range(3)]
    with pytest.raises(TargetBudgetInfeasibleError):
        allocate_with_bounds(bound_rows, Decimal("100"))


def test_target_rule_snapshot_and_legacy_profitability_guards() -> None:
    assumptions = TargetCalculatorService._saved_profitability_assumptions({
        "calculation_params": {"profitability": {}},
    })
    assert assumptions["vat_multiplier"] == 1.21
    rate_only = TargetCalculatorService._saved_profitability_assumptions({
        "calculation_params": {"profitability": {"vat_rate": 0.21}},
    })
    assert rate_only["vat_multiplier"] == 1.21

    snapshot = validate_target_rule_set(rule_record(), "2026-06").snapshot()
    loaded = TargetCalculatorService._saved_target_rule_set({
        "target_month": "2026-06",
        "rule_set_snapshot": json.dumps(snapshot),
    })
    assert loaded is not None

    with pytest.raises(HTTPException, match="nu este JSON valid"):
        TargetCalculatorService._saved_target_rule_set({
            "target_month": "2026-06",
            "rule_set_snapshot": "{" ,
        })

    with pytest.raises(HTTPException, match="este invalid"):
        TargetCalculatorService._saved_target_rule_set({
            "target_month": "2026-06",
            "rule_set_snapshot": {"schema_version": 999},
        })

    with pytest.raises(HTTPException, match="este incomplet"):
        TargetCalculatorService._saved_target_rule_set({
            "target_month": "2026-06",
            "rule_set_snapshot": {"schema_version": 1},
        })


@pytest.mark.asyncio
async def test_calculate_rejects_missing_invalid_and_infeasible_rule_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repo = make_calculation_service()
    monkeypatch.setattr(target, "get_forecast_factor", AsyncMock(return_value=Decimal("1")))

    repo.get_effective_target_rule_set.return_value = None
    with pytest.raises(HTTPException, match="Nu exista un rule-set"):
        await service.calculate(calculation_payload())

    repo.get_effective_target_rule_set.return_value = {"invalid": True}
    with pytest.raises(HTTPException, match="Rule-set-ul Target este invalid"):
        await service.calculate(calculation_payload())

    repo.get_effective_target_rule_set.return_value = rule_record()

    def fail_allocation(_rows: list[dict[str, Any]], _budget: Decimal) -> tuple[list[dict[str, Any]], list[str]]:
        raise TargetBudgetInfeasibleError(Decimal("35000"), Decimal("35000"), Decimal("35000"))

    monkeypatch.setattr(target, "allocate_with_bounds", fail_allocation)
    with pytest.raises(HTTPException, match="Bugetul Target este infezabil"):
        await service.calculate(calculation_payload())


@pytest.mark.asyncio
async def test_calculate_maps_algorithm_mismatch_without_writing_a_new_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repo = make_calculation_service()
    repo.save_draft_scenario.side_effect = TargetScenarioAlgorithmMismatch()
    monkeypatch.setattr(target, "get_forecast_factor", AsyncMock(return_value=Decimal("1")))

    with pytest.raises(HTTPException, match="altei versiuni de algoritm"):
        await service.calculate(calculation_payload())



def test_profitability_uses_saved_vat_snapshot_and_marks_target_below_break_even() -> None:
    service = TargetCalculatorService(MagicMock())
    rows = [{"site_code": "SITE01", "calculated_weight": Decimal("1"), "proposed_target": Decimal("1")}]
    summary = service._populate_profitability(
        {
            "target_month": "2025-07",
            "calculation_params": {"profitability": {"vat_multiplier": 1.21}},
        },
        rows,
        profitability_inputs(),
    )

    assert summary["status"] == "partial"
    profitability = rows[0].get("profitability")
    assert isinstance(profitability, dict)
    assert profitability["break_even_gross_sales"] > 0
    assert "TARGET_BELOW_BREAK_EVEN" in profitability["anomaly_flags"]


def frozen_scenario() -> tuple[dict[str, Any], dict[str, Any]]:
    record = rule_record()
    snapshot = validate_target_rule_set(record, "2026-06").snapshot()
    input_hash = "a" * 64
    scenario = {
        "target_month": "2026-06",
        "rule_set_id": record["id"],
        "rule_set_hash": record["rules_sha256"],
        "rule_set_snapshot": snapshot,
        "profitability_input_sha256": input_hash,
        "calculation_params": {"profitability_summary": {"input_sha256": input_hash}},
    }
    return scenario, snapshot


def test_frozen_profitability_rejects_incomplete_mismatched_and_bad_store_snapshots() -> None:
    service = TargetCalculatorService(MagicMock())
    scenario, _snapshot = frozen_scenario()

    incomplete = {**scenario, "calculation_params": {"profitability_summary": None}}
    with pytest.raises(HTTPException, match="este incomplet"):
        service._frozen_profitability(incomplete, [])

    mismatched = {**scenario, "calculation_params": {"profitability_summary": {"input_sha256": "b" * 64}}}
    with pytest.raises(HTTPException, match="nu corespunde"):
        service._frozen_profitability(mismatched, [])

    valid_row = {"profitability_snapshot": json.dumps({"agent_count": 2})}
    summary = service._frozen_profitability(scenario, [valid_row])
    assert summary["input_sha256"] == "a" * 64
    assert valid_row["profitability"] == {"agent_count": 2}

    with pytest.raises(HTTPException, match="nu este JSON valid"):
        service._frozen_profitability(scenario, [{"profitability_snapshot": "{"}])

    with pytest.raises(HTTPException, match="lipseste"):
        service._frozen_profitability(scenario, [{"profitability_snapshot": None}])


def test_row_serialization_decodes_profitability_snapshot() -> None:
    service = TargetCalculatorService(MagicMock())
    row = {"profitability_snapshot": json.dumps({"salary": 100})}

    serialized = service._serialize_row(row)

    assert serialized["profitability_snapshot"] == {"salary": 100}
    assert serialized["calculation_details"] == {}


@pytest.mark.asyncio
async def test_export_covers_manager_signals_negative_deltas_and_signal_styles() -> None:
    service = TargetCalculatorService(MagicMock())
    scenario = export_scenario()
    with patch.object(service, "get_scenario_detail", new=AsyncMock(return_value=scenario)):
        output, _filename = await service.export_excel(9)

    workbook = load_workbook(BytesIO(output.getvalue()))
    comparison = workbook["Comparație manageri"]
    signals = {comparison[f"M{row}"].value for row in range(10, 14)}
    assert signals == {"Peste AI", "Peste sezonier", "Echilibrat", "Rețea"}
    assert comparison["E5"].font.bold is True
    assert comparison["M10"].fill.fgColor.rgb in {"00FFF2CC", "FFF2CC"}
    assert comparison["M11"].fill.fgColor.rgb in {"00F4CCCC", "F4CCCC"}
