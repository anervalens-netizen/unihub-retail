"""Exact money and deterministic allocation primitives for Campaigns."""
from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

_MONEY = Decimal("0.01")


def money(value: Decimal | int | float) -> Decimal:
    """Normalize a monetary value exactly once at the calculation boundary."""
    return Decimal(str(value)).quantize(_MONEY, rounding=ROUND_HALF_UP)


def money_float(value: Decimal | int | float) -> float:
    """Convert only when populating the stable public float response contract."""
    return float(money(value))


def allocate_integer_target(
    quantities: dict[str | None, int],
    target: int,
) -> dict[str | None, int]:
    """Allocate a canonical non-negative store quantity across agent rows."""
    target = max(0, int(target))
    normalized = {
        agent: max(0, int(quantity))
        for agent, quantity in quantities.items()
    }
    current = sum(normalized.values())
    if current == target:
        return normalized
    if current < target:
        normalized[None] = normalized.get(None, 0) + target - current
        return normalized
    if target == 0:
        return {agent: 0 for agent in normalized}

    allocated = {
        agent: quantity * target // current
        for agent, quantity in normalized.items()
    }
    remainder = target - sum(allocated.values())
    ranked = sorted(
        normalized,
        key=lambda agent: (
            -(normalized[agent] * target % current),
            str(agent or "").casefold(),
        ),
    )
    for agent in ranked[:remainder]:
        allocated[agent] += 1
    return allocated


def allocate_currency_targets(
    values: dict[tuple[str, str], Decimal],
    store_targets: dict[str, Decimal],
) -> dict[tuple[str, str], Decimal]:
    """Round agent currency values while preserving each rounded store total."""
    by_store: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key in values:
        by_store[key[0]].append(key)

    allocated: dict[tuple[str, str], Decimal] = {}
    for site_code, keys in by_store.items():
        ordered = sorted(keys, key=lambda key: key[1].casefold())
        raw_cents = {
            key: max(Decimal("0"), values[key]) * Decimal("100")
            for key in ordered
        }
        cents = {key: int(raw_cents[key]) for key in ordered}
        target_cents = int(
            (
                max(Decimal("0"), store_targets.get(site_code, Decimal("0")))
                * 100
            ).to_integral_value()
        )
        remainder = target_cents - sum(cents.values())
        ranked_up = sorted(
            ordered,
            key=lambda key: (-(raw_cents[key] - cents[key]), key[1].casefold()),
        )
        ranked_down = list(reversed(ranked_up))
        while remainder > 0 and ranked_up:
            for key in ranked_up:
                if remainder == 0:
                    break
                cents[key] += 1
                remainder -= 1
        while remainder < 0 and ranked_down:
            progressed = False
            for key in ranked_down:
                if remainder == 0:
                    break
                if cents[key] > 0:
                    cents[key] -= 1
                    remainder += 1
                    progressed = True
            if not progressed:
                break
        for key in ordered:
            allocated[key] = (Decimal(cents[key]) / Decimal("100")).quantize(_MONEY)
    return allocated
