from __future__ import annotations

import asyncio
import json

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from oidc_settings import OIDCVerifierSettings
from oidc_verifier import OIDCVerifier


class Clock:
    def __init__(self) -> None: self.value = 0.0
    def __call__(self) -> float: return self.value
    def advance(self, seconds: float) -> None: self.value += seconds


def _settings(**changes: float | int) -> OIDCVerifierSettings:
    values: dict[str, float | int] = {"cache_ttl_seconds": 10.0, "max_stale_seconds": 30.0, "fetch_timeout_seconds": 1.0, "clock_skew_seconds": 0, "unknown_kid_refresh_cooldown_seconds": 5.0, "refresh_failure_retry_seconds": 5.0}
    values.update(changes)
    return OIDCVerifierSettings("https://issuer.example.invalid", "https://issuer.example.invalid/jwks", "test", float(values["cache_ttl_seconds"]), float(values["max_stale_seconds"]), float(values["fetch_timeout_seconds"]), int(values["clock_skew_seconds"]), float(values["unknown_kid_refresh_cooldown_seconds"]), float(values["refresh_failure_retry_seconds"]))


def _jwks(kid: str) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    value = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    value.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return json.dumps({"keys": [value]}).encode()


@pytest.mark.anyio
async def test_fresh_cache_rotation_and_single_flight() -> None:
    calls = 0
    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls; calls += 1
        await asyncio.sleep(0)
        return httpx.Response(200, content=_jwks("B" if calls > 1 else "A"))
    clock = Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client, clock)
        await verifier.signing_key({"alg": "RS256", "kid": "A"})
        await verifier.signing_key({"alg": "RS256", "kid": "A"})
        clock.advance(11)
        result = await asyncio.gather(*[verifier.signing_key({"alg": "RS256", "kid": "B"}) for _ in range(20)])
    assert calls == 2 and len(result) == 20


@pytest.mark.anyio
async def test_failure_single_flight_backoff_and_bounded_stale() -> None:
    calls = 0
    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls; calls += 1
        return httpx.Response(200, content=_jwks("A")) if calls == 1 else httpx.Response(503)
    clock = Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client, clock)
        await verifier.signing_key({"alg": "RS256", "kid": "A"})
        clock.advance(11)
        assert len(await asyncio.gather(*[verifier.signing_key({"alg": "RS256", "kid": "A"}) for _ in range(20)])) == 20
        for _ in range(20): await verifier.signing_key({"alg": "RS256", "kid": "A"})
        assert calls == 2
        clock.advance(20)
        with pytest.raises(Exception) as exc: await verifier.signing_key({"alg": "RS256", "kid": "A"})
    assert getattr(exc.value, "status_code", None) == 503 and calls == 3


@pytest.mark.anyio
async def test_unknown_cooldown_starts_at_completion_and_allows_later_rotation() -> None:
    calls = 0; clock = Clock()
    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls; calls += 1; clock.advance(6)
        return httpx.Response(200, content=_jwks("B"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client, clock)
        await verifier.signing_key({"alg": "RS256", "kid": "B"})
        with pytest.raises(Exception): await verifier.signing_key({"alg": "RS256", "kid": "C"})
        clock.advance(5)
        with pytest.raises(Exception): await verifier.signing_key({"alg": "RS256", "kid": "C"})
    assert calls == 2


@pytest.mark.anyio
@pytest.mark.parametrize("body", [b'{"keys": []}', b"not json", b"x" * (256 * 1024 + 1)])
async def test_invalid_or_oversized_jwks_fails_closed(body: bytes) -> None:
    async def handler(_: httpx.Request) -> httpx.Response: return httpx.Response(200, content=body)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(Exception) as exc: await OIDCVerifier(_settings(), client).signing_key({"alg": "RS256", "kid": "A"})
    assert getattr(exc.value, "status_code", None) == 503
