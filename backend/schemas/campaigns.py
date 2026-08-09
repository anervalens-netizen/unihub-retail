from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field
from schemas.common import StrictApiModel, MonthStr



class PromoIncentiveSummary(StrictApiModel):
    promo_qty: int = 0
    promo_sales: Decimal = Decimal(0)
    promo_impact: Decimal = Decimal(0)
    incentive_sold_qty: int = 0
    incentive_sales: Decimal = Decimal(0)
    incentive_qty: int | None = 0
    incentive_potential: Decimal | None = Decimal(0)
    incentive_value: Decimal | None = Decimal(0)
    incentive_qualified_qty: int | None = 0
    incentive_qualified_stores: int = 0
    incentive_qualified_stores_full: int = 0
    incentive_qualified_stores_half: int = 0
    incentive_qualified_agents: int = 0
    incentive_qualified_agents_full: int = 0
    incentive_qualified_agents_half: int = 0
    calculation_status: Literal["complete", "invalid"] = "complete"
    calculation_warnings: list[str] = Field(default_factory=list)


class CampaignOverview(StrictApiModel):
    month: MonthStr
    total_focus_sales: Decimal
    total_focus_qty: int
    focus_share_pct: Decimal | None
    active_focus_products: int
    active_focus_stores: int


class CampaignProductStat(StrictApiModel):
    item_code: str
    item_name: str
    qty_total: int
    sales_total: Decimal
    store_count: int


class CampaignStoreStat(StrictApiModel):
    site_code: str
    locatie: str
    qty_total: int
    sales_total: Decimal
    active_products: int


class CampaignSnapshot(StrictApiModel):
    overview: CampaignOverview
    products: list[CampaignProductStat]
    stores: list[CampaignStoreStat]


class PromoStoreStat(StrictApiModel):
    site_code: str
    locatie: str
    qty_total: int
    sales_total: Decimal
    target: Decimal | None = None
    realizat_pct: Decimal | None = None


class PromoData(StrictApiModel):
    overall_qty: int
    overall_sales: Decimal
    category_qty: int | None = None
    stores: list[PromoStoreStat]


class IncentiveAgentStat(StrictApiModel):
    agent: str
    qty_total: int
    value: Decimal


class IncentiveData(StrictApiModel):
    overall_qty: int
    overall_value: Decimal
    agents: list[IncentiveAgentStat]


class PromotionsIncentivesResponse(StrictApiModel):
    promo: PromoData | None
    incentive: IncentiveData | None


class FocusHistoryPoint(StrictApiModel):
    month: MonthStr
    total_focus_sales: Decimal
    total_focus_qty: int
    focus_share_pct: Decimal | None
    active_focus_products: int
    active_focus_stores: int


class FocusHistoryResponse(StrictApiModel):
    history: list[FocusHistoryPoint]


class PromoTopStore(StrictApiModel):
    store_name: str
    qty: int
    total_qty: int
    category_qty: int
    promo_bons: int = 0
    incentive_value: float = 0.0
    incentive_potential: float = 0.0
    achievement: float | None = None
    firma: str = ""


class PromoTopAgent(StrictApiModel):
    agent_name: str
    store_name: str = ""
    firma: str = ""
    promo_bons: int = 0


class IncentiveTopAgent(StrictApiModel):
    agent_name: str
    store_name: str = ""
    firma: str = ""
    qty_sold: int
    val_incentive: float
    incentive_potential: float = 0.0
    achievement: float | None = None


class IncentiveCategory(StrictApiModel):
    label: str
    qty: int
    value: float


class IncentivePeriodStat(StrictApiModel):
    label: str
    start_date: str
    end_date: str
    product_count: int
    reward_values: list[float] = Field(default_factory=list)
    qty: int = 0
    potential: float = 0.0
    value: float = 0.0


class IncentiveCategoryBreakdown(StrictApiModel):
    label: str
    qty: int
    qualified_qty: int
    potential: float
    value: float


class CampaignPromotionOption(StrictApiModel):
    key: str
    label: str


class CampaignsPromotionsResponse(StrictApiModel):
    promotions: list[CampaignPromotionOption] = Field(default_factory=list)
    selected_promotion_key: str = ""
    promo_title: str = ""
    promo_description: str = ""
    promo_qty: int = 0
    promo_total_qty: int = 0
    promo_category_qty: int | None = None
    promo_impact: float = 0.0
    promo_qualifying_bons: int = 0
    promo_discounted_units: int = 0
    promo_discount_value: Decimal = Decimal(0)
    promo_active_stores: int = 0
    promo_active_agents: int = 0
    incentive_title: str = ""
    incentive_description: str = ""
    incentive_qty: int | None = 0
    incentive_sold_qty: int = 0
    incentive_value: float | None = 0.0
    incentive_potential: float | None = 0.0
    incentive_qualified_qty: int | None = 0
    incentive_qualified_stores: int = 0
    incentive_qualified_stores_full: int = 0
    incentive_qualified_stores_half: int = 0
    incentive_qualified_agents: int = 0
    incentive_qualified_agents_full: int = 0
    incentive_qualified_agents_half: int = 0
    incentive_product_count: int = 0
    incentive_categories: list[IncentiveCategory] = Field(default_factory=list)
    incentive_periods: list[IncentivePeriodStat] = Field(default_factory=list)
    incentive_category_breakdown: list[IncentiveCategoryBreakdown] = Field(default_factory=list)
    has_active_promotion: bool = False
    promo_calculation_status: Literal["complete", "partial", "invalid", "not_configured"] = "not_configured"
    incentive_calculation_status: Literal["complete", "invalid", "not_configured"] = "not_configured"
    calculation_warnings: list[str] = Field(default_factory=list)
    top_stores: list[PromoTopStore] = Field(default_factory=list)
    promo_agents: list[PromoTopAgent] = Field(default_factory=list)
    top_agents: list[IncentiveTopAgent] = Field(default_factory=list)
