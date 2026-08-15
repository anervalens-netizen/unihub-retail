"""Fail-closed recovery policy for stale monthly Grile operations."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal
from uuid import uuid4

from services.grile_monthly_integrity import (
    MonthlyIntegrityError,
    file_sha256,
    snapshot_sha256,
)
from services.grile_monthly_types import StoreEntry


ReconciliationClass = Literal["safe_retry", "rolled_back", "recovery_required"]


@dataclass(frozen=True)
class ReconciliationPorts:
    claim_operations: Callable[..., Awaitable[list[dict[str, Any]]]]
    list_items: Callable[..., Awaitable[list[dict[str, Any]]]]
    mark_recovery: Callable[..., Awaitable[bool]]
    read_backup: Callable[[dict[str, Any]], dict[str, Any]]
    read_snapshot: Callable[[Any, StoreEntry], Awaitable[dict[str, Any]]]
    mark_safe_retry: Callable[..., Awaitable[bool]]
    prepare_rollback: Callable[..., Awaitable[dict[str, Any] | None]]
    confirm_rollback: Callable[..., Awaitable[bool]]
    restore_snapshot: Callable[[Any, StoreEntry, dict[str, Any]], Awaitable[None]]
    mark_operation: Callable[..., Awaitable[bool]]


@dataclass(frozen=True)
class ItemOutcome:
    classification: ReconciliationClass
    mark_recovery: bool = True


async def reconcile_operations(
    pool: Any,
    google_adapter: Any,
    ports: ReconciliationPorts,
) -> int:
    owner = f"reconciler-{uuid4().hex}"
    candidates = await ports.claim_operations(pool, execution_owner=owner)
    for operation in candidates:
        await _reconcile_operation(pool, google_adapter, operation, owner, ports)
    return len(candidates)


async def _reconcile_operation(
    pool: Any,
    google_adapter: Any,
    operation: dict[str, Any],
    owner: str,
    ports: ReconciliationPorts,
) -> None:
    operation_id = int(operation["id"])
    epoch = int(operation.get("execution_epoch", 0))
    items = await ports.list_items(pool, operation_id)
    classifications: list[ReconciliationClass] = []
    for item in items:
        outcome = await _reconcile_item(
            pool,
            google_adapter,
            item,
            operation_id,
            owner,
            epoch,
            ports,
        )
        classifications.append(outcome.classification)
        if outcome.classification == "recovery_required" and outcome.mark_recovery:
            await _mark_item_recovery(pool, item, operation_id, owner, epoch, ports)
    classification = _operation_classification(classifications)
    await ports.mark_operation(
        pool,
        operation_id=operation_id,
        execution_owner=owner,
        execution_epoch=epoch,
        classification=classification,
        error_message=classification,
        alert=classification == "recovery_required",
    )


async def _reconcile_item(
    pool: Any,
    google_adapter: Any,
    item: dict[str, Any],
    operation_id: int,
    owner: str,
    epoch: int,
    ports: ReconciliationPorts,
) -> ItemOutcome:
    if str(item.get("checkpoint_phase") or "legacy_unknown") == "legacy_unknown":
        await _mark_item_recovery(
            pool,
            item,
            operation_id,
            owner,
            epoch,
            ports,
            message="legacy_unknown_recovery_required",
        )
        return ItemOutcome("recovery_required", mark_recovery=False)
    try:
        return await _classify_snapshot(
            pool,
            google_adapter,
            item,
            operation_id,
            owner,
            epoch,
            ports,
        )
    except asyncio.CancelledError:
        raise
    except BaseException:  # noqa: BLE001 - read/hash failures block retry
        return ItemOutcome("recovery_required")


async def _classify_snapshot(
    pool: Any,
    google_adapter: Any,
    item: dict[str, Any],
    operation_id: int,
    owner: str,
    epoch: int,
    ports: ReconciliationPorts,
) -> ItemOutcome:
    snapshot = ports.read_backup(item)
    current = await ports.read_snapshot(google_adapter, reconciliation_entry(item))
    if snapshot_sha256(current) == snapshot_sha256(snapshot):
        return await _already_restored(
            pool,
            item,
            operation_id,
            owner,
            epoch,
            ports,
        )
    if snapshot_is_cleared(current):
        return await _restore_cleared(
            pool,
            google_adapter,
            item,
            snapshot,
            operation_id,
            owner,
            epoch,
            ports,
        )
    return ItemOutcome("recovery_required")


async def _already_restored(
    pool: Any,
    item: dict[str, Any],
    operation_id: int,
    owner: str,
    epoch: int,
    ports: ReconciliationPorts,
) -> ItemOutcome:
    site_code = str(item["site_code"])
    if str(item.get("checkpoint_phase")) == "snapshot_persisted":
        safe = await ports.mark_safe_retry(
            pool,
            operation_id=operation_id,
            site_code=site_code,
            execution_owner=owner,
            execution_epoch=epoch,
        )
        return ItemOutcome("safe_retry" if safe else "recovery_required")
    intent = await _prepare_rollback(pool, site_code, operation_id, owner, epoch, ports)
    restored = bool(intent) and await ports.confirm_rollback(
        pool,
        operation_id=operation_id,
        site_code=site_code,
        execution_owner=owner,
        execution_epoch=epoch,
        fence_epoch=int(intent["fence_epoch"]) if intent else -1,
        restored=True,
        error_message="rollback_verified_readback",
    )
    return ItemOutcome("rolled_back" if restored else "recovery_required")


async def _restore_cleared(
    pool: Any,
    google_adapter: Any,
    item: dict[str, Any],
    snapshot: dict[str, Any],
    operation_id: int,
    owner: str,
    epoch: int,
    ports: ReconciliationPorts,
) -> ItemOutcome:
    site_code = str(item["site_code"])
    intent = await _prepare_rollback(pool, site_code, operation_id, owner, epoch, ports)
    if intent is None:
        return ItemOutcome("recovery_required", mark_recovery=False)
    restored = await _try_restore(google_adapter, item, snapshot, ports)
    confirmed = await ports.confirm_rollback(
        pool,
        operation_id=operation_id,
        site_code=site_code,
        execution_owner=owner,
        execution_epoch=epoch,
        fence_epoch=int(intent["fence_epoch"]),
        restored=restored,
        error_message="rollback_verified" if restored else "recovery_required",
    )
    complete = restored and confirmed
    return ItemOutcome("rolled_back" if complete else "recovery_required")


async def _prepare_rollback(
    pool: Any,
    site_code: str,
    operation_id: int,
    owner: str,
    epoch: int,
    ports: ReconciliationPorts,
) -> dict[str, Any] | None:
    return await ports.prepare_rollback(
        pool,
        operation_id=operation_id,
        site_code=site_code,
        execution_owner=owner,
        execution_epoch=epoch,
    )


async def _try_restore(
    google_adapter: Any,
    item: dict[str, Any],
    snapshot: dict[str, Any],
    ports: ReconciliationPorts,
) -> bool:
    try:
        await ports.restore_snapshot(
            google_adapter,
            reconciliation_entry(item),
            snapshot,
        )
        return True
    except BaseException:  # noqa: BLE001 - recovery is fail-closed
        return False


async def _mark_item_recovery(
    pool: Any,
    item: dict[str, Any],
    operation_id: int,
    owner: str,
    epoch: int,
    ports: ReconciliationPorts,
    *,
    message: str = "recovery_required",
) -> None:
    await ports.mark_recovery(
        pool,
        operation_id=operation_id,
        site_code=str(item["site_code"]),
        execution_owner=owner,
        execution_epoch=epoch,
        error_message=message,
    )


def _operation_classification(
    classifications: list[ReconciliationClass],
) -> ReconciliationClass:
    if "recovery_required" in classifications:
        return "recovery_required"
    if "rolled_back" in classifications:
        return "rolled_back"
    return "safe_retry"


def reconciliation_entry(item: dict[str, Any]) -> StoreEntry:
    return StoreEntry(
        str(item.get("company") or ""),
        str(item.get("store") or ""),
        str(item.get("sheet_id") or ""),
        str(item.get("site_code") or ""),
        "Neatribuit",
    )


def read_reset_backup(
    item: dict[str, Any],
    *,
    outputs_dir: Path,
) -> dict[str, Any]:
    raw_path = Path(str(item.get("backup_path") or ""))
    path = raw_path if raw_path.is_absolute() else outputs_dir / raw_path
    if not path.exists() or file_sha256(path) != item.get("backup_sha256"):
        raise MonthlyIntegrityError("backup_invalid", "Reset backup cannot be verified")
    payload = json.loads(path.read_text(encoding="utf-8"))
    snapshot = payload.get("snapshot") if isinstance(payload, dict) else None
    if not isinstance(snapshot, dict):
        raise MonthlyIntegrityError("backup_invalid", "Reset backup snapshot is invalid")
    if payload.get("snapshot_sha256") != snapshot_sha256(snapshot):
        raise MonthlyIntegrityError("backup_invalid", "Reset backup hash is invalid")
    return snapshot


def snapshot_is_cleared(snapshot: dict[str, Any]) -> bool:
    return not any(
        item.get("values")
        for item in snapshot.get("value_ranges", [])
        if isinstance(item, dict)
    )
