"""Bounded privacy redaction shared by logs and outbound telemetry."""
from __future__ import annotations

import math
import re
from collections.abc import Iterable
from itertools import islice
from typing import Any

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "token",
    "secret",
    "password",
    "cnp",
    "salary_cnp",
    "salary",
    "salariu",
    "client_secret",
    "refresh_token",
    "access_token",
    "database_url",
    "dsn",
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_KEY_VALUE_RE = re.compile(
    r"(?i)\b(?P<key>"
    r"refresh_token|access_token|client_secret|salary_cnp|salary|salariu|database_url|"
    r"authorization|password|cookie|secret|token|cnp|dsn"
    r")\b(?P<sep>\s*[:=]\s*)"
    r"(?P<value>bearer\s+[^\s,;]+|\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_URL_CREDENTIAL_RE = re.compile(
    r"(?i)\b(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<credentials>[^/\s@]+)@"
)
_URL_QUERY_FRAGMENT_RE = re.compile(
    r"(?P<origin>\bhttps?://[^\s?#]+)(?:\?[^\s#]*)?(?:#[^\s]*)?",
    re.IGNORECASE,
)
_CNP_RE = re.compile(r"\b\d{13}\b")
_REDACTION_MAX_DEPTH = 8
_REDACTION_MAX_ITEMS = 64
_REDACTION_NODE_BUDGET = 512


def redact_text(value: str, limit: int) -> str:
    value = _URL_QUERY_FRAGMENT_RE.sub(lambda match: match.group("origin"), value)
    value = _URL_CREDENTIAL_RE.sub(
        lambda match: f"{match.group('scheme')}[REDACTED]@", value
    )
    value = _BEARER_RE.sub("Bearer [REDACTED]", value)
    value = _KEY_VALUE_RE.sub(
        lambda match: f"{match.group('key')}{match.group('sep')}[REDACTED]", value
    )
    return _CNP_RE.sub("[REDACTED]", value)[:limit]


def safe_key_text(key: Any) -> str:
    try:
        return str(key)[:200]
    except Exception:  # noqa: BLE001 - observability must never escape
        return f"<{type(key).__name__}>"


def _safe_repr(value: Any) -> str:
    try:
        return redact_text(repr(value), 2000)
    except Exception:  # noqa: BLE001 - observability must never escape
        return f"<{type(value).__module__}.{type(value).__qualname__}>"


def is_sensitive_key(key: Any) -> bool:
    normalized = safe_key_text(key).casefold()
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact_value(
    value: Any,
    *,
    depth: int = 0,
    seen: set[int] | None = None,
    budget: list[int] | None = None,
) -> Any:
    budget = [_REDACTION_NODE_BUDGET] if budget is None else budget
    if budget[0] <= 0 or depth >= _REDACTION_MAX_DEPTH:
        return "[TRUNCATED]"
    budget[0] -= 1

    if isinstance(value, str):
        return redact_text(value, 2000)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)

    seen = seen if seen is not None else set()
    value_id = id(value)
    if value_id in seen:
        return "[CIRCULAR]"
    seen.add(value_id)
    try:
        if isinstance(value, dict):
            output: dict[str, Any] = {}
            for key, item in islice(value.items(), _REDACTION_MAX_ITEMS):
                safe_key = safe_key_text(key)
                output[safe_key] = (
                    "[REDACTED]"
                    if is_sensitive_key(key)
                    else redact_value(item, depth=depth + 1, seen=seen, budget=budget)
                )
            return output
        if isinstance(value, (list, tuple)):
            return [
                redact_value(item, depth=depth + 1, seen=seen, budget=budget)
                for item in value[:_REDACTION_MAX_ITEMS]
            ]
        if isinstance(value, Iterable):
            return [
                redact_value(item, depth=depth + 1, seen=seen, budget=budget)
                for item in islice(iter(value), _REDACTION_MAX_ITEMS)
            ]
        return _safe_repr(value)
    finally:
        seen.discard(value_id)


def redact_observability_payload(value: Any) -> Any:
    """Deep-redact one outbound telemetry payload under bounded work."""
    return redact_value(value)
