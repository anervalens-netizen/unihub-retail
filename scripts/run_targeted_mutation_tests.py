#!/usr/bin/env python3
"""Deterministic mutation gate for money and Target state transitions."""

from __future__ import annotations

import importlib.util
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
        spec.loader.exec_module(module)
        return module


def expect_killed(label: str, probe: Callable[[], None]) -> None:
    try:
        probe()
    except AssertionError:
        print(f"KILLED {label}")
        return
    raise RuntimeError(f"SURVIVED {label}")


def main() -> int:
    calculations = ROOT / "backend/services/target_calculator/calculations.py"
    scenarios = ROOT / "backend/services/target_calculator/scenarios.py"

    rounding = load_mutant(
        calculations,
        "rounding=ROUND_HALF_UP",
        "rounding=__import__('decimal').ROUND_DOWN",
        "mutant_rounding",
    )
    expect_killed("money-half-up-to-down", lambda: assert_equal(rounding.money("1.005"), Decimal("1.01")))

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
    print("Mutation score: 3/3 = 100%")
    return 0


def assert_equal(actual: object, expected: object) -> None:
    assert actual == expected, f"expected {expected!r}, got {actual!r}"


if __name__ == "__main__":
    raise SystemExit(main())
