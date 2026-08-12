"""Heartbeat lease runner for monthly Grile execution."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Coroutine


Heartbeat = Callable[..., Awaitable[bool]]


async def run_with_lease(
    pool: Any,
    operation_id: int,
    *,
    execution_owner: str,
    execution_epoch: int,
    operation: Coroutine[Any, Any, Any],
    heartbeat_interval: float,
    heartbeat: Heartbeat,
) -> Any:
    async def monitor() -> None:
        while True:
            await asyncio.sleep(heartbeat_interval)
            alive = await heartbeat(
                pool,
                operation_id,
                execution_owner=execution_owner,
                execution_epoch=execution_epoch,
            )
            if not alive:
                from services.grile_monthly_integrity import MonthlyIntegrityError

                raise MonthlyIntegrityError(
                    "operation_lease_lost",
                    "Monthly operation lease was lost",
                )

    operation_task = asyncio.create_task(operation)
    heartbeat_task = asyncio.create_task(monitor())
    try:
        done, _ = await asyncio.wait(
            {operation_task, heartbeat_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if operation_task in done:
            return await operation_task
        operation_task.cancel()
        await asyncio.gather(operation_task, return_exceptions=True)
        await heartbeat_task
        raise AssertionError("Lease monitor exited without a result")
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
