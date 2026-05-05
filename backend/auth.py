"""authentik OIDC JWT verification for unihub-retail.

Light integration: verifies RS256-signed tokens issued by authentik.
No local user store — claims are extracted on-the-fly from the JWT.

Usage:
    from backend.auth import require_auth, AuthClaims

    @router.get("/protected")
    async def protected(claims: AuthClaims = Depends(require_auth)):
        return {"user": claims.email}

JWKS is fetched once at first request and cached for JWKS_CACHE_TTL seconds.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from jose import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────
OIDC_ISSUER = os.getenv(
    "OIDC_ISSUER", "https://auth.unihub.ro/application/o/unihub-retail/"
)
OIDC_JWKS_URL = os.getenv(
    "OIDC_JWKS_URL",
    "https://auth.unihub.ro/application/o/unihub-retail/jwks/",
)
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE", "4yiNauwNNzIoIE3Mq9IFnylxtdih9jFSqSKGw93t")  # = client_id
JWKS_CACHE_TTL = int(os.getenv("JWKS_CACHE_TTL", "3600"))  # 1 hour

# ── JWKS cache ───────────────────────────────────────────────────────
_jwks_cache: dict[str, Any] = {}
_jwks_fetched_at: float = 0.0


async def _fetch_jwks() -> dict[str, Any]:
    """Fetch JWKS from authentik. Uses cache with TTL."""
    global _jwks_cache, _jwks_fetched_at

    now = time.monotonic()
    if _jwks_cache and (now - _jwks_fetched_at) < JWKS_CACHE_TTL:
        return _jwks_cache

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(OIDC_JWKS_URL)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_fetched_at = now
            logger.info("JWKS refreshed from %s (%d keys)", OIDC_JWKS_URL, len(_jwks_cache.get("keys", [])))
            return _jwks_cache
    except Exception:
        logger.exception("Failed to fetch JWKS from %s", OIDC_JWKS_URL)
        if _jwks_cache:
            logger.warning("Using stale JWKS cache")
            return _jwks_cache
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service unavailable",
        )


def _get_signing_key(jwks: dict[str, Any], token: str) -> dict[str, Any]:
    """Find the correct key in JWKS for the token's kid header."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token header",
        ) from exc

    kid = header.get("kid")
    for key_data in jwks.get("keys", []):
        if key_data.get("kid") == kid:
            return key_data

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"No matching key found for kid={kid}",
    )


# ── Claims dataclass ────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class AuthClaims:
    """Verified OIDC claims extracted from the JWT."""
    sub: str
    email: str
    preferred_username: str
    groups: list[str]
    iss: str
    aud: str
    iat: int
    exp: int
    raw: dict[str, Any]  # full payload for anything else


# ── FastAPI dependencies ─────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthClaims:
    """FastAPI dependency — returns verified AuthClaims or raises 401."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    jwks = await _fetch_jwks()
    signing_key = _get_signing_key(jwks, token)

    decode_options: dict[str, Any] = {
        "verify_exp": True,
        "verify_iss": True,
        "verify_aud": bool(OIDC_AUDIENCE),
    }

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=OIDC_ISSUER,
            audience=OIDC_AUDIENCE if OIDC_AUDIENCE else None,
            options=decode_options,
        )
    except jwt.ExpiredSignatureError as exc:
        logger.warning("JWT validation failed (expired): %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        ) from exc
    except jwt.JWTClaimsError as exc:
        logger.warning("JWT validation failed (claims error): %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
        ) from exc
    except jwt.JWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    # Ensure python-jose returns lists correctly or fallback to empty
    groups = payload.get("groups", [])
    if isinstance(groups, str):
        groups = [groups]

    return AuthClaims(
        sub=payload.get("sub", ""),
        email=payload.get("email", ""),
        preferred_username=payload.get("preferred_username", ""),
        groups=groups,
        iss=payload.get("iss", ""),
        aud=payload.get("aud", ""),
        iat=payload.get("iat", 0),
        exp=payload.get("exp", 0),
        raw=payload,
    )


async def optional_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthClaims | None:
    """Like require_auth but returns None if no token is present.
    Useful for endpoints that behave differently for authenticated vs
    anonymous users."""
    if credentials is None:
        return None
    return await require_auth(credentials)