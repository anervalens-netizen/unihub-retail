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
    if value is None or isinstance(value, (int, float, Decimal, bool, date, datetime)):
        return value
    return sanitize_spreadsheet_text(str(value))


def csv_cell_value(value: object) -> object:
    safe = spreadsheet_cell_value(value)
    return safe.expression if isinstance(safe, TrustedFormula) else safe


def google_sheets_value(value: object) -> object:
    safe = spreadsheet_cell_value(value)
    return safe.expression if isinstance(safe, TrustedFormula) else safe


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
    row_index = 1 if ws.max_row == 1 and ws.cell(1, 1).value is None else ws.max_row + 1
    for column_index, value in enumerate(values, start=1):
        set_openpyxl_cell(ws.cell(row=row_index, column=column_index), value)
