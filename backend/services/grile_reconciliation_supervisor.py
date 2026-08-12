"""Self-healing supervision for invariant Grile reconciliation tasks."""
from __future__ import annotations

import asyncio
import logging
import os
import random
import signal
import time
from typing import Any

from observability import worker_metrics

logger = logging.getLogger(__name__)
RECONCILE_SECONDS = 60
STALE_RUN_RECONCILE_SECONDS = 60
MAX_BACKOFF_SECONDS = 15 * 60


async def reconcile_once(pool: Any, adapter: Any, *, failure_count: int = 1) -> None:
    from services.grile_monthly import reconcile_monthly_operations

    started = time.monotonic()
    try:
        await reconcile_monthly_operations(pool, adapter)
    except Exception:
        worker_metrics.observe_grile_reconciliation_failure(
            time.monotonic() - started,
            failure_count,
        )
        raise
    worker_metrics.observe_grile_reconciliation_success(time.monotonic() - started)


async def run_monthly_reconciliation_loop(ctx: dict[str, Any]) -> None:
    stop = ctx["grile_monthly_reconcile_stop"]
    failures = 0
    try:
        while not stop.is_set():
            backoff = min(
                RECONCILE_SECONDS * (2 ** min(failures, 10)),
                MAX_BACKOFF_SECONDS,
            )
            if failures:
                backoff += random.uniform(0, min(30.0, backoff * 0.2))
            try:
                await asyncio.wait_for(stop.wait(), timeout=backoff)
            except TimeoutError:
                pass
            if stop.is_set():
                break
            try:
                await reconcile_once(
                    ctx["db_pool"],
                    ctx["grile_monthly_google"],
                    failure_count=failures + 1,
                )
            except Exception:
                failures += 1
                logger.exception(
                    "Periodic Grile monthly reconciliation failed; retrying with backoff"
                )
            else:
                failures = 0
    except asyncio.CancelledError:
        return


async def run_stale_run_reconciliation_loop(ctx: dict[str, Any]) -> None:
    from repositories.grile import GrileRepository

    stop = ctx["grile_run_reconcile_stop"]
    repo = GrileRepository(ctx["db_pool"])
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=STALE_RUN_RECONCILE_SECONDS)
            except TimeoutError:
                pass
            if stop.is_set():
                break
            try:
                reconciled = await repo.reconcile_stale_runs()
                refreshes = await repo.reconcile_store_refreshes()
                if reconciled:
                    logger.warning("Closed stale Grile runs: %s", reconciled)
                if refreshes:
                    logger.warning("Closed stale Grile store refreshes: %s", refreshes)
            except Exception:
                logger.exception("Periodic Grile run reconciliation failed")
    except asyncio.CancelledError:
        return


def terminate_on_invariant_task_exit(
    task: asyncio.Task[Any],
    *,
    stop: asyncio.Event,
    name: str,
) -> None:
    """Fail the worker process if an invariant task exits outside shutdown."""
    if task.cancelled() or stop.is_set():
        return
    error = task.exception()
    logger.critical(
        "Invariant worker task exited unexpectedly: %s",
        name,
        exc_info=(type(error), error, error.__traceback__) if error else None,
    )
    os.kill(os.getpid(), signal.SIGTERM)


def attach_invariant_restart(
    task: asyncio.Task[Any],
    *,
    stop: asyncio.Event,
    name: str,
) -> None:
    task.add_done_callback(
        lambda completed: terminate_on_invariant_task_exit(
            completed,
            stop=stop,
            name=name,
        )
    )
