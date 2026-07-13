"""Authentik OIDC authentication with a lifecycle-managed JWKS verifier."""
from __future__ import annotations

import hmac
import math
import os
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.types import Options

from oidc_verifier import get_oidc_verifier


@dataclass(frozen=True, slots=True)
class AuthClaims:
    sub: str
    email: str
    preferred_username: str
    groups: list[str]
    iss: str
    aud: str
    iat: int
    exp: int
    raw: dict[str, Any]


_bearer = HTTPBearer(auto_error=False)


def _hub_secret_matches(header_value: str, secret: str) -> bool:
    return hmac.compare_digest(header_value.encode("utf-8", "surrogateescape"), secret.encode("utf-8", "surrogateescape"))


def _unauthorized() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token", headers={"WWW-Authenticate": "Bearer"})


def _valid_text(value: object, maximum: int = 256, allow_internal_space: bool = True) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip() and len(value) <= maximum and all(char.isprintable() and (allow_internal_space or not char.isspace()) for char in value)


def _validated_numeric_date(value: object) -> int | None:
    """Return a bounded JWT NumericDate without leaking conversion failures."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        if not math.isfinite(value) or value < 0 or value > 2**63 - 1:
            return None
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


async def verify_oidc_token(
    token: str,
    *,
    nonce: str | None = None,
    audience: str | None = None,
) -> AuthClaims:
    try:
        verifier = get_oidc_verifier()
        expected_audience = (
            verifier.settings.audience if audience is None else audience
        )
        header = jwt.get_unverified_header(token)
        key = await verifier.signing_key(header)
        options: Options = {"verify_exp": True, "verify_iss": True, "verify_aud": True, "require": ["exp", "iat", "iss", "aud", "sub"]}
        payload = jwt.decode(token, key.key, algorithms=["RS256"], issuer=verifier.settings.issuer, audience=expected_audience, leeway=verifier.settings.clock_skew_seconds, options=options)
    except HTTPException:
        raise
    except (jwt.PyJWTError, TypeError, ValueError, OverflowError):
        raise _unauthorized()
    sub = payload.get("sub")
    groups = payload.get("groups", [])
    email = payload.get("email", "")
    username = payload.get("preferred_username", "")
    iat, exp = payload.get("iat"), payload.get("exp")
    iat_value, exp_value = _validated_numeric_date(iat), _validated_numeric_date(exp)
    if not isinstance(sub, str) or not _valid_text(sub) or not isinstance(groups, list) or len(groups) > 256 or any(not _valid_text(group, 128) for group in groups) or ("email" in payload and (not isinstance(email, str) or len(email) > 320 or any(char.isspace() or not char.isprintable() for char in email))) or ("preferred_username" in payload and (not isinstance(username, str) or len(username) > 256 or not _valid_text(username))) or iat_value is None or exp_value is None or (nonce is not None and payload.get("nonce") != nonce):
        raise _unauthorized()
    return AuthClaims(sub, email, username, groups, verifier.settings.issuer, expected_audience, iat_value, exp_value, {})


async def require_auth(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> AuthClaims:
    secret = os.getenv("HUB_INTERNAL_SECRET", "")
    supplied = request.headers.get("X-Hub-Internal", "")
    if secret and _hub_secret_matches(supplied, secret) and request.client and request.client.host in ("127.0.0.1", "::1"):
        return AuthClaims("hub-service", "hub@unihub.ro", "hub-service", ["unihub-admin"], "hub-internal", "internal", 0, 0, {})
    if credentials is not None:
        return await verify_oidc_token(credentials.credentials)
    if "__Host-unihub_session" not in request.cookies and "unihub_session_dev" not in request.cookies:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    from session_auth import authenticate_session

    return await authenticate_session(request)
