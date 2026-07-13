from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict

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
from schemas.dashboard import (
    AgentStats,
    AsmStats,
    BrandMixItem,
    CategoryMixItem,
    DailySalesPoint,
    DashboardAllResponse,
    DashboardHistoryResponse,
    DashboardSpecialCard,
    DashboardSpecialCardMetric,
    DashboardSpecialCardsResponse,
    DashboardSummary,
    MonthlyHistoryPoint,
    PerformanceDetailResponse,
    PerformancePeerRow,
    PerformanceScoreBreakdown,
    PeriodComparisonPayload,
    PeriodComparisonPoint,
    ReceiptBucketItem,
    RegionalStats,
    StoreStats,
    YearHistoryPoint,
    YearHistoryResponse,
)
from schemas.common import (
    MonthStr,
    NonNegativeDecimal,
    NonNegativeInt,
    PercentageFloat,
    PercentageInt,
)


ImportSnapshotStatus = Literal["processing", "completed", "failed"]
ImportJobState = Literal["queued", "in_progress", "complete", "not_found"]


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
    import_month: MonthStr
    filename: str
    upload_date: date
    is_month_final: bool
    rows_in_file: NonNegativeInt | None
    rows_imported: NonNegativeInt | None
    status: ImportSnapshotStatus
    error_message: str | None
    created_at: datetime


class ImportResponse(BaseModel):
    import_month: MonthStr
    rows_in_file: NonNegativeInt
    rows_imported: NonNegativeInt
    rows_filtered: NonNegativeInt
    store_count: NonNegativeInt
    agent_count: NonNegativeInt
    snapshot_id: NonNegativeInt
    filename: str
    is_month_final: bool


class PromoActualImportResponse(BaseModel):
    import_month: MonthStr
    cutoff_date: date
    filename: str
    report_rows: NonNegativeInt
    promo_units: NonNegativeInt
    updated_promotions: NonNegativeInt


class ImportJobStatus(BaseModel):
    job_id: str
    status: ImportJobState
    result: ImportResponse | None = None
    error: str | None = None


class VisitReportRow(BaseModel):
    magazin: str
    asm: str | None
    regional: str | None
    firma: str | None
    nr_vizite: NonNegativeInt
    avg_completion: PercentageFloat
    curatenie_pct: PercentageFloat
    imagine_pct: PercentageFloat
    uniforma_pct: PercentageFloat
    afise_pct: PercentageFloat
    produse_promo_pct: PercentageFloat
    last_visit: str | None


class VisitReportResponse(BaseModel):
    month: MonthStr
    total_vizite: NonNegativeInt
    magazine_unice: NonNegativeInt
    avg_completion: PercentageFloat
    rows: list[VisitReportRow]


class VisitSummaryItem(BaseModel):
    id: str
    magazin: str
    locatie: str | None
    ora: str | None
    completion_pct: PercentageInt
    firma: str | None
    has_photos: bool


class VisitDayGroup(BaseModel):
    date: str
    nr_vizite: NonNegativeInt
    visits: list[VisitSummaryItem]


class VisitMonthGroup(BaseModel):
    month: MonthStr | Literal["—"]
    nr_vizite: NonNegativeInt
    days: list[VisitDayGroup]


class TeamLeaderGroup(BaseModel):
    team_leader: str
    nr_vizite: NonNegativeInt
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
    import_month: MonthStr
    target_value: NonNegativeDecimal
