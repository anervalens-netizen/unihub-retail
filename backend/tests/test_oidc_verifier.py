from __future__ import annotations

import json

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from oidc_settings import OIDCVerifierSettings
from oidc_verifier import OIDCVerifier


def _settings() -> OIDCVerifierSettings:
    return OIDCVerifierSettings("https://issuer.example.invalid", "https://issuer.example.invalid/jwks", "test", 60, 120, 1, 30)


def _jwks(kid: str) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    value = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    value.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return json.dumps({"keys": [value]}).encode()


@pytest.mark.anyio
async def test_fresh_cache_does_not_refetch() -> None:
    calls = 0
    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_jwks("synthetic-kid"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client)
        await verifier.signing_key({"alg": "RS256", "kid": "synthetic-kid"})
        await verifier.signing_key({"alg": "RS256", "kid": "synthetic-kid"})
    assert calls == 1


@pytest.mark.anyio
async def test_invalid_jwks_fails_closed() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"keys": []}')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client)
        with pytest.raises(Exception) as exc_info:
            await verifier.signing_key({"alg": "RS256", "kid": "synthetic-kid"})
    assert getattr(exc_info.value, "status_code", None) == 503
