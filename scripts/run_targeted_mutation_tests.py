#!/usr/bin/env python3
"""Deterministic mutation gate for critical Retail business boundaries."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]


def load_mutant(source: Path, old: str, new: str, name: str) -> ModuleType:
    original = source.read_text(encoding="utf-8")
    if original.count(old) != 1:
        raise RuntimeError(f"{source}: mutation anchor is not unique: {old!r}")
    with tempfile.TemporaryDirectory(prefix="retail-mutant-") as directory:
        target = Path(directory) / source.name
        target.write_text(original.replace(old, new), encoding="utf-8")
        spec = importlib.util.spec_from_file_location(name, target)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load mutant {name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(name, None)
            raise
        return module


def expect_killed(label: str, probe: Callable[[], None]) -> None:
    try:
        probe()
    except Exception:
        print(f"KILLED {label}")
        return
    raise RuntimeError(f"SURVIVED {label}")


def main() -> int:
    calculations = ROOT / "backend/services/target_calculator/calculations.py"
    scenarios = ROOT / "backend/services/target_calculator/scenarios.py"
    asm_salary = ROOT / "backend/services/asm_salary.py"
    sales_generation = ROOT / "backend/services/sales_generation.py"
    grile_monthly_state = ROOT / "backend/grile/domain/monthly_state.py"

    rounding = load_mutant(
        calculations,
        "rounding=ROUND_HALF_UP",
        "rounding=__import__('decimal').ROUND_DOWN",
        "mutant_rounding",
    )
    expect_killed("money-half-up-to-down", lambda: assert_equal(rounding.money("1.005"), Decimal("1.01")))

    stale_bounds = load_mutant(
        calculations,
        'if value < row["floor_target"]:',
        'if False and value < row["floor_target"]:',
        "mutant_stale_bounds",
    )
    expect_killed(
        "target-floor-cap-active-set-recomputation",
        lambda: assert_equal(
            target_allocations(stale_bounds),
            ([Decimal("50.00"), Decimal("54.00"), Decimal("6.00")], [["FLOOR_APPLIED"], [], []]),
        ),
    )

    wrong_remainder = load_mutant(
        calculations,
        "assigned[index] - bases[index]",
        "bases[index] - assigned[index]",
        "mutant_wrong_remainder",
    )
    expect_killed(
        "target-largest-remainder-order",
        lambda: assert_equal(
            remainder_allocations(wrong_remainder),
            [Decimal("0.33"), Decimal("0.67")],
        ),
    )

    editable = load_mutant(scenarios, '== "draft"', '!= "draft"', "mutant_editable")
    expect_killed(
        "draft-editability-inverted",
        lambda: assert_equal(
            (editable.is_editable_scenario({"status": "draft"}), editable.is_editable_scenario({"status": "finalized"})),
            (True, False),
        ),
    )

    pending = load_mutant(scenarios, "> 0", ">= 0", "mutant_pending")
    expect_killed(
        "pending-zero-boundary",
        lambda: assert_equal(
            (pending.has_pending_final_targets({"pending_final_count": 0}), pending.has_pending_final_targets({"pending_final_count": 1})),
            (False, True),
        ),
    )

    asm_boundary = load_mutant(
        asm_salary,
        "if exact_pct >= threshold:",
        "if exact_pct > threshold:",
        "mutant_asm_boundary",
    )
    expect_killed(
        "asm-tier-inclusive-boundary",
        lambda: assert_equal(
            asm_boundary.commission_for_tier(Decimal("79"), asm_boundary.ZONE_TARGET_TIERS),
            700,
        ),
    )

    import_promotion = load_mutant(
        sales_generation,
        "if classification == SalesAnomalyClassification.STRUCTURAL_CONTRADICTION.value:",
        "if classification != SalesAnomalyClassification.STRUCTURAL_CONTRADICTION.value:",
        "mutant_import_promotion",
    )
    expect_killed(
        "import-structural-anomaly-blocks-promotion",
        lambda: assert_equal(
            (
                import_promotion.manifest_has_structural_contradictions(
                    {"anomalies": [{"classification": "structural_contradiction"}]}
                ),
                import_promotion.manifest_has_structural_contradictions(
                    {"anomalies": [{"classification": "informational"}]}
                ),
            ),
            (True, False),
        ),
    )

    grile_completion = load_mutant(
        grile_monthly_state,
        "(MonthlyOperationState.RUNNING, MonthlyOperationEvent.COMPLETE): MonthlyOperationState.COMPLETED,",
        "(MonthlyOperationState.RUNNING, MonthlyOperationEvent.COMPLETE): MonthlyOperationState.FAILED,",
        "mutant_grile_completion",
    )
    expect_killed(
        "grile-running-completes-successfully",
        lambda: assert_equal(
            grile_completion.transition_monthly_operation("running", "complete").current.value,
            "completed",
        ),
    )

    print("Mutation score: 8/8 = 100%")
    return 0


def assert_equal(actual: object, expected: object) -> None:
    assert actual == expected, f"expected {expected!r}, got {actual!r}"


def target_row(weight: str, floor: str, cap: str, site_code: str) -> dict[str, object]:
    return {
        "calculated_weight": Decimal(weight),
        "floor_target": Decimal(floor),
        "cap_target": Decimal(cap),
        "site_code": site_code,
        "flags": [],
    }


def target_allocations(module: ModuleType) -> tuple[list[Decimal], list[list[str]]]:
    rows = [
        target_row("1", "50", "100", "A"),
        target_row("9", "0", "80", "B"),
        target_row("1", "0", "100", "C"),
    ]
    allocated, _ = module.allocate_with_bounds(rows, Decimal("110"))
    return (
        [row["proposed_target"] for row in allocated],
        [row["flags"] for row in allocated],
    )


def remainder_allocations(module: ModuleType) -> list[Decimal]:
    rows = [
        target_row("1", "0", "100", "A"),
        target_row("2", "0", "100", "Z"),
    ]
    allocated, _ = module.allocate_with_bounds(rows, Decimal("1"))
    return [row["proposed_target"] for row in allocated]


if __name__ == "__main__":
    raise SystemExit(main())
