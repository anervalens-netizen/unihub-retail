from __future__ import annotations

import asyncio
import time
from pathlib import Path
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
        token: str,
    ) -> int:
        if self.values.get(key) != token.encode("ascii"):
            return 0
        return int(self.values.pop(key, None) is not None)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


class FakeHttp:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload or {}
        self.posts: list[tuple[str, dict[str, object]]] = []

    async def post(self, url: str, data: dict[str, object]) -> httpx.Response:
        self.posts.append((url, data))
        return httpx.Response(200, json=self.payload)

    async def aclose(self) -> None:
        return None


def _settings(production: bool = True) -> SessionSettings:
    return SessionSettings(
        "redis://localhost:6379/14", KEY, "retail", "synthetic-client-secret",
        "https://retail.example.invalid", "https://auth.example.invalid/application/o/unihub-retail",
        3600, production,
    )


def _install(redis: FakeRedis, http: FakeHttp | None = None) -> None:
    session_auth._settings = _settings()
    session_auth._redis = redis  # type: ignore[assignment]
    session_auth._cipher = Fernet(KEY.encode("ascii"))
    session_auth._http = http or FakeHttp()  # type: ignore[assignment]


def _request(method: str, cookie: str, csrf: str | None = None, query: bytes = b"") -> Request:
    headers = [(b"cookie", f"{session_auth.COOKIE_NAME}={cookie}".encode())]
    if csrf is not None:
        headers.append((b"x-csrf-token", csrf.encode()))
    return Request({
        "type": "http", "method": method, "path": "/", "query_string": query,
        "headers": headers, "client": ("127.0.0.1", 1), "scheme": "https",
        "server": ("retail.example.invalid", 443),
    })


def test_session_settings_use_provider_endpoints_not_issuer_children() -> None:
    settings = _settings()
    assert settings.authorize_url == "https://auth.example.invalid/application/o/authorize/"
    assert settings.token_url == "https://auth.example.invalid/application/o/token/"
    assert settings.redirect_uri == "https://retail.example.invalid/auth/callback"


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
    cipher = session_auth._cipher
    assert cipher is not None
    state = "t" * 43
    await redis.set(session_auth.FLOW_PREFIX + state, session_auth._pack(cipher, {"nonce": "nonce", "verifier": "verifier"}))
    claims = AuthClaims(
        "subject", "user@example.invalid", "user", ["unihub-manager"],
        "issuer", "retail", int(time.time()) - 1, int(time.time()) + 600, {},
    )
    verify = AsyncMock(return_value=claims)
    monkeypatch.setattr(session_auth, "verify_oidc_token", verify)
    response = await session_auth.session_callback(_request("GET", "x" * 43, query=f"code=code&state={state}".encode()))
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
async def test_slow_session_refresh_does_not_log_out_waiting_request(
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

    claims = await asyncio.gather(
        session_auth.authenticate_session(_request("GET", session_id)),
        session_auth.authenticate_session(_request("GET", session_id)),
    )

    assert [claim.sub for claim in claims] == ["subject", "subject"]
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
