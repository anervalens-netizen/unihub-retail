from __future__ import annotations

import json
import time
from typing import Any, cast

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

import auth
from auth import _validated_numeric_date, require_auth
from oidc_settings import OIDCVerifierSettings
from oidc_verifier import OIDCVerifier


ISSUER = "https://issuer.example.invalid/oidc"
AUDIENCE = "retail"


def _private_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(private_key: RSAPrivateKey, kid: str) -> dict[str, object]:
    value: dict[str, object] = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    value.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return value


def _token(private_key: RSAPrivateKey, kid: str = "A", **changes: object) -> str:
    now = int(time.time())
    payload: dict[str, object] = {"sub": "subject", "iss": ISSUER, "aud": AUDIENCE, "iat": now - 1, "exp": now + 60, "groups": ["unihub-manager"], "email": "user@example.invalid", "preferred_username": "user"}
    payload.update(changes)
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


def _settings() -> OIDCVerifierSettings:
    return OIDCVerifierSettings(ISSUER, f"{ISSUER}/jwks", AUDIENCE, 10, 30, 1, 0)


def _app(verifier: OIDCVerifier) -> FastAPI:
    app = FastAPI()
    @app.get("/protected")
    async def protected(claims=Depends(require_auth)):
        return {"sub": claims.sub, "groups": claims.groups}
    return app


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


@pytest.mark.anyio
async def test_real_asgi_valid_rsa_token_and_key_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    key_a, key_b = _private_key(), _private_key()
    calls = 0
    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        keys = [_jwk(key_a, "A")] if calls == 1 else [_jwk(key_b, "B")]
        return httpx.Response(200, json={"keys": keys})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as jwks_client:
        verifier = OIDCVerifier(_settings(), jwks_client)
        monkeypatch.setattr(auth, "get_oidc_verifier", lambda: verifier)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(verifier)), base_url="http://test") as client:
            first = await client.get("/protected", headers={"Authorization": f"Bearer {_token(key_a, 'A')}"})
            second = await client.get("/protected", headers={"Authorization": f"Bearer {_token(key_b, 'B')}"})
    assert first.status_code == second.status_code == 200 and calls == 2


@pytest.mark.anyio
async def test_real_rsa_token_supports_explicit_client_id_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = _private_key()

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [_jwk(key, "A")]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client)
        monkeypatch.setattr(auth, "get_oidc_verifier", lambda: verifier)
        claims = await auth.verify_oidc_token(
            _token(key, aud="browser-client"),
            audience="browser-client",
        )
        with pytest.raises(auth.HTTPException) as denied:
            await auth.verify_oidc_token(
                _token(key, aud=AUDIENCE),
                audience="browser-client",
            )

    assert claims.aud == "browser-client"
    assert denied.value.status_code == 401


@pytest.mark.anyio
@pytest.mark.parametrize(
    "changes,algorithm,kid",
    [
        ({}, "RS256", "B"), ({"iss": "https://wrong.invalid"}, "RS256", "A"),
        ({"aud": "wrong"}, "RS256", "A"), ({"exp": int(time.time()) - 10}, "RS256", "A"),
        ({"iat": int(time.time()) + 3600}, "RS256", "A"), ({"sub": ""}, "RS256", "A"),
        ({"groups": "unihub-manager"}, "RS256", "A"), ({}, "RS256", "unsafe kid"),
    ],
)
async def test_real_rsa_invalid_signature_claims_and_kid_are_generic_401(monkeypatch: pytest.MonkeyPatch, changes: dict[str, object], algorithm: str, kid: str) -> None:
    signing, trusted = _private_key(), _private_key()
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [_jwk(trusted, "A")]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as jwks_client:
        verifier = OIDCVerifier(_settings(), jwks_client)
        monkeypatch.setattr(auth, "get_oidc_verifier", lambda: verifier)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(verifier)), base_url="http://test") as client:
            response = await client.get("/protected", headers={"Authorization": f"Bearer {_token(signing, kid, **changes)}"})
    assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer"
    assert "subject" not in response.text and "unsafe kid" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize("missing", ["exp", "iat", "iss", "aud", "sub"])
async def test_real_rsa_requires_every_registered_claim(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    key = _private_key()
    token = _token(key)
    # Build a genuine signed JWT with the selected required claim omitted.
    payload = jwt.decode(token, options={"verify_signature": False})
    payload.pop(missing)
    token = jwt.encode(payload, key, algorithm="RS256", headers={"kid": "A"})
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [_jwk(key, "A")]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as jwks_client:
        verifier = OIDCVerifier(_settings(), jwks_client)
        monkeypatch.setattr(auth, "get_oidc_verifier", lambda: verifier)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(verifier)), base_url="http://test") as client:
            response = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_real_asgi_rejects_a_signed_disallowed_algorithm(monkeypatch: pytest.MonkeyPatch) -> None:
    key = _private_key()
    token = jwt.encode(
        jwt.decode(_token(key), options={"verify_signature": False}),
        "s" * 32, algorithm="HS256", headers={"kid": "A"},
    )
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [_jwk(key, "A")]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as jwks_client:
        verifier = OIDCVerifier(_settings(), jwks_client)
        monkeypatch.setattr(auth, "get_oidc_verifier", lambda: verifier)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(verifier)), base_url="http://test") as client:
            response = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer"


@pytest.mark.anyio
@pytest.mark.parametrize("groups", [[], ["unihub-manager"], ["has space"], [""], [1], list(range(257))])
async def test_groups_and_optional_identity_claims_are_validated(monkeypatch: pytest.MonkeyPatch, groups: object) -> None:
    key = _private_key()
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [_jwk(key, "A")]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as jwks_client:
        verifier = OIDCVerifier(_settings(), jwks_client)
        monkeypatch.setattr(auth, "get_oidc_verifier", lambda: verifier)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(verifier)), base_url="http://test") as client:
            response = await client.get("/protected", headers={"Authorization": f"Bearer {_token(key, groups=groups, email="bad address" if groups == [] else "user@example.invalid", preferred_username=" bad " if groups == [] else "user")}"})
    assert response.status_code == (200 if groups in (["unihub-manager"], ["has space"]) else 401)


@pytest.mark.anyio
@pytest.mark.parametrize("changes", [{"sub": " valid subject "}, {"email": 1}, {"email": "invalid address"}, {"preferred_username": 1}, {"preferred_username": " invalid "}])
async def test_real_rsa_identity_claim_shapes_are_fail_closed(monkeypatch: pytest.MonkeyPatch, changes: dict[str, object]) -> None:
    key = _private_key()
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [_jwk(key, "A")]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as jwks_client:
        verifier = OIDCVerifier(_settings(), jwks_client)
        monkeypatch.setattr(auth, "get_oidc_verifier", lambda: verifier)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(verifier)), base_url="http://test") as client:
            response = await client.get("/protected", headers={"Authorization": f"Bearer {_token(key, **cast(Any, changes))}"})
    assert response.status_code == 401


@pytest.mark.anyio
@pytest.mark.parametrize("iat,exp", [(2**64, 1), (float("nan"), 1), (float("inf"), 1), (-float("inf"), 1), (True, 1), ([], 1), (1, "invalid")])
async def test_real_rsa_nonfinite_and_invalid_numeric_dates_are_generic_401(monkeypatch: pytest.MonkeyPatch, iat: object, exp: object) -> None:
    key = _private_key()
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [_jwk(key, "A")]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as jwks_client:
        verifier = OIDCVerifier(_settings(), jwks_client)
        monkeypatch.setattr(auth, "get_oidc_verifier", lambda: verifier)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(verifier)), base_url="http://test") as client:
            response = await client.get("/protected", headers={"Authorization": f"Bearer {_token(key, iat=iat, exp=exp)}"})
    assert response.status_code == 401 and "Authentication service unavailable" not in response.text


@pytest.mark.anyio
async def test_absent_verifier_and_missing_header_do_not_leak_token_or_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "synthetic-secret-token"
    monkeypatch.setattr(auth, "get_oidc_verifier", lambda: (_ for _ in ()).throw(auth.HTTPException(503, "Authentication service unavailable")))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(cast(OIDCVerifier, object()))), base_url="http://test") as client:
        missing = await client.get("/protected")
        unavailable = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert missing.status_code == 401 and unavailable.status_code == 503
    assert token not in missing.text + unavailable.text and ISSUER not in unavailable.text and AUDIENCE not in unavailable.text


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
