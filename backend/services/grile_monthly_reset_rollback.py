"""Cancel-safe reset rollback orchestration for sync and adapter Google paths."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Coroutine

from services.grile_monthly_types import StoreEntry


async def rollback_entries(
    pool: Any,
    *,
    operation_id: int,
    entries: list[StoreEntry],
    sheets_service: Any,
    snapshots: dict[str, dict[str, Any]],
    execution_owner: str,
    execution_epoch: int,
    restore_snapshot: Callable[[Any, StoreEntry, dict[str, Any]], None],
    record_rollback: Callable[..., Awaitable[bool]],
) -> bool:
    rollback_failed = False
    for entry in reversed(entries):
        restored = _restore_sync_entry(
            sheets_service,
            entry,
            snapshots,
            restore_snapshot,
        )
        rollback_failed = rollback_failed or not restored
        try:
            recorded = await record_rollback(
                pool,
                operation_id=operation_id,
                site_code=entry.site_code,
                restored=restored,
                execution_owner=execution_owner,
                execution_epoch=execution_epoch,
                error_message=_rollback_message(restored),
            )
        except Exception:  # noqa: BLE001 - Google restoration took precedence
            recorded = False
        rollback_failed = rollback_failed or not recorded
    return not rollback_failed


def _restore_sync_entry(
    sheets_service: Any,
    entry: StoreEntry,
    snapshots: dict[str, dict[str, Any]],
    restore_snapshot: Callable[[Any, StoreEntry, dict[str, Any]], None],
) -> bool:
    try:
        restore_snapshot(sheets_service, entry, snapshots[entry.site_code])
        return True
    except Exception:  # noqa: BLE001 - caller records uncertainty
        return False


async def cancel_safe(
    operation: Callable[[], Coroutine[Any, Any, bool]],
) -> bool:
    current = asyncio.current_task()
    if current is not None:
        while current.cancelling():
            current.uncancel()
    task: asyncio.Task[bool] = asyncio.create_task(operation())
    try:
        return await asyncio.shield(task)
    except BaseException:
        return False


async def rollback_adapter_entries(
    pool: Any,
    *,
    operation_id: int,
    entries: list[StoreEntry],
    google_adapter: Any,
    snapshots: dict[str, dict[str, Any]],
    execution_owner: str,
    execution_epoch: int,
    prepare_rollback: Callable[..., Awaitable[dict[str, Any] | None]],
    restore_snapshot: Callable[[Any, StoreEntry, dict[str, Any]], Awaitable[None]],
    confirm_rollback: Callable[..., Awaitable[bool]],
) -> bool:
    rollback_failed = False
    for entry in reversed(entries):
        intent = await prepare_rollback(
            pool,
            operation_id=operation_id,
            site_code=entry.site_code,
            execution_owner=execution_owner,
            execution_epoch=execution_epoch,
        )
        if intent is None:
            rollback_failed = True
            continue
        restored = await _restore_adapter_entry(
            google_adapter,
            entry,
            snapshots,
            restore_snapshot,
        )
        rollback_failed = rollback_failed or not restored
        confirmed = await confirm_rollback(
            pool,
            operation_id=operation_id,
            site_code=entry.site_code,
            execution_owner=execution_owner,
            execution_epoch=execution_epoch,
            fence_epoch=int(intent["fence_epoch"]),
            restored=restored,
            error_message=_rollback_message(restored),
        )
        rollback_failed = rollback_failed or not confirmed
    return not rollback_failed


async def _restore_adapter_entry(
    google_adapter: Any,
    entry: StoreEntry,
    snapshots: dict[str, dict[str, Any]],
    restore_snapshot: Callable[[Any, StoreEntry, dict[str, Any]], Awaitable[None]],
) -> bool:
    try:
        await restore_snapshot(google_adapter, entry, snapshots[entry.site_code])
        return True
    except BaseException:  # noqa: BLE001 - fenced checkpoint records uncertainty
        return False


def _rollback_message(restored: bool) -> str:
    return "reset_rolled_back" if restored else "reset_rollback_failed"
