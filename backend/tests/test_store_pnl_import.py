from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.import_store_pnl import (
    PnlRow,
    UNALLOCATED_SOURCE,
    WorkbookData,
    candidate_business_keys,
    coverage_regressions,
    detail_category,
    merged_rows,
    replace_rows,
    replacement_scopes,
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


def test_replacement_scope_is_exact_company_period() -> None:
    rows = [
        PnlRow(
            company,
            period,
            "SITE",
            "Magazin",
            "v1",
            "Venit",
            Decimal("1.00"),
            "file.xls",
            "a" * 64,
        )
        for company, period in (
            ("Mobiup", date(2025, 1, 1)),
            ("Mobiup", date(2025, 3, 1)),
            ("Mobicell", date(2025, 1, 1)),
        )
    ]

    assert replacement_scopes(rows) == [
        ("Mobicell", date(2025, 1, 1)),
        ("Mobiup", date(2025, 1, 1)),
        ("Mobiup", date(2025, 3, 1)),
    ]


def test_coverage_regression_blocks_missing_existing_key() -> None:
    candidate = workbook("candidate.xls", 1, 1).rows[0]
    current = [
        {
            "company_name": "Mobiup",
            "period": date(2025, 1, 1),
            "source_site_code": "SITE",
            "category_code": "v1",
        },
        {
            "company_name": "Mobiup",
            "period": date(2025, 1, 1),
            "source_site_code": "SITE",
            "category_code": "c1",
        },
    ]

    assert coverage_regressions(current, [candidate]) == [
        ("Mobiup", date(2025, 1, 1), "SITE", "c1")
    ]



def test_resolved_unallocated_bucket_is_not_a_coverage_regression() -> None:
    candidate = workbook("candidate.xls", 1, 1).rows[0]
    current = [
        {
            "company_name": "Mobiup",
            "period": date(2025, 1, 1),
            "source_site_code": UNALLOCATED_SOURCE,
            "category_code": "v1",
        }
    ]

    assert coverage_regressions(current, [candidate]) == []

def test_duplicate_candidate_business_key_is_rejected() -> None:
    candidate = workbook("candidate.xls", 1, 1).rows[0]
    with pytest.raises(RuntimeError, match="chei business duplicate"):
        candidate_business_keys([candidate, candidate])


@pytest.mark.anyio
async def test_replace_rows_deletes_only_exact_scope_and_verifies_totals() -> None:
    candidate = workbook("candidate.xls", 1, 1).rows[0]
    connection = MagicMock()
    connection.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    connection.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
    connection.fetch = AsyncMock(return_value=[])
    connection.execute = AsyncMock()
    connection.executemany = AsyncMock()
    connection.fetchrow = AsyncMock(
        return_value={"row_count": 1, "total_amount": Decimal("1.00")}
    )

    await replace_rows(connection, [candidate])

    delete_call = connection.execute.await_args
    assert delete_call is not None
    assert "company_name = $1" in delete_call.args[0]
    assert "period = $2" in delete_call.args[0]
    assert delete_call.args[1:] == ("Mobiup", date(2025, 1, 1))
    assert "make_date" not in delete_call.args[0]
    assert "__FINANCE_UNALLOCATED__" not in delete_call.args[0]
