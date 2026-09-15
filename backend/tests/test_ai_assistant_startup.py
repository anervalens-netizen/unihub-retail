"""Startup reconciles only exactly labeled stale sandboxes, then verifies DB."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from ai_assistant import runtime_app
from tests.test_ai_assistant_runtime_health import fake_runtime, request_for, turn_payload

LABELS = {"com.unihub.component": "ai-assistant", "com.unihub.runtime": "sandbox-agent"}


def container(labels: dict[str, str], state: str = "running") -> Any:
    return SimpleNamespace(labels=labels, status=state, remove=Mock())


def startup_runtime(tmp_path: Path, containers: list[Any]) -> Any:
    runtime: Any = fake_runtime(tmp_path, ready=False)
    runtime._orphans_ready = False
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


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["enumeration", "removal", "authority"])
async def test_startup_failure_stays_unhealthy_and_never_starts_guard(tmp_path: Path, failure: str) -> None:
    stale = container(LABELS)
    runtime = startup_runtime(tmp_path, [stale])
    if failure == "enumeration":
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
