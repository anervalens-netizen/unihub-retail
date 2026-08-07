from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from prometheus_client import CollectorRegistry, REGISTRY, generate_latest, multiprocess


UNMATCHED_HANDLER = "__unmatched__"


def multiprocess_directory() -> Path | None:
    raw = os.getenv("PROMETHEUS_MULTIPROC_DIR", "").strip()
    return Path(raw).resolve() if raw else None


def validate_multiprocess_directory() -> None:
    directory = multiprocess_directory()
    if directory is None:
        return
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    if not directory.is_dir():
        raise RuntimeError("PROMETHEUS_MULTIPROC_DIR is not a directory")


def metrics_payload() -> bytes:
    """Render the correct registry for one- or multi-process web topology."""
    if multiprocess_directory() is None:
        return generate_latest(REGISTRY)
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return generate_latest(registry)


def mark_current_process_dead() -> None:
    if multiprocess_directory() is not None:
        multiprocess.mark_process_dead(os.getpid())


def canonical_handler(scope: dict[str, Any]) -> str:
    route = scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path
    return UNMATCHED_HANDLER
