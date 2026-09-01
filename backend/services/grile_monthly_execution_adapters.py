"""Dependency adapters for the public monthly Grile compatibility facade.

The facade remains the monkeypatch boundary used by workers and characterization
tests.  These builders read its dependencies at call time and pass explicit
ports to the focused orchestration modules.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from services.grile_monthly_archive import ArchivePorts, ArchiveRequest, execute_archive
from services.grile_monthly_finalization import (
    FinalizationPorts,
    FinalizationRequest,
    execute_finalization,
)
from services.grile_monthly_orchestration import (
    MonthlyRunPorts,
    orchestrate_monthly_operation,
)
from services.grile_monthly_reconciler import ReconciliationPorts, reconcile_operations
from services.grile_monthly_reset_contracts import ResetPorts, ResetRunContext
from services.grile_monthly_reset_execution import execute_reset


async def finalize_execution(
    api: Any,
    pool: Any,
    month: str,
    *,
    month_key: str,
    requested_by_sub: str,
    operation_id: int | None,
    only: str | None = None,
    delay: float = 1.1,
    google_adapter: Any | None = None,
) -> Any:
    request = FinalizationRequest(
        month=month,
        month_key=month_key,
        requested_by_sub=requested_by_sub,
        operation_id=operation_id,
        only=only,
        delay=delay,
        google_adapter=google_adapter,
    )
    ports = FinalizationPorts(
        outputs_dir=api.OUTPUTS_DIR,
        load_entries=api.load_entries,
        build_google_services=api.build_google_services,
        extract_store_rows=api.extract_store_rows,
        google_request=api._google_request,
        validate_coverage=api._validate_finalization_coverage,
        control_totals=api._control_totals,
        staging_dir=api._staging_dir,
        build_workbook=api.build_workbook,
        secure_file=api.secure_file,
        validate_workbook=api._validate_final_workbook,
        promote_file=api._promote_file,
        with_source_registry=api._with_source_registry,
        sleep=api.asyncio.sleep,
    )
    return await execute_finalization(pool, request, ports)


async def finalize_month(
    api: Any,
    pool: Any,
    month: str,
    only: str | None = None,
    delay: float = 1.1,
    *,
    month_key: str | None = None,
    requested_by_sub: str = "direct-execution",
    operation_id: int | None = None,
    google_adapter: Any | None = None,
) -> Path:
    execution = await api._finalize_month_execution(
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


async def archive_execution(
    api: Any,
    pool: Any,
    month: str,
    *,
    month_key: str,
    requested_by_sub: str,
    operation_id: int | None,
    only: str | None = None,
    delay: float = 0.5,
    google_adapter: Any | None = None,
) -> Any:
    request = ArchiveRequest(
        month=month,
        month_key=month_key,
        requested_by_sub=requested_by_sub,
        operation_id=operation_id,
        only=only,
        delay=delay,
        google_adapter=google_adapter,
    )
    ports = ArchivePorts(
        outputs_dir=api.OUTPUTS_DIR,
        manifest_statuses=api.MANIFEST_ATTEMPT_STATUSES,
        fetch_latest_manifest=api.fetch_latest_monthly_manifest,
        load_entries=api.load_entries,
        source_registry=api._source_registry,
        validate_manifest=api.validate_verified_manifest,
        verify_artifacts=api.verify_artifacts,
        build_google_services=api.build_google_services,
        staging_dir=api._staging_dir,
        build_archive_dir=api.build_archive_dir,
        build_store_export_path=api.build_store_export_path,
        build_archive_zip_path=api.build_archive_zip_path,
        build_archive_manifest_path=api.build_archive_manifest_path,
        retry_api=api.retry_api,
        retry_attempts=api.GOOGLE_API_RETRY_ATTEMPTS,
        retry_base_delay=api.GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
        export_sheet_xlsx=api.export_sheet_xlsx,
        google_request=api._google_request,
        write_exported_xlsx=api.write_exported_xlsx,
        validate_source_workbook=api._validate_source_workbook,
        create_archive_zip=api.create_archive_zip,
        create_manager_zips=api.create_manager_zips,
        secure_file=api.secure_file,
        validate_archive_zip=api._validate_archive_zip,
        future_artifact=api._future_artifact,
        secure_write_json=api.secure_write_json,
        promote_directory=api._promote_directory,
        sleep=api.asyncio.sleep,
    )
    return await execute_archive(pool, request, ports)


async def archive_month(
    api: Any,
    pool: Any,
    month: str,
    only: str | None = None,
    delay: float = 0.5,
    *,
    month_key: str | None = None,
    requested_by_sub: str = "direct-execution",
    operation_id: int | None = None,
    google_adapter: Any | None = None,
) -> Path:
    execution = await api._archive_month_execution(
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
    timestamp = lambda value: value.isoformat() if isinstance(value, datetime) else value
    return {
        "id": record.get("id"),
        "operation_id": record.get("operation_id"),
        "month": record.get("closing_month"),
        "operation": record.get("operation"),
        "status": record.get("status"),
        "expected": manifest.get("expected", {}),
        "processed": manifest.get("processed", {}),
        "error_count": record.get("error_count", 0),
        "issues": _public_manifest_issues(manifest),
        "manifest_sha256": record.get("manifest_sha256"),
        "approved": bool(record.get("approved_by_sub")),
        "created_at": timestamp(record.get("created_at")),
        "verified_at": timestamp(record.get("verified_at")),
        "approved_at": timestamp(record.get("approved_at")),
        "consumed_at": timestamp(record.get("consumed_at")),
    }


def _public_manifest_issues(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw_issues = manifest.get("issues")
    if not isinstance(raw_issues, list):
        return []
    issues: list[dict[str, Any]] = []
    for raw in raw_issues[:200]:
        if not isinstance(raw, dict):
            continue
        site_code = raw.get("site_code")
        store = raw.get("store")
        slot = raw.get("slot")
        code = raw.get("code")
        field = raw.get("field")
        if (
            not isinstance(site_code, str)
            or not isinstance(store, str)
            or not isinstance(slot, int)
            or isinstance(slot, bool)
            or slot < 0
            or not isinstance(code, str)
            or (field is not None and not isinstance(field, str))
        ):
            continue
        issues.append(
            {
                "site_code": site_code,
                "store": store,
                "slot": slot,
                "code": code,
                "field": field,
            }
        )
    return issues


async def approve_manifest(
    api: Any,
    pool: Any,
    *,
    manifest_id: int,
    approved_by_sub: str,
) -> dict[str, Any]:
    record = await api.fetch_monthly_manifest(pool, manifest_id)
    if record is None:
        raise FileNotFoundError("Manifestul nu exista.")
    manifest = record.get("manifest")
    if record.get("operation") != "archive" or record.get("status") != "verified":
        raise api.MonthlyIntegrityError("manifest_not_approvable", "Manifest is not approvable")
    if not isinstance(manifest, dict):
        raise api.MonthlyIntegrityError("manifest_invalid", "Manifest is invalid")
    api.validate_verified_manifest(manifest, operation="archive")
    api.verify_artifacts(manifest, root=api.OUTPUTS_DIR)
    current_sha = manifest.get("manifest_sha256")
    if not isinstance(current_sha, str):
        raise api.MonthlyIntegrityError("manifest_hash_invalid", "Manifest hash is invalid")
    approved_manifest = dict(manifest)
    approved_manifest.update(
        status="approved",
        approved_by_sub=approved_by_sub,
        approved_at=api.utc_now(),
    )
    approved_manifest = api.finalize_manifest(approved_manifest)
    approved = await api.persist_monthly_manifest_approval(
        pool,
        manifest_id=manifest_id,
        expected_sha256=current_sha,
        approved_by_sub=approved_by_sub,
        approved_manifest=approved_manifest,
    )
    if approved is not None:
        return api.public_manifest_payload(approved)
    current = await api.fetch_monthly_manifest(pool, manifest_id)
    if current is not None and current.get("status") in {"approved", "consumed"}:
        return api.public_manifest_payload(current)
    raise api.MonthlyIntegrityError(
        "manifest_approval_race",
        "Manifest approval changed concurrently",
    )


async def reset_execution(
    api: Any,
    pool: Any,
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
    google_adapter: Any | None = None,
    execution_owner: str | None = None,
    execution_epoch: int | None = None,
) -> Any:
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
    ports = ResetPorts(
        outputs_dir=api.OUTPUTS_DIR,
        manifest_statuses=api.MANIFEST_ATTEMPT_STATUSES,
        fetch_latest_manifest=api.fetch_latest_monthly_manifest,
        fetch_manifest=api.fetch_monthly_manifest,
        validate_manifest=api.validate_verified_manifest,
        verify_artifacts=api.verify_artifacts,
        load_entries=api.load_entries,
        build_google_services=api.build_google_services,
        ensure_reset_items=api.ensure_reset_items,
        read_snapshot=api._read_reset_snapshot,
        read_snapshot_async=api._read_reset_snapshot_async,
        build_backup_dir=api.build_reset_backup_dir,
        secure_write_json=api.secure_write_json,
        record_backup=api.record_reset_item_backup,
        heartbeat=api.heartbeat_monthly_operation,
        mark_running=api.mark_reset_item_running,
        reset_store=api.reset_store,
        verify_cleared=api._verify_reset_cleared,
        finish_item=api.finish_reset_item,
        prepare_clear=api.persist_reset_clear_intent,
        google_request=api._google_request,
        reset_ranges=api.reset_ranges_for_entry,
        verify_cleared_async=api._verify_reset_cleared_async,
        confirm_clear=api.persist_reset_clear_confirmation,
        rollback_sync=api._rollback_reset_entries_cancel_safe,
        rollback_adapter=api._rollback_reset_entries_adapter_cancel_safe,
        build_dry_report_path=api.build_reset_dry_run_report_path,
        build_report_path=api.build_reset_report_path,
        staging_dir=api._staging_dir,
        promote_file=api._promote_file,
    )
    return await execute_reset(context, ports)


async def reset_month(api: Any, pool: Any, closing_month: str, next_month: str, **kwargs: Any) -> Path:
    kwargs.setdefault("requested_by_sub", "direct-execution")
    kwargs.setdefault("approved_manifest_id", None)
    execution = await api._reset_month_execution(
        pool,
        closing_month,
        next_month,
        closing_month_key=kwargs.pop("closing_month_key", None) or closing_month,
        next_month_key=kwargs.pop("next_month_key", None) or next_month,
        **kwargs,
    )
    return execution.path


async def reconcile(api: Any, pool: Any, google_adapter: Any) -> int:
    ports = ReconciliationPorts(
        claim_operations=api.claim_reconciliation_candidates,
        list_items=api.list_reset_items_for_reconciliation,
        mark_recovery=api.mark_item_recovery_required,
        read_backup=api._read_reset_backup,
        read_snapshot=api._read_reset_snapshot_async,
        mark_safe_retry=api.mark_item_safe_retry,
        prepare_rollback=api.persist_reset_rollback_intent,
        confirm_rollback=api.persist_reset_rollback_confirmation,
        restore_snapshot=api._restore_reset_snapshot_async,
        mark_operation=api.mark_reconciliation_result,
    )
    return await reconcile_operations(pool, google_adapter, ports)


def monthly_run_ports(api: Any) -> MonthlyRunPorts:
    return MonthlyRunPorts(
        valid_ops=frozenset(api.VALID_OPS),
        owner_hex=lambda: api.uuid4().hex,
        get_pool=api._monthly_operation_pool,
        start_operation=api.start_monthly_operation,
        heartbeat_operation=api.heartbeat_monthly_operation,
        finish_operation=api.finish_monthly_operation,
        run_with_lease=api._run_with_monthly_lease,
        persist_manifest=api.persist_manifest_result,
        persist_reset_success=api.persist_reset_success,
        fetch_manifest=api.fetch_monthly_manifest,
        finalize_execution=api._finalize_month_execution,
        archive_execution=api._archive_month_execution,
        reset_execution=api._reset_month_execution,
        base_manifest=api.base_manifest,
        public_manifest_payload=api.public_manifest_payload,
        finalize_manifest=api.finalize_manifest,
        ro_month_label=api.ro_month_label,
        next_month=api.next_ym,
        utc_now=api.utc_now,
        manifest_error_type=api.MonthlyManifestError,
        integrity_error_type=api.MonthlyIntegrityError,
    )


async def run_monthly_op(api: Any, **kwargs: Any) -> dict[str, Any]:
    return await orchestrate_monthly_operation(api._monthly_run_ports(), **kwargs)


async def fetch_download(api: Any, kind: str, month: str) -> tuple[bytes, str, str]:
    if kind not in api.VALID_DOWNLOADS:
        raise ValueError(f"Tip download necunoscut: {kind}")
    month_label = api.ro_month_label(month)
    if kind == "final":
        path = api.build_final_export_path(api.OUTPUTS_DIR, month_label)
        filename = f"Tabel Salarii - {month_label}.xlsx"
        media_type = api.XLSX_MIME
    else:
        path = api.build_archive_zip_path(api.OUTPUTS_DIR, month_label)
        filename = f"Arhiva Grile - {month_label}.zip"
        media_type = "application/zip"
    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(f"Fisierul {kind} pentru {month_label} nu exista inca.")
    return await asyncio.to_thread(path.read_bytes), filename, media_type
