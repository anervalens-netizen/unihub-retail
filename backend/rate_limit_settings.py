"""Pure, fail-closed settings for distributed request rate limiting."""
from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from typing import Literal, cast
from urllib.parse import urlsplit

from valkey_url import apply_valkey_endpoint_overrides


HeaderMode = Literal["none", "cloudflare", "x-forwarded-for"]


@dataclass(frozen=True, slots=True)
class PolicySettings:
    limit: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class RateLimitSettings:
    trusted_proxy_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]
    client_ip_header_mode: HeaderMode
    valkey_url: str
    key_hmac_secret: str
    failure_mode: Literal["closed"]
    policies: dict[str, PolicySettings]


_POLICY_DEFAULTS = {
    "auth_proxy": ("RATE_LIMIT_AUTH_PROXY", 120, 60),
    "sales_import_upload": ("RATE_LIMIT_SALES_IMPORT_UPLOAD", 5, 900),
    "report_export": ("RATE_LIMIT_REPORT_EXPORT", 30, 60),
    "business_write": ("RATE_LIMIT_BUSINESS_WRITE", 60, 60),
    "grile_job": ("RATE_LIMIT_GRILE_JOB", 10, 300),
    "target_mutation": ("RATE_LIMIT_TARGET_MUTATION", 30, 300),
}
_DISTRIBUTED_KEYS = (
    "TRUSTED_PROXY_CIDRS",
    "RATE_LIMIT_CLIENT_IP_HEADER",
    "RATE_LIMIT_KEY_HMAC_SECRET",
    "RATE_LIMIT_FAILURE_MODE",
)


def _integer(name: str, default: int, low: int, high: int) -> tuple[int | None, str | None]:
    raw = os.getenv(name)
    if raw is None:
        return default, None
    if raw == "" or raw != raw.strip() or not raw.isascii() or not raw.isdecimal():
        return None, f"{name} is invalid"
    value = int(raw)
    if value < low or value > high:
        return None, f"{name} is out of range"
    return value, None


def _valkey_url(raw: str) -> bool:
    if not raw or raw != raw.strip() or any(char.isspace() or not char.isprintable() for char in raw):
        return False
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"redis", "rediss"}
        and bool(parsed.hostname)
        and (parsed.username is None or parsed.password is not None)
        and not parsed.query
        and not parsed.fragment
        and (port is None or 0 < port <= 65535)
    )


def _parse(production: bool) -> tuple[RateLimitSettings | None, list[str]]:
    configured = any(os.getenv(name) not in (None, "") for name in (*_DISTRIBUTED_KEYS, "RATE_LIMIT_VALKEY_URL"))
    errors: list[str] = []
    if not production and not configured:
        return None, []

    raw_cidrs = os.getenv("TRUSTED_PROXY_CIDRS")
    mode_raw = os.getenv("RATE_LIMIT_CLIENT_IP_HEADER")
    secret = os.getenv("RATE_LIMIT_KEY_HMAC_SECRET")
    failure_mode = os.getenv("RATE_LIMIT_FAILURE_MODE")
    try:
        valkey_url = apply_valkey_endpoint_overrides(
            os.getenv("RATE_LIMIT_VALKEY_URL") or os.getenv("VALKEY_URL") or "",
            "RATE_LIMIT_VALKEY",
        )
    except ValueError:
        valkey_url = ""

    for name, value in (
        ("TRUSTED_PROXY_CIDRS", raw_cidrs),
        ("RATE_LIMIT_CLIENT_IP_HEADER", mode_raw),
        ("RATE_LIMIT_KEY_HMAC_SECRET", secret),
        ("RATE_LIMIT_FAILURE_MODE", failure_mode),
    ):
        if value in (None, ""):
            errors.append(f"{name} is required")

    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    if raw_cidrs:
        seen: set[str] = set()
        for item in raw_cidrs.split(","):
            if not item or item != item.strip():
                errors.append("TRUSTED_PROXY_CIDRS is invalid")
                break
            try:
                network = ipaddress.ip_network(item, strict=False)
            except ValueError:
                errors.append("TRUSTED_PROXY_CIDRS is invalid")
                break
            canonical = network.with_prefixlen
            if canonical not in seen:
                seen.add(canonical)
                networks.append(network)

    mode: HeaderMode | None = None
    if mode_raw in {"none", "cloudflare", "x-forwarded-for"}:
        mode = cast(HeaderMode, mode_raw)
    elif mode_raw not in (None, ""):
        errors.append("RATE_LIMIT_CLIENT_IP_HEADER is invalid")
    if mode in {"cloudflare", "x-forwarded-for"} and not networks:
        errors.append("TRUSTED_PROXY_CIDRS is required for forwarded client IP")

    if secret is not None and secret != "" and (
        len(secret) < 43 or len(secret) > 256
        or any(char.isspace() or not char.isprintable() for char in secret)
    ):
        errors.append("RATE_LIMIT_KEY_HMAC_SECRET is invalid")
    if failure_mode not in (None, "", "closed"):
        errors.append("RATE_LIMIT_FAILURE_MODE is invalid")
    if not _valkey_url(valkey_url):
        errors.append("RATE_LIMIT_VALKEY_URL is invalid")

    policies: dict[str, PolicySettings] = {}
    for policy_name, (limit_name, default_limit, default_window) in _POLICY_DEFAULTS.items():
        window_name = f"{limit_name}_WINDOW_SECONDS"
        limit, limit_error = _integer(limit_name, default_limit, 1, 100_000)
        window, window_error = _integer(window_name, default_window, 1, 86_400)
        if limit_error:
            errors.append(limit_error)
        if window_error:
            errors.append(window_error)
        if limit is not None and window is not None:
            policies[policy_name] = PolicySettings(limit, window)

    if errors or mode is None or secret in (None, "") or failure_mode != "closed":
        return None, errors
    assert secret is not None
    return RateLimitSettings(tuple(networks), mode, valkey_url, secret, "closed", policies), []


def load_rate_limit_settings() -> RateLimitSettings | None:
    settings, errors = _parse(os.getenv("UNIHUB_ENV", "development").strip().lower() == "production")
    if errors:
        raise ValueError("Distributed rate limit configuration is invalid")
    return settings


def rate_limit_config_errors(production: bool) -> list[str]:
    return _parse(production)[1]
