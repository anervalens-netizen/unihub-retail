from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

import services.grile_monthly as grile_monthly
from db.connection import close_db_pool, get_pool
from services.grile_monthly import (
    GrileMonthlyRetryBlockedError,
    StoreEntry,
    fail_monthly_operation,
    finish_monthly_operation,
    reserve_monthly_operation,
    reset_month,
    start_monthly_operation,
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
        started = await start_monthly_operation(pool, active.operation_id)
        assert started.status == "started"

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


async def test_completed_live_reset_is_idempotent_for_same_scope() -> None:
    pool = await get_pool()
    month = "2099-08"
    await _cleanup(month)

    try:
        async with pool.acquire() as conn:
            operation_id = await conn.fetchval(
                """
                INSERT INTO grile_monthly_operations (
                    op, closing_month, only_filter, dry_run, status,
                    job_id, finished_at
                )
                VALUES (
                    'reset', $1, 'Store 1', false, 'completed',
                    'job-completed', now()
                )
                RETURNING id
                """,
                month,
            )

        reservation = await reserve_monthly_operation(
            pool,
            op="reset",
            month=month,
            only="  Store 1  ",
            dry_run=False,
            triggered_by_email="admin@example.com",
        )

        assert reservation.status == "already_completed"
        assert reservation.operation_id == operation_id
        assert reservation.job_id == "job-completed"
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


async def _insert_operation(
    month: str,
    *,
    status: str = "queued",
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return int(
            await conn.fetchval(
                """
                INSERT INTO grile_monthly_operations
                    (op, closing_month, dry_run, status, result, error_message, finished_at, heartbeat_at)
                VALUES
                    ('finalize', $1, true, $2, $3::jsonb, $4,
                     CASE WHEN $2 IN ('completed', 'failed') THEN now() ELSE NULL END,
                     now())
                RETURNING id
                """,
                month,
                status,
                None if result is None else json.dumps(result),
                error_message,
            )
        )


async def test_h11_concurrent_start_allows_exactly_one_worker() -> None:
    month = "2099-10"
    await _cleanup(month)
    pool = await get_pool()
    try:
        operation_id = await _insert_operation(month)
        first, second = await asyncio.gather(
            start_monthly_operation(pool, operation_id),
            start_monthly_operation(pool, operation_id),
        )
        assert sorted([first.status, second.status]) == ["already_running", "started"]
        async with pool.acquire() as conn:
            assert await conn.fetchval(
                "SELECT status FROM grile_monthly_operations WHERE id = $1", operation_id
            ) == "running"
    finally:
        await _cleanup(month)
        await close_db_pool()


@pytest.mark.parametrize("op", ["finalize", "archive", "reset"])
@pytest.mark.parametrize("state", ["running", "completed", "failed"])
async def test_h11_duplicate_worker_delivery_has_no_side_effects(
    op: str,
    state: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    month = f"2099-{11 if op == 'finalize' else 12:02d}"
    await _cleanup(month)
    pool = await get_pool()
    stored_result = {"op": op, "status": "success", "output": "original", "exit_code": 0}
    operation_id = await _insert_operation(
        month,
        status=state,
        result=stored_result if state == "completed" else None,
        error_message="original failure" if state == "failed" else None,
    )
    try:
        from unittest.mock import AsyncMock

        monkeypatch.setattr("db.connection.get_pool", AsyncMock(return_value=pool))
        for name in ("finalize_month", "archive_month", "reset_month", "heartbeat_monthly_operation", "finish_monthly_operation"):
            monkeypatch.setattr(grile_monthly, name, AsyncMock())

        async with pool.acquire() as conn:
            before = await conn.fetchrow(
                "SELECT status, result, error_message, finished_at, heartbeat_at FROM grile_monthly_operations WHERE id = $1",
                operation_id,
            )
        replay = await grile_monthly.run_monthly_op(
            op=op, month=month, dry_run=True, operation_id=operation_id
        )
        async with pool.acquire() as conn:
            after = await conn.fetchrow(
                "SELECT status, result, error_message, finished_at, heartbeat_at FROM grile_monthly_operations WHERE id = $1",
                operation_id,
            )

        assert dict(after) == dict(before)
        assert replay["idempotent_replay"] is True
        assert replay["operation_status"] == state
        for name in ("finalize_month", "archive_month", "reset_month", "heartbeat_monthly_operation", "finish_monthly_operation"):
            getattr(grile_monthly, name).assert_not_awaited()
    finally:
        await _cleanup(month)
        await close_db_pool()


async def test_h11_missing_operation_is_deterministic_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import AsyncMock

    pool = await get_pool()
    monkeypatch.setattr("db.connection.get_pool", AsyncMock(return_value=pool))
    for name in ("finalize_month", "archive_month", "reset_month", "heartbeat_monthly_operation", "finish_monthly_operation"):
        monkeypatch.setattr(grile_monthly, name, AsyncMock())
    result = await grile_monthly.run_monthly_op(
        op="finalize", month="2099-01", operation_id=987654321
    )
    assert result["status"] == "failed"
    assert result["operation_status"] == "not_found"
    for name in ("finalize_month", "archive_month", "reset_month", "heartbeat_monthly_operation", "finish_monthly_operation"):
        getattr(grile_monthly, name).assert_not_awaited()
    await close_db_pool()


@pytest.mark.parametrize("terminal", ["completed", "failed"])
async def test_h11_late_finish_cannot_overwrite_terminal_row(terminal: str) -> None:
    month = f"2098-{1 if terminal == 'completed' else 2:02d}"
    await _cleanup(month)
    pool = await get_pool()
    try:
        operation_id = await _insert_operation(
            month,
            status=terminal,
            result={"status": "success", "output": "kept"},
            error_message="kept error" if terminal == "failed" else None,
        )
        changed = await finish_monthly_operation(
            pool, operation_id, result={"status": "success", "output": "late"}
        )
        assert changed is False
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, result, error_message FROM grile_monthly_operations WHERE id = $1", operation_id
            )
        assert row["status"] == terminal
        persisted_result = row["result"]
        if isinstance(persisted_result, str):
            persisted_result = json.loads(persisted_result)
        assert persisted_result["output"] == "kept"
    finally:
        await _cleanup(month)
        await close_db_pool()


@pytest.mark.parametrize("source", ["queued", "running", "completed", "failed"])
async def test_h11_fail_only_transitions_nonterminal_rows(source: str) -> None:
    month_number = ["queued", "running", "completed", "failed"].index(source) + 1
    month = f"2097-{month_number:02d}"
    await _cleanup(month)
    pool = await get_pool()
    try:
        operation_id = await _insert_operation(month, status=source, error_message="kept")
        changed = await fail_monthly_operation(pool, operation_id, error_message="new error")
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, error_message FROM grile_monthly_operations WHERE id = $1", operation_id
            )
        assert changed is (source in {"queued", "running"})
        assert row["status"] == ("failed" if changed else source)
        assert row["error_message"] == ("new error" if changed else "kept")
    finally:
        await _cleanup(month)
        await close_db_pool()


@pytest.mark.parametrize("op", ["finalize", "archive", "reset"])
async def test_h11_direct_execution_without_operation_id_runs_once(
    op: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock

    pool = object()
    monkeypatch.setattr("db.connection.get_pool", AsyncMock(return_value=pool))
    for name in ("finalize_month", "archive_month", "reset_month"):
        monkeypatch.setattr(grile_monthly, name, AsyncMock())
    result = await grile_monthly.run_monthly_op(op=op, month="2099-03", dry_run=True)
    assert result["status"] == "success"
    getattr(grile_monthly, f"{op}_month").assert_awaited_once()
