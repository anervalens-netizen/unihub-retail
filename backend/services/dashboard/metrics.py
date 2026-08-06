from __future__ import annotations

import time
from collections.abc import Awaitable
from typing import TypeVar

from prometheus_client import Counter, Gauge, Histogram


_T = TypeVar("_T")

DASHBOARD_COMPONENT_NAMES = frozenset(
    {
        "agents",
        "asms",
        "brand_mix",
        "campaign_context",
        "category_mix",
        "daily",
        "daily_last_year",
        "focus_subcategory_mix",
        "period_comparison",
        "premium_glass",
        "promo_incentive",
        "receipt_bucket_mix",
        "regionals",
        "special_cards",
        "stores",
        "summary",
    }
)

DASHBOARD_COMPONENT_DURATION_SECONDS = Histogram(
    "dashboard_component_duration_seconds",
    "Latency of fixed-cardinality components used by /api/dashboard/all.",
    ("component",),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 2.0, 5.0),
)

DASHBOARD_COMPONENT_QUEUE_SECONDS = Histogram(
    "dashboard_component_queue_seconds",
    "Time fixed-cardinality dashboard components wait for a bounded execution slot.",
    ("component",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0),
)

DASHBOARD_COMPONENT_GLOBAL_QUEUE_SECONDS = Histogram(
    "dashboard_component_global_queue_seconds",
    "Time dashboard components wait for the process-wide database work budget.",
    ("component",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0),
)

DASHBOARD_COMPONENT_ACTIVE = Gauge(
    "dashboard_component_active",
    "Dashboard database components currently executing inside the global budget.",
)

DASHBOARD_COMPONENT_GLOBAL_LIMIT = Gauge(
    "dashboard_component_global_limit",
    "Configured process-wide Dashboard database component budget.",
)

DASHBOARD_COMPONENT_BUDGET_VIOLATION_TOTAL = Counter(
    "dashboard_component_budget_violation_total",
    "Dashboard components observed above the configured global execution budget.",
)

DASHBOARD_CAMPAIGN_CONTEXT_SECONDS = Histogram(
    "dashboard_campaign_context_seconds",
    "Latency of the bounded Dashboard campaign-context projection.",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 2.0, 5.0),
)


def _validate_component(component: str) -> None:
    if component not in DASHBOARD_COMPONENT_NAMES:
        raise ValueError(f"Unknown dashboard component: {component}")


def record_dashboard_component_queue(component: str, seconds: float) -> None:
    _validate_component(component)
    DASHBOARD_COMPONENT_QUEUE_SECONDS.labels(component).observe(seconds)


def record_dashboard_component_global_queue(component: str, seconds: float) -> None:
    _validate_component(component)
    DASHBOARD_COMPONENT_GLOBAL_QUEUE_SECONDS.labels(component).observe(seconds)


def set_dashboard_component_global_limit(limit: int) -> None:
    if limit < 1:
        raise ValueError("Dashboard global component limit must be positive")
    DASHBOARD_COMPONENT_GLOBAL_LIMIT.set(limit)


def dashboard_component_started(*, active: int, limit: int) -> None:
    DASHBOARD_COMPONENT_ACTIVE.inc()
    if active > limit:
        DASHBOARD_COMPONENT_BUDGET_VIOLATION_TOTAL.inc()


def dashboard_component_finished() -> None:
    DASHBOARD_COMPONENT_ACTIVE.dec()


async def observe_dashboard_component(
    component: str,
    awaitable: Awaitable[_T],
) -> _T:
    _validate_component(component)
    started_at = time.perf_counter()
    try:
        return await awaitable
    finally:
        elapsed = time.perf_counter() - started_at
        DASHBOARD_COMPONENT_DURATION_SECONDS.labels(component).observe(elapsed)
        if component == "campaign_context":
            DASHBOARD_CAMPAIGN_CONTEXT_SECONDS.observe(elapsed)
