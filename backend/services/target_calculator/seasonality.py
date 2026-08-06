"""Pure multi-year seasonality rules for Target Calculator."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, TypedDict

from fastapi import HTTPException

from services.target_calculator.calculations import money

DEFAULT_SEASONALITY_YEARS = 3
MAX_SEASONALITY_YEARS = 3
MIN_SEASONALITY_BASE = Decimal("10000")
ROMANIAN_MONTH_NAMES = (
    "", "ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
    "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie",
)


class SeasonalityPair(TypedDict):
    year_offset: int
    base_month: str
    target_month: str


def shift_month(month: str, offset: int) -> str:
    try:
        year, month_number = (int(value) for value in month.split("-"))
        if month_number < 1 or month_number > 12:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Luna trebuie sa fie in format YYYY-MM") from exc
    index = year * 12 + month_number - 1 + offset
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_label_ro(month: str) -> str:
    try:
        month_number = int(month.split("-")[1])
        return ROMANIAN_MONTH_NAMES[month_number]
    except (IndexError, ValueError):
        return month


def seasonality_pair_configuration(target_month: str, years: int) -> list[SeasonalityPair]:
    years = max(1, min(int(years), MAX_SEASONALITY_YEARS))
    return [
        {
            "year_offset": year_offset,
            "base_month": shift_month(target_month, -1 - 12 * year_offset),
            "target_month": shift_month(target_month, -12 * year_offset),
        }
        for year_offset in range(1, years + 1)
    ]


def build_source_month_configuration(
    target_month: str,
    pairs: list[SeasonalityPair],
) -> list[dict[str, str]]:
    source_months: list[dict[str, str]] = []
    for pair in sorted(pairs, key=lambda item: item["base_month"]):
        source_months.extend([
            {
                "month": pair["base_month"],
                "label": f"Baza sezoniera Y-{pair['year_offset']}",
                "role": f"seasonality_base_y{pair['year_offset']}",
            },
            {
                "month": pair["target_month"],
                "label": f"Luna target Y-{pair['year_offset']}",
                "role": f"seasonality_target_y{pair['year_offset']}",
            },
        ])
    source_months.append({
        "month": shift_month(target_month, -1),
        "label": "Forecast luna curenta",
        "role": "floor_reference",
    })
    return source_months


def source_month_configuration(target_month: str) -> list[dict[str, str]]:
    return build_source_month_configuration(
        target_month,
        seasonality_pair_configuration(target_month, DEFAULT_SEASONALITY_YEARS),
    )


def seasonal_year_weights(count: int) -> list[Decimal]:
    if count <= 1:
        return [Decimal("1")]
    if count == 2:
        return [Decimal("0.70"), Decimal("0.30")]
    return [Decimal("0.50"), Decimal("0.30"), Decimal("0.20")]


def weighted_ratio(
    pairs: list[SeasonalityPair],
    value_by_month: dict[str, Decimal],
    *,
    minimum_base: Decimal = Decimal("0"),
) -> tuple[Decimal | None, list[dict[str, Any]]]:
    usable: list[tuple[SeasonalityPair, Decimal]] = []
    details: list[dict[str, Any]] = []
    for pair in pairs:
        base_value = money(value_by_month.get(pair["base_month"], Decimal("0")))
        target_value = money(value_by_month.get(pair["target_month"], Decimal("0")))
        ratio = target_value / base_value if base_value > minimum_base and target_value > 0 else None
        details.append({
            "year_offset": pair["year_offset"],
            "base_month": pair["base_month"],
            "target_month": pair["target_month"],
            "base_value": float(base_value),
            "target_value": float(target_value),
            "ratio": float(ratio.quantize(Decimal("0.0001"))) if ratio is not None else None,
        })
        if ratio is not None:
            usable.append((pair, ratio))
    if not usable:
        return None, details
    weights = seasonal_year_weights(len(usable))
    factor = sum((ratio * weights[index] for index, (_, ratio) in enumerate(usable)), Decimal("0"))
    return factor, details
