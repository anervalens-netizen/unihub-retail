from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import time
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, start_http_server

from observability.metrics_network import required_metrics_network


WORKER_UP = Gauge(
    "unihub_worker_up",
    "Whether one UniHub worker metrics endpoint is active.",
    ("service_role",),
)
QUEUE_BACKLOG = Gauge(
    "unihub_worker_queue_backlog",
    "Number of jobs waiting in a Retail worker queue.",
    ("service_role",),
)
QUEUE_OLDEST_AGE_SECONDS = Gauge(
    "unihub_worker_queue_oldest_age_seconds",
    "Age of the oldest queued Retail job.",
    ("service_role",),
)
JOB_DURATION_SECONDS = Histogram(
    "unihub_worker_job_duration_seconds",
    "Retail worker job execution duration.",
    ("service_role",),
)
JOB_RESULTS = Counter(
    "unihub_worker_job_results_total",
    "Terminal Retail worker job outcomes.",
    ("service_role", "result"),
)


async def observe_queue(redis: Any, *, role: str, queue_name: str) -> None:
    """Refresh bounded queue backlog and oldest-age gauges from the ARQ zset."""
    backlog = int(await redis.zcard(queue_name))
    QUEUE_BACKLOG.labels(role).set(backlog)
    oldest_age = 0.0
    if backlog:
        oldest = await redis.zrange(queue_name, 0, 0, withscores=True)
        if oldest:
            score_ms = float(oldest[0][1])
            oldest_age = max(0.0, time.time() - score_ms / 1000.0)
    QUEUE_OLDEST_AGE_SECONDS.labels(role).set(oldest_age)


async def observe_job_start(ctx: dict[str, Any]) -> None:
    enqueue_time = ctx.get("enqueue_time")
    if isinstance(enqueue_time, datetime):
        if enqueue_time.tzinfo is None:
            enqueue_time = enqueue_time.replace(tzinfo=timezone.utc)
        ctx["metrics_job_started_monotonic"] = time.monotonic()


async def observe_job_end(ctx: dict[str, Any]) -> None:
    role = str(ctx.get("worker_role", "unknown"))
    started = ctx.get("metrics_job_started_monotonic")
    if isinstance(started, (float, int)):
        JOB_DURATION_SECONDS.labels(role).observe(max(0.0, time.monotonic() - started))
    result = "unknown"
    try:
        from arq.jobs import Job

        info = await Job(
            str(ctx["job_id"]),
            ctx["redis"],
            _queue_name=str(ctx["queue_name"]),
        ).result_info()
        if info is not None:
            result = "success" if info.success else "failed"
    except Exception:
        result = "unknown"
    JOB_RESULTS.labels(role, result).inc()


@dataclass(slots=True)
class WorkerMetricsServer:
    role: str
    server: Any

    def close(self) -> None:
        WORKER_UP.labels(self.role).set(0)
        shutdown = getattr(self.server, "shutdown", None)
        if callable(shutdown):
            shutdown()
        close = getattr(self.server, "server_close", None)
        if callable(close):
            close()


def _port_for_role(role: str) -> int | None:
    raw = os.getenv("WORKER_METRICS_PORT", "").strip()
    if not raw:
        return None
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError("WORKER_METRICS_PORT must be an integer") from exc
    if not 1024 <= port <= 65535:
        raise RuntimeError("WORKER_METRICS_PORT must be between 1024 and 65535")
    return port


def start_worker_metrics(role: str) -> WorkerMetricsServer | None:
    if role not in {"operations", "imports", "grile", "exports", "legacy"}:
        raise RuntimeError("Unknown worker metrics role")
    port = _port_for_role(role)
    if port is None:
        return None
    try:
        network = required_metrics_network()
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    host = os.getenv("WORKER_METRICS_HOST", "").strip()
    if host != str(network.gateway):
        raise RuntimeError("Worker metrics must bind to the detected Prometheus Docker gateway")
    server, _thread = start_http_server(port, addr=host)
    WORKER_UP.labels(role).set(1)
    return WorkerMetricsServer(role=role, server=server)
