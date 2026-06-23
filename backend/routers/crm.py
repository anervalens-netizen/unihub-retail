from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from db.connection import get_pool
from permissions import require_business_write_access
from rate_limits import BUSINESS_WRITE_LIMIT, rate_limit
from repositories.crm import CrmRepository
from services.crm import CrmService

router = APIRouter(prefix="/api/crm", tags=["crm"])

async def get_crm_service() -> CrmService:
    pool = await get_pool()
    repo = CrmRepository(pool)
    return CrmService(repo, pool)


@router.get("/scores")
async def get_scores(
    month: str = Query(...),
    svc: CrmService = Depends(get_crm_service),
):
    return await svc.get_scores(month)


@router.post("/scores/recalculate")
async def recalculate_scores(
    month: str = Query(...),
    _claims=Depends(require_business_write_access),
    _rate_limit: None = Depends(rate_limit(BUSINESS_WRITE_LIMIT)),
    svc: CrmService = Depends(get_crm_service),
):
    recalculated_count = await svc.recalculate_scores(month)
    return {"recalculated": recalculated_count, "month": month}


@router.get("/alerts")
async def get_alerts(
    month: str = Query(...),
    svc: CrmService = Depends(get_crm_service),
):
    return await svc.get_alerts(month)
