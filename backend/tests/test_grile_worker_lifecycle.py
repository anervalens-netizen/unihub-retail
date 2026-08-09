from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import repositories.grile as grile_repository
import routers.grile as grile_router
import services.grile as grile_service
import services.grile_agent_targets as target_service
from services.grile_queries import GrileQueryService
import worker
from services.grile_agent_targets import AgentTargetsState


def _patch_read_only_target_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    state = AgentTargetsState(sha256="a" * 64, row_count=2)
    monkeypatch.setattr(
        target_service,
        "read_agent_targets_state",
        AsyncMock(return_value=state),
    )
    monkeypatch.setattr(
        target_service,
        "sync_agent_targets_from_grile",
        AsyncMock(return_value=SimpleNamespace(as_dict=lambda: {"apply": False})),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_reason"),
    [
        (RuntimeError("synthetic failure"), "grile_run_worker_failed"),
        (TimeoutError("synthetic timeout"), "grile_run_worker_timeout"),
    ],
)
async def test_grile_worker_terminalizes_exception_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_reason: str,
) -> None:
    _patch_read_only_target_boundary(monkeypatch)
    monkeypatch.setattr(
        grile_service,
        "run_grile_check",
        AsyncMock(side_effect=failure),
    )
    repo = SimpleNamespace(fail_run=AsyncMock(return_value=True))
    monkeypatch.setattr(grile_repository, "GrileRepository", lambda _pool: repo)

    with pytest.raises(type(failure)):
        await worker.grile_check_background(
            {"db_pool": object()},
            "2098-09",
            run_id=41,
        )

    repo.fail_run.assert_awaited_once_with(41, error_message=expected_reason)


@pytest.mark.asyncio
async def test_grile_worker_terminalizes_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_read_only_target_boundary(monkeypatch)
    started = asyncio.Event()

    async def never_finishes(*_args: object, **_kwargs: object) -> int:
        started.set()
        await asyncio.Event().wait()
        return 42

    monkeypatch.setattr(grile_service, "run_grile_check", never_finishes)
    repo = SimpleNamespace(fail_run=AsyncMock(return_value=True))
    monkeypatch.setattr(grile_repository, "GrileRepository", lambda _pool: repo)
    task = asyncio.create_task(
        worker.grile_check_background(
            {"db_pool": object()},
            "2098-09",
            run_id=42,
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    repo.fail_run.assert_awaited_once_with(
        42,
        error_message="grile_run_worker_cancelled",
    )


@pytest.mark.asyncio
async def test_run_status_reconciles_stale_run_before_exposing_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    latest = {
        "id": 77,
        "run_month": "2098-09",
        "source": "manual",
        "source_snapshot_id": None,
        "status": "running",
        "progress_current": 4,
        "progress_total": 8,
        "ok_count": 0,
        "problem_count": 0,
        "error_count": 0,
        "duration_ms": None,
        "error_message": None,
        "started_at": None,
        "heartbeat_at": None,
        "finished_at": None,
        "created_at": None,
    }

    class Repository:
        async def reconcile_stale_runs(self, *, run_month: str) -> list[int]:
            events.append(f"reconcile:{run_month}")
            latest["status"] = "failed"
            latest["error_message"] = "grile_run_lease_expired"
            return [77]

        async def get_latest_run(self, month: str) -> dict[str, object]:
            events.append(f"read:{month}")
            return latest

    service = object.__new__(GrileQueryService)
    service.pool = object()  # type: ignore[assignment]
    service.repo = Repository()  # type: ignore[assignment]
    monkeypatch.setattr(service, "resolve_month", AsyncMock(return_value="2098-09"))

    payload = await service.run_status("2098-09")

    assert events == ["reconcile:2098-09", "read:2098-09"]
    assert payload["run"]["status"] == "failed"
    assert payload["run"]["active"] is False
