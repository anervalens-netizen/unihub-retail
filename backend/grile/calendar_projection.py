"""One attendance aggregation for calendar, store views and future exports."""
from __future__ import annotations

from grile.calendar_models import AttendanceDay, CalendarAttendance, CalendarDay, RosterEntry, StoreHours


def attendance_by_agent_and_store(
    roster: list[RosterEntry], days: list[CalendarDay], hours: list[StoreHours] | None = None,
) -> tuple[list[CalendarAttendance], dict[str, list[CalendarAttendance]]]:
    """Count each confirmed person/day once, at its recorded store only.

    Worked minutes follow the actual store schedule; no salary is calculated.
    Cancelled rows retain revision history but do not contribute attendance.
    """
    settings = {row.site_code: row for row in (hours or [])}
    agents = {row.agent_code: CalendarAttendance(agent_code=row.agent_code) for row in roster}
    stores: dict[str, dict[str, CalendarAttendance]] = {}
    for day in days:
        if day.status == "cancelled":
            continue
        agent = agents[day.agent_code]
        store = stores.setdefault(day.site_code, {})
        local = store.setdefault(day.agent_code, CalendarAttendance(agent_code=day.agent_code))
        for entry in (agent, local):
            if day.status == "work":
                entry.worked_minutes += settings.get(day.site_code, StoreHours(site_code=day.site_code)).net_minutes
                entry.work_days += 1
                entry.work_days_by_site[day.site_code] = entry.work_days_by_site.get(day.site_code, 0) + 1
            elif day.status == "leave":
                entry.leave_days += 1
            elif day.status == "off":
                entry.off_days += 1
    return (
        [agents[code] for code in sorted(agents)],
        {site: [rows[code] for code in sorted(rows)] for site, rows in sorted(stores.items())},
    )


def attendance_days(days: list[CalendarDay], hours: list[StoreHours]) -> list[AttendanceDay]:
    settings = {row.site_code: row for row in hours}
    result = []
    for day in days:
        if day.status == "cancelled":
            continue
        schedule = settings.get(day.site_code, StoreHours(site_code=day.site_code))
        working = day.status == "work"
        result.append(AttendanceDay(
            work_date=day.work_date, agent_code=day.agent_code, site_code=day.site_code,
            status=day.status, worked_minutes=schedule.net_minutes if working else 0,
            opens=schedule.opens if working else None, closes=schedule.closes if working else None,
            break_minutes=schedule.break_minutes if working else 0,
        ))
    return result
