from __future__ import annotations

from typing import cast

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

import auth
from auth import _validated_numeric_date, require_auth


@pytest.mark.parametrize(
    "value",
    [10**10000, -(10**10000), float("nan"), float("inf"), -float("inf"), True, "1", [], {}, None],
    ids=["huge-positive", "huge-negative", "nan", "positive-infinity", "negative-infinity", "bool", "string", "list", "dict", "none"],
)
def test_numeric_dates_invalid_never_raise(value: object) -> None:
    assert _validated_numeric_date(value) is None


@pytest.mark.parametrize("value", [0, 1, 1.9, 2**63 - 1])
def test_numeric_dates_valid(value: object) -> None:
    assert _validated_numeric_date(value) == int(cast(int | float, value))


def test_real_asgi_missing_header_is_401_with_bearer() -> None:
    app = FastAPI()
    @app.get("/protected")
    async def protected(_=Depends(require_auth)): return {"ok": True}
    response = TestClient(app).get("/protected")
    assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer"


def _request(host: str = "127.0.0.1") -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": (host, 1), "scheme": "http"})


@pytest.mark.asyncio
async def test_hub_loopback_and_nonloopback(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "s" * 32
    monkeypatch.setenv("HUB_INTERNAL_SECRET", secret)
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [(b"x-hub-internal", secret.encode())], "client": ("127.0.0.1", 1), "scheme": "http"})
    assert (await require_auth(request, None)).sub == "hub-service"
    with pytest.raises(Exception) as exc:
        await require_auth(Request({**request.scope, "client": ("10.0.0.1", 1)}), None)
    assert getattr(exc.value, "status_code", None) == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("iat,exp", [(10**10000, 1), (1, float("nan")), (True, 1)], ids=["huge", "nan", "bool"])
async def test_invalid_numeric_claims_are_generic_401(monkeypatch: pytest.MonkeyPatch, iat: object, exp: object) -> None:
    class Verifier:
        settings = type("Settings", (), {"issuer": "issuer", "audience": "aud", "clock_skew_seconds": 0})()
        async def signing_key(self, _header: object): return type("Key", (), {"key": object()})()
    monkeypatch.setattr(auth, "get_oidc_verifier", lambda: Verifier())
    monkeypatch.setattr(auth.jwt, "get_unverified_header", lambda _token: {"alg": "RS256", "kid": "safe"})
    monkeypatch.setattr(auth.jwt, "decode", lambda *_args, **_kwargs: {"sub": "subject", "iss": "issuer", "aud": "aud", "iat": iat, "exp": exp})
    with pytest.raises(Exception) as exc:
        await require_auth(_request(), HTTPAuthorizationCredentials(scheme="Bearer", credentials="synthetic"))
    assert getattr(exc.value, "status_code", None) == 401
