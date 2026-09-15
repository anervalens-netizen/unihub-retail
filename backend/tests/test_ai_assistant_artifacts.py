"""Host-side artifact collection must be atomic per collection call.

The review finding: when a sandbox produced several changed outputs, a later
output that failed validation/read/size left the earlier copies invisibly on
disk with no completion event and no database rows. Collection now reads and
validates every candidate before writing anything and rolls back anything it
did write, while never touching artifacts from earlier successful runs.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
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

    async def exec(self, command: str, timeout: int | None = None) -> FakeExecResult:
        del command, timeout
        records = [
            f"{hashlib.sha256(self.files[relative]).hexdigest()}  output/{relative}".encode()
            for relative in sorted(self.files)
        ]
        return FakeExecResult(b"\0".join(records) + (b"\0" if records else b""))

    async def read(self, path: Path) -> io.BytesIO:
        relative = str(path).removeprefix("output/")
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
