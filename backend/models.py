from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.ai_forecast import (
    AiForecastDailyPoint,
    AiForecastManagerRow,
    AiForecastResponse,
    AiForecastRollingManagerRow,
    AiForecastRollingMonthlyPoint,
    AiForecastRollingResponse,
    AiForecastRollingStoreRow,
    AiForecastRollingSummary,
    AiForecastRunInfo,
    AiForecastStoreRow,
    AiForecastSummary,
)
from schemas.agents import (
    AgentEvaluationOption,
    AgentEvaluationResponse,
    AgentEvaluationRow,
    AgentEvaluationV2Component,
    AgentEvaluationV2Response,
    AgentEvaluationV2Row,
    AgentHistoryPoint,
    AgentHistoryResponse,
    AgentListItem,
    AgentListResponse,
    AgentMovementPoint,
    AgentMovementResponse,
    AgentProfileResponse,
    AgentsOverviewResponse,
    StoreCoverageItem,
    StoreCoverageResponse,
)
from schemas.contests import (
    ContestLeaderboardRow,
    ContestPrizeInfo,
    ContestResponse,
    ContestRuleInfo,
)
from schemas.campaigns import (
    CampaignOverview,
    CampaignProductStat,
    CampaignPromotionOption,
    CampaignsPromotionsResponse,
    CampaignSnapshot,
    CampaignStoreStat,
    FocusHistoryPoint,
    FocusHistoryResponse,
    IncentiveAgentStat,
    IncentiveCategory,
    IncentiveCategoryBreakdown,
    IncentiveData,
    IncentivePeriodStat,
    IncentiveTopAgent,
    PromoData,
    PromoIncentiveSummary,
    PromoStoreStat,
    PromoTopAgent,
    PromoTopStore,
    PromotionsIncentivesResponse,
)
from schemas.premium_glass import (
    PremiumGlassAgentStat,
    PremiumGlassAnalysis,
    PremiumGlassManagerStat,
    PremiumGlassModelStat,
    PremiumGlassProductStat,
    PremiumGlassStoreStat,
    PremiumGlassSummary,
    PremiumGlassSurfaceStat,
)


class DashboardSummary(BaseModel):
    month: str
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


class ReceiptBucketItem(BaseModel):
    bucket: str
    receipt_count: int
    share_pct: Decimal | None


class DailySalesPoint(BaseModel):
    sale_date: date
    total_sales: Decimal
    total_quantity: int
    receipt_count: int


class MonthlyHistoryPoint(BaseModel):
    month: str
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


class DashboardSpecialCardMetric(BaseModel):
    label: str
    value: str


class DashboardSpecialCard(BaseModel):
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


class DashboardSpecialCardsResponse(BaseModel):
    cards: list[DashboardSpecialCard] = Field(default_factory=list)


class AgentStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    import_month: str
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
    incentive_qty: int = 0
    return_receipt_count: int = 0


class StoreStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    import_month: str
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
    incentive_qty: int = 0
    return_receipt_count: int = 0


class RegionalStats(BaseModel):
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
    incentive_qty: int = 0
    medie_zilnica: Decimal | None
    medie_produs: Decimal | None = None
    proc_bon2acc: Decimal | None
    prc_focus_acc_qty: Decimal | None
    return_receipt_count: int = 0


class PerformancePeerRow(BaseModel):
    label: str
    sublabel: str | None = None
    total_sales: Decimal
    target_progress_pct: Decimal | None = None
    forecast_target_pct: Decimal | None = None
    proc_bon2acc: Decimal | None = None
    prc_focus_acc_qty: Decimal | None = None
    rank: int
    is_selected: bool = False


class PerformanceScoreBreakdown(BaseModel):
    target_points: Decimal
    bon2acc_points: Decimal
    focus_points: Decimal


class PerformanceDetailResponse(BaseModel):
    level: Literal["regional", "store", "agent"]
    key: str
    title: str
    subtitle: str | None = None
    month: str
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


class AsmStats(BaseModel):
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
    incentive_qty: int = 0
    medie_zilnica: Decimal | None
    medie_produs: Decimal | None = None
    proc_bon2acc: Decimal | None
    prc_focus_acc_qty: Decimal | None


class AgentOption(BaseModel):
    agent: str
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str


class FilterOptions(BaseModel):
    firme: list[str]
    regionali: list[str]
    asmi: list[str]
    magazine: list[StoreOption]
    agenti: list[AgentOption]


class ImportHistoryEntry(BaseModel):
    id: int
    import_month: str
    filename: str
    upload_date: date
    is_month_final: bool
    rows_in_file: int | None
    rows_imported: int | None
    status: str
    error_message: str | None
    created_at: datetime


class ImportResponse(BaseModel):
    import_month: str
    rows_in_file: int
    rows_imported: int
    rows_filtered: int
    store_count: int
    agent_count: int
    snapshot_id: int
    filename: str
    is_month_final: bool


class PromoActualImportResponse(BaseModel):
    import_month: str
    cutoff_date: date
    filename: str
    report_rows: int
    promo_units: int
    updated_promotions: int


class ImportJobStatus(BaseModel):
    job_id: str
    status: str
    result: ImportResponse | None = None
    error: str | None = None


class VisitReportRow(BaseModel):
    magazin: str
    asm: str | None
    regional: str | None
    firma: str | None
    nr_vizite: int
    avg_completion: float
    curatenie_pct: float
    imagine_pct: float
    uniforma_pct: float
    afise_pct: float
    produse_promo_pct: float
    last_visit: str | None


class VisitReportResponse(BaseModel):
    month: str
    total_vizite: int
    magazine_unice: int
    avg_completion: float
    rows: list[VisitReportRow]


class VisitSummaryItem(BaseModel):
    id: str
    magazin: str
    locatie: str | None
    ora: str | None
    completion_pct: int
    firma: str | None
    has_photos: bool


class VisitDayGroup(BaseModel):
    date: str
    nr_vizite: int
    visits: list[VisitSummaryItem]


class VisitMonthGroup(BaseModel):
    month: str
    nr_vizite: int
    days: list[VisitDayGroup]


class TeamLeaderGroup(BaseModel):
    team_leader: str
    nr_vizite: int
    months: list[VisitMonthGroup]


class VisitTreeResponse(BaseModel):
    team_leaders: list[TeamLeaderGroup]


class VisitDetail(BaseModel):
    id: str
    data_raport: str | None
    ora_trimitere: str | None
    firma: str | None
    regional: str | None
    asm: str | None
    team_leader: str | None
    magazin: str | None
    durata_vizita_ore: float | None
    curatenie: bool
    imagine: bool
    uniforma: bool
    afise: bool
    produse_promo: bool
    tpu: float | None
    sticla: float | None
    altele: float | None
    avizat: bool
    charisma: float | None
    casa: float | None
    incarcari_epay: float | None
    incarcari_charisma: float | None
    agent1_nume: str | None
    agent1_perf: float | None
    agent1_doi_pe_bon: float | None
    agent1_focus: float | None
    agent1_analiza: str | None
    agent1_plan: str | None
    agent2_nume: str | None
    agent2_perf: float | None
    agent2_doi_pe_bon: float | None
    agent2_focus: float | None
    agent2_analiza: str | None
    agent2_plan: str | None
    photos: list[str]
    completion_pct: int
    notes: str | None


class StoreOption(BaseModel):
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str


class StoreTargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_code: str
    import_month: str
    target_value: Decimal


class DashboardAllResponse(BaseModel):
    summary: DashboardSummary
    agents: list[AgentStats]
    stores: list[StoreStats]
    daily: list[DailySalesPoint]
    special_cards: list[DashboardSpecialCard] = Field(default_factory=list)
    period_comparison: "PeriodComparisonPayload | None" = None
    category_mix: list["CategoryMixItem"] = Field(default_factory=list)
    receipt_bucket_mix: list["ReceiptBucketItem"] = Field(default_factory=list)
    focus_subcategory_mix: list["CategoryMixItem"] = Field(default_factory=list)
    brand_mix: list["BrandMixItem"] = Field(default_factory=list)
    promo_incentive: "PromoIncentiveSummary" = Field(
        default_factory=PromoIncentiveSummary
    )
    premium_glass: "PremiumGlassAnalysis | None" = None
    regionals: list[RegionalStats] = Field(default_factory=list)
    asms: list[AsmStats] = Field(default_factory=list)
    daily_last_year: list[DailySalesPoint] = Field(default_factory=list)


class DashboardHistoryResponse(BaseModel):
    history: list[MonthlyHistoryPoint]


class YearHistoryPoint(BaseModel):
    label: str
    sort_key: str
    total_sales: Decimal
    total_target: Decimal
    total_quantity: int
    is_aggregate: bool


class YearHistoryResponse(BaseModel):
    points: list[YearHistoryPoint]


class PeriodComparisonPoint(BaseModel):
    label: str
    month: str
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


class PeriodComparisonPayload(BaseModel):
    current: PeriodComparisonPoint
    previous: PeriodComparisonPoint
    year_over_year: PeriodComparisonPoint


class CategoryMixItem(BaseModel):
    category: str
    sales_total: Decimal
    quantity_total: int
    share_pct: Decimal | None


class BrandMixItem(BaseModel):
    brand: str
    sales_total: Decimal
    quantity_total: int
    share_pct: Decimal | None
