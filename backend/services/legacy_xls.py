"""Resource-bounded parser boundary for untrusted legacy OLE2/XLS workbooks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import multiprocessing
import os
from pathlib import Path
import json
import resource
import tempfile
import time
from typing import Any, Sequence

import pandas as pd
import xlrd

from services.spreadsheet_safety import SpreadsheetUploadError, SpreadsheetUploadLimits


OLE2_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")


@dataclass(frozen=True)
class LegacyXlsLimits:
    max_source_bytes: int = 32 * 1024 * 1024
    max_cells: int = 2_000_000
    max_output_bytes: int = 256 * 1024 * 1024
    memory_bytes: int = 1024 * 1024 * 1024
    timeout_seconds: float = 30.0
    cpu_seconds: int = 25


@dataclass(frozen=True)
class LegacyXlsSheet:
    name: str
    rows: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True)
class LegacyXlsWorkbook:
    sheets: tuple[LegacyXlsSheet, ...]

    def sheet(self, name: str) -> LegacyXlsSheet:
        for sheet in self.sheets:
            if sheet.name == name:
                return sheet
        raise KeyError(name)


def limits_from_upload_policy(policy: SpreadsheetUploadLimits) -> LegacyXlsLimits:
    return LegacyXlsLimits(
        max_source_bytes=policy.max_source_bytes,
        max_cells=policy.max_cells,
        max_output_bytes=policy.max_uncompressed_bytes,
        memory_bytes=max(512 * 1024 * 1024, min(1536 * 1024 * 1024, policy.max_uncompressed_bytes * 4)),
        timeout_seconds=60.0 if policy.max_cells > 1_000_000 else 30.0,
        cpu_seconds=55 if policy.max_cells > 1_000_000 else 25,
    )


def _cell_value(book: xlrd.book.Book, cell: xlrd.sheet.Cell) -> Any:
    if cell.ctype in {xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR}:
        return None
    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate.xldate_as_datetime(cell.value, book.datemode)
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    return cell.value


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"__unihub_datetime__": value.isoformat()}
    return value


def _json_object(value: dict[str, Any]) -> Any:
    if set(value) == {"__unihub_datetime__"}:
        return datetime.fromisoformat(str(value["__unihub_datetime__"]))
    return value


def _child_parse(
    payload: bytes,
    sheet_references: tuple[str | int, ...],
    limits: LegacyXlsLimits,
    output: str,
) -> None:
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
        resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limits.max_output_bytes, limits.max_output_bytes))
        book = xlrd.open_workbook(file_contents=payload, on_demand=True)
        available_names = book.sheet_names()
        available = set(available_names)
        sheet_names: list[str] = []
        missing: list[str | int] = []
        for reference in sheet_references:
            if isinstance(reference, int):
                if reference < 0 or reference >= len(available_names):
                    missing.append(reference)
                else:
                    sheet_names.append(available_names[reference])
            elif reference not in available:
                missing.append(reference)
            else:
                sheet_names.append(reference)
        if missing:
            result: dict[str, Any] = {"ok": False, "missing": missing}
        else:
            emitted: list[tuple[str, tuple[tuple[Any, ...], ...]]] = []
            cells = 0
            for name in sheet_names:
                source = book.sheet_by_name(name)
                cells += source.nrows * source.ncols
                if cells > limits.max_cells:
                    raise SpreadsheetUploadError("Workbook-ul XLS depășește limita de celule")
                rows = tuple(
                    tuple(_json_value(_cell_value(book, source.cell(row, column))) for column in range(source.ncols))
                    for row in range(source.nrows)
                )
                emitted.append((name, rows))
                book.unload_sheet(name)
            result = {"ok": True, "sheets": emitted}
    except BaseException as exc:  # child serializes a bounded diagnostic only
        result = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > limits.max_output_bytes:
        encoded = b'{"ok":false,"error":"Parser output exceeded limit"}'
    with open(output, "wb") as stream:
        stream.write(encoded)


def parse_legacy_xls(
    source: bytes | bytearray | str | Path,
    *,
    sheets: Sequence[str | int],
    limits: LegacyXlsLimits | None = None,
) -> LegacyXlsWorkbook:
    policy = limits or LegacyXlsLimits()
    payload = bytes(source) if isinstance(source, (bytes, bytearray)) else Path(source).read_bytes()
    if len(payload) > policy.max_source_bytes:
        raise SpreadsheetUploadError("Workbook-ul XLS depășește limita sursei")
    if not payload.startswith(OLE2_MAGIC):
        raise SpreadsheetUploadError("Fișierul .xls are o semnătură invalidă")
    requested = tuple(dict.fromkeys(sheets))
    if not requested:
        raise ValueError("At least one XLS worksheet is required")
    if any(isinstance(reference, int) and reference < 0 for reference in requested):
        raise ValueError("sheet index must be non-negative")

    descriptor, output = tempfile.mkstemp(prefix="unihub-xls-", suffix=".json")
    os.close(descriptor)
    try:
        process = multiprocessing.get_context("fork").Process(
            target=_child_parse,
            args=(payload, requested, policy, output),
            daemon=True,
        )
        process.start()
        deadline = time.monotonic() + policy.timeout_seconds
        while process.is_alive() and time.monotonic() < deadline:
            process.join(timeout=min(0.1, max(0.0, deadline - time.monotonic())))
        if process.is_alive():
            process.terminate()
            process.join(timeout=2.0)
            if process.is_alive():
                process.kill()
                process.join(timeout=1.0)
            raise SpreadsheetUploadError("Parserul XLS a depășit timpul permis")
        if process.exitcode != 0:
            raise SpreadsheetUploadError("Parserul XLS izolat s-a închis anormal")
        if Path(output).stat().st_size > policy.max_output_bytes:
            raise SpreadsheetUploadError("Rezultatul parserului XLS depășește limita")
        result = json.loads(Path(output).read_text(encoding="utf-8"), object_hook=_json_object)
    finally:
        Path(output).unlink(missing_ok=True)
    if not result.get("ok"):
        if result.get("missing"):
            raise KeyError(tuple(result["missing"]))
        raise SpreadsheetUploadError(str(result.get("error", "Parser XLS failed")))
    return LegacyXlsWorkbook(
        tuple(
            LegacyXlsSheet(
                name=name,
                rows=tuple(tuple(row) for row in rows),
            )
            for name, rows in result["sheets"]
        )
    )


def _frame_from_rows(rows: tuple[tuple[Any, ...], ...], header: int | None) -> pd.DataFrame:
    if header is None:
        return pd.DataFrame(rows)
    if header < 0 or header >= len(rows):
        return pd.DataFrame()
    columns = list(rows[header])
    return pd.DataFrame(rows[header + 1 :], columns=columns)


def read_legacy_xls_frame(
    source: bytes | bytearray | str | Path,
    *,
    sheet_name: str | int = 0,
    header: int | None = 0,
    limits: LegacyXlsLimits | None = None,
) -> pd.DataFrame:
    payload = bytes(source) if isinstance(source, (bytes, bytearray)) else Path(source).read_bytes()
    policy = limits or LegacyXlsLimits()
    if isinstance(sheet_name, int):
        if sheet_name < 0:
            raise ValueError("sheet_name must be non-negative")
        parsed = parse_legacy_xls(payload, sheets=[sheet_name], limits=policy)
        return _frame_from_rows(parsed.sheets[0].rows, header)
    else:
        resolved = sheet_name
    parsed = parse_legacy_xls(payload, sheets=[resolved], limits=policy)
    return _frame_from_rows(parsed.sheet(resolved).rows, header)
