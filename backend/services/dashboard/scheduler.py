"""Bounded, cancellable scheduling shared by Dashboard projections."""

from __future__ import annotations

import asyncio
import time
import weakref
from collections.abc import Awaitable
from typing import Any

from services.dashboard.metrics import (
    record_dashboard_component_global_queue,
    record_dashboard_component_queue,
)

DASHBOARD_COMPONENT_CONCURRENCY = 4
DEFAULT_DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY = 6
_dashboard_global_slots: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[int, asyncio.Semaphore]
] = weakref.WeakKeyDictionary()


def _get_dashboard_global_slots(limit: int) -> asyncio.Semaphore:
    """Return an event-loop-local semaphore for the validated process budget."""
    loop = asyncio.get_running_loop()
    slots_by_limit = _dashboard_global_slots.get(loop)
    if slots_by_limit is None:
        slots_by_limit = {}
        _dashboard_global_slots[loop] = slots_by_limit
    slots = slots_by_limit.get(limit)
    if slots is None:
        slots = asyncio.Semaphore(limit)
        slots_by_limit[limit] = slots
    return slots


async def _gather_cancel_on_error(
    *operations: Awaitable[Any],
    task_name: str,
) -> list[Any]:
    """Await children or cancel and reap every child before propagating failure."""
    tasks: list[asyncio.Future[Any]] = [
        asyncio.ensure_future(operation)
        for operation in operations
    ]
    for index, task in enumerate(tasks):
        if isinstance(task, asyncio.Task):
            task.set_name(f"{task_name}:{index}")
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def _gather_named(
    max_concurrency: int,
    global_component_concurrency: int = DEFAULT_DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY,
    **components: Awaitable[Any],
) -> dict[str, Any]:
    """Run named loaders with bounded concurrency and preserve their names."""
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be positive")

    semaphore = asyncio.Semaphore(max_concurrency)
    global_slots = _get_dashboard_global_slots(global_component_concurrency)

    async def run_component(name: str, component: Awaitable[Any]) -> Any:
        queued_at = time.perf_counter()
        async with semaphore:
            record_dashboard_component_queue(
                name,
                time.perf_counter() - queued_at,
            )
            global_queued_at = time.perf_counter()
            async with global_slots:
                record_dashboard_component_global_queue(
                    name,
                    time.perf_counter() - global_queued_at,
                )
                return await component

    names = tuple(components)
    tasks = {
        name: asyncio.create_task(
            run_component(name, components[name]),
            name=f"dashboard:{name}",
        )
        for name in names
    }
    try:
        values = await asyncio.gather(*(tasks[name] for name in names))
    except BaseException:
        for task in tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
        raise
    return dict(zip(names, values, strict=True))
