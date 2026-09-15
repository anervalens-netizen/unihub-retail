"""Narrow SDK 0.22.2 adapter: create-time bounds and streaming bind snapshots."""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import tarfile
import threading
from pathlib import Path
from uuid import uuid4

from agents.sandbox import LocalSnapshot
from contextvars import ContextVar
from typing import Any, Literal

from agents.sandbox.sandboxes.docker import DockerSandboxClient, DockerSandboxClientOptions, DockerSandboxSession
from agents.sandbox.util.tar_utils import strip_tar_member_prefix, validate_tarfile
from docker.types import LogConfig, Mount
from pydantic import BaseModel

from ai_assistant.storage_slots import StorageSlot, storage_io, drain_io

_SLOT: ContextVar[StorageSlot | None] = ContextVar("ai_storage_slot", default=None)
LABELS = {"com.unihub.component": "ai-assistant", "com.unihub.runtime": "sandbox-agent"}
SLOT_LABEL = "com.unihub.storage-slot"
_EPHEMERAL_TMP = "/" + "tmp"
MAX_WORKSPACE_ARCHIVE_BYTES = 9 * 1024**3
MAX_SNAPSHOT_STORE_BYTES = 16 * 1024**3
_SNAPSHOT_STORE_LOCK = threading.Lock()
WORKSPACE_ENV = {
    "HOME": "/workspace/home",
    "XDG_CACHE_HOME": "/workspace/work/cache",
    "XDG_CONFIG_HOME": "/workspace/home/.config",
    "XDG_DATA_HOME": "/workspace/home/.local/share",
    "NPM_CONFIG_PREFIX": "/workspace/work/npm",
    "NPM_CONFIG_CACHE": "/workspace/work/cache/npm",
    "PIP_TARGET": "/workspace/work/python",
    "PYTHONPATH": "/workspace/work/python",
    "PATH": "/workspace/work/python/bin:/workspace/work/npm/bin:/opt/venv/bin:/usr/local/bin:/usr/bin:/bin",
}


class SlotDockerOptions(DockerSandboxClientOptions):
    type: Literal["unihub_bounded_docker"] = "unihub_bounded_docker"  # type: ignore[assignment]
    slot: StorageSlot

    def __init__(self, *, image: str, slot: StorageSlot, labels: dict[str, str] | None = None):
        BaseModel.__init__(self, image=image, slot=slot, labels=labels or {})


class _BoundedContainers:
    def __init__(self, containers: Any):
        self._containers = containers

    def __getattr__(self, name: str) -> Any:
        return getattr(self._containers, name)

    def create(self, **kwargs: Any) -> Any:
        slot = _SLOT.get()
        if slot is None:
            raise RuntimeError("Docker creation requires a reserved AI storage slot")
        if kwargs.get("mounts") or kwargs.get("devices") or kwargs.get("cap_add"):
            raise RuntimeError("Additional privileged mounts are not supported by the AI sandbox")
        kwargs.update(
            read_only=True, mem_limit=2147483648, memswap_limit=3221225472,
            nano_cpus=2000000000, pids_limit=512,
            user=f"{os.geteuid()}:{os.getegid()}",
            cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
            mounts=[Mount(target="/workspace", source=str(slot.workspace), type="bind")],
            tmpfs={_EPHEMERAL_TMP: "rw,nosuid,nodev,exec,size=512m,mode=1777", "/run": "rw,nosuid,nodev,noexec,size=64m,mode=755"},
            shm_size=268435456,
            log_config=LogConfig(type="local", config={"max-size": "10m", "max-file": "2"}),
            labels={**(kwargs.get("labels") or {}), **LABELS, SLOT_LABEL: str(slot.index)},
            environment={**(kwargs.get("environment") or {}), **WORKSPACE_ENV},
        )
        return self._containers.create(**kwargs)


class _BoundedDocker:
    def __init__(self, docker: Any):
        self._docker = docker
        self.containers = _BoundedContainers(docker.containers)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._docker, name)


class _BoundedArchive(io.RawIOBase):
    """Sparse logical files must not expand without bound on the host."""
    def __init__(self, stream: io.IOBase, *, limit: int = MAX_WORKSPACE_ARCHIVE_BYTES):
        self.stream = stream
        self.remaining = limit  # 8 GiB contents plus bounded tar/inode metadata.

    def read(self, size: int = -1) -> bytes:
        data = self.stream.read(min(size if size >= 0 else 65536, self.remaining + 1))
        if not isinstance(data, bytes):
            raise RuntimeError("Invalid workspace archive")
        self.remaining -= len(data)
        if self.remaining < 0:
            raise RuntimeError("Workspace snapshot exceeds its bounded archive allowance")
        return data

    def close(self) -> None:
        self.stream.close()
        super().close()


class SlotDockerSession(DockerSandboxSession):
    async def persist_workspace(self) -> io.IOBase:
        """Archive the bind directly, not SDK's unbounded full copy into /tmp.

        No manifest mounts are accepted, so no pruning is needed. Docker's tar
        endpoint includes bind contents. LocalSnapshot keeps its atomic replace,
        and SDK hydrate_workspace retains its validated tar restore lifecycle.
        """
        return await storage_io(self._persist_bind)

    def _persist_bind(self) -> io.IOBase:
        root = self._workspace_root_path()
        self._container.pause()
        try:
            stream = _BoundedArchive(self._workspace_archive_stream(root))
            archive = strip_tar_member_prefix(stream, prefix=root.name)
            try:
                with tarfile.open(fileobj=archive, mode="r:*") as tar:
                    validate_tarfile(tar, allow_external_symlink_targets=False)
                archive.seek(0)
                return archive
            except BaseException:
                archive.close()
                raise
        finally:
            self._container.unpause()


    async def hydrate_workspace(self, data: io.IOBase) -> None:
        archive = await storage_io(_validated_restore, data)
        try:
            await drain_io(self._stream_into_exec(cmd=["tar", "-x", "-C", "/workspace"], stream=archive, error_path=Path("/workspace")))
        finally:
            archive.close()


def _validated_restore(data: io.IOBase) -> io.IOBase:
    archive = tempfile.TemporaryFile()
    try:
        shutil.copyfileobj(_BoundedArchive(data), archive)
        archive.seek(0)
        with tarfile.open(fileobj=archive, mode="r:*") as tar:
            validate_tarfile(tar, allow_external_symlink_targets=False)
        archive.seek(0)
        return archive
    except BaseException:
        archive.close()
        raise


class WorkspaceSnapshot(LocalSnapshot):
    type: Literal["unihub_workspace"] = "unihub_workspace"  # type: ignore[assignment]

    async def persist(self, data: io.IOBase, *, dependencies: Any = None) -> None:
        await storage_io(self._persist_atomic, data)

    def _persist_atomic(self, data: io.IOBase) -> None:
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        with _SNAPSHOT_STORE_LOCK:
            files = [item for item in path.parent.rglob("*") if item.is_file()]
            current = sum(item.stat().st_size for item in files)
            replaced = path.stat().st_size if path.is_file() else 0
            allowance = MAX_SNAPSHOT_STORE_BYTES - current + replaced
            if allowance <= 0:
                raise RuntimeError("AI workspace snapshot store is full")
            try:
                with temporary.open("xb") as output:
                    shutil.copyfileobj(
                        _BoundedArchive(data, limit=min(MAX_WORKSPACE_ARCHIVE_BYTES, allowance)),
                        output,
                    )
                    output.flush()
                    os.fsync(output.fileno())
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)


class BoundedDockerSandboxClient(DockerSandboxClient):
    def __init__(self, docker: Any):
        super().__init__(_BoundedDocker(docker))

    async def create(self, **kwargs: Any) -> Any:
        options = kwargs.get("options")
        if not isinstance(options, SlotDockerOptions):
            raise RuntimeError("AI Docker client requires storage-slot options")
        token = _SLOT.set(options.slot)
        try:
            return await super().create(**kwargs)
        finally:
            _SLOT.reset(token)

    def _wrap_session(self, inner: Any, *, instrumentation: Any = None) -> Any:
        if not isinstance(inner, DockerSandboxSession):
            raise TypeError("AI Docker adapter requires an SDK Docker session")
        bounded = SlotDockerSession(
            docker_client=self.docker_client, container=inner._container, state=inner.state,
        )
        return super()._wrap_session(bounded, instrumentation=instrumentation)
