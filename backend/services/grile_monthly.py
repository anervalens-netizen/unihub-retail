"""Public compatibility facade for focused monthly Grile modules."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import asyncpg
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from repositories import grile_monthly_operations as monthly_repo
from repositories.grile_monthly_registry import fetch_active_registry
from services import grile_monthly_archive_artifacts as archive_artifacts
from services import grile_monthly_artifacts as artifacts
from services import grile_monthly_execution_adapters as execution_adapters
from services import grile_monthly_google_api as google_api
from services import grile_monthly_lease as monthly_lease
from services import grile_monthly_reconciler as reconciler
from services import grile_monthly_registry as registry
from services import grile_monthly_reset_adapters as reset_adapters
from services.grile_constants import (
    GOOGLE_API_RETRY_ATTEMPTS,
    GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
)
from services.grile_monthly_artifacts import (
    ARCHIVE_DIR_NAME,
    FINAL_EXPORT_NAME_PREFIX,
    build_archive_dir,
    build_archive_manifest_path,
    build_archive_zip_path,
    build_final_export_path,
    build_manager_zip_path,
    build_reset_backup_dir,
    build_reset_dry_run_report_path,
    build_reset_report_path,
    build_store_export_path,
    make_output_row,
    month_slug,
    resolve_output_path,
    safe_filename,
    style_sheet,
    validate_archive_manifest,
)
from services.grile_monthly_google import (
    GoogleAdapterClosed,
    GoogleSyncAdapter,
    call_with_backoff,
)
from services.grile_monthly_integrity import (
    MonthlyIntegrityError,
    base_manifest,
    canonical_snapshot,
    file_sha256,
    finalize_manifest,
    manifest_sha256,
    relative_artifact,
    resolve_artifact_path,
    secure_directory,
    secure_file,
    secure_write_json,
    snapshot_sha256,
    utc_now,
    validate_verified_manifest,
    verify_artifacts,
)
from services.grile_monthly_parsing import (
    control_totals as _control_totals,
    error_row as _error_row,
    finalization_coverage as _validate_finalization_coverage,
    parse_store_rows,
    scalar,
    source_registry as _source_registry,
    sum_scalars,
    to_number,
    value_ranges_for_entry,
    with_source_registry as _with_source_registry,
)
from services.grile_monthly_state import (
    GrileMonthlyRetryBlockedError,
    MonthlyOperationReservation,
    MonthlyOperationStartResult,
    safe_persisted_result,
)
from services.grile_monthly_types import (
    AUDIT_HEADERS,
    GRILA_CELLS,
    GRILA_CELLS_V3,
    HEADERS,
    RESET_RANGES,
    RESET_RANGES_V3,
    RO_MONTHS,
    ExtractedAgentRow,
    MonthlyExecution,
    MonthlyManifestError,
    StoreEntry,
    cells_for_entry,
    next_ym,
    reset_ranges_for_entry,
    ro_month_label,
)


# Repository aliases are intentionally public: workers and characterization
# tests replace them at this facade boundary.
MonthlyExecutionLease = monthly_repo.MonthlyExecutionLease
ResetItemInput = monthly_repo.ResetItemInput
persist_monthly_operation_job = monthly_repo.attach_job
persist_reset_item_claim = monthly_repo.claim_reset_item
persist_reset_items = monthly_repo.ensure_reset_items
persist_monthly_operation_failure = monthly_repo.fail
persist_queued_monthly_operation_failure = monthly_repo.fail_queued
fetch_monthly_execution_lease = monthly_repo.get_execution_lease
persist_cancelled_uncertain = monthly_repo.mark_cancelled_uncertain
persist_monthly_operation_result = monthly_repo.finish
persist_reset_success = monthly_repo.finish_reset_success
persist_reset_item_result = monthly_repo.finish_reset_item
fetch_latest_monthly_manifest = monthly_repo.get_latest_manifest
fetch_monthly_manifest = monthly_repo.get_manifest
fetch_operation_manifest = monthly_repo.get_operation_manifest
fetch_previous_completed_reset_item = monthly_repo.get_previous_completed_reset_item
persist_monthly_operation_heartbeat = monthly_repo.heartbeat
persist_monthly_manifest_approval = monthly_repo.approve_manifest
persist_manifest_result = monthly_repo.persist_manifest_result
persist_reset_item_backup = monthly_repo.record_reset_item_backup
persist_reset_item_rollback = monthly_repo.record_reset_item_rollback
persist_reset_clear_intent = monthly_repo.prepare_reset_clear
persist_reset_clear_confirmation = monthly_repo.confirm_reset_clear
persist_reset_rollback_intent = monthly_repo.prepare_reset_rollback
persist_reset_rollback_confirmation = monthly_repo.confirm_reset_rollback
claim_reconciliation_candidates = monthly_repo.claim_reconciliation_candidates
list_reset_items_for_reconciliation = monthly_repo.list_reset_items_for_reconciliation
mark_item_recovery_required = monthly_repo.mark_item_recovery_required
mark_item_safe_retry = monthly_repo.mark_item_safe_retry
mark_reconciliation_result = monthly_repo.mark_reconciliation_result
persisted_operation_to_dict = monthly_repo.operation_to_dict
persist_monthly_operation_reservation = monthly_repo.reserve
persist_monthly_operation_start = monthly_repo.start

GOOGLE_OPERATION_DEADLINE_SECONDS = 120.0
MONTHLY_OPERATION_HEARTBEAT_SECONDS = 60.0
VALID_OPS = {"finalize", "archive", "reset"}
MANIFEST_ATTEMPT_STATUSES = (
    "building", "failed", "verified", "approved", "consumed", "rolled_back", "uncertain"
)
VALID_DOWNLOADS = {"final": "final", "archive": "archive"}
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = Path(os.getenv("GRILE_OUTPUTS_DIR", BASE_DIR / "outputs" / "grile"))
_TRANSIENT = {429, 500, 502, 503, 504}


def _api() -> Any:
    return sys.modules[__name__]


def _sa_file() -> Path:
    return google_api.service_account_file(_api())


def get_credentials() -> Any:
    return google_api.credentials(_api())


def build_google_services() -> tuple[Any, Any]:
    return google_api.build_services(_api())


def _is_transient(exc: Exception) -> bool:
    return google_api.is_transient(_api(), exc)


def _google_error_code(exc: Exception) -> str:
    return google_api.error_code(_api(), exc)


def retry_api(fn: Any, *, label: str, attempts: int = 4, base_delay: float = 1.0) -> Any:
    return google_api.retry(
        _api(), fn, label=label, attempts=attempts, base_delay=base_delay
    )


async def _google_request(
    adapter: GoogleSyncAdapter,
    operation: str,
    request: dict[str, Any],
    *,
    label: str,
    destructive: bool = False,
) -> Any:
    return await google_api.request(
        _api(), adapter, operation, request, label=label, destructive=destructive
    )


def _company_from_values(registry_key: str | None, fallback: str | None) -> str:
    return registry.company_from_values(registry_key, fallback)


def _store_from_values(registry_key: str | None, fallback: str | None) -> str:
    return registry.store_from_values(registry_key, fallback)


async def load_entries(
    pool: asyncpg.Pool,
    only: str | None = None,
    *,
    month: str | None = None,
) -> list[StoreEntry]:
    return await registry.load_entries(
        pool,
        only,
        month=month,
        fetch_registry=fetch_active_registry,
    )


def _operation_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    return persisted_operation_to_dict(row)


def _safe_operation_result(operation: dict[str, Any] | None) -> dict[str, Any] | None:
    return safe_persisted_result(operation)


async def reserve_monthly_operation(*args: Any, **kwargs: Any) -> MonthlyOperationReservation:
    if kwargs.get("op") not in VALID_OPS:
        raise ValueError(f"Operatie necunoscuta: {kwargs.get('op')}")
    return await persist_monthly_operation_reservation(*args, **kwargs)


async def attach_monthly_operation_job(*args: Any, **kwargs: Any) -> bool:
    return await persist_monthly_operation_job(*args, **kwargs)


async def start_monthly_operation(*args: Any, **kwargs: Any) -> MonthlyOperationStartResult:
    return await persist_monthly_operation_start(*args, **kwargs)


async def heartbeat_monthly_operation(*args: Any, **kwargs: Any) -> bool:
    return await persist_monthly_operation_heartbeat(*args, **kwargs)


async def _run_with_monthly_lease(
    pool: Any,
    operation_id: int,
    *,
    execution_owner: str,
    execution_epoch: int,
    operation: Any,
    heartbeat_interval: float = MONTHLY_OPERATION_HEARTBEAT_SECONDS,
) -> MonthlyExecution:
    return await monthly_lease.run_with_lease(
        pool,
        operation_id,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
        operation=operation,
        heartbeat_interval=heartbeat_interval,
        heartbeat=heartbeat_monthly_operation,
    )


async def finish_monthly_operation(*args: Any, **kwargs: Any) -> bool:
    return await persist_monthly_operation_result(*args, **kwargs)


async def fail_monthly_operation(*args: Any, **kwargs: Any) -> bool:
    return await persist_monthly_operation_failure(*args, **kwargs)


async def fail_queued_monthly_operation(*args: Any, **kwargs: Any) -> bool:
    return await persist_queued_monthly_operation_failure(*args, **kwargs)


async def get_monthly_execution_lease(*args: Any, **kwargs: Any) -> Any:
    return await fetch_monthly_execution_lease(*args, **kwargs)


async def mark_monthly_operation_cancelled_uncertain(*args: Any, **kwargs: Any) -> bool:
    return await persist_cancelled_uncertain(*args, **kwargs)


async def get_monthly_manifest(pool: Any, manifest_id: int) -> dict[str, Any] | None:
    return await fetch_monthly_manifest(pool, manifest_id)


async def get_latest_monthly_manifest(pool: Any, *, month: str) -> dict[str, Any] | None:
    return await fetch_latest_monthly_manifest(
        pool,
        closing_month=month,
        operation="archive",
        statuses=MANIFEST_ATTEMPT_STATUSES,
    )


async def ensure_reset_items(
    pool: Any,
    *,
    operation_id: int,
    closing_month_key: str,
    next_month_key: str,
    entries: list[StoreEntry],
    execution_owner: str,
    execution_epoch: int,
) -> None:
    items = [
        ResetItemInput(
            site_code=entry.site_code,
            sheet_id=entry.sheet_id,
            company=entry.company,
            store=entry.store,
            ranges=tuple(reset_ranges_for_entry(entry)),
        )
        for entry in entries
    ]
    await persist_reset_items(
        pool,
        operation_id=operation_id,
        closing_month=closing_month_key,
        next_month=next_month_key,
        entries=items,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
    )


async def get_previous_completed_reset_item(*args: Any, **kwargs: Any) -> Any:
    if "closing_month_key" in kwargs:
        kwargs["closing_month"] = kwargs.pop("closing_month_key")
    return await fetch_previous_completed_reset_item(*args, **kwargs)


async def mark_reset_item_running(*args: Any, **kwargs: Any) -> bool:
    return await persist_reset_item_claim(*args, **kwargs)


async def finish_reset_item(*args: Any, **kwargs: Any) -> bool:
    return await persist_reset_item_result(*args, **kwargs)


async def record_reset_item_backup(*args: Any, **kwargs: Any) -> bool:
    return await persist_reset_item_backup(*args, **kwargs)


async def record_reset_item_rollback(*args: Any, **kwargs: Any) -> bool:
    return await persist_reset_item_rollback(*args, **kwargs)


def extract_store_rows(
    sheets_svc: Any,
    entry: StoreEntry,
    *,
    value_ranges: list[dict[str, Any]] | None = None,
) -> list[ExtractedAgentRow]:
    try:
        ranges = value_ranges_for_entry(entry)
        parsed = value_ranges if value_ranges is not None else _read_store_value_ranges(
            sheets_svc, entry, ranges
        )
        if len(parsed) != len(ranges):
            raise MonthlyIntegrityError(
                "google_response_incomplete", "Google sheet response is incomplete"
            )
        return parse_store_rows(entry, parsed)
    except Exception as exc:  # noqa: BLE001 - error becomes an auditable row
        code = exc.code if isinstance(exc, MonthlyIntegrityError) else _google_error_code(exc)
        return [_error_row(entry, slot=0, code=code)]


def _read_store_value_ranges(
    sheets_service: Any, entry: StoreEntry, ranges: list[str]
) -> list[dict[str, Any]]:
    def read_values() -> Any:
        return sheets_service.spreadsheets().values().batchGet(
            spreadsheetId=entry.sheet_id,
            ranges=ranges,
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute()

    response = retry_api(
        read_values,
        label="Google sheet read",
        attempts=GOOGLE_API_RETRY_ATTEMPTS,
        base_delay=GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
    )
    parsed = response.get("valueRanges") if isinstance(response, dict) else None
    if not isinstance(parsed, list):
        raise MonthlyIntegrityError(
            "google_response_incomplete", "Google sheet response is incomplete"
        )
    return parsed


def build_workbook(*args: Any, **kwargs: Any) -> None:
    artifacts.build_workbook(*args, **kwargs, style=style_sheet)


def _validate_final_workbook(*args: Any, **kwargs: Any) -> None:
    artifacts.validate_final_workbook(*args, **kwargs)


def _staging_dir(operation: str, operation_id: int | None) -> Path:
    return artifacts.staging_dir(OUTPUTS_DIR, operation, operation_id)


def _promote_file(staged: Path, destination: Path) -> None:
    artifacts.promote_file(OUTPUTS_DIR, staged, destination)


async def _finalize_month_execution(*args: Any, **kwargs: Any) -> MonthlyExecution:
    return await execution_adapters.finalize_execution(_api(), *args, **kwargs)


async def finalize_month(*args: Any, **kwargs: Any) -> Path:
    return await execution_adapters.finalize_month(_api(), *args, **kwargs)


def export_sheet_xlsx(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return archive_artifacts.export_sheet_xlsx(
        *args,
        **kwargs,
        downloader_type=MediaIoBaseDownload,
        secure_directory=secure_directory,
        secure_file=secure_file,
    )


def write_exported_xlsx(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return archive_artifacts.write_exported_xlsx(
        *args, **kwargs, secure_directory=secure_directory, secure_file=secure_file
    )


def create_archive_zip(zip_path: Path, files: list[Path], archive_dir: Path) -> None:
    archive_artifacts.create_archive_zip(
        zip_path, files, archive_dir, secure_directory=secure_directory
    )


def create_manager_zips(*args: Any, **kwargs: Any) -> dict[str, Path]:
    return archive_artifacts.create_manager_zips(
        *args,
        **kwargs,
        build_archive_dir=build_archive_dir,
        build_manager_zip_path=build_manager_zip_path,
        create_zip=create_archive_zip,
    )


def summarize_archive_results(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return archive_artifacts.summarize_archive_results(*args, **kwargs, now=utc_now)


def _validate_archive_zip(*args: Any, **kwargs: Any) -> None:
    archive_artifacts.validate_archive_zip(*args, **kwargs)


def _validate_source_workbook(path: Path) -> None:
    archive_artifacts.validate_source_workbook(path)


def _future_artifact(staged_path: Path, **kwargs: Any) -> dict[str, Any]:
    return archive_artifacts.future_artifact(staged_path, outputs_dir=OUTPUTS_DIR, **kwargs)


def _promote_directory(staged: Path, destination: Path, **kwargs: Any) -> None:
    archive_artifacts.promote_directory(
        staged,
        destination,
        outputs_dir=OUTPUTS_DIR,
        safe_filename=safe_filename,
        secure_directory=secure_directory,
        **kwargs,
    )


async def _archive_month_execution(*args: Any, **kwargs: Any) -> MonthlyExecution:
    return await execution_adapters.archive_execution(_api(), *args, **kwargs)


async def archive_month(*args: Any, **kwargs: Any) -> Path:
    return await execution_adapters.archive_month(_api(), *args, **kwargs)


def public_manifest_payload(record: dict[str, Any]) -> dict[str, Any]:
    return execution_adapters.public_manifest_payload(record)


def _public_timestamp(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


async def approve_monthly_manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return await execution_adapters.approve_manifest(_api(), *args, **kwargs)


def _read_reset_snapshot(sheets_svc: Any, entry: StoreEntry) -> dict[str, Any]:
    return reset_adapters.read_snapshot(_api(), sheets_svc, entry)


async def _read_reset_snapshot_async(adapter: Any, entry: StoreEntry) -> dict[str, Any]:
    return await reset_adapters.read_snapshot_async(_api(), adapter, entry)


def _restore_reset_snapshot(service: Any, entry: StoreEntry, snapshot: dict[str, Any]) -> None:
    reset_adapters.restore_snapshot(_api(), service, entry, snapshot)


async def _restore_reset_snapshot_async(
    adapter: Any, entry: StoreEntry, snapshot: dict[str, Any]
) -> None:
    await reset_adapters.restore_snapshot_async(_api(), adapter, entry, snapshot)


def _verify_reset_cleared(service: Any, entry: StoreEntry) -> None:
    reset_adapters.verify_cleared(_api(), service, entry)


async def _verify_reset_cleared_async(adapter: Any, entry: StoreEntry) -> None:
    await reset_adapters.verify_cleared_async(_api(), adapter, entry)


def reset_store(service: Any | None, entry: StoreEntry, *, dry_run: bool) -> dict[str, Any]:
    return reset_adapters.reset_store(_api(), service, entry, dry_run=dry_run)


async def _rollback_reset_entries(*args: Any, **kwargs: Any) -> bool:
    return await reset_adapters.rollback_sync(_api(), *args, **kwargs)


async def _rollback_reset_entries_cancel_safe(*args: Any, **kwargs: Any) -> bool:
    return await reset_adapters.cancel_safe(lambda: _rollback_reset_entries(*args, **kwargs))


async def _rollback_reset_entries_adapter(*args: Any, **kwargs: Any) -> bool:
    return await reset_adapters.rollback_adapter(_api(), *args, **kwargs)


async def _rollback_reset_entries_adapter_cancel_safe(*args: Any, **kwargs: Any) -> bool:
    return await reset_adapters.cancel_safe(
        lambda: _rollback_reset_entries_adapter(*args, **kwargs)
    )


async def _reset_month_execution(*args: Any, **kwargs: Any) -> MonthlyExecution:
    return await execution_adapters.reset_execution(_api(), *args, **kwargs)


async def reset_month(*args: Any, **kwargs: Any) -> Path:
    return await execution_adapters.reset_month(_api(), *args, **kwargs)


def _reconciliation_entry(item: dict[str, Any]) -> StoreEntry:
    return reconciler.reconciliation_entry(item)


def _read_reset_backup(item: dict[str, Any]) -> dict[str, Any]:
    return reconciler.read_reset_backup(item, outputs_dir=OUTPUTS_DIR)


def _snapshot_is_cleared(snapshot: dict[str, Any]) -> bool:
    return reconciler.snapshot_is_cleared(snapshot)


async def reconcile_monthly_operations(pool: Any, google_adapter: Any) -> int:
    return await execution_adapters.reconcile(_api(), pool, google_adapter)


async def _monthly_operation_pool() -> Any:
    from db.connection import get_pool

    return await get_pool()


def _monthly_run_ports() -> Any:
    return execution_adapters.monthly_run_ports(_api())


async def run_monthly_op(**kwargs: Any) -> dict[str, Any]:
    return await execution_adapters.run_monthly_op(_api(), **kwargs)


async def fetch_download(kind: str, month: str) -> tuple[bytes, str, str]:
    return await execution_adapters.fetch_download(_api(), kind, month)
