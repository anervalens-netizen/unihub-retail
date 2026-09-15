"""Deterministic concurrency certification for the AI sandbox runtime state machine.

These tests drive the REAL ``AiSandboxRuntime.stream_turn`` async generator with a
fake Docker client and a fake OpenAI Agents SDK ``Runner``. They reproduce the
original production race (two simultaneous runs both passing the active check and
overwriting ``_active``) and prove the redesigned reservation/identity contract.
"""

from __future__ import annotations

import asyncio
import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from ai_assistant import runtime as runtime_module
from ai_assistant.runtime import AiSandboxRuntime
from ai_assistant.settings import AiAssistantSettings
from schemas.ai_assistant import (
    RuntimeSteerRequest,
    RuntimeTurnRequest,
    RuntimeUpload,
)


class FakeExecResult:
    def __init__(self, stdout: bytes = b"", ok: bool = True) -> None:
        self.stdout = stdout
        self._ok = ok

    def ok(self) -> bool:
        return self._ok


class FakeSandbox:
    """Minimal sandbox session surface used by ``AiSandboxRuntime``."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.started = False
        self.closed = False
        self.writes: list[str] = []
        self.files: dict[str, bytes] = {}
        self.block_on: set[str] = set()
        self.write_gate: asyncio.Event | None = None
        self.entered_block: asyncio.Event = asyncio.Event()
        self.start_gate: asyncio.Event | None = None
        self.start_entered: asyncio.Event = asyncio.Event()

    async def start(self) -> None:
        if self.start_gate is not None:
            self.start_entered.set()
            await self.start_gate.wait()
        self.started = True

    async def write(self, path: Path, stream: Any) -> None:
        relative = str(path).replace("\\", "/")
        if relative in self.block_on:
            self.entered_block.set()
            gate = self.write_gate
            if gate is not None:
                await gate.wait()
        payload = stream.read() if hasattr(stream, "read") else b""
        if not isinstance(payload, bytes):
            payload = bytes(payload)
        self.files[relative] = payload
        self.writes.append(relative)

    async def exec(self, command: str, timeout: int | None = None) -> FakeExecResult:
        return FakeExecResult()

    async def read(self, path: Path) -> io.BytesIO:
        return io.BytesIO(self.files.get(str(path), b""))

    async def aclose(self) -> None:
        self.closed = True


class FakeDockerClient:
    def __init__(self) -> None:
        self.created: list[FakeSandbox] = []
        self.deleted: list[FakeSandbox] = []
        self.delete_calls: list[FakeSandbox] = []
        self.start_gates: list[asyncio.Event | None] = []

    async def create(self, *, manifest: Any, snapshot: Any, options: Any) -> FakeSandbox:
        del manifest, snapshot, options
        sandbox = FakeSandbox(f"sandbox-{len(self.created) + 1}")
        if self.start_gates:
            sandbox.start_gate = self.start_gates.pop(0)
        self.created.append(sandbox)
        return sandbox

    async def delete(self, session: FakeSandbox) -> FakeSandbox:
        self.delete_calls.append(session)
        self.deleted.append(session)
        return session


class FakeState:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    def add_input(self, text: str) -> None:
        self.inputs.append(text)


class FakeResult:
    def __init__(
        self,
        *,
        label: str,
        deltas: list[str] | None = None,
        last_response_id: str | None = None,
        stream_gate: asyncio.Event | None = None,
    ) -> None:
        self.label = label
        self.deltas = deltas or []
        self.last_response_id = last_response_id or f"resp-{label}"
        self.stream_gate = stream_gate
        self.cancel_modes: list[str] = []
        self.state = FakeState()
        self.stream_started = asyncio.Event()
        self.stream_finished = asyncio.Event()

    async def stream_events(self):
        self.stream_started.set()
        if self.stream_gate is not None:
            await self.stream_gate.wait()
        for delta in self.deltas:
            yield _delta_event(delta)
        self.stream_finished.set()

    @property
    def final_output(self) -> str:
        return "".join(self.deltas)

    def to_state(self) -> FakeState:
        return self.state

    def cancel(self, mode: str = "immediate") -> None:
        self.cancel_modes.append(mode)


class FakeRunner:
    """Fake ``agents.Runner`` recording every model start."""

    def __init__(self, results: list[FakeResult]) -> None:
        self.results = results
        self.calls: list[dict[str, Any]] = []

    def run_streamed(self, agent: Any, payload: Any, **kwargs: Any) -> FakeResult:
        self.calls.append({"agent": agent, "payload": payload, **kwargs})
        if not self.results:
            raise AssertionError("FakeRunner exhausted: unexpected extra model run")
        return self.results.pop(0)


def _delta_event(text: str) -> Any:
    from openai.types.responses import ResponseTextDeltaEvent

    return type(
        "Event",
        (),
        {
            "type": "raw_response_event",
            "data": ResponseTextDeltaEvent.model_construct(
                delta=text,
                type="response.output_text.delta",
                content_index=0,
                item_id="item",
                output_index=0,
                sequence_number=0,
            ),
        },
    )()


def build_settings(tmp_path: Path) -> AiAssistantSettings:
    storage = tmp_path / "store"
    snapshots = storage / "snapshots"
    storage.mkdir(parents=True, exist_ok=True)
    snapshots.mkdir(parents=True, exist_ok=True)
    return AiAssistantSettings(
        model="gpt-5.6-luna",
        runtime_url="http://127.0.0.1:9911",
        storage_root=storage,
        snapshot_root=snapshots,
        knowledge_root=Path(runtime_module.__file__).resolve().parent / "knowledge",
        sandbox_image="unihub-retail-sandbox:test",
        max_artifact_bytes=1024 * 1024,
        setup_timeout_seconds=30,
    )


def build_runtime(
    tmp_path: Path,
    results: list[FakeResult],
    monkeypatch: pytest.MonkeyPatch,
    settings: AiAssistantSettings | None = None,
) -> tuple[AiSandboxRuntime, FakeDockerClient, FakeRunner]:
    settings = settings or build_settings(tmp_path)
    client = FakeDockerClient()
    runner = FakeRunner(results)
    monkeypatch.setattr(runtime_module, "Runner", runner)

    runtime = object.__new__(AiSandboxRuntime)
    runtime.settings = settings  # type: ignore[assignment]
    runtime.client = client  # type: ignore[assignment]
    runtime.options = object()  # type: ignore[assignment]
    runtime._active = {}  # type: ignore[attr-defined]
    runtime._lock = asyncio.Lock()  # type: ignore[attr-defined]
    return runtime, client, runner


def turn_request(
    conversation_id: UUID,
    *,
    text: str = "Analizează luna",
    uploads: list[RuntimeUpload] | None = None,
    owner_subject: str = "owner-a",
) -> RuntimeTurnRequest:
    return RuntimeTurnRequest(
        conversation_id=conversation_id,
        owner_subject=owner_subject,
        text=text,
        effort="high",
        uploads=uploads or [],
    )


def steer_request(
    *,
    order_key: int,
    text: str | None = None,
    uploads: list[RuntimeUpload] | None = None,
) -> RuntimeSteerRequest:
    return RuntimeSteerRequest(
        text=text if text is not None else f"steer-{order_key}",
        order_key=order_key,
        uploads=uploads or [],
    )


async def collect(stream) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    async for chunk in stream:
        events.append(json.loads(chunk.decode("utf-8")))
    return events


def event_types(events: list[dict[str, Any]]) -> list[str]:
    return [event["type"] for event in events]


async def settle() -> None:
    """Let every runnable task make progress without waiting on real time."""
    for _ in range(6):
        await asyncio.sleep(0)


# --------------------------------------------------------------------------
# Phase 7 — original concurrency reproducer
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_concurrent_same_conversation_attempts_create_exactly_one_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    first_result = FakeResult(label="first", deltas=["ok"])
    runtime, client, runner = build_runtime(tmp_path, [first_result], monkeypatch)

    gate = asyncio.Event()
    original_create = client.create

    async def gated_create(**kwargs: Any) -> FakeSandbox:
        await gate.wait()
        return await original_create(**kwargs)

    client.create = gated_create  # type: ignore[method-assign]

    first = asyncio.create_task(collect(runtime.stream_turn(turn_request(conversation_id))))
    await settle()
    second = asyncio.create_task(collect(runtime.stream_turn(turn_request(conversation_id))))
    await settle()

    # The second attempt must be refused while the first still owns the slot.
    assert event_types(await second) == ["error"]
    assert len(runtime._active) == 1
    reserved = runtime._active[conversation_id]
    assert reserved.phase == "setup"
    assert client.created == []

    gate.set()
    events = await first

    assert event_types(events) == ["status", "delta", "complete"]
    assert len(runner.calls) == 1
    # CONCURRENT_RUNS_CREATED must be exactly 1: no second sandbox, no second model run.
    assert len(client.created) == 1
    assert len(runner.calls) == 1
    assert runtime._active == {}
    print(f"CURRENT CONCURRENT_RUNS_CREATED={len(runner.calls)}")
    print(f"CURRENT SANDBOXES_CREATED={len(client.created)}")
    print(f"CURRENT DOCKER_DELETE_CALLS={len(client.delete_calls)}")


@pytest.mark.anyio
async def test_old_cleanup_cannot_remove_a_newer_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    first_result = FakeResult(label="first", deltas=["ok"])
    runtime, client, _runner = build_runtime(tmp_path, [first_result], monkeypatch)

    gate = asyncio.Event()
    original_create = client.create

    async def gated_create(**kwargs: Any) -> FakeSandbox:
        await gate.wait()
        return await original_create(**kwargs)

    client.create = gated_create  # type: ignore[method-assign]

    task = asyncio.create_task(collect(runtime.stream_turn(turn_request(conversation_id))))
    await settle()
    stale = runtime._active[conversation_id]

    # A newer reservation for the same conversation replaces the stale slot.
    newer = runtime_module.ActiveRun()
    runtime._active[conversation_id] = newer

    gate.set()
    await task

    # The stale run's identity-checked cleanup must not evict the newer slot.
    assert runtime._active.get(conversation_id) is newer
    assert runtime._active.get(conversation_id) is not stale


# --------------------------------------------------------------------------
# Phase 8 — Stop during setup
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stop_during_setup_cancels_setup_and_never_runs_the_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    runtime, client, runner = build_runtime(tmp_path, [], monkeypatch)

    release_setup = asyncio.Event()
    client.start_gates = [release_setup]

    task = asyncio.create_task(collect(runtime.stream_turn(turn_request(conversation_id))))
    while not client.created:
        await settle()
    await client.created[0].start_entered.wait()
    await settle()

    active = runtime._active[conversation_id]
    assert active.phase == "setup"
    assert active.task is task
    # The runtime already owns the created sandbox handle at this point.
    assert active.sandbox is client.created[0]

    # Stop is observable during setup, before any model execution exists.
    await runtime.stop(conversation_id)
    assert active.stop_requested is True
    assert active.phase == "stopping"

    events = await task

    assert "stopped" in event_types(events)
    assert runner.calls == []
    assert client.created != []
    # Identity-matched cleanup released the slot and deleted the sandbox.
    assert runtime._active == {}
    assert client.deleted == client.created
    assert all(sandbox.closed for sandbox in client.created)


@pytest.mark.anyio
async def test_stop_during_setup_leaves_no_orphan_and_next_run_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    second_result = FakeResult(label="second", deltas=["ok"])
    runtime, client, runner = build_runtime(tmp_path, [second_result], monkeypatch)

    release_setup = asyncio.Event()
    client.start_gates = [release_setup]

    task = asyncio.create_task(collect(runtime.stream_turn(turn_request(conversation_id))))
    while not client.created:
        await settle()
    await client.created[0].start_entered.wait()
    await settle()
    await runtime.stop(conversation_id)
    await task

    assert runtime._active == {}
    assert runner.calls == []

    # Runtime stays healthy: a subsequent run for the same conversation succeeds.
    events = await collect(runtime.stream_turn(turn_request(conversation_id)))
    assert event_types(events) == ["status", "delta", "complete"]
    assert len(runner.calls) == 1
    assert runtime._active == {}
    assert client.deleted == client.created


# --------------------------------------------------------------------------
# Phase 9 — Stop during Steer staging / resume
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stop_during_steer_staging_never_installs_a_resumed_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    active_result = FakeResult(label="first", deltas=["part"], stream_gate=asyncio.Event())
    resumed_result = FakeResult(label="resumed", deltas=["resumed"])
    runtime, client, runner = build_runtime(
        tmp_path, [active_result, resumed_result], monkeypatch
    )

    block = "input/steer-block.csv"
    upload = RuntimeUpload(storage_key="input/block.csv", sandbox_name="steer-block.csv")
    source = runtime.settings.storage_root / "input" / "block.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"a,b\n1,2\n")

    task = asyncio.create_task(collect(runtime.stream_turn(turn_request(conversation_id))))
    await active_result.stream_started.wait()
    await settle()

    active = runtime._active[conversation_id]
    assert active.phase == "running"
    assert active.result is active_result

    # Steer is accepted while the run is active; the SDK is asked to cancel after the turn.
    await runtime.steer(conversation_id, steer_request(order_key=1, uploads=[upload]))
    assert active_result.cancel_modes == ["after_turn"]

    sandbox = client.created[0]
    sandbox.block_on = {block}
    sandbox.write_gate = asyncio.Event()

    # Let the streamed turn finish so the runtime enters Steer staging.
    active_result.stream_gate.set()
    await active_result.stream_finished.wait()
    await sandbox.entered_block.wait()

    # Stop lands while Steer files are being staged, before the resumed run exists.
    await runtime.stop(conversation_id)
    assert active.stop_requested is True
    assert active.phase == "stopping"
    assert active.result is active_result

    assert sandbox.write_gate is not None
    sandbox.write_gate.set()
    events = await task

    assert event_types(events)[-1] == "stopped"
    # The resumed model run was never started, so no uncancellable second run exists.
    assert len(runner.calls) == 1
    assert resumed_result.cancel_modes == []
    # No stale result became current.
    assert active.result is active_result
    assert active.phase == "stopping"
    # Cleanup released the slot and left no container behind.
    assert runtime._active == {}
    assert client.deleted == client.created
    assert all(item.closed for item in client.created)


@pytest.mark.anyio
async def test_install_result_refuses_after_stop_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    runtime, _client, _runner = build_runtime(tmp_path, [], monkeypatch)
    active = runtime_module.ActiveRun(phase="steering", stop_requested=True)
    runtime._active[conversation_id] = active
    replacement = FakeResult(label="replacement")

    installed = await runtime._install_result(conversation_id, active, replacement)

    assert installed is False
    assert replacement.cancel_modes == ["immediate"]
    assert active.result is None


@pytest.mark.anyio
async def test_install_result_refuses_a_replaced_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    runtime, _client, _runner = build_runtime(tmp_path, [], monkeypatch)
    stale = runtime_module.ActiveRun(phase="setup")
    newer = runtime_module.ActiveRun(phase="setup")
    runtime._active[conversation_id] = newer
    replacement = FakeResult(label="replacement")

    installed = await runtime._install_result(conversation_id, stale, replacement)

    assert installed is False
    assert replacement.cancel_modes == ["immediate"]
    assert newer.result is None


@pytest.mark.anyio
async def test_resumed_model_input_follows_durable_order_key_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    active_result = FakeResult(label="first", deltas=["part"], stream_gate=asyncio.Event())
    resumed_result = FakeResult(
        label="resumed",
        deltas=["done"],
        stream_gate=asyncio.Event(),
    )
    runtime, _client, runner = build_runtime(
        tmp_path, [active_result, resumed_result], monkeypatch
    )

    task = asyncio.create_task(collect(runtime.stream_turn(turn_request(conversation_id))))
    await active_result.stream_started.wait()
    await settle()

    # Steers arrive out of HTTP completion order but carry durable order keys.
    await runtime.steer(conversation_id, steer_request(order_key=3, text="al treilea"))
    await runtime.steer(conversation_id, steer_request(order_key=1, text="primul"))
    await runtime.steer(conversation_id, steer_request(order_key=2, text="al doilea"))
    assert active_result.cancel_modes == ["after_turn", "after_turn", "after_turn"]

    assert active_result.stream_gate is not None
    active_result.stream_gate.set()
    await active_result.stream_finished.wait()
    await settle()
    while len(runner.calls) < 2:
        await settle()

    assert len(runner.calls) == 2
    resumed_state = active_result.state
    assert [text for text in resumed_state.inputs] == ["primul", "al doilea", "al treilea"]

    assert resumed_result.stream_gate is not None
    resumed_result.stream_gate.set()
    events = await task

    assert event_types(events)[-1] == "complete"
    assert runtime._active == {}


# --------------------------------------------------------------------------
# Phase 10 — Docker lifecycle for completion / stop / setup failure
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_normal_completion_closes_and_deletes_the_sandbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    runtime, client, _runner = build_runtime(
        tmp_path, [FakeResult(label="only", deltas=["gata"])], monkeypatch
    )

    events = await collect(runtime.stream_turn(turn_request(conversation_id)))

    assert event_types(events) == ["status", "delta", "complete"]
    assert runtime._active == {}
    assert len(client.created) == 1
    assert client.deleted == client.created
    assert client.delete_calls == client.created
    assert client.created[0].closed is True


@pytest.mark.anyio
async def test_setup_timeout_reports_error_and_cleans_the_sandbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    runtime, client, runner = build_runtime(tmp_path, [], monkeypatch)
    runtime.settings = replace(runtime.settings, setup_timeout_seconds=5)

    never = asyncio.Event()

    async def hanging_create(**kwargs: Any) -> FakeSandbox:
        sandbox = await FakeDockerClient.create(client, **kwargs)
        await never.wait()
        return sandbox

    client.create = hanging_create  # type: ignore[method-assign]

    monkeypatch.setattr(runtime_module.asyncio, "timeout", _immediate_timeout)
    events = await collect(runtime.stream_turn(turn_request(conversation_id)))

    assert event_types(events) == ["error"]
    assert runner.calls == []
    assert runtime._active == {}
    assert client.deleted == client.created


def _immediate_timeout(seconds: int):
    del seconds

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _scope():
        raise TimeoutError("setup timed out")
        yield  # pragma: no cover

    return _scope()


# --------------------------------------------------------------------------
# Owner admission — bounded run creation across conversations
# --------------------------------------------------------------------------


def owner_settings(tmp_path: Path, ceiling: int) -> AiAssistantSettings:
    return replace(build_settings(tmp_path), max_concurrent_runs_per_owner=ceiling)


@pytest.mark.anyio
async def test_two_conversations_run_together_and_the_third_is_refused_before_any_sandbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner ceiling 2 must refuse the third run before Docker/model work."""
    results = [FakeResult(label="a", deltas=["a"]), FakeResult(label="b", deltas=["b"])]
    runtime, client, runner = build_runtime(
        tmp_path, results, monkeypatch, settings=owner_settings(tmp_path, 2)
    )

    gate = asyncio.Event()
    original_create = client.create

    async def gated_create(**kwargs: Any) -> FakeSandbox:
        await gate.wait()
        return await original_create(**kwargs)

    client.create = gated_create  # type: ignore[method-assign]

    conversations = [uuid4(), uuid4(), uuid4()]
    first = asyncio.create_task(collect(runtime.stream_turn(turn_request(conversations[0]))))
    await settle()
    second = asyncio.create_task(collect(runtime.stream_turn(turn_request(conversations[1]))))
    await settle()
    assert len(runtime._active) == 2

    third = asyncio.create_task(collect(runtime.stream_turn(turn_request(conversations[2]))))
    await settle()
    assert event_types(await third) == ["error"]
    assert conversations[2] not in runtime._active
    assert len(client.created) == 0

    gate.set()
    assert event_types(await first) == ["status", "delta", "complete"]
    assert event_types(await second) == ["status", "delta", "complete"]
    assert len(client.created) == 2
    assert len(runner.calls) == 2
    assert runtime._active == {}


@pytest.mark.anyio
async def test_a_second_owner_has_an_independent_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = [FakeResult(label="a", deltas=["a"]), FakeResult(label="b", deltas=["b"]), FakeResult(label="c", deltas=["c"])]
    runtime, client, _runner = build_runtime(
        tmp_path, results, monkeypatch, settings=owner_settings(tmp_path, 2)
    )

    gate = asyncio.Event()
    original_create = client.create

    async def gated_create(**kwargs: Any) -> FakeSandbox:
        await gate.wait()
        return await original_create(**kwargs)

    client.create = gated_create  # type: ignore[method-assign]

    owner_a = [
        asyncio.create_task(collect(runtime.stream_turn(turn_request(uuid4(), owner_subject="owner-a"))))
        for _ in range(2)
    ]
    await settle()
    await settle()
    owner_b = asyncio.create_task(
        collect(runtime.stream_turn(turn_request(uuid4(), owner_subject="owner-b")))
    )
    await settle()

    assert len(runtime._active) == 3
    gate.set()
    for task in (*owner_a, owner_b):
        assert event_types(await task)[-1] == "complete"
    assert len(client.created) == 3


@pytest.mark.anyio
async def test_completing_a_run_frees_owner_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = [FakeResult(label="a", deltas=["a"]), FakeResult(label="b", deltas=["b"])]
    runtime, client, _runner = build_runtime(
        tmp_path, results, monkeypatch, settings=owner_settings(tmp_path, 1)
    )

    held = uuid4()
    gate = asyncio.Event()
    original_create = client.create

    async def gated_create(**kwargs: Any) -> FakeSandbox:
        await gate.wait()
        return await original_create(**kwargs)

    client.create = gated_create  # type: ignore[method-assign]

    first = asyncio.create_task(collect(runtime.stream_turn(turn_request(held))))
    await settle()
    refused = await collect(runtime.stream_turn(turn_request(uuid4())))
    assert event_types(refused) == ["error"]

    gate.set()
    assert event_types(await first)[-1] == "complete"
    assert runtime._active == {}

    after = await collect(runtime.stream_turn(turn_request(uuid4())))
    assert event_types(after)[-1] == "complete"
    assert len(client.created) == 2


@pytest.mark.anyio
async def test_run_at_the_owner_ceiling_still_takes_internal_steer_turns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admission bounds run starts only; an accepted run keeps its own turns."""
    gate = asyncio.Event()
    results = [
        FakeResult(label="first", deltas=["a"], stream_gate=gate),
        FakeResult(label="second", deltas=["b"]),
    ]
    runtime, client, runner = build_runtime(
        tmp_path, results, monkeypatch, settings=owner_settings(tmp_path, 1)
    )

    conversation_id = uuid4()
    task = asyncio.create_task(collect(runtime.stream_turn(turn_request(conversation_id))))
    await results[0].stream_started.wait()

    # The owner is at its ceiling; the accepted run must still resume on Steer.
    assert len(runtime._active) == 1
    await runtime.steer(conversation_id, steer_request(order_key=1, text="continuă"))
    gate.set()

    events = await task
    assert event_types(events) == ["status", "delta", "status", "delta", "complete"]
    assert len(runner.calls) == 2
    assert len(client.created) == 1


@pytest.mark.anyio
async def test_stop_frees_the_owner_slot_for_the_next_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream_gate = asyncio.Event()
    results = [
        FakeResult(label="held", deltas=[], stream_gate=stream_gate),
        FakeResult(label="next", deltas=["b"]),
    ]
    runtime, client, _runner = build_runtime(
        tmp_path, results, monkeypatch, settings=owner_settings(tmp_path, 1)
    )

    held = uuid4()
    stopped = asyncio.create_task(collect(runtime.stream_turn(turn_request(held))))
    await results[0].stream_started.wait()

    await runtime.stop(held)
    # A real SDK result aborts on cancel; the fake only ends once released.
    stream_gate.set()
    assert event_types(await stopped) == ["status", "stopped"]
    assert runtime._active == {}

    after = await collect(runtime.stream_turn(turn_request(uuid4())))
    assert event_types(after) == ["status", "delta", "complete"]
    assert len(client.created) == 2
    assert client.deleted[0].closed is True
