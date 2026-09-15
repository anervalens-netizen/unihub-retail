"""Global storage admission and quarantine lifecycle, without host mounts."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from ai_assistant import runtime as runtime_module
from tests.test_ai_assistant_runtime_race import (
    FakeResult, FakeSandbox, build_runtime, collect, event_types, owner_settings, turn_request,
)


@pytest.mark.anyio
async def test_global_two_slot_reservation_is_atomic_across_distinct_owners(tmp_path, monkeypatch):
    runtime, client, runner = build_runtime(tmp_path, [], monkeypatch, settings=owner_settings(tmp_path, 16))
    conversations = [uuid4() for _ in range(16)]
    runs = await asyncio.gather(*(
        runtime._reserve(conversation, f"owner-{index}")
        for index, conversation in enumerate(conversations)
    ))
    accepted = [(conversation, active) for conversation, active in zip(conversations, runs) if active]
    assert len(accepted) == 2
    assert {active.slot.index for _, active in accepted} == {0, 1}
    assert len(runtime._active) == 2
    assert runtime.slots.available == set()
    assert client.created == runner.calls == []
    for conversation, active in accepted:
        await runtime._cleanup_sandbox(conversation, active)
        await runtime._release(conversation, active)
    assert runtime.slots.available == {0, 1}
    assert runtime.slots.unavailable == set()


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["close", "delete", "attached", "clean"])
async def test_cleanup_failure_quarantines_slots_and_never_publishes_complete(tmp_path, monkeypatch, failure):
    runtime, client, runner = build_runtime(
        tmp_path, [FakeResult(label="a", deltas=[]), FakeResult(label="b", deltas=[])], monkeypatch,
    )
    error = RuntimeError("forced cleanup failure")
    if failure == "close":
        monkeypatch.setattr(FakeSandbox, "aclose", AsyncMock(side_effect=error))
    elif failure == "delete":
        monkeypatch.setattr(client, "delete", AsyncMock(side_effect=error))
    elif failure == "attached":
        monkeypatch.setattr(runtime, "_verify_slots_unused", Mock(side_effect=error))
    else:
        monkeypatch.setattr(runtime_module, "clean_slot", Mock(side_effect=error))
    used = []
    original_create = client.create

    async def create(**kwargs):
        used.append(kwargs["options"].slot.index)
        return await original_create(**kwargs)

    monkeypatch.setattr(client, "create", create)
    for index in range(2):
        events = await collect(runtime.stream_turn(turn_request(uuid4(), owner_subject=f"owner-{index}")))
        assert event_types(events) == ["status", "error"]
        assert runtime._active == {}
        assert runtime.slots.unavailable == set(range(index + 1))
    assert used == [0, 1]
    assert runtime.slots.available == set()
    third = await collect(runtime.stream_turn(turn_request(uuid4(), owner_subject="third-owner")))
    assert event_types(third) == ["error"]
    assert len(client.created) == len(runner.calls) == 2


@pytest.mark.anyio
async def test_successful_cleanup_precedes_complete_and_slot_reuse(tmp_path: Path, monkeypatch):
    runtime, client, _ = build_runtime(tmp_path, [FakeResult(label="a", deltas=[])], monkeypatch)
    cleaned = []
    monkeypatch.setattr(runtime_module, "clean_slot", lambda slot: cleaned.append(slot.index))
    stream = runtime.stream_turn(turn_request(uuid4()))
    async for event in stream:
        if '"complete"' in event.decode():
            assert cleaned == [0]
            assert client.deleted == client.created
            assert runtime.slots.available == {1}
    assert runtime.slots.available == {0, 1}
