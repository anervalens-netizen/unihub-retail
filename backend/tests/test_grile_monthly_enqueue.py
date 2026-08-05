from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import db.connection as db_connection
import services.grile_monthly as grile_monthly
import services.jobs as jobs
import worker
from services.grile_monthly import MonthlyOperationReservation


pytestmark = pytest.mark.asyncio


@dataclass
class FakeJob:
    job_id: str


class FakeQueue:
    def __init__(
        self,
        events: list[str],
        *,
        result: FakeJob | None = None,
        error: Exception | None = None,
    ) -> None:
        self.events = events
        self.result = result
        self.error = error
        self.enqueue_job = AsyncMock(side_effect=self._enqueue)

    async def _enqueue(self, *args: Any, **kwargs: Any) -> FakeJob | None:
        self.events.append("enqueue")
        if self.error is not None:
            raise self.error
        return self.result


def _patch_reservation(
    monkeypatch: pytest.MonkeyPatch,
    *,
    events: list[str],
    reservation: MonthlyOperationReservation,
    attach_result: bool = True,
) -> tuple[Any, AsyncMock]:
    db_pool = object()

    async def reserve(*args: Any, **kwargs: Any) -> MonthlyOperationReservation:
        events.append("reserve")
        assert kwargs["requested_by_sub"] == "subject-1"
        return reservation

    async def attach(*args: Any, **kwargs: Any) -> bool:
        events.append("attach")
        assert kwargs["operation_id"] == reservation.operation_id
        assert kwargs["job_id"] == f"grile-monthly:{reservation.operation_id}"
        return attach_result

    fail = AsyncMock(return_value=True)
    monkeypatch.setattr(db_connection, "get_pool", AsyncMock(return_value=db_pool))
    monkeypatch.setattr(grile_monthly, "reserve_monthly_operation", reserve)
    monkeypatch.setattr(grile_monthly, "attach_monthly_operation_job", attach)
    monkeypatch.setattr(grile_monthly, "fail_queued_monthly_operation", fail)
    return db_pool, fail


async def test_h11_monthly_enqueue_persists_job_id_before_queue_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    reservation = MonthlyOperationReservation(status="enqueued", operation_id=42)
    _patch_reservation(monkeypatch, events=events, reservation=reservation)
    queue = FakeQueue(events, result=FakeJob("grile-monthly:42"))
    monkeypatch.setattr(jobs, "get_arq_pool", AsyncMock(return_value=queue))

    result = await jobs.enqueue_grile_monthly(
        op="finalize",
        month="2099-01",
        dry_run=False,
        requested_by_sub="subject-1",
    )

    assert events == ["reserve", "attach", "enqueue"]
    assert result.status == "enqueued"
    assert result.operation_id == 42
    assert result.job_id == "grile-monthly:42"
    queue.enqueue_job.assert_awaited_once()
    assert queue.enqueue_job.await_args is not None
    assert queue.enqueue_job.await_args.args == (
        "grile_monthly_background",
        42,
    )
    assert queue.enqueue_job.await_args.kwargs["_job_id"] == "grile-monthly:42"


async def test_h11_monthly_enqueue_does_not_publish_when_attachment_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    reservation = MonthlyOperationReservation(status="enqueued", operation_id=43)
    _, fail = _patch_reservation(
        monkeypatch,
        events=events,
        reservation=reservation,
        attach_result=False,
    )
    queue = FakeQueue(events, result=FakeJob("grile-monthly:43"))
    get_queue = AsyncMock(return_value=queue)
    monkeypatch.setattr(jobs, "get_arq_pool", get_queue)

    with pytest.raises(RuntimeError, match="no longer queued"):
        await jobs.enqueue_grile_monthly(
            op="archive",
            month="2099-02",
            requested_by_sub="subject-1",
        )

    assert events == ["reserve", "attach"]
    get_queue.assert_not_awaited()
    queue.enqueue_job.assert_not_awaited()
    fail.assert_not_awaited()


@pytest.mark.parametrize("publish_mode", ["none", "exception"])
async def test_h11_monthly_enqueue_handles_publish_uncertainty_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    publish_mode: str,
) -> None:
    events: list[str] = []
    reservation = MonthlyOperationReservation(status="enqueued", operation_id=44)
    db_pool, fail = _patch_reservation(
        monkeypatch,
        events=events,
        reservation=reservation,
    )
    queue = FakeQueue(
        events,
        result=None if publish_mode == "none" else FakeJob("unused"),
        error=ConnectionError("valkey unavailable") if publish_mode == "exception" else None,
    )
    monkeypatch.setattr(jobs, "get_arq_pool", AsyncMock(return_value=queue))

    if publish_mode == "exception":
        with pytest.raises(HTTPException) as exc_info:
            await jobs.enqueue_grile_monthly(
                op="reset",
                month="2099-03",
                dry_run=True,
                requested_by_sub="subject-1",
            )
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == {
            "status": "unknown",
            "job_id": "grile-monthly:44",
            "operation_id": 44,
        }
        fail.assert_not_awaited()
    else:
        with pytest.raises(RuntimeError, match="Failed to enqueue"):
            await jobs.enqueue_grile_monthly(
                op="reset",
                month="2099-03",
                dry_run=True,
                requested_by_sub="subject-1",
            )
        fail.assert_awaited_once_with(
            db_pool,
            44,
            error_message="monthly_queue_publish_failed",
        )

    assert events == ["reserve", "attach", "enqueue"]


async def test_h11_existing_monthly_reservation_bypasses_queue_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    reservation = MonthlyOperationReservation(
        status="already_running",
        operation_id=45,
        job_id="grile-monthly:45",
        operation={"status": "running"},
    )
    _, fail = _patch_reservation(
        monkeypatch,
        events=events,
        reservation=reservation,
    )
    queue = FakeQueue(events, result=FakeJob("unexpected"))
    get_queue = AsyncMock(return_value=queue)
    monkeypatch.setattr(jobs, "get_arq_pool", get_queue)

    result = await jobs.enqueue_grile_monthly(
        op="finalize",
        month="2099-04",
        requested_by_sub="subject-1",
    )

    assert events == ["reserve"]
    assert result.status == "already_running"
    assert result.job_id == "grile-monthly:45"
    get_queue.assert_not_awaited()
    queue.enqueue_job.assert_not_awaited()
    fail.assert_not_awaited()


async def test_monthly_worker_accepts_only_persisted_operation_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(grile_monthly, "run_monthly_op", run)

    result = await worker.grile_monthly_background(
        {},
        operation_id=51,
    )

    assert result == {"status": "success"}
    run.assert_awaited_once()
    assert run.await_args is not None
    assert run.await_args.kwargs["operation_id"] == 51
    assert len(run.await_args.kwargs["execution_owner_hint"]) == 32


async def test_monthly_worker_marks_unexpected_failure_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = TypeError("unexpected serialization failure")
    run = AsyncMock(side_effect=failure)
    fail = AsyncMock(return_value=True)
    db_pool = object()
    monkeypatch.setattr(grile_monthly, "run_monthly_op", run)
    monkeypatch.setattr(grile_monthly, "fail_monthly_operation", fail)
    monkeypatch.setattr(
        grile_monthly,
        "get_monthly_execution_lease",
        AsyncMock(return_value=SimpleNamespace(execution_owner="worker-owned", execution_epoch=7)),
    )

    with pytest.raises(TypeError, match="unexpected serialization"):
        await worker.grile_monthly_background(
            {"db_pool": db_pool},
            operation_id=53,
        )

    fail.assert_awaited_once_with(
        db_pool,
        53,
        error_message="monthly_operation_worker_failed",
        execution_owner="worker-owned",
        execution_epoch=7,
    )


async def test_monthly_worker_rejects_legacy_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(grile_monthly, "run_monthly_op", run)

    with pytest.raises(TypeError):
        await worker.grile_monthly_background(  # type: ignore[call-arg]
            {},
            "finalize",  # type: ignore[arg-type]
            "2099-05",
            None,
            False,
            "ignored-legacy-identity",
            "legacy-request-id",
        )

    run.assert_not_awaited()


async def test_monthly_worker_sigterm_marks_unconfirmed_reset_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = AsyncMock(side_effect=asyncio.CancelledError())
    mark_uncertain = AsyncMock(return_value=True)
    db_pool = object()
    monkeypatch.setattr(grile_monthly, "run_monthly_op", run)
    monkeypatch.setattr(
        grile_monthly,
        "mark_monthly_operation_cancelled_uncertain",
        mark_uncertain,
    )
    monkeypatch.setattr(
        grile_monthly,
        "get_monthly_execution_lease",
        AsyncMock(return_value=SimpleNamespace(execution_owner="worker-owned", execution_epoch=8)),
    )

    with pytest.raises(asyncio.CancelledError):
        await worker.grile_monthly_background(
            {"db_pool": db_pool},
            operation_id=54,
        )

    mark_uncertain.assert_awaited_once_with(
        db_pool,
        54,
        error_message="monthly_operation_cancelled_uncertain",
        execution_owner="worker-owned",
        execution_epoch=8,
    )
