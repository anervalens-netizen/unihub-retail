from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from auth import AuthClaims, require_auth
from composition import build_grile_calendar_service
from grile.calendar_models import CalendarChanges, CalendarDayInput, CalendarMonthKey, RosterInput
from repositories.grile_calendar import CalendarConflict
from routers.grile_calendar import router
from services.grile_calendar import GrileCalendarService


def change(**overrides):
    return CalendarDayInput(**{
        "work_date": "2026-09-01", "agent_code": "AG1", "site_code": "A",
        "status": "work", "expected_revision": 0, **overrides,
    })


@pytest.mark.parametrize("month", ["0000-01", "0001-01", "2026-13", "2026-9"])
def test_invalid_month_is_validation_error(month):
    with pytest.raises(ValidationError):
        TypeAdapter(CalendarMonthKey).validate_python(month)


def test_inputs_reject_ambiguous_or_unbounded_changes():
    with pytest.raises(ValidationError, match="Only a working"):
        change(status="leave", supplemental=True)
    with pytest.raises(ValidationError, match="only once"):
        CalendarChanges(days=[change(), change(site_code="B")])
    with pytest.raises(ValidationError):
        change(agent_code=" ")
    with pytest.raises(ValidationError):
        CalendarChanges(days=[])


@pytest.mark.asyncio
async def test_future_roster_uses_current_month_and_marks_absent_previous(monkeypatch):
    monkeypatch.setattr("services.grile_calendar.business_today", lambda: date(2026, 9, 15))
    repository = AsyncMock()
    repository.candidates.return_value = [
        {"agent_code": "AG1", "import_month": "2026-08", "site_code": "OLD"},
        {"agent_code": "AG1", "import_month": "2026-09", "site_code": "A"},
        {"agent_code": "AG1", "import_month": "2026-09", "site_code": "B"},
        {"agent_code": "AG1", "import_month": "2026-09", "site_code": "B"},
        {"agent_code": "LEAVE", "import_month": "2026-08", "site_code": "A"},
    ]
    result = await GrileCalendarService(repository).candidates("2026-10")
    repository.candidates.assert_awaited_once_with("2026-09", "2026-08")
    assert result[0].site_codes == ["A", "B"]
    assert result[0].needs_home_confirmation
    assert not result[0].needs_active_confirmation
    assert result[1].needs_active_confirmation
    assert not result[1].needs_home_confirmation


@pytest.mark.asyncio
async def test_attendance_uses_calendar_person_not_sales_leader_code():
    repository = AsyncMock()
    repository.read.return_value = {
        "roster": [{"month": "2026-09", "agent_code": "AG1", "home_site_code": "A", "active": True, "revision": 1}],
        "days": [
            {**change().model_dump(exclude={"expected_revision"}), "revision": 1},
            {**change(work_date="2026-09-02", site_code="B", supplemental=True).model_dump(exclude={"expected_revision"}), "revision": 2},
            {**change(work_date="2026-09-03", status="leave").model_dump(exclude={"expected_revision"}), "revision": 3},
            {**change(work_date="2026-09-04", status="off").model_dump(exclude={"expected_revision"}), "revision": 1},
            {**change(work_date="2026-09-05", status="cancelled").model_dump(exclude={"expected_revision"}), "revision": 2},
        ],
    }
    result = await GrileCalendarService(repository).read("2026-09")
    attendance = result.attendance[0]
    assert attendance.agent_code == "AG1"
    assert attendance.work_days_by_site == {"A": 1, "B": 1}
    assert (attendance.work_days, attendance.leave_days, attendance.off_days) == (2, 1, 1)


@pytest.mark.asyncio
async def test_service_fences_unknown_codes_wrong_month_and_repository_conflict():
    repository = AsyncMock()
    repository.candidates.return_value = []
    service = GrileCalendarService(repository)
    payload = RosterInput(home_site_code="A", expected_revision=0)
    with pytest.raises(HTTPException) as error:
        await service.save_roster("2026-09", "UNKNOWN", payload, "manager-sub")
    assert error.value.status_code == 422
    repository.save_roster.assert_not_awaited()
    with pytest.raises(HTTPException) as error:
        await service.save_days("2026-10", CalendarChanges(days=[change()]), "manager-sub")
    assert error.value.status_code == 422
    repository.save_days.assert_not_awaited()
    repository.save_days.side_effect = CalendarConflict("stale")
    with pytest.raises(HTTPException) as error:
        await service.save_days("2026-09", CalendarChanges(days=[change()]), "manager-sub")
    assert error.value.status_code == 409
    repository.save_roster.side_effect = CalendarConflict("stale")
    with pytest.raises(HTTPException) as error:
        await service.save_roster("2026-09", "AG1", payload.model_copy(update={"expected_revision": 1}), "manager-sub")
    assert error.value.status_code == 409


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(router)
    service = AsyncMock()
    app.dependency_overrides[build_grile_calendar_service] = lambda: service
    for route in router.routes:
        for dependency in route.dependant.dependencies:
            if dependency.name == "_limit":
                app.dependency_overrides[dependency.call] = lambda: None
    return app, service


def set_role(app, role):
    app.dependency_overrides[require_auth] = lambda: AuthClaims(
        sub="manager-sub", groups=[role], email="test@example.invalid",
        preferred_username="test", iss="test", aud="test", iat=1, exp=2, raw={},
    )


@pytest.mark.parametrize("role", ["unihub-agent", "unihub-team-leader", "unihub-hr"])
def test_agents_leaders_and_hr_cannot_write_calendar(api, role):
    app, service = api
    set_role(app, role)
    client = TestClient(app)
    assert client.put("/api/grile/calendar/2026-09/roster/AG1", json={"home_site_code": "A", "expected_revision": 0}).status_code == 403
    assert client.patch("/api/grile/calendar/2026-09/days", json={"days": [change().model_dump(mode="json")]}).status_code == 403
    service.save_days.assert_not_awaited()
    assert client.put("/api/grile/calendar/2026-09/store-hours/A", json={"expected_revision": 0}).status_code == 403


def test_manager_routes_preserve_actor_and_typed_contract(api):
    app, service = api
    set_role(app, "unihub-manager")
    service.candidates.return_value = []
    service.read.return_value = {"month": "2026-09", "roster": [], "days": [], "attendance": []}
    service.save_roster.return_value = {"month": "2026-09", "agent_code": "AG1", "home_site_code": "A", "active": True, "revision": 1}
    service.save_days.return_value = [{**change().model_dump(exclude={"expected_revision"}), "revision": 1}]
    client = TestClient(app)
    assert client.get("/api/grile/calendar/2026-09/candidates").status_code == 200
    assert client.get("/api/grile/calendar/2026-09").status_code == 200
    assert client.put("/api/grile/calendar/2026-09/roster/AG1", json={"home_site_code": "A", "expected_revision": 0}).status_code == 200
    assert service.save_roster.await_args.args[-1] == "manager-sub"
    assert client.patch("/api/grile/calendar/2026-09/days", json={"days": [change().model_dump(mode="json")]}).status_code == 200
    assert service.save_days.await_args.args[-1] == "manager-sub"
    assert client.get("/api/grile/calendar/0000-01").status_code == 422
    service.save_hours.return_value = {"site_code": "A", "revision": 1}
    assert client.put("/api/grile/calendar/2026-09/store-hours/A", json={"expected_revision": 0}).status_code == 200
    assert service.save_hours.await_args.args[-1] == "manager-sub"


@pytest.mark.parametrize("role", ["unihub-agent", "unihub-team-leader"])
def test_calendar_reads_are_management_only(api, role):
    app, _ = api
    set_role(app, role)
    assert TestClient(app).get("/api/grile/calendar/2026-09").status_code == 403
    assert TestClient(app).get("/api/grile/calendar/2026-09/attendance.zip", params={"expected_revision": "a" * 64}).status_code == 403


@pytest.mark.asyncio
async def test_calendar_composition_uses_existing_pool(monkeypatch):
    pool = object()
    monkeypatch.setattr("composition.get_pool", AsyncMock(return_value=pool))
    service = await build_grile_calendar_service()
    assert service.repository.pool is pool


def test_attendance_openapi_declares_binary_zip(api):
    app, _service = api
    response = app.openapi()['paths']['/api/grile/calendar/{month}/attendance.zip']['get']['responses']['200']
    assert response['content'] == {'application/zip': {'schema': {'type': 'string', 'format': 'binary'}}}
