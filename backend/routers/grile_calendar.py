from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import AuthClaims
from composition import build_grile_calendar_service
from grile.calendar_models import (
    AgentCandidate, CalendarChanges, CalendarDay, CalendarMonth, CalendarMonthKey, Code, RosterEntry, RosterInput,
)
from permissions import require_business_write_access, require_management_access
from rate_limits import BUSINESS_WRITE_LIMIT, rate_limit
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
