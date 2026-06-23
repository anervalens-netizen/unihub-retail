from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pandas as pd
import pytest

import services.importer as importer


class AsyncContext(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.execute = AsyncMock()
        self.copy_records_to_table = AsyncMock()

    def transaction(self) -> AsyncContext:
        return AsyncContext()


def sales_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Data": date(2099, 7, 1),
                "SiteCode": "SITE01",
                "ItemCode": "ITEM01",
                "ItemName": "Produs 1",
                "Cantitate": 2,
                "Brand": "Brand",
                "Pret": 10.125,
                "Valoare": 20.255,
                "Locatie": "Magazin 1",
                "Firma": "Mobiup",
                "ASM": "Manager",
                "Regional": "Regional",
                "Nr": "BON1",
                "Categorie": "Accesorii",
                "SubCategorie": "Test",
                "Agent": "Agent 1",
                "is_cartela": False,
                "is_return": False,
            },
            {
                "Data": date(2099, 7, 2),
                "SiteCode": "SITE02",
                "ItemCode": "ITEM02",
                "ItemName": "Produs 2",
                "Cantitate": -1,
                "Brand": None,
                "Pret": 5,
                "Valoare": -5,
                "Locatie": "Magazin 2",
                "Firma": "Mobicell",
                "ASM": "Manager",
                "Regional": "Regional",
                "Nr": "BON2",
                "Categorie": None,
                "SubCategorie": None,
                "Agent": "Agent 2",
                "is_cartela": True,
                "is_return": True,
            },
            {
                "Data": date(2099, 7, 3),
                "SiteCode": "TR01",
                "ItemCode": "ITEM03",
                "ItemName": "Produs exclus",
                "Cantitate": 1,
                "Brand": "Brand",
                "Pret": 1,
                "Valoare": 1,
                "Locatie": "TR Exclus",
                "Firma": "Mobiup",
                "ASM": "-",
                "Regional": "Regional",
                "Nr": "BON3",
                "Categorie": "Accesorii",
                "SubCategorie": "Test",
                "Agent": "Agent 3",
                "is_cartela": False,
                "is_return": False,
            },
        ]
    )


@pytest.mark.asyncio
async def test_import_sales_dataframe_completes_filtered_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConnection()
    reserve = AsyncMock(return_value=42)
    upsert = AsyncMock()
    replace = AsyncMock()
    insert = AsyncMock(return_value=2)
    rebuild_month = AsyncMock()
    rebuild_lifecycle = AsyncMock()
    monkeypatch.setattr(importer, "reserve_snapshot", reserve)
    monkeypatch.setattr(importer, "upsert_stores", upsert)
    monkeypatch.setattr(importer, "replace_month_snapshot", replace)
    monkeypatch.setattr(importer, "insert_transactions", insert)
    monkeypatch.setattr(importer, "rebuild_reporting_month", rebuild_month)
    monkeypatch.setattr(
        importer,
        "rebuild_agent_lifecycle_reporting",
        rebuild_lifecycle,
    )
    monkeypatch.setattr(importer, "is_month_final", lambda month: True)

    result = await importer.import_sales_dataframe(
        conn,  # type: ignore[arg-type]
        sales_frame(),
        "sales.xlsx",
    )

    assert result.import_month == "2099-07"
    assert result.rows_in_file == 3
    assert result.rows_imported == 2
    assert result.rows_filtered == 1
    assert result.store_count == 2
    assert result.agent_count == 2
    assert result.snapshot_id == 42
    assert result.is_month_final is True
    reserve.assert_awaited_once_with(
        conn,
        import_month="2099-07",
        filename="sales.xlsx",
        rows_in_file=3,
    )
    insert_call = insert.await_args
    assert insert_call is not None
    inserted_frame = insert_call.args[1]
    assert list(inserted_frame["SiteCode"]) == ["SITE01", "SITE02"]
    rebuild_month.assert_awaited_once_with(conn, "2099-07")
    rebuild_lifecycle.assert_awaited_once_with(conn)
    completed_call = conn.execute.await_args
    assert completed_call is not None
    assert "status = 'completed'" in completed_call.args[0]
    assert completed_call.args[1:] == (42, 2, True)


@pytest.mark.asyncio
async def test_import_sales_dataframe_records_truncated_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConnection()
    long_error = "x" * 600
    monkeypatch.setattr(importer, "reserve_snapshot", AsyncMock(return_value=77))
    monkeypatch.setattr(importer, "upsert_stores", AsyncMock())
    monkeypatch.setattr(
        importer,
        "replace_month_snapshot",
        AsyncMock(side_effect=RuntimeError(long_error)),
    )
    monkeypatch.setattr(importer, "is_month_final", lambda month: False)

    with pytest.raises(RuntimeError, match="x{10}"):
        await importer.import_sales_dataframe(
            conn,  # type: ignore[arg-type]
            sales_frame().iloc[:1],
            "broken.xlsx",
        )

    failed_call = conn.execute.await_args
    assert failed_call is not None
    assert "status = 'failed'" in failed_call.args[0]
    assert failed_call.args[1] == 77
    assert failed_call.args[2] == long_error[:500]


@pytest.mark.asyncio
async def test_import_sales_dataframe_rejects_fully_filtered_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reserve = AsyncMock()
    monkeypatch.setattr(importer, "reserve_snapshot", reserve)

    with pytest.raises(ValueError, match="ASM valid"):
        await importer.import_sales_dataframe(
            FakeConnection(),  # type: ignore[arg-type]
            sales_frame().iloc[2:],
            "invalid.xlsx",
        )

    reserve.assert_not_awaited()


@pytest.mark.asyncio
async def test_insert_transactions_preserves_bulk_record_contract() -> None:
    conn = FakeConnection()

    rows = await importer.insert_transactions(
        conn,  # type: ignore[arg-type]
        sales_frame().iloc[:2],
        snapshot_id=15,
        import_month="2099-07",
    )

    assert rows == 2
    copied = conn.copy_records_to_table.await_args
    assert copied is not None
    assert copied.args == ("tmp_sales_transactions",)
    records = copied.kwargs["records"]
    assert records[0][9:] == (
        2,
        Decimal("10.12"),
        Decimal("20.26"),
        "Agent 1",
        False,
        False,
        15,
    )
    assert records[1][9:] == (
        -1,
        Decimal("5.00"),
        Decimal("-5.00"),
        "Agent 2",
        True,
        True,
        15,
    )
    execute_call = conn.execute.await_args
    assert execute_call is not None
    assert "INSERT INTO sales_transactions" in execute_call.args[0]


@pytest.mark.asyncio
async def test_import_sales_file_delegates_loaded_dataframe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = sales_frame().iloc[:1]
    load = lambda source: frame
    run_import = AsyncMock(return_value="result")
    monkeypatch.setattr(importer, "load_sales_dataframe", load)
    monkeypatch.setattr(importer, "import_sales_dataframe", run_import)
    conn = FakeConnection()

    result = await importer.import_sales_file(
        conn,  # type: ignore[arg-type]
        Path("sales.xlsx"),
        "sales.xlsx",
    )

    assert result == "result"
    run_import.assert_awaited_once_with(conn, frame, filename="sales.xlsx")


@pytest.mark.asyncio
async def test_upsert_store_targets_handles_empty_and_updates() -> None:
    conn = FakeConnection()
    conn.executemany = AsyncMock()  # type: ignore[attr-defined]

    assert await importer.upsert_store_targets(  # type: ignore[arg-type]
        conn,
        [],
        "targets.xlsx",
    ) == 0
    conn.executemany.assert_not_awaited()  # type: ignore[attr-defined]

    targets = [
        {
            "site_code": "SITE01",
            "import_month": "2099-07",
            "target_value": Decimal("123.45"),
        }
    ]
    assert await importer.upsert_store_targets(  # type: ignore[arg-type]
        conn,
        targets,
        "targets.xlsx",
    ) == 1
    upsert_call = conn.executemany.await_args  # type: ignore[attr-defined]
    assert upsert_call is not None
    args = upsert_call.args
    assert "ON CONFLICT (import_month, site_code) DO UPDATE" in args[0]
    assert args[1] == [("SITE01", "2099-07", Decimal("123.45"), "targets.xlsx")]
