from __future__ import annotations

from decimal import Decimal

import pytest

from scripts.run_ai_forecast_backtest import (
    aggregate_rows,
    build_baseline_rows,
    make_result_row,
    parse_forecast_response,
    parse_models,
)
from scripts.run_ai_forecast_xreg import StoreInfo


def store(site_code: str, locatie: str = "Store") -> StoreInfo:
    return StoreInfo(
        site_code=site_code,
        locatie=locatie,
        firma="Mobiup",
        regional="RM 1",
        asm="ASM 1",
    )


def test_baseline_rows_compare_same_month_and_seasonal_average() -> None:
    stores = [store("S001"), store("S002")]
    sales = {
        ("S001", "2022-07"): Decimal("60"),
        ("S001", "2023-07"): Decimal("70"),
        ("S001", "2024-07"): Decimal("80"),
        ("S001", "2025-07"): Decimal("100"),
        ("S002", "2025-07"): Decimal("50"),
    }

    naive_rows = build_baseline_rows(
        model="seasonal_naive",
        target_month="2025-07",
        stores=stores,
        sales=sales,
        metric="sales_value",
        history_start_month="2022-01",
        seasonal_years=3,
    )
    assert naive_rows[0]["forecast_sales"] == Decimal("80.00")
    assert naive_rows[0]["error_sales"] == Decimal("-20.00")
    assert naive_rows[1]["forecast_sales"] == Decimal("0.00")
    assert naive_rows[1]["method"] == "seasonal_naive_zero"

    average_rows = build_baseline_rows(
        model="seasonal_moving_average",
        target_month="2025-07",
        stores=stores,
        sales=sales,
        metric="sales_value",
        history_start_month="2022-01",
        seasonal_years=3,
    )
    assert average_rows[0]["forecast_sales"] == Decimal("70.00")
    assert average_rows[0]["method"] == "seasonal_moving_average_3y"
    assert average_rows[1]["method"] == "seasonal_moving_average_zero"


def test_forecast_response_parses_quantiles_and_coverage_metrics() -> None:
    parsed = parse_forecast_response(
        {
            "series": [
                {
                    "series_id": "S001",
                    "point_forecast": [100],
                    "quantile_forecast": [[101, 80, 85, 90, 95, 100, 105, 110, 115, 120]],
                }
            ]
        },
        metric="sales_value",
    )

    row = make_result_row(
        model="xreg_timesfm",
        method="model_xreg_timesfm",
        meta={
            "site_code": "S001",
            "locatie": "Store",
            "firma": "Mobiup",
            "regional": "RM 1",
            "asm": "ASM 1",
            "first_input_month": "2020-01",
            "source_month": "2025-06",
            "context_months": 66,
        },
        target_month="2025-07",
        actual=Decimal("110.00"),
        forecast=parsed["S001"][0]["point"] or Decimal("0"),
        metric="sales_value",
        quantiles=parsed["S001"][0],
    )

    assert parsed["S001"][0]["q10"] == Decimal("80.00")
    assert parsed["S001"][0]["q90"] == Decimal("120.00")
    assert row["coverage_p10_p90"] == 1
    assert row["coverage_p20_p80"] == 1
    assert row["pinball_p10"] == Decimal("3.00")
    assert row["pinball_p90"] == Decimal("1.00")


def test_aggregate_rows_computes_network_metrics() -> None:
    rows = [
        make_result_row(
            model="seasonal_naive",
            method="seasonal_naive",
            meta={
                "site_code": "S001",
                "locatie": "Store 1",
                "firma": "Mobiup",
                "regional": "RM 1",
                "asm": "ASM 1",
                "first_input_month": "2024-01",
                "source_month": "2025-06",
                "context_months": 18,
            },
            target_month="2025-07",
            actual=Decimal("100.00"),
            forecast=Decimal("90.00"),
            metric="sales_value",
        ),
        make_result_row(
            model="seasonal_naive",
            method="seasonal_naive",
            meta={
                "site_code": "S002",
                "locatie": "Store 2",
                "firma": "Mobiup",
                "regional": "RM 1",
                "asm": "ASM 1",
                "first_input_month": "2024-01",
                "source_month": "2025-06",
                "context_months": 18,
            },
            target_month="2025-07",
            actual=Decimal("100.00"),
            forecast=Decimal("110.00"),
            metric="sales_value",
        ),
    ]

    summary = aggregate_rows(
        rows=rows,
        model="seasonal_naive",
        metric="sales_value",
        group_level="network",
        group_key="ALL",
        group_label="Retea",
        target_month="2025-07",
    )

    assert summary["actual_sales"] == Decimal("200.00")
    assert summary["forecast_sales"] == Decimal("200.00")
    assert summary["bias_pct"] == Decimal("0.00")
    assert summary["wape_pct"] == Decimal("10.00")
    assert summary["mae"] == Decimal("10.00")
    assert summary["mape_pct"] == Decimal("10.00")


def test_parse_models_validates_names() -> None:
    assert parse_models("seasonal_naive,xreg_timesfm") == ["seasonal_naive", "xreg_timesfm"]
    with pytest.raises(ValueError, match="Modele necunoscute"):
        parse_models("seasonal_naive,bad_model")
