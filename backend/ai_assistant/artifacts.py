"""Host-side collection of sandbox output artifacts.

Sandbox output is untrusted. Collection enumerates changed outputs by content
hash, reads and size-validates every candidate before writing anything, and
rolls the whole call back if a host write still fails. A failed run can
therefore never leave invisible files behind, and artifacts produced by earlier
successful runs are never touched.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
import re
from typing import Any
from uuid import UUID, uuid4

from ai_assistant.settings import AiAssistantSettings, resolve_storage_key
from schemas.ai_assistant import RuntimeArtifact

logger = logging.getLogger(__name__)

_SAFE_ARTIFACT_NAME_RE = re.compile(r"[^A-Za-z0-9._() -]+")
_OUTPUT_HASH_COMMAND = "find output -type f -print0 | sort -z | xargs -0 -r sha256sum -z"


def safe_artifact_filename(value: str, artifact_id: UUID) -> str:
    """Normalize a sandbox-provided name into a safe non-empty host filename."""
    name = _SAFE_ARTIFACT_NAME_RE.sub("_", Path(value).name).strip(" .")
    if not name:
        return f"artifact-{artifact_id}.bin"
    return name[:180].rstrip(" .") or f"artifact-{artifact_id}.bin"


async def output_hashes(sandbox: Any) -> dict[str, str]:
    """Return the content hash of every file currently under sandbox ``output/``."""
    result = await sandbox.exec(_OUTPUT_HASH_COMMAND, timeout=30)
    if not result.ok():
        raise RuntimeError("unable to enumerate sandbox output files")
    hashes: dict[str, str] = {}
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        digest, raw_path = record.split(b"  ", 1)
        path = raw_path.decode("utf-8", errors="strict")
        if path.startswith("output/"):
            hashes[path.removeprefix("output/")] = digest.decode("ascii")
    return hashes


async def _read_output(sandbox: Any, relative: str, limit: int) -> bytes:
    stream = await sandbox.read(Path("output") / relative)
    try:
        payload = stream.read()
        if not isinstance(payload, bytes):
            payload = bytes(payload)
        if len(payload) > limit:
            raise RuntimeError(f"generated artifact exceeds configured limit: {relative}")
        return payload
    finally:
        stream.close()


def _remove_host_artifacts(storage_root: Path, targets: list[Path]) -> None:
    """Delete every host-side artifact written by one collection call.

    Files are removed first, then the now-empty per-artifact directories are
    pruned deepest-first so a directory created for an output whose write failed
    cannot survive the rollback.
    """
    for target in targets:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            logger.exception("unable to roll back partially collected AI artifact")
    directories = sorted(
        {target.parent for target in targets},
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        current = directory
        while current != storage_root and current.is_relative_to(storage_root):
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent


async def collect_output_artifacts(
    settings: AiAssistantSettings,
    conversation_id: UUID,
    sandbox: Any,
    before: dict[str, str],
) -> list[RuntimeArtifact]:
    """Persist every sandbox output that changed since ``before``, atomically."""
    after = await output_hashes(sandbox)
    limit = settings.max_artifact_bytes
    candidates = [
        (relative, await _read_output(sandbox, relative, limit))
        for relative, digest in sorted(after.items())
        if before.get(relative) != digest
    ]
    artifacts: list[RuntimeArtifact] = []
    written: list[Path] = []
    try:
        for relative, payload in candidates:
            artifact_id = uuid4()
            filename = safe_artifact_filename(relative, artifact_id)
            storage_key = (
                Path("output") / str(conversation_id) / str(artifact_id) / filename
            ).as_posix()
            target = resolve_storage_key(settings.storage_root, storage_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            # Track before writing: a failed write must still roll back the
            # directory this artifact reserved.
            written.append(target)
            target.write_bytes(payload)
            artifacts.append(
                RuntimeArtifact(
                    id=artifact_id,
                    filename=filename,
                    mime_type=mimetypes.guess_type(filename)[0]
                    or "application/octet-stream",
                    size_bytes=len(payload),
                    storage_key=storage_key,
                )
            )
    except Exception:
        _remove_host_artifacts(settings.storage_root, written)
        raise
    return artifacts
