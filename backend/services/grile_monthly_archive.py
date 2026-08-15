"""Archive export and publication orchestration for monthly Grile closeout."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from services.grile_monthly_integrity import (
    MonthlyIntegrityError,
    base_manifest,
)
from services.grile_monthly_types import (
    MonthlyExecution,
    MonthlyManifestError,
    StoreEntry,
)


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class ArchiveRequest:
    month: str
    month_key: str
    requested_by_sub: str
    operation_id: int | None
    only: str | None
    delay: float
    google_adapter: Any | None


@dataclass(frozen=True)
class ArchivePorts:
    outputs_dir: Path
    manifest_statuses: tuple[str, ...]
    fetch_latest_manifest: Callable[..., Awaitable[dict[str, Any] | None]]
    load_entries: Callable[..., Awaitable[list[StoreEntry]]]
    source_registry: Callable[[list[StoreEntry]], list[dict[str, str]]]
    validate_manifest: Callable[..., None]
    verify_artifacts: Callable[..., None]
    build_google_services: Callable[[], tuple[Any, Any]]
    staging_dir: Callable[[str, int | None], Path]
    build_archive_dir: Callable[[Path, str], Path]
    build_store_export_path: Callable[[Path, str, StoreEntry], Path]
    build_archive_zip_path: Callable[[Path, str], Path]
    build_archive_manifest_path: Callable[[Path, str], Path]
    retry_api: Callable[..., Any]
    retry_attempts: int
    retry_base_delay: float
    export_sheet_xlsx: Callable[[Any, StoreEntry, Path], dict[str, Any]]
    google_request: Callable[..., Awaitable[Any]]
    write_exported_xlsx: Callable[[StoreEntry, Path, bytes], dict[str, Any]]
    validate_source_workbook: Callable[[Path], None]
    create_archive_zip: Callable[[Path, list[Path], Path], None]
    create_manager_zips: Callable[[Path, str, list[dict[str, Any]]], dict[str, Path]]
    secure_file: Callable[[Path], None]
    validate_archive_zip: Callable[..., None]
    future_artifact: Callable[..., dict[str, Any]]
    secure_write_json: Callable[[Path, dict[str, Any]], None]
    promote_directory: Callable[..., None]
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep


@dataclass(frozen=True)
class ArchiveWorkspace:
    stage_root: Path
    staged_archive_dir: Path
    official_archive_dir: Path


@dataclass
class ArchiveExports:
    results: list[dict[str, Any]]
    files: list[Path]
    errors: list[str]


async def execute_archive(
    pool: Any,
    request: ArchiveRequest,
    ports: ArchivePorts,
) -> MonthlyExecution:
    _reject_partial(request)
    final_manifest = await _load_final_manifest(pool, request, ports)
    entries = await ports.load_entries(pool, month=request.month_key)
    _require_unchanged_registry(entries, final_manifest, request, ports)
    workspace = _workspace(request, ports)
    try:
        drive_service = _drive_service(request, ports)
        exports = await _export_entries(
            entries,
            drive_service,
            workspace,
            request,
            ports,
        )
        _require_complete(exports, entries, final_manifest, request)
        return _publish_archive(
            entries,
            exports,
            final_manifest,
            workspace,
            request,
            ports,
        )
    finally:
        shutil.rmtree(workspace.stage_root, ignore_errors=True)


def _reject_partial(request: ArchiveRequest) -> None:
    if not request.only:
        return
    failed = _failure_manifest(request, 0, 0, 0, 0, {}, ["partial_archive_forbidden"])
    raise MonthlyManifestError(
        "partial_archive_forbidden",
        "Partial archive is not allowed",
        failed,
    )


async def _load_final_manifest(
    pool: Any,
    request: ArchiveRequest,
    ports: ArchivePorts,
) -> dict[str, Any]:
    record = await ports.fetch_latest_manifest(
        pool,
        closing_month=request.month_key,
        operation="finalize",
        statuses=ports.manifest_statuses,
    )
    manifest = record.get("manifest") if record else None
    if record is None or record.get("status") != "verified" or not isinstance(manifest, dict):
        failed = _failure_manifest(
            request,
            0,
            0,
            0,
            0,
            {},
            ["verified_finalization_missing"],
        )
        raise MonthlyManifestError(
            "verified_finalization_missing",
            "Verified finalization is required",
            failed,
        )
    ports.validate_manifest(manifest, operation="finalize")
    ports.verify_artifacts(manifest, root=ports.outputs_dir)
    return manifest


def _require_unchanged_registry(
    entries: list[StoreEntry],
    final_manifest: dict[str, Any],
    request: ArchiveRequest,
    ports: ArchivePorts,
) -> None:
    expected = final_manifest["expected"]
    unchanged = (
        len(entries) == expected["stores"]
        and len({entry.site_code for entry in entries}) == len(entries)
        and len({entry.sheet_id for entry in entries}) == len(entries)
        and final_manifest.get("source_registry") == ports.source_registry(entries)
    )
    if unchanged:
        return
    failed = _failure_manifest(
        request,
        int(expected["stores"]),
        int(expected["agents"]),
        0,
        0,
        final_manifest.get("control_totals", {}),
        ["registry_changed_or_duplicate_after_finalization"],
    )
    raise MonthlyManifestError(
        "registry_changed_or_duplicate_after_finalization",
        "Registry changed after finalization",
        failed,
    )


def _workspace(request: ArchiveRequest, ports: ArchivePorts) -> ArchiveWorkspace:
    stage_root = ports.staging_dir("archive", request.operation_id)
    return ArchiveWorkspace(
        stage_root,
        ports.build_archive_dir(stage_root, request.month),
        ports.build_archive_dir(ports.outputs_dir, request.month),
    )


def _drive_service(request: ArchiveRequest, ports: ArchivePorts) -> Any:
    if request.google_adapter is not None:
        return None
    _, drive_service = ports.build_google_services()
    return drive_service


async def _export_entries(
    entries: list[StoreEntry],
    drive_service: Any,
    workspace: ArchiveWorkspace,
    request: ArchiveRequest,
    ports: ArchivePorts,
) -> ArchiveExports:
    exports = ArchiveExports([], [], [])
    for index, entry in enumerate(entries, start=1):
        output_path = ports.build_store_export_path(
            workspace.stage_root,
            request.month,
            entry,
        )
        result, error_code = await _export_entry(
            entry,
            output_path,
            drive_service,
            request,
            ports,
        )
        exports.results.append(result)
        if result["status"] == "OK":
            exports.files.append(Path(result["xlsx_path"]))
        if error_code is not None:
            exports.errors.append(error_code)
        if request.delay > 0 and index < len(entries):
            await ports.sleep(request.delay)
    return exports


async def _export_entry(
    entry: StoreEntry,
    output_path: Path,
    drive_service: Any,
    request: ArchiveRequest,
    ports: ArchivePorts,
) -> tuple[dict[str, Any], str | None]:
    try:
        if request.google_adapter is None:
            result = ports.retry_api(
                lambda: ports.export_sheet_xlsx(drive_service, entry, output_path),
                label="Google source export",
                attempts=ports.retry_attempts,
                base_delay=ports.retry_base_delay,
            )
        else:
            content = await ports.google_request(
                request.google_adapter,
                "export_xlsx",
                {"spreadsheet_id": entry.sheet_id, "mime_type": XLSX_MIME},
                label="Google source export",
            )
            result = ports.write_exported_xlsx(entry, output_path, content)
        ports.validate_source_workbook(Path(result["xlsx_path"]))
        return result, None
    except MonthlyIntegrityError as exc:
        return _export_error(entry, exc.code), exc.code


def _export_error(entry: StoreEntry, code: str) -> dict[str, Any]:
    return {
        "company": entry.company,
        "store": entry.store,
        "site_code": entry.site_code,
        "manager": entry.manager,
        "sheet_id": entry.sheet_id,
        "template_version": entry.template_version,
        "status": "ERROR",
        "xlsx_path": "",
        "bytes": 0,
        "error": code,
    }


def _require_complete(
    exports: ArchiveExports,
    entries: list[StoreEntry],
    final_manifest: dict[str, Any],
    request: ArchiveRequest,
) -> None:
    if not exports.errors and len(exports.files) == len(entries):
        return
    expected_agents = int(final_manifest["expected"]["agents"])
    failed = _failure_manifest(
        request,
        len(entries),
        expected_agents,
        len(exports.files),
        expected_agents if not exports.errors else 0,
        final_manifest.get("control_totals", {}),
        exports.errors or ["archive_coverage_incomplete"],
    )
    raise MonthlyManifestError("archive_incomplete", "Archive is incomplete", failed)


def _publish_archive(
    entries: list[StoreEntry],
    exports: ArchiveExports,
    final_manifest: dict[str, Any],
    workspace: ArchiveWorkspace,
    request: ArchiveRequest,
    ports: ArchivePorts,
) -> MonthlyExecution:
    zip_path, manager_zips = _build_zips(entries, exports, workspace, request, ports)
    source_backups, artifacts = _archive_artifacts(
        exports,
        zip_path,
        manager_zips,
        final_manifest,
        workspace,
        ports,
    )
    manifest = _verified_manifest(
        request,
        entries,
        final_manifest,
        artifacts,
        source_backups,
    )
    ports.validate_manifest(manifest, operation="archive")
    staged_manifest = ports.build_archive_manifest_path(workspace.stage_root, request.month)
    ports.secure_write_json(staged_manifest, manifest)
    official_manifest = ports.build_archive_manifest_path(ports.outputs_dir, request.month)
    ports.promote_directory(
        workspace.staged_archive_dir,
        workspace.official_archive_dir,
        verify=lambda: ports.verify_artifacts(manifest, root=ports.outputs_dir),
    )
    return MonthlyExecution(path=official_manifest, manifest=manifest)


def _build_zips(
    entries: list[StoreEntry],
    exports: ArchiveExports,
    workspace: ArchiveWorkspace,
    request: ArchiveRequest,
    ports: ArchivePorts,
) -> tuple[Path, dict[str, Path]]:
    zip_path = ports.build_archive_zip_path(workspace.stage_root, request.month)
    ports.create_archive_zip(zip_path, exports.files, workspace.staged_archive_dir)
    ports.secure_file(zip_path)
    ports.validate_archive_zip(zip_path, expected_files=len(entries))
    manager_zips = ports.create_manager_zips(
        workspace.stage_root,
        request.month,
        exports.results,
    )
    for path in manager_zips.values():
        ports.secure_file(path)
    return zip_path, manager_zips


def _archive_artifacts(
    exports: ArchiveExports,
    zip_path: Path,
    manager_zips: dict[str, Path],
    final_manifest: dict[str, Any],
    workspace: ArchiveWorkspace,
    ports: ArchivePorts,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_backups = [
        ports.future_artifact(
            Path(result["xlsx_path"]),
            staged_archive_dir=workspace.staged_archive_dir,
            official_archive_dir=workspace.official_archive_dir,
            kind="source_workbook",
            extra={
                "site_code": result["site_code"],
                "sheet_id": result["sheet_id"],
                "template_version": result.get("template_version", "v2"),
            },
        )
        for result in exports.results
    ]
    generated = [
        ports.future_artifact(
            zip_path,
            staged_archive_dir=workspace.staged_archive_dir,
            official_archive_dir=workspace.official_archive_dir,
            kind="archive_zip",
        ),
        *source_backups,
        *[
            ports.future_artifact(
                path,
                staged_archive_dir=workspace.staged_archive_dir,
                official_archive_dir=workspace.official_archive_dir,
                kind="manager_archive_zip",
            )
            for path in manager_zips.values()
        ],
    ]
    return source_backups, [*generated, *map(dict, final_manifest["artifacts"])]


def _verified_manifest(
    request: ArchiveRequest,
    entries: list[StoreEntry],
    final_manifest: dict[str, Any],
    artifacts: list[dict[str, Any]],
    source_backups: list[dict[str, Any]],
) -> dict[str, Any]:
    agents = int(final_manifest["expected"]["agents"])
    return base_manifest(
        month=request.month_key,
        operation="archive",
        requested_by_sub=request.requested_by_sub,
        expected_stores=len(entries),
        expected_agents=agents,
        processed_stores=len(entries),
        processed_agents=agents,
        control_totals=final_manifest.get("control_totals", {}),
        artifacts=artifacts,
        source_backups=source_backups,
    )


def _failure_manifest(
    request: ArchiveRequest,
    expected_stores: int,
    expected_agents: int,
    processed_stores: int,
    processed_agents: int,
    totals: dict[str, str],
    errors: list[str],
) -> dict[str, Any]:
    return base_manifest(
        month=request.month_key,
        operation="archive",
        requested_by_sub=request.requested_by_sub,
        expected_stores=expected_stores,
        expected_agents=expected_agents,
        processed_stores=processed_stores,
        processed_agents=processed_agents,
        control_totals=totals,
        artifacts=[],
        errors=errors,
        status="failed",
    )
