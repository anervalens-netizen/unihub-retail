"""Fenced mutation and recovery orchestration for monthly Grile reset."""

from __future__ import annotations

import asyncio
from typing import Any

from services.grile_monthly_integrity import MonthlyIntegrityError
from services.grile_monthly_reset_contracts import ResetPorts, ResetRunContext
from services.grile_monthly_reset_preflight import (
    build_dry_run,
    capture_backups,
    load_archive,
    load_entries,
    prepare_execution,
    report_artifact,
    reset_manifest,
    validate_request,
)
from services.grile_monthly_types import MonthlyExecution, MonthlyManifestError, StoreEntry


async def execute_reset(
    context: ResetRunContext,
    ports: ResetPorts,
) -> MonthlyExecution:
    validate_request(context)
    archive = await load_archive(context, ports)
    entries, expected = await load_entries(context, archive, ports)
    sheets_service = await prepare_execution(context, entries, ports)
    snapshots, backups = await capture_backups(
        context,
        entries=entries,
        sheets_service=sheets_service,
        expected=expected,
        archive=archive,
        ports=ports,
    )
    if context.dry_run:
        return build_dry_run(
            context,
            expected=expected,
            snapshots=snapshots,
            archive=archive,
            ports=ports,
        )
    touched = await _execute_effects(
        context,
        entries=entries,
        sheets_service=sheets_service,
        snapshots=snapshots,
        backups=backups,
        expected=expected,
        archive=archive,
        ports=ports,
    )
    return await _build_live_execution(
        context,
        entries=entries,
        touched=touched,
        sheets_service=sheets_service,
        snapshots=snapshots,
        backups=backups,
        expected=expected,
        archive=archive,
        ports=ports,
    )


async def _clear_entry(
    context: ResetRunContext,
    *,
    entry: StoreEntry,
    sheets_service: Any,
    ports: ResetPorts,
) -> None:
    assert context.operation_id is not None
    assert context.execution_owner is not None
    assert context.execution_epoch is not None
    await ports.heartbeat(
        context.pool,
        context.operation_id,
        execution_owner=context.execution_owner,
        execution_epoch=context.execution_epoch,
    )
    claimed = await ports.mark_running(
        context.pool,
        operation_id=context.operation_id,
        site_code=entry.site_code,
        execution_owner=context.execution_owner,
        execution_epoch=context.execution_epoch,
    )
    if not claimed:
        raise MonthlyIntegrityError(
            "reset_checkpoint_claim_failed",
            "Reset checkpoint claim failed",
        )
    if context.google_adapter is None:
        persisted = await _clear_sync(context, entry, sheets_service, ports)
    else:
        persisted = await _clear_adapter(context, entry, ports)
    if not persisted:
        raise MonthlyIntegrityError(
            "reset_checkpoint_finish_failed",
            "Reset checkpoint finish failed",
        )


async def _clear_sync(
    context: ResetRunContext,
    entry: StoreEntry,
    sheets_service: Any,
    ports: ResetPorts,
) -> bool:
    result = ports.reset_store(sheets_service, entry, dry_run=False)
    if result["status"] != "OK":
        raise MonthlyIntegrityError(result["error"], "Google reset failed")
    ports.verify_cleared(sheets_service, entry)
    return await ports.finish_item(
        context.pool,
        operation_id=context.operation_id,
        site_code=entry.site_code,
        status="completed",
        execution_owner=context.execution_owner,
        execution_epoch=context.execution_epoch,
    )


async def _clear_adapter(
    context: ResetRunContext,
    entry: StoreEntry,
    ports: ResetPorts,
) -> bool:
    intent = await ports.prepare_clear(
        context.pool,
        operation_id=context.operation_id,
        site_code=entry.site_code,
        execution_owner=context.execution_owner,
        execution_epoch=context.execution_epoch,
    )
    if intent is None:
        raise MonthlyIntegrityError(
            "operation_lease_lost",
            "Reset clear intent was fenced",
        )
    await ports.google_request(
        context.google_adapter,
        "clear",
        {
            "spreadsheet_id": entry.sheet_id,
            "ranges": ports.reset_ranges(entry),
        },
        label="Google reset",
        destructive=True,
    )
    await ports.verify_cleared_async(context.google_adapter, entry)
    return await ports.confirm_clear(
        context.pool,
        operation_id=context.operation_id,
        site_code=entry.site_code,
        execution_owner=context.execution_owner,
        execution_epoch=context.execution_epoch,
        fence_epoch=int(intent["fence_epoch"]),
    )


async def _rollback_touched(
    context: ResetRunContext,
    *,
    entries: list[StoreEntry],
    sheets_service: Any,
    snapshots: dict[str, dict[str, Any]],
    ports: ResetPorts,
) -> bool:
    assert context.operation_id is not None
    if context.execution_owner is None or context.execution_epoch is None:
        return False
    if context.google_adapter is None:
        return await ports.rollback_sync(
            context.pool,
            operation_id=context.operation_id,
            entries=entries,
            sheets_svc=sheets_service,
            snapshots=snapshots,
            execution_owner=context.execution_owner,
            execution_epoch=context.execution_epoch,
        )
    return await ports.rollback_adapter(
        context.pool,
        operation_id=context.operation_id,
        entries=entries,
        google_adapter=context.google_adapter,
        snapshots=snapshots,
        execution_owner=context.execution_owner,
        execution_epoch=context.execution_epoch,
    )


async def _execute_effects(
    context: ResetRunContext,
    *,
    entries: list[StoreEntry],
    sheets_service: Any,
    snapshots: dict[str, dict[str, Any]],
    backups: list[dict[str, Any]],
    expected: dict[str, Any],
    archive: dict[str, Any],
    ports: ResetPorts,
) -> list[StoreEntry]:
    touched: list[StoreEntry] = []
    try:
        for entry in entries:
            touched.append(entry)
            await _clear_entry(
                context,
                entry=entry,
                sheets_service=sheets_service,
                ports=ports,
            )
        return touched
    except BaseException as exc:
        code = _reset_error_code(exc)
        rollback_ok = await _rollback_touched(
            context,
            entries=touched,
            sheets_service=sheets_service,
            snapshots=snapshots,
            ports=ports,
        )
        status = "rolled_back" if rollback_ok else "uncertain"
        manifest = reset_manifest(
            context,
            expected=expected,
            archive_manifest=archive,
            source_backups=backups,
            errors=[code, "rollback_verified" if rollback_ok else "rollback_failed"],
            status=status,
        )
        raise MonthlyManifestError(
            status,
            "Reset failed and rollback was evaluated",
            manifest,
        ) from exc


def _reset_error_code(exc: BaseException) -> str:
    if isinstance(exc, MonthlyIntegrityError):
        return exc.code
    if isinstance(exc, asyncio.CancelledError):
        return "reset_cancelled"
    return "reset_failed"


async def _rollback_manifest(
    context: ResetRunContext,
    *,
    touched: list[StoreEntry],
    sheets_service: Any,
    snapshots: dict[str, dict[str, Any]],
    backups: list[dict[str, Any]],
    expected: dict[str, Any],
    archive: dict[str, Any],
    ports: ResetPorts,
) -> dict[str, Any]:
    rollback_ok = await _rollback_touched(
        context,
        entries=touched,
        sheets_service=sheets_service,
        snapshots=snapshots,
        ports=ports,
    )
    return reset_manifest(
        context,
        expected=expected,
        archive_manifest=archive,
        source_backups=backups,
        errors=[
            "reset_commit_failed",
            "rollback_verified" if rollback_ok else "rollback_failed",
        ],
        status="rolled_back" if rollback_ok else "uncertain",
    )


async def _build_live_execution(
    context: ResetRunContext,
    *,
    entries: list[StoreEntry],
    touched: list[StoreEntry],
    sheets_service: Any,
    snapshots: dict[str, dict[str, Any]],
    backups: list[dict[str, Any]],
    expected: dict[str, Any],
    archive: dict[str, Any],
    ports: ResetPorts,
) -> MonthlyExecution:
    async def rollback_after_commit_failure() -> dict[str, Any]:
        return await _rollback_manifest(
            context,
            touched=touched,
            sheets_service=sheets_service,
            snapshots=snapshots,
            backups=backups,
            expected=expected,
            archive=archive,
            ports=ports,
        )

    try:
        report_path, artifact = report_artifact(
            context,
            expected=expected,
            processed_stores=len(entries),
            dry_run=False,
            ports=ports,
        )
        manifest = reset_manifest(
            context,
            expected=expected,
            archive_manifest=archive,
            processed_stores=len(entries),
            source_backups=backups,
            artifacts=[artifact],
            errors=[],
            status="verified",
        )
        ports.validate_manifest(manifest, operation="reset")
        ports.verify_artifacts(manifest, root=ports.outputs_dir)
        return MonthlyExecution(
            path=report_path,
            manifest=manifest,
            rollback=rollback_after_commit_failure,
        )
    except BaseException as exc:
        failed = await rollback_after_commit_failure()
        raise MonthlyManifestError(
            str(failed["status"]),
            "Reset output failed and rollback was evaluated",
            failed,
        ) from exc
