from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import date
from decimal import Decimal
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
        self.fetchrow = AsyncMock()
        self.fetchval = AsyncMock()

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
    stage = AsyncMock(return_value=2)
    heartbeat = AsyncMock()
    persist = AsyncMock()
    load_previous = AsyncMock(return_value=(None, None))
    coverage = {"incoming_store_count": 2, "store_activity_writes": 0}
    build_coverage = AsyncMock(return_value=coverage)
    monkeypatch.setattr(importer, "reserve_snapshot", reserve)
    monkeypatch.setattr(importer, "load_current_sales_manifest", load_previous)
    monkeypatch.setattr(importer, "fenced_generation_heartbeat", heartbeat)
    monkeypatch.setattr(importer, "stage_sales_generation_rows", stage)
    monkeypatch.setattr(importer, "persist_validated_sales_generation", persist)
    monkeypatch.setattr(importer, "build_import_coverage_report", build_coverage)
    monkeypatch.setattr(importer, "is_month_final", lambda month: True)

    result = await importer.import_sales_dataframe(
        conn,  # type: ignore[arg-type]
        sales_frame(),
        "sales.xlsx",
        stage_only=True,
    )

    assert result.import_month == "2099-07"
    assert result.rows_in_file == 3
    assert result.rows_imported == 2
    assert result.rows_filtered == 1
    assert result.store_count == 2
    assert result.agent_count == 2
    assert result.snapshot_id == 42
    assert result.is_month_final is True
    assert result.coverage_report == coverage
    assert result.generation_state == "validated"
    reserve_call = reserve.await_args
    assert reserve_call is not None
    assert reserve_call.kwargs["import_month"] == "2099-07"
    assert reserve_call.kwargs["filename"] == "sales.xlsx"
    assert reserve_call.kwargs["rows_in_file"] == 3
    assert reserve_call.kwargs["cutoff_date"] == date(2099, 7, 2)
    stage_call = stage.await_args
    assert stage_call is not None
    inserted_frame = stage_call.args[1]
    assert list(inserted_frame["SiteCode"]) == ["SITE01", "SITE02"]
    assert stage_call.kwargs == {"snapshot_id": 42, "import_month": "2099-07"}
    build_coverage.assert_awaited_once()
    heartbeat.assert_awaited_once()
    persist.assert_awaited_once()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_sales_dataframe_records_truncated_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConnection()
    long_error = "x" * 600
    monkeypatch.setattr(importer, "reserve_snapshot", AsyncMock(return_value=77))
    monkeypatch.setattr(
        importer,
        "build_import_coverage_report",
        AsyncMock(return_value={"store_activity_writes": 0}),
    )
    monkeypatch.setattr(importer, "load_current_sales_manifest", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(importer, "fenced_generation_heartbeat", AsyncMock())
    monkeypatch.setattr(importer, "stage_sales_generation_rows", AsyncMock(side_effect=RuntimeError(long_error)))
    monkeypatch.setattr(importer, "is_month_final", lambda month: False)

    with pytest.raises(RuntimeError, match="x{10}"):
        await importer.import_sales_dataframe(
            conn,  # type: ignore[arg-type]
            sales_frame().iloc[:1],
            "broken.xlsx",
        )

    failed_call = conn.fetchval.await_args
    assert failed_call is not None
    assert "status = 'failed'" in failed_call.args[0]
    assert "finished_at = now()" in failed_call.args[0]
    assert failed_call.args[1] == 77
    assert failed_call.args[4] == long_error[:500]


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
    records = list(copied.kwargs["records"])
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
    load = lambda source, **_kwargs: frame
    run_import = AsyncMock(return_value="result")
    monkeypatch.setattr(importer, "load_sales_dataframe", load)
    monkeypatch.setattr(importer, "import_sales_dataframe", run_import)
    conn = FakeConnection()

    result = await importer.import_sales_file(
        conn,  # type: ignore[arg-type]
        b"excel-bytes",
        "sales.xlsx",
    )

    assert result == "result"
    run_import.assert_awaited_once_with(
        conn,
        frame,
        filename="sales.xlsx",
        source_sha256=importer.sha256(b"excel-bytes").hexdigest(),
        cutoff_date=None,
        stage_only=False,
        requested_by_sub="direct-execution",
        override_reason=None,
        source_artifact_required=False,
        source_artifact_path=None,
        source_artifact_bytes=None,
        parser_resource_stats={},
    )


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
