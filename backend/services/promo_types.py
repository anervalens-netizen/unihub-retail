"""Shared promotion result types and exact aggregation primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


class PromoActualsError(RuntimeError):
    """Raised when a configured POS actuals report exists but cannot be used."""


@dataclass
class PromoCoPurchaseResult:
    """Aggregated promotion result for one period and scope."""

    qualifying_bons: int = 0
    discounted_units: int = 0
    active_stores: int = 0
    active_agents: int = 0
    excluded_units: dict[tuple[str, str, str], int] = field(default_factory=dict)
    excluded_discount_values: dict[tuple[str, str, str], Decimal] = field(
        default_factory=dict
    )

    def excluded_by_site_item(self) -> dict[tuple[str, str], int]:
        output: dict[tuple[str, str], int] = {}
        for (site_code, _agent, item_code), units in self.excluded_units.items():
            key = (site_code, item_code)
            output[key] = output.get(key, 0) + units
        return output

    @property
    def discount_value(self) -> Decimal:
        return sum(self.excluded_discount_values.values(), Decimal("0"))


def result_from_metrics(
    excluded_units: dict[tuple[str, str, str], int],
    excluded_discount_values: dict[tuple[str, str, str], Decimal],
) -> PromoCoPurchaseResult:
    stores = {site for site, _agent, _item in excluded_units}
    agents = {
        agent
        for _site, agent, _item in excluded_units
        if agent and agent != "-"
    }
    total = sum(excluded_units.values())
    return PromoCoPurchaseResult(
        qualifying_bons=total,
        discounted_units=total,
        active_stores=len(stores),
        active_agents=len(agents),
        excluded_units=excluded_units,
        excluded_discount_values=excluded_discount_values,
    )


def merge_promo_results(
    *results: PromoCoPurchaseResult | None,
) -> PromoCoPurchaseResult:
    excluded_units: dict[tuple[str, str, str], int] = {}
    excluded_values: dict[tuple[str, str, str], Decimal] = {}
    for result in results:
        if result is None:
            continue
        for key, units in result.excluded_units.items():
            excluded_units[key] = excluded_units.get(key, 0) + units
        for key, value in result.excluded_discount_values.items():
            excluded_values[key] = excluded_values.get(key, Decimal("0")) + value
    return result_from_metrics(excluded_units, excluded_values)
