from __future__ import annotations

from decimal import Decimal
from typing import Literal

import pytest

from services.agent_evaluation import (
    build_agent_evaluation_v2_row,
    score_band,
    score_rating,
)


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "month": "2026-06",
        "firma": "Firma",
        "site_code": "S1",
        "locatie": "Magazin",
        "regional": "Regional",
        "asm": "Manager",
        "agent": "Agent",
        "total_sales": Decimal("10000"),
        "forecast_sales": Decimal("12000"),
        "total_quantity": 100,
        "working_days": 12,
        "receipt_count": 40,
        "target_value": Decimal("10000"),
        "target_source": "allocated_store_target",
        "target_pct": Decimal("100"),
        "target_forecast_pct": Decimal("120"),
        "target_score_ratio": Decimal("1"),
        "is_partial": False,
        "period_month_count": 1,
        "partial_month_count": 0,
        "final_month_count": 1,
        "partial_min_working_days": 0,
        "available_days": 30,
        "forecast_factor": Decimal("1"),
        "daily_average": Decimal("100"),
        "daily_reference": Decimal("100"),
        "daily_reference_type": "colegi",
        "daily_vs_reference_pct": Decimal("115"),
        "value_reper": Decimal("100"),
        "receipt_2plus_count": 20,
        "bonuri_pct": Decimal("35"),
        "focus_quantity": 10,
        "focus_pct": Decimal("10"),
        "glass_qty": 5,
        "premium_glass_qty": 3,
        "premium_glass_pct": Decimal("50"),
        "trend_daily_pct": Decimal("5"),
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (Decimal("84.99"), Decimal("0.0")),
        (Decimal("85"), Decimal("3.3")),
        (Decimal("100"), Decimal("6.7")),
        (Decimal("115"), Decimal("10.0")),
    ],
)
def test_score_band_boundaries(value: Decimal | None, expected: Decimal | None) -> None:
    assert score_band(
        value,
        (Decimal("85"), Decimal("100"), Decimal("115")),
        10,
    ) == expected


@pytest.mark.parametrize(
    ("score", "eligibility", "expected"),
    [
        (Decimal("100"), "insuficient", "Insuficient"),
        (None, "eligibil", "Fara scor"),
        (Decimal("85"), "eligibil", "Excelent"),
        (Decimal("75"), "eligibil", "Foarte Bun"),
        (Decimal("65"), "eligibil", "Bun"),
        (Decimal("50"), "eligibil", "Risc"),
        (Decimal("49.9"), "eligibil", "Critic"),
    ],
)
def test_score_rating_boundaries(
    score: Decimal | None,
    eligibility: Literal["eligibil", "insuficient"],
    expected: str,
) -> None:
    assert score_rating(score, eligibility) == expected


def test_final_month_full_score_and_threshold_flags() -> None:
    result = build_agent_evaluation_v2_row(_row())

    assert result.total_score == Decimal("100.0")
    assert result.rating == "Excelent"
    assert result.eligibility_status == "eligibil"
    assert result.confidence_flags == ["target_alocat_din_magazin"]
    assert result.trend_direction == "up"


def test_single_partial_month_uses_partial_weights_and_volume_thresholds() -> None:
    result = build_agent_evaluation_v2_row(
        _row(
            is_partial=True,
            final_month_count=0,
            partial_month_count=1,
            available_days=10,
            working_days=3,
            receipt_count=19,
            target_source="partial_agent_target",
            daily_reference_type="istoric_locatie",
            trend_daily_pct=Decimal("-5"),
        )
    )

    assert result.target_score == Decimal("10.0")
    assert result.daily_score == Decimal("25.0")
    assert result.eligibility_status == "insuficient"
    assert result.rating == "Insuficient"
    assert result.trend_direction == "down"
    assert result.confidence_flags == [
        "luna_partiala",
        "target_partial_din_grile",
        "reper_istoric_locatie",
        "volum_insuficient",
    ]


def test_multi_month_thresholds_and_missing_components_are_normalized() -> None:
    result = build_agent_evaluation_v2_row(
        _row(
            period_month_count=3,
            final_month_count=2,
            partial_month_count=1,
            partial_min_working_days=4,
            working_days=20,
            receipt_count=80,
            glass_qty=4,
            premium_glass_pct=None,
            daily_vs_reference_pct=None,
            trend_daily_pct=Decimal("4.99"),
        )
    )

    assert result.eligibility_status == "eligibil"
    assert result.premium_glass_score is None
    assert result.daily_score is None
    assert result.total_score == Decimal("100.0")
    assert result.trend_direction == "flat"
    assert "folii_volum_mic" in result.confidence_flags
    assert "volum_insuficient" not in result.confidence_flags
