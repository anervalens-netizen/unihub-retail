from __future__ import annotations

from decimal import Decimal
from typing import Any

from services.target_calculator.serialization import regional_summary


def test_regional_summary_modern_rows_accumulate_and_sort_exactly() -> None:
    rows = [
        {
            "regional": "Regional B",
            "floor_target": Decimal("10.10"),
            "proposed_target": Decimal("50"),
            "final_target": None,
            "calculation_details": {
                "current_month": "2026-08",
                "current_forecast": Decimal("0"),
                "seasonality": {
                    "store_years": [
                        {
                            "year_offset": 1,
                            "base_month": "2025-08",
                            "target_month": "2025-09",
                            "base_value": Decimal("0"),
                            "target_value": Decimal("50"),
                        }
                    ]
                },
            },
            "history": [],
        },
        {
            "regional": "Regional A",
            "floor_target": Decimal("30"),
            "proposed_target": Decimal("120"),
            "final_target": Decimal("110"),
            "calculation_details": {
                "current_month": "2026-08",
                "current_forecast": Decimal("100"),
                "seasonality": {
                    "store_years": [
                        {
                            "year_offset": 1,
                            "base_month": "2025-08",
                            "target_month": "2025-09",
                            "base_value": Decimal("80"),
                            "target_value": Decimal("100"),
                        }
                    ]
                },
            },
            "history": [],
        },
        {
            "regional": "Regional A",
            "floor_target": 40,
            "proposed_target": 240,
            "final_target": Decimal("190"),
            "calculation_details": {
                "current_month": "2026-08",
                "current_forecast": 200,
                "seasonality": {
                    "store_years": [
                        {
                            "year_offset": 2,
                            "base_month": "2024-08",
                            "target_month": "2024-09",
                            "base_value": 999,
                            "target_value": 999,
                        },
                        {
                            "year_offset": 1,
                            "base_month": "2025-08",
                            "target_month": "2025-09",
                            "base_value": 160,
                            "target_value": 200,
                        },
                    ]
                },
            },
            "history": [],
        },
    ]

    assert regional_summary(rows) == [
        {
            "regional": "Regional A",
            "store_count": 2,
            "floor_total": 70.0,
            "proposed_total": 360.0,
            "final_total": 300.0,
            "current_month": "2026-08",
            "current_forecast_total": 300.0,
            "last_year_base_month": "2025-08",
            "last_year_target_month": "2025-09",
            "last_year_base_total": 240.0,
            "last_year_target_total": 300.0,
            "proposed_growth_vs_current_pct": 20.0,
            "final_growth_vs_current_pct": 0.0,
            "last_year_growth_pct": 25.0,
        },
        {
            "regional": "Regional B",
            "store_count": 1,
            "floor_total": 10.1,
            "proposed_total": 50.0,
            "final_total": 0.0,
            "current_month": "2026-08",
            "current_forecast_total": 0.0,
            "last_year_base_month": "2025-08",
            "last_year_target_month": "2025-09",
            "last_year_base_total": 0.0,
            "last_year_target_total": 50.0,
            "proposed_growth_vs_current_pct": None,
            "final_growth_vs_current_pct": None,
            "last_year_growth_pct": None,
        },
    ]


def test_regional_summary_parses_json_details_and_uses_year_one_entry() -> None:
    rows = [
        {
            "regional": "Regional JSON",
            "floor_target": "25.50",
            "proposed_target": "125",
            "final_target": "100",
            "calculation_details": (
                '{"current_month":"2026-08","current_forecast":100,'
                '"seasonality":{"store_years":['
                '{"year_offset":2,"base_month":"2024-08","target_month":"2024-09",'
                '"base_value":500,"target_value":700},'
                '{"year_offset":1,"base_month":"2025-08","target_month":"2025-09",'
                '"base_value":80,"target_value":120}]}}'
            ),
            "history": (
                '[{"month":"2026-07","role":"floor_reference","realized":999},'
                '{"month":"2025-07","role":"seasonality_base_y1","realized":999},'
                '{"month":"2025-08","role":"seasonality_target_y1","realized":999}]'
            ),
        }
    ]

    assert regional_summary(rows) == [
        {
            "regional": "Regional JSON",
            "store_count": 1,
            "floor_total": 25.5,
            "proposed_total": 125.0,
            "final_total": 100.0,
            "current_month": "2026-08",
            "current_forecast_total": 100.0,
            "last_year_base_month": "2025-08",
            "last_year_target_month": "2025-09",
            "last_year_base_total": 80.0,
            "last_year_target_total": 120.0,
            "proposed_growth_vs_current_pct": 25.0,
            "final_growth_vs_current_pct": 0.0,
            "last_year_growth_pct": 50.0,
        }
    ]


def test_regional_summary_falls_back_to_history_exactly() -> None:
    rows = [
        {
            "regional": "Regional Legacy",
            "floor_target": 10000.0,
            "proposed_target": 50000.0,
            "final_target": None,
            "calculation_details": "{}",
            "history": (
                '[{"month":"2025-06","role":"seasonality_base_y1","realized":40000.0},'
                '{"month":"2025-07","role":"seasonality_target_y1","realized":60000.0},'
                '{"month":"2026-06","role":"floor_reference","realized":45000.0}]'
            ),
        }
    ]

    assert regional_summary(rows) == [
        {
            "regional": "Regional Legacy",
            "store_count": 1,
            "floor_total": 10000.0,
            "proposed_total": 50000.0,
            "final_total": 0.0,
            "current_month": "2026-06",
            "current_forecast_total": 45000.0,
            "last_year_base_month": "2025-06",
            "last_year_target_month": "2025-07",
            "last_year_base_total": 40000.0,
            "last_year_target_total": 60000.0,
            "proposed_growth_vs_current_pct": 11.11,
            "final_growth_vs_current_pct": -100.0,
            "last_year_growth_pct": 50.0,
        }
    ]


def test_regional_summary_empty_inputs_and_last_truthy_month_semantics() -> None:
    assert regional_summary([]) == []

    rows: list[dict[str, Any]] = [
        {
            "regional": "Regional A",
            "floor_target": None,
            "proposed_target": None,
            "final_target": None,
            "calculation_details": None,
            "history": None,
        },
        {
            "regional": "Regional A",
            "floor_target": 1,
            "proposed_target": 2,
            "final_target": 3,
            "calculation_details": {
                "current_month": "2026-07",
                "current_forecast": -10,
                "seasonality": {
                    "store_years": [
                        {
                            "year_offset": 1,
                            "base_month": "2025-07",
                            "target_month": "2025-08",
                            "base_value": -5,
                            "target_value": 10,
                        }
                    ]
                },
            },
            "history": [],
        },
        {
            "regional": "Regional A",
            "floor_target": 4,
            "proposed_target": 5,
            "final_target": 6,
            "calculation_details": {
                "current_month": "2026-08",
                "current_forecast": None,
                "seasonality": {"store_years": []},
            },
            "history": [
                {"month": None, "role": "floor_reference", "realized": None},
                {"month": None, "role": "seasonality_base_y1", "realized": None},
                {"month": None, "role": "seasonality_target_y1", "realized": None},
            ],
        },
    ]

    assert regional_summary(rows) == [
        {
            "regional": "Regional A",
            "store_count": 3,
            "floor_total": 5.0,
            "proposed_total": 7.0,
            "final_total": 9.0,
            "current_month": "2026-08",
            "current_forecast_total": -10.0,
            "last_year_base_month": "2025-07",
            "last_year_target_month": "2025-08",
            "last_year_base_total": -5.0,
            "last_year_target_total": 10.0,
            "proposed_growth_vs_current_pct": None,
            "final_growth_vs_current_pct": None,
            "last_year_growth_pct": None,
        }
    ]
