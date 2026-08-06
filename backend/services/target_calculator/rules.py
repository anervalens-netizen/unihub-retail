"""Pure Target Calculator rules that do not require a repository."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from services.target_calculator.calculations import money


def percent_change(new_value: float, base_value: float) -> float | None:
    if base_value <= 0:
        return None
    return round((new_value - base_value) * 100 / base_value, 2)


def realized_for_calculation(actual_realized: Decimal, forecast_factor: Decimal) -> Decimal:
    return money(actual_realized * forecast_factor)


def unique_months(months: list[str]) -> list[str]:
    return list(dict.fromkeys(months))


def clamp_decimal(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    return min(max(value, minimum), maximum)


def weighted_available(components: dict[str, tuple[Decimal | None, Decimal]]) -> Decimal | None:
    total_weight = sum(
        weight for value, weight in components.values() if value is not None and weight > 0
    )
    if total_weight <= 0:
        return None
    return sum(
        (
            value * weight / total_weight
            for value, weight in components.values()
            if value is not None and weight > 0
        ),
        Decimal("0"),
    )


def canonical_input_hash(payload: Any) -> str:
    import hashlib
    import json

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
