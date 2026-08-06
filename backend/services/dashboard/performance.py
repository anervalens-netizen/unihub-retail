"""Pure performance scoring rules used by Dashboard detail responses."""

from __future__ import annotations

from decimal import Decimal

from schemas.dashboard import DashboardSummary, PerformanceScoreBreakdown

PERFORMANCE_COMPONENT_WEIGHT = Decimal("20")


def score_breakdown(summary: DashboardSummary) -> PerformanceScoreBreakdown:
    target_pct = summary.forecast_target_progress_pct or summary.target_progress_pct or Decimal(0)
    bon_pct = summary.proc_bon2acc or Decimal(0)
    focus_pct = summary.prc_focus_acc_qty or Decimal(0)
    target_score = (
        min(max(target_pct, Decimal(0)), Decimal(120)) / Decimal(120) * Decimal(60)
    ).quantize(Decimal("0.1"))
    return PerformanceScoreBreakdown(
        target_points=target_score,
        bon2acc_points=score_bon2acc(bon_pct),
        focus_points=score_focus(focus_pct),
    )


def score_total(breakdown: PerformanceScoreBreakdown) -> int:
    score = breakdown.target_points + breakdown.bon2acc_points + breakdown.focus_points
    return max(0, min(100, round(float(score))))


def score_bon2acc(value: Decimal) -> Decimal:
    if value > Decimal("35"):
        points = PERFORMANCE_COMPONENT_WEIGHT
    elif value >= Decimal("30"):
        points = PERFORMANCE_COMPONENT_WEIGHT * Decimal(2) / Decimal(3)
    elif value >= Decimal("20"):
        points = PERFORMANCE_COMPONENT_WEIGHT / Decimal(3)
    else:
        points = Decimal(0)
    return points.quantize(Decimal("0.1"))


def score_focus(value: Decimal) -> Decimal:
    if value > Decimal("8"):
        points = PERFORMANCE_COMPONENT_WEIGHT
    elif value >= Decimal("6"):
        points = PERFORMANCE_COMPONENT_WEIGHT * Decimal(2) / Decimal(3)
    else:
        points = Decimal(0)
    return points.quantize(Decimal("0.1"))


def trend_sales(summary: DashboardSummary) -> Decimal:
    if not summary.is_month_final and summary.forecast_sales is not None:
        return summary.forecast_sales
    return summary.total_sales


def score_label(score: int) -> str:
    if score >= 85:
        return "Foarte bine"
    if score >= 70:
        return "Bun"
    if score >= 55:
        return "De urmarit"
    return "Necesita interventie"
