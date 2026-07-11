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
