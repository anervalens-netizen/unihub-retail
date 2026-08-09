"""Pure validation for outbound HTTP endpoint configuration."""
from __future__ import annotations

from urllib.parse import urlsplit


class InvalidHttpEndpoint(ValueError):
    """Raised when an outbound endpoint is not an explicit HTTP(S) URL."""


def validated_http_endpoint(value: str, *, setting: str = "endpoint") -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise InvalidHttpEndpoint(f"{setting} must use http or https")
    if not parsed.hostname:
        raise InvalidHttpEndpoint(f"{setting} must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise InvalidHttpEndpoint(f"{setting} must not contain credentials")
    return candidate
