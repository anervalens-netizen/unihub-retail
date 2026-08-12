"""Google snapshot, clear, verification and restore primitives for Grile reset."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from services.grile_monthly_integrity import (
    MonthlyIntegrityError,
    canonical_snapshot,
    snapshot_sha256,
)
from services.grile_monthly_types import StoreEntry, reset_ranges_for_entry


def read_snapshot(
    sheets_service: Any,
    entry: StoreEntry,
    *,
    retry_api: Callable[..., Any],
    attempts: int,
    base_delay: float,
) -> dict[str, Any]:
    reset_ranges = reset_ranges_for_entry(entry)

    def read() -> Any:
        return sheets_service.spreadsheets().values().batchGet(
            spreadsheetId=entry.sheet_id,
            ranges=reset_ranges,
            valueRenderOption="FORMULA",
            dateTimeRenderOption="SERIAL_NUMBER",
        ).execute()

    response = retry_api(
        read,
        label="Google reset backup",
        attempts=attempts,
        base_delay=base_delay,
    )
    value_ranges = response.get("valueRanges") if isinstance(response, dict) else None
    _require_complete(value_ranges, len(reset_ranges))
    return canonical_snapshot(value_ranges)


async def read_snapshot_async(
    google_adapter: Any,
    entry: StoreEntry,
    *,
    google_request: Callable[..., Awaitable[Any]],
) -> dict[str, Any]:
    ranges = reset_ranges_for_entry(entry)
    response = await google_request(
        google_adapter,
        "read_values",
        {
            "spreadsheet_id": entry.sheet_id,
            "ranges": ranges,
            "value_render_option": "FORMULA",
            "date_time_render_option": "SERIAL_NUMBER",
        },
        label="Google reset readback",
    )
    value_ranges = response.get("valueRanges") if isinstance(response, dict) else None
    _require_complete(value_ranges, len(ranges))
    return canonical_snapshot(value_ranges)


def _require_complete(value_ranges: Any, expected: int) -> None:
    if not isinstance(value_ranges, list) or len(value_ranges) != expected:
        raise MonthlyIntegrityError(
            "backup_response_incomplete",
            "Google backup response is incomplete",
        )


def restore_snapshot(
    sheets_service: Any,
    entry: StoreEntry,
    snapshot: dict[str, Any],
    *,
    retry_api: Callable[..., Any],
    attempts: int,
    base_delay: float,
    read_snapshot: Callable[[Any, StoreEntry], dict[str, Any]],
) -> None:
    data = _restore_data(snapshot)

    def restore() -> Any:
        return sheets_service.spreadsheets().values().batchUpdate(
            spreadsheetId=entry.sheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": data},
        ).execute()

    if data:
        retry_api(
            restore,
            label="Google reset rollback",
            attempts=attempts,
            base_delay=base_delay,
        )
    _verify_restored(read_snapshot(sheets_service, entry), snapshot)


async def restore_snapshot_async(
    google_adapter: Any,
    entry: StoreEntry,
    snapshot: dict[str, Any],
    *,
    google_request: Callable[..., Awaitable[Any]],
    read_snapshot: Callable[[Any, StoreEntry], Awaitable[dict[str, Any]]],
) -> None:
    data = _restore_data(snapshot)
    if data:
        await google_request(
            google_adapter,
            "restore",
            {"spreadsheet_id": entry.sheet_id, "data": data},
            label="Google reset rollback",
            destructive=True,
        )
    _verify_restored(await read_snapshot(google_adapter, entry), snapshot)


def _restore_data(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    value_ranges = snapshot.get("value_ranges")
    if not isinstance(value_ranges, list):
        raise MonthlyIntegrityError("backup_invalid", "Reset backup is invalid")
    return [
        {
            "range": item["range"],
            "majorDimension": item.get("majorDimension", "ROWS"),
            "values": item.get("values", []),
        }
        for item in value_ranges
        if isinstance(item, dict) and item.get("values")
    ]


def _verify_restored(restored: dict[str, Any], expected: dict[str, Any]) -> None:
    if snapshot_sha256(restored) != snapshot_sha256(expected):
        raise MonthlyIntegrityError(
            "rollback_verification_failed",
            "Reset rollback verification failed",
        )


def verify_cleared(snapshot: dict[str, Any]) -> None:
    value_ranges = snapshot.get("value_ranges", [])
    if any(item.get("values") for item in value_ranges if isinstance(item, dict)):
        raise MonthlyIntegrityError(
            "reset_verification_failed",
            "Reset verification failed",
        )


def reset_store(
    sheets_service: Any | None,
    entry: StoreEntry,
    *,
    dry_run: bool,
    retry_api: Callable[..., Any],
    attempts: int,
    base_delay: float,
    error_code: Callable[[Exception], str],
) -> dict[str, Any]:
    ranges = reset_ranges_for_entry(entry)
    result = _reset_result(entry, ranges, dry_run)
    if dry_run:
        return result
    assert sheets_service is not None
    try:
        retry_api(
            lambda: _clear(sheets_service, entry, ranges),
            label="Google reset",
            attempts=attempts,
            base_delay=base_delay,
        )
    except Exception as exc:  # noqa: BLE001 - provider error is classified
        result["status"] = "ERROR"
        result["error"] = exc.code if isinstance(exc, MonthlyIntegrityError) else error_code(exc)
    return result


def _clear(sheets_service: Any, entry: StoreEntry, ranges: list[str]) -> Any:
    return sheets_service.spreadsheets().values().batchClear(
        spreadsheetId=entry.sheet_id,
        body={"ranges": ranges},
    ).execute()


def _reset_result(
    entry: StoreEntry,
    ranges: list[str],
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "company": entry.company,
        "store": entry.store,
        "site_code": entry.site_code,
        "sheet_id": entry.sheet_id,
        "status": "DRY_RUN" if dry_run else "OK",
        "error": "",
        "ranges": ranges,
    }
