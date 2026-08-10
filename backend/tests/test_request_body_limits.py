from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request

from request_body_limits import RequestBodyLimitMiddleware, RequestBodyLimits


def limited_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, limits=RequestBodyLimits(8, 16, 14, 12))

    @app.post("/{path:path}")
    async def consume(path: str, request: Request) -> dict[str, int | str]:
        return {"path": path, "size": len(await request.body())}

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
