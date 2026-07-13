from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from math import ceil
from typing import Any

from schemas.agents import AgentEvaluationV2Row


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


def score_rating(score: Decimal | None, eligibility_status: str) -> str:
    if eligibility_status == "insuficient":
        return "Insuficient"
    if score is None:
        return "Fara scor"
    if score >= Decimal("85"):
        return "Excelent"
    if score >= Decimal("75"):
        return "Foarte Bun"
    if score >= Decimal("65"):
        return "Bun"
    if score >= Decimal("50"):
        return "Risc"
    return "Critic"


def build_agent_evaluation_v2_row(row: Mapping[str, Any]) -> AgentEvaluationV2Row:
    """Apply the evaluation policy to one repository result without I/O."""
    is_partial = bool(row["is_partial"])
    period_month_count = max(1, int(row["period_month_count"] or 1))
    partial_month_count = int(row["partial_month_count"] or 0)
    final_month_count = int(row["final_month_count"] or 0)
    available_days = int(row["available_days"] or 0)
    working_days = int(row["working_days"] or 0)
    receipt_count = int(row["receipt_count"] or 0)

    if period_month_count == 1:
        min_working_days = ceil(available_days * 0.4) if is_partial and available_days else 8
        min_receipts = 20 if is_partial else 30
    else:
        min_working_days = 8 * final_month_count + int(row["partial_min_working_days"] or 0)
        min_receipts = 30 * final_month_count + 20 * partial_month_count

    confidence_flags: list[str] = []
    if is_partial:
        confidence_flags.append("luna_partiala")
    if row["target_source"] == "partial_agent_target":
        confidence_flags.append("target_partial_din_grile")
    elif row["target_source"] == "allocated_store_target":
        confidence_flags.append("target_alocat_din_magazin")
    if row["daily_reference_type"] != "colegi":
        confidence_flags.append(f"reper_{row['daily_reference_type']}")
    if int(row["glass_qty"] or 0) < 5:
        confidence_flags.append("folii_volum_mic")
    if working_days < min_working_days or receipt_count < min_receipts:
        confidence_flags.append("volum_insuficient")

    eligibility_status = (
        "insuficient" if "volum_insuficient" in confidence_flags else "eligibil"
    )
    if is_partial and period_month_count == 1:
        weights = {
            "target": 10,
            "daily": 25,
            "bonuri": 20,
            "focus": 20,
            "premium": 10,
            "value": 15,
        }
    else:
        weights = {
            "target": 25,
            "daily": 20,
            "bonuri": 15,
            "focus": 15,
            "premium": 10,
            "value": 15,
        }

    target_score_ratio = row["target_score_ratio"]
    target_score = (
        (Decimal(weights["target"]) * target_score_ratio).quantize(Decimal("0.1"))
        if target_score_ratio is not None
        else None
    )
    daily_score = score_band(
        row["daily_vs_reference_pct"],
        (Decimal("85"), Decimal("100"), Decimal("115")),
        weights["daily"],
    )
    bonuri_score = score_band(
        row["bonuri_pct"],
        (Decimal("25"), Decimal("30"), Decimal("35")),
        weights["bonuri"],
    )
    focus_score = score_band(
        row["focus_pct"],
        (Decimal("6"), Decimal("8"), Decimal("10")),
        weights["focus"],
    )
    value_score = score_band(
        row["value_reper"],
        (Decimal("90"), Decimal("95"), Decimal("100")),
        weights["value"],
    )
    premium_score = (
        score_band(
            row["premium_glass_pct"],
            (Decimal("30"), Decimal("40"), Decimal("50")),
            weights["premium"],
        )
        if int(row["glass_qty"] or 0) >= 5
        else None
    )

    scored_components = (
        (target_score, weights["target"]),
        (daily_score, weights["daily"]),
        (bonuri_score, weights["bonuri"]),
        (focus_score, weights["focus"]),
        (premium_score, weights["premium"]),
        (value_score, weights["value"]),
    )
    raw_score = sum(
        (score for score, _weight in scored_components if score is not None),
        Decimal(0),
    )
    applicable_weight = sum(
        weight for score, weight in scored_components if score is not None
    )
    total_score = (
        (raw_score * Decimal(100) / Decimal(applicable_weight)).quantize(Decimal("0.1"))
        if applicable_weight > 0
        else None
    )

    trend = row["trend_daily_pct"]
    if trend is None:
        trend_direction = "flat"
    elif trend >= Decimal("5"):
        trend_direction = "up"
    elif trend <= Decimal("-5"):
        trend_direction = "down"
    else:
        trend_direction = "flat"

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
        is_partial=is_partial,
        period_month_count=period_month_count,
        partial_month_count=partial_month_count,
        final_month_count=final_month_count,
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
        trend_direction=trend_direction,
        eligibility_status=eligibility_status,
        confidence_flags=confidence_flags,
        target_score=target_score,
        daily_score=daily_score,
        bonuri_score=bonuri_score,
        focus_score=focus_score,
        premium_glass_score=premium_score,
        value_reper_score=value_score,
        total_score=total_score,
        rating=score_rating(total_score, eligibility_status),
    )
