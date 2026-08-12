"""Exact and mutation-killing Target allocator contract."""
from __future__ import annotations

from decimal import Decimal
from itertools import permutations
from typing import Any

from services.target_calculator import calculations
from services.target_calculator.calculations import (
    _clip_box_value,
    _solve_box_allocations,
    _solve_box_interval,
    allocate_with_bounds,
    money,
)


def _row(site: str, weight: str, floor: str, cap: str) -> dict[str, Any]:
    return {
        "site_code": site,
        "calculated_weight": Decimal(weight),
        "floor_target": Decimal(floor),
        "cap_target": Decimal(cap),
        "flags": [],
    }


EXACT_ROWS = (
    ("A", "9000", "15000.00", "42000.00"),
    ("B", "18000", "30000.00", "66000.00"),
    ("C", "6000", "18000.00", "18000.00"),
    ("D", "0", "26000.00", "31000.00"),
    ("E", "18000", "12000.00", "26000.00"),
)
EXACT_EXPECTED = {
    "A": (Decimal("15000.00"), ["FLOOR_APPLIED"], "floor"),
    "B": (Decimal("30000.00"), ["FLOOR_APPLIED"], "floor"),
    "C": (Decimal("18000.00"), ["FLOOR_APPLIED", "CAP_APPLIED"], "floor_cap"),
    "D": (Decimal("26000.00"), ["FLOOR_APPLIED"], "floor"),
    "E": (Decimal("26000.00"), ["CAP_APPLIED"], "cap"),
}


def _allocation_by_site(rows: list[dict[str, Any]]) -> dict[str, tuple[Decimal, list[str], str]]:
    allocated, warnings = allocate_with_bounds(rows, Decimal("115000.00"))
    assert warnings == []
    assert sum((row["proposed_target"] for row in allocated), Decimal("0")) == Decimal(
        "115000.00"
    )
    return {
        str(row["site_code"]): (
            row["proposed_target"],
            row["flags"],
            row["allocation_reason"],
        )
        for row in allocated
    }


def test_exact_breakpoint_115000_all_120_permutations() -> None:
    for order in permutations(EXACT_ROWS):
        assert _allocation_by_site([_row(*values) for values in order]) == EXACT_EXPECTED


def test_money_half_up_boundary() -> None:
    assert money("1.005") == Decimal("1.01")


def test_floor_clipping_strict_direction() -> None:
    row = _row("A", "1", "10", "20")
    assert _clip_box_value(row, Decimal("9.99")) == Decimal("10")
    assert _clip_box_value(row, Decimal("10")) == Decimal("10")


def test_cap_clipping_strict_direction() -> None:
    row = _row("A", "1", "10", "20")
    assert _clip_box_value(row, Decimal("20.01")) == Decimal("20")
    assert _clip_box_value(row, Decimal("20")) == Decimal("20")


def test_budget_equal_floor_is_feasible() -> None:
    rows = [_row("A", "1", "10", "30"), _row("B", "2", "20", "50")]
    allocated, _ = allocate_with_bounds(rows, Decimal("30"))
    assert [row["proposed_target"] for row in allocated] == [
        Decimal("10.00"),
        Decimal("20.00"),
    ]


def test_budget_equal_cap_is_feasible() -> None:
    rows = [_row("A", "1", "10", "30"), _row("B", "2", "20", "50")]
    allocated, _ = allocate_with_bounds(rows, Decimal("80"))
    assert [row["proposed_target"] for row in allocated] == [
        Decimal("30.00"),
        Decimal("50.00"),
    ]


def test_active_floor_breakpoint_boundary() -> None:
    rows = [_row("A", "1", "10", "20")]
    result = _solve_box_interval(
        rows,
        [0],
        {0: Decimal("1")},
        Decimal("10"),
        Decimal("0"),
        Decimal("20"),
    )
    assert result is None


def test_active_cap_breakpoint_boundary() -> None:
    rows = [_row("A", "1", "0", "10")]
    result = _solve_box_interval(
        rows,
        [0],
        {0: Decimal("1")},
        Decimal("10"),
        Decimal("0"),
        Decimal("20"),
    )
    assert result is None


def test_zero_weight_reserve_at_weighted_limit(monkeypatch: Any) -> None:
    rows = [_row("P", "1", "0", "60"), _row("Z", "0", "10", "50")]
    calls: list[tuple[int, ...]] = []
    original = calculations._solve_positive_box

    def traced(
        traced_rows: list[dict[str, Any]],
        indices: list[int],
        target: Decimal,
        weights: dict[int, Decimal],
    ) -> dict[int, Decimal]:
        calls.append(tuple(indices))
        return original(traced_rows, indices, target, weights)

    monkeypatch.setattr(calculations, "_solve_positive_box", traced)
    assigned = _solve_box_allocations(rows, Decimal("70"))
    assert calls == [(0,)]
    assert assigned == {0: Decimal("60"), 1: Decimal("10")}


def test_largest_fractional_remainder_gets_cent() -> None:
    rows = [_row("A", "1", "0", "100"), _row("Z", "2", "0", "100")]
    allocated, _ = allocate_with_bounds(rows, Decimal("1"))
    assert [row["proposed_target"] for row in allocated] == [
        Decimal("0.33"),
        Decimal("0.67"),
    ]


def test_equal_remainder_uses_site_code_not_input_order() -> None:
    rows = [_row("Z", "1", "0", "100"), _row("A", "1", "0", "100")]
    allocated, _ = allocate_with_bounds(rows, Decimal("0.01"))
    assert {row["site_code"]: row["proposed_target"] for row in allocated} == {
        "A": Decimal("0.01"),
        "Z": Decimal("0.00"),
    }
