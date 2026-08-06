"""Typed normalization and validation for Target proposal inputs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from services.target_calculator.calculations import money


def normalize_proposal_parameters(
    payload: dict[str, Any],
    *,
    default_min_floor: Decimal,
    default_floor_pct: Decimal,
    default_cap_pct: Decimal,
    default_trend_weight: Decimal,
    default_seasonality_min: Decimal,
    default_seasonality_max: Decimal,
    default_trend_min: Decimal,
    default_trend_max: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    total_target = money(payload["total_target"])
    min_floor = money(payload.get("min_floor", default_min_floor))
    floor_pct = Decimal(str(payload.get("previous_month_floor_pct", default_floor_pct)))
    cap_pct = Decimal(str(payload.get("previous_month_cap_pct", default_cap_pct)))
    trend_weight = Decimal(str(payload.get("trend_weight", default_trend_weight)))
    seasonality_min = Decimal(str(payload.get("seasonality_min", default_seasonality_min)))
    seasonality_max = Decimal(str(payload.get("seasonality_max", default_seasonality_max)))
    trend_min = Decimal(str(payload.get("trend_adjustment_min", default_trend_min)))
    trend_max = Decimal(str(payload.get("trend_adjustment_max", default_trend_max)))
    valid = (
        total_target > 0 and min_floor >= 0 and floor_pct >= 0 and cap_pct > 0
        and cap_pct >= floor_pct and trend_weight >= 0 and seasonality_min > 0
        and seasonality_max >= seasonality_min and trend_min > 0 and trend_max >= trend_min
    )
    if not valid:
        raise ValueError("Parametrii de calcul nu sunt valizi.")
    return (
        total_target, min_floor, floor_pct, cap_pct, trend_weight,
        seasonality_min, seasonality_max, trend_min, trend_max,
    )
