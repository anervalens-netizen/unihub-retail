from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from ai_assistant.run_state_machine import ActiveRun
from ai_assistant.runtime import AiSandboxRuntime
from ai_assistant.settings import AiAssistantSettings
from ai_assistant.storage_slots import StorageSlots
from schemas.ai_assistant import RuntimeSteerRequest


class FakeResult:
    def __init__(self) -> None:
        self.cancel_modes: list[str] = []

    def cancel(self, mode: str = "immediate") -> None:
        self.cancel_modes.append(mode)


def bare_runtime(tmp_path: Path) -> AiSandboxRuntime:
    runtime = object.__new__(AiSandboxRuntime)
    runtime.settings = AiAssistantSettings(  # type: ignore[assignment]
        model="gpt-5.6-luna",
        runtime_url="http://127.0.0.1:9911",
        storage_root=tmp_path,
        snapshot_root=tmp_path,
        knowledge_root=tmp_path,
        sandbox_image="unihub-retail-sandbox:test",
        max_artifact_bytes=1024 * 1024,
        setup_timeout_seconds=30,
    )
    runtime.slots = StorageSlots(tmp_path / "slots", tmp_path / "images")  # type: ignore[assignment]
    runtime.slots.available.update({0, 1})
    runtime._active = {}  # type: ignore[attr-defined]
    runtime._lock = asyncio.Lock()  # type: ignore[attr-defined]
    return runtime


@pytest.mark.anyio
async def test_only_one_run_can_reserve_a_conversation(tmp_path: Path) -> None:
    runtime = bare_runtime(tmp_path)
    conversation_id = uuid4()

    first, second = await asyncio.gather(
        runtime._reserve(conversation_id, "owner-a"),
        runtime._reserve(conversation_id, "owner-a"),
    )

    assert (first is None) != (second is None)
    active = first or second
    assert active is not None
    assert active.owner_subject == "owner-a"
    assert runtime._active[conversation_id] is active


@pytest.mark.anyio
async def test_steers_are_sorted_by_durable_message_order(tmp_path: Path) -> None:
    runtime = bare_runtime(tmp_path)
    conversation_id = uuid4()
    result = FakeResult()
    active = ActiveRun(phase="running", result=result)
    runtime._active[conversation_id] = active

    await runtime.steer(
        conversation_id,
        RuntimeSteerRequest(text="second", order_key=2),
    )
    await runtime.steer(
        conversation_id,
        RuntimeSteerRequest(text="first", order_key=1),
    )

    assert [item.order_key for item in active.pending_steers] == [1, 2]
    assert result.cancel_modes == ["after_turn", "after_turn"]


@pytest.mark.anyio
async def test_stop_cancels_current_result_immediately(tmp_path: Path) -> None:
    runtime = bare_runtime(tmp_path)
    conversation_id = uuid4()
    result = FakeResult()
    active = ActiveRun(phase="running", result=result)
    runtime._active[conversation_id] = active

    await runtime.stop(conversation_id)

    assert active.stop_requested is True
    assert active.phase == "stopping"
    assert result.cancel_modes == ["immediate"]


@pytest.mark.anyio
async def test_stop_during_setup_cancels_reserved_owner_task(tmp_path: Path) -> None:
    runtime = bare_runtime(tmp_path)
    conversation_id = uuid4()
    reserved = asyncio.Event()

    async def owner() -> None:
        active = await runtime._reserve(conversation_id, "owner-a")
        assert active is not None
        reserved.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(owner())
    await reserved.wait()
    await runtime.stop(conversation_id)
    with pytest.raises(asyncio.CancelledError):
        await task

    assert runtime._active[conversation_id].stop_requested is True


@pytest.mark.anyio
async def test_stopped_run_cannot_install_a_resumed_result(tmp_path: Path) -> None:
    runtime = bare_runtime(tmp_path)
    conversation_id = uuid4()
    active = ActiveRun(phase="steering", stop_requested=True)
    runtime._active[conversation_id] = active
    replacement = FakeResult()

    installed = await runtime._install_result(conversation_id, active, replacement)

    assert installed is False
    assert replacement.cancel_modes == ["immediate"]
    assert active.result is None
