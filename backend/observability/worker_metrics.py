from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from prometheus_client import Gauge, start_http_server

from observability.metrics_network import required_metrics_network


WORKER_UP = Gauge(
    "unihub_worker_up",
    "Whether one UniHub worker metrics endpoint is active.",
    ("service_role",),
)


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
    if role not in {"operations", "imports"}:
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
