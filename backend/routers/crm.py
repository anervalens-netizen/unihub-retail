from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from schemas.common import StrictApiModel, MonthStr

from composition import build_crm_service
from permissions import require_business_write_access
from rate_limits import BUSINESS_WRITE_LIMIT, rate_limit
from services.crm import CrmService

router = APIRouter(prefix="/api/crm", tags=["crm"])


class CrmBreakdownResponse(StrictApiModel):

    target_pct: float | None = None
    trend_pct: float | None = None
    kpi_pct: float | None = None
    visits_pct: float | None = None
    kpi_bon2acc_score: float | None = None
    kpi_focus_score: float | None = None
    target_attainment: float | None = None
    forecast_factor: float | None = None
    kpi_bon2acc: float | None = None
    kpi_focus: float | None = None
    kpi_bon2acc_avg: float | None = None
    kpi_focus_avg: float | None = None
    nr_vizite: int | None = None
    avg_completion: float | None = None


class CrmScoreResponse(StrictApiModel):

    site_code: str
    score: float
    breakdown: CrmBreakdownResponse
    calculated_at: str | None = None
    regional: str | None = None
    asm: str | None = None
    locatie: str | None = None


class CrmAlertResponse(StrictApiModel):

    site_code: str
    score: float
    reasons: list[str] = Field(default_factory=list)
    regional: str | None = None
    asm: str | None = None
    locatie: str | None = None


class CrmRecalculateResponse(StrictApiModel):
    recalculated: int
    month: str

get_crm_service = build_crm_service


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
