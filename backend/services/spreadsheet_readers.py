"""Canonical XLS/XLSX readers with a bounded legacy parser boundary."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Sequence

import pandas as pd

from services.legacy_xls import LegacyXlsLimits, read_legacy_xls_frame, parse_legacy_xls, _frame_from_rows
from services.spreadsheet_safety import SpreadsheetUploadError


class MissingWorksheetsError(ValueError):
    def __init__(self, missing: Sequence[str]) -> None:
        self.missing = tuple(missing)
        super().__init__("Missing worksheets: " + ", ".join(self.missing))


def _payload_and_suffix(source: bytes | bytearray | str | Path, suffix: str | None) -> tuple[bytes, str]:
    if isinstance(source, (bytes, bytearray)):
        payload = bytes(source)
        resolved = suffix or (".xls" if payload.startswith(bytes.fromhex("d0cf11e0a1b11ae1")) else ".xlsx")
    else:
        path = Path(source)
        payload = path.read_bytes()
        resolved = suffix or path.suffix
    normalized = resolved.casefold()
    if normalized not in {".xls", ".xlsx"}:
        raise SpreadsheetUploadError("Format spreadsheet neacceptat")
    return payload, normalized


def read_spreadsheet_frame(
    source: bytes | bytearray | str | Path,
    *,
    suffix: str | None = None,
    sheet_name: str | int = 0,
    header: int | None = 0,
    limits: LegacyXlsLimits | None = None,
) -> pd.DataFrame:
    payload, normalized = _payload_and_suffix(source, suffix)
    if normalized == ".xls":
        return read_legacy_xls_frame(payload, sheet_name=sheet_name, header=header, limits=limits)
    if limits is not None and len(payload) > limits.max_source_bytes:
        raise SpreadsheetUploadError("Workbook-ul XLSX depășește limita sursei")
    return pd.read_excel(BytesIO(payload), sheet_name=sheet_name, header=header, engine="openpyxl")


def read_required_spreadsheet_frames(
    source: bytes | bytearray | str | Path,
    *,
    suffix: str | None = None,
    sheet_names: Sequence[str],
    header: int | None = 0,
    limits: LegacyXlsLimits | None = None,
) -> dict[str, pd.DataFrame]:
    payload, normalized = _payload_and_suffix(source, suffix)
    requested = tuple(dict.fromkeys(sheet_names))
    if normalized == ".xls":
        try:
            parsed = parse_legacy_xls(payload, sheets=requested, limits=limits)
        except KeyError as exc:
            missing_sheets = exc.args[0] if exc.args and isinstance(exc.args[0], tuple) else requested
            raise MissingWorksheetsError(missing_sheets) from exc
        return {name: _frame_from_rows(parsed.sheet(name).rows, header) for name in requested}

    if limits is not None and len(payload) > limits.max_source_bytes:
        raise SpreadsheetUploadError("Workbook-ul XLSX depășește limita sursei")
    workbook = pd.ExcelFile(BytesIO(payload), engine="openpyxl")
    missing_names = [name for name in requested if name not in workbook.sheet_names]
    if missing_names:
        raise MissingWorksheetsError(missing_names)
    return {name: workbook.parse(sheet_name=name, header=header) for name in requested}
