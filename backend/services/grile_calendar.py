"""Native calendar: confirmed identity and attendance, independent of POS codes."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException

from business_clock import business_today
from grile.calendar_models import (
    AgentCandidate, CalendarAttendance, CalendarChanges, CalendarDay,
    CalendarMonth, RosterEntry, RosterInput,
)
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
        roster = [RosterEntry.model_validate(row) for row in data["roster"]]
        days = [CalendarDay.model_validate(row) for row in data["days"]]
        attendance = {row.agent_code: CalendarAttendance(agent_code=row.agent_code) for row in roster}
        for day in days:
            entry = attendance[day.agent_code]
            if day.status == "work":
                entry.work_days += 1
                entry.work_days_by_site[day.site_code] = entry.work_days_by_site.get(day.site_code, 0) + 1
            elif day.status == "leave":
                entry.leave_days += 1
            elif day.status == "off":
                entry.off_days += 1
        return CalendarMonth(month=month, roster=roster, days=days, attendance=list(attendance.values()))

    async def save_roster(self, month: str, agent_code: str, payload: RosterInput, actor: str) -> RosterEntry:
        if payload.expected_revision == 0:
            candidates = await self.candidates(month)
            if agent_code not in {item.agent_code for item in candidates}:
                raise HTTPException(422, "Agent code is not a current/previous month candidate")
        try:
            result = await self.repository.save_roster(
                month, agent_code, payload.home_site_code, payload.active, payload.expected_revision, actor,
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
