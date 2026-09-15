"""Unit regressions for bounded AI sandbox storage and Docker adapter."""
from __future__ import annotations

import asyncio
import io
import os
import tarfile
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from ai_assistant import docker_client
from ai_assistant.docker_client import (
    LABELS,
    SLOT_LABEL,
    WORKSPACE_ENV,
    SlotDockerSession,
    WorkspaceSnapshot,
    _BoundedArchive,
    _BoundedContainers,
)
from ai_assistant.storage_slots import StorageSlot, drain_io, storage_io


@pytest.mark.anyio
async def test_storage_io_heartbeat_and_repeated_cancellation_wait_for_worker() -> None:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    heartbeat = 0

    def blocking() -> str:
        started.set()
        release.wait(5)
        finished.set()
        return "done"

    async def beat() -> None:
        nonlocal heartbeat
        while not finished.is_set():
            heartbeat += 1
            await asyncio.sleep(0)

    operation = asyncio.create_task(storage_io(blocking))
    beat_task = asyncio.create_task(beat())
    await asyncio.to_thread(started.wait, 1)
    assert heartbeat > 0  # the event loop remains live during the blocking worker
    operation.cancel()
    await asyncio.sleep(0)
    operation.cancel()  # repeated cancellation must not abandon the worker
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    await beat_task
    assert finished.is_set()


@pytest.mark.anyio
async def test_drain_io_waits_for_worker_after_cancellation() -> None:
    release = threading.Event()
    finished = threading.Event()

    def worker() -> bytes:
        release.wait(5)
        finished.set()
        return b"result"

    operation = asyncio.create_task(drain_io(asyncio.to_thread(worker)))
    await asyncio.sleep(0)
    operation.cancel()
    operation.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert finished.is_set()


def test_workspace_snapshot_keeps_previous_bytes_on_bounded_read_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = WorkspaceSnapshot(id="conversation", base_path=tmp_path)
    path = snapshot._path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"previous snapshot")

    class TinyBoundedArchive(_BoundedArchive):
        def __init__(self, stream: io.IOBase, *, limit: int = 3) -> None:
            super().__init__(stream, limit=min(limit, 3))

    monkeypatch.setattr(docker_client, "_BoundedArchive", TinyBoundedArchive)
    with pytest.raises(RuntimeError, match="bounded archive"):
        snapshot._persist_atomic(io.BytesIO(b"new bytes"))
    assert path.read_bytes() == b"previous snapshot"


def test_bounded_archive_enforces_small_remaining_budget_without_large_allocation() -> None:
    archive = _BoundedArchive(io.BytesIO(b"12345"))
    archive.remaining = 4
    with pytest.raises(RuntimeError, match="bounded archive allowance"):
        archive.read()
    archive.close()


def test_workspace_snapshot_enforces_aggregate_store_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(docker_client, "MAX_SNAPSHOT_STORE_BYTES", 20)
    snapshot = WorkspaceSnapshot(id="conversation", base_path=tmp_path)
    path = snapshot._path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"previous")
    (path.parent / "other-snapshot").write_bytes(b"123456789012")

    with pytest.raises(RuntimeError, match="bounded archive allowance"):
        snapshot._persist_atomic(io.BytesIO(b"replacement-too-large"))

    assert path.read_bytes() == b"previous"
    assert not list(path.parent.glob(".*.tmp"))


def _slot(tmp_path: Path) -> StorageSlot:
    return StorageSlot(1, tmp_path / "slot-1", tmp_path / "slot-1.ext4")


def test_bounded_docker_rejects_missing_slot_and_additional_mounts(tmp_path: Path) -> None:
    containers = Mock()
    adapter = _BoundedContainers(containers)
    with pytest.raises(RuntimeError, match="reserved AI storage slot"):
        adapter.create(image="image")
    token = docker_client._SLOT.set(_slot(tmp_path))
    try:
        for key in ("mounts", "devices", "cap_add"):
            with pytest.raises(RuntimeError, match="Additional privileged mounts"):
                adapter.create(image="image", **{key: ["extra"]})
    finally:
        docker_client._SLOT.reset(token)


def test_bounded_docker_create_has_exact_sandbox_kwargs(tmp_path: Path) -> None:
    containers = Mock()
    containers.create.return_value = "container"
    adapter = _BoundedContainers(containers)
    slot = _slot(tmp_path)
    token = docker_client._SLOT.set(slot)
    try:
        assert adapter.create(
            image="image", command=["run"], labels={"caller": "yes"}, environment={"CUSTOM": "value"}
        ) == "container"
    finally:
        docker_client._SLOT.reset(token)
    kwargs = containers.create.call_args.kwargs
    assert kwargs["read_only"] is True
    assert (kwargs["mem_limit"], kwargs["memswap_limit"], kwargs["nano_cpus"], kwargs["pids_limit"]) == (
        2147483648, 3221225472, 2000000000, 512
    )
    assert kwargs["user"] == f"{os.geteuid()}:{os.getegid()}"
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["security_opt"] == ["no-new-privileges:true"]
    assert len(kwargs["mounts"]) == 1
    assert kwargs["mounts"][0]["Target"] == "/workspace"
    assert kwargs["mounts"][0]["Source"] == str(slot.workspace)
    assert kwargs["tmpfs"] == {
        "/tmp": "rw,nosuid,nodev,exec,size=512m,mode=1777",
        "/run": "rw,nosuid,nodev,noexec,size=64m,mode=755",
    }
    assert kwargs["log_config"].type == "local"
    assert kwargs["log_config"].config == {"max-size": "10m", "max-file": "2"}
    assert kwargs["labels"] == {"caller": "yes", **LABELS, SLOT_LABEL: "1"}
    assert kwargs["environment"] == {"CUSTOM": "value", **WORKSPACE_ENV}


def test_outgoing_snapshot_rejects_external_symlink(tmp_path: Path) -> None:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        member = tarfile.TarInfo("workspace/escape")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../outside"
        tar.addfile(member)
    raw.seek(0)
    session: Any = object.__new__(SlotDockerSession)
    session._container = SimpleNamespace(pause=Mock(), unpause=Mock())
    root = tmp_path / "workspace"
    session._workspace_root_path = Mock(return_value=root)
    session._workspace_archive_stream = Mock(return_value=raw)
    with pytest.raises(Exception):
        session._persist_bind()
    session._container.pause.assert_called_once_with()
    session._container.unpause.assert_called_once_with()
