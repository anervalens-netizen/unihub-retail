"""Private, content-addressed filesystem lifecycle for sales import sources."""

from __future__ import annotations

import os
import re
import time
from hashlib import sha256
from pathlib import Path
from uuid import uuid4


DEFAULT_SALES_IMPORT_SPOOL_MAX_AGE_SECONDS = 24 * 60 * 60
_SALES_ARTIFACT_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IMPORT_SPOOL_NAMESPACE = re.compile(r"^[0-9a-f]{64}$")


class SalesImportArtifactError(RuntimeError):
    pass


class SalesImportArtifactConflictError(SalesImportArtifactError):
    pass


def get_sales_import_spool_dir() -> Path:
    configured = os.getenv("SALES_IMPORT_SPOOL_DIR")
    path = (
        Path(configured).expanduser()
        if configured
        else Path(__file__).resolve().parents[2] / "data" / "import_spool"
    )
    return path.resolve()


def _sales_spool_path(path: str | Path) -> Path:
    root = get_sales_import_spool_dir()
    raw = Path(path)
    if raw.is_symlink():
        raise SalesImportArtifactError("Sales import spool symlink is not allowed")
    candidate = raw.resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Sales import spool path escapes the configured directory")
    return candidate


def _artifact_digest_from_path(path: Path) -> str:
    digest = path.name.rsplit(".", 1)[0]
    if not _SALES_ARTIFACT_DIGEST.fullmatch(digest):
        raise SalesImportArtifactError("Sales import artifact name is not content-addressed")
    return digest


def _file_digest_and_size(path: Path) -> tuple[str, int]:
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise SalesImportArtifactError("Sales import artifact is not a regular file")
    digest = sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _fsync_file(path: Path) -> None:
    with path.open("rb") as source:
        os.fsync(source.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def verify_sales_import_artifact(
    path: str | Path,
    expected_digest: str,
    expected_bytes: int | None = None,
) -> int:
    candidate = _sales_spool_path(path)
    digest, size = _file_digest_and_size(candidate)
    if digest != expected_digest or (expected_bytes is not None and size != expected_bytes):
        raise SalesImportArtifactError("Sales import artifact integrity check failed")
    return size


def resolve_sales_import_artifact(
    path: str | Path,
    expected_digest: str,
    expected_bytes: int | None = None,
) -> Path:
    """Resolve the queued upload or its canonical retained successor."""
    if not _SALES_ARTIFACT_DIGEST.fullmatch(expected_digest):
        raise ValueError("Invalid sales import artifact digest")
    candidate = _sales_spool_path(path)
    if candidate.exists():
        try:
            verify_sales_import_artifact(candidate, expected_digest, expected_bytes)
        except SalesImportArtifactError:
            pass
        else:
            return candidate
    retained = _sales_spool_path(
        get_sales_import_spool_dir() / "retained" / f"{expected_digest}.source"
    )
    verify_sales_import_artifact(retained, expected_digest, expected_bytes)
    return retained


def stage_sales_import_spool_file(
    content: bytes,
    digest: str,
    *,
    namespace: str | None = None,
) -> Path:
    if not _SALES_ARTIFACT_DIGEST.fullmatch(digest):
        raise ValueError("Invalid sales import source digest")
    if namespace is not None and not _IMPORT_SPOOL_NAMESPACE.fullmatch(namespace):
        raise ValueError("Invalid import spool namespace")
    spool_dir = get_sales_import_spool_dir()
    spool_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    spool_dir.chmod(0o700)
    artifact_stem = f"{digest}.{namespace}" if namespace is not None else digest
    destination = spool_dir / f"{artifact_stem}.upload"
    temporary = spool_dir / f".{artifact_stem}.{uuid4().hex}.tmp"
    if destination.exists():
        actual_digest, actual_size = _file_digest_and_size(destination)
        if actual_digest != digest or actual_size != len(content):
            raise SalesImportArtifactConflictError("Conflicting content-addressed sales source")
        destination.chmod(0o600)
        _fsync_file(destination)
        _fsync_directory(spool_dir)
        return destination
    try:
        temporary.write_bytes(content)
        temporary.chmod(0o600)
        _fsync_file(temporary)
        actual_digest, actual_size = _file_digest_and_size(temporary)
        if actual_digest != digest or actual_size != len(content):
            raise SalesImportArtifactError("Staged sales source integrity check failed")
        temporary.replace(destination)
        destination.chmod(0o600)
        _fsync_file(destination)
        _fsync_directory(spool_dir)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def remove_sales_import_spool_file(path: str | Path) -> None:
    _sales_spool_path(path).unlink(missing_ok=True)


def retain_sales_import_spool_file(
    path: str | Path,
    *,
    import_month: str,
    snapshot_id: int,
    expected_digest: str | None = None,
    expected_bytes: int | None = None,
) -> Path:
    del import_month, snapshot_id  # Retained for the stable public call contract.
    candidate = _sales_spool_path(path)
    spool_dir = get_sales_import_spool_dir()
    digest = expected_digest or _artifact_digest_from_path(candidate)
    if not _SALES_ARTIFACT_DIGEST.fullmatch(digest):
        raise ValueError("Invalid sales import artifact digest")
    retained_dir = spool_dir / "retained"
    retained_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    retained_dir.chmod(0o700)
    destination = _sales_spool_path(retained_dir / f"{digest}.source")
    if destination.exists():
        actual_digest, actual_size = _file_digest_and_size(destination)
        if actual_digest != digest or (expected_bytes is not None and actual_size != expected_bytes):
            raise SalesImportArtifactConflictError("Conflicting retained sales artifact")
        destination.chmod(0o600)
        _fsync_file(destination)
        if candidate != destination and candidate.exists():
            candidate.unlink()
            _fsync_directory(candidate.parent)
        _fsync_directory(retained_dir)
        return destination
    if not candidate.exists():
        raise SalesImportArtifactError("Sales source disappeared before retain")
    actual_digest, actual_size = _file_digest_and_size(candidate)
    if actual_digest != digest or (expected_bytes is not None and actual_size != expected_bytes):
        raise SalesImportArtifactError("Sales source integrity check failed before retain")
    candidate.replace(destination)
    destination.chmod(0o600)
    _fsync_file(destination)
    _fsync_directory(retained_dir)
    actual_digest, actual_size = _file_digest_and_size(destination)
    if actual_digest != digest or (expected_bytes is not None and actual_size != expected_bytes):
        raise SalesImportArtifactError("Retained sales artifact readback failed")
    return destination


def cleanup_sales_import_retained_artifacts(keep_paths: set[str]) -> int:
    retained_dir = get_sales_import_spool_dir() / "retained"
    if not retained_dir.exists():
        return 0
    keep = {_sales_spool_path(path) for path in keep_paths}
    removed = 0
    for candidate in retained_dir.rglob("*.source"):
        if candidate.resolve() not in keep:
            candidate.unlink(missing_ok=True)
            removed += 1
    if removed:
        _fsync_directory(retained_dir)
    return removed


def read_sales_import_spool_file(path: str, expected_digest: str) -> bytes:
    content = _sales_spool_path(path).read_bytes()
    if sha256(content).hexdigest() != expected_digest:
        raise ValueError("Sales import spool integrity check failed")
    return content


def cleanup_stale_sales_import_spool_files() -> int:
    spool_dir = get_sales_import_spool_dir()
    if not spool_dir.exists():
        return 0
    max_age = int(
        os.getenv(
            "SALES_IMPORT_SPOOL_MAX_AGE_SECONDS",
            str(DEFAULT_SALES_IMPORT_SPOOL_MAX_AGE_SECONDS),
        )
    )
    if max_age < 3600:
        raise ValueError("SALES_IMPORT_SPOOL_MAX_AGE_SECONDS must be at least one hour")
    cutoff = time.time() - max_age
    removed = 0
    for pattern in ("*.upload", ".*.tmp"):
        for candidate in spool_dir.glob(pattern):
            if candidate.is_file() and candidate.stat().st_mtime < cutoff:
                candidate.unlink(missing_ok=True)
                removed += 1
    return removed
