from __future__ import annotations

import httpx
import pytest

from main import app, spa_fallback_allowed


def scope(*, method: str = "GET", accept: str = "text/html") -> dict:
    return {
        "method": method,
        "headers": [(b"accept", accept.encode("ascii"))],
    }


def test_spa_fallback_is_only_for_html_navigation() -> None:
    assert spa_fallback_allowed("dashboard", scope()) is True
    assert spa_fallback_allowed("agents/history", scope(method="HEAD")) is True
    assert spa_fallback_allowed("dashboard", scope(accept="application/json")) is False
    assert spa_fallback_allowed("dashboard", scope(method="POST")) is False


@pytest.mark.parametrize(
    "path",
    [
        "api/unknown",
        "auth/unknown",
        "metrics/unknown",
        "docs",
        "redoc",
        "openapi.json",
        "assets/missing.js",
    ],
)
def test_server_namespaces_never_use_spa_fallback(path: str) -> None:
    assert spa_fallback_allowed(path, scope()) is False


@pytest.mark.anyio
async def test_docs_are_disabled_and_api_responses_are_private_no_store() -> None:
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://retail.example.invalid",
    ) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = await client.get(path, headers={"Accept": "text/html"})
            assert response.status_code == 404
            assert not response.headers.get("content-type", "").startswith("text/html")

        api_response = await client.get("/api/unknown")
        assert api_response.status_code == 404
        assert api_response.headers["Cache-Control"] == "private, no-store, max-age=0"
        assert api_response.headers["CDN-Cache-Control"] == "no-store"
        assert api_response.headers["Surrogate-Control"] == "no-store"

        for sensitive_path in (
            "/salarii/overview",
            "/api/store-pnl/months",
            "/api/visits-report/photo/missing/missing.jpg",
            "/api/exports/catalog",
        ):
            sensitive_response = await client.get(sensitive_path)
            assert sensitive_response.status_code in {401, 403, 404, 422}
            assert (
                sensitive_response.headers["Cache-Control"]
                == "private, no-store, max-age=0"
            )
            assert sensitive_response.headers["CDN-Cache-Control"] == "no-store"
