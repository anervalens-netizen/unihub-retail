"""OIDC BFF with encrypted Valkey sessions and an HttpOnly host cookie."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from redis.asyncio import Redis

from auth import AuthClaims, verify_oidc_token
from rate_limits import AUTH_PROXY_LIMIT, anonymous_rate_limit


COOKIE_NAME = "__Host-unihub_session"
FLOW_PREFIX = "unihub:retail:oidc-flow:v1:"
SESSION_PREFIX = "unihub:retail:session:v1:"
LOCK_PREFIX = "unihub:retail:session-refresh:v1:"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
OPAQUE_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


@dataclass(frozen=True, slots=True)
class SessionSettings:
    valkey_url: str
    encryption_key: str
    client_id: str
    client_secret: str
    public_origin: str
    issuer: str
    session_ttl_seconds: int
    secure_cookie: bool

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_origin}/auth/callback"

    @property
    def authorize_url(self) -> str:
        parsed = urlsplit(self.issuer)
        return f"{parsed.scheme}://{parsed.netloc}/application/o/authorize/"

    @property
    def token_url(self) -> str:
        parsed = urlsplit(self.issuer)
        return f"{parsed.scheme}://{parsed.netloc}/application/o/token/"

    @property
    def logout_url(self) -> str:
        return f"{self.issuer}/end-session/"


_settings: SessionSettings | None = None
_redis: Redis | None = None
_cipher: Fernet | None = None
_http: httpx.AsyncClient | None = None


def _bounded_text(value: str | None, maximum: int) -> str:
    if not value or value != value.strip() or len(value) > maximum or any(not char.isprintable() for char in value):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid authentication response")
    return value


def load_session_settings() -> SessionSettings | None:
    production = os.getenv("UNIHUB_ENV", "development").strip().lower() == "production"
    names = ("SESSION_ENCRYPTION_KEY", "OIDC_CLIENT_SECRET", "OIDC_ISSUER")
    configured = any(os.getenv(name) not in (None, "") for name in names)
    if not configured and not production:
        return None
    try:
        encryption_key = os.environ["SESSION_ENCRYPTION_KEY"]
        Fernet(encryption_key.encode("ascii"))
        client_secret = os.environ["OIDC_CLIENT_SECRET"]
        issuer = os.environ["OIDC_ISSUER"].rstrip("/")
    except (KeyError, ValueError, UnicodeError) as exc:
        raise ValueError("Session authentication configuration is invalid") from exc
    client_id = os.getenv("OIDC_CLIENT_ID") or os.getenv("OIDC_AUDIENCE", "")
    public_origin = os.getenv("SESSION_PUBLIC_ORIGIN", "http://localhost:3000").rstrip("/")
    valkey_url = os.getenv("SESSION_VALKEY_URL") or os.getenv("VALKEY_URL", "")
    try:
        ttl = int(os.getenv("SESSION_TTL_SECONDS", "2592000"))
        origin = urlsplit(public_origin)
        valkey = urlsplit(valkey_url)
        origin_port = origin.port
        valkey_port = valkey.port
    except ValueError as exc:
        raise ValueError("Session authentication configuration is invalid") from exc
    if (
        len(client_secret) < 16
        or len(client_secret) > 512
        or any(char.isspace() or not char.isprintable() for char in client_secret)
        or not client_id
        or len(client_id) > 256
        or any(char.isspace() or not char.isprintable() for char in client_id)
        or not valkey_url
        or valkey.scheme not in {"redis", "rediss"}
        or not valkey.hostname
        or (valkey.username is not None and valkey.password is None)
        or valkey.query
        or valkey.fragment
        or (valkey_port is not None and not 0 < valkey_port <= 65535)
        or origin.scheme not in ({"https"} if production else {"http", "https"})
        or not origin.hostname
        or origin.username is not None
        or origin.password is not None
        or (origin_port is not None and not 0 < origin_port <= 65535)
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
        or ttl < 900
        or ttl > 60 * 60 * 24 * 90
    ):
        raise ValueError("Session authentication configuration is invalid")
    return SessionSettings(
        valkey_url, encryption_key, client_id, client_secret, public_origin,
        issuer, ttl, production,
    )


def session_config_errors(production: bool) -> list[str]:
    previous = os.getenv("UNIHUB_ENV")
    try:
        os.environ["UNIHUB_ENV"] = "production" if production else "development"
        load_session_settings()
    except ValueError:
        return ["Session authentication configuration is invalid"]
    finally:
        if previous is None:
            os.environ.pop("UNIHUB_ENV", None)
        else:
            os.environ["UNIHUB_ENV"] = previous
    return []


def _cookie_name(settings: SessionSettings) -> str:
    return COOKIE_NAME if settings.secure_cookie else "unihub_session_dev"


async def init_session_runtime() -> None:
    global _settings, _redis, _cipher, _http
    if _redis is not None:
        return
    settings = load_session_settings()
    if settings is None:
        return
    client = Redis.from_url(settings.valkey_url, decode_responses=False, socket_timeout=2.0)
    http = httpx.AsyncClient(timeout=15.0, follow_redirects=False)
    try:
        await asyncio.wait_for(client.ping(), timeout=2.0)
    except Exception:
        await client.aclose()
        await http.aclose()
        raise RuntimeError("Session backend unavailable")
    _settings, _redis, _cipher, _http = settings, client, Fernet(settings.encryption_key.encode("ascii")), http


async def close_session_runtime() -> None:
    global _settings, _redis, _cipher, _http
    client, http = _redis, _http
    _settings = _redis = _cipher = _http = None
    if client is not None:
        await client.aclose()
    if http is not None:
        await http.aclose()


def _runtime() -> tuple[SessionSettings, Redis, Fernet, httpx.AsyncClient]:
    if _settings is None or _redis is None or _cipher is None or _http is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Session authentication unavailable")
    return _settings, _redis, _cipher, _http


async def verify_session_runtime_ready() -> None:
    if _settings is None and os.getenv("UNIHUB_ENV", "development").strip().lower() != "production":
        return
    _, client, _, _ = _runtime()
    try:
        await asyncio.wait_for(client.ping(), timeout=1.0)
    except Exception as exc:
        raise RuntimeError("Session backend unavailable") from exc


def _pack(cipher: Fernet, payload: dict[str, Any]) -> bytes:
    return cipher.encrypt(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))


def _unpack(cipher: Fernet, payload: bytes | None) -> dict[str, Any] | None:
    if not payload:
        return None
    try:
        result = json.loads(cipher.decrypt(payload).decode("utf-8"))
    except (InvalidToken, UnicodeError, json.JSONDecodeError):
        return None
    return result if isinstance(result, dict) else None


def _claims(payload: dict[str, Any]) -> AuthClaims:
    return AuthClaims(
        sub=str(payload["sub"]), email=str(payload.get("email", "")),
        preferred_username=str(payload.get("preferred_username", "")),
        groups=[str(group) for group in payload.get("groups", [])],
        iss=str(payload["iss"]), aud=str(payload["aud"]),
        iat=int(payload["iat"]), exp=int(payload["exp"]), raw={},
    )


async def _store_session(session_id: str, payload: dict[str, Any]) -> None:
    settings, client, cipher, _ = _runtime()
    await client.set(SESSION_PREFIX + session_id, _pack(cipher, payload), ex=settings.session_ttl_seconds)


async def _refresh(session_id: str, record: dict[str, Any]) -> dict[str, Any] | None:
    settings, client, cipher, http = _runtime()
    lock_key = LOCK_PREFIX + session_id
    if not await client.set(lock_key, b"1", ex=15, nx=True):
        for _attempt in range(20):
            await asyncio.sleep(0.1)
            refreshed = _unpack(cipher, await client.get(SESSION_PREFIX + session_id))
            if refreshed is not None and int(refreshed.get("exp", 0)) > int(time.time()) + 60:
                return refreshed
        return None
    try:
        refresh_token = record.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            return None
        response = await http.post(settings.token_url, data={
            "grant_type": "refresh_token", "refresh_token": refresh_token,
            "client_id": settings.client_id, "client_secret": settings.client_secret,
        })
        if response.status_code != 200 or len(response.content) > 256 * 1024:
            return None
        tokens = response.json()
        if not isinstance(tokens, dict):
            return None
        access_token = tokens.get("access_token")
        if not isinstance(access_token, str):
            return None
        claims = await verify_oidc_token(access_token)
        record.update(asdict(claims))
        if isinstance(tokens.get("refresh_token"), str):
            record["refresh_token"] = tokens["refresh_token"]
        await _store_session(session_id, record)
        return record
    except (httpx.HTTPError, ValueError, json.JSONDecodeError, HTTPException):
        return None
    finally:
        await client.delete(lock_key)


async def authenticate_session(request: Request) -> AuthClaims:
    settings, client, cipher, _ = _runtime()
    session_id = request.cookies.get(_cookie_name(settings), "")
    if not OPAQUE_RE.fullmatch(session_id):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    record = _unpack(cipher, await client.get(SESSION_PREFIX + session_id))
    if record is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    if int(record.get("exp", 0)) <= int(time.time()) + 60:
        record = await _refresh(session_id, record)
        if record is None:
            await client.delete(SESSION_PREFIX + session_id)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    if request.method not in SAFE_METHODS:
        supplied = request.headers.get("X-CSRF-Token", "")
        expected = record.get("csrf", "")
        if not isinstance(expected, str) or not hmac.compare_digest(supplied, expected):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF validation failed")
    return _claims(record)


_auth_rate_limit = Depends(anonymous_rate_limit(AUTH_PROXY_LIMIT))
router = APIRouter(
    prefix="/auth/session", tags=["session-auth"], dependencies=[_auth_rate_limit]
)


@router.get("/login")
async def session_login() -> RedirectResponse:
    settings, client, cipher, _ = _runtime()
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    await client.set(FLOW_PREFIX + state, _pack(cipher, {"nonce": nonce, "verifier": verifier}), ex=600, nx=True)
    query = urlencode({
        "client_id": settings.client_id, "redirect_uri": settings.redirect_uri,
        "response_type": "code", "scope": "openid profile email offline_access",
        "state": state, "nonce": nonce, "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return RedirectResponse(f"{settings.authorize_url}?{query}", status_code=302)


async def session_callback(request: Request) -> RedirectResponse:
    settings, client, cipher, http = _runtime()
    code = _bounded_text(request.query_params.get("code"), 4096)
    state = _bounded_text(request.query_params.get("state"), 128)
    if not OPAQUE_RE.fullmatch(state):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid authentication response")
    flow = _unpack(cipher, await client.getdel(FLOW_PREFIX + state))
    if flow is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid authentication response")
    try:
        response = await http.post(settings.token_url, data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": settings.redirect_uri, "client_id": settings.client_id,
            "client_secret": settings.client_secret, "code_verifier": flow["verifier"],
        })
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Authentication provider is unavailable") from exc
    if response.status_code != 200 or len(response.content) > 256 * 1024:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Authentication provider rejected the response")
    try:
        tokens = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Authentication provider returned an invalid response") from exc
    if not isinstance(tokens, dict):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Authentication provider returned an invalid response")
    access_token, id_token, refresh_token = tokens.get("access_token"), tokens.get("id_token"), tokens.get("refresh_token")
    if (
        not isinstance(access_token, str) or not access_token
        or not isinstance(id_token, str) or not id_token
        or not isinstance(refresh_token, str) or not refresh_token
    ):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Authentication provider returned an invalid response")
    claims = await verify_oidc_token(access_token)
    await verify_oidc_token(
        id_token,
        nonce=str(flow["nonce"]),
        audience=settings.client_id,
    )
    session_id, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    await _store_session(session_id, {**asdict(claims), "refresh_token": refresh_token, "csrf": csrf})
    result = RedirectResponse(settings.public_origin + "/", status_code=303)
    result.set_cookie(
        _cookie_name(settings), session_id, max_age=settings.session_ttl_seconds,
        secure=settings.secure_cookie, httponly=True, samesite="lax", path="/",
    )
    return result


callback_router = APIRouter(dependencies=[_auth_rate_limit])
callback_router.add_api_route(
    "/auth/callback", session_callback, methods=["GET"], include_in_schema=False
)


@router.get("")
async def session_status(request: Request) -> JSONResponse:
    claims = await authenticate_session(request)
    settings, client, cipher, _ = _runtime()
    record = _unpack(cipher, await client.get(SESSION_PREFIX + request.cookies[_cookie_name(settings)])) or {}
    return JSONResponse({
        "profile": {
            "sub": claims.sub, "email": claims.email,
            "preferred_username": claims.preferred_username, "groups": claims.groups,
        },
        "csrf_token": record.get("csrf", ""),
    }, headers={"Cache-Control": "no-store"})


@router.post("/logout")
async def session_logout(request: Request) -> JSONResponse:
    await authenticate_session(request)
    settings, client, _, _ = _runtime()
    cookie_name = _cookie_name(settings)
    session_id = request.cookies.get(cookie_name, "")
    await client.delete(SESSION_PREFIX + session_id)
    response = JSONResponse({"logout_url": settings.logout_url + "?" + urlencode({"post_logout_redirect_uri": settings.public_origin + "/"})})
    response.delete_cookie(cookie_name, path="/", secure=settings.secure_cookie, httponly=True, samesite="lax")
    return response
