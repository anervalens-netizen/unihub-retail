"""Pure aggregation helpers shared by campaign evaluators and responses."""

from __future__ import annotations


def merge_excluded_units(
    target: dict[tuple[str, str, str], int],
    source: dict[tuple[str, str, str], int],
) -> None:
    for key, units in source.items():
        target[key] = target.get(key, 0) + units


def excluded_by_site_item(
    excluded_units: dict[tuple[str, str, str], int],
) -> dict[tuple[str, str], int]:
    result: dict[tuple[str, str], int] = {}
    for (site_code, _agent, item_code), units in excluded_units.items():
        result[(site_code, item_code)] = result.get((site_code, item_code), 0) + units
    return result
