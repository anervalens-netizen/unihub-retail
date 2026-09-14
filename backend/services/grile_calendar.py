"""Native calendar: confirmed identity and attendance, independent of POS codes."""
from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256

from fastapi import HTTPException

from business_clock import business_today
from grile.calendar_models import (
    AgentCandidate, CalendarChanges, CalendarClosure, CalendarDay,
    CalendarMonth, RosterEntry, RosterInput, StoreHours, StoreHoursInput,
)
from grile.earnings_models import EarningsMonth
from grile.earnings_projection import project_earnings
from repositories.grile_earnings import read_earnings_sources
from services.grile_incentives import read_incentives
from grile.calendar_projection import attendance_by_agent_and_store, attendance_days, project_calendar as _project_calendar
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
                    agent_code=code, display_name=row.get("display_name"), source_month=row["import_month"],
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
        return _project_calendar(month, data)

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

    async def save_transfer(self, month, agent_code, payload, actor):
        from repositories.grile_transfers import save_transfer
        if payload.effective_from.strftime("%Y-%m") != month:
            raise HTTPException(422, "Transfer date must belong to the selected month")
        try:
            data = await save_transfer(self.repository.pool, month, agent_code, payload, actor)
        except CalendarConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return self.project_calendar(month, data)

    async def save_store_team(self, month, site, payload, actor):
        from repositories.grile_store_team import save_store_team
        if payload.effective_from.strftime('%Y-%m') != month:
            raise HTTPException(422, 'Allocation date must belong to the selected month')
        candidates = {c.agent_code for c in await self.candidates(month)}
        try:
            data = await save_store_team(self.repository.pool, month, site, payload, actor, candidates)
        except CalendarConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return self.project_calendar(month, data)

    async def save_days(self, month: str, payload: CalendarChanges, actor: str) -> list[CalendarDay]:
        if any(day.work_date.strftime("%Y-%m") != month for day in payload.days) or any(c.work_date.strftime("%Y-%m") != month for c in payload.closures):
            raise HTTPException(422, "Every changed day must belong to the selected month")
        try:
            rows = await self.repository.save_days(payload.days, actor, payload.closures) if payload.days else []
            if payload.closures and not payload.days:
                await self.repository.save_closures(payload.closures, actor)
        except CalendarConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return [CalendarDay.model_validate(row) for row in rows]

    async def save_closures(self, month, payload, actor):
        if any(c.work_date.strftime('%Y-%m') != month for c in payload.closures):
            raise HTTPException(422, "Every closed day must belong to the selected month")
        try:
            rows = await self.repository.save_closures(payload.closures, actor)
        except CalendarConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return rows

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
        sources = await read_earnings_sources(self.repository.pool, month, incentive_reader=read_incentives)
        calendar = self.project_calendar(month, sources["calendar"])
        return project_earnings(calendar, sources)

    async def export_earnings(self, month: str, expected_revision: str):
        from starlette.concurrency import run_in_threadpool
        from services.grile_earnings_export import build_earnings_zip
        sources = await read_earnings_sources(self.repository.pool, month, incentive_reader=read_incentives)
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


    async def save_target(self, month, agent, payload, actor):
        from grile.target_models import AgentTargetEntry
        from repositories.grile_target_settings import save_target
        try:
            row = await save_target(self.repository.pool, month, agent, payload, actor)
        except CalendarConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return AgentTargetEntry.model_validate(row)

    async def save_epay(self, month, agent, payload, actor):
        from grile.compensation_models import CompensationEntry
        from repositories.grile_compensation import save_epay
        try:
            row = await save_epay(self.repository.pool, month, agent, payload, actor)
        except CalendarConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return CompensationEntry.model_validate(dict(row))
