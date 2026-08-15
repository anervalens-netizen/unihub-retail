"""Deterministic 100k-profile Target allocator oracle contract."""
from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
import random
from typing import Any

from services.target_calculator.calculations import (
    TargetBudgetInfeasibleError,
    allocate_with_bounds,
)


SEED = 20260812
PROFILE_COUNT = 100_000
CENT = Decimal("0.01")


def _fraction_clip(value: Fraction, floor: int, cap: int) -> Fraction:
    return max(Fraction(floor), min(Fraction(cap), value))


def _continuous_box(
    rows: list[dict[str, Any]],
    sites: list[str],
    target: int,
    weights: dict[str, int],
) -> dict[str, Fraction]:
    """Exhaust every rational breakpoint; intentionally unlike production."""
    breakpoints = sorted(
        {
            Fraction(bound, weights[site])
            for site in sites
            for bound in (rows_by_site(rows)[site]["floor_cents"], rows_by_site(rows)[site]["cap_cents"])
        }
    )
    row_map = rows_by_site(rows)
    target_fraction = Fraction(target)
    previous: Fraction | None = None
    for point in breakpoints:
        allocations = {
            site: _fraction_clip(
                point * weights[site],
                row_map[site]["floor_cents"],
                row_map[site]["cap_cents"],
            )
            for site in sites
        }
        total = sum(allocations.values(), Fraction())
        if total == target_fraction:
            return allocations
        if total > target_fraction:
            assert previous is not None
            midpoint = (previous + point) / 2
            active = [
                site
                for site in sites
                if row_map[site]["floor_cents"]
                < midpoint * weights[site]
                < row_map[site]["cap_cents"]
            ]
            assert active
            fixed_total = sum(
                (
                    row_map[site]["floor_cents"]
                    if midpoint * weights[site] <= row_map[site]["floor_cents"]
                    else row_map[site]["cap_cents"]
                )
                for site in sites
                if site not in active
            )
            multiplier = Fraction(
                target - fixed_total,
                sum(weights[site] for site in active),
            )
            result = {
                site: _fraction_clip(
                    multiplier * weights[site],
                    row_map[site]["floor_cents"],
                    row_map[site]["cap_cents"],
                )
                for site in sites
            }
            assert sum(result.values(), Fraction()) == target_fraction
            return result
        previous = point
    raise AssertionError("feasible rational target had no breakpoint interval")


def rows_by_site(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["site_code"]): row for row in rows}


def _continuous_reference(
    rows: list[dict[str, Any]], target: int
) -> dict[str, Fraction]:
    positive = [str(row["site_code"]) for row in rows if row["weight"] > 0]
    zero = [str(row["site_code"]) for row in rows if row["weight"] == 0]
    row_map = rows_by_site(rows)
    if not positive:
        return _continuous_box(
            rows,
            zero,
            target,
            {site: 1 for site in zero},
        )

    positive_cap = sum(row_map[site]["cap_cents"] for site in positive)
    zero_floor = sum(row_map[site]["floor_cents"] for site in zero)
    if target <= positive_cap + zero_floor:
        result = {
            site: Fraction(row_map[site]["floor_cents"])
            for site in zero
        }
        result.update(
            _continuous_box(
                rows,
                positive,
                target - zero_floor,
                {site: row_map[site]["weight"] for site in positive},
            )
        )
        return result

    result = {
        site: Fraction(row_map[site]["cap_cents"])
        for site in positive
    }
    result.update(
        _continuous_box(
            rows,
            zero,
            target - positive_cap,
            {site: 1 for site in zero},
        )
    )
    return result


def _reference(
    rows: list[dict[str, Any]], target: int
) -> dict[str, tuple[Decimal, tuple[str, ...], str]]:
    row_map = rows_by_site(rows)
    continuous = _continuous_reference(rows, target)
    base = {
        site: value.numerator // value.denominator
        for site, value in continuous.items()
    }
    residual = target - sum(base.values())
    candidates = sorted(
        (
            continuous[site] - base[site],
            site,
        )
        for site in base
        if row_map[site]["cap_cents"] - base[site] >= 1
    )
    candidates.sort(key=lambda item: (-item[0], item[1]))
    assert 0 <= residual <= len(candidates)
    for _fraction, site in candidates[:residual]:
        base[site] += 1

    expected: dict[str, tuple[Decimal, tuple[str, ...], str]] = {}
    for site, cents in base.items():
        at_floor = cents == row_map[site]["floor_cents"]
        at_cap = cents == row_map[site]["cap_cents"]
        flags = (
            (("FLOOR_APPLIED",) if at_floor else ())
            + (("CAP_APPLIED",) if at_cap else ())
        )
        reason = "floor_cap" if at_floor and at_cap else "floor" if at_floor else "cap" if at_cap else "proportional"
        expected[site] = (Decimal(cents) * CENT, flags, reason)
    assert sum(value[0] for value in expected.values()) == Decimal(target) * CENT
    return expected


def _half_up_fraction(value: Fraction) -> int:
    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + int(remainder * 2 >= value.denominator)


def _positive_breakpoints(
    row_map: dict[str, dict[str, Any]],
    positive: list[str],
) -> set[Fraction]:
    return {
        Fraction(bound, row_map[site]["weight"])
        for site in positive
        for bound in (row_map[site]["floor_cents"], row_map[site]["cap_cents"])
    }


def _zero_breakpoints(
    row_map: dict[str, dict[str, Any]],
    zero: list[str],
) -> set[Fraction]:
    return {
        Fraction(bound)
        for site in zero
        for bound in (row_map[site]["floor_cents"], row_map[site]["cap_cents"])
    }


def _zero_only_breakpoints(rows: list[dict[str, Any]]) -> set[Fraction]:
    return {
        Fraction(bound)
        for row in rows
        for bound in (row["floor_cents"], row["cap_cents"])
    }


def _add_positive_branch_totals(
    row_map: dict[str, dict[str, Any]],
    positive: list[str],
    zero: list[str],
    exact_totals: set[Fraction],
) -> None:
    zero_floor = sum(row_map[site]["floor_cents"] for site in zero)
    for point in _positive_breakpoints(row_map, positive):
        exact_totals.add(
            Fraction(zero_floor)
            + sum(
                _fraction_clip(
                    point * row_map[site]["weight"],
                    row_map[site]["floor_cents"],
                    row_map[site]["cap_cents"],
                )
                for site in positive
            )
        )
    if zero:
        positive_cap = sum(row_map[site]["cap_cents"] for site in positive)
        for point in _zero_breakpoints(row_map, zero):
            exact_totals.add(
                Fraction(positive_cap)
                + sum(
                    _fraction_clip(
                        point,
                        row_map[site]["floor_cents"],
                        row_map[site]["cap_cents"],
                    )
                    for site in zero
                )
            )


def _add_zero_only_branch_totals(
    rows: list[dict[str, Any]],
    exact_totals: set[Fraction],
) -> None:
    for point in _zero_only_breakpoints(rows):
        exact_totals.add(
            sum(
                (
                    _fraction_clip(
                        point, row["floor_cents"], row["cap_cents"]
                    )
                    for row in rows
                ),
                Fraction(0),
            )
        )


def _extend_budgets_around(
    exact_total: Fraction,
    floor_total: int,
    cap_total: int,
    budgets: set[int],
) -> None:
    rounded = _half_up_fraction(exact_total)
    budgets.update(
        candidate
        for candidate in (rounded - 1, rounded, rounded + 1)
        if floor_total <= candidate <= cap_total
    )


def _budget_candidates(rows: list[dict[str, Any]]) -> list[int]:
    row_map = rows_by_site(rows)
    positive = [str(row["site_code"]) for row in rows if row["weight"] > 0]
    zero = [str(row["site_code"]) for row in rows if row["weight"] == 0]
    floor_total = sum(row["floor_cents"] for row in rows)
    cap_total = sum(row["cap_cents"] for row in rows)
    exact_totals: set[Fraction] = {Fraction(floor_total), Fraction(cap_total)}

    if positive:
        _add_positive_branch_totals(row_map, positive, zero, exact_totals)
    else:
        _add_zero_only_branch_totals(rows, exact_totals)

    budgets = {floor_total, cap_total}
    for exact_total in exact_totals:
        _extend_budgets_around(exact_total, floor_total, cap_total, budgets)
    return sorted(budgets)

def _production_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "site_code": row["site_code"],
        "calculated_weight": Decimal(row["weight"]),
        "floor_target": Decimal(row["floor_cents"]) * CENT,
        "cap_target": Decimal(row["cap_cents"]) * CENT,
        "flags": [],
    }


def _actual(
    rows: list[dict[str, Any]], target: int
) -> dict[str, tuple[Decimal, tuple[str, ...], str]]:
    try:
        allocated, warnings = allocate_with_bounds(
            [_production_row(row) for row in rows],
            Decimal(target) * CENT,
        )
    except TargetBudgetInfeasibleError as exc:
        raise AssertionError("integer-cent feasibility oracle said feasible") from exc
    assert warnings == []
    return {
        str(row["site_code"]): (
            row["proposed_target"],
            tuple(row["flags"]),
            str(row["allocation_reason"]),
        )
        for row in allocated
    }


def test_100000_feasible_profiles_match_fraction_oracle_and_all_permutations() -> None:
    rng = random.Random(SEED)
    for profile_index in range(PROFILE_COUNT):
        row_count = rng.randint(1, 25)
        site_codes = [f"P{profile_index:06d}S{index:02d}" for index in range(row_count)]
        rng.shuffle(site_codes)
        rows: list[dict[str, Any]] = []
        for site_code in site_codes:
            floor_cents = rng.randint(0, 5_000_000)
            rows.append(
                {
                    "site_code": site_code,
                    "weight": rng.randint(0, 100_000),
                    "floor_cents": floor_cents,
                    "cap_cents": floor_cents + rng.randint(0, 5_000_000),
                }
            )
        target = rng.choice(_budget_candidates(rows))
        expected = _reference(rows, target)
        shuffled = list(rows)
        rng.shuffle(shuffled)
        orders = (
            rows,
            list(reversed(rows)),
            sorted(rows, key=lambda row: str(row["site_code"])),
            shuffled,
        )
        for order_name, order in zip(
            ("original", "reverse", "site", "fisher_yates"),
            orders,
            strict=True,
        ):
            actual = _actual(order, target)
            assert actual == expected, (
                f"profile={profile_index} order={order_name} target_cents={target} "
                f"rows={rows!r} expected={expected!r} actual={actual!r}"
            )
