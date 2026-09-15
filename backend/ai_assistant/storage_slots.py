"""Two root-provisioned disk slots; the runtime never mounts or formats storage."""
from __future__ import annotations

import asyncio
import os
import stat
from typing import Any, Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path

SLOT_BYTES = 8 * 1024**3
SLOT_COUNT = 2
SLOT_ROOT = Path("/var/lib/unihub-retail/ai-sandbox-slots")
IMAGE_ROOT = Path("/var/lib/unihub-retail/ai-storage-images")
_LOCAL_TEST_PARENT = Path(os.sep) / "tmp"
_WORKSPACE_MODE = stat.S_IRWXU | stat.S_IRWXG


@dataclass(frozen=True)
class StorageSlot:
    index: int
    mount: Path
    image: Path

    @property
    def workspace(self) -> Path:
        return self.mount / "workspace"


def _unescape_mount(value: str) -> str:
    for escaped, decoded in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
        value = value.replace(escaped, decoded)
    return value


def _root_owned_path(path: Path) -> None:
    for item in (path, *path.parents):
        info = item.lstat()
        sticky_tmp = item == _LOCAL_TEST_PARENT and bool(info.st_mode & stat.S_ISVTX)
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or (info.st_mode & 0o022 and not sticky_tmp):
            raise RuntimeError("AI storage path is not exclusively root controlled")


def verify_slot(slot: StorageSlot, *, require_workspace_mode: bool = True) -> None:
    """Verify the actual ext4 loop mount, backing reservation and workspace owner."""
    _root_owned_path(slot.mount)
    _root_owned_path(slot.image)
    image = slot.image.stat()
    if not stat.S_ISREG(image.st_mode) or image.st_size != SLOT_BYTES or image.st_blocks * 512 < SLOT_BYTES:
        raise RuntimeError("AI storage image lacks its fixed preallocation")
    records = [line.split() for line in Path("/proc/self/mountinfo").read_text().splitlines()]
    mounts = [row for row in records if _unescape_mount(row[4]) == str(slot.mount)]
    if len(mounts) != 1:
        raise RuntimeError("AI storage slot is not a unique mounted filesystem")
    record = mounts[0]
    separator = record.index("-")
    source = record[separator + 2]
    if record[separator + 1] != "ext4" or not source.startswith("/dev/loop"):
        raise RuntimeError("AI storage slot is not an ext4 loop filesystem")
    flags = set(record[5].split(","))
    if not {"nosuid", "nodev", "noatime"} <= flags or "discard" in record[separator + 3].split(","):
        raise RuntimeError("AI storage mount flags are unsafe")
    # ProtectSystem=strict makes the slot parent ro in the service namespace;
    # only its workspace is a writable ReadWritePaths bind on the same device.
    if os.statvfs(slot.workspace).f_flag & os.ST_RDONLY:
        raise RuntimeError("AI workspace is not writable in this service namespace")
    backing = Path("/sys/dev/block") / record[2] / "loop/backing_file"
    if Path(backing.read_text().strip()).resolve() != slot.image:
        raise RuntimeError("AI storage slot has an unexpected backing image")
    fs = os.statvfs(slot.mount)
    if not 7 * 1024**3 < fs.f_blocks * fs.f_frsize <= SLOT_BYTES:
        raise RuntimeError("AI storage slot has an unexpected capacity")
    info = slot.workspace.lstat()
    if not stat.S_ISDIR(info.st_mode) or (info.st_uid, info.st_gid) != (os.geteuid(), os.getegid()):
        raise RuntimeError("AI workspace has an unexpected owner or type")
    if info.st_dev != slot.mount.stat().st_dev:
        raise RuntimeError("AI workspace is not on its slot filesystem")
    if require_workspace_mode and stat.S_IMODE(info.st_mode) != _WORKSPACE_MODE:
        raise RuntimeError("AI workspace has unsafe permissions")


def _clear_directory(fd: int, device: int) -> None:
    """Descriptor-relative, no-follow removal, including owner-created mode-000 dirs."""
    for name in os.listdir(fd):
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if info.st_dev != device:
            raise RuntimeError("AI workspace cleanup refuses another filesystem")
        if stat.S_ISDIR(info.st_mode):
            os.chmod(name, 0o700, dir_fd=fd, follow_symlinks=False)
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                _clear_directory(child, device)
            finally:
                os.close(child)
            os.rmdir(name, dir_fd=fd)
        else:
            os.unlink(name, dir_fd=fd)


def clean_slot(slot: StorageSlot) -> None:
    """Caller must first prove no container still holds this slot."""
    # The sandbox owner can chmod its own mount root. Validate immutable host
    # boundaries first, then restore traversal permissions before no-follow cleanup.
    verify_slot(slot, require_workspace_mode=False)
    os.chmod(slot.workspace, _WORKSPACE_MODE, follow_symlinks=False)
    fd = os.open(slot.workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _clear_directory(fd, os.fstat(fd).st_dev)
    finally:
        os.close(fd)
    os.chmod(slot.workspace, _WORKSPACE_MODE, follow_symlinks=False)
    verify_slot(slot)


async def storage_io(function: Callable[..., Any], *args: Any) -> Any:
    """Drain disk work even on cancellation before a slot can be cleaned/reused."""
    return await drain_io(asyncio.to_thread(function, *args))


async def drain_io(operation: Coroutine[Any, Any, Any]) -> Any:
    task = asyncio.create_task(operation)
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True
    if cancelled:
        if hasattr(result, "close"):
            result.close()
        raise asyncio.CancelledError
    return result


class StorageSlots:
    def __init__(self, root: Path = SLOT_ROOT, images: Path = IMAGE_ROOT):
        self.slots = tuple(StorageSlot(i, root / f"slot-{i}", images / f"slot-{i}.ext4") for i in range(SLOT_COUNT))
        self.available: set[int] = set()
        self.unavailable: set[int] = set()

    def verify(self) -> None:
        # A crashed sandbox may have chmodded its writable mount root. Confirm
        # immutable storage identity/capacity here; reconciliation restores 0770.
        for slot in self.slots:
            verify_slot(slot, require_workspace_mode=False)

    def reconcile(self) -> None:
        self.available.clear()
        for slot in self.slots:
            clean_slot(slot)
        self.unavailable.clear()
        self.available.update(range(SLOT_COUNT))

    def acquire(self) -> StorageSlot | None:
        # All calls to acquire/release occur under the runtime's admission lock.
        if not self.available:
            return None
        index = min(self.available)
        self.available.remove(index)
        return self.slots[index]

    def release(self, slot: StorageSlot, *, clean: bool) -> None:
        if clean and slot.index not in self.unavailable:
            self.available.add(slot.index)
        else:
            self.unavailable.add(slot.index)
            self.available.discard(slot.index)
