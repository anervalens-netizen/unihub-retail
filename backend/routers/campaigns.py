from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from db.connection import get_pool
from schemas.campaigns import (
    CampaignSnapshot,
    CampaignsPromotionsResponse,
    FocusHistoryResponse,
)
from repositories.campaigns import CampaignsRepository
from services.campaigns import CampaignsService

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

async def get_campaigns_service() -> CampaignsService:
    pool = await get_pool()
    repo = CampaignsRepository(pool)
    return CampaignsService(repo, pool)

@router.get("/overview", response_model=CampaignSnapshot)
async def get_campaign_overview(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    svc: CampaignsService = Depends(get_campaigns_service),
) -> CampaignSnapshot:
    return await svc.get_campaign_overview(month, firma, regional, asm, site_code, agent)

@router.get("/history", response_model=FocusHistoryResponse)
async def get_focus_history(
    month: str = Query(...),
    months_back: int = Query(12, ge=2, le=24),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    svc: CampaignsService = Depends(get_campaigns_service),
) -> FocusHistoryResponse:
    return await svc.get_focus_history(month, months_back, firma, regional, asm, site_code, agent)

@router.get("/promotions-incentives", response_model=CampaignsPromotionsResponse)
async def get_promotions_incentives(
    start_date: str = Query(...),
    end_date: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    promotion_key: str | None = None,
    view: Literal["all", "promo", "incentive"] = "all",
    current_scope: bool = Query(False),
    include_closed_stores: bool = Query(False),
    svc: CampaignsService = Depends(get_campaigns_service),
) -> CampaignsPromotionsResponse:
    data = await svc.get_promotions_incentives(
        start_date,
        end_date,
        firma,
        regional,
        asm,
        site_code,
        agent,
        promotion_key,
        view,
        current_scope,
        include_closed_stores,
    )
    return CampaignsPromotionsResponse(**data)
