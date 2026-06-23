from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request

from auth import AuthClaims
from rate_limits import InMemoryRateLimiter, RateLimitPolicy, enforce_rate_limit


def request(path: str = "/api/exports/download", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": headers or [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def claims(sub: str = "subject-1") -> AuthClaims:
    return AuthClaims(
        sub=sub,
        email=f"{sub}@example.com",
        preferred_username=sub,
        groups=["unihub-manager"],
        iss="test",
        aud="test",
        iat=0,
        exp=0,
        raw={},
    )


def test_in_memory_limiter_blocks_until_window_expires() -> None:
    now = 1000.0
    limiter = InMemoryRateLimiter(clock=lambda: now)
    policy = RateLimitPolicy(name="test", limit=2, window_seconds=10)

    assert limiter.hit(policy, "user:1") is None
    assert limiter.hit(policy, "user:1") is None
    assert limiter.hit(policy, "user:1") == 10

    now = 1010.1
    assert limiter.hit(policy, "user:1") is None


@pytest.mark.asyncio
async def test_enforce_rate_limit_returns_429_with_retry_after() -> None:
    limiter = InMemoryRateLimiter(clock=lambda: 2000.0)
    policy = RateLimitPolicy(name="test", limit=1, window_seconds=30)
    user_claims = claims()

    await enforce_rate_limit(request(), policy, user_claims, limiter)

    with pytest.raises(HTTPException) as exc:
        await enforce_rate_limit(request(), policy, user_claims, limiter)

    assert exc.value.status_code == 429
    assert exc.value.headers == {"Retry-After": "30"}


@pytest.mark.asyncio
async def test_rate_limit_key_uses_user_and_forwarded_ip() -> None:
    limiter = InMemoryRateLimiter(clock=lambda: 3000.0)
    policy = RateLimitPolicy(name="test", limit=1, window_seconds=30)
    forwarded_request = request(headers=[(b"cf-connecting-ip", b"203.0.113.10")])

    await enforce_rate_limit(forwarded_request, policy, claims("user-a"), limiter)
    await enforce_rate_limit(forwarded_request, policy, claims("user-b"), limiter)

    with pytest.raises(HTTPException):
        await enforce_rate_limit(forwarded_request, policy, claims("user-a"), limiter)


def _route_dependency_names(route: APIRoute) -> set[str]:
    return {
        getattr(route_dependency.call, "__name__", "")
        for route_dependency in route.dependant.dependencies
    }


def test_sensitive_routes_have_rate_limit_dependencies() -> None:
    from main import app

    expected = {
        ("GET", "/auth/proxy/{path:path}"): "rate_limit_auth_proxy",
        ("POST", "/auth/proxy/{path:path}"): "rate_limit_auth_proxy",
        ("POST", "/api/import/sales"): "rate_limit_sales_import_upload",
        ("POST", "/api/exports/preview"): "rate_limit_report_export",
        ("POST", "/api/exports/download"): "rate_limit_report_export",
        ("POST", "/api/grile/run"): "rate_limit_grile_job",
        ("POST", "/api/grile/monthly/run"): "rate_limit_grile_job",
        ("POST", "/api/target-calculator/scenarios/calculate"): "rate_limit_target_mutation",
        ("PATCH", "/api/target-calculator/scenarios/{scenario_id}/rows"): "rate_limit_target_mutation",
        ("POST", "/api/target-calculator/scenarios/{scenario_id}/finalize"): "rate_limit_target_mutation",
        ("GET", "/api/target-calculator/scenarios/{scenario_id}/export"): "rate_limit_report_export",
        ("POST", "/api/crm/scores/recalculate"): "rate_limit_business_write",
        ("POST", "/api/stores/targets"): "rate_limit_business_write",
    }

    routes = {
        (method, route.path): route
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }

    for route_key, dependency_name in expected.items():
        route = routes[route_key]
        assert dependency_name in _route_dependency_names(route), route_key
