"""Native calendar: confirmed identity and attendance, independent of POS codes."""
from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256

from fastapi import HTTPException

from business_clock import business_today
from grile.calendar_models import (
    AgentCandidate, CalendarChanges, CalendarDay,
    CalendarMonth, RosterEntry, RosterInput, StoreHours, StoreHoursInput,
)
from grile.earnings_models import EarningsMonth
from grile.earnings_projection import project_earnings
from repositories.grile_earnings import read_earnings_sources
from grile.calendar_projection import attendance_by_agent_and_store, attendance_days
from repositories.grile_calendar import CalendarConflict, GrileCalendarRepository


class GrileCalendarService:
    def __init__(self, repository: GrileCalendarRepository):
        self.repository = repository

    async def candidates(self, month: str) -> list[AgentCandidate]:
        # Preparing next month uses today's roster candidates, never future sales.
        source = min(month, business_today().strftime("%Y-%m"))
        previous = (date.fromisoformat(source + "-01") - timedelta(days=1)).strftime("%Y-%m")
        rows = await self.repository.candidates(source, previous)
        by_code: dict[str, AgentCandidate] = {}
        for row in rows:
            code = row["agent_code"]
            selected = by_code.get(code)
            if selected is None or row["import_month"] > selected.source_month:
                by_code[code] = AgentCandidate(
                    agent_code=code, source_month=row["import_month"],
                    site_codes=[row["site_code"]],
                    needs_active_confirmation=row["import_month"] != source,
                    needs_home_confirmation=False,
                )
            elif row["import_month"] == selected.source_month and row["site_code"] not in selected.site_codes:
                selected.site_codes.append(row["site_code"])
        for candidate in by_code.values():
            candidate.site_codes.sort()
            candidate.needs_home_confirmation = len(candidate.site_codes) != 1
        return sorted(by_code.values(), key=lambda item: item.agent_code)

    async def read(self, month: str) -> CalendarMonth:
        data = await self.repository.read(month)
        return self.project_calendar(month, data)

    @staticmethod
    def project_calendar(month: str, data: dict) -> CalendarMonth:
        roster = [RosterEntry.model_validate(row) for row in data["roster"]]
        days = [CalendarDay.model_validate(row) for row in data["days"]]
        hours = [StoreHours.model_validate(row) for row in data.get("store_hours", [])]
        attendance, stores = attendance_by_agent_and_store(roster, days, hours)
        result = CalendarMonth(month=month, roster=roster, days=days, attendance=attendance,
                               store_hours=hours, attendance_by_store=stores,
                               attendance_days=attendance_days(days, hours))
        result.projection_revision = sha256(result.model_dump_json().encode()).hexdigest()
        return result

    async def save_roster(self, month: str, agent_code: str, payload: RosterInput, actor: str) -> RosterEntry:
        if payload.expected_revision == 0 and payload.home_site_code != "TL":
            candidates = await self.candidates(month)
            if agent_code not in {item.agent_code for item in candidates}:
                raise HTTPException(422, "Agent code is not a current/previous month candidate")
        try:
            result = await self.repository.save_roster(
                month, agent_code, payload.home_site_code, payload.active, payload.expected_revision, actor,
                regional=payload.regional,
            )
        except CalendarConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return RosterEntry.model_validate(result)

    async def save_days(self, month: str, payload: CalendarChanges, actor: str) -> list[CalendarDay]:
        if any(day.work_date.strftime("%Y-%m") != month for day in payload.days):
            raise HTTPException(422, "Every changed day must belong to the selected month")
        try:
            rows = await self.repository.save_days(payload.days, actor)
        except CalendarConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return [CalendarDay.model_validate(row) for row in rows]

    async def save_hours(self, month: str, site_code: str, payload: StoreHoursInput, actor: str) -> StoreHours:
        try:
            row = await self.repository.save_hours(month, site_code, payload, actor)
        except CalendarConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return StoreHours.model_validate(row)

    async def export_attendance(self, month: str, expected_revision: str):
        from starlette.concurrency import run_in_threadpool
        from services.grile_attendance_export import build_attendance_zip
        data = await self.read(month)
        if data.projection_revision != expected_revision:
            raise HTTPException(409, "Calendar changed; reload before exporting")
        return await run_in_threadpool(build_attendance_zip, data)

    async def earnings(self, month: str) -> EarningsMonth:
        sources = await read_earnings_sources(self.repository.pool, month)
        calendar = self.project_calendar(month, sources["calendar"])
        return project_earnings(calendar, sources)

    async def export_earnings(self, month: str, expected_revision: str):
        from starlette.concurrency import run_in_threadpool
        from services.grile_earnings_export import build_earnings_zip
        sources = await read_earnings_sources(self.repository.pool, month)
        calendar = self.project_calendar(month, sources['calendar'])
        earnings = project_earnings(calendar, sources)
        if earnings.projection_revision != expected_revision:
            raise HTTPException(409, 'Earnings changed; reload before exporting')
        return await run_in_threadpool(build_earnings_zip, calendar, earnings)

    async def save_compensation(self, month, agent, payload, actor):
        from grile.compensation_models import CompensationEntry
        from repositories.grile_compensation import save_compensation
        try:
            row = await save_compensation(self.repository.pool, month, agent, payload, actor)
        except CalendarConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return CompensationEntry.model_validate(dict(row))
