"""Backend error-tracking configuration with a strict privacy boundary."""
from __future__ import annotations

import math
import os
from typing import Any, cast

import sentry_sdk

from observability.redaction import redact_observability_payload

_BACKEND_DSN_ENV = "BACKEND_SENTRY_DSN"
_LEGACY_BACKEND_DSN_ENV = "SENTRY_DSN"
_BACKEND_SAMPLE_RATE_ENV = "BACKEND_SENTRY_TRACES_SAMPLE_RATE"
_LEGACY_SAMPLE_RATE_ENV = "SENTRY_TRACES_SAMPLE_RATE"


def _sample_rate() -> float:
    raw = os.getenv(
        _BACKEND_SAMPLE_RATE_ENV,
        os.getenv(_LEGACY_SAMPLE_RATE_ENV, "0.1"),
    )
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.1
    if not math.isfinite(value):
        return 0.1
    return min(1.0, max(0.0, value))


def _backend_dsn() -> str:
    return os.getenv(
        _BACKEND_DSN_ENV,
        os.getenv(_LEGACY_BACKEND_DSN_ENV, ""),
    ).strip()


def redact_sentry_event(
    event: dict[str, Any],
    _hint: dict[str, Any],
) -> dict[str, Any]:
    """Return a bounded deep-redacted event before it leaves the process."""
    redacted = redact_observability_payload(event)
    payload = redacted if isinstance(redacted, dict) else {"message": "[REDACTED]"}
    return payload


def configure_error_tracking() -> bool:
    """Configure backend Sentry/GlitchTip from a backend-only DSN."""
    dsn = _backend_dsn()
    if not dsn:
        return False
    runtime_sha = os.getenv("UNIHUB_RUNTIME_SHA", "").strip()
    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("UNIHUB_ENV", "development").strip().lower(),
        release=runtime_sha or None,
        traces_sample_rate=_sample_rate(),
        send_default_pii=False,
        max_request_body_size="never",
        before_send=cast(Any, redact_sentry_event),
        before_send_transaction=cast(Any, redact_sentry_event),
    )
    return True
