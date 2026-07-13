from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import REGISTRY

from main import (
    HTTP_REQUESTS_TOTAL,
    SecurityHeadersMiddleware,
    app,
)
from services import health as health_service


@pytest.mark.anyio
async def test_liveness_is_process_only(monkeypatch: pytest.MonkeyPatch) -> None:
    check = AsyncMock(side_effect=AssertionError("dependencies must not run"))
    monkeypatch.setattr("routers.health.verify_readiness", check)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/livez")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    check.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/health", "/readyz"])
async def test_readiness_aliases_are_dependency_backed(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    check = AsyncMock()
    monkeypatch.setattr("routers.health.verify_readiness", check)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(path)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    check.assert_awaited_once_with()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [RuntimeError("database unavailable"), TimeoutError()],
)
async def test_readiness_fails_closed_without_dependency_details(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    monkeypatch.setattr(
        "routers.health.verify_readiness",
        AsyncMock(side_effect=failure),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy"}
    assert "database" not in response.text.lower()


class _Connection:
    fetchval = AsyncMock(return_value=1)


class _Acquire:
    async def __aenter__(self) -> _Connection:
        return _Connection()

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Pool:
    def acquire(self) -> _Acquire:
        return _Acquire()


@pytest.mark.anyio
async def test_readiness_service_checks_postgres_and_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_pool = AsyncMock(return_value=_Pool())
    check_session = AsyncMock()
    monkeypatch.setattr(health_service, "get_pool", get_pool)
    monkeypatch.setattr(
        health_service,
        "verify_session_runtime_ready",
        check_session,
    )

    await health_service.verify_readiness(timeout_seconds=1.0)

    get_pool.assert_awaited_once_with()
    check_session.assert_awaited_once_with()


@pytest.mark.anyio
async def test_readiness_service_has_a_total_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow_pool() -> _Pool:
        await asyncio.sleep(1)
        return _Pool()

    monkeypatch.setattr(health_service, "get_pool", slow_pool)

    with pytest.raises(TimeoutError):
        await health_service.verify_readiness(timeout_seconds=0.001)


@pytest.mark.anyio
async def test_unhandled_5xx_is_counted_for_slo_metrics() -> None:
    test_app = FastAPI()
    test_app.add_middleware(SecurityHeadersMiddleware)

    @test_app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    HTTP_REQUESTS_TOTAL.labels("GET", "5xx", "/boom")
    labels = {"method": "GET", "status": "5xx", "handler": "/boom"}
    before = REGISTRY.get_sample_value("http_requests_total", labels) or 0.0
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=test_app,
            raise_app_exceptions=False,
        ),
        base_url="http://test",
    ) as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert REGISTRY.get_sample_value("http_requests_total", labels) == before + 1
