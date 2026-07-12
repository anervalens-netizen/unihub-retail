from __future__ import annotations

import asyncio
import ipaddress
from typing import Any

import httpx
import pytest
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from starlette.requests import Request

from auth import AuthClaims
from rate_limit_settings import PolicySettings, RateLimitSettings
from rate_limit_store import RateLimitDecision
from rate_limits import RateLimitPolicy, anonymous_rate_limit, enforce_rate_limit, rate_limit


class Store:
    def __init__(self, decision: RateLimitDecision | None = None, error: BaseException | None = None) -> None:
        self.decision = decision or RateLimitDecision(True, 4, 0, 30)
        self.error = error
        self.calls: list[tuple[str, int, int]] = []

    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        self.calls.append((key, limit, window_seconds))
        if self.error:
            raise self.error
        return self.decision

    async def close(self) -> None:
        return None


def settings(mode: str = "none") -> RateLimitSettings:
    return RateLimitSettings(
        (ipaddress.ip_network("127.0.0.1/32"),), mode,  # type: ignore[arg-type]
        "redis://localhost", "s" * 43, "closed", {"test": PolicySettings(5, 30)},
    )


def request(peer: str = "127.0.0.1", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/test", "headers": headers or [], "client": (peer, 12345), "server": ("test", 80), "scheme": "http", "query_string": b""})


def claims(sub: str = "subject-1", email: str = "user@example.invalid") -> AuthClaims:
    return AuthClaims(sub, email, "user", ["unihub-manager"], "issuer", "audience", 0, 0, {})


@pytest.mark.asyncio
async def test_authenticated_identity_is_subject_only_and_private() -> None:
    store = Store(); cfg = settings(); policy = RateLimitPolicy("test", 1, 1)
    await enforce_rate_limit(request("127.0.0.1"), policy, claims("same-sub", "first@example.invalid"), store, cfg)
    await enforce_rate_limit(request("127.0.0.2"), policy, claims("same-sub", "second@example.invalid"), store, cfg)
    keys = [call[0] for call in store.calls]
    assert keys[0] == keys[1]
    assert "same-sub" not in keys[0] and "example.invalid" not in keys[0] and "127.0.0" not in keys[0]
    assert keys[0].startswith("unihub:retail:ratelimit:v1:test:")


@pytest.mark.asyncio
async def test_different_subjects_and_anonymous_ips_have_independent_keys() -> None:
    store = Store(); cfg = settings(); policy = RateLimitPolicy("test", 1, 1)
    await enforce_rate_limit(request(), policy, claims("a"), store, cfg)
    await enforce_rate_limit(request(), policy, claims("b"), store, cfg)
    await enforce_rate_limit(request("127.0.0.1"), policy, None, store, cfg)
    await enforce_rate_limit(request("127.0.0.2"), policy, None, store, cfg)
    assert len({call[0] for call in store.calls}) == 4


@pytest.mark.asyncio
async def test_allowed_and_rejected_response_headers_are_exact() -> None:
    cfg = settings(); policy = RateLimitPolicy("test", 1, 1); response = Response()
    await enforce_rate_limit(request(), policy, claims(), Store(RateLimitDecision(True, 4, 0, 30)), cfg, response)
    assert {name: response.headers[name] for name in ("ratelimit-limit", "ratelimit-remaining", "ratelimit-reset")} == {"ratelimit-limit": "5", "ratelimit-remaining": "4", "ratelimit-reset": "30"}
    with pytest.raises(HTTPException) as exc:
        await enforce_rate_limit(request(), policy, claims(), Store(RateLimitDecision(False, 0, 7, 8)), cfg)
    assert exc.value.status_code == 429
    assert exc.value.headers == {"RateLimit-Limit": "5", "RateLimit-Remaining": "0", "RateLimit-Reset": "8", "Retry-After": "7"}


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimeoutError(), ConnectionError(), RuntimeError("script")])
async def test_backend_failures_are_generic_503_never_allow_or_429(error: Exception) -> None:
    with pytest.raises(HTTPException) as exc:
        await enforce_rate_limit(request(), RateLimitPolicy("test", 1, 1), claims(), Store(error=error), settings())
    assert exc.value.status_code == 503 and exc.value.headers is None
    assert "script" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_cancellation_propagates() -> None:
    with pytest.raises(asyncio.CancelledError):
        await enforce_rate_limit(request(), RateLimitPolicy("test", 1, 1), claims(), Store(error=asyncio.CancelledError()), settings())


@pytest.mark.asyncio
async def test_missing_runtime_is_fail_closed() -> None:
    import rate_limits
    old_store, old_settings = rate_limits._store, rate_limits._settings
    rate_limits._store = None; rate_limits._settings = None
    try:
        with pytest.raises(HTTPException) as exc:
            await enforce_rate_limit(request(), RateLimitPolicy("test", 1, 1), claims())
        assert exc.value.status_code == 503
    finally:
        rate_limits._store, rate_limits._settings = old_store, old_settings


@pytest.mark.anyio
async def test_real_asgi_contract_is_shared_and_has_exact_429_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    import rate_limits

    class CountingStore:
        def __init__(self) -> None:
            self.counts: dict[str, int] = {}
            self.lock = asyncio.Lock()

        async def check(self, key: str, limit: int, _window: int) -> RateLimitDecision:
            async with self.lock:
                current = self.counts.get(key, 0)
                if current >= limit:
                    return RateLimitDecision(False, 0, 4, 4)
                current += 1; self.counts[key] = current
                return RateLimitDecision(True, limit - current, 0, 30)

        async def close(self) -> None:
            return None

    cfg = settings(); cfg.policies["anonymous-test"] = PolicySettings(2, 30)
    monkeypatch.setattr(rate_limits, "_store", CountingStore())
    monkeypatch.setattr(rate_limits, "_settings", cfg)
    dependency = anonymous_rate_limit(RateLimitPolicy("anonymous-test", 2, 30))

    def app() -> FastAPI:
        value = FastAPI()
        @value.get("/limited", dependencies=[Depends(dependency)])
        async def limited() -> dict[str, bool]:
            return {"ok": True}
        return value

    clients = [httpx.AsyncClient(transport=httpx.ASGITransport(app=app()), base_url="http://test") for _ in range(2)]
    try:
        first = await clients[0].get("/limited"); second = await clients[1].get("/limited"); rejected = await clients[0].get("/limited")
    finally:
        await asyncio.gather(*(client.aclose() for client in clients))
    assert first.status_code == second.status_code == 200 and rejected.status_code == 429
    assert first.headers["ratelimit-limit"] == "2" and second.headers["ratelimit-remaining"] == "0"
    assert rejected.headers["retry-after"] == "4" and rejected.headers["ratelimit-reset"] == "4"


@pytest.mark.anyio
async def test_authenticated_asgi_dependency_uses_verified_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    import rate_limits
    store = Store(); cfg = settings(); cfg.policies["test"] = PolicySettings(5, 30)
    monkeypatch.setattr(rate_limits, "_store", store); monkeypatch.setattr(rate_limits, "_settings", cfg)
    app = FastAPI()
    dependency = rate_limit(RateLimitPolicy("test", 5, 30))
    @app.get("/mutation", dependencies=[Depends(dependency)])
    async def mutation() -> dict[str, bool]:
        return {"ok": True}
    app.dependency_overrides[rate_limits.require_auth] = lambda: claims("verified-subject")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/mutation")
    assert response.status_code == 200 and response.headers["ratelimit-limit"] == "5"
    assert store.calls and "verified-subject" not in store.calls[0][0]


@pytest.mark.anyio
async def test_explicit_response_keeps_success_rate_limit_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rate_limits
    from main import SecurityHeadersMiddleware

    store = Store()
    cfg = settings()
    cfg.policies["explicit-response"] = PolicySettings(5, 30)
    monkeypatch.setattr(rate_limits, "_store", store)
    monkeypatch.setattr(rate_limits, "_settings", cfg)
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    dependency = anonymous_rate_limit(RateLimitPolicy("explicit-response", 5, 30))

    @app.get("/explicit", dependencies=[Depends(dependency)])
    async def explicit() -> Response:
        return Response(content="ok", media_type="text/plain")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/explicit")

    assert response.status_code == 200
    assert response.headers["ratelimit-limit"] == "5"
    assert response.headers["ratelimit-remaining"] == "4"
    assert response.headers["ratelimit-reset"] == "30"


def _api_route_contexts(app: Any) -> list[RouteContext]:
    return [route for route in iter_route_contexts(app.routes) if isinstance(route.original_route, APIRoute)]


def test_sensitive_routes_keep_named_rate_limit_dependencies() -> None:
    from main import app
    expected = {
        ("GET", "/auth/session/login"): "rate_limit_auth_proxy", ("GET", "/auth/callback"): "rate_limit_auth_proxy",
        ("GET", "/auth/session"): "rate_limit_auth_proxy", ("POST", "/auth/session/logout"): "rate_limit_auth_proxy",
        ("POST", "/api/import/sales"): "rate_limit_sales_import_upload", ("POST", "/api/import/promo-actuals"): "rate_limit_sales_import_upload",
        ("POST", "/api/exports/preview"): "rate_limit_report_export", ("POST", "/api/exports/download"): "rate_limit_report_export",
        ("POST", "/api/grile/run"): "rate_limit_grile_job", ("POST", "/api/grile/monthly/run"): "rate_limit_grile_job",
        ("POST", "/api/target-calculator/scenarios/calculate"): "rate_limit_target_mutation",
        ("PATCH", "/api/target-calculator/scenarios/{scenario_id}/rows"): "rate_limit_target_mutation",
        ("POST", "/api/target-calculator/scenarios/{scenario_id}/finalize"): "rate_limit_target_mutation",
        ("GET", "/api/target-calculator/scenarios/{scenario_id}/export"): "rate_limit_report_export",
        ("POST", "/api/crm/scores/recalculate"): "rate_limit_business_write", ("POST", "/api/stores/targets"): "rate_limit_business_write",
    }
    routes = {(method, route.path): route for route in _api_route_contexts(app) for method in (route.methods or set())}
    for route_key, name in expected.items():
        route = routes[route_key]; assert route.dependant is not None
        dependencies = {getattr(item.call, "__name__", "") for item in route.dependant.dependencies}
        assert name in dependencies, route_key
