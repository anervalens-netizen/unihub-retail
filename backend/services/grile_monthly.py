"""Operatii lunare native pentru grile in UniHub Retail.

Inlocuieste proxy-ul catre aplicatia veche `grile-salarii`: Retail citeste
registrul din DB (`grile_sheets` + `stores`), genereaza Excelul final, arhiva
XLSX/ZIP si ruleaza resetul controlat direct cu Google APIs.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Coroutine, Literal
from uuid import uuid4

import asyncpg
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from repositories.grile_monthly_operations import (
    MonthlyExecutionLease,
    ResetItemInput,
    attach_job as persist_monthly_operation_job,
    claim_reset_item as persist_reset_item_claim,
    ensure_reset_items as persist_reset_items,
    fail as persist_monthly_operation_failure,
    fail_queued as persist_queued_monthly_operation_failure,
    get_execution_lease as fetch_monthly_execution_lease,
    mark_cancelled_uncertain as persist_cancelled_uncertain,
    finish as persist_monthly_operation_result,
    finish_reset_success as persist_reset_success,
    finish_reset_item as persist_reset_item_result,
    get_latest_manifest as fetch_latest_monthly_manifest,
    get_manifest as fetch_monthly_manifest,
    get_operation_manifest as fetch_operation_manifest,
    get_previous_completed_reset_item as fetch_previous_completed_reset_item,
    heartbeat as persist_monthly_operation_heartbeat,
    approve_manifest as persist_monthly_manifest_approval,
    persist_manifest_result,
    record_reset_item_backup as persist_reset_item_backup,
    record_reset_item_rollback as persist_reset_item_rollback,
    prepare_reset_clear as persist_reset_clear_intent,
    confirm_reset_clear as persist_reset_clear_confirmation,
    prepare_reset_rollback as persist_reset_rollback_intent,
    confirm_reset_rollback as persist_reset_rollback_confirmation,
    claim_reconciliation_candidates,
    list_reset_items_for_reconciliation,
    mark_item_recovery_required,
    mark_item_safe_retry,
    mark_reconciliation_result,
    operation_to_dict as persisted_operation_to_dict,
    reserve as persist_monthly_operation_reservation,
    start as persist_monthly_operation_start,
)
from services.grile_monthly_google import (
    GoogleAdapterClosed,
    GoogleSyncAdapter,
    call_with_backoff,
)
from services.grile_monthly_finalization import (
    FinalizationPorts,
    FinalizationRequest,
    execute_finalization,
)
from services import grile_monthly_reset_google as reset_google
from services import grile_monthly_reset_rollback as reset_rollback
from services.grile_monthly_reset_contracts import ResetPorts, ResetRunContext
from services.grile_monthly_reset_execution import execute_reset
from services import grile_monthly_artifacts as monthly_artifacts
from services import grile_monthly_archive_artifacts as monthly_archive_artifacts
from services.grile_monthly_archive import (
    ArchivePorts,
    ArchiveRequest,
    execute_archive,
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
from services.grile_monthly_state import (
    GrileMonthlyRetryBlockedError,
    MonthlyOperationReservation,
    MonthlyOperationStartResult,
    safe_persisted_result,
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
from services.grile_constants import (
    GOOGLE_API_RETRY_ATTEMPTS,
    GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
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
    secure_directory, secure_file,
    secure_write_json,
    snapshot_sha256,
    utc_now,
    validate_verified_manifest,
    verify_artifacts,
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

GOOGLE_OPERATION_DEADLINE_SECONDS = 120.0
MONTHLY_OPERATION_HEARTBEAT_SECONDS = 60.0

VALID_OPS = {"finalize", "archive", "reset"}
MANIFEST_ATTEMPT_STATUSES = (
    "building",
    "failed",
    "verified",
    "approved",
    "consumed",
    "rolled_back",
    "uncertain",
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


def _sa_file() -> Path:
    return Path(
        os.getenv(
            "GRILE_GOOGLE_SA_FILE",
            BASE_DIR / "config" / "google" / "service-account.json",
        )
    )


def get_credentials() -> Any:
    from google.oauth2.service_account import Credentials

    path = _sa_file()
    if not path.exists():
        raise FileNotFoundError(
            f"Service account Google lipsa: {path}. Pune fisierul sau seteaza GRILE_GOOGLE_SA_FILE."
        )
    return Credentials.from_service_account_file(str(path), scopes=SCOPES)


def build_google_services() -> tuple[Any, Any]:
    creds = get_credentials()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    return sheets, drive


def _is_transient(exc: Exception) -> bool:
    status = getattr(getattr(exc, "resp", None), "status", None)
    return status in _TRANSIENT


def _google_error_code(exc: Exception) -> str:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status == 429:
        return "google_rate_limited"
    if status in {500, 502, 503, 504}:
        return "google_unavailable"
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "google_timeout"
    return "google_request_failed"


def retry_api(fn, *, label: str, attempts: int = 4, base_delay: float = 1.0):
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if isinstance(exc, MonthlyIntegrityError):
                raise
            if attempt < attempts - 1 and _is_transient(exc):
                # Compatibility-only synchronous callers.  Worker operations
                # use call_with_backoff(), which yields with asyncio.sleep.
                threading.Event().wait(base_delay * (2**attempt))
                continue
            raise MonthlyIntegrityError(_google_error_code(exc), f"{label} failed") from exc
    assert last is not None
    raise last


async def _google_request(
    adapter: GoogleSyncAdapter,
    operation: str,
    request: dict[str, Any],
    *,
    label: str,
    destructive: bool = False,
) -> Any:
    try:
        deadline = asyncio.get_running_loop().time() + GOOGLE_OPERATION_DEADLINE_SECONDS
        return await call_with_backoff(
            adapter,
            operation,
            request,
            label=label,
            attempts=GOOGLE_API_RETRY_ATTEMPTS,
            base_delay=GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
            destructive=destructive,
            deadline=deadline,
        )
    except MonthlyIntegrityError:
        raise
    except Exception as exc:  # noqa: BLE001 - provider boundary is classified here
        raise MonthlyIntegrityError(_google_error_code(exc), f"{label} failed") from exc


def _company_from_values(registry_key: str | None, fallback: str | None) -> str:
    raw = (registry_key or "").split("/", 1)[0].strip() or (fallback or "").strip()
    normalized = raw.casefold()
    if normalized == "mobicell":
        return "Mobicell"
    if normalized == "mobiup":
        return "Mobiup"
    raise MonthlyIntegrityError(
        "unknown_company",
        "Grile registry company is missing or unsupported",
    )


def _store_from_values(registry_key: str | None, fallback: str | None) -> str:
    if registry_key and "/" in registry_key:
        return registry_key.split("/", 1)[1].strip()
    return (fallback or "").strip()


async def load_entries(
    pool: asyncpg.Pool,
    only: str | None = None,
    *,
    month: str | None = None,
) -> list[StoreEntry]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                gs.site_code,
                gs.sheet_id,
                gs.registry_key,
                s.locatie,
                s.firma,
                s.asm,
                gs.template_version
            FROM grile_sheets gs
            JOIN stores s ON s.site_code = gs.site_code
            WHERE gs.is_active = true
              AND s.is_active = true
              AND ($1::TEXT IS NULL OR gs.active_from_month IS NULL OR gs.active_from_month <= $1)
            ORDER BY COALESCE(gs.registry_key, s.firma || '/' || s.locatie)
            """,
            month,
        )

    entries = [
        StoreEntry(
            company=_company_from_values(r["registry_key"], r["firma"]),
            store=_store_from_values(r["registry_key"], r["locatie"]),
            sheet_id=r["sheet_id"],
            site_code=r["site_code"],
            manager=(r["asm"] or "Neatribuit").strip() or "Neatribuit",
            is_closed=str(r["locatie"] or "").strip().upper().startswith("INCHIS "),
            template_version=r.get("template_version") or "v2",
        )
        for r in rows
    ]
    if only:
        needle = only.casefold()
        entries = [
            e for e in entries
            if needle in f"{e.company}/{e.store}/{e.site_code}/{e.manager}".casefold()
        ]
    if not entries:
        raise RuntimeError("No active grile matched the requested filter.")
    return entries


def _operation_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    return persisted_operation_to_dict(row)


def _safe_operation_result(operation: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return an independent copy of a persisted JSON result for replays."""
    return safe_persisted_result(operation)


async def reserve_monthly_operation(
    pool: asyncpg.Pool,
    *,
    op: str,
    month: str,
    only: str | None,
    dry_run: bool,
    requested_by_sub: str,
    approved_manifest_id: int | None = None,
) -> MonthlyOperationReservation:
    if op not in VALID_OPS:
        raise ValueError(f"Operatie necunoscuta: {op}")
    return await persist_monthly_operation_reservation(
        pool,
        op=op,
        month=month,
        only=only,
        dry_run=dry_run,
        requested_by_sub=requested_by_sub,
        approved_manifest_id=approved_manifest_id,
    )


async def attach_monthly_operation_job(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    job_id: str,
) -> bool:
    return await persist_monthly_operation_job(
        pool,
        operation_id=operation_id,
        job_id=job_id,
    )


async def start_monthly_operation(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    execution_owner: str | None = None,
) -> MonthlyOperationStartResult:
    return await persist_monthly_operation_start(
        pool,
        operation_id,
        execution_owner=execution_owner,
    )


async def heartbeat_monthly_operation(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    execution_owner: str,
    execution_epoch: int,
) -> bool:
    return await persist_monthly_operation_heartbeat(
        pool,
        operation_id,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
    )


async def _run_with_monthly_lease(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    execution_owner: str,
    execution_epoch: int,
    operation: Coroutine[Any, Any, MonthlyExecution],
    heartbeat_interval: float = MONTHLY_OPERATION_HEARTBEAT_SECONDS,
) -> MonthlyExecution:
    """Keep the DB lease alive and abort work immediately when its fence is lost."""

    async def monitor() -> None:
        while True:
            await asyncio.sleep(heartbeat_interval)
            alive = await heartbeat_monthly_operation(
                pool,
                operation_id,
                execution_owner=execution_owner,
                execution_epoch=execution_epoch,
            )
            if not alive:
                raise MonthlyIntegrityError(
                    "operation_lease_lost",
                    "Monthly operation lease was lost",
                )

    operation_task: asyncio.Task[MonthlyExecution] = asyncio.create_task(operation)
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


async def finish_monthly_operation(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    result: dict[str, Any],
    error_message: str | None = None,
    execution_owner: str,
    execution_epoch: int,
) -> bool:
    return await persist_monthly_operation_result(
        pool,
        operation_id,
        result=result,
        error_message=error_message,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
    )


async def fail_monthly_operation(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    error_message: str,
    execution_owner: str,
    execution_epoch: int,
) -> bool:
    return await persist_monthly_operation_failure(
        pool,
        operation_id,
        error_message=error_message,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
    )


async def fail_queued_monthly_operation(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    error_message: str,
) -> bool:
    return await persist_queued_monthly_operation_failure(
        pool,
        operation_id,
        error_message=error_message,
    )


async def get_monthly_execution_lease(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    execution_owner: str,
) -> MonthlyExecutionLease | None:
    return await fetch_monthly_execution_lease(
        pool,
        operation_id,
        execution_owner=execution_owner,
    )


async def mark_monthly_operation_cancelled_uncertain(
    pool: asyncpg.Pool,
    operation_id: int,
    *,
    error_message: str,
    execution_owner: str,
    execution_epoch: int,
) -> bool:
    return await persist_cancelled_uncertain(
        pool,
        operation_id,
        error_message=error_message,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
    )


async def get_monthly_manifest(
    pool: asyncpg.Pool,
    manifest_id: int,
) -> dict[str, Any] | None:
    return await fetch_monthly_manifest(pool, manifest_id)


async def get_latest_monthly_manifest(
    pool: asyncpg.Pool,
    *,
    month: str,
) -> dict[str, Any] | None:
    return await fetch_latest_monthly_manifest(
        pool,
        closing_month=month,
        operation="archive",
        statuses=MANIFEST_ATTEMPT_STATUSES,
    )


async def ensure_reset_items(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    closing_month_key: str,
    next_month_key: str,
    entries: list[StoreEntry],
    execution_owner: str,
    execution_epoch: int,
) -> None:
    await persist_reset_items(
        pool,
        operation_id=operation_id,
        closing_month=closing_month_key,
        next_month=next_month_key,
        entries=[
            ResetItemInput(
                site_code=entry.site_code,
                sheet_id=entry.sheet_id,
                company=entry.company,
                store=entry.store,
                ranges=tuple(reset_ranges_for_entry(entry)),
            )
            for entry in entries
        ],
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
    )


async def get_previous_completed_reset_item(
    pool: asyncpg.Pool,
    *,
    closing_month_key: str,
    site_code: str,
) -> asyncpg.Record | None:
    return await fetch_previous_completed_reset_item(
        pool,
        closing_month=closing_month_key,
        site_code=site_code,
    )


async def mark_reset_item_running(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    execution_owner: str,
    execution_epoch: int,
) -> bool:
    return await persist_reset_item_claim(
        pool,
        operation_id=operation_id,
        site_code=site_code,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
    )


async def finish_reset_item(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    status: Literal["completed", "error", "skipped"],
    execution_owner: str,
    execution_epoch: int,
    error_message: str | None = None,
) -> bool:
    return await persist_reset_item_result(
        pool,
        operation_id=operation_id,
        site_code=site_code,
        status=status,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
        error_message=error_message,
    )


async def record_reset_item_backup(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    backup_path: str,
    backup_sha256: str,
    execution_owner: str,
    execution_epoch: int,
) -> bool:
    return await persist_reset_item_backup(
        pool,
        operation_id=operation_id,
        site_code=site_code,
        backup_path=backup_path,
        backup_sha256=backup_sha256,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
    )


async def record_reset_item_rollback(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    site_code: str,
    restored: bool,
    execution_owner: str,
    execution_epoch: int,
    error_message: str | None = None,
) -> bool:
    return await persist_reset_item_rollback(
        pool,
        operation_id=operation_id,
        site_code=site_code,
        restored=restored,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
        error_message=error_message,
    )


def extract_store_rows(
    sheets_svc: Any,
    entry: StoreEntry,
    *,
    value_ranges: list[dict[str, Any]] | None = None,
) -> list[ExtractedAgentRow]:
    try:
        ranges = value_ranges_for_entry(entry)
        parsed_ranges = (
            value_ranges
            if value_ranges is not None
            else _read_store_value_ranges(sheets_svc, entry, ranges)
        )
        if len(parsed_ranges) != len(ranges):
            raise MonthlyIntegrityError(
                "google_response_incomplete",
                "Google sheet response is incomplete",
            )
        return parse_store_rows(entry, parsed_ranges)
    except Exception as exc:  # noqa: BLE001
        code = exc.code if isinstance(exc, MonthlyIntegrityError) else _google_error_code(exc)
        return [_error_row(entry, slot=0, code=code)]


def _read_store_value_ranges(
    sheets_service: Any,
    entry: StoreEntry,
    ranges: list[str],
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
            "google_response_incomplete",
            "Google sheet response is incomplete",
        )
    return parsed


def build_workbook(
    rows: list[ExtractedAgentRow],
    output_path: Path,
    metadata_by_company_store: dict[tuple[str, str], dict[str, Any]],
) -> None:
    monthly_artifacts.build_workbook(
        rows,
        output_path,
        metadata_by_company_store,
        style=style_sheet,
    )


def _validate_final_workbook(path: Path, *, expected_agents: int) -> None:
    monthly_artifacts.validate_final_workbook(path, expected_agents=expected_agents)


def _staging_dir(operation: str, operation_id: int | None) -> Path:
    return monthly_artifacts.staging_dir(OUTPUTS_DIR, operation, operation_id)


def _promote_file(staged: Path, destination: Path) -> None:
    monthly_artifacts.promote_file(OUTPUTS_DIR, staged, destination)


async def _finalize_month_execution(
    pool: asyncpg.Pool,
    month: str,
    *,
    month_key: str,
    requested_by_sub: str,
    operation_id: int | None,
    only: str | None = None,
    delay: float = 1.1,
    google_adapter: GoogleSyncAdapter | None = None,
) -> MonthlyExecution:
    return await execute_finalization(
        pool,
        FinalizationRequest(
            month=month,
            month_key=month_key,
            requested_by_sub=requested_by_sub,
            operation_id=operation_id,
            only=only,
            delay=delay,
            google_adapter=google_adapter,
        ),
        FinalizationPorts(
            outputs_dir=OUTPUTS_DIR,
            load_entries=load_entries,
            build_google_services=build_google_services,
            extract_store_rows=extract_store_rows,
            google_request=_google_request,
            validate_coverage=_validate_finalization_coverage,
            control_totals=_control_totals,
            staging_dir=_staging_dir,
            build_workbook=build_workbook,
            secure_file=secure_file,
            validate_workbook=_validate_final_workbook,
            promote_file=_promote_file,
            with_source_registry=_with_source_registry,
            sleep=asyncio.sleep,
        ),
    )


async def finalize_month(
    pool: asyncpg.Pool,
    month: str,
    only: str | None = None,
    delay: float = 1.1,
    *,
    month_key: str | None = None,
    requested_by_sub: str = "direct-execution",
    operation_id: int | None = None,
    google_adapter: GoogleSyncAdapter | None = None,
) -> Path:
    execution = await _finalize_month_execution(
        pool,
        month,
        month_key=month_key or month,
        requested_by_sub=requested_by_sub,
        operation_id=operation_id,
        only=only,
        delay=delay,
        google_adapter=google_adapter,
    )
    return execution.path


def export_sheet_xlsx(drive_service: Any, entry: StoreEntry, output_path: Path) -> dict[str, Any]:
    return monthly_archive_artifacts.export_sheet_xlsx(
        drive_service,
        entry,
        output_path,
        downloader_type=MediaIoBaseDownload,
        secure_directory=secure_directory,
        secure_file=secure_file,
    )


def write_exported_xlsx(entry: StoreEntry, output_path: Path, content: bytes) -> dict[str, Any]:
    return monthly_archive_artifacts.write_exported_xlsx(
        entry,
        output_path,
        content,
        secure_directory=secure_directory,
        secure_file=secure_file,
    )


def create_archive_zip(zip_path: Path, exported_files: list[Path], archive_dir: Path) -> None:
    monthly_archive_artifacts.create_archive_zip(
        zip_path,
        exported_files,
        archive_dir,
        secure_directory=secure_directory,
    )


def create_manager_zips(output_dir: Path, month: str, results: list[dict[str, Any]]) -> dict[str, Path]:
    return monthly_archive_artifacts.create_manager_zips(
        output_dir,
        month,
        results,
        build_archive_dir=build_archive_dir,
        build_manager_zip_path=build_manager_zip_path,
        create_zip=create_archive_zip,
    )


def summarize_archive_results(
    month: str,
    registry_count: int,
    results: list[dict[str, Any]],
    zip_path: Path,
    manager_zip_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    return monthly_archive_artifacts.summarize_archive_results(
        month,
        registry_count,
        results,
        zip_path,
        manager_zip_paths,
        now=utc_now,
    )


def _validate_archive_zip(zip_path: Path, *, expected_files: int) -> None:
    monthly_archive_artifacts.validate_archive_zip(
        zip_path,
        expected_files=expected_files,
    )


def _validate_source_workbook(path: Path) -> None:
    monthly_archive_artifacts.validate_source_workbook(path)


def _future_artifact(
    staged_path: Path,
    *,
    staged_archive_dir: Path,
    official_archive_dir: Path,
    kind: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return monthly_archive_artifacts.future_artifact(
        staged_path,
        outputs_dir=OUTPUTS_DIR,
        staged_archive_dir=staged_archive_dir,
        official_archive_dir=official_archive_dir,
        kind=kind,
        extra=extra,
    )


def _promote_directory(
    staged: Path,
    destination: Path,
    *,
    verify: Callable[[], None] | None = None,
) -> None:
    monthly_archive_artifacts.promote_directory(
        staged,
        destination,
        outputs_dir=OUTPUTS_DIR,
        safe_filename=safe_filename,
        secure_directory=secure_directory,
        verify=verify,
    )


async def _archive_month_execution(
    pool: asyncpg.Pool,
    month: str,
    *,
    month_key: str,
    requested_by_sub: str,
    operation_id: int | None,
    only: str | None = None,
    delay: float = 0.5,
    google_adapter: GoogleSyncAdapter | None = None,
) -> MonthlyExecution:
    return await execute_archive(
        pool,
        ArchiveRequest(
            month=month,
            month_key=month_key,
            requested_by_sub=requested_by_sub,
            operation_id=operation_id,
            only=only,
            delay=delay,
            google_adapter=google_adapter,
        ),
        ArchivePorts(
            outputs_dir=OUTPUTS_DIR,
            manifest_statuses=MANIFEST_ATTEMPT_STATUSES,
            fetch_latest_manifest=fetch_latest_monthly_manifest,
            load_entries=load_entries,
            source_registry=_source_registry,
            validate_manifest=validate_verified_manifest,
            verify_artifacts=verify_artifacts,
            build_google_services=build_google_services,
            staging_dir=_staging_dir,
            build_archive_dir=build_archive_dir,
            build_store_export_path=build_store_export_path,
            build_archive_zip_path=build_archive_zip_path,
            build_archive_manifest_path=build_archive_manifest_path,
            retry_api=retry_api,
            retry_attempts=GOOGLE_API_RETRY_ATTEMPTS,
            retry_base_delay=GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
            export_sheet_xlsx=export_sheet_xlsx,
            google_request=_google_request,
            write_exported_xlsx=write_exported_xlsx,
            validate_source_workbook=_validate_source_workbook,
            create_archive_zip=create_archive_zip,
            create_manager_zips=create_manager_zips,
            secure_file=secure_file,
            validate_archive_zip=_validate_archive_zip,
            future_artifact=_future_artifact,
            secure_write_json=secure_write_json,
            promote_directory=_promote_directory,
            sleep=asyncio.sleep,
        ),
    )


async def archive_month(
    pool: asyncpg.Pool,
    month: str,
    only: str | None = None,
    delay: float = 0.5,
    *,
    month_key: str | None = None,
    requested_by_sub: str = "direct-execution",
    operation_id: int | None = None,
    google_adapter: GoogleSyncAdapter | None = None,
) -> Path:
    execution = await _archive_month_execution(
        pool,
        month,
        month_key=month_key or month,
        requested_by_sub=requested_by_sub,
        operation_id=operation_id,
        only=only,
        delay=delay,
        google_adapter=google_adapter,
    )
    return execution.path


def public_manifest_payload(record: dict[str, Any]) -> dict[str, Any]:
    raw_manifest = record.get("manifest")
    manifest: dict[str, Any] = raw_manifest if isinstance(raw_manifest, dict) else {}
    return {
        "id": record.get("id"),
        "operation_id": record.get("operation_id"),
        "month": record.get("closing_month"),
        "operation": record.get("operation"),
        "status": record.get("status"),
        "expected": manifest.get("expected", {}),
        "processed": manifest.get("processed", {}),
        "error_count": record.get("error_count", 0),
        "manifest_sha256": record.get("manifest_sha256"),
        "approved": bool(record.get("approved_by_sub")),
        "created_at": _public_timestamp(record.get("created_at")),
        "verified_at": _public_timestamp(record.get("verified_at")),
        "approved_at": _public_timestamp(record.get("approved_at")),
        "consumed_at": _public_timestamp(record.get("consumed_at")),
    }


def _public_timestamp(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


async def approve_monthly_manifest(
    pool: asyncpg.Pool,
    *,
    manifest_id: int,
    approved_by_sub: str,
) -> dict[str, Any]:
    record = await fetch_monthly_manifest(pool, manifest_id)
    if record is None:
        raise FileNotFoundError("Manifestul nu exista.")
    manifest = record.get("manifest")
    if record.get("operation") != "archive" or record.get("status") != "verified":
        raise MonthlyIntegrityError("manifest_not_approvable", "Manifest is not approvable")
    if not isinstance(manifest, dict):
        raise MonthlyIntegrityError("manifest_invalid", "Manifest is invalid")
    validate_verified_manifest(manifest, operation="archive")
    verify_artifacts(manifest, root=OUTPUTS_DIR)
    current_sha = manifest.get("manifest_sha256")
    if not isinstance(current_sha, str):
        raise MonthlyIntegrityError("manifest_hash_invalid", "Manifest hash is invalid")
    approved_manifest = dict(manifest)
    approved_manifest["status"] = "approved"
    approved_manifest["approved_by_sub"] = approved_by_sub
    approved_manifest["approved_at"] = utc_now()
    approved_manifest = finalize_manifest(approved_manifest)
    approved = await persist_monthly_manifest_approval(
        pool,
        manifest_id=manifest_id,
        expected_sha256=current_sha,
        approved_by_sub=approved_by_sub,
        approved_manifest=approved_manifest,
    )
    if approved is None:
        current = await fetch_monthly_manifest(pool, manifest_id)
        if current is not None and current.get("status") in {"approved", "consumed"}:
            return public_manifest_payload(current)
        raise MonthlyIntegrityError("manifest_approval_race", "Manifest approval changed concurrently")
    return public_manifest_payload(approved)


def _read_reset_snapshot(sheets_svc: Any, entry: StoreEntry) -> dict[str, Any]:
    return reset_google.read_snapshot(
        sheets_svc,
        entry,
        retry_api=retry_api,
        attempts=GOOGLE_API_RETRY_ATTEMPTS,
        base_delay=GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
    )


async def _read_reset_snapshot_async(
    google_adapter: GoogleSyncAdapter,
    entry: StoreEntry,
) -> dict[str, Any]:
    return await reset_google.read_snapshot_async(
        google_adapter,
        entry,
        google_request=_google_request,
    )


def _restore_reset_snapshot(
    sheets_svc: Any,
    entry: StoreEntry,
    snapshot: dict[str, Any],
) -> None:
    reset_google.restore_snapshot(
        sheets_svc,
        entry,
        snapshot,
        retry_api=retry_api,
        attempts=GOOGLE_API_RETRY_ATTEMPTS,
        base_delay=GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
        read_snapshot=_read_reset_snapshot,
    )


async def _restore_reset_snapshot_async(
    google_adapter: GoogleSyncAdapter,
    entry: StoreEntry,
    snapshot: dict[str, Any],
) -> None:
    await reset_google.restore_snapshot_async(
        google_adapter,
        entry,
        snapshot,
        google_request=_google_request,
        read_snapshot=_read_reset_snapshot_async,
    )


def _verify_reset_cleared(sheets_svc: Any, entry: StoreEntry) -> None:
    reset_google.verify_cleared(_read_reset_snapshot(sheets_svc, entry))


async def _verify_reset_cleared_async(
    google_adapter: GoogleSyncAdapter,
    entry: StoreEntry,
) -> None:
    reset_google.verify_cleared(
        await _read_reset_snapshot_async(google_adapter, entry)
    )


def reset_store(
    sheets_svc: Any | None,
    entry: StoreEntry,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    return reset_google.reset_store(
        sheets_svc,
        entry,
        dry_run=dry_run,
        retry_api=retry_api,
        attempts=GOOGLE_API_RETRY_ATTEMPTS,
        base_delay=GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
        error_code=_google_error_code,
    )


async def _rollback_reset_entries(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    entries: list[StoreEntry],
    sheets_svc: Any,
    snapshots: dict[str, dict[str, Any]],
    execution_owner: str,
    execution_epoch: int,
) -> bool:
    return await reset_rollback.rollback_entries(
        pool,
        operation_id=operation_id,
        entries=entries,
        sheets_service=sheets_svc,
        snapshots=snapshots,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
        restore_snapshot=_restore_reset_snapshot,
        record_rollback=record_reset_item_rollback,
    )


async def _rollback_reset_entries_cancel_safe(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    entries: list[StoreEntry],
    sheets_svc: Any,
    snapshots: dict[str, dict[str, Any]],
    execution_owner: str,
    execution_epoch: int,
) -> bool:
    return await reset_rollback.cancel_safe(
        lambda: _rollback_reset_entries(
            pool,
            operation_id=operation_id,
            entries=entries,
            sheets_svc=sheets_svc,
            snapshots=snapshots,
            execution_owner=execution_owner,
            execution_epoch=execution_epoch,
        )
    )


async def _rollback_reset_entries_adapter(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    entries: list[StoreEntry],
    google_adapter: GoogleSyncAdapter,
    snapshots: dict[str, dict[str, Any]],
    execution_owner: str,
    execution_epoch: int,
) -> bool:
    return await reset_rollback.rollback_adapter_entries(
        pool,
        operation_id=operation_id,
        entries=entries,
        google_adapter=google_adapter,
        snapshots=snapshots,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
        prepare_rollback=persist_reset_rollback_intent,
        restore_snapshot=_restore_reset_snapshot_async,
        confirm_rollback=persist_reset_rollback_confirmation,
    )


async def _rollback_reset_entries_adapter_cancel_safe(
    pool: asyncpg.Pool,
    *,
    operation_id: int,
    entries: list[StoreEntry],
    google_adapter: GoogleSyncAdapter,
    snapshots: dict[str, dict[str, Any]],
    execution_owner: str,
    execution_epoch: int,
) -> bool:
    return await reset_rollback.cancel_safe(
        lambda: _rollback_reset_entries_adapter(
            pool,
            operation_id=operation_id,
            entries=entries,
            google_adapter=google_adapter,
            snapshots=snapshots,
            execution_owner=execution_owner,
            execution_epoch=execution_epoch,
        )
    )


async def _reset_month_execution(
    pool: asyncpg.Pool,
    closing_month: str,
    next_month: str,
    *,
    closing_month_key: str,
    next_month_key: str,
    requested_by_sub: str,
    operation_id: int | None,
    approved_manifest_id: int | None,
    only: str | None = None,
    dry_run: bool = True,
    google_adapter: GoogleSyncAdapter | None = None,
    execution_owner: str | None = None,
    execution_epoch: int | None = None,
) -> MonthlyExecution:
    context = ResetRunContext(
        pool=pool,
        closing_month=closing_month,
        next_month=next_month,
        closing_month_key=closing_month_key,
        next_month_key=next_month_key,
        requested_by_sub=requested_by_sub,
        operation_id=operation_id,
        approved_manifest_id=approved_manifest_id,
        only=only,
        dry_run=dry_run,
        google_adapter=google_adapter,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
    )
    return await execute_reset(
        context,
        ResetPorts(
            outputs_dir=OUTPUTS_DIR,
            manifest_statuses=MANIFEST_ATTEMPT_STATUSES,
            fetch_latest_manifest=fetch_latest_monthly_manifest,
            fetch_manifest=fetch_monthly_manifest,
            validate_manifest=validate_verified_manifest,
            verify_artifacts=verify_artifacts,
            load_entries=load_entries,
            build_google_services=build_google_services,
            ensure_reset_items=ensure_reset_items,
            read_snapshot=_read_reset_snapshot,
            read_snapshot_async=_read_reset_snapshot_async,
            build_backup_dir=build_reset_backup_dir,
            secure_write_json=secure_write_json,
            record_backup=record_reset_item_backup,
            heartbeat=heartbeat_monthly_operation,
            mark_running=mark_reset_item_running,
            reset_store=reset_store,
            verify_cleared=_verify_reset_cleared,
            finish_item=finish_reset_item,
            prepare_clear=persist_reset_clear_intent,
            google_request=_google_request,
            reset_ranges=reset_ranges_for_entry,
            verify_cleared_async=_verify_reset_cleared_async,
            confirm_clear=persist_reset_clear_confirmation,
            rollback_sync=_rollback_reset_entries_cancel_safe,
            rollback_adapter=_rollback_reset_entries_adapter_cancel_safe,
            build_dry_report_path=build_reset_dry_run_report_path,
            build_report_path=build_reset_report_path,
            staging_dir=_staging_dir,
            promote_file=_promote_file,
        ),
    )


async def reset_month(
    pool: asyncpg.Pool,
    closing_month: str,
    next_month: str,
    only: str | None = None,
    dry_run: bool = True,
    operation_id: int | None = None,
    closing_month_key: str | None = None,
    next_month_key: str | None = None,
    requested_by_sub: str = "direct-execution",
    approved_manifest_id: int | None = None,
    google_adapter: GoogleSyncAdapter | None = None,
    execution_owner: str | None = None,
    execution_epoch: int | None = None,
) -> Path:
    execution = await _reset_month_execution(
        pool,
        closing_month,
        next_month,
        closing_month_key=closing_month_key or closing_month,
        next_month_key=next_month_key or next_month,
        requested_by_sub=requested_by_sub,
        operation_id=operation_id,
        approved_manifest_id=approved_manifest_id,
        only=only,
        dry_run=dry_run,
        google_adapter=google_adapter,
        execution_owner=execution_owner,
        execution_epoch=execution_epoch,
    )
    return execution.path


def _reconciliation_entry(item: dict[str, Any]) -> StoreEntry:
    return StoreEntry(
        str(item.get("company") or ""),
        str(item.get("store") or ""),
        str(item.get("sheet_id") or ""),
        str(item.get("site_code") or ""),
        "Neatribuit",
    )


def _read_reset_backup(item: dict[str, Any]) -> dict[str, Any]:
    raw_path = Path(str(item.get("backup_path") or ""))
    path = raw_path if raw_path.is_absolute() else OUTPUTS_DIR / raw_path
    if not path.exists() or file_sha256(path) != item.get("backup_sha256"):
        raise MonthlyIntegrityError("backup_invalid", "Reset backup cannot be verified")
    payload = json.loads(path.read_text(encoding="utf-8"))
    snapshot = payload.get("snapshot") if isinstance(payload, dict) else None
    if not isinstance(snapshot, dict):
        raise MonthlyIntegrityError("backup_invalid", "Reset backup snapshot is invalid")
    if payload.get("snapshot_sha256") != snapshot_sha256(snapshot):
        raise MonthlyIntegrityError("backup_invalid", "Reset backup hash is invalid")
    return snapshot


def _snapshot_is_cleared(snapshot: dict[str, Any]) -> bool:
    return not any(
        item.get("values")
        for item in snapshot.get("value_ranges", [])
        if isinstance(item, dict)
    )


async def reconcile_monthly_operations(
    pool: asyncpg.Pool,
    google_adapter: GoogleSyncAdapter,
) -> int:
    """Recover stale monthly work without replaying a reset automatically."""
    owner = f"reconciler-{uuid4().hex}"
    candidates = await claim_reconciliation_candidates(
        pool,
        execution_owner=owner,
    )
    reconciled = 0
    for operation in candidates:
        operation_id = int(operation["id"])
        epoch = int(operation.get("execution_epoch", 0))
        items = await list_reset_items_for_reconciliation(pool, operation_id)
        classifications: list[Literal["safe_retry", "rolled_back", "recovery_required"]] = []
        for item in items:
            site_code = str(item["site_code"])
            phase = str(item.get("checkpoint_phase") or "legacy_unknown")
            if phase == "legacy_unknown":
                await mark_item_recovery_required(
                    pool,
                    operation_id=operation_id,
                    site_code=site_code,
                    execution_owner=owner,
                    execution_epoch=epoch,
                    error_message="legacy_unknown_recovery_required",
                )
                classifications.append("recovery_required")
                continue

            try:
                snapshot = _read_reset_backup(item)
                current = await _read_reset_snapshot_async(
                    google_adapter,
                    _reconciliation_entry(item),
                )
                if snapshot_sha256(current) == snapshot_sha256(snapshot):
                    if phase == "snapshot_persisted":
                        safe = await mark_item_safe_retry(
                            pool,
                            operation_id=operation_id,
                            site_code=site_code,
                            execution_owner=owner,
                            execution_epoch=epoch,
                        )
                        classifications.append("safe_retry" if safe else "recovery_required")
                    else:
                        intent = await persist_reset_rollback_intent(
                            pool,
                            operation_id=operation_id,
                            site_code=site_code,
                            execution_owner=owner,
                            execution_epoch=epoch,
                        )
                        restored = bool(intent) and await persist_reset_rollback_confirmation(
                            pool,
                            operation_id=operation_id,
                            site_code=site_code,
                            execution_owner=owner,
                            execution_epoch=epoch,
                            fence_epoch=int(intent["fence_epoch"]) if intent else -1,
                            restored=True,
                            error_message="rollback_verified_readback",
                        )
                        classifications.append("rolled_back" if restored else "recovery_required")
                elif _snapshot_is_cleared(current):
                    intent = await persist_reset_rollback_intent(
                        pool,
                        operation_id=operation_id,
                        site_code=site_code,
                        execution_owner=owner,
                        execution_epoch=epoch,
                    )
                    if intent is None:
                        classifications.append("recovery_required")
                        continue
                    restored = False
                    try:
                        await _restore_reset_snapshot_async(
                            google_adapter,
                            _reconciliation_entry(item),
                            snapshot,
                        )
                        restored = True
                    except BaseException:  # noqa: BLE001 - recovery is fail-closed
                        restored = False
                    confirmed = await persist_reset_rollback_confirmation(
                        pool,
                        operation_id=operation_id,
                        site_code=site_code,
                        execution_owner=owner,
                        execution_epoch=epoch,
                        fence_epoch=int(intent["fence_epoch"]),
                        restored=restored,
                        error_message="rollback_verified" if restored else "recovery_required",
                    )
                    classifications.append("rolled_back" if restored and confirmed else "recovery_required")
                else:
                    classifications.append("recovery_required")
            except asyncio.CancelledError:
                raise
            except BaseException:  # noqa: BLE001 - read/hash failures block retry
                classifications.append("recovery_required")

            if classifications[-1] == "recovery_required":
                await mark_item_recovery_required(
                    pool,
                    operation_id=operation_id,
                    site_code=site_code,
                    execution_owner=owner,
                    execution_epoch=epoch,
                    error_message="recovery_required",
                )

        classification: Literal["safe_retry", "rolled_back", "recovery_required"]
        if "recovery_required" in classifications:
            classification = "recovery_required"
        elif "rolled_back" in classifications:
            classification = "rolled_back"
        else:
            classification = "safe_retry"
        await mark_reconciliation_result(
            pool,
            operation_id=operation_id,
            execution_owner=owner,
            execution_epoch=epoch,
            classification=classification,
            error_message=classification,
            alert=classification == "recovery_required",
        )
        reconciled += 1
    return reconciled


async def _monthly_operation_pool() -> Any:
    from db.connection import get_pool

    return await get_pool()


def _monthly_run_ports() -> Any:
    from services.grile_monthly_orchestration import MonthlyRunPorts

    return MonthlyRunPorts(
        valid_ops=frozenset(VALID_OPS),
        owner_hex=lambda: uuid4().hex,
        get_pool=_monthly_operation_pool,
        start_operation=start_monthly_operation,
        heartbeat_operation=heartbeat_monthly_operation,
        finish_operation=finish_monthly_operation,
        run_with_lease=_run_with_monthly_lease,
        persist_manifest=persist_manifest_result,
        persist_reset_success=persist_reset_success,
        fetch_manifest=fetch_monthly_manifest,
        finalize_execution=_finalize_month_execution,
        archive_execution=_archive_month_execution,
        reset_execution=_reset_month_execution,
        base_manifest=base_manifest,
        public_manifest_payload=public_manifest_payload,
        finalize_manifest=finalize_manifest,
        ro_month_label=ro_month_label,
        next_month=next_ym,
        utc_now=utc_now,
        manifest_error_type=MonthlyManifestError,
        integrity_error_type=MonthlyIntegrityError,
    )


async def run_monthly_op(
    *,
    op: str | None = None,
    month: str | None = None,
    only: str | None = None,
    dry_run: bool = True,
    operation_id: int | None = None,
    google_adapter: GoogleSyncAdapter | None = None,
    execution_owner_hint: str | None = None,
) -> dict[str, Any]:
    from services.grile_monthly_orchestration import orchestrate_monthly_operation

    return await orchestrate_monthly_operation(
        _monthly_run_ports(),
        op=op,
        month=month,
        only=only,
        dry_run=dry_run,
        operation_id=operation_id,
        google_adapter=google_adapter,
        execution_owner_hint=execution_owner_hint,
    )


async def fetch_download(kind: str, month: str) -> tuple[bytes, str, str]:
    if kind not in VALID_DOWNLOADS:
        raise ValueError(f"Tip download necunoscut: {kind}")
    month_label = ro_month_label(month)
    if kind == "final":
        path = build_final_export_path(OUTPUTS_DIR, month_label)
        filename = f"Tabel Salarii - {month_label}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        path = build_archive_zip_path(OUTPUTS_DIR, month_label)
        filename = f"Arhiva Grile - {month_label}.zip"
        media_type = "application/zip"

    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(f"Fisierul {kind} pentru {month_label} nu exista inca.")
    return await asyncio.to_thread(path.read_bytes), filename, media_type
