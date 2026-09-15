"""Opt-in real Docker proof using explicitly provisioned disposable loop slots."""
from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
from uuid import uuid4

import docker
import pytest

from ai_assistant.docker_client import BoundedDockerSandboxClient, SlotDockerOptions, WorkspaceSnapshot, LABELS
from ai_assistant.runtime import _manifest
from ai_assistant.storage_slots import StorageSlots, clean_slot

pytestmark = pytest.mark.skipif(
    os.getenv("AI_TEST_STORAGE_ROOT", "") == "" or os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated runner and explicitly provisioned disposable storage root",
)


async def command(session, text: str) -> bytes:
    result = await session.exec(text)
    assert result.ok(), (result.stdout, result.stderr)
    return result.stdout


@pytest.mark.anyio
async def test_real_storage_capabilities_limits_and_snapshot(tmp_path: Path, monkeypatch) -> None:
    root = Path(os.environ["AI_TEST_STORAGE_ROOT"])
    assert root.parent == Path("/tmp") and root.name.startswith("unihub-ai-storage.")
    monkeypatch.setenv("AI_ASSISTANT_READONLY_DSN", "postgresql://unihub_ai_readonly:isolated@192.0.2.1:5432/unused")
    slots = StorageSlots(root / "ai-sandbox-slots", root / "ai-storage-images")
    slots.verify()
    slots.reconcile()
    raw = docker.from_env(timeout=30)
    client = BoundedDockerSandboxClient(raw)
    sessions = []
    image = os.getenv("AI_TEST_SANDBOX_IMAGE", "unihub-retail-ai-sandbox:pr409-slots")
    snapshot = WorkspaceSnapshot(id=str(uuid4()), base_path=tmp_path)
    try:
        acquired = [slots.acquire(), slots.acquire()]
        assert acquired[0] is not None and acquired[1] is not None
        assert slots.acquire() is None
        for slot in acquired:
            assert slot is not None
            session = await client.create(manifest=_manifest(), snapshot=snapshot if slot.index == 0 else None,
                                          options=SlotDockerOptions(image=image, slot=slot, labels=LABELS))
            sessions.append(session)
            await session.start()
            container = raw.containers.get(session._inner.state.container_id)
            cfg = container.attrs["HostConfig"]
            assert (cfg["Memory"], cfg["MemorySwap"], cfg["NanoCpus"], cfg["PidsLimit"]) == (2147483648, 3221225472, 2000000000, 512)
            assert cfg["ReadonlyRootfs"] and cfg["ShmSize"] == 268435456
            assert "size=512m" in cfg["Tmpfs"]["/tmp"] and "size=64m" in cfg["Tmpfs"]["/run"]
            assert cfg["LogConfig"] == {"Type": "local", "Config": {"max-size": "10m", "max-file": "2"}}
            assert any(m["Source"] == str(slot.workspace) and m["Destination"] == "/workspace" and m["RW"] for m in container.attrs["Mounts"])
            values = await command(session, "cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.swap.max /sys/fs/cgroup/cpu.max /sys/fs/cgroup/pids.max")
            assert values.splitlines() == [b"2147483648", b"1073741824", b"200000 100000", b"512"]
            await command(session, "python -c \"import errno,os; p='/opt/venv/forbidden';\ntry: os.open(p,os.O_WRONLY|os.O_CREAT)\nexcept OSError as e: assert e.errno==errno.EROFS\nelse: raise AssertionError('writable root')\"")
        first = sessions[0]
        await command(first, "mkdir -p /workspace/home /workspace/work/cache /workspace/output; python -c 'import pandas,numpy; print(pandas.DataFrame({\"a\":[1]}).to_csv())'")
        await command(first, "psql --version; git --version; curl --version; jq --version; node --version; npm --version; pandoc --version")
        await command(first, "python -m pip install --disable-pip-version-check --no-deps pyfiglet==1.0.4 && python -c 'import pyfiglet; assert pyfiglet.figlet_format(\"ok\")'")
        await command(first, "npm install -g --ignore-scripts --no-audit --no-fund cowsay@1.6.0 && cowsay bounded")
        await command(first, "chromium --headless --no-sandbox --disable-dev-shm-usage --disable-gpu --dump-dom 'data:text/html,<h1>bounded</h1>' > /workspace/output/chromium.html; test -s /workspace/output/chromium.html")
        await command(first, "printf 'bounded document' > /workspace/work/proof.txt; libreoffice -env:UserInstallation=file:///workspace/work/lo --headless --convert-to pdf --outdir /workspace/output /workspace/work/proof.txt; test -s /workspace/output/proof.pdf")
        await command(first, "printf 'int main(){return 0;}' > /workspace/work/proof.c; cc /workspace/work/proof.c -o /workspace/work/proof; /workspace/work/proof")
        await command(first, "python -c \"import os,errno; p='/workspace/work/allocation'; s=os.statvfs('/workspace'); n=s.f_bavail*s.f_frsize-64*1024**2; f=os.open(p,os.O_CREAT|os.O_RDWR,0o600);\ntry:\n os.posix_fallocate(f,0,n); print('allocated',os.fstat(f).st_blocks*512)\n try: os.posix_fallocate(f,n,128*1024**2)\n except OSError as e: assert e.errno==errno.ENOSPC; print('ENOSPC')\n else: raise AssertionError('unbounded disk')\nfinally: os.close(f); os.unlink(p)\"")
        # A >tmpfs-sized file proves persistence does not copy the bind to /tmp.
        await command(first, "fallocate -l 600M /workspace/work/persist-large; printf durable-state > /workspace/work/persistent.txt")
        await first.aclose()
        await client.delete(first)
        sessions.remove(first)
        clean_slot(acquired[0])
        assert list(acquired[0].workspace.iterdir()) == []
        slots.release(acquired[0], clean=True)
        restored_slot = slots.acquire()
        assert restored_slot is not None
        resumed = await client.create(manifest=_manifest(), snapshot=snapshot,
                                      options=SlotDockerOptions(image=image, slot=restored_slot, labels=LABELS))
        sessions.append(resumed)
        await resumed.start()
        assert await command(resumed, "cat /workspace/work/persistent.txt") == b"durable-state"
        assert await command(resumed, "stat -c %s /workspace/work/persist-large") == b"629145600\n"
        await command(resumed, "python -c 'import pyfiglet'; cowsay resumed; rm /workspace/work/persist-large")
    finally:
        for session in sessions:
            try:
                await session.aclose()
            finally:
                await client.delete(session)
        for slot in slots.slots:
            assert not [c for c in raw.containers.list(all=True) if any(m.get('Source') == str(slot.workspace) for m in c.attrs.get('Mounts', []))]
            clean_slot(slot)
        raw.close()
