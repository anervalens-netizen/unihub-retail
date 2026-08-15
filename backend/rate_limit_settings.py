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


def _required_values(errors: list[str]) -> tuple[str | None, ...]:
    values = (
        os.getenv("TRUSTED_PROXY_CIDRS"),
        os.getenv("RATE_LIMIT_CLIENT_IP_HEADER"),
        os.getenv("RATE_LIMIT_KEY_HMAC_SECRET"),
        os.getenv("RATE_LIMIT_FAILURE_MODE"),
    )
    for name, value in zip(_DISTRIBUTED_KEYS, values, strict=True):
        if value in (None, ""):
            errors.append(f"{name} is required")
    return values


def _proxy_networks(
    raw_cidrs: str | None,
    errors: list[str],
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    if not raw_cidrs:
        return networks
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
    return networks


def _header_mode(
    raw: str | None,
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
    errors: list[str],
) -> HeaderMode | None:
    mode: HeaderMode | None = None
    if raw in {"none", "cloudflare", "x-forwarded-for"}:
        mode = cast(HeaderMode, raw)
    elif raw not in (None, ""):
        errors.append("RATE_LIMIT_CLIENT_IP_HEADER is invalid")
    if mode in {"cloudflare", "x-forwarded-for"} and not networks:
        errors.append("TRUSTED_PROXY_CIDRS is required for forwarded client IP")
    return mode


def _validate_secret_and_backend(
    secret: str | None,
    failure_mode: str | None,
    valkey_url: str,
    errors: list[str],
) -> None:
    if secret not in (None, "") and (
        len(secret) < 43
        or len(secret) > 256
        or any(char.isspace() or not char.isprintable() for char in secret)
    ):
        errors.append("RATE_LIMIT_KEY_HMAC_SECRET is invalid")
    if failure_mode not in (None, "", "closed"):
        errors.append("RATE_LIMIT_FAILURE_MODE is invalid")
    if not _valkey_url(valkey_url):
        errors.append("RATE_LIMIT_VALKEY_URL is invalid")


def _policy_settings(errors: list[str]) -> dict[str, PolicySettings]:
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
    return policies


def _parse(production: bool) -> tuple[RateLimitSettings | None, list[str]]:
    configured = any(os.getenv(name) not in (None, "") for name in (*_DISTRIBUTED_KEYS, "RATE_LIMIT_VALKEY_URL"))
    errors: list[str] = []
    if not production and not configured:
        return None, []

    raw_cidrs, mode_raw, secret, failure_mode = _required_values(errors)
    try:
        valkey_url = apply_valkey_endpoint_overrides(
            os.getenv("RATE_LIMIT_VALKEY_URL") or os.getenv("VALKEY_URL") or "",
            "RATE_LIMIT_VALKEY",
        )
    except ValueError:
        valkey_url = ""

    networks = _proxy_networks(raw_cidrs, errors)
    mode = _header_mode(mode_raw, networks, errors)
    _validate_secret_and_backend(secret, failure_mode, valkey_url, errors)
    policies = _policy_settings(errors)

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
