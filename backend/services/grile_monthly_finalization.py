"""Finalization orchestration for monthly Grile salary workbooks."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from services.grile_monthly_artifacts import resolve_output_path
from services.grile_monthly_integrity import (
    MonthlyIntegrityError,
    base_manifest,
    finalize_manifest,
    relative_artifact,
    validate_verified_manifest,
    verify_artifacts,
)
from services.grile_monthly_parsing import value_ranges_for_entry
from services.grile_monthly_types import (
    ExtractedAgentRow,
    MonthlyExecution,
    MonthlyManifestError,
    StoreEntry,
)


@dataclass(frozen=True)
class FinalizationPorts:
    outputs_dir: Path
    load_entries: Callable[..., Awaitable[list[StoreEntry]]]
    build_google_services: Callable[[], tuple[Any, Any]]
    extract_store_rows: Callable[..., list[ExtractedAgentRow]]
    google_request: Callable[..., Awaitable[Any]]
    validate_coverage: Callable[..., tuple[int, int, int, int, list[str]]]
    control_totals: Callable[[list[ExtractedAgentRow]], dict[str, str]]
    staging_dir: Callable[[str, int | None], Path]
    build_workbook: Callable[..., None]
    secure_file: Callable[[Path], None]
    validate_workbook: Callable[..., None]
    promote_file: Callable[[Path, Path], None]
    with_source_registry: Callable[[dict[str, Any], list[StoreEntry]], dict[str, Any]]
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep


@dataclass(frozen=True)
class FinalizationRequest:
    month: str
    month_key: str
    requested_by_sub: str
    operation_id: int | None
    only: str | None
    delay: float
    google_adapter: Any | None


@dataclass(frozen=True)
class FinalizationCoverage:
    expected_stores: int
    processed_stores: int
    expected_agents: int
    processed_agents: int
    errors: list[str]
    totals: dict[str, str]
    issues: list[dict[str, Any]]


async def execute_finalization(
    pool: Any,
    request: FinalizationRequest,
    ports: FinalizationPorts,
) -> MonthlyExecution:
    entries = await ports.load_entries(
        pool,
        only=request.only,
        month=request.month_key,
    )
    rows = await _load_rows(entries, request, ports)
    coverage = _coverage(entries, rows, ports)
    _require_complete(request, coverage)
    output_path = _publish_workbook(entries, rows, request, coverage, ports)
    manifest = ports.with_source_registry(
        _manifest(request, coverage, [relative_artifact(
            output_path,
            root=ports.outputs_dir,
            kind="final_workbook",
        )]),
        entries,
    )
    validate_verified_manifest(manifest, operation="finalize")
    verify_artifacts(manifest, root=ports.outputs_dir)
    return MonthlyExecution(path=output_path, manifest=manifest)


async def _load_rows(
    entries: list[StoreEntry],
    request: FinalizationRequest,
    ports: FinalizationPorts,
) -> list[ExtractedAgentRow]:
    sheets_service = None
    if request.google_adapter is None:
        sheets_service, _ = ports.build_google_services()
    rows: list[ExtractedAgentRow] = []
    for index, entry in enumerate(entries, start=1):
        rows.extend(await _load_entry_rows(entry, sheets_service, request, ports))
        if request.delay > 0 and index < len(entries):
            await ports.sleep(request.delay)
    return rows


async def _load_entry_rows(
    entry: StoreEntry,
    sheets_service: Any,
    request: FinalizationRequest,
    ports: FinalizationPorts,
) -> list[ExtractedAgentRow]:
    if request.google_adapter is None:
        return ports.extract_store_rows(sheets_service, entry)
    ranges = value_ranges_for_entry(entry)
    response = await ports.google_request(
        request.google_adapter,
        "read_values",
        {
            "spreadsheet_id": entry.sheet_id,
            "ranges": ranges,
            "value_render_option": "UNFORMATTED_VALUE",
        },
        label="Google sheet read",
    )
    value_ranges = response.get("valueRanges") if isinstance(response, dict) else None
    if not isinstance(value_ranges, list) or len(value_ranges) != len(ranges):
        raise MonthlyIntegrityError(
            "google_response_incomplete",
            "Google sheet response is incomplete",
        )
    return ports.extract_store_rows(None, entry, value_ranges=value_ranges)


def _coverage(
    entries: list[StoreEntry],
    rows: list[ExtractedAgentRow],
    ports: FinalizationPorts,
) -> FinalizationCoverage:
    expected_stores, processed_stores, expected_agents, processed_agents, errors = (
        ports.validate_coverage(entries, rows)
    )
    return FinalizationCoverage(
        expected_stores,
        processed_stores,
        expected_agents,
        processed_agents,
        errors,
        ports.control_totals(rows),
        _source_issues(rows),
    )


def _source_issues(rows: list[ExtractedAgentRow]) -> list[dict[str, Any]]:
    return [
        {
            "site_code": row.site_code,
            "store": row.store,
            "slot": row.slot,
            "code": row.error_code or "store_read_failed",
            "field": row.error_field or None,
        }
        for row in rows
        if row.status != "OK"
    ]


def _require_complete(
    request: FinalizationRequest,
    coverage: FinalizationCoverage,
) -> None:
    complete = (
        not coverage.errors
        and coverage.processed_stores == coverage.expected_stores
        and coverage.processed_agents == coverage.expected_agents
    )
    if complete:
        return
    failed = _manifest(
        request,
        coverage,
        [],
        errors=coverage.errors or ["coverage_incomplete"],
        status="failed",
    )
    raise MonthlyManifestError(
        "finalization_incomplete",
        "Finalization coverage is incomplete",
        failed,
    )


def _publish_workbook(
    entries: list[StoreEntry],
    rows: list[ExtractedAgentRow],
    request: FinalizationRequest,
    coverage: FinalizationCoverage,
    ports: FinalizationPorts,
) -> Path:
    stage_dir = ports.staging_dir("finalize", request.operation_id)
    staged_path = stage_dir / "candidate.xlsx"
    output_path = resolve_output_path(request.month, request.only, ports.outputs_dir)
    metadata = {(entry.company, entry.store): {"Manager": entry.manager} for entry in entries}
    try:
        ports.build_workbook(rows, staged_path, metadata)
        ports.secure_file(staged_path)
        ports.validate_workbook(staged_path, expected_agents=coverage.expected_agents)
        ports.promote_file(staged_path, output_path)
    except Exception as exc:
        code = exc.code if isinstance(exc, MonthlyIntegrityError) else "workbook_promotion_failed"
        raise MonthlyManifestError(
            code,
            "Final workbook could not be verified",
            _manifest(request, coverage, [], errors=[code], status="failed"),
        ) from exc
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
    return output_path


def _manifest(
    request: FinalizationRequest,
    coverage: FinalizationCoverage,
    artifacts: list[dict[str, Any]],
    *,
    errors: list[str] | None = None,
    status: str = "verified",
) -> dict[str, Any]:
    manifest = base_manifest(
        month=request.month_key,
        operation="finalize",
        requested_by_sub=request.requested_by_sub,
        expected_stores=coverage.expected_stores,
        expected_agents=coverage.expected_agents,
        processed_stores=coverage.processed_stores,
        processed_agents=coverage.processed_agents,
        control_totals=coverage.totals,
        artifacts=artifacts,
        errors=errors or (),
        status=status,
    )
    manifest["issues"] = coverage.issues
    return finalize_manifest(manifest)
