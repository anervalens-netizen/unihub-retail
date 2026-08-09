"""Cycle-safe internal contracts shared by Campaigns evaluation and projection."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from schemas.campaigns import (
    IncentiveCategory,
    IncentiveCategoryBreakdown,
    IncentivePeriodStat,
    IncentiveTopAgent,
    PromoIncentiveSummary,
    PromoTopAgent,
    PromoTopStore,
)
from services.promo_copurchase import PromoCoPurchaseResult
from services.promotion_evaluation import PromotionEvaluation, PromotionEvaluationStatus


@dataclass
class CampaignContext:
    """Request-local Promo/Incentive inputs from one repeatable-read snapshot."""

    config_error: str | None
    promotion_definitions: list[dict[str, Any]]
    promotion_definition: dict[str, Any] | None
    promotion_error: str | None
    incentive_campaign: dict[str, Any] | None
    promotion_results: list[tuple[dict[str, Any], PromoCoPurchaseResult]]
    promo_excluded_units: dict[tuple[str, str, str], int]
    promo_discount_values: dict[tuple[str, str, str], Decimal] = field(
        default_factory=dict
    )
    promotion_status: PromotionEvaluationStatus = PromotionEvaluationStatus.COMPLETE
    promotion_warnings: tuple[str, ...] = ()
    promotion_evaluations: list[
        tuple[dict[str, Any], PromotionEvaluation]
    ] = field(default_factory=list)
    period_evaluations: dict[
        tuple[int, date, date], PromotionEvaluation
    ] = field(default_factory=dict)

    @property
    def selected_promotion_result(self) -> PromoCoPurchaseResult | None:
        selected_key = (
            self.promotion_definition.get("key")
            if self.promotion_definition is not None
            else None
        )
        for definition, result in self.promotion_results:
            if definition.get("key") == selected_key:
                return result
        return None

    @property
    def selected_promotion_evaluation(self) -> PromotionEvaluation | None:
        selected_key = (
            self.promotion_definition.get("key")
            if self.promotion_definition is not None
            else None
        )
        for definition, evaluation in self.promotion_evaluations:
            if definition.get("key") == selected_key:
                return evaluation
        return None

    @staticmethod
    def period_evaluation_key(
        definition: dict[str, Any],
        start_date: date,
        end_date: date,
    ) -> tuple[int, date, date]:
        return id(definition), start_date, end_date


@dataclass(frozen=True)
class CampaignResponseSnapshot:
    """All values needed after releasing the repeatable-read connection."""

    start: date
    end: date
    month: str
    promotion_definitions: list[dict[str, Any]]
    promotion_list_error: str | None
    promotion_definition: dict[str, Any] | None
    promotion_error: str | None
    include_incentive: bool
    incentive_campaign: dict[str, Any] | None
    incentive_periods: list[dict[str, Any]]
    campaign_context: CampaignContext
    summary: PromoIncentiveSummary | None
    store_multipliers: dict[str, float]
    store_achievements: dict[str, float | None]
    promo_total_row: Any | None
    promo_store_rows: list[Any] = field(default_factory=list)
    incentive_store_rows: list[Any] = field(default_factory=list)
    incentive_agent_rows: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class PromotionProjection:
    title: str = ""
    description: str = ""
    error: str | None = None
    has_active: bool = False
    calculation_status: str = "not_configured"
    warnings: list[str] = field(default_factory=list)
    invalidates_incentive: bool = False
    total_qty: int = 0
    qty: int = 0
    impact: Decimal = Decimal("0")
    qualifying_bons: int = 0
    discounted_units: int = 0
    discount_value: Decimal = Decimal("0")
    active_stores: int = 0
    active_agents: int = 0
    top_stores: list[PromoTopStore] = field(default_factory=list)
    promo_agents: list[PromoTopAgent] = field(default_factory=list)
    incentive_excluded_units: dict[tuple[str, str, str], int] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class IncentiveProjection:
    title: str = ""
    description: str = ""
    calculation_status: str = "not_configured"
    warnings: list[str] = field(default_factory=list)
    qty: int | None = 0
    sold_qty: int = 0
    value: Decimal | None = Decimal("0")
    potential: Decimal | None = Decimal("0")
    qualified_qty: int | None = 0
    qualified_stores: int = 0
    qualified_stores_full: int = 0
    qualified_stores_half: int = 0
    qualified_agents: int = 0
    qualified_agents_full: int = 0
    qualified_agents_half: int = 0
    product_count: int = 0
    categories: list[IncentiveCategory] = field(default_factory=list)
    periods: list[IncentivePeriodStat] = field(default_factory=list)
    category_breakdown: list[IncentiveCategoryBreakdown] = field(
        default_factory=list
    )
    top_stores: list[PromoTopStore] = field(default_factory=list)
    top_agents: list[IncentiveTopAgent] = field(default_factory=list)
