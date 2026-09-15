"""Host-side artifact collection must be atomic per collection call.

The review finding: when a sandbox produced several changed outputs, a later
output that failed validation/read/size left the earlier copies invisibly on
disk with no completion event and no database rows. Collection prechecks metadata,
then reads/writes/releases sequentially and rolls back this attempt on failure.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from ai_assistant import artifacts as artifacts_module
from ai_assistant import runtime as runtime_module
from ai_assistant.artifacts import collect_output_artifacts, output_hashes
from ai_assistant.runtime import AiSandboxRuntime
from ai_assistant.settings import AiAssistantSettings

MAX_BYTES = 4096


class FakeExecResult:
    def __init__(self, stdout: bytes) -> None:
        self.stdout = stdout

    def ok(self) -> bool:
        return True


class FakeSandbox:
    """Sandbox exposing only the output enumeration/read surface."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.read_failures: set[str] = set()
        self.read_calls: list[str] = []
        self.metadata_sizes: dict[str, int] = {}

    async def exec(self, command: str, timeout: int | None = None) -> FakeExecResult:
        if command == artifacts_module._OUTPUT_METADATA_COMMAND:
            return FakeExecResult(json.dumps([
                [relative, hashlib.sha256(payload).hexdigest(),
                 self.metadata_sizes.get(relative, len(payload))]
                for relative, payload in self.files.items()
            ]).encode())
        del command, timeout
        records = [
            f"{hashlib.sha256(self.files[relative]).hexdigest()}  output/{relative}".encode()
            for relative in sorted(self.files)
        ]
        return FakeExecResult(b"\0".join(records) + (b"\0" if records else b""))

    async def read(self, path: Path) -> io.BytesIO:
        relative = str(path).removeprefix("output/")
        self.read_calls.append(relative)
        if relative in self.read_failures:
            raise OSError("sandbox read failed")
        return io.BytesIO(self.files[relative])


def build_runtime(tmp_path: Path) -> AiSandboxRuntime:
    storage = tmp_path / "store"
    storage.mkdir(parents=True, exist_ok=True)
    runtime = object.__new__(AiSandboxRuntime)
    runtime.settings = AiAssistantSettings(  # type: ignore[assignment]
        model="gpt-5.6-luna",
        runtime_url="http://127.0.0.1:9911",
        storage_root=storage,
        snapshot_root=storage / "snapshots",
        knowledge_root=Path(runtime_module.__file__).resolve().parent / "knowledge",
        sandbox_image="unihub-retail-sandbox:test",
        max_artifact_bytes=MAX_BYTES,
        setup_timeout_seconds=30,
    )
    return runtime


def host_files(runtime: AiSandboxRuntime) -> list[Path]:
    return sorted(
        path for path in runtime.settings.storage_root.rglob("*") if path.is_file()
    )


@pytest.mark.anyio
async def test_multiple_outputs_are_collected_together(tmp_path: Path) -> None:
    runtime = build_runtime(tmp_path)
    sandbox = FakeSandbox({"b.txt": b"second", "a.txt": b"first"})

    artifacts = await collect_output_artifacts(runtime.settings, uuid4(), sandbox, {})

    assert [artifact.filename for artifact in artifacts] == ["a.txt", "b.txt"]
    assert [artifact.size_bytes for artifact in artifacts] == [5, 6]
    assert sorted(path.read_bytes() for path in host_files(runtime)) == [b"first", b"second"]
    for artifact in artifacts:
        assert (
            runtime.settings.storage_root / artifact.storage_key
        ).read_bytes() in {b"first", b"second"}


@pytest.mark.anyio
async def test_output_that_exceeds_the_limit_leaves_no_host_output(tmp_path: Path) -> None:
    runtime = build_runtime(tmp_path)
    sandbox = FakeSandbox({"a.txt": b"first", "large.bin": b"x" * (MAX_BYTES + 1)})

    with pytest.raises(RuntimeError, match="exceeds configured limit"):
        await collect_output_artifacts(runtime.settings, uuid4(), sandbox, {})

    assert host_files(runtime) == []


@pytest.mark.anyio
async def test_unreadable_later_output_leaves_no_host_output(tmp_path: Path) -> None:
    runtime = build_runtime(tmp_path)
    sandbox = FakeSandbox({"a.txt": b"first", "b.txt": b"second"})
    sandbox.read_failures.add("b.txt")

    with pytest.raises(OSError):
        await collect_output_artifacts(runtime.settings, uuid4(), sandbox, {})

    assert host_files(runtime) == []


@pytest.mark.anyio
async def test_host_write_failure_rolls_back_earlier_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = build_runtime(tmp_path)
    sandbox = FakeSandbox({"a.txt": b"first", "b.txt": b"second"})
    original_write = Path.write_bytes

    def flaky_write(self: Path, data: bytes) -> int:
        if self.name == "b.txt":
            raise OSError("no space left on device")
        return original_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", flaky_write)

    with pytest.raises(OSError, match="no space left"):
        await collect_output_artifacts(runtime.settings, uuid4(), sandbox, {})

    assert host_files(runtime) == []
    assert list(runtime.settings.storage_root.rglob("*")) == []


@pytest.mark.anyio
async def test_failed_collection_never_removes_earlier_successful_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = build_runtime(tmp_path)
    conversation_id = uuid4()
    previous = await collect_output_artifacts(
        runtime.settings, conversation_id, FakeSandbox({"keep.txt": b"earlier run"}), {}
    )
    assert len(previous) == 1
    keep_path = runtime.settings.storage_root / previous[0].storage_key

    def always_fails(self: Path, data: bytes) -> int:
        raise OSError("no space left on device")

    monkeypatch.setattr(Path, "write_bytes", always_fails)
    with pytest.raises(OSError):
        await collect_output_artifacts(
            runtime.settings, conversation_id, FakeSandbox({"new.txt": b"this run"}), {}
        )

    assert keep_path.read_bytes() == b"earlier run"
    assert host_files(runtime) == [keep_path]


@pytest.mark.anyio
async def test_unchanged_sandbox_outputs_are_not_recollected(tmp_path: Path) -> None:
    runtime = build_runtime(tmp_path)
    sandbox = FakeSandbox({"a.txt": b"first"})
    before = await output_hashes(sandbox)

    artifacts = await collect_output_artifacts(runtime.settings, uuid4(), sandbox, before)

    assert artifacts == []
    assert host_files(runtime) == []
    assert asyncio.iscoroutinefunction(collect_output_artifacts)


def test_collection_rollback_stays_inside_the_ai_storage_boundary() -> None:
    source = Path(artifacts_module.__file__).read_text(encoding="utf-8")
    assert "def _remove_host_artifacts" in source
    assert "written.append(target)" in source
    # The runtime itself must not keep a second, divergent copy of the logic.
    runtime_source = Path(runtime_module.__file__).read_text(encoding="utf-8")
    assert "_remove_host_artifacts" not in runtime_source
    assert "collect_output_artifacts" in runtime_source


@pytest.mark.anyio
@pytest.mark.parametrize("files,aggregate", [
    ({"a": b"123", "b": b"456"}, 5),
    ({"a": b"x" * (MAX_BYTES + 1)}, MAX_BYTES * 2),
])
async def test_metadata_limits_reject_before_any_read(tmp_path, files, aggregate):
    runtime = build_runtime(tmp_path)
    settings = replace(runtime.settings, max_total_artifact_bytes=aggregate)
    sandbox = FakeSandbox(files)
    with pytest.raises(RuntimeError, match="configured"):
        await collect_output_artifacts(settings, uuid4(), sandbox, {})
    assert sandbox.read_calls == []
    assert host_files(runtime) == []


@pytest.mark.anyio
async def test_payload_is_written_closed_and_released_before_next_read(tmp_path, monkeypatch):
    runtime = build_runtime(tmp_path)
    events = []

    class Payload(bytes):
        def __del__(self):
            events.append("release")

    class Stream(io.BytesIO):
        def read(self, size=-1):
            return Payload(super().read(size))

        def close(self):
            if not self.closed:
                events.append("close")
            super().close()

    class Sandbox(FakeSandbox):
        async def read(self, path):
            if events:
                assert events == ["read", "close", "write", "release"]
            events.append("read")
            return Stream(b"abc")

    write = Path.write_bytes

    def record_write(path, payload):
        events.append("write")
        return write(path, payload)

    monkeypatch.setattr(Path, "write_bytes", record_write)
    result = await collect_output_artifacts(
        runtime.settings, uuid4(), Sandbox({"a": b"abc", "b": b"abc"}), {}
    )
    assert len(result) == 2
    assert events == ["read", "close", "write", "release"] * 2


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["growth", "read", "write", "cancel"])
async def test_later_failure_rolls_back_only_this_attempt(tmp_path, monkeypatch, failure):
    runtime = build_runtime(tmp_path)
    settings = replace(runtime.settings, max_total_artifact_bytes=8)
    conversation_id = uuid4()
    previous = await collect_output_artifacts(
        settings, conversation_id, FakeSandbox({"keep": b"old"}), {}
    )
    keep = settings.storage_root / previous[0].storage_key
    sandbox = FakeSandbox({"a": b"12345", "b": b"67890"})
    sandbox.metadata_sizes = {"a": 3, "b": 3}
    original_read = sandbox.read
    original_write = Path.write_bytes
    written = []

    async def read(path):
        if path.name == "b":
            assert len(written) == 1
            if failure == "read":
                raise OSError("read failed")
            if failure == "cancel":
                raise asyncio.CancelledError()
        return await original_read(path)

    def write(path, payload):
        written.append(path)
        count = original_write(path, payload)
        if path.name == "b" and failure == "write":
            raise OSError("partial write failed")
        return count

    if failure != "growth":
        sandbox.files = {"a": b"123", "b": b"456"}
    monkeypatch.setattr(sandbox, "read", read)
    monkeypatch.setattr(Path, "write_bytes", write)
    error = asyncio.CancelledError if failure == "cancel" else (
        RuntimeError if failure == "growth" else OSError
    )
    with pytest.raises(error):
        await collect_output_artifacts(settings, conversation_id, sandbox, {})
    assert keep.read_bytes() == b"old"
    assert host_files(runtime) == [keep]
    assert sorted(keep.parent.parent.iterdir()) == [keep.parent]


@pytest.mark.anyio
async def test_identifier_collision_never_overwrites_previous_output(tmp_path, monkeypatch):
    runtime = build_runtime(tmp_path)
    conversation_id = uuid4()
    fixed_id = uuid4()
    monkeypatch.setattr(artifacts_module, "uuid4", lambda: fixed_id)
    previous = await collect_output_artifacts(
        runtime.settings, conversation_id, FakeSandbox({"same": b"old"}), {}
    )
    with pytest.raises(FileExistsError):
        await collect_output_artifacts(
            runtime.settings, conversation_id, FakeSandbox({"same": b"new"}), {}
        )
    keep = runtime.settings.storage_root / previous[0].storage_key
    assert keep.read_bytes() == b"old"
    assert host_files(runtime) == [keep]


@pytest.mark.anyio
async def test_metadata_command_returns_hash_size_and_safe_unusual_names(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    name = "unusual\n name ü.txt"
    (output / name).write_bytes(b"hello")
    (output / "link").symlink_to(output / name)
    (output / "directory-link").symlink_to(output, target_is_directory=True)

    class LocalSandbox:
        async def exec(self, command, timeout):
            result = subprocess.run(
                command, shell=True, cwd=tmp_path, capture_output=True,
                timeout=timeout, check=True,
            )
            return FakeExecResult(result.stdout)

    assert await artifacts_module._output_metadata(LocalSandbox()) == [
        (name, hashlib.sha256(b"hello").hexdigest(), 5)
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("record", [
    ["../outside", "a" * 64, 1], ["/outside", "a" * 64, 1],
    ["file", "invalid", 1], ["file", "a" * 64, -1],
    ["file", "a" * 64, True],
])
async def test_invalid_metadata_rejected_before_read(tmp_path, record):
    runtime = build_runtime(tmp_path)

    class Sandbox(FakeSandbox):
        async def exec(self, command, timeout=None):
            return FakeExecResult(json.dumps([record]).encode())

    sandbox = Sandbox({})
    with pytest.raises(RuntimeError, match="invalid sandbox output metadata"):
        await collect_output_artifacts(runtime.settings, uuid4(), sandbox, {})
    assert sandbox.read_calls == []


@pytest.mark.anyio
async def test_unchanged_large_files_do_not_use_changed_output_budget(tmp_path):
    runtime = build_runtime(tmp_path)
    settings = replace(runtime.settings, max_total_artifact_bytes=3)
    sandbox = FakeSandbox({"unchanged": b"x" * (MAX_BYTES + 1), "new": b"abc"})
    before = await output_hashes(sandbox)
    del before["new"]
    result = await collect_output_artifacts(settings, uuid4(), sandbox, before)
    assert len(result) == 1
    assert sandbox.read_calls == ["new"]
