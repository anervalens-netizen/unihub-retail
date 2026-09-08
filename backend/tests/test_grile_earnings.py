"""Reconcile two stores and one supplemental person without POS-name matching."""
from datetime import date
from decimal import Decimal as D

import pytest

from grile.earnings_projection import project_earnings
from grile.earnings_rules import daily_commission, monthly_commission, whole_ron
from services.grile_calendar import GrileCalendarService


def sources():
    roster = [dict(month="2026-09", agent_code=agent, home_site_code=home, active=True, revision=1)
              for agent, home in [("AG1", "A"), ("AG2", "A"), ("SUP", "B")]]
    schedule = [("AG1", "A", 1, "800"), ("AG1", "A", 2, "800"), ("AG2", "A", 3, "1200"),
                ("SUP", "B", 1, "1000"), ("SUP", "B", 2, "1200"), ("AG1", "B", 3, "790")]
    days = [dict(agent_code=agent, site_code=site, work_date=date(2026, 9, number),
                 status="work", supplemental=agent == "AG1" and site == "B", revision=1)
            for agent, site, number, _ in schedule]
    sales = [dict(site_code=site, sale_date=date(2026, 9, number), sales=D(value))
             for _, site, number, value in schedule]
    return dict(calendar=dict(roster=roster, days=days, store_hours=[]), sales=sales,
                targets=[dict(site_code=site, target_value=D(3000)) for site in ["A", "B"]],
                source=dict(snapshot_id=1, revision=1, cutoff_date=date(2026, 9, 3)))


def project(data):
    return project_earnings(GrileCalendarService.project_calendar("2026-09", data["calendar"]), data)


@pytest.mark.parametrize("sales,expected", [("799.99", "0"), ("800", "24"), ("999.99", "30"),
                                           ("1000", "230"), ("1199.99", "236"), ("1200", "436")])
def test_monthly_boundaries(sales, expected):
    assert monthly_commission(D(sales), D(1000)) == D(expected)


@pytest.mark.parametrize("sales,expected", [("789.99", "0"), ("790", "24"), ("800", "24"), ("-10", "0")])
def test_daily_79_inclusive_is_distinct(sales, expected):
    assert daily_commission(D(sales), D(1000)) == D(expected)


def test_rounding_and_fractional_divisor_do_not_shift_thresholds():
    assert whole_ron(D("22.5")) == 23
    assert whole_ron(D("-22.5")) == -23
    assert daily_commission(D(79), D(300), 3) == 2
    assert monthly_commission(D(100), D(300), 3) == 203
    assert monthly_commission(D(1), D(0)) is None
    assert daily_commission(D(1), D(-1)) is None


def test_two_stores_supplemental_reconciles_person_and_physical_sales():
    result = project(sources())
    agents = {row.agent_code: row for row in result.agents}
    assert set(agents) == {"AG1", "AG2", "SUP"}
    assert result.selling_days == {"A": 3, "B": 3}
    agent = agents["AG1"]
    assert (agent.home_target, agent.home_sales, agent.home_commission) == (2000, 1600, 48)
    assert (agent.away_commission, agent.supplemental_pay, agent.known_earnings) == (24, 150, 222)
    assert agents["AG2"].home_commission == 436
    assert agents["SUP"].home_commission == 266
    assert sum(day.sales for row in result.agents for day in row.days) == 5790
    assert result.unassigned_sales == []
    assert result.status == "provisional"
    assert "salary_base" in result.unavailable_components


def test_missing_is_not_zero_and_absence_does_not_earn():
    data = sources()
    data["sales"][0]["sales"] = D(0)
    zero = project(data).agents[0]
    assert zero.home_sales == 800 and zero.home_commission == 0
    data["sales"].pop(0)
    missing = project(data).agents[0]
    assert missing.home_sales is None and missing.known_earnings is None
    assert missing.issues == ["missing_sales"]
    data["calendar"]["days"][0]["status"] = "leave"
    leave = project(data).agents[0]
    assert leave.home_work_days == 1
    assert len(leave.days) == 2


def test_cutoff_and_missing_target_remain_explicit():
    data = sources()
    data["source"]["cutoff_date"] = date(2026, 9, 2)
    agent = project(data).agents[0]
    assert agent.home_target == 2000
    assert agent.supplemental_pay == 0 and agent.away_commission == 0
    assert agent.days[-1].issue == "after_cutoff"
    data["targets"].pop(0)
    assert project(data).agents[0].home_commission is None
    data["source"] = None
    assert project(data).agents[0].known_earnings is None


def test_reassignment_and_hash_include_sales_targets_and_calendar():
    data = sources()
    original = project(data)
    data["sales"][0]["sales"] += 1
    sales_changed = project(data)
    assert original.projection_revision != sales_changed.projection_revision
    assert original.calendar_revision == sales_changed.calendar_revision
    data["targets"][0]["target_value"] += 1
    target_changed = project(data)
    assert sales_changed.projection_revision != target_changed.projection_revision
    data["calendar"]["days"][-1]["agent_code"] = "AG2"
    changed = project(data)
    assert changed.calendar_revision != original.calendar_revision
    assert changed.agents[0].away_commission == 0
    assert changed.agents[1].away_commission == 24
    assert sum(day.sales for row in changed.agents for day in row.days) == 5791


def test_away_commission_rounds_each_day_before_sum_and_own_supplement_is_monthly():
    data = sources()
    data["calendar"]["days"][-2].update(agent_code="AG1", supplemental=True)
    data["sales"][-2]["sales"] = D("790")
    agent = project(data).agents[0]
    assert agent.away_commission == 48  # ROUND(23.7) + ROUND(23.7), not ROUND(47.4).
    assert agent.supplemental_pay == 300
    data["calendar"]["days"][0]["supplemental"] = True
    own = project(data).agents[0]
    assert own.home_commission == 48 and own.away_commission == 48
    assert own.supplemental_pay == 450


def test_cancelled_work_keeps_physical_sales_unassigned():
    data = sources()
    data["calendar"]["days"][-1].update(status="cancelled", supplemental=False)
    result = project(data)
    assert result.agents[0].supplemental_pay == 0
    assert [row.model_dump() for row in result.unassigned_sales] == [data["sales"][-1]]
