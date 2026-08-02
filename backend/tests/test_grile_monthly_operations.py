from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

import services.grile_monthly as grile_monthly
from db.connection import close_db_pool, get_pool
from repositories.grile_monthly_operations import (
    approve_manifest,
    mark_cancelled_uncertain,
    finish_reset_success,
    persist_manifest_result,
)
from services.grile_monthly import (
    GrileMonthlyRetryBlockedError,
    StoreEntry,
    fail_monthly_operation,
    finish_monthly_operation,
    finish_reset_item,
    ensure_reset_items,
    mark_reset_item_running,
    record_reset_item_rollback,
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
                requested_by_sub="subject-first",
            ),
            reserve_monthly_operation(
                pool,
                op="archive",
                month=month,
                only=None,
                dry_run=False,
                requested_by_sub="subject-second",
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
            requested_by_sub="subject-third",
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
                requested_by_sub="subject-admin",
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
            requested_by_sub="subject-admin",
        )

        assert reservation.status == "already_completed"
        assert reservation.operation_id == operation_id
        assert reservation.job_id == "job-completed"
    finally:
        await _cleanup(month)
        await close_db_pool()


async def test_reset_checkpoint_claim_and_finish_are_compare_and_set() -> None:
    pool = await get_pool()
    month = "2099-09"
    await _cleanup(month)

    try:
        async with pool.acquire() as conn:
            operation_id = await conn.fetchval(
                """
                INSERT INTO grile_monthly_operations (op, closing_month, dry_run, status)
                VALUES ('reset', $1, false, 'running')
                RETURNING id
                """,
                month,
            )

        await ensure_reset_items(
            pool,
            operation_id=operation_id,
            closing_month_key=month,
            next_month_key="2099-10",
            entries=[StoreEntry("Mobiup", "Store 1", "sheet-1", "SITE01", "Manager")],
        )

        claims = await asyncio.gather(
            mark_reset_item_running(pool, operation_id=operation_id, site_code="SITE01"),
            mark_reset_item_running(pool, operation_id=operation_id, site_code="SITE01"),
        )
        assert sorted(claims) == [False, True]

        assert await finish_reset_item(
            pool,
            operation_id=operation_id,
            site_code="SITE01",
            status="completed",
        ) is True
        assert await finish_reset_item(
            pool,
            operation_id=operation_id,
            site_code="SITE01",
            status="error",
            error_message="late worker",
        ) is False

        async with pool.acquire() as conn:
            item = await conn.fetchrow(
                """
                SELECT status, error_message
                FROM grile_monthly_reset_items
                WHERE operation_id = $1 AND site_code = 'SITE01'
                """,
                operation_id,
            )
        assert dict(item) == {"status": "completed", "error_message": None}
    finally:
        await _cleanup(month)
        await close_db_pool()


async def test_failed_reset_rollback_is_uncertain_and_blocks_retry() -> None:
    pool = await get_pool()
    month = "2099-10"
    await _cleanup(month)

    try:
        async with pool.acquire() as conn:
            operation_id = await conn.fetchval(
                """
                INSERT INTO grile_monthly_operations (op, closing_month, dry_run, status)
                VALUES ('reset', $1, false, 'running')
                RETURNING id
                """,
                month,
            )

        await ensure_reset_items(
            pool,
            operation_id=operation_id,
            closing_month_key=month,
            next_month_key="2099-11",
            entries=[StoreEntry("Mobiup", "Store 1", "sheet-1", "SITE01", "Manager")],
        )
        assert await mark_reset_item_running(
            pool,
            operation_id=operation_id,
            site_code="SITE01",
        )
        assert await record_reset_item_rollback(
            pool,
            operation_id=operation_id,
            site_code="SITE01",
            restored=False,
            error_message="reset_rollback_failed",
        )
        await fail_monthly_operation(
            pool,
            operation_id,
            error_message="Reset failed",
        )

        with pytest.raises(GrileMonthlyRetryBlockedError, match="uncertain"):
            await reserve_monthly_operation(
                pool,
                op="reset",
                month=month,
                only=None,
                dry_run=False,
                requested_by_sub="subject-admin",
                approved_manifest_id=123,
            )

        async with pool.acquire() as conn:
            item = await conn.fetchrow(
                """
                SELECT status, rollback_status
                FROM grile_monthly_reset_items
                WHERE operation_id = $1 AND site_code = 'SITE01'
                """,
                operation_id,
            )
        assert dict(item) == {"status": "uncertain", "rollback_status": "failed"}
    finally:
        await _cleanup(month)
        await close_db_pool()


async def test_live_reset_reservation_requires_and_links_approved_manifest() -> None:
    pool = await get_pool()
    month = "2099-07"
    await _cleanup(month)
    try:
        with pytest.raises(grile_monthly.GrileMonthlyRetryBlockedError, match="manifest"):
            await reserve_monthly_operation(
                pool,
                op="reset",
                month=month,
                only=None,
                dry_run=False,
                requested_by_sub="reset-subject",
            )

        async with pool.acquire() as conn:
            archive_operation_id = await conn.fetchval(
                """
                INSERT INTO grile_monthly_operations (
                    op, closing_month, dry_run, status, requested_by_sub
                )
                VALUES ('archive', $1, false, 'completed', 'archive-subject')
                RETURNING id
                """,
                month,
            )
            approved_manifest_id = await conn.fetchval(
                """
                INSERT INTO grile_monthly_manifests (
                    operation_id, closing_month, operation, status,
                    expected_store_count, processed_store_count,
                    expected_agent_count, processed_agent_count, error_count,
                    requested_by_sub, approved_by_sub, approved_at
                )
                VALUES ($1, $2, 'archive', 'approved', 2, 2, 3, 3, 0,
                        'archive-subject', 'approval-subject', now())
                RETURNING id
                """,
                archive_operation_id,
                month,
            )

        reservation = await reserve_monthly_operation(
            pool,
            op="reset",
            month=month,
            only=None,
            dry_run=False,
            requested_by_sub="reset-subject",
            approved_manifest_id=approved_manifest_id,
        )
        assert reservation.status == "enqueued"

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT o.requested_by_sub, o.approved_manifest_id,
                       m.status AS manifest_status, m.requested_by_sub AS manifest_subject
                FROM grile_monthly_operations o
                JOIN grile_monthly_manifests m ON m.operation_id = o.id
                WHERE o.id = $1
                """,
                reservation.operation_id,
            )
        assert dict(row) == {
            "requested_by_sub": "reset-subject",
            "approved_manifest_id": approved_manifest_id,
            "manifest_status": "building",
            "manifest_subject": "reset-subject",
        }
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
        async with conn.transaction():
            operation_id = int(
                await conn.fetchval(
                    """
                    INSERT INTO grile_monthly_operations
                        (op, closing_month, dry_run, status, result, error_message,
                         finished_at, heartbeat_at, requested_by_sub)
                    VALUES
                        ('finalize', $1, true, $2, $3::jsonb, $4,
                         CASE WHEN $2 IN ('completed', 'failed') THEN now() ELSE NULL END,
                         now(), 'synthetic-operation-subject')
                    RETURNING id
                    """,
                    month,
                    status,
                    None if result is None else json.dumps(result),
                    error_message,
                )
            )
            await conn.execute(
                """
                INSERT INTO grile_monthly_manifests (
                    operation_id, closing_month, operation, status, requested_by_sub
                )
                VALUES ($1, $2, 'finalize', 'building', 'synthetic-operation-subject')
                """,
                operation_id,
                month,
            )
        return operation_id


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


async def test_legacy_queued_operation_without_subject_or_manifest_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    month = "2098-09"
    await _cleanup(month)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            operation_id = int(
                await conn.fetchval(
                    """
                    INSERT INTO grile_monthly_operations (
                        op, closing_month, dry_run, status, heartbeat_at
                    )
                    VALUES ('finalize', $1, false, 'queued', now())
                    RETURNING id
                    """,
                    month,
                )
            )

        monkeypatch.setattr("db.connection.get_pool", AsyncMock(return_value=pool))
        execute = AsyncMock()
        heartbeat = AsyncMock()
        monkeypatch.setattr(grile_monthly, "_finalize_month_execution", execute)
        monkeypatch.setattr(grile_monthly, "heartbeat_monthly_operation", heartbeat)

        result = await grile_monthly.run_monthly_op(operation_id=operation_id)

        assert result["status"] == "failed"
        assert result["operation_status"] == "failed"
        assert result["exit_code"] == -1
        assert result["idempotent_replay"] is True
        execute.assert_not_awaited()
        heartbeat.assert_not_awaited()
        async with pool.acquire() as conn:
            operation = await conn.fetchrow(
                """
                SELECT status, error_message, finished_at
                FROM grile_monthly_operations
                WHERE id = $1
                """,
                operation_id,
            )
            manifest_count = await conn.fetchval(
                "SELECT count(*) FROM grile_monthly_manifests WHERE operation_id = $1",
                operation_id,
            )
        assert operation["status"] == "failed"
        assert operation["error_message"] == "legacy_operation_missing_identity_or_manifest"
        assert operation["finished_at"] is not None
        assert manifest_count == 0
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
    execution = grile_monthly.MonthlyExecution(Path("unused"), {"status": "verified"})
    implementations = {
        "finalize": "_finalize_month_execution",
        "archive": "_archive_month_execution",
        "reset": "_reset_month_execution",
    }
    for name in implementations.values():
        monkeypatch.setattr(grile_monthly, name, AsyncMock(return_value=execution))
    result = await grile_monthly.run_monthly_op(op=op, month="2099-03", dry_run=True)
    assert result["status"] == "success"
    getattr(grile_monthly, implementations[op]).assert_awaited_once()


async def test_manifest_approval_and_reset_consumption_are_persistent_and_atomic() -> None:
    pool = await get_pool()
    month = "2099-10"
    await _cleanup(month)
    try:
        archive_reservation = await reserve_monthly_operation(
            pool,
            op="archive",
            month=month,
            only=None,
            dry_run=False,
            requested_by_sub="request-subject",
        )
        archive_start = await start_monthly_operation(pool, archive_reservation.operation_id)
        assert archive_start.status == "started"
        archive_manifest = grile_monthly.base_manifest(
            month=month,
            operation="archive",
            requested_by_sub="request-subject",
            expected_stores=2,
            expected_agents=3,
            processed_stores=2,
            processed_agents=3,
            control_totals={"salary_components": "1.00"},
            artifacts=[
                {
                    "kind": "archive_zip",
                    "path": "synthetic/archive.zip",
                    "bytes": 1,
                    "sha256": "a" * 64,
                }
            ],
        )
        persisted_archive = await persist_manifest_result(
            pool,
            operation_id=archive_reservation.operation_id,
            manifest=archive_manifest,
        )
        assert persisted_archive["requested_by_sub"] == "request-subject"
        assert await finish_monthly_operation(
            pool,
            archive_reservation.operation_id,
            result={"status": "success"},
        )

        approved_payload = dict(archive_manifest)
        approved_payload["status"] = "approved"
        approved_payload["approved_by_sub"] = "approval-subject"
        approved_payload["approved_at"] = grile_monthly.utc_now()
        approved_payload = grile_monthly.finalize_manifest(approved_payload)
        approved = await approve_manifest(
            pool,
            manifest_id=int(persisted_archive["id"]),
            expected_sha256=archive_manifest["manifest_sha256"],
            approved_by_sub="approval-subject",
            approved_manifest=approved_payload,
        )
        assert approved is not None
        assert approved["status"] == "approved"
        assert approved["approved_by_sub"] == "approval-subject"

        reset_reservation = await reserve_monthly_operation(
            pool,
            op="reset",
            month=month,
            only=None,
            dry_run=False,
            requested_by_sub="reset-subject",
            approved_manifest_id=int(persisted_archive["id"]),
        )
        reset_start = await start_monthly_operation(pool, reset_reservation.operation_id)
        assert reset_start.status == "started"
        reset_manifest = grile_monthly.base_manifest(
            month=month,
            operation="reset",
            requested_by_sub="reset-subject",
            expected_stores=2,
            expected_agents=3,
            processed_stores=2,
            processed_agents=3,
            control_totals={"salary_components": "1.00"},
            artifacts=[
                {
                    "kind": "reset_report",
                    "path": "synthetic/reset.json",
                    "bytes": 1,
                    "sha256": "b" * 64,
                }
            ],
        )
        consumed_payload = dict(approved_payload)
        consumed_payload["status"] = "consumed"
        consumed_payload["consumed_at"] = grile_monthly.utc_now()
        consumed_payload = grile_monthly.finalize_manifest(consumed_payload)
        with pytest.raises(RuntimeError, match="consumption lease"):
            await finish_reset_success(
                pool,
                reset_reservation.operation_id,
                result={"status": "success"},
                reset_manifest=reset_manifest,
                manifest_id=int(persisted_archive["id"]),
                expected_manifest_sha256="0" * 64,
                consumed_manifest=consumed_payload,
            )
        async with pool.acquire() as conn:
            state_after_failed_commit = await conn.fetchrow(
                """
                SELECT o.status AS operation_status, m.status AS manifest_status
                FROM grile_monthly_operations o
                JOIN grile_monthly_manifests m ON m.operation_id = o.id
                WHERE o.id = $1
                """,
                reset_reservation.operation_id,
            )
        assert dict(state_after_failed_commit) == {
            "operation_status": "running",
            "manifest_status": "building",
        }
        committed_reset = await finish_reset_success(
            pool,
            reset_reservation.operation_id,
            result={"status": "success"},
            reset_manifest=reset_manifest,
            manifest_id=int(persisted_archive["id"]),
            expected_manifest_sha256=approved_payload["manifest_sha256"],
            consumed_manifest=consumed_payload,
        )
        assert committed_reset["status"] == "verified"

        async with pool.acquire() as conn:
            state = await conn.fetchrow(
                """
                SELECT o.status AS operation_status,
                       approved.status AS approved_status,
                       approved.manifest->>'status' AS approved_json_status,
                       reset_manifest.status AS reset_manifest_status
                FROM grile_monthly_operations o
                JOIN grile_monthly_manifests approved
                  ON approved.id = o.approved_manifest_id
                JOIN grile_monthly_manifests reset_manifest
                  ON reset_manifest.operation_id = o.id
                WHERE o.id = $1
                """,
                reset_reservation.operation_id,
            )
        assert dict(state) == {
            "operation_status": "completed",
            "approved_status": "consumed",
            "approved_json_status": "consumed",
            "reset_manifest_status": "verified",
        }
    finally:
        await _cleanup(month)
        await close_db_pool()


async def test_cancelled_operation_fences_completed_clear_as_uncertain() -> None:
    month = "2098-11"
    pool = await get_pool()
    try:
        await _cleanup(month)
        async with pool.acquire() as conn:
            operation_id = await conn.fetchval(
                """
                INSERT INTO grile_monthly_operations (
                    op, closing_month, dry_run, status, requested_by_sub,
                    started_at, heartbeat_at
                ) VALUES ('reset', $1, false, 'running', 'test:cancel', now(), now())
                RETURNING id
                """,
                month,
            )
            await conn.execute(
                """
                INSERT INTO grile_monthly_reset_items (
                    operation_id, closing_month, next_month, site_code,
                    sheet_id, company, store, status, ranges, completed_at
                ) VALUES ($1, $2, '2098-12', 'CANCEL01', 'sheet-1',
                          'Mobiup', 'Cancel Store', 'completed', '[]'::jsonb, now())
                """,
                operation_id,
                month,
            )

        assert await mark_cancelled_uncertain(
            pool,
            int(operation_id),
            error_message="cancelled before confirmation",
        )

        async with pool.acquire() as conn:
            state = await conn.fetchrow(
                """
                SELECT o.status AS operation_status,
                       i.status AS item_status,
                       i.rollback_status,
                       i.error_message
                FROM grile_monthly_operations o
                JOIN grile_monthly_reset_items i ON i.operation_id = o.id
                WHERE o.id = $1
                """,
                operation_id,
            )
        assert dict(state) == {
            "operation_status": "failed",
            "item_status": "uncertain",
            "rollback_status": "failed",
            "error_message": "cancelled before confirmation",
        }
    finally:
        await _cleanup(month)
        await close_db_pool()
