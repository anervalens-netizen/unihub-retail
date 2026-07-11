"""Single writer boundary for untrusted spreadsheet text."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable


_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


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
    """Copy a pandas-like table and neutralize only its textual columns."""
    safe_frame = frame.copy()
    for column in safe_frame.columns:
        if str(safe_frame[column].dtype) in {"object", "string"}:
            safe_frame[column] = safe_frame[column].map(spreadsheet_cell_value)
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
