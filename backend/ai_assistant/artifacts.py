"""Host-side collection of sandbox output artifacts.

Sandbox output is untrusted. Collection enumerates changed outputs by content
hash and size before fetching payloads, then reads/writes/releases one payload
at a time under per-file and aggregate caps. Any failure rolls this call back. A failed run can
therefore never leave invisible files behind, and artifacts produced by earlier
successful runs are never touched.
"""

from __future__ import annotations

import json
import logging
import shlex
import mimetypes
from pathlib import Path
import re
from typing import Any
from uuid import UUID, uuid4

from ai_assistant.artifact_store import write_artifact_bounded
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


_OUTPUT_METADATA_COMMAND = "python3 -c " + shlex.quote('''
import hashlib, json, os
records = []
for root, directories, files in os.walk("output", followlinks=False):
    directories[:] = sorted(d for d in directories if not os.path.islink(os.path.join(root, d)))
    for name in sorted(files):
        path = os.path.join(root, name)
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        with open(path, "rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        records.append([os.path.relpath(path, "output"), digest, size])
print(json.dumps(records))
''')


async def _output_metadata(sandbox: Any) -> list[tuple[str, str, int]]:
    result = await sandbox.exec(_OUTPUT_METADATA_COMMAND, timeout=30)
    if not result.ok():
        raise RuntimeError("unable to enumerate sandbox output files")
    records = json.loads(result.stdout)
    candidates: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    for relative, digest, size in records:
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or relative in seen
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or type(size) is not int
            or size < 0
        ):
            raise RuntimeError("invalid sandbox output metadata")
        seen.add(relative)
        candidates.append((relative, digest, size))
    return sorted(candidates)


async def _read_output(sandbox: Any, relative: str, limit: int) -> bytes:
    stream = await sandbox.read(Path("output") / relative)
    try:
        payload = stream.read(limit + 1)
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


def remove_collected_artifacts(
    settings: AiAssistantSettings, artifacts: list[RuntimeArtifact],
) -> None:
    """Roll back outputs that were collected but never emitted as complete."""
    targets = [
        resolve_storage_key(settings.storage_root, artifact.storage_key)
        for artifact in artifacts
    ]
    _remove_host_artifacts(settings.storage_root, targets)


async def collect_output_artifacts(
    settings: AiAssistantSettings,
    conversation_id: UUID,
    sandbox: Any,
    before: dict[str, str],
) -> list[RuntimeArtifact]:
    """Persist every sandbox output that changed since ``before``, atomically."""
    after = await _output_metadata(sandbox)
    limit = settings.max_artifact_bytes
    total_limit = settings.max_total_artifact_bytes
    candidates = [
        (relative, size)
        for relative, digest, size in after
        if before.get(relative) != digest
    ]
    for relative, size in candidates:
        if size > limit:
            raise RuntimeError(f"generated artifact exceeds configured limit: {relative}")
    if sum(size for _, size in candidates) > total_limit:
        raise RuntimeError("generated artifacts exceed configured aggregate limit")
    artifacts: list[RuntimeArtifact] = []
    written: list[Path] = []
    actual_total = 0
    try:
        for relative, _ in candidates:
            payload = await _read_output(sandbox, relative, limit)
            actual_total += len(payload)
            if actual_total > total_limit:
                del payload
                raise RuntimeError("generated artifacts exceed configured aggregate limit")
            artifact_id = uuid4()
            filename = safe_artifact_filename(relative, artifact_id)
            storage_key = (
                Path("output") / str(conversation_id) / str(artifact_id) / filename
            ).as_posix()
            target = resolve_storage_key(settings.storage_root, storage_key)
            # Never overwrite or roll back a pre-existing artifact directory,
            # even if an identifier unexpectedly collides.
            write_artifact_bounded(settings.storage_root, target, payload)
            written.append(target)
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
            del payload
    except BaseException:
        # CancelledError also rolls back only the targets reserved by this call.
        _remove_host_artifacts(settings.storage_root, written)
        raise
    return artifacts
