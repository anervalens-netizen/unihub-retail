"""Bounded orchestration primitives for Dashboard component phases."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from services.dashboard.scheduler import _gather_named


async def gather_dashboard_phase(
    components: dict[str, Awaitable[Any]],
    *,
    component_limit: int,
    global_limit: int,
) -> dict[str, Any]:
    """Resolve one dependency phase through the shared Dashboard scheduler."""
    return await _gather_named(component_limit, global_limit, **components)
