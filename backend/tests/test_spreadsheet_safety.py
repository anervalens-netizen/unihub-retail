from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

import pytest
from openpyxl import Workbook, load_workbook

from services.spreadsheet_safety import TrustedFormula, append_openpyxl_row


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
