"""Finite resource limits and request validation primitives."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .metrics import EXPORT_REJECTED_TOTAL

EXPORT_MAX_ROWS = 50_000
EXPORT_MAX_CELLS = 1_000_000
EXPORT_MAX_OUTPUT_BYTES = 64 * 1024 * 1024
EXPORT_MAX_PEAK_RSS_BYTES = 512 * 1024 * 1024
# Absolute web-process fence; the smaller peak cap below remains the maximum
# memory growth attributable to one in-process writer.
EXPORT_MAX_PROCESS_RSS_BYTES = 1024 * 1024 * 1024
EXPORT_ESTIMATED_BYTES_PER_CELL = 128
EXPORT_MAX_PREVIEW_ROWS = 500


class ExportValidationError(ValueError):
    pass


def selected_days(request: dict[str, Any]) -> list[int] | None:
    raw_days = request.get("selected_days")
    if raw_days is None:
        return None
    try:
        days = sorted({int(day) for day in raw_days})
    except (TypeError, ValueError) as exc:
        raise ExportValidationError("Selectia zilelor este invalida.") from exc
    if not days:
        raise ExportValidationError("Selecteaza cel putin o zi.")
    if any(day < 1 or day > 31 for day in days):
        raise ExportValidationError("Zilele trebuie sa fie intre 1 si 31.")
    return None if days == list(range(1, 32)) else days


def normalize_filters(filters: dict[str, Any]) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for key, value in filters.items():
        if key not in {"firma", "regional", "asm", "site_code", "agent"}:
            continue
        normalized[key] = [str(item) for item in value if str(item).strip()] if isinstance(value, list) else ([str(value)] if value else [])
    if normalized.get("site_code"):
        for hierarchy_key in ("firma", "regional", "asm"):
            normalized.pop(hierarchy_key, None)
    return {key: value for key, value in normalized.items() if value}


def scoped_filter_values(
    filters: dict[str, list[str]],
    key: str,
) -> list[str] | None:
    """Preserve one normalized multi-select scope for canonical SQL builders."""
    return filters.get(key) or None


def valid_keys(value: Any, allowed: set[str], default: list[str], label: str) -> list[str]:
    if not value:
        return default
    keys = [str(item) for item in value]
    invalid = [key for key in keys if key not in allowed]
    if invalid:
        raise ExportValidationError(f"Selectie invalida pentru {label}: {', '.join(invalid)}")
    return keys


def preview_limit(request: dict[str, Any]) -> int:
    try:
        limit = int(request.get("preview_limit", 100))
    except (TypeError, ValueError) as exc:
        raise ExportValidationError("Limita preview este invalida.") from exc
    if limit < 1 or limit > EXPORT_MAX_PREVIEW_ROWS:
        raise ExportValidationError(
            f"Limita preview poate fi intre 1 si maxim {EXPORT_MAX_PREVIEW_ROWS}."
        )
    return limit


def max_days_for_months(months: list[str]) -> int:
    maximum = 0
    for month in months:
        try:
            year_value, month_value = month.split("-", 1)
            year, month_number = int(year_value), int(month_value)
            current = datetime(year, month_number, 1)
            following = datetime(year + 1, 1, 1) if month_number == 12 else datetime(year, month_number + 1, 1)
            maximum = max(maximum, (following - current).days)
        except (TypeError, ValueError):
            continue
    return maximum or 31


def validate_budget(row_count: int, column_count: int, *, operation: str, cells: int | None = None) -> None:
    if row_count > EXPORT_MAX_ROWS:
        EXPORT_REJECTED_TOTAL.labels("rows").inc()
        raise ExportValidationError(f"{operation} depaseste limita de {EXPORT_MAX_ROWS} randuri.")
    cell_count = cells if cells is not None else row_count * max(1, column_count)
    if cell_count > EXPORT_MAX_CELLS:
        EXPORT_REJECTED_TOTAL.labels("cells").inc()
        raise ExportValidationError(f"{operation} depaseste limita de {EXPORT_MAX_CELLS} celule.")
    if 4096 + cell_count * EXPORT_ESTIMATED_BYTES_PER_CELL > EXPORT_MAX_OUTPUT_BYTES:
        EXPORT_REJECTED_TOTAL.labels("output_bytes").inc()
        raise ExportValidationError(f"{operation} depaseste limita de dimensiune estimata ({EXPORT_MAX_OUTPUT_BYTES} bytes).")
