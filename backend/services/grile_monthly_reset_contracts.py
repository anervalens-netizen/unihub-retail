"""Typed request context and injected ports for monthly Grile reset."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(slots=True)
class ResetRunContext:
    pool: Any
    closing_month: str
    next_month: str
    closing_month_key: str
    next_month_key: str
    requested_by_sub: str
    operation_id: int | None
    approved_manifest_id: int | None
    only: str | None
    dry_run: bool
    google_adapter: Any | None
    execution_owner: str | None
    execution_epoch: int | None


@dataclass(frozen=True)
class ResetPorts:
    outputs_dir: Path
    manifest_statuses: tuple[str, ...]
    fetch_latest_manifest: Callable[..., Any]
    fetch_manifest: Callable[..., Any]
    validate_manifest: Callable[..., Any]
    verify_artifacts: Callable[..., Any]
    load_entries: Callable[..., Any]
    build_google_services: Callable[..., Any]
    ensure_reset_items: Callable[..., Any]
    read_snapshot: Callable[..., Any]
    read_snapshot_async: Callable[..., Any]
    build_backup_dir: Callable[..., Any]
    secure_write_json: Callable[..., Any]
    record_backup: Callable[..., Any]
    heartbeat: Callable[..., Any]
    mark_running: Callable[..., Any]
    reset_store: Callable[..., Any]
    verify_cleared: Callable[..., Any]
    finish_item: Callable[..., Any]
    prepare_clear: Callable[..., Any]
    google_request: Callable[..., Any]
    reset_ranges: Callable[..., Any]
    verify_cleared_async: Callable[..., Any]
    confirm_clear: Callable[..., Any]
    rollback_sync: Callable[..., Any]
    rollback_adapter: Callable[..., Any]
    build_dry_report_path: Callable[..., Any]
    build_report_path: Callable[..., Any]
    staging_dir: Callable[..., Any]
    promote_file: Callable[..., Any]
