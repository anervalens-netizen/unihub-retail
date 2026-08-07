from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from auth import AuthClaims
from db.connection import get_pool
from permissions import require_salary_access
from repositories.hr import HrRepository
from schemas.common import MonthStr
from services.hr import HrService

router = APIRouter(prefix="/api/hr", tags=["hr"])
logger = logging.getLogger(__name__)


class LeaveRequestItem(BaseModel):
    id: int
    agent_name: str
    start_date: str
    end_date: str
    leave_type: str
    notes: str | None = None
    status: str
    created_at: str | None = None
    updated_at: str | None = None


class LeaveRequestListResponse(BaseModel):
    items: list[LeaveRequestItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class HrAgentPerformanceItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    import_month: str
    total_value: float
    transaction_count: int
    active_days: int
    target_pct: float


class HrAsmPerformanceItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    asm: str
    regional: str | None = None
    total_sales: float
    total_target: float
    target_pct: float | None = None
    forecast_sales: float
    forecast_target_pct: float | None = None
    is_forecast: bool
    active_stores: int
    active_agents: int
    pct_bon2acc: float
    pct_focus: float
    total_visits: int
    avg_completion: float | None = None
    avg_duration: float | None = None
    distinct_stores_visited: int
    checklist_score: float | None = None
    approved_pct: float | None = None


class HrAsmHistoryItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    month: str
    total_sales: float
    total_target: float
    target_pct: float | None = None
    forecast_sales: float
    forecast_target_pct: float | None = None
    is_forecast: bool
    active_stores: int
    total_visits: int
    avg_completion: float | None = None
    avg_duration: float | None = None


class HrManagerStoreItem(BaseModel):
    site_code: str
    locatie: str
    firma: str
    active_agents: int
    previous_active_agents: int
    agent_delta: int


class HrManagerOverviewItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    manager: str
    regional: str | None = None
    month: str
    reporting_available: bool
    active_stores: int
    active_agents: int
    previous_active_agents: int
    agent_delta: int
    agents_added: int
    agents_left: int
    stores_without_agents: int
    agents_per_store: float
    visits_available: bool
    total_visits: int
    visited_stores: int
    visit_coverage_pct: float | None = None
    avg_visit_completion: float | None = None
    checklist_score: float | None = None
    approved_pct: float | None = None
    stores: list[HrManagerStoreItem] = Field(default_factory=list)


class HrAsmSalaryIsland(BaseModel):
    model_config = ConfigDict(extra="allow")

    site_code: str
    locatie: str
    firma: str
    total_sales: float
    total_target: float
    target_pct: float | None = None
    forecast_sales: float
    forecast_target_pct: float | None = None
    pct_used: float | None = None
    commission: float


class HrAsmSalaryZone(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_sales: float
    total_target: float
    target_pct: float | None = None
    forecast_sales: float
    forecast_target_pct: float | None = None
    pct_used: float | None = None
    commission: float


class HrAsmSalaryHomogeneity(BaseModel):
    islands_count: int
    qualifying_count: int
    qualifying_pct: float
    min_pct: float
    eligible: bool
    commission: float


class HrAsmSalaryAccFocus(BaseModel):
    pct: float | None = None
    commission: float


class HrAsmSalaryBreakdown(BaseModel):
    model_config = ConfigDict(extra="allow")

    asm: str
    month: str
    is_forecast: bool
    forecast_factor: float
    fixed_salary: float
    zone: HrAsmSalaryZone
    islands: list[HrAsmSalaryIsland] = Field(default_factory=list)
    islands_commission: float
    homogeneity: HrAsmSalaryHomogeneity
    acc_focus: HrAsmSalaryAccFocus
    total_salary: float


def _trim_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


class LeaveRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date
    leave_type: str = Field(min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("agent_name", "leave_type")
    @classmethod
    def normalize_text(cls, value: str, info) -> str:
        return _trim_text(value, field_name=info.field_name)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_interval(self) -> "LeaveRequestCreate":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class LeaveStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1, max_length=16)

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        return _trim_text(value, field_name="status")


async def get_hr_service() -> HrService:
    pool = await get_pool()
    repo = HrRepository(pool)
    return HrService(repo)


@router.get("/leave-requests", response_model=LeaveRequestListResponse)
async def get_leave_requests(
    status: str | None = Query(None, min_length=1, max_length=16),
    agent_name: str | None = Query(None, min_length=1, max_length=120),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100_000),
    svc: HrService = Depends(get_hr_service),
):
    return await svc.list_leave_requests(status, agent_name, limit=limit, offset=offset)


@router.post("/leave-requests", response_model=LeaveRequestItem)
async def post_leave_request(
    body: LeaveRequestCreate,
    svc: HrService = Depends(get_hr_service),
):
    return await svc.create_leave_request(body.model_dump())


@router.patch("/leave-requests/{request_id}", response_model=LeaveRequestItem)
async def patch_leave_request(
    request_id: int,
    body: LeaveStatusUpdate,
    svc: HrService = Depends(get_hr_service),
):
    return await svc.update_leave_status(request_id, body.status)


@router.get("/performance/{agent_name}", response_model=list[HrAgentPerformanceItem])
async def get_performance(
    agent_name: str,
    svc: HrService = Depends(get_hr_service),
):
    return await svc.get_agent_performance(agent_name)


@router.get("/asm-performance", response_model=list[HrAsmPerformanceItem])
async def get_asm_perf(
    month: MonthStr = Query(...),
    regional: str | None = Query(None),
    svc: HrService = Depends(get_hr_service),
):
    return await svc.get_asm_performance(month, regional)


@router.get("/manager-overview", response_model=list[HrManagerOverviewItem])
async def get_manager_overview(
    month: MonthStr = Query(...),
    svc: HrService = Depends(get_hr_service),
):
    """Overview operațional de portofoliu și sănătate a echipei per manager."""
    return await svc.get_manager_overview(month)


@router.get("/asm-performance/{asm_name}/history", response_model=list[HrAsmHistoryItem])
async def get_asm_perf_history(
    asm_name: str,
    months: int = Query(6, ge=1, le=24),
    svc: HrService = Depends(get_hr_service),
):
    return await svc.get_asm_performance_history(asm_name, months)


@router.get("/asm-salary/{asm_name}", response_model=HrAsmSalaryBreakdown)
async def get_asm_salary(
    asm_name: str,
    month: MonthStr = Query(...),
    svc: HrService = Depends(get_hr_service),
    claims: AuthClaims = Depends(require_salary_access),
):
    """Defalcarea salariului ASM după grila de comisionare.

    Returnează salariu fix + comisioane (zonă, insule, omogenitate, Acc Focus)
    cu prognoză pentru luna curentă parțială și valori finale pentru lunile
    încheiate. Accesul este autorizat ca resursă salarială (același set de
    roluri ca tabul Salarii) și logat fără CNP sau valori salariale.
    """
    logger.info("asm_salary_access subject=%s asm=%s month=%s", claims.sub, asm_name, month)
    return await svc.get_asm_salary(asm_name, month)
