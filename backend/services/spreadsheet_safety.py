"""Single writer boundary for untrusted spreadsheet text."""
from __future__ import annotations

import math
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable
from xml.etree import ElementTree


_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")
_OLE_COMPOUND_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")


class SpreadsheetUploadError(ValueError):
    """The uploaded spreadsheet exceeded a structural safety boundary."""


@dataclass(frozen=True)
class SpreadsheetUploadLimits:
    max_members: int = 2_048
    max_member_bytes: int = 64 * 1024 * 1024
    max_uncompressed_bytes: int = 256 * 1024 * 1024
    max_compression_ratio: int = 100
    max_cells: int = 2_000_000


def validate_spreadsheet_upload(
    content: bytes,
    suffix: str,
    *,
    limits: SpreadsheetUploadLimits | None = None,
) -> None:
    """Validate file signature and bounded XLSX expansion before parsing."""

    normalized_suffix = suffix.casefold()
    if normalized_suffix == ".xls":
        if not content.startswith(_OLE_COMPOUND_MAGIC):
            raise SpreadsheetUploadError("Fișierul .xls are o semnătură invalidă")
        return
    if normalized_suffix != ".xlsx":
        raise SpreadsheetUploadError("Format spreadsheet neacceptat")
    if not content.startswith(b"PK"):
        raise SpreadsheetUploadError("Fișierul .xlsx are o semnătură invalidă")

    policy = limits or SpreadsheetUploadLimits()
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > policy.max_members:
                raise SpreadsheetUploadError("Workbook-ul conține prea mulți membri ZIP")
            names = {member.filename for member in members}
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise SpreadsheetUploadError("Structura XLSX obligatorie lipsește")

            expanded = 0
            compressed = 0
            for member in members:
                if member.flag_bits & 0x1:
                    raise SpreadsheetUploadError("Workbook-urile ZIP criptate nu sunt acceptate")
                if member.file_size > policy.max_member_bytes:
                    raise SpreadsheetUploadError("Un membru XLSX depășește limita permisă")
                expanded += member.file_size
                compressed += member.compress_size
                if expanded > policy.max_uncompressed_bytes:
                    raise SpreadsheetUploadError("Workbook-ul depășește bugetul decomprimat")
            if expanded > max(compressed, 1) * policy.max_compression_ratio:
                raise SpreadsheetUploadError("Raportul de compresie XLSX este excesiv")

            cell_count = 0
            worksheets = [
                member
                for member in members
                if member.filename.startswith("xl/worksheets/")
                and member.filename.endswith(".xml")
            ]
            for worksheet in worksheets:
                with archive.open(worksheet) as stream:
                    for _event, element in ElementTree.iterparse(stream, events=("end",)):
                        if element.tag.rsplit("}", 1)[-1] == "c":
                            cell_count += 1
                            if cell_count > policy.max_cells:
                                raise SpreadsheetUploadError(
                                    "Workbook-ul depășește limita de celule"
                                )
                        element.clear()
    except SpreadsheetUploadError:
        raise
    except (zipfile.BadZipFile, OSError, ElementTree.ParseError) as exc:
        raise SpreadsheetUploadError("Workbook-ul XLSX este corupt") from exc


@dataclass(frozen=True)
class TrustedFormula:
    expression: str

    def __post_init__(self) -> None:
        if not self.expression.startswith("="):
            raise ValueError("TrustedFormula must start with '='")


def sanitize_spreadsheet_text(value: str) -> str:
    return "'" + value if value.startswith(_DANGEROUS_PREFIXES) else value


def spreadsheet_cell_value(value: object) -> object:
    if isinstance(value, TrustedFormula):
        return value
    if isinstance(value, str):
        return sanitize_spreadsheet_text(value)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, Decimal) and not value.is_finite():
        return str(value)
    if value is None or isinstance(value, (int, float, Decimal, bool, date, datetime)):
        return value
    try:
        text = str(value)
    except Exception:
        text = f"<{type(value).__name__}>"
    return sanitize_spreadsheet_text(text)


def csv_cell_value(value: object) -> object:
    safe = spreadsheet_cell_value(value)
    return safe.expression if isinstance(safe, TrustedFormula) else safe


def google_sheets_value(value: object) -> object:
    safe = spreadsheet_cell_value(value)
    return safe.expression if isinstance(safe, TrustedFormula) else safe


def sanitize_dataframe_text(frame: Any) -> Any:
    """Copy a pandas-like table and neutralize textual cells only.

    Missing values remain blank instead of becoming the literal strings ``nan``
    or ``<NA>``.  Object, pandas string, categorical and compatible extension
    text columns are covered while numeric columns retain their native dtype.
    """
    import pandas as pd

    safe_frame = frame.copy()
    for column in safe_frame.columns:
        series = safe_frame[column]
        dtype = series.dtype
        kind = getattr(dtype, "kind", None)
        is_textual = (
            kind in {"O", "U", "S"}
            or isinstance(dtype, pd.StringDtype)
            or isinstance(dtype, pd.CategoricalDtype)
        )
        if not is_textual:
            continue

        def sanitize_value(value: object) -> object:
            try:
                missing = pd.isna(value)
                try:
                    if bool(missing):
                        return None
                except (TypeError, ValueError):
                    pass
            except Exception:
                pass
            return spreadsheet_cell_value(value)

        # Convert extension/categorical columns to object so neutralized values
        # that are not part of the original category set can be assigned safely.
        safe_frame[column] = series.astype("object").map(sanitize_value)
    return safe_frame


def set_openpyxl_cell(cell: Any, value: object) -> None:
    safe = spreadsheet_cell_value(value)
    if isinstance(safe, TrustedFormula):
        cell.value = safe.expression
        cell.data_type = "f"
    elif isinstance(safe, str):
        cell.value = safe
        cell.data_type = "s"
    else:
        cell.value = safe


def append_openpyxl_row(ws: Any, values: Iterable[object]) -> None:
    if ws.__class__.__name__ == "WriteOnlyWorksheet":
        raise TypeError("append_openpyxl_row does not support write-only worksheets")

    # ``max_row`` cannot distinguish an untouched worksheet from a logical row
    # beginning in column B.  Preserve writer state so such rows are never reused.
    last_row = getattr(ws, "_unihub_safe_last_row", None)
    if last_row is None:
        first_row_is_empty = ws.max_row == 1 and all(cell.value is None for cell in ws[1])
        last_row = 0 if first_row_is_empty else ws.max_row
    row_index = last_row + 1
    for column_index, value in enumerate(values, start=1):
        set_openpyxl_cell(ws.cell(row=row_index, column=column_index), value)
    setattr(ws, "_unihub_safe_last_row", row_index)
