from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from composition import build_campaigns_service
from schemas.common import BoundedListItem100, BoundedText120, MonthStr
from schemas.campaigns import (
    CampaignSnapshot,
    CampaignsPromotionsResponse,
    FocusHistoryResponse,
)
from services.campaigns import (
    CampaignDateRangeError,
    CampaignsService,
    validate_campaign_date_range,
)
from services.campaigns.metrics import record_campaign_request_rejected
from services.request_deadline import RequestDeadline, RequestDeadlineExceeded

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

async def get_campaigns_deadline(request: Request) -> RequestDeadline:
    """Start the Campaigns budget before pool/service resolution."""
    runtime_config = getattr(request.app.state, "runtime_config", None)
    if runtime_config is None:
        raise RuntimeError("Campaigns runtime config is unavailable before startup")
    deadline_ms = runtime_config.campaigns_request_deadline_ms
    if deadline_ms is None:
        raise RuntimeError("Campaigns deadline is unavailable outside the web process")
    return RequestDeadline(float(deadline_ms) / 1_000)


async def get_campaigns_service(
    _deadline: RequestDeadline = Depends(get_campaigns_deadline),
) -> CampaignsService:
    return await build_campaigns_service()

@router.get("/overview", response_model=CampaignSnapshot)
async def get_campaign_overview(
    month: MonthStr,
    firma: BoundedText120 | None = None,
    regional: BoundedText120 | None = None,
    asm: BoundedText120 | None = None,
    site_code: list[BoundedListItem100] | None = Query(None, max_length=100),
    agent: list[BoundedListItem100] | None = Query(None, max_length=100),
    svc: CampaignsService = Depends(get_campaigns_service),
) -> CampaignSnapshot:
    return await svc.get_campaign_overview(month, firma, regional, asm, site_code, agent)

@router.get("/history", response_model=FocusHistoryResponse)
async def get_focus_history(
    month: MonthStr,
    months_back: int = Query(12, ge=2, le=24),
    firma: BoundedText120 | None = None,
    regional: BoundedText120 | None = None,
    asm: BoundedText120 | None = None,
    site_code: list[BoundedListItem100] | None = Query(None, max_length=100),
    agent: list[BoundedListItem100] | None = Query(None, max_length=100),
    svc: CampaignsService = Depends(get_campaigns_service),
) -> FocusHistoryResponse:
    return await svc.get_focus_history(month, months_back, firma, regional, asm, site_code, agent)

@router.get("/promotions-incentives", response_model=CampaignsPromotionsResponse)
async def get_promotions_incentives(
    start_date: date = Query(...),
    end_date: date = Query(...),
    firma: BoundedText120 | None = None,
    regional: BoundedText120 | None = None,
    asm: BoundedText120 | None = None,
    site_code: list[BoundedListItem100] | None = Query(None, max_length=100),
    agent: list[BoundedListItem100] | None = Query(None, max_length=100),
    promotion_key: BoundedText120 | None = None,
    view: Literal["all", "promo", "incentive"] = "all",
    current_scope: bool = Query(False),
    include_closed_stores: bool = Query(False),
    deadline: RequestDeadline = Depends(get_campaigns_deadline),
    svc: CampaignsService = Depends(get_campaigns_service),
) -> CampaignsPromotionsResponse:
    try:
        validate_campaign_date_range(start_date, end_date)
    except CampaignDateRangeError as exc:
        record_campaign_request_rejected(exc.reason)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "reason": exc.reason},
        ) from exc
    try:
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
            deadline=deadline,
        )
    except RequestDeadlineExceeded:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Campaigns request deadline exceeded.",
        ) from None
    return CampaignsPromotionsResponse(**data)
