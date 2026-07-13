"""Public API contracts for agent lifecycle and evaluation."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from schemas.common import MonthStr


StoreCoverageStatus = Literal["covered", "uncovered", "closed", "inactive"]
AgentCurrentStatus = Literal["active", "inactive_recent", "churned"]
AgentQualifier = Literal["Excelent", "Foarte Bun", "Bun", "Mediu", "Scazut"]
TargetSource = Literal["partial_agent_target", "allocated_store_target"]
DailyReferenceType = Literal["colegi", "istoric_locatie", "media_manager", "none"]
TrendDirection = Literal["up", "down", "flat"]
EligibilityStatus = Literal["eligibil", "insuficient"]
AgentRating = Literal[
    "Insuficient",
    "Fara scor",
    "Excelent",
    "Foarte Bun",
    "Bun",
    "Risc",
    "Critic",
]


class AgentsOverviewResponse(BaseModel):
    active_count: int
    new_count: int
    reactivated_count: int
    left_this_month_count: int
    retention_rate: Decimal | None
    total_unique_agents: int
    avg_seniority_months: Decimal | None
    stability_rate: Decimal | None
    churned_total_count: int


class StoreCoverageItem(BaseModel):
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str
    status: StoreCoverageStatus
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
    month: MonthStr
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
    current_status: AgentCurrentStatus


class AgentListResponse(BaseModel):
    items: list[AgentListItem]


class AgentProfileResponse(BaseModel):
    agent: str
    first_seen_month: MonthStr
    last_seen_month: MonthStr
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
    best_month: MonthStr | None
    best_month_sales: Decimal
    current_status: AgentCurrentStatus


class AgentHistoryPoint(BaseModel):
    month: MonthStr
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
    month: MonthStr
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
    qualifier: AgentQualifier


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
    month: MonthStr
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
    target_source: TargetSource
    target_pct: Decimal | None
    target_forecast_pct: Decimal | None
    is_partial: bool
    period_month_count: int
    partial_month_count: int
    final_month_count: int
    forecast_factor: Decimal
    daily_average: Decimal | None
    daily_reference: Decimal | None
    daily_reference_type: DailyReferenceType
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
    trend_direction: TrendDirection
    eligibility_status: EligibilityStatus
    confidence_flags: list[str]
    target_score: Decimal | None
    daily_score: Decimal | None
    bonuri_score: Decimal | None
    focus_score: Decimal | None
    premium_glass_score: Decimal | None
    value_reper_score: Decimal | None
    total_score: Decimal | None
    max_score: int = 100
    rating: AgentRating


class AgentEvaluationV2Response(BaseModel):
    months: list[AgentEvaluationOption]
    firmas: list[AgentEvaluationOption]
    asms: list[AgentEvaluationOption]
    stores: list[AgentEvaluationOption]
    rows: list[AgentEvaluationV2Row]
