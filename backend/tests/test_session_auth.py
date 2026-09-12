from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.fernet import Fernet
from starlette.requests import Request

import session_auth
from auth import AuthClaims
from session_auth import SessionSettings


KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.closed = False

    async def set(self, key: str, value: bytes, **_kwargs: object) -> bool:
        if _kwargs.get("nx") and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def getdel(self, key: str) -> bytes | None:
        return self.values.pop(key, None)

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def eval(
        self,
        _script: str,
        _keys: int,
        key: str,
        token: str | bytes,
    ) -> int:
        expected = token if isinstance(token, bytes) else token.encode("ascii")
        if self.values.get(key) != expected:
            return 0
        return int(self.values.pop(key, None) is not None)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self.closed = True


class FakeHttp:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload or {}
        self.posts: list[tuple[str, dict[str, object]]] = []
        self.closed = False

    async def post(self, url: str, data: dict[str, object]) -> httpx.Response:
        self.posts.append((url, data))
        return httpx.Response(200, json=self.payload)

    async def aclose(self) -> None:
        self.closed = True


def _settings(production: bool = True) -> SessionSettings:
    return SessionSettings(
        "redis://localhost:6379/14", KEY, "retail", "synthetic-client-secret",
        "https://retail.example.invalid", "https://auth.example.invalid/application/o/unihub-retail",
        3600, production,
    )


def _install(redis: FakeRedis, http: FakeHttp | None = None) -> None:
    session_auth._session_closing = False
    session_auth._local_refresh_tasks.clear()
    session_auth._settings = _settings()
    session_auth._redis = redis  # type: ignore[assignment]
    session_auth._cipher = Fernet(KEY.encode("ascii"))
    session_auth._http = http or FakeHttp()  # type: ignore[assignment]


def _request(
    method: str,
    cookie: str,
    csrf: str | None = None,
    query: bytes = b"",
    extra_cookies: dict[str, str] | None = None,
) -> Request:
    cookies = {session_auth.COOKIE_NAME: cookie}
    if extra_cookies:
        cookies.update(extra_cookies)
    cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
    headers = [(b"cookie", cookie_header.encode())]
    if csrf is not None:
        headers.append((b"x-csrf-token", csrf.encode()))
    return Request({
        "type": "http", "method": method, "path": "/", "query_string": query,
        "headers": headers, "client": ("127.0.0.1", 1), "scheme": "https",
        "server": ("retail.example.invalid", 443),
    })


def _request_without_session_cookie() -> Request:
    """A browser that already dropped the session cookie kept its unrelated cookies."""
    return Request({
        "type": "http", "method": "POST", "path": "/", "query_string": b"",
        "headers": [(b"cookie", b"__Host-unihub_oidc_flow_unrelated=kept")],
        "client": ("127.0.0.1", 1), "scheme": "https",
        "server": ("retail.example.invalid", 443),
    })


def _flow_state(response: session_auth.RedirectResponse) -> str:
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def _flow_cookie_name(state: str) -> str:
    return session_auth._flow_cookie_name(_settings(), state)


def _flow_cookie_value(response: session_auth.RedirectResponse, state: str) -> str:
    marker = _flow_cookie_name(state) + "="
    return response.headers["set-cookie"].split(marker, 1)[1].split(";", 1)[0]


async def _store_bound_flow(
    redis: FakeRedis,
    state: str,
    binding: str,
    *,
    nonce: str = "nonce",
    verifier: str = "verifier",
) -> None:
    cipher = session_auth._cipher
    assert cipher is not None
    await redis.set(
        session_auth.FLOW_PREFIX + state,
        session_auth._pack(cipher, {
            "nonce": nonce,
            "verifier": verifier,
            "browser_binding_hash": session_auth._flow_binding_digest(binding),
        }),
    )


def test_session_settings_use_provider_endpoints_not_issuer_children() -> None:
    settings = _settings()
    assert settings.authorize_url == "https://auth.example.invalid/application/o/authorize/"
    assert settings.token_url == "https://auth.example.invalid/application/o/token/"
    assert settings.redirect_uri == "https://retail.example.invalid/auth/callback"


def test_refresh_singleflight_window_is_bounded_below_browser_timeout() -> None:
    assert session_auth.REFRESH_OWNER_TIMEOUT_SECONDS < 15
    assert session_auth.REFRESH_OWNER_TIMEOUT_SECONDS < session_auth.REFRESH_LOCK_TTL_SECONDS
    assert session_auth.REFRESH_WAIT_SECONDS <= 2
    assert session_auth.REFRESH_WAIT_SECONDS < session_auth.REFRESH_OWNER_TIMEOUT_SECONDS


def test_production_session_settings_fail_closed_without_leaking_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "UNIHUB_ENV": "production",
        "SESSION_ENCRYPTION_KEY": KEY,
        "OIDC_CLIENT_ID": "retail",
        "OIDC_AUDIENCE": "api-audience",
        "OIDC_CLIENT_SECRET": "synthetic-client-secret",
        "OIDC_ISSUER": "https://auth.example.invalid/application/o/unihub-retail/",
        "SESSION_PUBLIC_ORIGIN": "https://retail.example.invalid",
        "SESSION_VALKEY_URL": "redis://localhost:6379/14",
        "SESSION_TTL_SECONDS": "900",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    assert session_auth.load_session_settings() is not None
    for missing in (
        "SESSION_ENCRYPTION_KEY", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET",
        "OIDC_ISSUER", "SESSION_PUBLIC_ORIGIN", "SESSION_VALKEY_URL",
    ):
        with monkeypatch.context() as scoped:
            scoped.delenv(missing)
            if missing == "SESSION_VALKEY_URL":
                scoped.delenv("VALKEY_URL", raising=False)
            with pytest.raises(ValueError) as exc_info:
                session_auth.load_session_settings()
            assert all(value not in str(exc_info.value) for value in values.values())
    for invalid_ttl in ("899", "7776001", "nan"):
        monkeypatch.setenv("SESSION_TTL_SECONDS", invalid_ttl)
        with pytest.raises(ValueError, match="configuration is invalid"):
            session_auth.load_session_settings()


def test_session_settings_can_route_to_non_persistent_valkey(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "UNIHUB_ENV": "production",
        "SESSION_ENCRYPTION_KEY": KEY,
        "OIDC_CLIENT_ID": "retail",
        "OIDC_CLIENT_SECRET": "synthetic-client-secret",
        "OIDC_ISSUER": "https://auth.example.invalid/application/o/unihub-retail/",
        "SESSION_PUBLIC_ORIGIN": "https://retail.example.invalid",
        "SESSION_VALKEY_URL": "redis://service:p%40ssword@localhost:6379/7",
        "SESSION_VALKEY_PORT": "6380",
        "SESSION_VALKEY_DATABASE": "0",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    settings = session_auth.load_session_settings()

    assert settings is not None
    assert settings.valkey_url == "redis://service:p%40ssword@localhost:6380/0"


def test_generic_browser_auth_proxy_is_removed() -> None:
    content = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "/auth/proxy/{path:path}" not in content
    assert "client_secret injection" not in content


@pytest.mark.anyio
async def test_login_stores_encrypted_pkce_flow_and_redirects() -> None:
    redis = FakeRedis()
    _install(redis)
    response = await session_auth.session_login()
    assert response.status_code == 302
    assert "code_challenge_method=S256" in response.headers["location"]
    assert "client_secret" not in response.headers["location"]
    assert len(redis.values) == 1
    ciphertext = next(iter(redis.values.values()))
    assert b"verifier" not in ciphertext and b"nonce" not in ciphertext


@pytest.mark.anyio
async def test_login_sets_distinct_browser_binding_cookie_for_parallel_flows() -> None:
    redis = FakeRedis()
    _install(redis)

    first = await session_auth.session_login()
    second = await session_auth.session_login()
    first_state, second_state = _flow_state(first), _flow_state(second)
    first_binding = _flow_cookie_value(first, first_state)
    second_binding = _flow_cookie_value(second, second_state)

    assert first_state != second_state
    assert _flow_cookie_name(first_state) != _flow_cookie_name(second_state)
    assert first_binding != second_binding
    assert len(redis.values) == 2
    for response, state, binding in (
        (first, first_state, first_binding),
        (second, second_state, second_binding),
    ):
        cookie = response.headers["set-cookie"]
        assert _flow_cookie_name(state) + "=" in cookie
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
        assert f"Max-Age={session_auth.FLOW_TTL_SECONDS}" in cookie
        cipher = session_auth._cipher
        assert cipher is not None
        flow = session_auth._unpack(cipher, redis.values[session_auth.FLOW_PREFIX + state])
        assert flow is not None
        assert flow["browser_binding_hash"] == session_auth._flow_binding_digest(binding)
        assert binding.encode() not in redis.values[session_auth.FLOW_PREFIX + state]


@pytest.mark.anyio
async def test_session_authentication_enforces_csrf_without_exposing_tokens() -> None:
    redis = FakeRedis()
    _install(redis)
    session_id, csrf = "s" * 43, "csrf-value"
    record = {
        "sub": "subject", "email": "user@example.invalid", "preferred_username": "user",
        "groups": ["unihub-manager"], "iss": "issuer", "aud": "retail",
        "iat": int(time.time()) - 1, "exp": int(time.time()) + 600,
        "refresh_token": "private-refresh-token", "csrf": csrf,
    }
    await session_auth._store_session(session_id, record)
    assert b"private-refresh-token" not in redis.values[session_auth.SESSION_PREFIX + session_id]
    assert (await session_auth.authenticate_session(_request("GET", session_id))).sub == "subject"
    with pytest.raises(session_auth.HTTPException) as denied:
        await session_auth.authenticate_session(_request("POST", session_id))
    assert denied.value.status_code == 403
    assert (await session_auth.authenticate_session(_request("POST", session_id, csrf))).sub == "subject"


@pytest.mark.anyio
async def test_callback_consumes_state_sets_host_cookie_and_stores_only_encrypted_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    http = FakeHttp({
        "access_token": "private-access-token",
        "id_token": "private-id-token",
        "refresh_token": "private-refresh-token",
    })
    _install(redis, http)
    state, binding = "t" * 43, "b" * 43
    await _store_bound_flow(redis, state, binding)
    claims = AuthClaims(
        "subject", "user@example.invalid", "user", ["unihub-manager"],
        "issuer", "retail", int(time.time()) - 1, int(time.time()) + 600, {},
    )
    verify = AsyncMock(return_value=claims)
    monkeypatch.setattr(session_auth, "verify_oidc_token", verify)
    response = await session_auth.session_callback(_request(
        "GET",
        "x" * 43,
        query=f"code=code&state={state}".encode(),
        extra_cookies={_flow_cookie_name(state): binding},
    ))
    cookie = response.headers["set-cookie"]
    assert response.status_code == 303
    assert "__Host-unihub_session=" in cookie
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert session_auth.FLOW_PREFIX + state not in redis.values
    session_values = [value for key, value in redis.values.items() if key.startswith(session_auth.SESSION_PREFIX)]
    assert len(session_values) == 1
    assert all(token not in session_values[0] for token in (b"private-access-token", b"private-id-token", b"private-refresh-token"))
    assert verify.await_count == 2
    assert verify.await_args_list[0].args == ("private-access-token",)
    assert verify.await_args_list[0].kwargs == {}
    assert verify.await_args_list[1].args == ("private-id-token",)
    assert verify.await_args_list[1].kwargs == {
        "nonce": "nonce",
        "audience": "retail",
    }


@pytest.mark.anyio
async def test_foreign_browser_callback_cannot_consume_valid_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    http = FakeHttp({
        "access_token": "access-token",
        "id_token": "id-token",
        "refresh_token": "refresh-token",
    })
    _install(redis, http)
    login = await session_auth.session_login()
    state = _flow_state(login)
    binding = _flow_cookie_value(login, state)
    flow_key = session_auth.FLOW_PREFIX + state

    with pytest.raises(session_auth.HTTPException) as missing:
        await session_auth.session_callback(_request(
            "GET", "x" * 43, query=f"code=code&state={state}".encode(),
        ))
    assert missing.value.status_code == 400
    assert flow_key in redis.values

    with pytest.raises(session_auth.HTTPException) as wrong:
        await session_auth.session_callback(_request(
            "GET",
            "x" * 43,
            query=f"code=code&state={state}".encode(),
            extra_cookies={_flow_cookie_name(state): "z" * 43},
        ))
    assert wrong.value.status_code == 400
    assert flow_key in redis.values
    assert http.posts == []

    claims = AuthClaims(
        "subject", "user@example.invalid", "user", ["unihub-manager"],
        "issuer", "retail", int(time.time()) - 1, int(time.time()) + 600, {},
    )
    monkeypatch.setattr(session_auth, "verify_oidc_token", AsyncMock(return_value=claims))
    valid_request = _request(
        "GET",
        "x" * 43,
        query=f"code=code&state={state}".encode(),
        extra_cookies={_flow_cookie_name(state): binding},
    )
    result = await session_auth.session_callback(valid_request)
    assert result.status_code == 303
    assert flow_key not in redis.values
    assert len(http.posts) == 1

    with pytest.raises(session_auth.HTTPException) as replay:
        await session_auth.session_callback(valid_request)
    assert replay.value.status_code == 400
    assert len(http.posts) == 1


@pytest.mark.anyio
async def test_parallel_browser_bound_flows_can_complete_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    http = FakeHttp({
        "access_token": "access-token",
        "id_token": "id-token",
        "refresh_token": "refresh-token",
    })
    _install(redis, http)
    first = await session_auth.session_login()
    second = await session_auth.session_login()
    first_state, second_state = _flow_state(first), _flow_state(second)
    first_binding = _flow_cookie_value(first, first_state)
    second_binding = _flow_cookie_value(second, second_state)
    claims = AuthClaims(
        "subject", "user@example.invalid", "user", ["unihub-manager"],
        "issuer", "retail", int(time.time()) - 1, int(time.time()) + 600, {},
    )
    monkeypatch.setattr(session_auth, "verify_oidc_token", AsyncMock(return_value=claims))

    first_result = await session_auth.session_callback(_request(
        "GET",
        "x" * 43,
        query=f"code=first&state={first_state}".encode(),
        extra_cookies={_flow_cookie_name(first_state): first_binding},
    ))
    assert first_result.status_code == 303
    assert session_auth.FLOW_PREFIX + second_state in redis.values

    second_result = await session_auth.session_callback(_request(
        "GET",
        "x" * 43,
        query=f"code=second&state={second_state}".encode(),
        extra_cookies={_flow_cookie_name(second_state): second_binding},
    ))
    assert second_result.status_code == 303
    assert len(http.posts) == 2
    assert not any(key.startswith(session_auth.FLOW_PREFIX) for key in redis.values)
    assert sum(key.startswith(session_auth.SESSION_PREFIX) for key in redis.values) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("changed_field", ["sub", "iss"])
async def test_callback_rejects_identity_mismatch_between_access_and_id_token(
    monkeypatch: pytest.MonkeyPatch,
    changed_field: str,
) -> None:
    redis = FakeRedis()
    _install(redis, FakeHttp({
        "access_token": "access-token",
        "id_token": "id-token",
        "refresh_token": "refresh-token",
    }))
    state, binding = "i" * 43, "c" * 43
    await _store_bound_flow(redis, state, binding)
    now = int(time.time())
    access_claims = AuthClaims(
        "subject-a", "", "", [], "issuer-a", "retail", now, now + 600, {},
    )
    id_claims = AuthClaims(
        "subject-b" if changed_field == "sub" else "subject-a",
        "",
        "",
        [],
        "issuer-b" if changed_field == "iss" else "issuer-a",
        "retail",
        now,
        now + 600,
        {},
    )
    monkeypatch.setattr(
        session_auth,
        "verify_oidc_token",
        AsyncMock(side_effect=[access_claims, id_claims]),
    )

    with pytest.raises(session_auth.HTTPException) as rejected:
        await session_auth.session_callback(_request(
            "GET",
            "x" * 43,
            query=f"code=code&state={state}".encode(),
            extra_cookies={_flow_cookie_name(state): binding},
        ))

    assert rejected.value.status_code == 502
    assert not any(key.startswith(session_auth.SESSION_PREFIX) for key in redis.values)


@pytest.mark.anyio
async def test_expired_concurrent_session_requests_singleflight_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()

    class SlowHttp(FakeHttp):
        async def post(self, url: str, data: dict[str, object]) -> httpx.Response:
            await asyncio.sleep(0.2)
            return await super().post(url, data)

    http = SlowHttp({"access_token": "rotated-access", "refresh_token": "rotated-refresh"})
    _install(redis, http)
    session_id, csrf = "r" * 43, "csrf"
    old = AuthClaims(
        "subject", "user@example.invalid", "user", ["unihub-manager"],
        "issuer", "retail", int(time.time()) - 600, int(time.time()) - 1, {},
    )
    await session_auth._store_session(session_id, {**session_auth.asdict(old), "refresh_token": "old-refresh", "csrf": csrf})
    refreshed = AuthClaims(
        "subject", "user@example.invalid", "user", ["unihub-manager"],
        "issuer", "retail", int(time.time()), int(time.time()) + 600, {},
    )
    monkeypatch.setattr(session_auth, "verify_oidc_token", AsyncMock(return_value=refreshed))
    claims = await asyncio.gather(*[
        session_auth.authenticate_session(_request("GET", session_id))
        for _index in range(20)
    ])
    assert {claim.sub for claim in claims} == {"subject"}
    assert len(http.posts) == 1
    stored = session_auth._unpack(session_auth._cipher, redis.values[session_auth.SESSION_PREFIX + session_id])  # type: ignore[arg-type]
    assert stored and stored["refresh_token"] == "rotated-refresh"


@pytest.mark.anyio
async def test_refresh_rejects_subject_change_and_invalidates_expired_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    _install(redis, FakeHttp({"access_token": "rotated-access"}))
    now = int(time.time())
    session_id = "j" * 43
    record = {
        "sub": "subject-a",
        "email": "",
        "preferred_username": "",
        "groups": [],
        "iss": "issuer",
        "aud": "retail",
        "iat": now - 600,
        "exp": now - 1,
        "refresh_token": "refresh-token",
        "csrf": "csrf",
    }
    await session_auth._store_session(session_id, record)
    monkeypatch.setattr(
        session_auth,
        "verify_oidc_token",
        AsyncMock(
            return_value=AuthClaims(
                "subject-b", "", "", [], "issuer", "retail", now, now + 600, {},
            )
        ),
    )

    with pytest.raises(session_auth.HTTPException) as rejected:
        await session_auth.authenticate_session(_request("GET", session_id))

    assert rejected.value.status_code == 401
    assert session_auth.SESSION_PREFIX + session_id not in redis.values


@pytest.mark.anyio
async def test_shutdown_drains_refresh_tasks_before_closing_clients() -> None:
    redis = FakeRedis()
    http = FakeHttp()
    _install(redis, http)
    release = asyncio.Event()

    async def refresh_in_flight() -> None:
        await release.wait()

    task = asyncio.create_task(refresh_in_flight())
    session_auth._local_refresh_tasks["shutdown-test"] = task  # type: ignore[assignment]
    closing = asyncio.create_task(session_auth.close_session_runtime())
    await asyncio.sleep(0)

    assert not redis.closed
    assert not http.closed
    release.set()
    await closing

    assert redis.closed
    assert http.closed
    assert session_auth._local_refresh_tasks == {}


@pytest.mark.anyio
async def test_slow_session_refresh_fails_waiters_fast_without_herding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()

    class SlowHttp(FakeHttp):
        async def post(self, url: str, data: dict[str, object]) -> httpx.Response:
            await asyncio.sleep(2.2)
            return await super().post(url, data)

    http = SlowHttp({"access_token": "rotated-access", "refresh_token": "rotated-refresh"})
    _install(redis, http)
    session_id = "w" * 43
    old = AuthClaims(
        "subject", "user@example.invalid", "user", ["unihub-manager"],
        "issuer", "retail", int(time.time()) - 600, int(time.time()) - 1, {},
    )
    await session_auth._store_session(
        session_id,
        {**session_auth.asdict(old), "refresh_token": "old-refresh", "csrf": "csrf"},
    )
    refreshed = AuthClaims(
        "subject", "user@example.invalid", "user", ["unihub-manager"],
        "issuer", "retail", int(time.time()), int(time.time()) + 600, {},
    )
    monkeypatch.setattr(session_auth, "verify_oidc_token", AsyncMock(return_value=refreshed))

    owner = asyncio.create_task(
        session_auth.authenticate_session(_request("GET", session_id)),
    )
    await asyncio.sleep(0)
    started = time.monotonic()
    waiters = await asyncio.gather(
        *(
            session_auth.authenticate_session(_request("GET", session_id))
            for _ in range(12)
        ),
        return_exceptions=True,
    )
    elapsed = time.monotonic() - started
    claims = await owner

    assert claims.sub == "subject"
    assert elapsed < 1.5
    assert all(
        isinstance(result, session_auth.HTTPException)
        and result.status_code == 503
        and result.headers == {"Retry-After": "2"}
        for result in waiters
    )
    assert len(http.posts) == 1
    assert session_auth.SESSION_PREFIX + session_id in redis.values


@pytest.mark.anyio
async def test_refresh_waiter_rechecks_session_after_lock_release() -> None:
    session_id = "q" * 43
    session_key = session_auth.SESSION_PREFIX + session_id
    lock_key = session_auth.LOCK_PREFIX + session_id

    class ReleaseBetweenReadsRedis(FakeRedis):
        async def get(self, key: str) -> bytes | None:
            if key == lock_key and key in self.values:
                self.values.pop(lock_key)
                assert session_auth._cipher is not None
                self.values[session_key] = session_auth._pack(
                    session_auth._cipher,
                    refreshed,
                )
                return None
            return await super().get(key)

    redis = ReleaseBetweenReadsRedis()
    _install(redis)
    now = int(time.time())
    expired = {
        "sub": "subject",
        "email": "user@example.invalid",
        "preferred_username": "user",
        "groups": ["unihub-manager"],
        "iss": "issuer",
        "aud": "retail",
        "iat": now - 600,
        "exp": now - 1,
        "refresh_token": "old-refresh",
        "csrf": "csrf",
    }
    refreshed = {**expired, "iat": now, "exp": now + 600}
    await session_auth._store_session(session_id, expired)
    redis.values[lock_key] = b"other-owner"

    result = await session_auth._refresh(session_id, expired)

    assert result == refreshed


@pytest.mark.anyio
async def test_refresh_waiter_timeout_preserves_owner_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    _install(redis)
    now = int(time.time())
    session_id = "v" * 43
    session_key = session_auth.SESSION_PREFIX + session_id
    lock_key = session_auth.LOCK_PREFIX + session_id
    expired = {
        "sub": "subject",
        "email": "user@example.invalid",
        "preferred_username": "user",
        "groups": ["unihub-manager"],
        "iss": "issuer",
        "aud": "retail",
        "iat": now - 600,
        "exp": now - 1,
        "refresh_token": "old-refresh",
        "csrf": "csrf",
    }
    await session_auth._store_session(session_id, expired)
    redis.values[lock_key] = b"other-owner"
    monkeypatch.setattr(session_auth, "REFRESH_WAIT_SECONDS", 0.01)
    monkeypatch.setattr(session_auth, "REFRESH_POLL_SECONDS", 0.001)

    with pytest.raises(session_auth.HTTPException) as unavailable:
        await session_auth.authenticate_session(_request("GET", session_id))

    assert unavailable.value.status_code == 503
    assert unavailable.value.headers == {"Retry-After": "2"}
    assert session_key in redis.values
    assert redis.values[lock_key] == b"other-owner"


@pytest.mark.anyio
async def test_refresh_owner_work_is_bounded_below_lock_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()

    class SlowHttp(FakeHttp):
        async def post(self, url: str, data: dict[str, object]) -> httpx.Response:
            await asyncio.sleep(0.05)
            return await super().post(url, data)

    _install(redis, SlowHttp({"access_token": "late-access"}))
    session_id = "o" * 43
    lock_key = session_auth.LOCK_PREFIX + session_id
    monkeypatch.setattr(session_auth, "REFRESH_OWNER_TIMEOUT_SECONDS", 0.01)

    result = await session_auth._refresh(
        session_id,
        {"refresh_token": "old-refresh"},
    )

    assert result is None
    assert lock_key not in redis.values


@pytest.mark.anyio
async def test_failed_refresh_cannot_delete_concurrently_rotated_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "z" * 43
    session_key = session_auth.SESSION_PREFIX + session_id
    now = int(time.time())
    expired = {
        "sub": "subject",
        "email": "user@example.invalid",
        "preferred_username": "user",
        "groups": ["unihub-manager"],
        "iss": "issuer",
        "aud": "retail",
        "iat": now - 600,
        "exp": now - 1,
        "refresh_token": "old-refresh",
        "csrf": "csrf",
    }
    refreshed = {**expired, "iat": now, "exp": now + 600}

    class RotateBeforeCompareRedis(FakeRedis):
        rotate = False

        async def eval(
            self,
            script: str,
            keys: int,
            key: str,
            token: str | bytes,
        ) -> int:
            if self.rotate and key == session_key:
                assert session_auth._cipher is not None
                self.values[session_key] = session_auth._pack(
                    session_auth._cipher,
                    refreshed,
                )
                self.rotate = False
            return await super().eval(script, keys, key, token)

    redis = RotateBeforeCompareRedis()
    _install(redis)
    await session_auth._store_session(session_id, expired)
    redis.rotate = True
    monkeypatch.setattr(session_auth, "_refresh", AsyncMock(return_value=None))

    claims = await session_auth.authenticate_session(_request("GET", session_id))

    assert claims.sub == "subject"
    stored = session_auth._unpack(session_auth._cipher, redis.values[session_key])  # type: ignore[arg-type]
    assert stored is not None and stored["exp"] == refreshed["exp"]


LOGOUT_URL = (
    "https://auth.example.invalid/application/o/unihub-retail/end-session/"
    "?post_logout_redirect_uri=https%3A%2F%2Fretail.example.invalid%2F"
)


def _session_record(*, expires_in: int = 600, csrf: str = "csrf") -> dict[str, object]:
    now = int(time.time())
    return {
        "sub": "subject",
        "email": "user@example.invalid",
        "preferred_username": "user",
        "groups": ["unihub-manager"],
        "iss": "issuer",
        "aud": "retail",
        "iat": now - 600,
        "exp": now + expires_in,
        "refresh_token": "refresh-token",
        "csrf": csrf,
    }


@pytest.mark.anyio
async def test_logout_revokes_an_expired_session_without_refreshing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired session must be revoked directly, never refreshed first."""
    redis, http = FakeRedis(), FakeHttp({"access_token": "rotated-access"})
    _install(redis, http)
    session_id = "L" * 43
    await session_auth._store_session(session_id, _session_record(expires_in=-600))
    refresh = AsyncMock(return_value=None)
    distributed = AsyncMock(return_value=None)
    verify = AsyncMock(return_value=None)
    monkeypatch.setattr(session_auth, "_refresh", refresh)
    monkeypatch.setattr(session_auth, "_refresh_distributed", distributed)
    monkeypatch.setattr(session_auth, "verify_oidc_token", verify)

    response = await session_auth.session_logout(_request("POST", session_id, "csrf"))

    assert response.status_code == 200
    assert session_auth.SESSION_PREFIX + session_id not in redis.values
    assert refresh.await_count == 0
    assert distributed.await_count == 0
    assert verify.await_count == 0
    assert http.posts == []
    assert json.loads(response.body)["logout_url"] == LOGOUT_URL
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(session_auth.COOKIE_NAME + "=")
    assert "Max-Age=0" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie


@pytest.mark.anyio
async def test_logout_requires_csrf_from_a_live_session() -> None:
    """A live session must not be revoked on a missing or wrong CSRF token."""
    redis = FakeRedis()
    _install(redis)
    session_id = "M" * 43
    await session_auth._store_session(session_id, _session_record())
    session_key = session_auth.SESSION_PREFIX + session_id
    lock_key = session_auth.LOCK_PREFIX + session_id

    for label, csrf in (("missing", None), ("wrong", "not-the-csrf")):
        with pytest.raises(session_auth.HTTPException) as rejected:
            await session_auth.session_logout(_request("POST", session_id, csrf))
        assert rejected.value.status_code == 403, label
        assert str(rejected.value.detail) == "CSRF validation failed", label
        assert session_key in redis.values, label
        assert lock_key not in redis.values, label


@pytest.mark.anyio
async def test_logout_fails_closed_while_a_refresh_owns_the_lock() -> None:
    """A refresh already in flight must never be raced by logout."""
    redis = FakeRedis()
    _install(redis)
    session_id = "N" * 43
    await session_auth._store_session(session_id, _session_record())
    lock_key = session_auth.LOCK_PREFIX + session_id
    owner_token = b"in-flight-refresh-owner"
    assert await redis.set(lock_key, owner_token, ex=session_auth.REFRESH_LOCK_TTL_SECONDS, nx=True)

    with pytest.raises(session_auth.HTTPException) as rejected:
        await session_auth.session_logout(_request("POST", session_id, "csrf"))

    assert rejected.value.status_code == 503
    assert rejected.value.headers is not None
    assert rejected.value.headers["Retry-After"] == "2"
    assert rejected.value.headers["Retry-After"] == str(session_auth.REFRESH_RETRY_AFTER_SECONDS)
    assert session_auth.SESSION_PREFIX + session_id in redis.values
    assert redis.values[lock_key] == owner_token


@pytest.mark.anyio
async def test_logout_releases_its_own_lock_after_revocation() -> None:
    """The session is deleted while the caller owns the lock, then the lock is freed."""
    redis = FakeRedis()
    _install(redis)
    session_id = "O" * 43
    await session_auth._store_session(session_id, _session_record())
    session_key = session_auth.SESSION_PREFIX + session_id
    lock_key = session_auth.LOCK_PREFIX + session_id
    lock_state_during_delete: list[bytes | None] = []

    class ObservingRedis(FakeRedis):
        async def delete(self, key: str) -> int:
            if key == session_key:
                lock_state_during_delete.append(self.values.get(lock_key))
            return await super().delete(key)

    redis = ObservingRedis()
    _install(redis)
    await session_auth._store_session(session_id, _session_record())

    response = await session_auth.session_logout(_request("POST", session_id, "csrf"))

    assert response.status_code == 200
    assert session_key not in redis.values
    assert lock_state_during_delete and all(
        isinstance(held, bytes) and held for held in lock_state_during_delete
    )
    assert lock_key not in redis.values


@pytest.mark.anyio
async def test_logout_is_idempotent_when_the_session_is_already_revoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry after a lost response must still finish the provider logout."""
    redis = FakeRedis()
    _install(redis)
    session_id = "P" * 43
    refresh = AsyncMock(return_value=None)
    monkeypatch.setattr(session_auth, "_refresh", refresh)

    response = await session_auth.session_logout(_request("POST", session_id, "csrf"))

    assert response.status_code == 200
    assert json.loads(response.body)["logout_url"] == LOGOUT_URL
    assert response.headers["set-cookie"].startswith(session_auth.COOKIE_NAME + "=")
    assert session_auth.LOCK_PREFIX + session_id not in redis.values
    assert refresh.await_count == 0

    session_key = session_auth.SESSION_PREFIX + session_id
    redis.values[session_key] = b"rotated-but-unreadable-ciphertext"
    retried = await session_auth.session_logout(_request("POST", session_id, "csrf"))

    assert retried.status_code == 200
    assert json.loads(retried.body)["logout_url"] == LOGOUT_URL
    assert session_key not in redis.values
    assert refresh.await_count == 0


@pytest.mark.anyio
async def test_logout_rejects_a_non_empty_non_opaque_session_cookie() -> None:
    """Only a genuinely dropped cookie is idempotent: junk still fails closed."""
    redis = FakeRedis()
    _install(redis)

    for label, cookie in (
        ("short", "short"),
        ("illegal", "!" * 43),
        ("dots", "." * 43),
        ("too long", "x" * 44),
    ):
        with pytest.raises(session_auth.HTTPException) as rejected:
            await session_auth.session_logout(_request("POST", cookie, "csrf"))
        assert rejected.value.status_code == 401, label
        assert str(rejected.value.detail) == "Authentication required", label
        assert not redis.values, label


@pytest.mark.anyio
async def test_a_logged_out_session_cannot_be_revived_by_a_later_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After revocation neither a normal read nor a refresh may resurrect it."""
    redis, http = FakeRedis(), FakeHttp({"access_token": "rotated-access"})
    _install(redis, http)
    session_id = "Q" * 43
    await session_auth._store_session(session_id, _session_record(expires_in=-600))
    refresh = AsyncMock(return_value=None)
    monkeypatch.setattr(session_auth, "_refresh", refresh)

    response = await session_auth.session_logout(_request("POST", session_id, "csrf"))
    assert response.status_code == 200

    with pytest.raises(session_auth.HTTPException) as rejected:
        await session_auth.authenticate_session(_request("GET", session_id))

    assert rejected.value.status_code == 401
    assert refresh.await_count == 0
    assert http.posts == []
    assert not any(key.startswith(session_auth.SESSION_PREFIX) for key in redis.values)


@pytest.mark.anyio
async def test_logout_without_a_session_cookie_is_an_idempotent_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry whose cookie was already deleted must still end the provider session."""
    redis, http = FakeRedis(), FakeHttp({"access_token": "rotated-access"})
    _install(redis, http)
    refresh = AsyncMock(return_value=None)
    distributed = AsyncMock(return_value=None)
    monkeypatch.setattr(session_auth, "_refresh", refresh)
    monkeypatch.setattr(session_auth, "_refresh_distributed", distributed)

    for label, request in (
        ("absent", _request_without_session_cookie()),
        ("empty", _request("POST", "", "csrf")),
        ("stripped", _request("POST", " ", "csrf")),
    ):
        response = await session_auth.session_logout(request)

        assert response.status_code == 200, label
        assert json.loads(bytes(response.body))["logout_url"] == LOGOUT_URL, label
        cookie = response.headers["set-cookie"]
        assert cookie.startswith(session_auth.COOKIE_NAME + "="), label
        assert "Max-Age=0" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie, label
        assert not redis.values, label

    assert refresh.await_count == 0
    assert distributed.await_count == 0
    assert http.posts == []


@pytest.mark.anyio
async def test_stale_refresh_snapshot_cannot_resurrect_a_logged_out_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex P1: a refresh holding a pre-logout snapshot must never write it back."""
    redis, http = FakeRedis(), FakeHttp({"access_token": "rotated-access"})
    _install(redis, http)
    session_id = "R" * 43
    session_key = session_auth.SESSION_PREFIX + session_id
    lock_key = session_auth.LOCK_PREFIX + session_id
    await session_auth._store_session(session_id, _session_record(expires_in=-600))
    stale_record = session_auth._unpack(session_auth._cipher, await redis.get(session_key))  # type: ignore[arg-type]
    assert stale_record is not None and stale_record["refresh_token"] == "refresh-token"
    now = int(time.time())
    verify = AsyncMock(return_value=AuthClaims(
        "subject", "user@example.invalid", "user", ["unihub-manager"],
        "issuer", "retail", now, now + 600, {},
    ))
    monkeypatch.setattr(session_auth, "verify_oidc_token", verify)

    revoked = await session_auth.session_logout(_request("POST", session_id, "csrf"))
    assert revoked.status_code == 200
    assert session_key not in redis.values

    # The suspended refresh now acquires the lock it was waiting for with its stale snapshot.
    result = await session_auth._refresh_distributed(session_id, stale_record)

    assert result is None
    assert http.posts == []
    assert verify.await_count == 0
    assert session_key not in redis.values
    assert lock_key not in redis.values
