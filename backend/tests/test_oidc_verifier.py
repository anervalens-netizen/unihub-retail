from __future__ import annotations

import asyncio
import json

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import oidc_verifier
from oidc_settings import OIDCVerifierSettings
from oidc_verifier import OIDCVerifier, _MAX_BODY, _safe_text


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class Stream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], failure: Exception | None = None) -> None:
        self.chunks, self.failure, self.closed = chunks, failure, False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
        if self.failure is not None:
            raise self.failure

    async def aclose(self) -> None:
        self.closed = True


def _settings(**changes: float | int) -> OIDCVerifierSettings:
    values: dict[str, float | int] = {
        "cache_ttl_seconds": 10.0, "max_stale_seconds": 30.0, "fetch_timeout_seconds": 1.0,
        "clock_skew_seconds": 0, "unknown_kid_refresh_cooldown_seconds": 5.0,
        "refresh_failure_retry_seconds": 5.0,
    }
    values.update(changes)
    return OIDCVerifierSettings(
        "https://issuer.example.invalid", "https://issuer.example.invalid/jwks", "test",
        float(values["cache_ttl_seconds"]), float(values["max_stale_seconds"]),
        float(values["fetch_timeout_seconds"]), int(values["clock_skew_seconds"]),
        float(values["unknown_kid_refresh_cooldown_seconds"]), float(values["refresh_failure_retry_seconds"]),
    )


def _jwk(kid: str = "A") -> dict[str, object]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    value: dict[str, object] = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    value.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return value


def _jwks(kid: str = "A") -> bytes:
    return json.dumps({"keys": [_jwk(kid)]}).encode()


async def _key(verifier: OIDCVerifier, kid: str = "A") -> jwt.PyJWK:
    return await verifier.signing_key({"alg": "RS256", "kid": kid})


@pytest.mark.anyio
async def test_readiness_prewarms_jwks_before_the_first_token() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_jwks())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client)
        await verifier.ensure_ready()
        await verifier.ensure_ready()
        assert verifier.cache is not None
        assert await _key(verifier)
    assert calls == 1


@pytest.mark.anyio
async def test_readiness_fails_without_cache_and_accepts_bounded_stale_cache() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_jwks()) if calls == 1 else httpx.Response(503)

    clock = Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client, clock)
        await verifier.ensure_ready()
        clock.advance(10)
        await verifier.ensure_ready()
        assert verifier.cache is not None
        clock.advance(21)
        with pytest.raises(Exception) as unavailable:
            await verifier.ensure_ready()
    assert getattr(unavailable.value, "status_code", None) == 503
    assert calls == 3


@pytest.mark.anyio
async def test_readiness_refresh_timeout_uses_bounded_stale_cache() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls > 1:
            await asyncio.sleep(1)
        return httpx.Response(200, content=_jwks())

    clock = Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client, clock)
        await verifier.ensure_ready()
        clock.advance(10)
        await verifier.ensure_ready(refresh_timeout_seconds=0.001)

    assert verifier.cache is not None
    assert verifier.last_refresh_outcome == "failure"
    assert calls == 2


@pytest.mark.anyio
async def test_concurrent_readiness_rechecks_fresh_cache_inside_lock() -> None:
    calls = 0
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return httpx.Response(200, content=_jwks())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client)
        first = asyncio.create_task(verifier.ensure_ready())
        await entered.wait()
        second = asyncio.create_task(verifier.ensure_ready())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, second)

    assert calls == 1


@pytest.mark.anyio
async def test_readiness_failure_backoff_accepts_stale_then_fails_closed() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_jwks()) if calls == 1 else httpx.Response(503)

    clock = Clock()
    settings = _settings(cache_ttl_seconds=0.5, max_stale_seconds=1.0)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(settings, client, clock)
        await verifier.ensure_ready()
        clock.advance(0.5)
        await verifier.ensure_ready()
        await verifier.ensure_ready()
        clock.advance(0.6)
        with pytest.raises(Exception) as unavailable:
            await verifier.ensure_ready()

    assert getattr(unavailable.value, "status_code", None) == 503
    assert calls == 2


@pytest.mark.anyio
async def test_readiness_timeout_without_cache_is_unavailable() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, content=_jwks())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client)
        with pytest.raises(Exception) as unavailable:
            await verifier.ensure_ready(refresh_timeout_seconds=0.001)

    assert getattr(unavailable.value, "status_code", None) == 503


@pytest.mark.anyio
async def test_runtime_prewarm_failure_is_degraded_and_closed_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable(*_args: object, **_kwargs: object) -> None:
        raise oidc_verifier._unavailable()

    monkeypatch.setattr(oidc_verifier, "_client", None)
    monkeypatch.setattr(oidc_verifier, "_verifier", None)
    monkeypatch.setattr(oidc_verifier, "load_oidc_verifier_settings", _settings)
    monkeypatch.setattr(OIDCVerifier, "ensure_ready", unavailable)

    await oidc_verifier.init_oidc_runtime()
    assert oidc_verifier._verifier is not None
    await oidc_verifier.close_oidc_runtime()
    assert oidc_verifier._verifier is None


@pytest.mark.anyio
async def test_runtime_readiness_distinguishes_disabled_absent_and_failed_jwks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oidc_verifier, "_verifier", None)
    monkeypatch.setattr(oidc_verifier, "load_oidc_verifier_settings", lambda: None)
    await oidc_verifier.verify_oidc_runtime_ready()

    monkeypatch.setattr(oidc_verifier, "load_oidc_verifier_settings", _settings)
    with pytest.raises(RuntimeError, match="verifier unavailable"):
        await oidc_verifier.verify_oidc_runtime_ready()

    class FailedVerifier:
        async def ensure_ready(self, **_kwargs: object) -> None:
            raise oidc_verifier._unavailable()

    monkeypatch.setattr(oidc_verifier, "_verifier", FailedVerifier())
    with pytest.raises(RuntimeError, match="JWKS unavailable"):
        await oidc_verifier.verify_oidc_runtime_ready()


@pytest.mark.anyio
async def test_runtime_readiness_allows_provider_response_inside_probe_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.6)
        return httpx.Response(200, content=_jwks())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(fetch_timeout_seconds=2.0), client)
        monkeypatch.setattr(oidc_verifier, "_verifier", verifier)
        await oidc_verifier.verify_oidc_runtime_ready()


@pytest.mark.parametrize("value,valid", [("A", True), ("", False), ("has space", False), ("x" * 257, False), (1, False), (None, False)])
def test_safe_text_contract(value: object, valid: bool) -> None:
    assert _safe_text(value) is valid


@pytest.mark.anyio
async def test_rotation_a_to_b_has_one_http_refresh_for_twenty_concurrent_requests() -> None:
    calls = 0
    release = asyncio.Event()

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            await release.wait()
        return httpx.Response(200, content=_jwks("A" if calls == 1 else "B"))

    clock = Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client, clock)
        await _key(verifier, "A")
        clock.advance(10)
        waiting = asyncio.gather(*[_key(verifier, "B") for _ in range(20)])
        await asyncio.sleep(0)
        release.set()
        result = await waiting
    assert calls == 2 and len(result) == 20


@pytest.mark.anyio
async def test_fresh_cache_and_invalid_header_do_not_fetch_again() -> None:
    calls = 0
    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_jwks())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client)
        await _key(verifier)
        assert await _key(verifier)
        for header in ({"alg": "HS256", "kid": "A"}, {"alg": "RS256", "kid": " bad"}):
            with pytest.raises(Exception) as exc:
                await verifier.signing_key(header)
            assert getattr(exc.value, "status_code", None) == 401
    assert calls == 1


@pytest.mark.anyio
async def test_concurrent_unknown_refresh_that_does_not_contain_kid_is_invalid_once() -> None:
    calls = 0
    release = asyncio.Event()
    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            await release.wait()
        return httpx.Response(200, content=_jwks("A"))
    clock = Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client, clock)
        await _key(verifier)
        clock.advance(5)
        waiting = asyncio.gather(*[_key(verifier, "missing") for _ in range(20)], return_exceptions=True)
        await asyncio.sleep(0)
        release.set()
        values = await waiting
    assert calls == 2 and all(getattr(value, "status_code", None) == 401 for value in values)


@pytest.mark.anyio
async def test_failure_is_single_flight_then_backoff_and_new_fetch_after_expiry() -> None:
    calls = 0
    release = asyncio.Event()

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            await release.wait()
            return httpx.Response(503)
        return httpx.Response(200, content=_jwks("A"))

    clock = Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client, clock)
        await _key(verifier)
        clock.advance(10)
        waiting = asyncio.gather(*[_key(verifier) for _ in range(20)])
        await asyncio.sleep(0)
        release.set()
        assert len(await waiting) == 20
        for _ in range(20):
            await _key(verifier)
        assert calls == 2
        clock.advance(5)
        await _key(verifier)
    assert calls == 3


@pytest.mark.anyio
async def test_stale_boundary_is_inclusive_and_immediately_after_is_unavailable() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_jwks()) if calls == 1 else httpx.Response(503)

    clock = Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client, clock)
        await _key(verifier)
        clock.advance(30)
        assert await _key(verifier)
        clock.advance(0.001)
        with pytest.raises(Exception) as exc:
            await _key(verifier)
    assert getattr(exc.value, "status_code", None) == 503 and calls == 2


@pytest.mark.anyio
async def test_one_hundred_unknown_kids_are_bounded_by_completion_cooldown_and_legitimate_rotation_follows() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_jwks("A" if calls == 1 else "B" if calls == 2 else "C"))

    clock = Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OIDCVerifier(_settings(), client, clock)
        await _key(verifier, "A")
        clock.advance(5)
        for value in range(100):
            with pytest.raises(Exception) as exc:
                await _key(verifier, f"unknown-{value}")
            assert getattr(exc.value, "status_code", None) == 401
        assert calls == 2
        clock.advance(5)
        assert await _key(verifier, "C")
    assert calls == 3


@pytest.mark.anyio
async def test_jwks_body_exact_limit_is_accepted_and_over_limit_is_closed() -> None:
    accepted = _jwks()
    accepted += b" " * (_MAX_BODY - len(accepted))
    streams: list[Stream] = []

    async def handler(_: httpx.Request) -> httpx.Response:
        stream = Stream([accepted])
        streams.append(stream)
        return httpx.Response(200, stream=stream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await _key(OIDCVerifier(_settings(), client))
    assert streams[0].closed

    for chunks in ([b"x" * (_MAX_BODY + 1)], [b"x" * 1024] * 257):
        stream = Stream(chunks)
        async def oversized(_: httpx.Request, stream: Stream = stream) -> httpx.Response:
            return httpx.Response(200, stream=stream)
        async with httpx.AsyncClient(transport=httpx.MockTransport(oversized)) as client:
            with pytest.raises(Exception) as exc:
                await _key(OIDCVerifier(_settings(), client))
        assert getattr(exc.value, "status_code", None) == 503 and stream.closed


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body,headers",
    [
        (b"not-json", {}), (b'{"keys": []}', {}), (b"[]", {}),
        (json.dumps({"keys": [dict(_jwk(), kid="")] }).encode(), {}),
        (json.dumps({"keys": [dict(_jwk(), kty="EC")] }).encode(), {}),
        (json.dumps({"keys": [dict(_jwk(), use="enc")] }).encode(), {}),
        (json.dumps({"keys": [dict(_jwk(), alg="HS256")] }).encode(), {}),
        (json.dumps({"keys": [_jwk(), _jwk()] }).encode(), {}),
        (_jwks(), {"content-length": "wat"}), (_jwks(), {"content-length": str(_MAX_BODY + 1)}),
    ],
)
async def test_invalid_jwks_forms_and_content_length_fail_closed(body: bytes, headers: dict[str, str]) -> None:
    stream = Stream([body])
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=headers, stream=stream)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(Exception) as exc:
            await _key(OIDCVerifier(_settings(), client))
    assert getattr(exc.value, "status_code", None) == 503 and stream.closed


@pytest.mark.anyio
@pytest.mark.parametrize("response_or_error", [301, 400, 500, httpx.ReadTimeout("timeout"), httpx.ConnectError("connection")])
async def test_redirect_http_timeout_and_connection_errors_are_unavailable(response_or_error: int | Exception) -> None:
    stream = Stream([_jwks()], RuntimeError("stream failed") if response_or_error == 500 else None)
    async def handler(_: httpx.Request) -> httpx.Response:
        if isinstance(response_or_error, Exception):
            raise response_or_error
        return httpx.Response(response_or_error, stream=stream)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(Exception) as exc:
            await _key(OIDCVerifier(_settings(), client))
    assert getattr(exc.value, "status_code", None) == 503


@pytest.mark.anyio
async def test_stream_failure_closes_response() -> None:
    stream = Stream([b"{"], RuntimeError("read failed"))
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(Exception):
            await _key(OIDCVerifier(_settings(), client))
    assert stream.closed
