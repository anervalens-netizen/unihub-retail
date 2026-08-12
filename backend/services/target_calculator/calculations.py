"""Pure Decimal allocation primitives for Target Calculator."""

from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP, localcontext
from typing import Any

MONEY = Decimal("0.01")
_BOUND_FLAGS = {"FLOOR_APPLIED", "CAP_APPLIED"}


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


def _reset_bound_state(row: dict[str, Any]) -> None:
    """Remove only allocator-owned state before deriving it from final values."""
    row["is_floor_limited"] = False
    row["is_cap_limited"] = False
    row["allocation_reason"] = "proportional"
    row["flags"] = [flag for flag in row.get("flags", []) if flag not in _BOUND_FLAGS]


def _mark_final_bounds(row: dict[str, Any]) -> None:
    """Derive bound flags exclusively from the final cent allocation."""
    at_floor = row["proposed_target"] == row["floor_target"]
    at_cap = row["proposed_target"] == row["cap_target"]
    row["is_floor_limited"] = at_floor
    row["is_cap_limited"] = at_cap
    if at_floor:
        row["flags"].append("FLOOR_APPLIED")
    if at_cap:
        row["flags"].append("CAP_APPLIED")
    if at_floor and at_cap:
        row["allocation_reason"] = "floor_cap"
    elif at_floor:
        row["allocation_reason"] = "floor"
    elif at_cap:
        row["allocation_reason"] = "cap"
    else:
        row["allocation_reason"] = "proportional"


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


def _stable_indices(rows: list[dict[str, Any]], indices: list[int]) -> list[int]:
    return sorted(indices, key=lambda index: (str(rows[index].get("site_code", "")), index))


def _clip_box_value(row: dict[str, Any], value: Decimal) -> Decimal:
    if value < row["floor_target"]:
        return row["floor_target"]
    if value > row["cap_target"]:
        return row["cap_target"]
    return value


def _box_allocations_at(
    rows: list[dict[str, Any]],
    ordered: list[int],
    weights: dict[int, Decimal],
    multiplier: Decimal,
) -> dict[int, Decimal]:
    return {
        index: _clip_box_value(rows[index], multiplier * weights[index])
        for index in ordered
    }


def _decimal_breakpoint_equal(left: Decimal, right: Decimal) -> bool:
    """Ignore only division dust far below one cent, never a rounded cent gap."""
    return abs(left - right) <= Decimal("1e-30")


def _reconcile_box_residual(
    rows: list[dict[str, Any]],
    allocations: dict[int, Decimal],
    active: list[int],
    target: Decimal,
) -> dict[int, Decimal] | None:
    residual = target - sum(allocations.values(), Decimal("0"))
    if not residual:
        return allocations
    for index in _stable_indices(rows, active):
        adjusted = allocations[index] + residual
        if rows[index]["floor_target"] <= adjusted <= rows[index]["cap_target"]:
            allocations[index] = adjusted
            return allocations
    return None


def _solve_box_interval(
    rows: list[dict[str, Any]],
    ordered: list[int],
    weights: dict[int, Decimal],
    target: Decimal,
    previous_point: Decimal,
    point: Decimal,
) -> dict[int, Decimal] | None:
    midpoint = (previous_point + point) / Decimal("2")
    active = [
        index
        for index in ordered
        if rows[index]["floor_target"] < midpoint * weights[index] < rows[index]["cap_target"]
    ]
    if not active:
        return None
    fixed_total = sum(
        (
            rows[index]["floor_target"]
            if midpoint * weights[index] <= rows[index]["floor_target"]
            else rows[index]["cap_target"]
        )
        for index in ordered
        if index not in active
    )
    active_weight = sum((weights[index] for index in active), Decimal("0"))
    allocations = _box_allocations_at(
        rows,
        ordered,
        weights,
        (target - fixed_total) / active_weight,
    )
    return _reconcile_box_residual(rows, allocations, active, target)


def _solve_positive_box(
    rows: list[dict[str, Any]],
    indices: list[int],
    target: Decimal,
    weights: dict[int, Decimal],
) -> dict[int, Decimal]:
    """Solve sum(clip(multiplier * weight, floor, cap)) == target exactly."""
    ordered = _stable_indices(rows, indices)
    floor_total = sum((rows[index]["floor_target"] for index in ordered), Decimal("0"))
    cap_total = sum((rows[index]["cap_target"] for index in ordered), Decimal("0"))
    if target == floor_total:
        return {index: rows[index]["floor_target"] for index in ordered}
    if target == cap_total:
        return {index: rows[index]["cap_target"] for index in ordered}
    if target < floor_total or target > cap_total:
        raise TargetBudgetInfeasibleError(target, floor_total, cap_total)

    with localcontext() as context:
        context.prec = 60
        breakpoints = sorted(
            {
                bound / weights[index]
                for index in ordered
                for bound in (rows[index]["floor_target"], rows[index]["cap_target"])
            }
        )

        lower_index = 0
        upper_index = len(breakpoints) - 1
        previous_point = breakpoints[lower_index]
        previous_allocations = _box_allocations_at(rows, ordered, weights, previous_point)
        previous_total = sum(previous_allocations.values(), Decimal("0"))
        if _decimal_breakpoint_equal(target, previous_total):
            return previous_allocations
        if target < previous_total:
            return {index: rows[index]["floor_target"] for index in ordered}

        while upper_index - lower_index > 1:
            middle_index = (lower_index + upper_index) // 2
            middle_allocations = _box_allocations_at(
                rows, ordered, weights, breakpoints[middle_index]
            )
            middle_total = sum(middle_allocations.values(), Decimal("0"))
            if _decimal_breakpoint_equal(target, middle_total):
                return middle_allocations
            if target > middle_total:
                lower_index = middle_index
            else:
                upper_index = middle_index

        previous_point = breakpoints[lower_index]
        point = breakpoints[upper_index]
        previous_allocations = _box_allocations_at(rows, ordered, weights, previous_point)
        point_allocations = _box_allocations_at(rows, ordered, weights, point)
        previous_total = sum(previous_allocations.values(), Decimal("0"))
        point_total = sum(point_allocations.values(), Decimal("0"))
        if _decimal_breakpoint_equal(target, previous_total):
            return previous_allocations
        if _decimal_breakpoint_equal(target, point_total):
            return point_allocations
        if _decimal_breakpoint_equal(point_total, previous_total):
            raise TargetBudgetInfeasibleError(target, floor_total, cap_total)
        allocations = _solve_box_interval(
            rows, ordered, weights, target, previous_point, point
        )
        if allocations is not None:
            return allocations

    raise TargetBudgetInfeasibleError(target, floor_total, cap_total)


def _solve_box_allocations(
    rows: list[dict[str, Any]],
    requested_total: Decimal,
) -> dict[int, Decimal]:
    """Solve weighted bounds; zero weights become reserve capacity after positive caps."""
    positive = [index for index, row in enumerate(rows) if row["calculated_weight"] > 0]
    zero = [index for index, row in enumerate(rows) if row["calculated_weight"] == 0]
    if len(positive) + len(zero) != len(rows):
        raise ValueError("Ponderile de alocare nu pot fi negative.")
    if not positive:
        return _solve_positive_box(
            rows,
            zero,
            requested_total,
            {index: Decimal("1") for index in zero},
        )

    positive_cap_total = sum((rows[index]["cap_target"] for index in positive), Decimal("0"))
    zero_floor_total = sum((rows[index]["floor_target"] for index in zero), Decimal("0"))
    weighted_limit = positive_cap_total + zero_floor_total
    if requested_total <= weighted_limit:
        allocations = {index: rows[index]["floor_target"] for index in zero}
        allocations.update(
            _solve_positive_box(
                rows,
                positive,
                requested_total - zero_floor_total,
                {index: rows[index]["calculated_weight"] for index in positive},
            )
        )
        return allocations

    allocations = {index: rows[index]["cap_target"] for index in positive}
    allocations.update(
        _solve_positive_box(
            rows,
            zero,
            requested_total - positive_cap_total,
            {index: Decimal("1") for index in zero},
        )
    )
    return allocations


def _round_bounded_allocations(
    rows: list[dict[str, Any]],
    assigned: dict[int, Decimal],
    requested_total: Decimal,
    floor_total: Decimal,
    cap_total: Decimal,
) -> None:
    """Round down, then distribute residual cents by largest remainder."""
    bases = {
        index: value.quantize(MONEY, rounding=ROUND_FLOOR)
        for index, value in assigned.items()
    }
    rounded_total = sum(bases.values(), Decimal("0"))
    residual = requested_total - rounded_total
    if residual < 0 or residual % MONEY:
        raise TargetBudgetInfeasibleError(requested_total, floor_total, cap_total)
    residual_cents = int(residual / MONEY)
    candidates = sorted(
        (
            (assigned[index] - bases[index], str(rows[index].get("site_code", "")), index)
            for index in bases
            if rows[index]["cap_target"] - bases[index] >= MONEY
        ),
        key=lambda candidate: (-candidate[0], candidate[1], candidate[2]),
    )
    if residual_cents > len(candidates):
        raise TargetBudgetInfeasibleError(requested_total, floor_total, cap_total)
    for _fraction, _site_code, index in candidates[:residual_cents]:
        bases[index] += MONEY
    for index, row in enumerate(rows):
        row["proposed_target"] = bases[index]


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

    for row in rows:
        _reset_bound_state(row)

    assigned = _solve_box_allocations(rows, requested_total)

    _round_bounded_allocations(rows, assigned, requested_total, floor_total, cap_total)
    for row in rows:
        _mark_final_bounds(row)
    final_total = sum((row["proposed_target"] for row in rows), Decimal("0"))
    if final_total != requested_total or any(
        row["proposed_target"] < row["floor_target"] or row["proposed_target"] > row["cap_target"]
        for row in rows
    ):
        raise TargetBudgetInfeasibleError(requested_total, floor_total, cap_total)
    return rows, []
