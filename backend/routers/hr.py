from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from auth import AuthClaims
from db.connection import get_pool
from permissions import require_salary_access
from repositories.hr import HrRepository
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


def _trim_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _valid_date(value: str) -> str:
    date.fromisoformat(value)
    return value


class LeaveRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1, max_length=120)
    start_date: str = Field(min_length=10, max_length=10)
    end_date: str = Field(min_length=10, max_length=10)
    leave_type: str = Field(min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("agent_name", "leave_type")
    @classmethod
    def normalize_text(cls, value: str, info) -> str:
        return _trim_text(value, field_name=info.field_name)

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        return _valid_date(value)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


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


@router.post("/leave-requests")
async def post_leave_request(
    body: LeaveRequestCreate,
    svc: HrService = Depends(get_hr_service),
):
    return await svc.create_leave_request(body.model_dump(mode="json"))


@router.patch("/leave-requests/{request_id}")
async def patch_leave_request(
    request_id: int,
    body: LeaveStatusUpdate,
    svc: HrService = Depends(get_hr_service),
):
    return await svc.update_leave_status(request_id, body.status)


@router.get("/performance/{agent_name}")
async def get_performance(
    agent_name: str,
    svc: HrService = Depends(get_hr_service),
):
    return await svc.get_agent_performance(agent_name)


@router.get("/asm-performance")
async def get_asm_perf(
    month: str = Query(...),
    regional: str | None = Query(None),
    svc: HrService = Depends(get_hr_service),
):
    return await svc.get_asm_performance(month, regional)


@router.get("/manager-overview")
async def get_manager_overview(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    svc: HrService = Depends(get_hr_service),
):
    """Overview operațional de portofoliu și sănătate a echipei per manager."""
    return await svc.get_manager_overview(month)


@router.get("/asm-performance/{asm_name}/history")
async def get_asm_perf_history(
    asm_name: str,
    months: int = Query(6, ge=1, le=24),
    svc: HrService = Depends(get_hr_service),
):
    return await svc.get_asm_performance_history(asm_name, months)


@router.get("/asm-salary/{asm_name}")
async def get_asm_salary(
    asm_name: str,
    month: str = Query(...),
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
