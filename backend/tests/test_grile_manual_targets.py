"""Characterization tests for monthly Grile agent target overrides.

These tests deliberately exercise the same two-store/supplemental shape as
``test_grile_earnings.py`` while keeping the target source explicit.  The
manual setting is per (month, agent); a resolved target row is per
(month, site, agent).
"""

from datetime import date
from decimal import Decimal as D

import pytest

from grile.earnings_projection import project_earnings
from services.grile_calendar import GrileCalendarService
from grile.target_models import AgentTargetInput
from services.grile_calendar import GrileCalendarService


MONTH = "2026-09"


def _sources() -> dict:
    roster = [
        dict(month=MONTH, agent_code=agent, home_site_code=home, active=True, revision=1)
        for agent, home in [("AG1", "A"), ("AG2", "A"), ("SUP", "B")]
    ]
    schedule = [
        ("AG1", "A", 1, "800"),
        ("AG1", "A", 2, "800"),
        ("AG2", "A", 3, "1200"),
        ("SUP", "B", 1, "1000"),
        ("SUP", "B", 2, "1200"),
        ("AG1", "B", 3, "790"),
    ]
    days = [
        dict(
            agent_code=agent,
            site_code=site,
            work_date=date(2026, 9, number),
            status="work",
            supplemental=agent == "AG1" and site == "B",
            revision=1,
        )
        for agent, site, number, _ in schedule
    ]
    sales = [
        dict(site_code=site, sale_date=date(2026, 9, number), sales=D(value))
        for _, site, number, value in schedule
    ]
    return {
        "calendar": dict(roster=roster, days=days, store_hours=[]),
        "sales": sales,
        "targets": [
            dict(site_code=site, target_value=D(3000)) for site in ["A", "B"]
        ],
        "source": dict(cutoff_date=date(2026, 9, 3)),
        "target_settings": [],
        "agent_target_rows": [],
    }


def _project(sources: dict):
    calendar = GrileCalendarService.project_calendar(MONTH, sources["calendar"])
    return project_earnings(calendar, sources)


def _agent(result, code: str):
    return next(row for row in result.agents if row.agent_code == code)


def test_manual_target_updates_target_progress_commission_and_daily_metrics():
    automatic = _project(_sources())
    auto = _agent(automatic, "AG1")

    assert auto.home_target == D(2000)
    assert auto.home_commission == D(48)
    assert auto.performance is not None
    assert auto.performance.target == D(2000)
    assert auto.performance.progress == D(80)
    assert auto.performance.average == D(800)
    assert auto.performance.daily_100 is None

    manual_sources = _sources()
    manual_sources["target_settings"] = [
        {
            "month": MONTH,
            "agent_code": "AG1",
            "mode": "manual",
            "manual_target": D(1500),
            "revision": 1,
        }
    ]
    manual = _project(manual_sources)
    overridden = _agent(manual, "AG1")

    assert overridden.target_setting.mode == "manual"
    assert overridden.target_setting.manual_target == D(1500)
    assert overridden.home_target == D(1500)
    assert overridden.home_commission == D(248)
    assert overridden.performance is not None
    assert overridden.performance.target == D(1500)
    assert overridden.performance.progress.quantize(D("0.01")) == D("106.67")
    assert overridden.performance.average == D(800)
    assert overridden.performance.daily_100 is None


def test_manual_target_updates_daily_thresholds_when_days_remain():
    automatic_sources = _sources()
    automatic_sources["source"]["cutoff_date"] = date(2026, 9, 1)
    automatic = _project(automatic_sources)

    manual_sources = _sources()
    manual_sources["source"]["cutoff_date"] = date(2026, 9, 1)
    manual_sources["target_settings"] = [
        {
            "month": MONTH,
            "agent_code": "AG1",
            "mode": "manual",
            "manual_target": D(1500),
            "revision": 1,
        }
    ]
    manual = _project(manual_sources)

    assert _agent(automatic, "AG1").performance.daily_100 == D(1200)
    assert _agent(manual, "AG1").performance.daily_100 == D(700)


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "manual", "manual_target": None, "expected_revision": 0},
        {"mode": "manual", "manual_target": D(0), "expected_revision": 0},
        {"mode": "manual", "manual_target": D("-1"), "expected_revision": 0},
        {"mode": "manual", "manual_target": D("1000000.01"), "expected_revision": 0},
        {"mode": "manual", "manual_target": D("1500.001"), "expected_revision": 0},
        {"mode": "automatic", "manual_target": D("1500"), "expected_revision": 0},
    ],
)
def test_agent_target_input_rejects_invalid_manual_choices(payload):
    with pytest.raises(ValueError):
        AgentTargetInput(**payload)


def test_agent_target_input_accepts_positive_manual_target():
    value = AgentTargetInput(
        mode="manual", manual_target=D("1500.00"), expected_revision=0
    )
    assert value.manual_target == D("1500.00")


def test_agent_target_input_accepts_automatic_without_manual_sum():
    value = AgentTargetInput(mode="automatic", manual_target=None, expected_revision=3)
    assert value.mode == "automatic"
    assert value.manual_target is None


def test_returning_to_automatic_restores_derived_target_and_revision_changes():
    manual_sources = _sources()
    manual_sources["target_settings"] = [
        {
            "month": MONTH,
            "agent_code": "AG1",
            "mode": "manual",
            "manual_target": D(1500),
            "revision": 2,
        }
    ]
    manual = _project(manual_sources)

    automatic_sources = _sources()
    automatic_sources["target_settings"] = [
        {
            "month": MONTH,
            "agent_code": "AG1",
            "mode": "automatic",
            "manual_target": None,
            "revision": 3,
        }
    ]
    automatic = _project(automatic_sources)

    assert _agent(manual, "AG1").home_target == D(1500)
    assert _agent(automatic, "AG1").home_target == D(2000)
    assert _agent(automatic, "AG1").home_commission == D(48)
    assert manual.projection_revision != automatic.projection_revision


def test_target_setting_is_isolated_by_agent_and_month():
    sources = _sources()
    sources["target_settings"] = [
        {
            "month": MONTH,
            "agent_code": "AG2",
            "mode": "manual",
            "manual_target": D(1500),
            "revision": 1,
        },
        {
            "month": "2026-10",
            "agent_code": "AG1",
            "mode": "manual",
            "manual_target": D(900),
            "revision": 1,
        },
    ]
    result = _project(sources)

    assert _agent(result, "AG1").home_target == D(2000)
    assert _agent(result, "AG2").home_target == D(1500)
    assert _agent(result, "SUP").home_target == D(2000)


def test_manual_home_target_does_not_change_supplemental_location_commission():
    automatic_sources = _sources()
    automatic = _project(automatic_sources)
    manual_sources = _sources()
    manual_sources["target_settings"] = [
        {
            "month": MONTH,
            "agent_code": "AG1",
            "mode": "manual",
            "manual_target": D(1500),
            "revision": 1,
        }
    ]
    manual = _project(manual_sources)

    auto = _agent(automatic, "AG1")
    overridden = _agent(manual, "AG1")
    assert auto.away_commission == D(24)
    assert overridden.away_commission == D(24)
    assert overridden.supplemental_pay == D(150)
    assert overridden.home_commission != auto.home_commission


def test_resolved_rows_are_isolated_by_site_agent_and_month():
    sources = _sources()
    sources["agent_target_rows"] = [
        {"import_month": MONTH, "site_code": "A", "agent": "AG1", "target_value": D(1500)},
        {"import_month": "2026-10", "site_code": "A", "agent": "AG1", "target_value": D(900)},
        {"import_month": MONTH, "site_code": "B", "agent": "AG1", "target_value": D(900)},
    ]
    result = _project(sources)

    # The home target is the current-month resolved row for the home site;
    # rows for another month/site must not leak into this projection.
    assert _agent(result, "AG1").home_target == D(1500)
    assert _agent(result, "AG2").home_target == D(1000)
    assert _agent(result, "SUP").home_target == D(2000)
