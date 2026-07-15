from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from prometheus_client import Counter, Gauge

logger = logging.getLogger(__name__)

retail_visit_shadow_comparisons_total = Counter(
    "retail_visit_shadow_comparisons_total",
    "Retail visit comparisons between the configured primary and shadow stores.",
    ("operation", "result"),
)
retail_visit_shadow_match = Gauge(
    "retail_visit_shadow_match",
    "Whether the latest Retail visit shadow comparison matched.",
    ("operation",),
)
retail_visit_shadow_last_success_timestamp_seconds = Gauge(
    "retail_visit_shadow_last_success_timestamp_seconds",
    "Unix timestamp of the latest matching Retail visit shadow comparison.",
    ("operation",),
)


def _stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compare_visit_result(operation: str, primary: Any, shadow: Any) -> bool:
    matched = _stable(primary) == _stable(shadow)
    result = "match" if matched else "mismatch"
    retail_visit_shadow_comparisons_total.labels(
        operation=operation,
        result=result,
    ).inc()
    retail_visit_shadow_match.labels(operation=operation).set(int(matched))
    if matched:
        retail_visit_shadow_last_success_timestamp_seconds.labels(
            operation=operation
        ).set(datetime.now(UTC).timestamp())
    else:
        logger.warning("Retail visit shadow mismatch operation=%s", operation)
    return matched


def record_visit_shadow_error(operation: str) -> None:
    retail_visit_shadow_comparisons_total.labels(
        operation=operation,
        result="error",
    ).inc()
    retail_visit_shadow_match.labels(operation=operation).set(0)
    logger.exception("Retail visit shadow read failed operation=%s", operation)


for _operation in ("report", "tree", "detail", "snapshot", "crm"):
    retail_visit_shadow_match.labels(operation=_operation).set(0)
    retail_visit_shadow_last_success_timestamp_seconds.labels(
        operation=_operation
    ).set(0)
    for _result in ("match", "mismatch", "error"):
        retail_visit_shadow_comparisons_total.labels(
            operation=_operation,
            result=_result,
        )
