from __future__ import annotations

from typing import Any

import pytest

from services.target_calculator.export import manager_allocation_analysis


def _row(
    *,
    regional: str,
    proposed_target: float,
    previous: float,
    previous_year_base: float,
    previous_year_target: float,
    forecast: float | None,
) -> dict[str, Any]:
    return {
        "regional": regional,
        "proposed_target": proposed_target,
        "history": [
            {"month": "2025-05", "realized": previous_year_base},
            {"month": "2025-06", "realized": previous_year_target},
            {"month": "2026-05", "realized": previous},
        ],
        "profitability": {"forecast_sales": forecast},
    }


def test_manager_allocation_analysis_preserves_signals_sorting_and_missing_forecast() -> None:
    scenario = {
        "target_month": "2026-06",
        "rows": [
            _row(
                regional="Regional A",
                proposed_target=120,
                previous=100,
                previous_year_base=80,
                previous_year_target=88,
                forecast=100,
            ),
            _row(
                regional="Regional B",
                proposed_target=103,
                previous=100,
                previous_year_base=100,
                previous_year_target=100,
                forecast=None,
            ),
        ],
    }

    result = manager_allocation_analysis(scenario)

    assert [item["manager"] for item in result] == [
        "Regional A",
        "Regional B",
        "TOTAL REȚEA",
    ]

    regional_a, regional_b, network = result
    assert regional_a["signal"] == "Peste AI"
    assert regional_a["target"] == 120.0
    assert regional_a["forecast"] == 100.0
    assert regional_a["target_vs_forecast_pct"] == 20.0

    assert regional_b["signal"] == "Peste sezonier"
    assert regional_b["target_vs_seasonal_pct"] == 3.0
    assert regional_b["forecast"] is None

    assert network["signal"] == "Rețea"
    assert network["target"] == 223.0
    assert network["forecast"] is None

    assert regional_a["target_share"] == pytest.approx(120 / 223)
    assert regional_b["target_share"] == pytest.approx(103 / 223)
    assert network["target_share"] == 1.0
    assert all(item["forecast_share"] is None for item in result)
    assert all(item["target_vs_forecast_share_pp"] is None for item in result)
