"""Google/reset adapters for the monthly Grile compatibility facade."""

from __future__ import annotations

from typing import Any

from services import grile_monthly_reset_google as reset_google
from services import grile_monthly_reset_rollback as reset_rollback


def read_snapshot(api: Any, service: Any, entry: Any) -> dict[str, Any]:
    return reset_google.read_snapshot(
        service,
        entry,
        retry_api=api.retry_api,
        attempts=api.GOOGLE_API_RETRY_ATTEMPTS,
        base_delay=api.GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
    )


async def read_snapshot_async(api: Any, adapter: Any, entry: Any) -> dict[str, Any]:
    return await reset_google.read_snapshot_async(
        adapter,
        entry,
        google_request=api._google_request,
    )


def restore_snapshot(
    api: Any,
    service: Any,
    entry: Any,
    snapshot: dict[str, Any],
) -> None:
    reset_google.restore_snapshot(
        service,
        entry,
        snapshot,
        retry_api=api.retry_api,
        attempts=api.GOOGLE_API_RETRY_ATTEMPTS,
        base_delay=api.GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
        read_snapshot=api._read_reset_snapshot,
    )


async def restore_snapshot_async(
    api: Any,
    adapter: Any,
    entry: Any,
    snapshot: dict[str, Any],
) -> None:
    await reset_google.restore_snapshot_async(
        adapter,
        entry,
        snapshot,
        google_request=api._google_request,
        read_snapshot=api._read_reset_snapshot_async,
    )


def verify_cleared(api: Any, service: Any, entry: Any) -> None:
    reset_google.verify_cleared(api._read_reset_snapshot(service, entry))


async def verify_cleared_async(api: Any, adapter: Any, entry: Any) -> None:
    reset_google.verify_cleared(await api._read_reset_snapshot_async(adapter, entry))


def reset_store(
    api: Any,
    service: Any | None,
    entry: Any,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    return reset_google.reset_store(
        service,
        entry,
        dry_run=dry_run,
        retry_api=api.retry_api,
        attempts=api.GOOGLE_API_RETRY_ATTEMPTS,
        base_delay=api.GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
        error_code=api._google_error_code,
    )


async def rollback_sync(api: Any, *args: Any, **kwargs: Any) -> bool:
    if "sheets_svc" in kwargs:
        kwargs["sheets_service"] = kwargs.pop("sheets_svc")
    return await reset_rollback.rollback_entries(
        *args,
        **kwargs,
        restore_snapshot=api._restore_reset_snapshot,
        record_rollback=api.record_reset_item_rollback,
    )


async def rollback_adapter(api: Any, *args: Any, **kwargs: Any) -> bool:
    return await reset_rollback.rollback_adapter_entries(
        *args,
        **kwargs,
        prepare_rollback=api.persist_reset_rollback_intent,
        restore_snapshot=api._restore_reset_snapshot_async,
        confirm_rollback=api.persist_reset_rollback_confirmation,
    )


async def cancel_safe(operation: Any) -> bool:
    return await reset_rollback.cancel_safe(operation)
