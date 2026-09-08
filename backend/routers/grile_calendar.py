from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from auth import AuthClaims
from composition import build_grile_calendar_service
from grile.calendar_models import (
    AgentCandidate, CalendarChanges, CalendarDay, CalendarMonth, CalendarMonthKey, Code, RosterEntry, RosterInput, StoreHours, StoreHoursInput,
)
from grile.earnings_models import EarningsMonth
from permissions import require_business_write_access, require_management_access
from rate_limits import BUSINESS_WRITE_LIMIT, REPORT_EXPORT_LIMIT, rate_limit
from services.grile_calendar import GrileCalendarService

router = APIRouter(prefix="/api/grile/calendar", tags=["grile-calendar"])


@router.get("/{month}/candidates", response_model=list[AgentCandidate])
async def candidates(
    month: CalendarMonthKey,
    _claims: AuthClaims = Depends(require_management_access),
    svc: GrileCalendarService = Depends(build_grile_calendar_service),
) -> list[AgentCandidate]:
    return await svc.candidates(month)


@router.get("/{month}", response_model=CalendarMonth)
async def read_calendar(
    month: CalendarMonthKey,
    _claims: AuthClaims = Depends(require_management_access),
    svc: GrileCalendarService = Depends(build_grile_calendar_service),
) -> CalendarMonth:
    return await svc.read(month)


@router.put("/{month}/roster/{agent_code}", response_model=RosterEntry)
async def save_roster(
    month: CalendarMonthKey, agent_code: Code, payload: RosterInput,
    claims: AuthClaims = Depends(require_business_write_access),
    _limit: None = Depends(rate_limit(BUSINESS_WRITE_LIMIT)),
    svc: GrileCalendarService = Depends(build_grile_calendar_service),
) -> RosterEntry:
    return await svc.save_roster(month, agent_code, payload, claims.sub)


@router.patch("/{month}/days", response_model=list[CalendarDay])
async def save_days(
    month: CalendarMonthKey, payload: CalendarChanges,
    claims: AuthClaims = Depends(require_business_write_access),
    _limit: None = Depends(rate_limit(BUSINESS_WRITE_LIMIT)),
    svc: GrileCalendarService = Depends(build_grile_calendar_service),
) -> list[CalendarDay]:
    return await svc.save_days(month, payload, claims.sub)


@router.put("/{month}/store-hours/{site_code}", response_model=StoreHours)
async def save_store_hours(
    month: CalendarMonthKey, site_code: Code, payload: StoreHoursInput,
    claims: AuthClaims = Depends(require_business_write_access),
    _limit: None = Depends(rate_limit(BUSINESS_WRITE_LIMIT)),
    svc: GrileCalendarService = Depends(build_grile_calendar_service),
) -> StoreHours:
    return await svc.save_hours(month, site_code, payload, claims.sub)


@router.get(
    "/{month}/attendance.zip", response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}}},
)
async def export_attendance(
    month: CalendarMonthKey,
    expected_revision: str = Query(pattern="^[a-f0-9]{64}$"),
    _claims: AuthClaims = Depends(require_management_access),
    _limit: None = Depends(rate_limit(REPORT_EXPORT_LIMIT)),
    svc: GrileCalendarService = Depends(build_grile_calendar_service),
):
    artifact = await svc.export_attendance(month, expected_revision)
    return StreamingResponse(artifact.iter_chunks(), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
                             background=BackgroundTask(artifact.close))


@router.get("/{month}/earnings", response_model=EarningsMonth)
async def read_earnings(
    month: CalendarMonthKey,
    _claims: AuthClaims = Depends(require_management_access),
    svc: GrileCalendarService = Depends(build_grile_calendar_service),
) -> EarningsMonth:
    return await svc.earnings(month)


@router.get(
    "/{month}/earnings.zip", response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}}},
)
async def export_earnings(
    month: CalendarMonthKey,
    expected_revision: str = Query(pattern="^[a-f0-9]{64}$"),
    _claims: AuthClaims = Depends(require_management_access),
    _limit: None = Depends(rate_limit(REPORT_EXPORT_LIMIT)),
    svc: GrileCalendarService = Depends(build_grile_calendar_service),
):
    artifact = await svc.export_earnings(month, expected_revision)
    return StreamingResponse(artifact.iter_chunks(), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
                             background=BackgroundTask(artifact.close))
