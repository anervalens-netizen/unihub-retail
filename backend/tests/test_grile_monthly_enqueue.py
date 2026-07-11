from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import ANY, AsyncMock

import pytest

import db.connection as db_connection
import services.grile_monthly as grile_monthly
import services.jobs as jobs
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
    monkeypatch.setattr(grile_monthly, "fail_monthly_operation", fail)
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
        triggered_by_email="admin@example.com",
    )

    assert events == ["reserve", "attach", "enqueue"]
    assert result.status == "enqueued"
    assert result.operation_id == 42
    assert result.job_id == "grile-monthly:42"
    queue.enqueue_job.assert_awaited_once()
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
        await jobs.enqueue_grile_monthly(op="archive", month="2099-02")

    assert events == ["reserve", "attach"]
    get_queue.assert_not_awaited()
    queue.enqueue_job.assert_not_awaited()
    fail.assert_not_awaited()


@pytest.mark.parametrize("publish_mode", ["none", "exception"])
async def test_h11_monthly_enqueue_failure_transitions_queued_reservation_to_failed(
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

    with pytest.raises((RuntimeError, ConnectionError)):
        await jobs.enqueue_grile_monthly(op="reset", month="2099-03", dry_run=True)

    assert events == ["reserve", "attach", "enqueue"]
    fail.assert_awaited_once_with(
        db_pool,
        44,
        error_message="Jobul lunar Grile nu a putut fi adaugat in coada",
    )


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

    result = await jobs.enqueue_grile_monthly(op="finalize", month="2099-04")

    assert events == ["reserve"]
    assert result.status == "already_running"
    assert result.job_id == "grile-monthly:45"
    get_queue.assert_not_awaited()
    queue.enqueue_job.assert_not_awaited()
    fail.assert_not_awaited()
