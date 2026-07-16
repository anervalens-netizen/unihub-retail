from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from starlette.requests import Request

from auth import AuthClaims
from permissions import (
    can_access_salaries,
    can_administer_imports,
    can_access_management,
    can_write_business_data,
    require_business_write_access,
    require_import_admin,
    require_management_access,
    require_report_export_access,
    require_salary_access,
)
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


def _api_route_contexts(app: Any) -> list[RouteContext]:
    """Flatten direct and included routers across supported FastAPI versions."""
    return [
        route
        for route in iter_route_contexts(app.routes)
        if isinstance(route.original_route, APIRoute)
    ]


def _route_path(route: RouteContext) -> str:
    assert route.path is not None
    return route.path


def _route_methods(route: RouteContext) -> set[str]:
    assert route.methods is not None
    return route.methods


def _dependency_calls(route: RouteContext) -> set[object]:
    assert route.dependant is not None
    return {
        route_dependency.call
        for route_dependency in route.dependant.dependencies
    }


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
        for route in _api_route_contexts(app)
        if _route_path(route).startswith("/salarii")
    ]

    assert salary_routes
    for route in salary_routes:
        assert require_salary_access in _dependency_calls(route)


@pytest.mark.parametrize("group", ["unihub-admin", "authentik Admins"])
def test_import_access_allows_admin_groups(group: str) -> None:
    user_claims = claims([group])
    assert can_administer_imports(user_claims) is True
    assert require_import_admin(request(), user_claims) is user_claims


@pytest.mark.parametrize(
    "group",
    ["unihub-manager", "unihub-hr", "unihub-agent", "unihub-team-lead"],
)
def test_import_access_rejects_non_admin_groups(group: str) -> None:
    user_claims = claims([group])
    assert can_administer_imports(user_claims) is False
    with pytest.raises(HTTPException) as exc:
        require_import_admin(request(), user_claims)
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "group",
    ["unihub-manager", "unihub-admin", "authentik Admins", "unihub-hr"],
)
def test_management_access_allows_management_groups(group: str) -> None:
    user_claims = claims([group])
    assert can_access_management(user_claims) is True
    assert require_management_access(request(), user_claims) is user_claims
    assert require_report_export_access(request(), user_claims) is user_claims


@pytest.mark.parametrize("group", ["unihub-agent", "unihub-team-lead"])
def test_management_access_rejects_non_management_groups(group: str) -> None:
    user_claims = claims([group])
    assert can_access_management(user_claims) is False
    with pytest.raises(HTTPException) as exc:
        require_management_access(request(), user_claims)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        require_report_export_access(request(), user_claims)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("group", ["unihub-manager", "unihub-admin", "authentik Admins"])
def test_business_write_access_allows_managers_and_admins(group: str) -> None:
    user_claims = claims([group])
    assert can_write_business_data(user_claims) is True
    assert require_business_write_access(request(), user_claims) is user_claims


@pytest.mark.parametrize("group", ["unihub-hr", "unihub-agent", "unihub-team-lead"])
def test_business_write_access_rejects_non_business_writers(group: str) -> None:
    user_claims = claims([group])
    assert can_write_business_data(user_claims) is False
    with pytest.raises(HTTPException) as exc:
        require_business_write_access(request(), user_claims)
    assert exc.value.status_code == 403


def test_every_import_route_uses_the_import_admin_dependency() -> None:
    from main import app

    import_routes = [
        route
        for route in _api_route_contexts(app)
        if _route_path(route).startswith("/api/import")
    ]
    assert import_routes
    for route in import_routes:
        assert require_import_admin in _dependency_calls(route)

    store_activity_routes = [
        route
        for route in _api_route_contexts(app)
        if _route_path(route) == "/api/stores/{site_code}/activity"
    ]
    assert store_activity_routes
    assert require_import_admin in _dependency_calls(store_activity_routes[0])


def test_sensitive_management_routes_use_role_dependencies() -> None:
    from main import app

    expected = {
        "/api/exports": require_report_export_access,
        "/api/hr": require_management_access,
        "/api/target-calculator": require_management_access,
    }
    api_routes = _api_route_contexts(app)

    for prefix, dependency in expected.items():
        routes = [
            route
            for route in api_routes
            if _route_path(route).startswith(prefix)
        ]
        assert routes, prefix
        for route in routes:
            assert dependency in _dependency_calls(route), _route_path(route)


def test_business_write_routes_use_business_write_dependency() -> None:
    from main import app

    expected_routes = {
        ("POST", "/api/stores/targets"),
        ("POST", "/api/tasks"),
        ("PATCH", "/api/tasks/{task_id}"),
        ("DELETE", "/api/tasks/{task_id}"),
        ("POST", "/api/crm/scores/recalculate"),
    }

    routes = [
        route
        for route in _api_route_contexts(app)
        if any(
            method in _route_methods(route)
            for method, path in expected_routes
            if path == _route_path(route)
        )
    ]
    seen = {
        (next(iter(_route_methods(route) & {"POST", "PATCH", "DELETE"})), _route_path(route))
        for route in routes
    }
    assert expected_routes <= seen

    for route in routes:
        assert require_business_write_access in _dependency_calls(route), _route_path(route)


def test_target_row_write_uses_target_owner_dependency() -> None:
    from main import app
    from routers.target_calculator import require_target_owner

    route = next(
        route
        for route in _api_route_contexts(app)
        if _route_path(route) == "/api/target-calculator/scenarios/{scenario_id}/rows"
    )
    assert require_target_owner in _dependency_calls(route)


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
