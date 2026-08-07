from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from db.connection import get_pool
from schemas.common import MonthStr
from permissions import require_business_write_access
from rate_limits import BUSINESS_WRITE_LIMIT, rate_limit
from repositories.crm import CrmRepository
from services.crm import CrmService

router = APIRouter(prefix="/api/crm", tags=["crm"])


class CrmBreakdownResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    target_pct: float | None = None
    trend_pct: float | None = None
    kpi_pct: float | None = None
    visits_pct: float | None = None


class CrmScoreResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    site_code: str
    score: float
    breakdown: CrmBreakdownResponse


class CrmAlertResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    site_code: str
    score: float
    reasons: list[str] = Field(default_factory=list)
    regional: str | None = None
    asm: str | None = None
    locatie: str | None = None


class CrmRecalculateResponse(BaseModel):
    recalculated: int
    month: str

async def get_crm_service() -> CrmService:
    pool = await get_pool()
    repo = CrmRepository(pool)
    return CrmService(repo, pool)


@router.get("/scores", response_model=list[CrmScoreResponse])
async def get_scores(
    month: MonthStr = Query(...),
    svc: CrmService = Depends(get_crm_service),
):
    return await svc.get_scores(month)


@router.post("/scores/recalculate", response_model=CrmRecalculateResponse)
async def recalculate_scores(
    month: MonthStr = Query(...),
    _claims=Depends(require_business_write_access),
    _rate_limit: None = Depends(rate_limit(BUSINESS_WRITE_LIMIT)),
    svc: CrmService = Depends(get_crm_service),
):
    recalculated_count = await svc.recalculate_scores(month)
    return {"recalculated": recalculated_count, "month": month}


@router.get("/alerts", response_model=list[CrmAlertResponse])
async def get_alerts(
    month: MonthStr = Query(...),
    svc: CrmService = Depends(get_crm_service),
):
    return await svc.get_alerts(month)
