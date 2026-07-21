from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from db.connection import get_pool
from schemas.dashboard import (
    DailySalesPoint,
    DashboardAllBatchRequest,
    DashboardAllBatchResponse,
    DashboardAllResponse,
    DashboardHistoryResponse,
    PerformanceDetailResponse,
    DashboardSpecialCardsResponse,
    DashboardSummary,
    YearHistoryResponse,
)
from schemas.premium_glass import PremiumGlassAnalysis
from repositories.dashboard import DashboardRepository
from services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

async def get_dashboard_service() -> DashboardService:
    pool = await get_pool()
    repo = DashboardRepository(pool)
    return DashboardService(repo, pool)

@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardSummary:
    return await svc.get_summary(month, firma, regional, asm, site_code, agent)

@router.get("/all", response_model=DashboardAllResponse)
async def get_dashboard_all(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    current_scope: bool = Query(False),
    include_closed_stores: bool = Query(False),
    svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardAllResponse:
    return await svc.get_dashboard_all(
        month, firma, regional, asm, site_code, agent, current_scope, include_closed_stores
    )


@router.post("/all-batch", response_model=DashboardAllBatchResponse)
async def get_dashboard_all_batch(
    request: DashboardAllBatchRequest,
    svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardAllBatchResponse:
    return await svc.get_dashboard_all_batch(request.queries)


@router.post("/history-details-batch", response_model=DashboardAllBatchResponse)
async def get_dashboard_history_details_batch(
    request: DashboardAllBatchRequest,
    svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardAllBatchResponse:
    return await svc.get_dashboard_history_details_batch(request.queries)

@router.get("/daily", response_model=list[DailySalesPoint])
async def get_daily_sales(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    svc: DashboardService = Depends(get_dashboard_service),
) -> list[DailySalesPoint]:
    return await svc.get_daily_sales(month, firma, regional, asm, site_code, agent)

@router.get("/special-cards", response_model=DashboardSpecialCardsResponse)
async def get_special_cards(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardSpecialCardsResponse:
    return await svc.get_special_cards(month, firma, regional, asm, site_code, agent)

@router.get("/premium-glass", response_model=PremiumGlassAnalysis)
async def get_premium_glass(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    surface: Literal["all", "screen", "camera"] = Query("all"),
    current_scope: bool = Query(True),
    include_closed_stores: bool = Query(False),
    svc: DashboardService = Depends(get_dashboard_service),
) -> PremiumGlassAnalysis:
    return await svc.get_premium_glass(
        month,
        firma,
        regional,
        asm,
        site_code,
        agent,
        surface,
        current_scope,
        include_closed_stores,
    )

@router.get("/history", response_model=DashboardHistoryResponse)
async def get_monthly_history(
    month: str = Query(...),
    months_back: int = Query(12, ge=2, le=24),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    current_scope: bool = Query(True),
    include_closed_stores: bool = Query(False),
    svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardHistoryResponse:
    return await svc.get_monthly_history(
        month,
        months_back,
        firma,
        regional,
        asm,
        site_code,
        agent,
        current_scope,
        include_closed_stores,
    )

@router.get("/history-year", response_model=YearHistoryResponse)
async def get_history_by_year(
    year: int = Query(..., ge=2018, le=2030),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    current_scope: bool = Query(True),
    include_closed_stores: bool = Query(False),
    svc: DashboardService = Depends(get_dashboard_service),
) -> YearHistoryResponse:
    return await svc.get_history_by_year(
        year, firma, regional, asm, site_code, agent, current_scope, include_closed_stores
    )


@router.get("/performance-detail", response_model=PerformanceDetailResponse)
async def get_performance_detail(
    month: str = Query(...),
    level: Literal["regional", "store", "agent"] = Query(...),
    key: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    current_scope: bool = Query(True),
    include_closed_stores: bool = Query(False),
    svc: DashboardService = Depends(get_dashboard_service),
) -> PerformanceDetailResponse:
    return await svc.get_performance_detail(
        month,
        level,
        key,
        firma,
        regional,
        asm,
        site_code,
        agent,
        current_scope,
        include_closed_stores,
    )
