"""Lifecycle wrapper for the bounded Grile V2 pilot synchronizer."""

from __future__ import annotations

import asyncio
import logging
from typing import Any


logger = logging.getLogger(__name__)
SYNC_INTERVAL_SECONDS = 5 * 60
STOP_KEY = "grile_v2_sheet_sync_stop"
TASK_KEY = "grile_v2_sheet_sync_task"


async def _run_loop(ctx: dict[str, Any], *, interval_seconds: float) -> None:
    stop: asyncio.Event = ctx[STOP_KEY]
    pool = ctx["db_pool"]
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except TimeoutError:
                pass
            if stop.is_set():
                break
            try:
                from services.grile_v2_sheet_sync import sync_pilot

                result = await sync_pilot(pool)
                logger.info("Grile V2 pilot sheet sync completed result=%s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Grile V2 pilot sheet sync failed")
    except asyncio.CancelledError:
        return


def start_grile_v2_sync_loop(
    ctx: dict[str, Any], *, interval_seconds: float = SYNC_INTERVAL_SECONDS
) -> None:
    if ctx.get(TASK_KEY) is not None:
        raise RuntimeError("Grile V2 pilot sync loop is already active")
    if interval_seconds <= 0:
        raise ValueError("Grile V2 pilot sync interval must be positive")
    ctx[STOP_KEY] = asyncio.Event()
    ctx[TASK_KEY] = asyncio.create_task(
        _run_loop(ctx, interval_seconds=interval_seconds),
        name="grile-v2-pilot-sheet-sync",
    )


async def stop_grile_v2_sync_loop(ctx: dict[str, Any]) -> None:
    stop = ctx.get(STOP_KEY)
    task = ctx.get(TASK_KEY)
    if stop is not None:
        stop.set()
    if task is not None:
        try:
            # sync_pilot owns the Google to_thread calls. Shield the task so
            # shutdown does not cancel its coroutine while a provider thread
            # is still active; systemd remains the final bounded terminator.
            await asyncio.wait_for(asyncio.shield(task), timeout=200)
        except asyncio.TimeoutError:
            logger.error("Grile V2 pilot sync did not drain within 200 seconds")
        except asyncio.CancelledError:
            raise
    ctx.pop(TASK_KEY, None)
    ctx.pop(STOP_KEY, None)
