from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    proc_bon2acc: Decimal | None
    prc_focus_acc_qty: Decimal | None
    total_stores: int
    total_agents: int
    working_days: int
    daily_average: Decimal | None


class DashboardSpecialCardMetric(BaseModel):
    label: str
    value: str


class DashboardSpecialCard(BaseModel):
    key: Literal["promotion", "incentive"]
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
    incentive_qty: int = 0
    incentive_value: Decimal = Decimal(0)
    incentive_qualified_stores: int = 0
    incentive_qualified_agents: int = 0


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
    acc_focus_qty: int
    prc_focus_acc_qty: Decimal | None
    target: Decimal | None = None
    proc_realizare_target: Decimal | None = None
    promo_qty: int = 0
    incentive_qty: int = 0


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
    promo_qty: int = 0
    incentive_qty: int = 0


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
    promo_qty: int = 0
    incentive_qty: int = 0
    medie_zilnica: Decimal | None
    proc_bon2acc: Decimal | None
    prc_focus_acc_qty: Decimal | None


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
    proc_bon2acc: Decimal | None
    prc_focus_acc_qty: Decimal | None


class StoreAgentStats(BaseModel):
    """Per-agent stats for a specific store — used for Card D auto-population."""

    agent_name: str
    acc_qty_realizat: int
    nr_bonuri: int
    proc_bon2acc: Decimal | None
    total_vanzari: Decimal
    medie_zilnica: Decimal | None
    acc_focus_qty: int
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


class ImportJobStatus(BaseModel):
    job_id: str
    status: str


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


class AsmGroup(BaseModel):
    asm: str
    nr_vizite: int
    months: list[VisitMonthGroup]


class VisitTreeResponse(BaseModel):
    asms: list[AsmGroup]


class VisitDetail(BaseModel):
    id: str
    data_raport: str | None
    ora_trimitere: str | None
    firma: str | None
    regional: str | None
    asm: str | None
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


class FocusProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_code: str
    item_name: str | None = None


class FocusProductResponse(BaseModel):
    item_code: str
    item_name: str | None = None
    added_at: datetime


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
    regionals: list[RegionalStats] = Field(default_factory=list)
    asms: list[AsmStats] = Field(default_factory=list)


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
    working_days: int
    daily_average: Decimal | None
    avg_receipt_value: Decimal | None
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


class AgentMovementResponse(BaseModel):
    history: list[AgentMovementPoint]


class AgentListItem(BaseModel):
    agent: str
    store_name: str | None = None
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


# ---- Salarii DB Models ----


class SalaryRecordResponse(BaseModel):
    id: int
    year: int
    month: int
    full_name: str
    cnp: str | None
    total_salary: Decimal
    company_name: str
    site_code: str | None
    locatie: str | None


class SalaryAgentSummary(BaseModel):
    full_name: str
    cnp: str | None
    company_name: str
    locatie: str | None = None
    month_count: int
    total_salary: Decimal
    avg_salary: Decimal


class SalaryAgentHistoryRecord(BaseModel):
    year: int
    month: int
    company_name: str
    total_salary: Decimal
    site_code: str | None
    locatie: str | None


class SalaryAgentHistoryResponse(BaseModel):
    records: list[SalaryAgentHistoryRecord]
    total: float
    avg: float
    month_count: int


class SalariiOverviewResponse(BaseModel):
    total: float
    by_company: list[dict]
    record_count: int
    agent_count: int
    months_span: list[int]  # [min_year, min_month, max_year, max_month]


class SalaryEvolutionPoint(BaseModel):
    month: str
    total: float
    mobicell: float
    mobiup: float


class SalaryAgentsSummaryResponse(BaseModel):
    items: list[SalaryAgentSummary]
    total: int


class PromoTopStore(BaseModel):
    store_name: str
    qty: int
    total_qty: int
    category_qty: int
    incentive_value: float = 0.0
    achievement: float | None = None  # ratio 0-1, None = no target configured
    firma: str = ""


class IncentiveTopAgent(BaseModel):
    agent_name: str
    qty_sold: int
    val_incentive: float
    achievement: float | None = None


class IncentiveCategory(BaseModel):
    label: str
    qty: int
    value: float


class CampaignsPromotionsResponse(BaseModel):
    promo_title: str = ""
    promo_description: str = ""
    promo_qty: int = 0
    promo_total_qty: int = 0
    promo_category_qty: int | None = None
    promo_impact: float = 0.0
    incentive_title: str = ""
    incentive_description: str = ""
    incentive_qty: int = 0
    incentive_value: float = 0.0
    incentive_product_count: int = 0
    incentive_categories: list[IncentiveCategory] = Field(default_factory=list)
    has_active_promotion: bool = False
    top_stores: list[PromoTopStore] = Field(default_factory=list)
    top_agents: list[IncentiveTopAgent] = Field(default_factory=list)
