from __future__ import annotations

import time
from collections.abc import Awaitable
from typing import TypeVar

from prometheus_client import Histogram


_T = TypeVar("_T")

DASHBOARD_COMPONENT_DURATION_SECONDS = Histogram(
    "dashboard_component_duration_seconds",
    "Latency of fixed-cardinality components used by /api/dashboard/all.",
    ("component",),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 2.0, 5.0),
)


async def observe_dashboard_component(
    component: str,
    awaitable: Awaitable[_T],
) -> _T:
    started_at = time.perf_counter()
    try:
        return await awaitable
    finally:
        DASHBOARD_COMPONENT_DURATION_SECONDS.labels(component).observe(
            time.perf_counter() - started_at
        )
