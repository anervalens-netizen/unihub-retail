"""Prerequisite, backup and report preparation for monthly Grile reset."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from services.grile_monthly_integrity import (
    MonthlyIntegrityError,
    base_manifest,
    manifest_sha256,
    relative_artifact,
    snapshot_sha256,
    utc_now,
)
from services.grile_monthly_reset_contracts import ResetPorts, ResetRunContext
from services.grile_monthly_types import MonthlyExecution, MonthlyManifestError, StoreEntry


def reset_manifest(
    context: ResetRunContext,
    *,
    errors: list[str],
    expected: dict[str, Any] | None = None,
    archive_manifest: dict[str, Any] | None = None,
    processed_stores: int = 0,
    source_backups: list[dict[str, Any]] | None = None,
    status: str = "failed",
    artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    expected = expected or {"stores": 0, "agents": 0}
    return base_manifest(
        month=context.closing_month_key,
        operation="reset",
        requested_by_sub=context.requested_by_sub,
        expected_stores=int(expected["stores"]),
        expected_agents=int(expected["agents"]),
        processed_stores=processed_stores,
        processed_agents=int(expected["agents"]) if status == "verified" else 0,
        control_totals=(archive_manifest or {}).get("control_totals", {}),
        artifacts=artifacts or [],
        source_backups=source_backups or [],
        errors=errors,
        status=status,
    )


def validate_request(context: ResetRunContext) -> None:
    if not context.dry_run and (
        context.operation_id is None or context.approved_manifest_id is None
    ):
        raise MonthlyManifestError(
            "approved_manifest_required",
            "Approved manifest is required",
            reset_manifest(context, errors=["approved_manifest_required"]),
        )
    if context.only and not context.dry_run:
        raise MonthlyManifestError(
            "partial_live_reset_forbidden",
            "Partial live reset is forbidden",
            reset_manifest(context, errors=["partial_live_reset_forbidden"]),
        )


async def load_archive(
    context: ResetRunContext,
    ports: ResetPorts,
) -> dict[str, Any]:
    latest = await ports.fetch_latest_manifest(
        context.pool,
        closing_month=context.closing_month_key,
        operation="archive",
        statuses=ports.manifest_statuses,
    )
    prerequisite = await _selected_prerequisite(context, latest, ports)
    archive = prerequisite.get("manifest") if prerequisite else None
    allowed = {"approved"} if not context.dry_run else {"verified", "approved"}
    if (
        prerequisite is None
        or prerequisite.get("status") not in allowed
        or not isinstance(archive, dict)
    ):
        raise MonthlyManifestError(
            "verified_archive_required",
            "Verified archive is required",
            reset_manifest(context, errors=["verified_archive_required"]),
        )
    ports.validate_manifest(archive, operation="archive")
    ports.verify_artifacts(archive, root=ports.outputs_dir)
    if not context.dry_run and (
        context.execution_owner is None or context.execution_epoch is None
    ):
        raise MonthlyIntegrityError(
            "operation_lease_missing",
            "Reset operation lease is missing",
        )
    return archive


async def _selected_prerequisite(
    context: ResetRunContext,
    latest: dict[str, Any] | None,
    ports: ResetPorts,
) -> dict[str, Any] | None:
    if context.approved_manifest_id is None:
        return latest
    prerequisite = await ports.fetch_manifest(
        context.pool,
        context.approved_manifest_id,
    )
    if latest is None or prerequisite is None or latest.get("id") != prerequisite.get("id"):
        return None
    return prerequisite


async def load_entries(
    context: ResetRunContext,
    archive: dict[str, Any],
    ports: ResetPorts,
) -> tuple[list[StoreEntry], dict[str, Any]]:
    entries = await ports.load_entries(
        context.pool,
        only=context.only,
        month=context.closing_month_key,
    )
    expected = archive["expected"]
    source_backups = archive.get("source_backups")
    archived_by_site = _backups_by_site(source_backups)
    if not _coverage_matches(entries, expected, source_backups, archived_by_site):
        raise MonthlyManifestError(
            "registry_or_archive_coverage_changed",
            "Registry or archive coverage changed before reset",
            reset_manifest(
                context,
                expected=expected,
                archive_manifest=archive,
                errors=["registry_or_archive_coverage_changed"],
            ),
        )
    return entries, expected


def _backups_by_site(source_backups: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(source_backups, list):
        return {}
    return {
        item["site_code"]: item
        for item in source_backups
        if isinstance(item, dict) and isinstance(item.get("site_code"), str)
    }


def _coverage_matches(
    entries: list[StoreEntry],
    expected: dict[str, Any],
    source_backups: Any,
    archived_by_site: dict[str, dict[str, Any]],
) -> bool:
    current_sites = {entry.site_code for entry in entries}
    return (
        len(entries) == int(expected["stores"])
        and set(archived_by_site) == current_sites
        and len(current_sites) == len(entries)
        and isinstance(source_backups, list)
        and len(source_backups) == len(entries)
        and all(_backup_matches(entry, archived_by_site[entry.site_code]) for entry in entries)
    )


def _backup_matches(entry: StoreEntry, backup: dict[str, Any]) -> bool:
    return (
        backup.get("sheet_id") == entry.sheet_id
        and backup.get("template_version", "v2") == entry.template_version
    )


async def prepare_execution(
    context: ResetRunContext,
    entries: list[StoreEntry],
    ports: ResetPorts,
) -> Any | None:
    sheets_service = None
    if context.google_adapter is None:
        sheets_service, _ = ports.build_google_services()
    if context.operation_id is not None and not context.dry_run:
        assert context.execution_owner is not None
        assert context.execution_epoch is not None
        await ports.ensure_reset_items(
            context.pool,
            operation_id=context.operation_id,
            closing_month_key=context.closing_month_key,
            next_month_key=context.next_month_key,
            entries=entries,
            execution_owner=context.execution_owner,
            execution_epoch=context.execution_epoch,
        )
    return sheets_service


async def capture_backups(
    context: ResetRunContext,
    *,
    entries: list[StoreEntry],
    sheets_service: Any,
    expected: dict[str, Any],
    archive: dict[str, Any],
    ports: ResetPorts,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    snapshots: dict[str, dict[str, Any]] = {}
    artifacts: list[dict[str, Any]] = []
    backup_dir = _backup_dir(context, ports)
    try:
        for entry in entries:
            snapshot = await _read_entry_snapshot(context, sheets_service, entry, ports)
            snapshots[entry.site_code] = snapshot
            if backup_dir is not None:
                artifacts.append(
                    await _persist_backup(context, entry, snapshot, backup_dir, ports)
                )
        if artifacts:
            ports.verify_artifacts({"artifacts": artifacts}, root=ports.outputs_dir)
        return snapshots, artifacts
    except BaseException as exc:
        code = exc.code if isinstance(exc, MonthlyIntegrityError) else "reset_preflight_failed"
        raise MonthlyManifestError(
            code,
            "Reset preflight failed",
            reset_manifest(
                context,
                expected=expected,
                archive_manifest=archive,
                processed_stores=len(snapshots),
                source_backups=artifacts,
                errors=[code],
            ),
        ) from exc


def _backup_dir(context: ResetRunContext, ports: ResetPorts) -> Path | None:
    if context.operation_id is None or context.dry_run:
        return None
    return ports.build_backup_dir(
        ports.outputs_dir,
        context.closing_month,
        context.operation_id,
    )


async def _read_entry_snapshot(
    context: ResetRunContext,
    sheets_service: Any,
    entry: StoreEntry,
    ports: ResetPorts,
) -> dict[str, Any]:
    if context.google_adapter is None:
        return ports.read_snapshot(sheets_service, entry)
    return await ports.read_snapshot_async(context.google_adapter, entry)


async def _persist_backup(
    context: ResetRunContext,
    entry: StoreEntry,
    snapshot: dict[str, Any],
    backup_dir: Path,
    ports: ResetPorts,
) -> dict[str, Any]:
    assert context.operation_id is not None
    assert context.execution_owner is not None
    assert context.execution_epoch is not None
    token = manifest_sha256({"site_code": entry.site_code})[:20]
    backup_path = backup_dir / f"source-{token}.json"
    ports.secure_write_json(
        backup_path,
        _backup_payload(context, entry, snapshot),
    )
    artifact = relative_artifact(
        backup_path,
        root=ports.outputs_dir,
        kind="reset_source_snapshot",
    )
    artifact.update(
        site_code=entry.site_code,
        sheet_id=entry.sheet_id,
        template_version=entry.template_version,
    )
    recorded = await ports.record_backup(
        context.pool,
        operation_id=context.operation_id,
        site_code=entry.site_code,
        backup_path=artifact["path"],
        backup_sha256=artifact["sha256"],
        execution_owner=context.execution_owner,
        execution_epoch=context.execution_epoch,
    )
    if not recorded:
        raise MonthlyIntegrityError("backup_checkpoint_failed", "Backup checkpoint failed")
    return artifact


def _backup_payload(
    context: ResetRunContext,
    entry: StoreEntry,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "operation_id": context.operation_id,
        "closing_month": context.closing_month_key,
        "site_code": entry.site_code,
        "sheet_id": entry.sheet_id,
        "template_version": entry.template_version,
        "snapshot": snapshot,
        "snapshot_sha256": snapshot_sha256(snapshot),
        "created_at": utc_now(),
    }


def report_artifact(
    context: ResetRunContext,
    *,
    expected: dict[str, Any],
    processed_stores: int,
    dry_run: bool,
    ports: ResetPorts,
) -> tuple[Path, dict[str, Any]]:
    report = _report_payload(context, expected, processed_stores, dry_run)
    report_path = (
        ports.build_dry_report_path(ports.outputs_dir, context.next_month)
        if dry_run
        else ports.build_report_path(ports.outputs_dir, context.next_month)
    )
    stage_dir = ports.staging_dir(
        "reset-dry-run" if dry_run else "reset",
        context.operation_id,
    )
    staged_report = stage_dir / "report.json"
    try:
        ports.secure_write_json(staged_report, report)
        ports.promote_file(staged_report, report_path)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
    artifact = relative_artifact(
        report_path,
        root=ports.outputs_dir,
        kind="reset_dry_run_report" if dry_run else "reset_report",
    )
    return report_path, artifact


def _report_payload(
    context: ResetRunContext,
    expected: dict[str, Any],
    processed_stores: int,
    dry_run: bool,
) -> dict[str, Any]:
    report = {
        "schema_version": 1,
        "operation": "reset",
        "month": context.closing_month_key,
        "next_month": context.next_month_key,
        "dry_run": dry_run,
        "expected_store_count": int(expected["stores"]),
        "processed_store_count": processed_stores,
        "error_count": 0,
        "created_at": utc_now(),
    }
    if not dry_run:
        report["approved_manifest_id"] = context.approved_manifest_id
    return report


def build_dry_run(
    context: ResetRunContext,
    *,
    expected: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
    archive: dict[str, Any],
    ports: ResetPorts,
) -> MonthlyExecution:
    report_path, artifact = report_artifact(
        context,
        expected=expected,
        processed_stores=len(snapshots),
        dry_run=True,
        ports=ports,
    )
    manifest = reset_manifest(
        context,
        expected=expected,
        archive_manifest=archive,
        processed_stores=len(snapshots),
        source_backups=archive.get("source_backups", []),
        artifacts=[artifact],
        errors=[],
        status="verified",
    )
    return MonthlyExecution(path=report_path, manifest=manifest)
