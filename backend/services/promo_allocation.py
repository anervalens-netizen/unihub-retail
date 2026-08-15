"""Exact allocation of store-level POS promotion actuals to agents."""

from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any


def allocate_units_to_agents(
    promo_units: int,
    candidates: list[tuple[str, int]],
) -> list[tuple[str, int]]:
    """Allocate units by positive sales share, retaining impossible remainder."""
    promo_units = max(0, int(promo_units))
    if promo_units <= 0:
        return []
    normalized = [
        (agent, max(0, int(quantity)))
        for agent, quantity in candidates
        if agent and agent != "-" and int(quantity) > 0
    ]
    total_positive = sum(quantity for _agent, quantity in normalized)
    if total_positive <= 0:
        return [("-", promo_units)]
    distributable = min(promo_units, total_positive)
    allocations: list[dict[str, Any]] = []
    base_total = 0
    for agent, quantity in normalized:
        numerator = distributable * quantity
        base_units = min(quantity, numerator // total_positive)
        allocations.append(
            {
                "agent": agent,
                "positive_qty": quantity,
                "units": base_units,
                "remainder": numerator % total_positive,
            }
        )
        base_total += base_units
    remaining = distributable - base_total
    order = sorted(
        allocations,
        key=lambda item: (
            -int(item["remainder"]),
            -int(item["positive_qty"]),
            str(item["agent"]),
        ),
    )
    for allocation in order:
        if remaining <= 0:
            break
        if int(allocation["units"]) >= int(allocation["positive_qty"]):
            continue
        allocation["units"] = int(allocation["units"]) + 1
        remaining -= 1
    rows = [
        (str(item["agent"]), int(item["units"]))
        for item in allocations
        if int(item["units"]) > 0
    ]
    if promo_units > total_positive:
        rows.append(("-", promo_units - total_positive))
    return rows


def allocate_value_to_agents(
    total_value: Decimal,
    allocations: list[tuple[str, int]],
) -> dict[str, Decimal]:
    """Allocate an exact POS value using the already-determined unit split."""
    total_units = sum(units for _agent, units in allocations)
    if total_units <= 0:
        return {}
    total_cents = int(
        (total_value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    parts: list[dict[str, Any]] = []
    assigned_cents = 0
    for agent_name, units in allocations:
        exact = Decimal(total_cents * units) / Decimal(total_units)
        cents = int(exact.to_integral_value(rounding=ROUND_FLOOR))
        parts.append(
            {"agent": agent_name, "cents": cents, "remainder": exact - cents}
        )
        assigned_cents += cents
    for part in sorted(
        parts,
        key=lambda item: (-item["remainder"], str(item["agent"])),
    ):
        if assigned_cents >= total_cents:
            break
        part["cents"] += 1
        assigned_cents += 1
    return {
        str(part["agent"]): Decimal(int(part["cents"])) / Decimal(100)
        for part in parts
    }
