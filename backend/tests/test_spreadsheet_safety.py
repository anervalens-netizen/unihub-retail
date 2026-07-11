from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

import pytest
from openpyxl import Workbook, load_workbook

from services.spreadsheet_safety import (
    TrustedFormula,
    append_openpyxl_row,
    csv_cell_value,
    google_sheets_value,
    sanitize_spreadsheet_text,
    spreadsheet_cell_value,
)


@pytest.mark.parametrize("value", ["=1+1", "+SUM(1,1)", "-1+2", "@SUM(1,1)", "\t=1", "\r=1", "\n=1", "-123"])
def test_untrusted_formula_prefixes_are_explicit_text(value: str) -> None:
    wb = Workbook()
    ws = wb.active
    append_openpyxl_row(ws, [value])
    cell = ws["A1"]
    assert cell.data_type == "s"
    assert cell.value == "'" + value


def test_native_values_and_trusted_formula_round_trip() -> None:
    wb = Workbook()
    ws = wb.active
    append_openpyxl_row(ws, ["Buna ziua", "", None, -123, -1.5, Decimal("-2.3"), True, date(2026, 1, 2), datetime(2026, 1, 2, 3, 4), TrustedFormula("=SUM(A1:A1)")])
    stream = BytesIO()
    wb.save(stream)
    reopened = load_workbook(BytesIO(stream.getvalue()), data_only=False)
    assert reopened.active["J1"].data_type == "f"
    assert reopened.active["J1"].value == "=SUM(A1:A1)"
    assert reopened.active["D1"].value == -123
    with ZipFile(BytesIO(stream.getvalue())) as archive:
        xml = archive.read("xl/worksheets/sheet1.xml").decode()
    assert "<f>" in xml


def test_untrusted_hyperlink_is_not_formula_in_xlsx_xml() -> None:
    payload = '=HYPERLINK("https://example.invalid","click")'
    wb = Workbook()
    append_openpyxl_row(wb.active, [payload])
    stream = BytesIO()
    wb.save(stream)
    with ZipFile(BytesIO(stream.getvalue())) as archive:
        xml = archive.read("xl/worksheets/sheet1.xml").decode()
    assert "<f>HYPERLINK" not in xml
    assert load_workbook(BytesIO(stream.getvalue()), data_only=False).active["A1"].data_type == "s"


def test_invalid_trusted_formula_is_rejected() -> None:
    with pytest.raises(ValueError, match="must start"):
        TrustedFormula("SUM(A1:A2)")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Buna ziua", "Buna ziua"), ("", ""), (None, None), ("Ștefan", "Ștefan"),
        (-4, -4), (-1.5, -1.5), (Decimal("-2.5"), Decimal("-2.5")),
        (True, True), (date(2026, 1, 2), date(2026, 1, 2)),
        (datetime(2026, 1, 2, 3, 4), datetime(2026, 1, 2, 3, 4)),
    ],
)
def test_central_value_api_preserves_safe_native_values(value: object, expected: object) -> None:
    assert spreadsheet_cell_value(value) == expected


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r", "\n"])
def test_csv_and_google_values_neutralize_all_formula_prefixes(prefix: str) -> None:
    value = prefix + "1+1"
    assert csv_cell_value(value) == "'" + value
    assert google_sheets_value(value) == "'" + value


def test_append_rows_do_not_overwrite_leading_or_fully_empty_rows() -> None:
    wb = Workbook()
    ws = wb.active
    append_openpyxl_row(ws, [None, "primul"])
    append_openpyxl_row(ws, ["al doilea", "valoare"])
    append_openpyxl_row(ws, [None, None])
    append_openpyxl_row(ws, ["dupa-rand-gol"])

    assert ws["B1"].value == "primul"
    assert ws["A2"].value == "al doilea"
    assert ws["B2"].value == "valoare"
    assert ws["A3"].value is None
    assert ws["A4"].value == "dupa-rand-gol"


def test_non_finite_decimal_and_broken_string_conversion_are_safe() -> None:
    class BrokenString:
        def __str__(self) -> str:
            raise RuntimeError("no string")

    assert spreadsheet_cell_value(Decimal("NaN")) == "NaN"
    assert spreadsheet_cell_value(Decimal("Infinity")) == "Infinity"
    assert spreadsheet_cell_value(BrokenString()) == "<BrokenString>"
    assert sanitize_spreadsheet_text("=1+1") == "'=1+1"


def test_dataframe_boundary_only_neutralizes_text_columns() -> None:
    import pandas as pd

    from services.spreadsheet_safety import sanitize_dataframe_text

    safe = sanitize_dataframe_text(pd.DataFrame({"text": ["=1+1"], "amount": [-12]}))
    assert safe.loc[0, "text"] == "'=1+1"
    assert safe.loc[0, "amount"] == -12
