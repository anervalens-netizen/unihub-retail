"""Pure, fail-closed settings for OIDC JWT verification."""
from __future__ import annotations

import os
import math
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit


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
    if not raw or raw != raw.strip() or any(not char.isprintable() for char in raw):
        return None, f"{name} is invalid"
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
    return raw, None


def normalized_origin(parsed: SplitResult) -> tuple[str, str, int]:
    scheme = parsed.scheme.casefold()
    port = parsed.port if parsed.port is not None else (443 if scheme == "https" else 80)
    return scheme, (parsed.hostname or "").casefold(), port


def _number(name: str, default: float, low: float, high: float, integer: bool = False) -> tuple[float | None, str | None]:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default, None
    if raw != raw.strip() or any(not char.isprintable() for char in raw):
        return None, f"{name} is invalid"
    try:
        value = int(raw) if integer else float(raw)
    except ValueError:
        return None, f"{name} is invalid"
    if not math.isfinite(value) or value < low or value > high:
        return None, f"{name} is out of range"
    return float(value), None


def _parse(production: bool) -> tuple[OIDCVerifierSettings | None, list[str]]:
    raw = {name: os.getenv(name) for name in _REQUIRED}
    populated = {name: value for name, value in raw.items() if value not in (None, "")}
    errors: list[str] = []
    ttl, ttl_error = _number("JWKS_CACHE_TTL", 3600, 60, 86400)
    stale, stale_error = _number("JWKS_MAX_STALE_SECONDS", 86400, 60, 604800)
    timeout, timeout_error = _number("JWKS_FETCH_TIMEOUT_SECONDS", 5.0, 0.5, 30.0)
    skew, skew_error = _number("OIDC_CLOCK_SKEW_SECONDS", 30, 0, 120, integer=True)
    for error in (ttl_error, stale_error, timeout_error, skew_error):
        if error: errors.append(error)
    if not populated and not production:
        return None, errors
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
    if ttl is not None and stale is not None and stale < ttl:
        errors.append("JWKS_MAX_STALE_SECONDS must be at least JWKS_CACHE_TTL")
    if issuer and jwks and normalized_origin(urlsplit(issuer)) != normalized_origin(urlsplit(jwks)):
        errors.append("OIDC_ISSUER and OIDC_JWKS_URL must have the same origin")
    if errors or issuer is None or jwks is None or audience == "" or ttl is None or stale is None or timeout is None or skew is None:
        return None, errors
    assert issuer is not None and jwks is not None
    assert ttl is not None and stale is not None and timeout is not None and skew is not None
    return OIDCVerifierSettings(issuer, jwks, audience, ttl, stale, timeout, int(skew)), []


def load_oidc_verifier_settings() -> OIDCVerifierSettings | None:
    settings, errors = _parse(os.getenv("UNIHUB_ENV", "development").strip().lower() == "production")
    if errors:
        raise ValueError("OIDC verifier configuration is invalid")
    return settings


def oidc_config_errors(production: bool) -> list[str]:
    return _parse(production)[1]


def hub_internal_secret_errors() -> list[str]:
    value = os.getenv("HUB_INTERNAL_SECRET")
    if value is None or value == "":
        return []
    if len(value) < 32 or len(value) > 256 or any(char.isspace() or not char.isprintable() for char in value):
        return ["HUB_INTERNAL_SECRET is invalid"]
    return []
