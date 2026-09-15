"""Startup reconciles only exactly labeled stale sandboxes, then verifies DB."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from ai_assistant import runtime_app, runtime as runtime_module
from tests.test_ai_assistant_runtime_health import fake_runtime, request_for, turn_payload

LABELS = {"com.unihub.component": "ai-assistant", "com.unihub.runtime": "sandbox-agent"}


@pytest.fixture(autouse=True)
def guard_authority(monkeypatch: pytest.MonkeyPatch):
    verify = AsyncMock()
    monkeypatch.setattr(runtime_module, "verify_guard_authority", verify)
    monkeypatch.setattr(runtime_module, "verify_guard_database", AsyncMock())
    return verify


def container(labels: dict[str, str], state: str = "running") -> Any:
    return SimpleNamespace(labels=labels, status=state, remove=Mock())


def startup_runtime(tmp_path: Path, containers: list[Any]) -> Any:
    runtime: Any = fake_runtime(tmp_path, ready=False)
    runtime._orphans_ready = False
    runtime.slots.verify = Mock()
    runtime._verify_slots_unused = Mock()
    runtime.slots.reconcile = Mock()
    runtime.docker = SimpleNamespace(containers=SimpleNamespace(list=Mock(return_value=containers)), close=Mock())
    runtime.db_guard = SimpleNamespace(ready=False, error="not scanned", start=AsyncMock(), close=AsyncMock())

    async def verified() -> None:
        assert runtime._orphans_ready
        runtime._authority_ready = True

    async def scanned() -> None:
        assert runtime.authority_ready
        runtime.db_guard.ready = True
        runtime.db_guard.error = None

    runtime.verify_readonly_authority = AsyncMock(side_effect=verified)
    runtime.db_guard.start.side_effect = scanned
    return runtime


@pytest.mark.anyio
async def test_startup_removes_all_matching_states_and_preserves_others(tmp_path: Path) -> None:
    matching = [container(LABELS, state) for state in ("running", "exited", "created", "paused")]
    unrelated = [container({}), container({"com.unihub.component": "ai-assistant"}),
                 container({"com.unihub.runtime": "sandbox-agent"}),
                 container({**LABELS, "com.unihub.runtime": "something-else"})]
    runtime = startup_runtime(tmp_path, matching + unrelated)
    assert not runtime.ready
    await runtime.startup()
    runtime.docker.containers.list.assert_called_once_with(
        all=True, filters={"label": [f"{key}={value}" for key, value in LABELS.items()]}
    )
    for item in matching:
        item.remove.assert_called_once_with(force=True, v=True)
    for item in unrelated:
        item.remove.assert_not_called()
    assert runtime.ready
    assert (await runtime_app.health(request_for(runtime))).status_code == 200
    assert (await runtime_app.run_turn(turn_payload(), request_for(runtime))).status_code == 200
    await runtime.shutdown()
    runtime.db_guard.close.assert_awaited_once()
    runtime.docker.close.assert_called_once()
    runtime.slots.verify.assert_called_once()
    runtime._verify_slots_unused.assert_called_once()
    runtime.slots.reconcile.assert_called_once()


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["slots", "enumeration", "removal", "attached", "reconcile", "authority", "guard_authority", "guard_database"])
async def test_startup_failure_stays_unhealthy_and_never_starts_guard(tmp_path: Path, failure: str, guard_authority) -> None:
    stale = container(LABELS)
    runtime = startup_runtime(tmp_path, [stale])
    if failure == "guard_database":
        cast(Any, runtime_module.verify_guard_database).side_effect = RuntimeError("wrong database")
    elif failure == "slots":
        runtime.slots.verify.side_effect = RuntimeError("invalid slot")
    elif failure == "attached":
        runtime._verify_slots_unused.side_effect = RuntimeError("slot attached")
    elif failure == "reconcile":
        runtime.slots.reconcile.side_effect = RuntimeError("cleanup failure")
    elif failure == "guard_authority":
        guard_authority.side_effect = RuntimeError("invalid guard authority")
    elif failure == "enumeration":
        runtime.docker.containers.list.side_effect = OSError("daemon unreachable")
    elif failure == "removal":
        stale.remove.side_effect = OSError("remove rejected")
    else:
        runtime.verify_readonly_authority.side_effect = RuntimeError("invalid authority")
    with pytest.raises((OSError, RuntimeError)):
        await runtime.startup()
    assert not runtime.ready
    assert (await runtime_app.health(request_for(runtime))).status_code == 503
    with pytest.raises(HTTPException) as error:
        await runtime_app.run_turn(turn_payload(), request_for(runtime))
    assert error.value.status_code == 503
    runtime.db_guard.start.assert_not_awaited()


@pytest.mark.anyio
async def test_guard_loss_refuses_new_runs_and_health_recovers(tmp_path: Path) -> None:
    runtime = startup_runtime(tmp_path, [])
    await runtime.startup()
    active = Mock()
    runtime._active = {"existing": active}
    runtime.db_guard.ready = False
    runtime.db_guard.error = "disconnected"
    assert (await runtime_app.health(request_for(runtime))).status_code == 503
    with pytest.raises(HTTPException):
        await runtime_app.run_turn(turn_payload(), request_for(runtime))
    assert runtime._active == {"existing": active}
    assert not active.mock_calls
    runtime.db_guard.ready = True
    runtime.db_guard.error = None
    assert (await runtime_app.health(request_for(runtime))).status_code == 200


@pytest.mark.anyio
async def test_startup_preflight_order(tmp_path: Path, guard_authority) -> None:
    runtime = startup_runtime(tmp_path, [])
    calls = Mock()
    calls.attach_mock(runtime.slots.verify, "verify_slots")
    calls.attach_mock(runtime.docker.containers.list, "remove_stale")
    calls.attach_mock(runtime._verify_slots_unused, "verify_unused")
    calls.attach_mock(runtime.slots.reconcile, "reconcile_slots")
    calls.attach_mock(runtime.verify_readonly_authority, "readonly")
    calls.attach_mock(guard_authority, "guard_authority")
    calls.attach_mock(cast(Any, runtime_module.verify_guard_database), "guard_database")
    calls.attach_mock(runtime.db_guard.start, "start_guard")
    await runtime.startup()
    assert [call[0] for call in calls.mock_calls] == [
        "verify_slots", "remove_stale", "verify_unused", "reconcile_slots",
        "readonly", "guard_authority", "guard_database", "start_guard",
    ]
    guard_authority.assert_awaited_once_with(runtime.settings.guard_dsn)
