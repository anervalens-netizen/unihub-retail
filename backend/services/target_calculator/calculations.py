"""Pure Decimal allocation primitives for Target Calculator."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

MONEY = Decimal("0.01")


def money(value: Decimal | int | str | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


class TargetBudgetInfeasibleError(ValueError):
    def __init__(self, requested_total: Decimal, floor_total: Decimal, cap_total: Decimal | None = None):
        self.requested_total = money(requested_total)
        self.floor_total = money(floor_total)
        self.cap_total = money(cap_total) if cap_total is not None else None
        detail = (
            "Bugetul este sub suma floor-urilor"
            if self.requested_total < self.floor_total
            else "Bugetul depaseste suma cap-urilor"
        )
        super().__init__(detail)


def _mark_bound(row: dict[str, Any], *, floor: bool = False, cap: bool = False) -> None:
    if floor:
        row["is_floor_limited"] = True
        row["allocation_reason"] = "floor"
        if "FLOOR_APPLIED" not in row["flags"]:
            row["flags"].append("FLOOR_APPLIED")
    if cap:
        row["is_cap_limited"] = True
        row["allocation_reason"] = "cap"
        if "CAP_APPLIED" not in row["flags"]:
            row["flags"].append("CAP_APPLIED")


def _normalize_bounds(rows: list[dict[str, Any]], include_caps: bool) -> tuple[Decimal, Decimal | None]:
    floor_total = Decimal("0")
    cap_total = Decimal("0") if include_caps else None
    for row in rows:
        row["floor_target"] = money(row["floor_target"])
        row.setdefault("is_floor_limited", False)
        row.setdefault("is_cap_limited", False)
        row.setdefault("allocation_reason", "proportional")
        row.setdefault("flags", [])
        floor_total += row["floor_target"]
        if include_caps:
            row["cap_target"] = money(row["cap_target"])
            if row["cap_target"] < row["floor_target"]:
                raise ValueError("Cap-ul unei locatii nu poate fi sub floor.")
            cap_total = (cap_total or Decimal("0")) + row["cap_target"]
    return floor_total, cap_total


def _apply_rounding_difference(
    rows: list[dict[str, Any]],
    requested_total: Decimal,
    *,
    include_caps: bool,
) -> None:
    """Distribute the final cent residual deterministically over available capacity."""
    rounded_total = sum((row["proposed_target"] for row in rows), Decimal("0"))
    difference = money(requested_total - rounded_total)
    if not difference:
        return

    increase = difference > 0
    remaining = abs(difference)
    while remaining > 0:
        candidates: list[tuple[Decimal, str, int, dict[str, Any]]] = []
        for index, row in enumerate(rows):
            capacity = (
                row["cap_target"] - row["proposed_target"]
                if increase and include_caps
                else row["proposed_target"] - row["floor_target"]
                if not increase
                else remaining
            )
            capacity = money(capacity)
            if capacity > 0:
                candidates.append((capacity, str(row.get("site_code", "")), index, row))
        if not candidates:
            floor_total, cap_total = _normalize_bounds(rows, include_caps)
            raise TargetBudgetInfeasibleError(requested_total, floor_total, cap_total)

        for capacity, _site_code, _index, row in sorted(
            candidates,
            key=lambda candidate: (-candidate[0], candidate[1], candidate[2]),
        ):
            step = min(capacity, remaining)
            row["proposed_target"] = money(
                row["proposed_target"] + step if increase else row["proposed_target"] - step
            )
            remaining = money(remaining - step)
            if include_caps and row["proposed_target"] == row["cap_target"]:
                _mark_bound(row, cap=True)
            if row["proposed_target"] == row["floor_target"]:
                _mark_bound(row, floor=True)
            if not remaining:
                return


def allocate_with_floors(
    rows: list[dict[str, Any]],
    requested_total: Decimal,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Allocate an exactly feasible budget proportionally while honoring floors."""
    if not rows:
        return rows, []
    requested_total = money(requested_total)
    floor_total, _ = _normalize_bounds(rows, include_caps=False)
    if floor_total > requested_total:
        raise TargetBudgetInfeasibleError(requested_total, floor_total)

    remaining = set(range(len(rows)))
    assigned: dict[int, Decimal] = {}
    remaining_budget = requested_total
    while remaining:
        weight_total = sum((rows[index]["calculated_weight"] for index in remaining), Decimal("0"))
        allocations = {
            index: (
                remaining_budget * rows[index]["calculated_weight"] / weight_total
                if weight_total > 0
                else remaining_budget / Decimal(len(remaining))
            )
            for index in remaining
        }
        below_floor = {index for index in remaining if allocations[index] < rows[index]["floor_target"]}
        if not below_floor:
            assigned.update(allocations)
            break
        for index in below_floor:
            assigned[index] = rows[index]["floor_target"]
            remaining_budget -= rows[index]["floor_target"]
            _mark_bound(rows[index], floor=True)
        remaining -= below_floor

    for index, row in enumerate(rows):
        row["proposed_target"] = money(assigned[index])
    _apply_rounding_difference(rows, requested_total, include_caps=False)
    if sum((row["proposed_target"] for row in rows), Decimal("0")) != requested_total:
        raise TargetBudgetInfeasibleError(requested_total, floor_total)
    return rows, []


def allocate_with_bounds(
    rows: list[dict[str, Any]],
    requested_total: Decimal,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Allocate only a budget that can exactly satisfy every floor and cap."""
    if not rows:
        return rows, []
    requested_total = money(requested_total)
    floor_total, cap_total = _normalize_bounds(rows, include_caps=True)
    assert cap_total is not None
    if requested_total < floor_total or requested_total > cap_total:
        raise TargetBudgetInfeasibleError(requested_total, floor_total, cap_total)

    remaining = set(range(len(rows)))
    assigned: dict[int, Decimal] = {}
    remaining_budget = requested_total
    while remaining:
        weight_total = sum((rows[index]["calculated_weight"] for index in remaining), Decimal("0"))
        allocations = {
            index: (
                remaining_budget * rows[index]["calculated_weight"] / weight_total
                if weight_total > 0
                else remaining_budget / Decimal(len(remaining))
            )
            for index in remaining
        }
        fixed = False
        for index in sorted(remaining):
            row = rows[index]
            if allocations[index] < row["floor_target"]:
                assigned[index] = row["floor_target"]
                remaining_budget -= row["floor_target"]
                remaining.remove(index)
                _mark_bound(row, floor=True)
                fixed = True
            elif allocations[index] > row["cap_target"]:
                assigned[index] = row["cap_target"]
                remaining_budget -= row["cap_target"]
                remaining.remove(index)
                _mark_bound(row, cap=True)
                fixed = True
        if not fixed:
            assigned.update(allocations)
            break

    for index, row in enumerate(rows):
        row["proposed_target"] = money(assigned[index])
    _apply_rounding_difference(rows, requested_total, include_caps=True)
    for row in rows:
        if row["proposed_target"] == row["floor_target"]:
            _mark_bound(row, floor=True)
        if row["proposed_target"] == row["cap_target"]:
            _mark_bound(row, cap=True)
    final_total = sum((row["proposed_target"] for row in rows), Decimal("0"))
    if final_total != requested_total or any(
        row["proposed_target"] < row["floor_target"] or row["proposed_target"] > row["cap_target"]
        for row in rows
    ):
        raise TargetBudgetInfeasibleError(requested_total, floor_total, cap_total)
    return rows, []
