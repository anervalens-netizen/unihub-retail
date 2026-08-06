from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from schemas.erp_reconciliation import ErpReconciliationResponse

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


class ImportCoverageReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    incoming_store_count: int | None = None
    company_count: int | None = None
    active_store_count_before: int | None = None
    prior_snapshot_store_count: int | None = None
    active_store_coverage_pct: float | None = None
    prior_snapshot_coverage_pct: float | None = None
    missing_active_store_count: int | None = None
    missing_prior_store_count: int | None = None
    new_store_count: int | None = None
    metadata_change_count: int | None = None
    store_activity_writes: int | None = None

class SalesGenerationAnomaly(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    blocking: bool
    message: str
    count: int | None = None


class SalesGenerationManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    cutoff_date: date | None = None
    receipt_count: NonNegativeInt | None = None
    total_value: str | None = None
    total_quantity: NonNegativeInt | None = None
    business_sha256: str | None = None
    site_day_count: NonNegativeInt | None = None
    anomalies: list[SalesGenerationAnomaly] = Field(default_factory=list)
    generation_state: Literal["validated", "promoted"] | None = None

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
    coverage_report: ImportCoverageReport = Field(default_factory=ImportCoverageReport)
    created_at: datetime
    finished_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)


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
    coverage_report: ImportCoverageReport = Field(default_factory=ImportCoverageReport)
    generation_state: Literal["validated", "promoted"] = "promoted"
    generation_token: str | None = Field(default=None, pattern=r"^[0-9a-f-]{36}$")
    manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    manifest: SalesGenerationManifest | None = None


class SalesGenerationPromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generation_token: str = Field(pattern=r"^[0-9a-f-]{36}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    override_reason: str | None = Field(default=None, min_length=10, max_length=500)


class PromoActualImportResponse(BaseModel):
    import_month: MonthStr
    cutoff_date: date
    filename: str
    report_rows: NonNegativeInt
    promo_units: NonNegativeInt
    updated_promotions: NonNegativeInt
    generation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    material_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ImportJobStatus(BaseModel):
    job_id: str
    status: ImportJobState
    job_kind: Literal["sales", "promo_actuals", "erp_reconciliation"] = "sales"
    result: ImportResponse | None = None
    promo_result: PromoActualImportResponse | None = None
    erp_result: ErpReconciliationResponse | None = None
    error: str | None = None


class ExportOperationResponse(BaseModel):
    id: int = Field(gt=0)
    kind: Literal["daily_metrics", "daily_comparison"]
    status: Literal["queued", "running", "completed", "failed", "cancelled", "expired"]
    job_id: str
    filename: str | None = None
    artifact_size: int | None = Field(default=None, ge=0)
    artifact_sha256: str | None = None
    peak_rss_bytes: int | None = Field(default=None, ge=0)
    build_seconds: float | None = Field(default=None, ge=0)
    cell_count: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    expires_at: datetime | None = None
    can_download: bool = False


class ExportOperationPublishUncertainDetail(BaseModel):
    status: Literal["unknown"]
    job_id: str | None = None
    operation_id: int | None = None


class ExportOperationUnavailableResponse(BaseModel):
    detail: str | ExportOperationPublishUncertainDetail


class StoreActivityChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool
    expected_is_active: bool
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 10:
            raise ValueError("reason must contain at least 10 non-space characters")
        return normalized


class StoreActivityChangeResponse(BaseModel):
    site_code: str
    previous_is_active: bool
    is_active: bool
    event_id: int


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


class StoreTargetsSaveResponse(BaseModel):
    inserted: NonNegativeInt


class StoreTargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_code: str
    import_month: MonthStr
    target_value: NonNegativeDecimal
