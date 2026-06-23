from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request

from auth import AuthClaims
from permissions import can_access_salaries, require_salary_access
from routers.salarii import SalaryExportAudit, audit_salary_export


def claims(groups: list[str]) -> AuthClaims:
    return AuthClaims(
        sub="subject-1",
        email="user@example.com",
        preferred_username="user",
        groups=groups,
        iss="test",
        aud="test",
        iat=0,
        exp=0,
        raw={},
    )


def request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/salarii/overview",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


@pytest.mark.parametrize(
    "group",
    [
        "unihub-manager",
        "unihub-admin",
        "authentik Admins",
        "unihub-hr",
    ],
)
def test_salary_access_allows_authorized_groups(group: str) -> None:
    user_claims = claims([group])
    assert can_access_salaries(user_claims) is True
    assert require_salary_access(request(), user_claims) is user_claims


@pytest.mark.parametrize(
    "groups",
    [
        [],
        ["unihub-agent"],
        ["unihub-team-lead"],
        ["manager"],
    ],
)
def test_salary_access_rejects_other_users(groups: list[str]) -> None:
    user_claims = claims(groups)
    assert can_access_salaries(user_claims) is False

    with pytest.raises(HTTPException) as exc:
        require_salary_access(request(), user_claims)
    assert exc.value.status_code == 403


def test_every_salary_route_uses_the_salary_dependency() -> None:
    from main import app

    salary_routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/salarii")
    ]

    assert salary_routes
    for route in salary_routes:
        dependency_calls = {
            dependency.call
            for dependency in route.dependant.dependencies
        }
        assert require_salary_access in dependency_calls


@pytest.mark.asyncio
async def test_salary_export_audit_logs_metadata_only(caplog: pytest.LogCaptureFixture) -> None:
    export_request = request()
    user_claims = claims(["unihub-manager"])
    require_salary_access(export_request, user_claims)

    with caplog.at_level("INFO", logger="routers.salarii"):
        response = await audit_salary_export(
            SalaryExportAudit(export_kind="agents_page", row_count=17),
            export_request,
        )

    assert response.status_code == 204
    assert "subject=subject-1" in caplog.text
    assert "kind=agents_page" in caplog.text
    assert "rows=17" in caplog.text
    assert user_claims.email not in caplog.text
