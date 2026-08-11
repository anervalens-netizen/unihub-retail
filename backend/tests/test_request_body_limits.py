from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import REGISTRY

from main import HTTP_REQUESTS_TOTAL, SecurityHeadersMiddleware, app as retail_app
from observability.prometheus import UNMATCHED_HANDLER
from request_context import RequestContextMiddleware
from request_body_limits import RequestBodyLimitMiddleware, RequestBodyLimits


def limited_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, limits=RequestBodyLimits(8, 16, 14, 12))

    @app.post("/{path:path}")
    async def consume(path: str, request: Request) -> dict[str, int | str]:
        return {"path": path, "size": len(await request.body())}

    return app


def composed_limited_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        RequestBodyLimitMiddleware,
        limits=RequestBodyLimits(8, 16, 14, 12),
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://retail.example.invalid"],
        allow_credentials=True,
        allow_methods=["POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    @app.post("/api/body")
    async def consume_body(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    return app


@pytest.mark.anyio
async def test_content_length_is_rejected_before_endpoint_reads_body() -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=limited_app()), base_url="http://test") as client:
        response = await client.post("/json", content=b"123456789")
    assert response.status_code == 413


@pytest.mark.anyio
async def test_chunked_body_without_content_length_is_counted() -> None:
    async def chunks():
        yield b"12345"
        yield b"67890"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=limited_app()), base_url="http://test") as client:
        response = await client.post("/json", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413


@pytest.mark.anyio
async def test_import_routes_have_separate_multipart_limits() -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=limited_app()), base_url="http://test") as client:
        accepted = await client.post("/api/import/sales", content=b"x" * 15, headers={"Content-Type": "multipart/form-data; boundary=x"})
        rejected = await client.post("/api/import/erp-reconciliation", content=b"x" * 13, headers={"Content-Type": "multipart/form-data; boundary=x"})
    assert accepted.status_code == 200
    assert accepted.json()["size"] == 15
    assert rejected.status_code == 413


@pytest.mark.anyio
async def test_composed_413_keeps_security_request_id_cache_and_metrics_contract() -> None:
    labels = {
        "method": "POST",
        "status": "4xx",
        "handler": UNMATCHED_HANDLER,
    }
    HTTP_REQUESTS_TOTAL.labels(**labels)
    before = REGISTRY.get_sample_value("http_requests_total", labels) or 0.0
    request_id = "oversize-contract-test"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=retail_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/import/sales",
            content=b"x",
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(2 * 1024 * 1024),
                "X-Request-ID": request_id,
            },
        )

    assert response.status_code == 413
    assert response.headers["x-request-id"] == request_id
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["cdn-cache-control"] == "no-store"
    assert REGISTRY.get_sample_value("http_requests_total", labels) == before + 1


@pytest.mark.anyio
async def test_chunked_413_keeps_the_composed_response_contract() -> None:
    async def chunks():
        yield b"12345"
        yield b"67890"

    request_id = "oversize-chunked-contract-test"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=composed_limited_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/body",
            content=chunks(),
            headers={
                "Content-Type": "application/json",
                "Origin": "https://retail.example.invalid",
                "X-Request-ID": request_id,
            },
        )

    assert response.status_code == 413
    assert response.headers["x-request-id"] == request_id
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["access-control-allow-origin"] == "https://retail.example.invalid"
