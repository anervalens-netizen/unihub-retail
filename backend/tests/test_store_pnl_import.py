from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from scripts.import_store_pnl import (
    PnlRow,
    UNALLOCATED_SOURCE,
    WorkbookData,
    detail_category,
    merged_rows,
    select_snapshots,
    unallocated_rows,
)


def workbook(path: str, months: int, cells: int) -> WorkbookData:
    row = PnlRow("Mobiup", date(2025, 1, 1), "SITE", "Magazin", "v1", "Venit", Decimal("1.00"), path, "a" * 64)
    return WorkbookData(Path(path), "a" * 64, "Mobiup", (date(2025, 1, 1),), (row,), (), months, cells)


def test_select_snapshots_prefers_most_complete_file() -> None:
    early = workbook("early.xls", 2, 20)
    late = workbook("late.xls", 10, 100)
    selected, superseded = select_snapshots([early, late])
    assert selected == [late]
    assert superseded == [early]


def test_detail_category_recovers_shifted_finance_rows() -> None:
    sheet = MagicMock()
    sheet.cell_value.side_effect = lambda _row, column: {
        1: "",
        5: "c11-ACM",
    }.get(column, "")

    assert detail_category(sheet, 421) == "c11"


def test_merged_rows_sums_duplicate_accounting_lines() -> None:
    one = workbook("one.xls", 1, 1)
    two = workbook("two.xls", 1, 1)
    rows = merged_rows([one, two])
    assert len(rows) == 1
    assert rows[0].amount == Decimal("2.00")


def test_unallocated_rows_preserve_finance_consolidated_total() -> None:
    detail = PnlRow("Mobiup", date(2025, 1, 1), "SITE", "Magazin", "v11", "Venit", Decimal("90.00"), "file.xls", "a" * 64)
    total = PnlRow("Mobiup", date(2025, 1, 1), UNALLOCATED_SOURCE, "Total", "v11", "Venit", Decimal("100.00"), "file.xls", "a" * 64)
    source = WorkbookData(Path("file.xls"), "a" * 64, "Mobiup", (date(2025, 1, 1),), (detail,), (total,), 1, 1)

    rows = unallocated_rows([detail], [source])

    assert len(rows) == 1
    assert rows[0].source_site_code == UNALLOCATED_SOURCE
    assert rows[0].amount == Decimal("10.00")


def test_unallocated_rows_reject_store_filtered_summary() -> None:
    detail = PnlRow("Mobiup", date(2025, 1, 1), "SITE", "Magazin", "v11", "Venit", Decimal("100.00"), "late.xls", "a" * 64)
    filtered_total = PnlRow("Mobiup", date(2025, 1, 1), UNALLOCATED_SOURCE, "Total", "v11", "Venit", Decimal("10.00"), "late.xls", "a" * 64)
    source = WorkbookData(Path("late.xls"), "a" * 64, "Mobiup", (date(2025, 1, 1),), (detail,), (filtered_total,), 10, 100)

    assert unallocated_rows([detail], [source]) == []


def test_unallocated_rows_can_use_older_valid_consolidated_snapshot() -> None:
    detail = PnlRow("Mobiup", date(2025, 1, 1), "SITE", "Magazin", "v11", "Venit", Decimal("100.00"), "late.xls", "a" * 64)
    valid_total = PnlRow("Mobiup", date(2025, 1, 1), UNALLOCATED_SOURCE, "Total", "v11", "Venit", Decimal("120.00"), "early.xls", "b" * 64)
    filtered_total = PnlRow("Mobiup", date(2025, 1, 1), UNALLOCATED_SOURCE, "Total", "v11", "Venit", Decimal("10.00"), "late.xls", "a" * 64)
    early = WorkbookData(Path("early.xls"), "b" * 64, "Mobiup", (date(2025, 1, 1),), (), (valid_total,), 7, 70)
    late = WorkbookData(Path("late.xls"), "a" * 64, "Mobiup", (date(2025, 1, 1),), (detail,), (filtered_total,), 10, 100)

    rows = unallocated_rows([detail], [early, late])

    assert len(rows) == 1
    assert rows[0].amount == Decimal("20.00")
    assert rows[0].source_file == "early.xls"
