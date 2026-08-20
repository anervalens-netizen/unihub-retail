"""Pure manager-level target allocation analysis."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from services.target_calculator.rules import percent_change
from services.target_calculator.seasonality import shift_month


def _money(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _manager_period_value(row: dict[str, Any], month: str) -> Decimal:
    period = next(
        (item for item in row["history"] if item["month"] == month), None
    )
    return _money((period or {}).get("realized"))


def _manager_signal(
    target_vs_forecast_pct: float | None,
    target_vs_seasonal_pct: float | None,
) -> str:
    if target_vs_forecast_pct is not None and target_vs_forecast_pct >= 5:
        return "Peste AI"
    if target_vs_seasonal_pct is not None and round(target_vs_seasonal_pct, 1) >= 3:
        return "Peste sezonier"
    return "Echilibrat"


def _manager_allocation_row(
    manager: str,
    rows: list[dict[str, Any]],
    *,
    previous_month: str,
    previous_year_base_month: str,
    previous_year_target_month: str,
) -> dict[str, Any]:
    target = sum((_money(row["proposed_target"]) for row in rows), Decimal("0"))
    previous = sum(
        (_manager_period_value(row, previous_month) for row in rows), Decimal("0")
    )
    previous_year_base = sum(
        (
            _manager_period_value(row, previous_year_base_month)
            for row in rows
        ),
        Decimal("0"),
    )
    previous_year_target = sum(
        (
            _manager_period_value(row, previous_year_target_month)
            for row in rows
        ),
        Decimal("0"),
    )
    forecast_values = [
        (row.get("profitability") or {}).get("forecast_sales") for row in rows
    ]
    forecast = (
        sum(
            (_money(value) for value in forecast_values if value is not None),
            Decimal("0"),
        )
        if all(value is not None for value in forecast_values)
        else None
    )
    seasonality_pct = percent_change(
        float(previous_year_target), float(previous_year_base)
    )
    seasonal_target = (
        previous
        * (Decimal("1") + Decimal(str(seasonality_pct)) / Decimal("100"))
        if seasonality_pct is not None
        else None
    )
    target_vs_previous_pct = percent_change(float(target), float(previous))
    target_vs_seasonal_pct = (
        percent_change(float(target), float(seasonal_target))
        if seasonal_target is not None
        else None
    )
    target_vs_forecast_pct = (
        percent_change(float(target), float(forecast))
        if forecast is not None
        else None
    )
    return {
        "manager": manager,
        "store_count": len(rows),
        "target": float(target),
        "previous": float(previous),
        "previous_year_base": float(previous_year_base),
        "previous_year_target": float(previous_year_target),
        "forecast": float(forecast) if forecast is not None else None,
        "target_vs_previous_pct": target_vs_previous_pct,
        "seasonality_pct": seasonality_pct,
        "seasonality_deviation_pp": (
            target_vs_previous_pct - seasonality_pct
            if target_vs_previous_pct is not None and seasonality_pct is not None
            else None
        ),
        "seasonal_target": (
            float(seasonal_target) if seasonal_target is not None else None
        ),
        "target_vs_seasonal_pct": target_vs_seasonal_pct,
        "target_vs_previous_year_pct": percent_change(
            float(target), float(previous_year_target)
        ),
        "target_vs_forecast_pct": target_vs_forecast_pct,
        "signal": _manager_signal(
            target_vs_forecast_pct,
            target_vs_seasonal_pct,
        ),
    }


def manager_allocation_analysis(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    target_month = scenario["target_month"]
    previous_year_base_month = shift_month(target_month, -13)
    previous_year_target_month = shift_month(target_month, -12)
    previous_month = shift_month(target_month, -1)
    rows_by_manager: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scenario["rows"]:
        rows_by_manager[row["regional"]].append(row)

    managers = [
        _manager_allocation_row(
            manager,
            manager_rows,
            previous_month=previous_month,
            previous_year_base_month=previous_year_base_month,
            previous_year_target_month=previous_year_target_month,
        )
        for manager, manager_rows in rows_by_manager.items()
    ]
    managers.sort(key=lambda item: (-item["target"], item["manager"]))
    network = _manager_allocation_row(
        "TOTAL REȚEA",
        list(scenario["rows"]),
        previous_month=previous_month,
        previous_year_base_month=previous_year_base_month,
        previous_year_target_month=previous_year_target_month,
    )
    network["signal"] = "Rețea"
    for item in [*managers, network]:
        item["target_share"] = (
            item["target"] / network["target"] if network["target"] > 0 else 0
        )
        item["previous_share"] = (
            item["previous"] / network["previous"] if network["previous"] > 0 else 0
        )
        item["previous_year_share"] = (
            item["previous_year_target"] / network["previous_year_target"]
            if network["previous_year_target"] > 0
            else 0
        )
        item["forecast_share"] = (
            item["forecast"] / network["forecast"]
            if item["forecast"] is not None and network["forecast"]
            else None
        )
        item["target_vs_previous_share_pp"] = (
            item["target_share"] - item["previous_share"]
        ) * 100
        item["target_vs_previous_year_share_pp"] = (
            item["target_share"] - item["previous_year_share"]
        ) * 100
        item["target_vs_forecast_share_pp"] = (
            (item["target_share"] - item["forecast_share"]) * 100
            if item["forecast_share"] is not None
            else None
        )
    return [*managers, network]
