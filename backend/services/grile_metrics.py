"""Fixed-cardinality Prometheus metrics for queued Grile store refreshes."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from prometheus_client import Counter, Histogram


GRILE_STORE_REFRESH_PHASES = frozenset({"queue_wait", "provider", "db", "total"})

GRILE_STORE_REFRESH_OUTCOMES = frozenset(
    {"completed", "failed", "cancelled", "not_claimed", "worker_failed"}
)

GRILE_STORE_REFRESH_OUTCOMES_TOTAL = Counter(
    "grile_store_refresh_outcomes_total",
    "Terminal outcomes for persisted per-store Grile refresh operations.",
    ("outcome",),
)


GRILE_STORE_REFRESH_PHASE_SECONDS = Histogram(
    "grile_store_refresh_phase_seconds",
    "Latency split for the queued Grile per-store refresh lifecycle.",
    ("phase",),
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
    ),
)


def observe_grile_store_refresh_outcome(outcome: str) -> None:
    normalized = outcome if outcome in GRILE_STORE_REFRESH_OUTCOMES else "not_claimed"
    GRILE_STORE_REFRESH_OUTCOMES_TOTAL.labels(normalized).inc()


P = ParamSpec("P")
R = TypeVar("R", bound=dict[str, Any])


def observe_grile_store_refresh_operation(
    function: Callable[P, Coroutine[Any, Any, R]],
) -> Callable[P, Coroutine[Any, Any, R]]:
    @wraps(function)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            result = await function(*args, **kwargs)
        except asyncio.CancelledError:
            observe_grile_store_refresh_outcome("cancelled")
            raise
        except Exception:
            observe_grile_store_refresh_outcome("worker_failed")
            raise
        observe_grile_store_refresh_outcome(str(result.get("status") or "not_claimed"))
        return result

    return wrapped


def observe_grile_store_refresh_phase(phase: str, seconds: float) -> None:
    if phase not in GRILE_STORE_REFRESH_PHASES:
        raise ValueError(f"Unknown Grile refresh phase: {phase}")
    GRILE_STORE_REFRESH_PHASE_SECONDS.labels(phase).observe(max(0.0, seconds))


@dataclass
class GrileStoreRefreshTimings:
    """Accumulate per-job DB time while retaining robust total timing."""

    started_at: float = field(default_factory=time.perf_counter)
    db_seconds: float = 0.0
    queue_wait_seconds: float = 0.0
    _finished: bool = False

    @contextmanager
    def db(self) -> Iterator[None]:
        started_at = time.perf_counter()
        try:
            yield
        finally:
            self.db_seconds += time.perf_counter() - started_at

    def queue_wait(self, seconds: float) -> None:
        normalized = max(0.0, seconds)
        self.queue_wait_seconds = normalized
        observe_grile_store_refresh_phase("queue_wait", normalized)

    def provider(self, seconds: float) -> None:
        observe_grile_store_refresh_phase("provider", seconds)

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        observe_grile_store_refresh_phase("db", self.db_seconds)
        observe_grile_store_refresh_phase(
            "total",
            self.queue_wait_seconds + time.perf_counter() - self.started_at,
        )
