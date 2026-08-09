from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from composition import build_dashboard_service
from schemas.dashboard import (
    DailySalesPoint,
    DashboardAllBatchRequest,
    DashboardAllBatchResponse,
    DashboardAllResponse,
    DashboardHistoryResponse,
    DashboardSpecialCardsResponse,
    DashboardSummary,
    PerformanceDetailResponse,
    YearHistoryResponse,
)
from schemas.premium_glass import PremiumGlassAnalysis
from schemas.common import MonthStr
from services.dashboard_filters import canonical_dashboard_site_codes
from services.dashboard_service import DashboardService
from services.request_deadline import RequestDeadline, RequestDeadlineExceeded


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


async def get_dashboard_deadline(request: Request) -> RequestDeadline:
    """Start the immutable request budget before resolving Dashboard resources."""
    runtime_config = getattr(request.app.state, "runtime_config", None)
    if runtime_config is None:
        raise RuntimeError("Dashboard runtime config is unavailable before startup")
    return RequestDeadline.from_runtime_config(runtime_config)


async def get_dashboard_service(
    request: Request,
    _deadline: RequestDeadline = Depends(get_dashboard_deadline),
) -> DashboardService:
    return await build_dashboard_service(request.app.state.runtime_config)


async def _run_dashboard(
    deadline: RequestDeadline,
    operation: Callable[[RequestDeadline], Awaitable[Any]],
) -> Any:
    try:
        return await deadline.run(operation(deadline))
    except RequestDeadlineExceeded:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Dashboard request deadline exceeded.",
        ) from None


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    month: MonthStr = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    deadline: RequestDeadline = Depends(get_dashboard_deadline),
    svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardSummary:
    site_code = canonical_dashboard_site_codes(site_code)
    return await _run_dashboard(
        deadline,
        lambda _deadline: svc.get_summary(
            month, firma, regional, asm, site_code, agent, deadline=deadline
        )
    )


@router.get("/all", response_model=DashboardAllResponse)
async def get_dashboard_all(
    month: MonthStr = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    current_scope: bool = Query(False),
    include_closed_stores: bool = Query(False),
    deadline: RequestDeadline = Depends(get_dashboard_deadline),
    svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardAllResponse:
    site_code = canonical_dashboard_site_codes(site_code)
    return await _run_dashboard(
        deadline,
        lambda _deadline: svc.get_dashboard_all(
            month,
            firma,
            regional,
            asm,
            site_code,
            agent,
            current_scope,
            include_closed_stores,
            deadline=deadline,
        )
    )


@router.post("/all-batch", response_model=DashboardAllBatchResponse)
async def get_dashboard_all_batch(
    request: DashboardAllBatchRequest,
    deadline: RequestDeadline = Depends(get_dashboard_deadline),
    svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardAllBatchResponse:
    return await _run_dashboard(
        deadline,
        lambda _deadline: svc.get_dashboard_all_batch(request.queries, deadline=deadline)
    )


@router.post("/history-details-batch", response_model=DashboardAllBatchResponse)
async def get_dashboard_history_details_batch(
    request: DashboardAllBatchRequest,
    deadline: RequestDeadline = Depends(get_dashboard_deadline),
    svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardAllBatchResponse:
    return await _run_dashboard(
        deadline,
        lambda _deadline: svc.get_dashboard_history_details_batch(
            request.queries,
            deadline=deadline,
        )
    )


@router.get("/daily", response_model=list[DailySalesPoint])
async def get_daily_sales(
    month: MonthStr = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    deadline: RequestDeadline = Depends(get_dashboard_deadline),
    svc: DashboardService = Depends(get_dashboard_service),
) -> list[DailySalesPoint]:
    site_code = canonical_dashboard_site_codes(site_code)
    return await _run_dashboard(
        deadline,
        lambda _deadline: svc.get_daily_sales(
            month, firma, regional, asm, site_code, agent, deadline=deadline
        )
    )


@router.get("/special-cards", response_model=DashboardSpecialCardsResponse)
async def get_special_cards(
    month: MonthStr = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    deadline: RequestDeadline = Depends(get_dashboard_deadline),
    svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardSpecialCardsResponse:
    site_code = canonical_dashboard_site_codes(site_code)
    return await _run_dashboard(
        deadline,
        lambda _deadline: svc.get_special_cards(
            month, firma, regional, asm, site_code, agent, deadline=deadline
        )
    )


@router.get("/premium-glass", response_model=PremiumGlassAnalysis)
async def get_premium_glass(
    month: MonthStr = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    surface: Literal["all", "screen", "camera"] = Query("all"),
    current_scope: bool = Query(True),
    include_closed_stores: bool = Query(False),
    deadline: RequestDeadline = Depends(get_dashboard_deadline),
    svc: DashboardService = Depends(get_dashboard_service),
) -> PremiumGlassAnalysis:
    site_code = canonical_dashboard_site_codes(site_code)
    return await _run_dashboard(
        deadline,
        lambda _deadline: svc.get_premium_glass(
            month,
            firma,
            regional,
            asm,
            site_code,
            agent,
            surface,
            current_scope,
            include_closed_stores,
            deadline=deadline,
        )
    )


@router.get("/history", response_model=DashboardHistoryResponse)
async def get_monthly_history(
    month: MonthStr = Query(...),
    months_back: int = Query(12, ge=2, le=24),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    current_scope: bool = Query(True),
    include_closed_stores: bool = Query(False),
    deadline: RequestDeadline = Depends(get_dashboard_deadline),
    svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardHistoryResponse:
    site_code = canonical_dashboard_site_codes(site_code)
    return await _run_dashboard(
        deadline,
        lambda _deadline: svc.get_monthly_history(
            month,
            months_back,
            firma,
            regional,
            asm,
            site_code,
            agent,
            current_scope,
            include_closed_stores,
            deadline=deadline,
        )
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
    deadline: RequestDeadline = Depends(get_dashboard_deadline),
    svc: DashboardService = Depends(get_dashboard_service),
) -> YearHistoryResponse:
    site_code = canonical_dashboard_site_codes(site_code)
    return await _run_dashboard(
        deadline,
        lambda _deadline: svc.get_history_by_year(
            year,
            firma,
            regional,
            asm,
            site_code,
            agent,
            current_scope,
            include_closed_stores,
            deadline=deadline,
        )
    )


@router.get("/performance-detail", response_model=PerformanceDetailResponse)
async def get_performance_detail(
    month: MonthStr = Query(...),
    level: Literal["regional", "store", "agent"] = Query(...),
    key: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    current_scope: bool = Query(True),
    include_closed_stores: bool = Query(False),
    deadline: RequestDeadline = Depends(get_dashboard_deadline),
    svc: DashboardService = Depends(get_dashboard_service),
) -> PerformanceDetailResponse:
    site_code = canonical_dashboard_site_codes(site_code)
    performance_key: str | None = key
    if level == "store":
        performance_key = canonical_dashboard_site_codes(key)
    return await _run_dashboard(
        deadline,
        lambda _deadline: svc.get_performance_detail(
            month,
            level,
            performance_key,
            firma,
            regional,
            asm,
            site_code,
            agent,
            current_scope,
            include_closed_stores,
            deadline=deadline,
        )
    )
