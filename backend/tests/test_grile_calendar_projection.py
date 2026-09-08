from datetime import date

from grile.calendar_models import CalendarDay, RosterEntry
from grile.calendar_projection import attendance_by_agent_and_store


def test_person_totals_equal_store_totals_without_counting_cancelled_days():
    roster = [RosterEntry(month="2026-09", agent_code="AG1", home_site_code="A", active=True, revision=1)]
    days = [CalendarDay(work_date=date(2026, 9, number), agent_code="AG1", site_code=site,
                        status=status, supplemental=supplemental, revision=2)
            for number, site, status, supplemental in [
                (1, "A", "work", False), (2, "B", "work", True),
                (3, "C", "work", True), (4, "A", "leave", False),
                (5, "A", "off", False), (6, "B", "cancelled", False),
            ]]
    agents, stores = attendance_by_agent_and_store(roster, days)
    assert agents[0].work_days == 3
    assert agents[0].work_days_by_site == {"A": 1, "B": 1, "C": 1}
    assert agents[0].leave_days == agents[0].off_days == 1
    for attribute in ("work_days", "leave_days", "off_days"):
        assert getattr(agents[0], attribute) == sum(getattr(rows[0], attribute) for rows in stores.values())
    assert stores["B"][0].work_days == 1
    assert attendance_by_agent_and_store(roster, list(reversed(days))) == (agents, stores)


def test_roster_without_days_is_explicitly_empty_and_not_assigned_to_home():
    roster = [RosterEntry(month="2026-09", agent_code="AG1", home_site_code="A", active=True, revision=1)]
    agents, stores = attendance_by_agent_and_store(roster, [])
    assert agents[0].work_days == 0
    assert stores == {}
