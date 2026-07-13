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
from schemas.contests import (
    ContestLeaderboardRow,
    ContestPrizeInfo,
    ContestResponse,
    ContestRuleInfo,
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


class PromoIncentiveSummary(BaseModel):
    promo_qty: int = 0
    promo_sales: Decimal = Decimal(0)
    promo_impact: Decimal = Decimal(0)
    incentive_sold_qty: int = 0
    incentive_qty: int = 0
    incentive_value: Decimal = Decimal(0)
    incentive_qualified_qty: int = 0
    incentive_qualified_stores: int = 0
    incentive_qualified_stores_full: int = 0
    incentive_qualified_stores_half: int = 0
    incentive_qualified_agents: int = 0
    incentive_qualified_agents_full: int = 0
    incentive_qualified_agents_half: int = 0


class PremiumGlassSummary(BaseModel):
    month: str
    total_qty: int = 0
    total_sales: Decimal = Decimal(0)
    premium_qty: int = 0
    premium_sales: Decimal = Decimal(0)
    regular_qty: int = 0
    regular_sales: Decimal = Decimal(0)
    premium_qty_share_pct: Decimal | None = None
    premium_sales_share_pct: Decimal | None = None
    active_stores: int = 0
    active_agents: int = 0
    premium_active_stores: int = 0
    premium_active_agents: int = 0
    target_model_count: int = 0


class PremiumGlassModelStat(BaseModel):
    model_key: str
    model_label: str
    premium_qty: int = 0
    regular_qty: int = 0
    total_qty: int = 0
    premium_sales: Decimal = Decimal(0)
    regular_sales: Decimal = Decimal(0)
    total_sales: Decimal = Decimal(0)
    premium_qty_share_pct: Decimal | None = None
    premium_item_count: int = 0
    regular_item_count: int = 0


class PremiumGlassSurfaceStat(BaseModel):
    surface_key: Literal["screen", "camera"]
    surface_label: str
    premium_qty: int = 0
    regular_qty: int = 0
    total_qty: int = 0
    premium_sales: Decimal = Decimal(0)
    regular_sales: Decimal = Decimal(0)
    total_sales: Decimal = Decimal(0)
    premium_qty_share_pct: Decimal | None = None


class PremiumGlassStoreStat(BaseModel):
    site_code: str
    locatie: str
    firma: str
    premium_qty: int = 0
    regular_qty: int = 0
    total_qty: int = 0
    premium_sales: Decimal = Decimal(0)
    regular_sales: Decimal = Decimal(0)
    total_sales: Decimal = Decimal(0)
    premium_qty_share_pct: Decimal | None = None


class PremiumGlassManagerStat(BaseModel):
    manager: str
    premium_qty: int = 0
    regular_qty: int = 0
    total_qty: int = 0
    premium_sales: Decimal = Decimal(0)
    regular_sales: Decimal = Decimal(0)
    total_sales: Decimal = Decimal(0)
    premium_qty_share_pct: Decimal | None = None
    store_count: int = 0
    agent_count: int = 0


class PremiumGlassAgentStat(BaseModel):
    agent: str
    site_code: str
    locatie: str
    firma: str
    premium_qty: int = 0
    regular_qty: int = 0
    total_qty: int = 0
    premium_sales: Decimal = Decimal(0)
    regular_sales: Decimal = Decimal(0)
    total_sales: Decimal = Decimal(0)
    premium_qty_share_pct: Decimal | None = None


class PremiumGlassProductStat(BaseModel):
    item_code: str
    item_name: str
    is_premium: bool
    model_labels: list[str] = Field(default_factory=list)
    qty: int = 0
    sales: Decimal = Decimal(0)
    store_count: int = 0


class PremiumGlassAnalysis(BaseModel):
    summary: PremiumGlassSummary
    models: list[PremiumGlassModelStat] = Field(default_factory=list)
    surfaces: list[PremiumGlassSurfaceStat] = Field(default_factory=list)
    managers: list[PremiumGlassManagerStat] = Field(default_factory=list)
    stores: list[PremiumGlassStoreStat] = Field(default_factory=list)
    agents: list[PremiumGlassAgentStat] = Field(default_factory=list)
    products: list[PremiumGlassProductStat] = Field(default_factory=list)


class CampaignOverview(BaseModel):
    month: str
    total_focus_sales: Decimal
    total_focus_qty: int
    focus_share_pct: Decimal | None
    active_focus_products: int
    active_focus_stores: int


class CampaignProductStat(BaseModel):
    item_code: str
    item_name: str
    qty_total: int
    sales_total: Decimal
    store_count: int


class CampaignStoreStat(BaseModel):
    site_code: str
    locatie: str
    qty_total: int
    sales_total: Decimal
    active_products: int


class CampaignSnapshot(BaseModel):
    overview: CampaignOverview
    products: list[CampaignProductStat]
    stores: list[CampaignStoreStat]


class PromoStoreStat(BaseModel):
    site_code: str
    locatie: str
    qty_total: int
    sales_total: Decimal
    target: Decimal | None = None
    realizat_pct: Decimal | None = None


class PromoData(BaseModel):
    overall_qty: int
    overall_sales: Decimal
    category_qty: int | None = None
    stores: list[PromoStoreStat]


class IncentiveAgentStat(BaseModel):
    agent: str
    qty_total: int
    value: Decimal


class IncentiveData(BaseModel):
    overall_qty: int
    overall_value: Decimal
    agents: list[IncentiveAgentStat]


class PromotionsIncentivesResponse(BaseModel):
    promo: PromoData | None
    incentive: IncentiveData | None


class FocusHistoryPoint(BaseModel):
    month: str
    total_focus_sales: Decimal
    total_focus_qty: int
    focus_share_pct: Decimal | None
    active_focus_products: int
    active_focus_stores: int


class FocusHistoryResponse(BaseModel):
    history: list[FocusHistoryPoint]


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


class AgentsOverviewResponse(BaseModel):
    # Snapshot (Luna Selectata)
    active_count: int
    new_count: int
    reactivated_count: int
    left_this_month_count: int  # au fost activi luna trecuta, nu mai sunt acum
    retention_rate: Decimal | None

    # Sanatate Echipaj (Global / Istoric in contextul filtrelor)
    total_unique_agents: int
    avg_seniority_months: Decimal | None
    stability_rate: Decimal | None  # % agenti cu vechime > 6 luni din total activi
    churned_total_count: int  # toti cei care au gap >= 2 luni fata de luna selectata


class StoreCoverageItem(BaseModel):
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str
    status: str  # 'covered', 'uncovered', 'closed', 'inactive'
    agent_count: int
    has_changes: bool = False
    previous_agent_count: int = 0
    added_agents_count: int = 0
    removed_agents_count: int = 0
    change_reason: str | None = None


class StoreCoverageResponse(BaseModel):
    active_stores_count: int
    uncovered_stores_count: int
    closed_stores_count: int
    modified_stores_count: int = 0
    items: list[StoreCoverageItem]


class AgentMovementPoint(BaseModel):
    month: str
    active: int
    new: int
    reactivated: int
    churned: int
    net_growth: int = 0
    is_baseline: bool = False


class AgentMovementResponse(BaseModel):
    history: list[AgentMovementPoint]


class AgentListItem(BaseModel):
    agent: str
    store_name: str | None = None
    firma: str | None = None
    active_in_month: bool
    is_new: bool
    is_reactivated: bool
    total_sales: Decimal
    total_quantity: int
    current_status: str


class AgentListResponse(BaseModel):
    items: list[AgentListItem]


class AgentProfileResponse(BaseModel):
    agent: str
    first_seen_month: str
    last_seen_month: str
    active_months_count: int
    distinct_store_count: int
    distinct_firma_count: int
    distinct_regional_count: int
    distinct_asm_count: int
    months_since_last_seen: int
    reactivation_count: int
    longest_active_streak: int
    career_total_sales: Decimal
    career_total_quantity: int
    avg_monthly_sales: Decimal
    best_month: str | None
    best_month_sales: Decimal
    current_status: str


class AgentHistoryPoint(BaseModel):
    month: str
    total_sales: Decimal
    total_quantity: int
    receipt_count: int
    active_store_count: int
    is_active: bool


class AgentHistoryResponse(BaseModel):
    history: list[AgentHistoryPoint]


class AgentEvaluationOption(BaseModel):
    value: str
    label: str


class AgentEvaluationRow(BaseModel):
    month: str
    firma: str
    site_code: str
    locatie: str
    regional: str
    asm: str
    agent: str
    total_sales: Decimal
    total_quantity: int
    working_days: int
    store_target: Decimal
    store_working_days: int
    target_value: Decimal
    target_pct: Decimal | None
    daily_average: Decimal | None
    peer_daily_average: Decimal | None
    value_reper: Decimal | None
    receipt_count: int
    receipt_2plus_count: int
    bonuri_pct: Decimal | None
    focus_quantity: int
    focus_pct: Decimal | None
    glass_qty: int
    premium_glass_qty: int
    premium_glass_pct: Decimal | None
    target_points: int
    daily_points: int
    value_reper_points: int
    bonuri_points: int
    focus_points: int
    premium_glass_points: int
    total_points: int
    has_red_segment: bool
    qualifier: str


class AgentEvaluationResponse(BaseModel):
    months: list[AgentEvaluationOption]
    firmas: list[AgentEvaluationOption]
    asms: list[AgentEvaluationOption]
    stores: list[AgentEvaluationOption]
    rows: list[AgentEvaluationRow]


class AgentEvaluationV2Component(BaseModel):
    value: Decimal | None
    reference: Decimal | None = None
    score: Decimal | None
    weight: int
    label: str | None = None


class AgentEvaluationV2Row(BaseModel):
    month: str
    firma: str
    site_code: str
    locatie: str
    regional: str
    asm: str
    agent: str
    total_sales: Decimal
    forecast_sales: Decimal
    total_quantity: int
    working_days: int
    receipt_count: int
    target_value: Decimal
    target_source: str
    target_pct: Decimal | None
    target_forecast_pct: Decimal | None
    is_partial: bool
    period_month_count: int
    partial_month_count: int
    final_month_count: int
    forecast_factor: Decimal
    daily_average: Decimal | None
    daily_reference: Decimal | None
    daily_reference_type: str
    daily_vs_reference_pct: Decimal | None
    value_reper: Decimal | None
    receipt_2plus_count: int
    bonuri_pct: Decimal | None
    focus_quantity: int
    focus_pct: Decimal | None
    glass_qty: int
    premium_glass_qty: int
    premium_glass_pct: Decimal | None
    trend_daily_pct: Decimal | None
    trend_direction: str
    eligibility_status: str
    confidence_flags: list[str]
    target_score: Decimal | None
    daily_score: Decimal | None
    bonuri_score: Decimal | None
    focus_score: Decimal | None
    premium_glass_score: Decimal | None
    value_reper_score: Decimal | None
    total_score: Decimal | None
    max_score: int = 100
    rating: str


class AgentEvaluationV2Response(BaseModel):
    months: list[AgentEvaluationOption]
    firmas: list[AgentEvaluationOption]
    asms: list[AgentEvaluationOption]
    stores: list[AgentEvaluationOption]
    rows: list[AgentEvaluationV2Row]


class PromoTopStore(BaseModel):
    store_name: str
    qty: int
    total_qty: int
    category_qty: int
    promo_bons: int = 0
    incentive_value: float = 0.0
    incentive_potential: float = 0.0
    achievement: float | None = None  # ratio 0-1, None = no target configured
    firma: str = ""


class PromoTopAgent(BaseModel):
    agent_name: str
    store_name: str = ""
    firma: str = ""
    promo_bons: int = 0


class IncentiveTopAgent(BaseModel):
    agent_name: str
    store_name: str = ""
    firma: str = ""
    qty_sold: int
    val_incentive: float
    incentive_potential: float = 0.0
    achievement: float | None = None


class IncentiveCategory(BaseModel):
    label: str
    qty: int
    value: float


class IncentivePeriodStat(BaseModel):
    label: str
    start_date: str
    end_date: str
    product_count: int
    reward_values: list[float] = Field(default_factory=list)
    qty: int = 0
    potential: float = 0.0
    value: float = 0.0


class IncentiveCategoryBreakdown(BaseModel):
    label: str
    qty: int
    potential: float
    value: float


class CampaignPromotionOption(BaseModel):
    key: str
    label: str


class CampaignsPromotionsResponse(BaseModel):
    promotions: list[CampaignPromotionOption] = Field(default_factory=list)
    selected_promotion_key: str = ""
    promo_title: str = ""
    promo_description: str = ""
    promo_qty: int = 0
    promo_total_qty: int = 0
    promo_category_qty: int | None = None
    promo_impact: float = 0.0
    # Metrici co-purchase (regula campaniei) — consistente cu cardul Hub:
    promo_qualifying_bons: int = 0
    promo_discounted_units: int = 0
    promo_active_stores: int = 0
    promo_active_agents: int = 0
    incentive_title: str = ""
    incentive_description: str = ""
    incentive_qty: int = 0
    incentive_sold_qty: int = 0
    incentive_value: float = 0.0
    incentive_potential: float = 0.0
    incentive_qualified_qty: int = 0
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
    top_stores: list[PromoTopStore] = Field(default_factory=list)
    promo_agents: list[PromoTopAgent] = Field(default_factory=list)
    top_agents: list[IncentiveTopAgent] = Field(default_factory=list)
