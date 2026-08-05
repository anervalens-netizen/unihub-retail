"""Fail-closed approval and privacy gates for the official salary import."""

from __future__ import annotations

import hashlib
import ast
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

APPROVAL_ARTIFACT_TYPE = "unihub.salary_import.approval"
APPROVAL_SCHEMA_VERSION = 1
AUDIT_ENVELOPE_VERSION = 1
KNOWN_GROUPS_TOTAL = 8
REQUIRED_COMPANIES = ("Mobiup", "Mobicell")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_APPROVAL_KEYS = frozenset(
    {
        "artifact_type",
        "schema_version",
        "decision",
        "manifest_sha256",
        "year",
        "month",
        "companies",
        "known_groups_total",
        "resolved_groups_count",
        "unresolved_groups_count",
        "reviewer",
        "approval_timestamp",
        "approval_reference",
    }
)
_ENVELOPE_KEYS = frozenset(
    {
        "audit_envelope_version",
        "dry_run_manifest",
        "dry_run_manifest_sha256",
        "approval_metadata",
        "approval_artifact_sha256",
        "applied_by",
    }
)
_FORBIDDEN_IDENTITY_KEY_PARTS = frozenset(
    {
        "cnp",
        "salary_cnp",
        "raw_cnp",
        "person_id",
        "salary_private",
        "identity_key",
        "identity_source",
        "normalized_name",
        "full_name",
    }
)
_PRIVATE_IDENTITY_VALUE = re.compile(r"(?<!\d)\d(?:[\s-]?\d){12}(?!\d)")


class SalaryImportApprovalError(ValueError):
    """A safe, non-sensitive explanation for a rejected approval."""


@dataclass(frozen=True)
class ValidatedApproval:
    """Validated metadata that is safe to place in the salary audit envelope."""

    metadata: dict[str, Any]
    manifest: dict[str, Any]
    manifest_sha256: str
    artifact_sha256: str
    applied_by: str

    def envelope(self) -> dict[str, Any]:
        return build_audit_envelope(
            self.manifest,
            self.manifest_sha256,
            self.metadata,
            self.artifact_sha256,
            self.applied_by,
        )


def canonical_json_sha256(value: Any) -> str:
    """Return the stable SHA-256 for a JSON-compatible value."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalise_comparison(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _is_forbidden_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    return normalized in _FORBIDDEN_IDENTITY_KEY_PARTS or any(
        part in _FORBIDDEN_IDENTITY_KEY_PARTS for part in normalized.split("_")
    )


def _assert_no_private_identity_material(value: Any, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise SalaryImportApprovalError("Approval contains a non-text key")
            if _is_forbidden_key(key):
                raise SalaryImportApprovalError("Approval contains a forbidden identity field")
            _assert_no_private_identity_material(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_no_private_identity_material(child, f"{path}[{index}]")
        return
    if isinstance(value, str) and _PRIVATE_IDENTITY_VALUE.search(value):
        raise SalaryImportApprovalError("Approval contains private identity material")


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise SalaryImportApprovalError(f"{field} must be a lowercase SHA-256")
    return value


def _require_nonblank(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SalaryImportApprovalError(f"{field} is required")
    return value.strip()


def _require_int(value: Any, field: str, expected: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SalaryImportApprovalError(f"{field} must be an integer")
    if expected is not None and value != expected:
        raise SalaryImportApprovalError(f"{field} is not approved")
    return value


def validate_dry_run_manifest(
    manifest: Mapping[str, Any],
    *,
    expected_sha256: str | None = None,
    year: int | None = None,
    month: int | None = None,
) -> dict[str, Any]:
    """Validate the public, identity-free shape of a dry-run manifest."""

    if not isinstance(manifest, Mapping):
        raise SalaryImportApprovalError("Dry-run manifest must be an object")
    _assert_no_private_identity_material(manifest)
    normalized = json.loads(json.dumps(manifest, ensure_ascii=False))
    if normalized.get("manifest_version") != 1:
        raise SalaryImportApprovalError("Unsupported dry-run manifest version")
    manifest_year = _require_int(normalized.get("year"), "manifest.year")
    manifest_month = _require_int(normalized.get("month"), "manifest.month")
    if year is not None and manifest_year != year:
        raise SalaryImportApprovalError("Dry-run period does not match approval")
    if month is not None and manifest_month != month:
        raise SalaryImportApprovalError("Dry-run period does not match approval")
    companies = normalized.get("companies")
    if not isinstance(companies, list) or [item.get("company_name") for item in companies if isinstance(item, Mapping)] != list(REQUIRED_COMPANIES):
        raise SalaryImportApprovalError("Dry-run must contain exactly both required companies")
    for company in companies:
        if not isinstance(company, Mapping):
            raise SalaryImportApprovalError("Dry-run company entry must be an object")
        if _require_nonblank(company.get("company_name"), "company_name") not in REQUIRED_COMPANIES:
            raise SalaryImportApprovalError("Dry-run contains an unsupported company")
        _require_sha256(company.get("source_sha256"), "source_sha256")
        _require_int(company.get("row_count"), "company.row_count")
        _require_nonblank(company.get("control_total"), "company.control_total")
        locations = company.get("unmapped_locations", [])
        if not isinstance(locations, list) or not all(isinstance(item, str) for item in locations):
            raise SalaryImportApprovalError("unmapped_locations must be a string list")
    _require_int(normalized.get("row_count"), "manifest.row_count")
    _require_nonblank(normalized.get("control_total"), "manifest.control_total")
    if expected_sha256 is not None:
        expected = _require_sha256(expected_sha256, "expected manifest SHA-256")
        actual = canonical_json_sha256(normalized)
        if actual != expected:
            raise SalaryImportApprovalError("Dry-run manifest SHA-256 mismatch")
    return normalized


def _validate_approval_metadata(
    artifact: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    manifest_sha256: str,
    applied_by: str,
) -> dict[str, Any]:
    _assert_no_private_identity_material(artifact)
    unknown = set(artifact) - _APPROVAL_KEYS
    missing = _APPROVAL_KEYS - set(artifact)
    if unknown:
        raise SalaryImportApprovalError("Approval contains unsupported fields")
    if missing:
        raise SalaryImportApprovalError("Approval is missing required fields")
    if artifact["artifact_type"] != APPROVAL_ARTIFACT_TYPE:
        raise SalaryImportApprovalError("Approval artifact type is invalid")
    _require_int(artifact["schema_version"], "schema_version", APPROVAL_SCHEMA_VERSION)
    if artifact["decision"] != "approved":
        raise SalaryImportApprovalError("Approval decision is not approved")
    if _require_sha256(artifact["manifest_sha256"], "manifest_sha256") != manifest_sha256:
        raise SalaryImportApprovalError("Approval is bound to another manifest")
    if _require_int(artifact["year"], "approval.year") != manifest["year"]:
        raise SalaryImportApprovalError("Approval period does not match manifest")
    if _require_int(artifact["month"], "approval.month") != manifest["month"]:
        raise SalaryImportApprovalError("Approval period does not match manifest")
    if artifact["companies"] != list(REQUIRED_COMPANIES):
        raise SalaryImportApprovalError("Approval company scope is invalid")
    _require_int(artifact["known_groups_total"], "known_groups_total", KNOWN_GROUPS_TOTAL)
    _require_int(artifact["resolved_groups_count"], "resolved_groups_count", KNOWN_GROUPS_TOTAL)
    _require_int(artifact["unresolved_groups_count"], "unresolved_groups_count", 0)
    reviewer = _require_nonblank(artifact["reviewer"], "reviewer")
    operator = _require_nonblank(applied_by, "applied_by")
    if _normalise_comparison(reviewer) == _normalise_comparison(operator):
        raise SalaryImportApprovalError("Independent reviewer must differ from operator")
    timestamp = _require_nonblank(artifact["approval_timestamp"], "approval_timestamp")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SalaryImportApprovalError("approval_timestamp must be ISO-8601") from exc
    if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
        raise SalaryImportApprovalError("approval_timestamp must include a timezone")
    reference = _require_nonblank(artifact["approval_reference"], "approval_reference")
    return {
        "artifact_type": APPROVAL_ARTIFACT_TYPE,
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "decision": "approved",
        "manifest_sha256": manifest_sha256,
        "year": manifest["year"],
        "month": manifest["month"],
        "companies": list(REQUIRED_COMPANIES),
        "known_groups_total": KNOWN_GROUPS_TOTAL,
        "resolved_groups_count": KNOWN_GROUPS_TOTAL,
        "unresolved_groups_count": 0,
        "reviewer": reviewer,
        "approval_timestamp": timestamp,
        "approval_reference": reference,
    }


def validate_approval_artifact(
    artifact: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    expected_manifest_sha256: str,
    applied_by: str,
) -> ValidatedApproval:
    normalized_manifest = validate_dry_run_manifest(
        manifest,
        expected_sha256=expected_manifest_sha256,
    )
    manifest_sha256 = _require_sha256(expected_manifest_sha256, "expected manifest SHA-256")
    metadata = _validate_approval_metadata(
        artifact,
        manifest=normalized_manifest,
        manifest_sha256=manifest_sha256,
        applied_by=applied_by,
    )
    return ValidatedApproval(
        metadata=metadata,
        manifest=normalized_manifest,
        manifest_sha256=manifest_sha256,
        artifact_sha256="",
        applied_by=_require_nonblank(applied_by, "applied_by"),
    )


def load_and_validate_approval_artifact(
    path: Path,
    *,
    manifest: Mapping[str, Any],
    expected_manifest_sha256: str,
    applied_by: str,
) -> ValidatedApproval:
    if path.name.startswith(".env"):
        raise SalaryImportApprovalError("Approval artifact path is not allowed")
    raw = path.read_bytes()
    try:
        artifact = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SalaryImportApprovalError("Approval artifact must be UTF-8 JSON") from exc
    if not isinstance(artifact, Mapping):
        raise SalaryImportApprovalError("Approval artifact must be an object")
    validated = validate_approval_artifact(
        artifact,
        manifest=manifest,
        expected_manifest_sha256=expected_manifest_sha256,
        applied_by=applied_by,
    )
    return ValidatedApproval(
        metadata=validated.metadata,
        manifest=validated.manifest,
        manifest_sha256=validated.manifest_sha256,
        artifact_sha256=sha256_bytes(raw),
        applied_by=validated.applied_by,
    )


def require_apply_inputs(expected_manifest_sha256: str | None, approval_artifact: Path | None) -> None:
    if not expected_manifest_sha256 or approval_artifact is None:
        raise SalaryImportApprovalError(
            "--apply requires both --expected-manifest-sha256 and --approval-artifact"
        )
    _require_sha256(expected_manifest_sha256, "expected manifest SHA-256")


def build_audit_envelope(
    manifest: Mapping[str, Any],
    manifest_sha256: str,
    approval_metadata: Mapping[str, Any],
    approval_artifact_sha256: str,
    applied_by: str,
) -> dict[str, Any]:
    normalized_manifest = validate_dry_run_manifest(manifest, expected_sha256=manifest_sha256)
    _require_sha256(approval_artifact_sha256, "approval artifact SHA-256")
    _assert_no_private_identity_material(approval_metadata)
    safe_metadata = _validate_approval_metadata(
        approval_metadata,
        manifest=normalized_manifest,
        manifest_sha256=manifest_sha256,
        applied_by=applied_by,
    )
    return {
        "audit_envelope_version": AUDIT_ENVELOPE_VERSION,
        "dry_run_manifest": normalized_manifest,
        "dry_run_manifest_sha256": manifest_sha256,
        "approval_metadata": safe_metadata,
        "approval_artifact_sha256": approval_artifact_sha256,
        "applied_by": _require_nonblank(applied_by, "applied_by"),
    }


def validate_audit_envelope(
    envelope: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    manifest_sha256: str,
    applied_by: str,
) -> dict[str, Any]:
    if not isinstance(envelope, Mapping):
        raise SalaryImportApprovalError("Validated approval envelope is required")
    _assert_no_private_identity_material(envelope)
    if set(envelope) != _ENVELOPE_KEYS:
        raise SalaryImportApprovalError("Approval envelope shape is invalid")
    if envelope["audit_envelope_version"] != AUDIT_ENVELOPE_VERSION:
        raise SalaryImportApprovalError("Unsupported approval envelope version")
    safe_manifest = validate_dry_run_manifest(manifest, expected_sha256=manifest_sha256)
    if envelope["dry_run_manifest"] != safe_manifest:
        raise SalaryImportApprovalError("Approval envelope manifest mismatch")
    if envelope["dry_run_manifest_sha256"] != manifest_sha256:
        raise SalaryImportApprovalError("Approval envelope SHA-256 mismatch")
    safe_metadata = _validate_approval_metadata(
        envelope["approval_metadata"],
        manifest=safe_manifest,
        manifest_sha256=manifest_sha256,
        applied_by=applied_by,
    )
    safe_applied_by = _require_nonblank(applied_by, "applied_by")
    if envelope["applied_by"] != safe_applied_by:
        raise SalaryImportApprovalError("Approval envelope operator mismatch")
    return build_audit_envelope(
        safe_manifest,
        manifest_sha256,
        safe_metadata,
        _require_sha256(envelope["approval_artifact_sha256"], "approval artifact SHA-256"),
        safe_applied_by,
    )


def _runtime_salary_files(repo_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for relative_dir in ("backend/routers", "backend/services", "backend/repositories", "backend/schemas"):
        directory = repo_root / relative_dir
        if directory.is_dir():
            candidates.extend(directory.glob("*.py"))
    src = repo_root / "src"
    if src.is_dir():
        candidates.extend(
            path
            for pattern in ("**/*.ts", "**/*.tsx")
            for path in src.glob(pattern)
            if ".env" not in path.name.casefold()
            and ".test." not in path.name.casefold()
            and "test" not in path.parts
        )
    return sorted(set(candidates))


def scan_runtime_salary_surfaces(repo_root: Path) -> None:
    """Reject raw identity fields/routes in runtime salary surfaces."""

    violations: list[str] = []
    for path in _runtime_salary_files(repo_root):
        if path.name.startswith(".env"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise SalaryImportApprovalError("Cannot scan runtime salary surface") from exc
        if path.suffix == ".py":
            try:
                tree = ast.parse(text, filename=str(path))
            except SyntaxError as exc:
                raise SalaryImportApprovalError("Cannot parse runtime salary surface") from exc
            for node in ast.walk(tree):
                identifier: str | None = None
                if isinstance(node, ast.Name):
                    identifier = node.id
                elif isinstance(node, ast.arg):
                    identifier = node.arg
                elif isinstance(node, ast.Attribute):
                    identifier = node.attr
                if identifier and identifier.casefold() in {"cnp", "salary_cnp"}:
                    violations.append(
                        f"{path.relative_to(repo_root)}:{getattr(node, 'lineno', 0)}:{identifier.casefold()}"
                    )
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    literal = node.value.casefold()
                    if literal in {"cnp", "salary_cnp"} or re.search(
                        r"history/\s*\{\s*cnp\s*\}", literal
                    ):
                        violations.append(
                            f"{path.relative_to(repo_root)}:{getattr(node, 'lineno', 0)}:raw_identity_literal"
                        )
        else:
            for line_number, line in enumerate(text.splitlines(), start=1):
                if re.search(r"\bcnp\b|salary[_-]?cnp|history/\s*\{\s*cnp\s*\}", line, re.I):
                    violations.append(
                        f"{path.relative_to(repo_root)}:{line_number}:raw_identity"
                    )
    if violations:
        raise SalaryImportApprovalError("Runtime salary privacy gate failed: " + ", ".join(violations))
