from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import ConfigDict, Field, field_validator
from schemas.common import StrictApiModel, MonthStr

from schemas.campaigns import PromoIncentiveSummary
from schemas.premium_glass import PremiumGlassAnalysis
from domain.dashboard_filters import canonical_dashboard_site_codes


class DashboardSummary(StrictApiModel):
    month: MonthStr
    total_sales: Decimal
    total_target: Decimal
    target_progress_pct: Decimal | None
    forecast_sales: Decimal | None = None
    forecast_target_progress_pct: Decimal | None = None
    total_quantity: int
    total_receipts: int
    proc_bon2acc: Decimal | None
    prc_focus_acc_qty: Decimal | None
    total_stores: int
    total_agents: int
    working_days: int
    daily_average: Decimal | None
    medie_produs: Decimal | None = None
    is_month_final: bool = True
    last_sale_date: date | None = None
    imported_day_of_month: int | None = None
    days_in_month: int | None = None
    cartele_qty: int = 0


class ReceiptBucketItem(StrictApiModel):
    bucket: str
    receipt_count: int
    share_pct: Decimal | None


class DailySalesPoint(StrictApiModel):
    sale_date: date
    total_sales: Decimal
    total_quantity: int
    receipt_count: int


class MonthlyHistoryPoint(StrictApiModel):
    month: MonthStr
    total_sales: Decimal
    total_target: Decimal
    target_progress_pct: Decimal | None
    total_quantity: int
    total_receipts: int
    return_receipt_count: int = 0
    proc_bon2acc: Decimal | None
    prc_focus_acc_qty: Decimal | None
    total_stores: int
    total_agents: int
    working_days: int
    daily_average: Decimal | None
    medie_produs: Decimal | None = None


class DashboardSpecialCardMetric(StrictApiModel):
    label: str
    value: str


class DashboardSpecialCard(StrictApiModel):
    key: Literal["promotion", "incentive", "premium_glass"]
    title: str
    subtitle: str | None = None
    status: Literal[
        "ready",
        "inactive",
        "no_data",
        "missing_config",
        "missing_source",
        "limited_scope",
    ]
    status_label: str
    highlight_value: str
    description: str
    coverage_note: str | None = None
    metrics: list[DashboardSpecialCardMetric] = Field(default_factory=list)


class DashboardSpecialCardsResponse(StrictApiModel):
    cards: list[DashboardSpecialCard] = Field(default_factory=list)


class AgentStats(StrictApiModel):
    model_config = ConfigDict(from_attributes=True)

    import_month: MonthStr
    agent: str
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str
    acc_qty_realizat: int
    nr_bonuri: int
    nr_bon2acc: int
    proc_bon2acc: Decimal | None
    total_vanzari: Decimal
    zile_lucrate: int
    medie_zilnica: Decimal | None
    medie_produs: Decimal | None = None
    acc_focus_qty: int
    prc_focus_acc_qty: Decimal | None
    target: Decimal | None = None
    proc_realizare_target: Decimal | None = None
    promo_qty: int = 0
    promo_discount_value: Decimal = Decimal(0)
    incentive_qty: int = 0
    return_receipt_count: int = 0


class StoreStats(StrictApiModel):
    model_config = ConfigDict(from_attributes=True)

    import_month: MonthStr
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str
    total_vanzari: Decimal
    qty_total: int | None
    nr_bonuri: int
    nr_agenti: int
    zile_active: int
    target: Decimal
    proc_realizare_target: Decimal | None
    forecast_target_pct: Decimal | None = None
    medie_produs: Decimal | None = None
    promo_qty: int = 0
    promo_discount_value: Decimal = Decimal(0)
    incentive_qty: int = 0
    return_receipt_count: int = 0
    proc_bon2acc: Decimal | None = None
    prc_focus_acc_qty: Decimal | None = None


class RegionalStats(StrictApiModel):
    model_config = ConfigDict(from_attributes=True)

    regional: str
    total_vanzari: Decimal
    qty_total: int
    nr_bonuri: int
    nr_agenti: int
    zile_active: int
    target: Decimal
    proc_realizare_target: Decimal | None
    forecast_target_pct: Decimal | None = None
    promo_qty: int = 0
    promo_discount_value: Decimal = Decimal(0)
    incentive_qty: int = 0
    medie_zilnica: Decimal | None
    medie_produs: Decimal | None = None
    proc_bon2acc: Decimal | None
    prc_focus_acc_qty: Decimal | None
    return_receipt_count: int = 0


class PerformancePeerRow(StrictApiModel):
    label: str
    sublabel: str | None = None
    total_sales: Decimal
    target_progress_pct: Decimal | None = None
    forecast_target_pct: Decimal | None = None
    proc_bon2acc: Decimal | None = None
    prc_focus_acc_qty: Decimal | None = None
    rank: int
    is_selected: bool = False


class PerformanceScoreBreakdown(StrictApiModel):
    target_points: Decimal
    bon2acc_points: Decimal
    focus_points: Decimal


class PerformanceDetailResponse(StrictApiModel):
    level: Literal["regional", "store", "agent"]
    key: str
    title: str
    subtitle: str | None = None
    month: MonthStr
    summary: DashboardSummary
    history: list[MonthlyHistoryPoint] = Field(default_factory=list)
    daily: list[DailySalesPoint] = Field(default_factory=list)
    score: int
    score_breakdown: PerformanceScoreBreakdown
    score_label: str
    note: str
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    peer_rows: list[PerformancePeerRow] = Field(default_factory=list)
    context_summary: DashboardSummary | None = None


class AsmStats(StrictApiModel):
    model_config = ConfigDict(from_attributes=True)

    asm: str
    regional: str
    total_vanzari: Decimal
    qty_total: int
    nr_bonuri: int
    nr_agenti: int
    zile_active: int
    target: Decimal
    proc_realizare_target: Decimal | None
    promo_qty: int = 0
    promo_discount_value: Decimal = Decimal(0)
    incentive_qty: int = 0
    medie_zilnica: Decimal | None
    medie_produs: Decimal | None = None
    proc_bon2acc: Decimal | None
    prc_focus_acc_qty: Decimal | None


class YearHistoryPoint(StrictApiModel):
    label: str
    sort_key: str
    total_sales: Decimal
    total_target: Decimal
    total_quantity: int
    is_aggregate: bool


class YearHistoryResponse(StrictApiModel):
    points: list[YearHistoryPoint]


class PeriodComparisonPoint(StrictApiModel):
    label: str
    month: MonthStr
    day_range: str
    total_sales: Decimal
    total_quantity: int
    total_receipts: int
    cartele_qty: int = 0
    working_days: int
    daily_average: Decimal | None
    avg_receipt_value: Decimal | None
    medie_produs: Decimal | None = None
    proc_bon2acc: Decimal | None
    prc_focus_acc_qty: Decimal | None


class PeriodComparisonPayload(StrictApiModel):
    current: PeriodComparisonPoint
    previous: PeriodComparisonPoint
    year_over_year: PeriodComparisonPoint


class CategoryMixItem(StrictApiModel):
    category: str
    sales_total: Decimal
    quantity_total: int
    share_pct: Decimal | None


class BrandMixItem(StrictApiModel):
    brand: str
    sales_total: Decimal
    quantity_total: int
    share_pct: Decimal | None


class DashboardAllResponse(StrictApiModel):
    summary: DashboardSummary
    agents: list[AgentStats]
    stores: list[StoreStats]
    daily: list[DailySalesPoint]
    special_cards: list[DashboardSpecialCard] = Field(default_factory=list)
    period_comparison: PeriodComparisonPayload | None = None
    category_mix: list[CategoryMixItem] = Field(default_factory=list)
    receipt_bucket_mix: list[ReceiptBucketItem] = Field(default_factory=list)
    focus_subcategory_mix: list[CategoryMixItem] = Field(default_factory=list)
    brand_mix: list[BrandMixItem] = Field(default_factory=list)
    promo_incentive: PromoIncentiveSummary = Field(default_factory=PromoIncentiveSummary)
    premium_glass: PremiumGlassAnalysis | None = None
    regionals: list[RegionalStats] = Field(default_factory=list)
    asms: list[AsmStats] = Field(default_factory=list)
    daily_last_year: list[DailySalesPoint] = Field(default_factory=list)


class DashboardAllQuery(StrictApiModel):
    month: MonthStr
    firma: str | None = None
    regional: str | None = None
    asm: str | None = None
    site_code: str | None = None
    agent: str | None = None
    current_scope: bool = False
    include_closed_stores: bool = False

    @field_validator("site_code", mode="before")
    @classmethod
    def canonicalize_site_code(cls, value: object) -> str | None:
        return canonical_dashboard_site_codes(value)


class DashboardAllBatchRequest(StrictApiModel):
    queries: list[DashboardAllQuery] = Field(min_length=1, max_length=12)


class DashboardAllBatchResponse(StrictApiModel):
    results: list[DashboardAllResponse]


class DashboardHistoryResponse(StrictApiModel):
    history: list[MonthlyHistoryPoint]
