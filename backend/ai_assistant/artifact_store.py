"""Cross-process hard ceiling for persistent AI input and output files."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path

MAX_PERSISTENT_ARTIFACT_BYTES = 16 * 1024**3


def write_artifact_bounded(storage_root: Path, target: Path, payload: bytes) -> None:
    """Create one artifact while holding the shared store quota lock."""
    storage_root.mkdir(parents=True, exist_ok=True)
    lock_path = storage_root / ".artifact-store.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        total = sum(
            item.stat().st_size
            for namespace in (storage_root / "input", storage_root / "output")
            if namespace.is_dir()
            for item in namespace.rglob("*")
            if item.is_file() and not item.is_symlink()
        )
        if total + len(payload) > MAX_PERSISTENT_ARTIFACT_BYTES:
            raise RuntimeError("AI persistent artifact store is full")
        target.parent.mkdir(parents=True, exist_ok=False)
        try:
            target.write_bytes(payload)
        except BaseException:
            target.unlink(missing_ok=True)
            target.parent.rmdir()
            raise
    finally:
        os.close(descriptor)
