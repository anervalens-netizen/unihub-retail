from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from db.connection import get_pool
from permissions import require_business_write_access
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
    svc: CrmService = Depends(get_crm_service),
    _claims=Depends(require_business_write_access),
):
    recalculated_count = await svc.recalculate_scores(month)
    return {"recalculated": recalculated_count, "month": month}


@router.get("/alerts")
async def get_alerts(
    month: str = Query(...),
    svc: CrmService = Depends(get_crm_service),
):
    return await svc.get_alerts(month)
