from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.import_store_pnl import PnlRow, WorkbookData, merged_rows, select_snapshots


def workbook(path: str, months: int, cells: int) -> WorkbookData:
    row = PnlRow("Mobiup", date(2025, 1, 1), "SITE", "Magazin", "v1", "Venit", Decimal("1.00"), path, "a" * 64)
    return WorkbookData(Path(path), "a" * 64, "Mobiup", (date(2025, 1, 1),), (row,), months, cells)


def test_select_snapshots_prefers_most_complete_file() -> None:
    early = workbook("early.xls", 2, 20)
    late = workbook("late.xls", 10, 100)
    selected, superseded = select_snapshots([early, late])
    assert selected == [late]
    assert superseded == [early]


def test_merged_rows_sums_duplicate_accounting_lines() -> None:
    one = workbook("one.xls", 1, 1)
    two = workbook("two.xls", 1, 1)
    rows = merged_rows([one, two])
    assert len(rows) == 1
    assert rows[0].amount == Decimal("2.00")
