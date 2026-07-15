from __future__ import annotations

import logging
import uuid
from typing import Literal

import httpx
import pytest
import structlog
from fastapi import FastAPI, Request

import request_context
from logging_config import RequestContextFilter
from request_context import RequestContextMiddleware


class _FakeSentryScope:
    def __init__(self) -> None:
        self.tags: dict[str, str] = {}
        self.extra: dict[str, str] = {}

    def __enter__(self) -> "_FakeSentryScope":
        return self

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        return False

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = value

    def set_extra(self, key: str, value: str) -> None:
        self.extra[key] = value


def _build_ping_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    async def ping(request: Request) -> dict[str, str]:
        return {"request_id": request.state.request_id}

    return app


@pytest.mark.anyio
@pytest.mark.parametrize("incoming_request_id", ["retail-req-123", "bad id with spaces"])
async def test_request_context_middleware_sets_response_header_and_sentry_scope(
    incoming_request_id: str,
) -> None:
    transport = httpx.ASGITransport(app=_build_ping_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ping", headers={"X-Request-ID": incoming_request_id})

    response_request_id = response.headers["x-request-id"]
    assert response.status_code == 200
    assert response.json()["request_id"] == response_request_id
    assert request_context.get_request_id() is None

    if incoming_request_id == "bad id with spaces":
        assert response_request_id != incoming_request_id
        uuid.UUID(response_request_id)
    else:
        assert response_request_id == incoming_request_id


def test_request_id_is_applied_to_sentry_scope() -> None:
    fake_scope = _FakeSentryScope()

    request_context.apply_request_id_to_sentry_scope(fake_scope, "retail-req-123")

    assert fake_scope.tags["request_id"] == "retail-req-123"
    assert fake_scope.extra["request_id"] == "retail-req-123"


def test_request_context_helpers_bind_structlog_and_logging_records() -> None:
    token = request_context.bind_request_id("retail-req-123")
    try:
        assert request_context.get_request_id() == "retail-req-123"
        assert structlog.contextvars.get_contextvars()["request_id"] == "retail-req-123"

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        assert RequestContextFilter().filter(record) is True
        assert getattr(record, "request_id") == "retail-req-123"
    finally:
        request_context.reset_request_id(token)


def test_request_context_filter_uses_dash_outside_request() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )

    assert RequestContextFilter().filter(record) is True
    assert getattr(record, "request_id") == "-"


@pytest.mark.anyio
async def test_request_id_header_is_allowed_in_cors_preflight() -> None:
    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/metrics",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Request-ID",
            },
        )

    assert response.status_code == 200
    assert "x-request-id" in response.headers["access-control-allow-headers"].lower()


@pytest.mark.anyio
async def test_api_responses_are_not_cached_by_browser_or_cdn() -> None:
    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/filters/months")

    assert response.status_code == 401
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["cdn-cache-control"] == "no-store"
    assert response.headers["surrogate-control"] == "no-store"


@pytest.mark.anyio
async def test_unhandled_exception_response_preserves_request_id() -> None:
    from main import unhandled_exception_handler

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/boom",
            "raw_path": b"/boom",
            "query_string": b"",
            "headers": [],
            "state": {"request_id": "retail-error-123"},
            "scheme": "http",
            "server": ("test", 80),
            "client": ("test", 123),
            "root_path": "",
            "http_version": "1.1",
        },
    )

    response = await unhandled_exception_handler(request, RuntimeError("boom"))

    assert response.status_code == 500
    assert response.headers[request_context.REQUEST_ID_HEADER] == "retail-error-123"
