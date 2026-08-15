from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from math import ceil
from typing import Any

from schemas.agents import (
    AgentEvaluationV2Row,
    AgentRating,
    EligibilityStatus,
    TrendDirection,
)


PARTIAL_MONTH_WEIGHTS = {
    "target": 10,
    "daily": 25,
    "bonuri": 20,
    "focus": 20,
    "premium": 10,
    "value": 15,
}
FINAL_MONTH_WEIGHTS = {
    "target": 25,
    "daily": 20,
    "bonuri": 15,
    "focus": 15,
    "premium": 10,
    "value": 15,
}
RATING_BANDS: tuple[tuple[Decimal, AgentRating], ...] = (
    (Decimal("85"), "Excelent"),
    (Decimal("75"), "Foarte Bun"),
    (Decimal("65"), "Bun"),
    (Decimal("50"), "Risc"),
)
DAILY_SCORE_THRESHOLDS = (Decimal("85"), Decimal("100"), Decimal("115"))
RECEIPT_SCORE_THRESHOLDS = (Decimal("25"), Decimal("30"), Decimal("35"))
FOCUS_SCORE_THRESHOLDS = (Decimal("6"), Decimal("8"), Decimal("10"))
VALUE_SCORE_THRESHOLDS = (Decimal("90"), Decimal("95"), Decimal("100"))
PREMIUM_GLASS_SCORE_THRESHOLDS = (Decimal("30"), Decimal("40"), Decimal("50"))
PARTIAL_MONTH_MINIMUM_DAY_SHARE = 0.4
FINAL_MONTH_MINIMUM_WORKING_DAYS = 8
PARTIAL_MONTH_MINIMUM_RECEIPTS = 20
FINAL_MONTH_MINIMUM_RECEIPTS = 30
PREMIUM_GLASS_CONFIDENCE_MINIMUM_QTY = 5


@dataclass(frozen=True)
class EvaluationBasis:
    is_partial: bool
    period_month_count: int
    partial_month_count: int
    final_month_count: int
    working_days: int
    receipt_count: int
    min_working_days: int
    min_receipts: int
    weights: Mapping[str, int]


def _evaluation_basis(row: Mapping[str, Any]) -> EvaluationBasis:
    is_partial = bool(row["is_partial"])
    period_month_count = max(1, int(row["period_month_count"] or 1))
    partial_month_count = int(row["partial_month_count"] or 0)
    final_month_count = int(row["final_month_count"] or 0)
    working_days = int(row["working_days"] or 0)
    receipt_count = int(row["receipt_count"] or 0)
    if period_month_count == 1:
        available_days = int(row["available_days"] or 0)
        min_working_days = (
            ceil(available_days * PARTIAL_MONTH_MINIMUM_DAY_SHARE)
            if is_partial and available_days
            else FINAL_MONTH_MINIMUM_WORKING_DAYS
        )
        min_receipts = (
            PARTIAL_MONTH_MINIMUM_RECEIPTS
            if is_partial
            else FINAL_MONTH_MINIMUM_RECEIPTS
        )
    else:
        min_working_days = (
            FINAL_MONTH_MINIMUM_WORKING_DAYS * final_month_count
            + int(row["partial_min_working_days"] or 0)
        )
        min_receipts = (
            FINAL_MONTH_MINIMUM_RECEIPTS * final_month_count
            + PARTIAL_MONTH_MINIMUM_RECEIPTS * partial_month_count
        )
    weights = (
        PARTIAL_MONTH_WEIGHTS
        if is_partial and period_month_count == 1
        else FINAL_MONTH_WEIGHTS
    )
    return EvaluationBasis(
        is_partial,
        period_month_count,
        partial_month_count,
        final_month_count,
        working_days,
        receipt_count,
        min_working_days,
        min_receipts,
        weights,
    )


def _confidence_flags(row: Mapping[str, Any], basis: EvaluationBasis) -> list[str]:
    flags: list[str] = []
    if basis.is_partial:
        flags.append("luna_partiala")
    source = row["target_source"]
    if source == "partial_agent_target":
        flags.append("target_partial_din_grile")
    elif source == "allocated_store_target":
        flags.append("target_alocat_din_magazin")
    reference_type = row["daily_reference_type"]
    if reference_type != "colegi":
        flags.append(f"reper_{reference_type}")
    if int(row["glass_qty"] or 0) < PREMIUM_GLASS_CONFIDENCE_MINIMUM_QTY:
        flags.append("folii_volum_mic")
    if (
        basis.working_days < basis.min_working_days
        or basis.receipt_count < basis.min_receipts
    ):
        flags.append("volum_insuficient")
    return flags


def _component_scores(
    row: Mapping[str, Any],
    weights: Mapping[str, int],
) -> dict[str, Decimal | None]:
    target_ratio = row["target_score_ratio"]
    target = (
        (Decimal(weights["target"]) * target_ratio).quantize(Decimal("0.1"))
        if target_ratio is not None
        else None
    )
    premium = (
        score_band(
            row["premium_glass_pct"],
            PREMIUM_GLASS_SCORE_THRESHOLDS,
            weights["premium"],
        )
        if int(row["glass_qty"] or 0) >= PREMIUM_GLASS_CONFIDENCE_MINIMUM_QTY
        else None
    )
    return {
        "target": target,
        "daily": score_band(row["daily_vs_reference_pct"], DAILY_SCORE_THRESHOLDS, weights["daily"]),
        "bonuri": score_band(row["bonuri_pct"], RECEIPT_SCORE_THRESHOLDS, weights["bonuri"]),
        "focus": score_band(row["focus_pct"], FOCUS_SCORE_THRESHOLDS, weights["focus"]),
        "premium": premium,
        "value": score_band(row["value_reper"], VALUE_SCORE_THRESHOLDS, weights["value"]),
    }


def _normalized_score(
    scores: Mapping[str, Decimal | None],
    weights: Mapping[str, int],
) -> Decimal | None:
    raw = sum((score for score in scores.values() if score is not None), Decimal(0))
    applicable = sum(weights[name] for name, score in scores.items() if score is not None)
    if applicable == 0:
        return None
    return (raw * Decimal(100) / Decimal(applicable)).quantize(Decimal("0.1"))


def _trend_direction(value: Decimal | None) -> TrendDirection:
    if value is not None and value >= Decimal("5"):
        return "up"
    if value is not None and value <= Decimal("-5"):
        return "down"
    return "flat"


def score_band(
    value: Decimal | None,
    thresholds: tuple[Decimal, Decimal, Decimal],
    weight: int,
) -> Decimal | None:
    if value is None:
        return None
    if value >= thresholds[2]:
        points = Decimal(3)
    elif value >= thresholds[1]:
        points = Decimal(2)
    elif value >= thresholds[0]:
        points = Decimal(1)
    else:
        points = Decimal(0)
    return (Decimal(weight) * points / Decimal(3)).quantize(Decimal("0.1"))


def score_rating(score: Decimal | None, eligibility_status: EligibilityStatus) -> AgentRating:
    if eligibility_status == "insuficient":
        return "Insuficient"
    if score is None:
        return "Fara scor"
    for minimum_score, rating in RATING_BANDS:
        if score >= minimum_score:
            return rating
    return "Critic"


def build_agent_evaluation_v2_row(row: Mapping[str, Any]) -> AgentEvaluationV2Row:
    """Apply the evaluation policy to one repository result without I/O."""
    basis = _evaluation_basis(row)
    confidence_flags = _confidence_flags(row, basis)
    eligibility_status: EligibilityStatus = (
        "insuficient" if "volum_insuficient" in confidence_flags else "eligibil"
    )
    scores = _component_scores(row, basis.weights)
    total_score = _normalized_score(scores, basis.weights)
    trend = row["trend_daily_pct"]
    return AgentEvaluationV2Row(
        month=row["month"],
        firma=row["firma"],
        site_code=row["site_code"],
        locatie=row["locatie"],
        regional=row["regional"],
        asm=row["asm"],
        agent=row["agent"],
        total_sales=row["total_sales"],
        forecast_sales=row["forecast_sales"],
        total_quantity=row["total_quantity"],
        working_days=row["working_days"],
        receipt_count=row["receipt_count"],
        target_value=row["target_value"],
        target_source=row["target_source"],
        target_pct=row["target_pct"],
        target_forecast_pct=row["target_forecast_pct"],
        is_partial=basis.is_partial,
        period_month_count=basis.period_month_count,
        partial_month_count=basis.partial_month_count,
        final_month_count=basis.final_month_count,
        forecast_factor=row["forecast_factor"],
        daily_average=row["daily_average"],
        daily_reference=row["daily_reference"],
        daily_reference_type=row["daily_reference_type"],
        daily_vs_reference_pct=row["daily_vs_reference_pct"],
        value_reper=row["value_reper"],
        receipt_2plus_count=row["receipt_2plus_count"],
        bonuri_pct=row["bonuri_pct"],
        focus_quantity=row["focus_quantity"],
        focus_pct=row["focus_pct"],
        glass_qty=row["glass_qty"],
        premium_glass_qty=row["premium_glass_qty"],
        premium_glass_pct=row["premium_glass_pct"],
        trend_daily_pct=trend,
        trend_direction=_trend_direction(trend),
        eligibility_status=eligibility_status,
        confidence_flags=confidence_flags,
        target_score=scores["target"],
        daily_score=scores["daily"],
        bonuri_score=scores["bonuri"],
        focus_score=scores["focus"],
        premium_glass_score=scores["premium"],
        value_reper_score=scores["value"],
        total_score=total_score,
        rating=score_rating(total_score, eligibility_status),
    )
