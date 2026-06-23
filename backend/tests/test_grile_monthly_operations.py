from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest

import services.grile_monthly as grile_monthly
from db.connection import close_db_pool, get_pool
from services.grile_monthly import (
    GrileMonthlyRetryBlockedError,
    StoreEntry,
    finish_monthly_operation,
    reserve_monthly_operation,
    reset_month,
)


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("UNIHUB_TEST_DATABASE") != "1",
        reason="Requires the explicitly isolated PostgreSQL test database",
    ),
]


async def _cleanup(month: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM grile_monthly_operations WHERE closing_month = $1",
            month,
        )


async def test_monthly_operation_reservation_serializes_same_month() -> None:
    pool = await get_pool()
    month = "2099-05"
    await _cleanup(month)

    try:
        reservations = await asyncio.gather(
            reserve_monthly_operation(
                pool,
                op="finalize",
                month=month,
                only=None,
                dry_run=False,
                triggered_by_email="first@example.com",
            ),
            reserve_monthly_operation(
                pool,
                op="archive",
                month=month,
                only=None,
                dry_run=False,
                triggered_by_email="second@example.com",
            ),
        )

        assert sorted(item.status for item in reservations) == ["already_running", "enqueued"]
        active = next(item for item in reservations if item.status == "enqueued")

        await finish_monthly_operation(
            pool,
            active.operation_id,
            result={
                "op": "finalize",
                "month_label": "Mai 2099",
                "status": "success",
                "output": "",
                "exit_code": 0,
            },
        )

        next_reservation = await reserve_monthly_operation(
            pool,
            op="archive",
            month=month,
            only=None,
            dry_run=False,
            triggered_by_email="third@example.com",
        )
        assert next_reservation.status == "enqueued"
        assert next_reservation.operation_id != active.operation_id
    finally:
        await _cleanup(month)
        await close_db_pool()


async def test_live_reset_retry_blocks_after_uncertain_stale_checkpoint() -> None:
    pool = await get_pool()
    month = "2099-06"
    await _cleanup(month)

    try:
        async with pool.acquire() as conn:
            operation_id = await conn.fetchval(
                """
                INSERT INTO grile_monthly_operations (
                    op, closing_month, dry_run, status, heartbeat_at, created_at
                )
                VALUES (
                    'reset', $1, false, 'running',
                    now() - interval '3 hours',
                    now() - interval '3 hours'
                )
                RETURNING id
                """,
                month,
            )
            await conn.execute(
                """
                INSERT INTO grile_monthly_reset_items (
                    operation_id, closing_month, next_month, site_code, sheet_id,
                    company, store, status
                )
                VALUES ($1, $2, '2099-07', 'SITE01', 'sheet-1', 'Mobiup', 'Store 1', 'running')
                """,
                operation_id,
                month,
            )

        with pytest.raises(GrileMonthlyRetryBlockedError, match="uncertain"):
            await reserve_monthly_operation(
                pool,
                op="reset",
                month=month,
                only=None,
                dry_run=False,
                triggered_by_email="admin@example.com",
            )

        async with pool.acquire() as conn:
            statuses = await conn.fetch(
                """
                SELECT o.status AS op_status, i.status AS item_status
                FROM grile_monthly_operations o
                JOIN grile_monthly_reset_items i ON i.operation_id = o.id
                WHERE o.closing_month = $1
                """,
                month,
            )
        assert [(row["op_status"], row["item_status"]) for row in statuses] == [
            ("failed", "uncertain")
        ]
    finally:
        await _cleanup(month)
        await close_db_pool()


async def test_live_reset_checkpoint_skips_already_completed_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = await get_pool()
    month = "2099-07"
    await _cleanup(month)
    calls: list[tuple[str, dict[str, Any]]] = []
    entries = [
        StoreEntry("Mobiup", "Store 1", "sheet-1", "SITE01", "Manager"),
        StoreEntry("Mobiup", "Store 2", "sheet-2", "SITE02", "Manager"),
    ]

    async def load_entries(_: Any, only: str | None = None) -> list[StoreEntry]:
        return entries

    class FakeRequest:
        def execute(self) -> dict[str, Any]:
            return {}

    class FakeValues:
        def batchClear(self, *, spreadsheetId: str, body: dict[str, Any]) -> FakeRequest:  # noqa: N802
            calls.append((spreadsheetId, body))
            return FakeRequest()

    class FakeSpreadsheets:
        def values(self) -> FakeValues:
            return FakeValues()

    class FakeSheets:
        def spreadsheets(self) -> FakeSpreadsheets:
            return FakeSpreadsheets()

    monkeypatch.setattr(grile_monthly, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(grile_monthly, "load_entries", load_entries)
    monkeypatch.setattr(grile_monthly, "build_google_services", lambda: (FakeSheets(), None))
    monkeypatch.setattr(grile_monthly, "assert_final_export_exists", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(grile_monthly, "assert_archive_complete", lambda *_args, **_kwargs: None)

    try:
        async with pool.acquire() as conn:
            first_operation_id = await conn.fetchval(
                """
                INSERT INTO grile_monthly_operations (op, closing_month, dry_run, status)
                VALUES ('reset', $1, false, 'running')
                RETURNING id
                """,
                month,
            )

        await reset_month(
            pool,
            closing_month="Iulie 2099",
            next_month="August 2099",
            dry_run=False,
            operation_id=first_operation_id,
            closing_month_key=month,
            next_month_key="2099-08",
        )
        assert [call[0] for call in calls] == ["sheet-1", "sheet-2"]

        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE grile_monthly_operations
                SET status = 'completed', finished_at = now()
                WHERE id = $1
                """,
                first_operation_id,
            )
            second_operation_id = await conn.fetchval(
                """
                INSERT INTO grile_monthly_operations (op, closing_month, dry_run, status)
                VALUES ('reset', $1, false, 'running')
                RETURNING id
                """,
                month,
            )

        await reset_month(
            pool,
            closing_month="Iulie 2099",
            next_month="August 2099",
            dry_run=False,
            operation_id=second_operation_id,
            closing_month_key=month,
            next_month_key="2099-08",
        )
        assert [call[0] for call in calls] == ["sheet-1", "sheet-2"]

        async with pool.acquire() as conn:
            statuses = await conn.fetch(
                """
                SELECT operation_id, site_code, status
                FROM grile_monthly_reset_items
                WHERE closing_month = $1
                ORDER BY operation_id, site_code
                """,
                month,
            )
        assert [row["status"] for row in statuses] == [
            "completed",
            "completed",
            "skipped",
            "skipped",
        ]
    finally:
        await _cleanup(month)
        await close_db_pool()
