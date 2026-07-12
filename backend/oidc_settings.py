"""Pure, fail-closed settings for OIDC JWT verification."""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True, slots=True)
class OIDCVerifierSettings:
    issuer: str
    jwks_url: str
    audience: str
    cache_ttl_seconds: float
    max_stale_seconds: float
    fetch_timeout_seconds: float
    clock_skew_seconds: int


_REQUIRED = ("OIDC_ISSUER", "OIDC_JWKS_URL", "OIDC_AUDIENCE")


def _url(raw: str, name: str, production: bool) -> tuple[str | None, str | None]:
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None, f"{name} is invalid"
    if not parsed.scheme or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None, f"{name} is invalid"
    if parsed.scheme == "https":
        pass
    elif not production and parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        pass
    else:
        return None, f"{name} must use an allowed scheme"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/") or "/", "", "")), None


def _number(name: str, default: float, low: float, high: float, integer: bool = False) -> tuple[float | None, str | None]:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default, None
    try:
        value = int(raw) if integer else float(raw)
    except ValueError:
        return None, f"{name} is invalid"
    if value < low or value > high:
        return None, f"{name} is out of range"
    return float(value), None


def _parse(production: bool) -> tuple[OIDCVerifierSettings | None, list[str]]:
    raw = {name: os.getenv(name) for name in _REQUIRED}
    populated = {name: value for name, value in raw.items() if value not in (None, "")}
    if not populated and not production:
        return None, []
    errors: list[str] = []
    for name in _REQUIRED:
        if raw[name] is None or raw[name] == "":
            errors.append(f"{name} is required")
    issuer = jwks = None
    if raw["OIDC_ISSUER"] not in (None, ""):
        issuer, error = _url(raw["OIDC_ISSUER"] or "", "OIDC_ISSUER", production)
        if error: errors.append(error)
    if raw["OIDC_JWKS_URL"] not in (None, ""):
        jwks, error = _url(raw["OIDC_JWKS_URL"] or "", "OIDC_JWKS_URL", production)
        if error: errors.append(error)
    audience = raw["OIDC_AUDIENCE"] or ""
    if audience and (len(audience) > 256 or any(char.isspace() or not char.isprintable() for char in audience)):
        errors.append("OIDC_AUDIENCE is invalid")
    ttl, error = _number("JWKS_CACHE_TTL", 3600, 60, 86400)
    if error: errors.append(error)
    stale, error = _number("JWKS_MAX_STALE_SECONDS", 86400, 60, 604800)
    if error: errors.append(error)
    timeout, error = _number("JWKS_FETCH_TIMEOUT_SECONDS", 5.0, 0.5, 30.0)
    if error: errors.append(error)
    skew, error = _number("OIDC_CLOCK_SKEW_SECONDS", 30, 0, 120, integer=True)
    if error: errors.append(error)
    if ttl is not None and stale is not None and stale < ttl:
        errors.append("JWKS_MAX_STALE_SECONDS must be at least JWKS_CACHE_TTL")
    if issuer and jwks and urlsplit(issuer).netloc != urlsplit(jwks).netloc:
        errors.append("OIDC_ISSUER and OIDC_JWKS_URL must have the same origin")
    if errors or not all((issuer, jwks, audience, ttl, stale, timeout, skew)):
        return None, errors
    assert issuer is not None and jwks is not None
    assert ttl is not None and stale is not None and timeout is not None and skew is not None
    return OIDCVerifierSettings(issuer, jwks, audience, ttl, stale, timeout, int(skew)), []


def load_oidc_verifier_settings() -> OIDCVerifierSettings | None:
    return _parse(os.getenv("UNIHUB_ENV", "development").strip().lower() == "production")[0]


def oidc_config_errors(production: bool) -> list[str]:
    return _parse(production)[1]
