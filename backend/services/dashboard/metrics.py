from __future__ import annotations

import time
from collections.abc import Awaitable
from typing import TypeVar

from prometheus_client import Histogram


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


def _validate_component(component: str) -> None:
    if component not in DASHBOARD_COMPONENT_NAMES:
        raise ValueError(f"Unknown dashboard component: {component}")


def record_dashboard_component_queue(component: str, seconds: float) -> None:
    _validate_component(component)
    DASHBOARD_COMPONENT_QUEUE_SECONDS.labels(component).observe(seconds)


async def observe_dashboard_component(
    component: str,
    awaitable: Awaitable[_T],
) -> _T:
    _validate_component(component)
    started_at = time.perf_counter()
    try:
        return await awaitable
    finally:
        DASHBOARD_COMPONENT_DURATION_SECONDS.labels(component).observe(
            time.perf_counter() - started_at
        )
