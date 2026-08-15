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
    "operation_id",
    "scenario_id",
    "export_id",
    "job_id",
    "visit_id",
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
    r"(?P<origin>\bhttps?://[^/\s?#]+)(?:/[^\s?#]*)?(?:\?[^\s#]*)?(?:#[^\s]*)?",
    re.IGNORECASE,
)
_CNP_RE = re.compile(r"\b\d{13}\b")
_SALARY_PERSON_RE = re.compile(r"\bsp1_[0-9a-f]{64}\b", re.IGNORECASE)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_IDENTIFIER_VALUE_RE = re.compile(
    r"(?i)\b(?P<key>operation_id|scenario_id|export_id|job_id|visit_id)"
    r"(?P<sep>\s*[:=]\s*)(?P<value>[^\s,;]+)"
)
_PATH_RE = re.compile(r"(?<![:/\w])/(?:[^\s?#]+/)*[^\s?#]*")
_DYNAMIC_ROUTE_SEGMENT_RE = re.compile(
    r"(?:^|/)(?:sp1_[0-9a-f]{64}|\d+|[0-9a-f]{8}-[0-9a-f-]{27,}|[0-9a-f]{32,})(?:/|$)",
    re.IGNORECASE,
)
_ROUTE_TEMPLATE_RE = re.compile(r"^/(?:[A-Za-z0-9._~-]+|\{[A-Za-z_][A-Za-z0-9_]*\})(?:/(?:[A-Za-z0-9._~-]+|\{[A-Za-z_][A-Za-z0-9_]*\}))*$")
_SAFE_ROUTE_KEYS = frozenset({"route_template", "handler", "transaction"})
_SAFE_SCALAR_KEYS = frozenset({"request_id", "method", "status", "duration_ms", "service_role"})
_REDACTION_MAX_DEPTH = 8
_REDACTION_MAX_ITEMS = 64
_REDACTION_NODE_BUDGET = 512


_NOT_SCALAR = object()  # unique sentinel; distinct from real scalar None


def redact_text(value: str, limit: int) -> str:
    value = _URL_QUERY_FRAGMENT_RE.sub(lambda match: match.group("origin"), value)
    value = _URL_CREDENTIAL_RE.sub(
        lambda match: f"{match.group('scheme')}[REDACTED]@", value
    )
    value = _BEARER_RE.sub("Bearer [REDACTED]", value)
    value = _KEY_VALUE_RE.sub(
        lambda match: f"{match.group('key')}{match.group('sep')}[REDACTED]", value
    )
    value = _IDENTIFIER_VALUE_RE.sub(
        lambda match: f"{match.group('key')}{match.group('sep')}[REDACTED]", value
    )
    value = _SALARY_PERSON_RE.sub("[REDACTED]", value)
    value = _UUID_RE.sub("[REDACTED]", value)
    value = _CNP_RE.sub("[REDACTED]", value)
    return _PATH_RE.sub("/[REDACTED]", value)[:limit]


def canonical_route_template(value: Any) -> str:
    """Retain only bounded low-cardinality route templates."""
    if not isinstance(value, str) or len(value) > 240:
        return "__unmatched__"
    if "?" in value or "#" in value or not _ROUTE_TEMPLATE_RE.fullmatch(value):
        return "__unmatched__"
    if _DYNAMIC_ROUTE_SEGMENT_RE.search(value):
        return "__unmatched__"
    return value


def _safe_scalar(key: str, value: Any) -> Any:
    if key == "duration_ms":
        return value if isinstance(value, (int, float)) and math.isfinite(value) else 0
    if key == "method":
        candidate = str(value).upper()
        return candidate if candidate in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"} else "OTHER"
    if key == "status":
        candidate = str(value)
        return candidate if re.fullmatch(r"(?:[1-5]\d\d|[1-5]xx)", candidate) else "unknown"
    if key == "service_role":
        candidate = str(value)
        return candidate if candidate in {"web", "operations", "imports", "grile", "exports", "salary_exports", "migration"} else "unknown"
    candidate = str(value)
    return candidate[:128] if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", candidate) else "invalid"


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


def _redact_dict_item(
    key: object,
    item: Any,
    *,
    depth: int,
    seen: set[int],
    budget: list[int],
) -> tuple[str, Any]:
    safe_key = safe_key_text(key)
    normalized_key = safe_key.casefold()
    if normalized_key in _SAFE_ROUTE_KEYS:
        return safe_key, canonical_route_template(item)
    if normalized_key in _SAFE_SCALAR_KEYS:
        return safe_key, _safe_scalar(normalized_key, item)
    if normalized_key == "url" and isinstance(item, str):
        match = _URL_QUERY_FRAGMENT_RE.search(item)
        return safe_key, match.group("origin") if match else "[REDACTED]"
    if normalized_key in {"pathname", "referer", "referrer", "query_string"}:
        return safe_key, "[REDACTED]"
    if normalized_key == "description" and isinstance(item, str) and item.startswith("/"):
        return safe_key, canonical_route_template(item)
    if is_sensitive_key(key):
        return safe_key, "[REDACTED]"
    return safe_key, redact_value(item, depth=depth + 1, seen=seen, budget=budget)


def _redact_dict(
    value: dict[Any, Any],
    *,
    depth: int,
    seen: set[int],
    budget: list[int],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, item in islice(value.items(), _REDACTION_MAX_ITEMS):
        safe_key, redacted = _redact_dict_item(
            key, item, depth=depth, seen=seen, budget=budget
        )
        output[safe_key] = redacted
    return output


def _redact_iterable(
    value: Iterable[Any],
    *,
    depth: int,
    seen: set[int],
    budget: list[int],
) -> list[Any]:
    if isinstance(value, (list, tuple)):
        items = list(value[:_REDACTION_MAX_ITEMS])
    else:
        items = list(islice(iter(value), _REDACTION_MAX_ITEMS))
    return [
        redact_value(item, depth=depth + 1, seen=seen, budget=budget)
        for item in items
    ]


def _redact_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value, 2000)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    return _NOT_SCALAR


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

    scalar = _redact_scalar(value)
    if scalar is not _NOT_SCALAR:
        return scalar

    seen = seen if seen is not None else set()
    value_id = id(value)
    if value_id in seen:
        return "[CIRCULAR]"
    seen.add(value_id)
    try:
        if isinstance(value, dict):
            return _redact_dict(value, depth=depth, seen=seen, budget=budget)
        if isinstance(value, Iterable):
            return _redact_iterable(value, depth=depth, seen=seen, budget=budget)
        return _safe_repr(value)
    finally:
        seen.discard(value_id)


def redact_observability_payload(value: Any) -> Any:
    """Deep-redact one outbound telemetry payload under bounded work."""
    return redact_value(value)
