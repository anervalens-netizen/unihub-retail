"""Fail-closed integrity helpers for monthly Grile artifacts.

The module is deliberately independent from PostgreSQL and Google clients.
It owns canonical manifest hashing, strict numeric parsing and filesystem
verification so orchestration cannot silently coerce or trust stale files.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping


MANIFEST_SCHEMA_VERSION = 1
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ZERO = Decimal("0")


class MonthlyIntegrityError(RuntimeError):
    """Safe operational failure carrying a non-sensitive machine code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_required_decimal(value: Any, *, field: str) -> Decimal:
    """Parse a required, finite, non-negative number without coercion to zero."""

    if value is None or value == "" or isinstance(value, bool):
        raise MonthlyIntegrityError("invalid_numeric_value", f"{field} is not a valid number")
    try:
        if isinstance(value, Decimal):
            parsed = value
        elif isinstance(value, int):
            parsed = Decimal(value)
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise InvalidOperation
            parsed = Decimal(str(value))
        elif isinstance(value, str):
            cleaned = value.strip().replace(" ", "")
            if not cleaned:
                raise InvalidOperation
            if "," in cleaned and "." in cleaned:
                cleaned = cleaned.replace(".", "").replace(",", ".")
            elif "," in cleaned:
                cleaned = cleaned.replace(",", ".")
            parsed = Decimal(cleaned)
        else:
            raise InvalidOperation
    except (InvalidOperation, ValueError) as exc:
        raise MonthlyIntegrityError(
            "invalid_numeric_value",
            f"{field} is not a valid number",
        ) from exc
    if not parsed.is_finite() or parsed < ZERO:
        raise MonthlyIntegrityError("invalid_numeric_value", f"{field} is not a valid number")
    return parsed


def decimal_text(value: Decimal) -> str:
    normalized = value.quantize(Decimal("0.01"))
    return format(normalized, "f")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("manifest_sha256", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_artifact(path: Path, *, root: Path, kind: str) -> dict[str, Any]:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise MonthlyIntegrityError("unsafe_artifact_path", "Artifact is outside the output root") from exc
    if not resolved_path.is_file() or resolved_path.stat().st_size <= 0:
        raise MonthlyIntegrityError("missing_artifact", "Artifact is missing or empty")
    return {
        "kind": kind,
        "path": relative.as_posix(),
        "bytes": resolved_path.stat().st_size,
        "sha256": file_sha256(resolved_path),
    }


def resolve_artifact_path(root: Path, relative_path: Any) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise MonthlyIntegrityError("unsafe_artifact_path", "Artifact path is invalid")
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise MonthlyIntegrityError("unsafe_artifact_path", "Artifact path is outside the output root") from exc
    return candidate


def verify_artifacts(manifest: Mapping[str, Any], *, root: Path) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise MonthlyIntegrityError("manifest_artifacts_missing", "Manifest has no artifacts")
    seen: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise MonthlyIntegrityError("manifest_artifact_invalid", "Manifest artifact is invalid")
        path = resolve_artifact_path(root, artifact.get("path"))
        relative = path.relative_to(root.resolve()).as_posix()
        if relative in seen:
            raise MonthlyIntegrityError("manifest_artifact_duplicate", "Manifest has duplicate artifacts")
        seen.add(relative)
        expected_hash = artifact.get("sha256")
        expected_bytes = artifact.get("bytes")
        if not isinstance(expected_hash, str) or not SHA256_PATTERN.fullmatch(expected_hash):
            raise MonthlyIntegrityError("manifest_hash_invalid", "Manifest artifact hash is invalid")
        if not isinstance(expected_bytes, int) or expected_bytes <= 0:
            raise MonthlyIntegrityError("manifest_size_invalid", "Manifest artifact size is invalid")
        if not path.is_file() or path.stat().st_size != expected_bytes:
            raise MonthlyIntegrityError("artifact_size_mismatch", "Manifest artifact size does not match")
        if file_sha256(path) != expected_hash:
            raise MonthlyIntegrityError("artifact_hash_mismatch", "Manifest artifact hash does not match")


def validate_verified_manifest(manifest: Mapping[str, Any], *, operation: str) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise MonthlyIntegrityError("manifest_schema_invalid", "Manifest schema is invalid")
    if manifest.get("operation") != operation:
        raise MonthlyIntegrityError("manifest_operation_invalid", "Manifest operation is invalid")
    if manifest.get("status") not in {"verified", "approved", "consumed"}:
        raise MonthlyIntegrityError("manifest_not_verified", "Manifest is not verified")
    expected = manifest.get("expected")
    processed = manifest.get("processed")
    if not isinstance(expected, Mapping) or not isinstance(processed, Mapping):
        raise MonthlyIntegrityError("manifest_coverage_invalid", "Manifest coverage is invalid")
    for key in ("stores", "agents"):
        value = expected.get(key)
        if not isinstance(value, int) or value <= 0 or processed.get(key) != value:
            raise MonthlyIntegrityError("manifest_coverage_incomplete", "Manifest coverage is incomplete")
    if operation == "finalize":
        source_registry = manifest.get("source_registry")
        if not isinstance(source_registry, list) or len(source_registry) != expected.get("stores"):
            raise MonthlyIntegrityError("manifest_registry_invalid", "Manifest registry is invalid")
        identities: set[tuple[str, str]] = set()
        for item in source_registry:
            if not isinstance(item, Mapping):
                raise MonthlyIntegrityError("manifest_registry_invalid", "Manifest registry is invalid")
            site_code = item.get("site_code")
            sheet_id = item.get("sheet_id")
            if (
                not isinstance(site_code, str)
                or not site_code.strip()
                or not isinstance(sheet_id, str)
                or not sheet_id.strip()
            ):
                raise MonthlyIntegrityError("manifest_registry_invalid", "Manifest registry is invalid")
            identities.add((site_code, sheet_id))
        if len(identities) != len(source_registry):
            raise MonthlyIntegrityError("manifest_registry_invalid", "Manifest registry is invalid")
    if manifest.get("error_count") != 0 or manifest.get("errors") not in ([], None):
        raise MonthlyIntegrityError("manifest_has_errors", "Manifest contains errors")
    claimed = manifest.get("manifest_sha256")
    if not isinstance(claimed, str) or not SHA256_PATTERN.fullmatch(claimed):
        raise MonthlyIntegrityError("manifest_hash_invalid", "Manifest hash is invalid")
    if manifest_sha256(manifest) != claimed:
        raise MonthlyIntegrityError("manifest_hash_mismatch", "Manifest hash does not match")


def finalize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    output = dict(manifest)
    output["manifest_sha256"] = manifest_sha256(output)
    return output


def base_manifest(
    *,
    month: str,
    operation: str,
    requested_by_sub: str,
    expected_stores: int,
    expected_agents: int,
    processed_stores: int,
    processed_agents: int,
    control_totals: Mapping[str, Any],
    artifacts: Iterable[Mapping[str, Any]],
    source_backups: Iterable[Mapping[str, Any]] = (),
    errors: Iterable[str] = (),
    status: str = "verified",
) -> dict[str, Any]:
    error_codes = sorted(set(errors))
    return finalize_manifest(
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "month": month,
            "operation": operation,
            "status": status,
            "expected": {"stores": expected_stores, "agents": expected_agents},
            "processed": {"stores": processed_stores, "agents": processed_agents},
            "control_totals": dict(control_totals),
            "error_count": len(error_codes),
            "errors": error_codes,
            "artifacts": [dict(item) for item in artifacts],
            "source_backups": [dict(item) for item in source_backups],
            "requested_by_sub": requested_by_sub,
            "approved_by_sub": None,
            "created_at": utc_now(),
        }
    )


def secure_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def secure_file(path: Path) -> None:
    if path.exists():
        os.chmod(path, 0o600)


def canonical_snapshot(value_ranges: Any) -> dict[str, Any]:
    if not isinstance(value_ranges, list):
        raise MonthlyIntegrityError("backup_response_invalid", "Google backup response is invalid")
    normalized: list[dict[str, Any]] = []
    for item in value_ranges:
        if not isinstance(item, Mapping) or not isinstance(item.get("range"), str):
            raise MonthlyIntegrityError("backup_response_invalid", "Google backup range is invalid")
        values = item.get("values", [])
        if not isinstance(values, list):
            raise MonthlyIntegrityError("backup_response_invalid", "Google backup values are invalid")
        normalized.append(
            {
                "range": item["range"],
                "majorDimension": item.get("majorDimension", "ROWS"),
                "values": values,
            }
        )
    return {"value_ranges": normalized}


def snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(snapshot)).hexdigest()
