from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from salary_import_approval import (
    APPROVAL_ARTIFACT_TYPE,
    APPROVAL_SCHEMA_VERSION,
    KNOWN_GROUPS_TOTAL,
    REQUIRED_COMPANIES,
    SalaryImportApprovalError,
    canonical_json_bytes,
    canonical_json_sha256,
    load_and_validate_approval_artifact,
    require_apply_inputs,
    scan_runtime_salary_surfaces,
    validate_approval_artifact,
)


REVIEWER_KEY_ID = "synthetic-reviewer-key"
REVIEWER_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
TRUSTED_REVIEWER_KEYS = {
    REVIEWER_KEY_ID: base64.b64encode(
        REVIEWER_PRIVATE_KEY.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
}


def make_manifest(*, year: int = 2099, month: int = 7, companies: tuple[str, ...] = REQUIRED_COMPANIES) -> dict:
    return {
        "manifest_version": 1,
        "year": year,
        "month": month,
        "companies": [
            {
                "company_name": company,
                "source_file": f"synthetic-{company}.xlsx",
                "source_sha256": ("a" if company == "Mobiup" else "b") * 64,
                "row_count": 1,
                "control_total": "100.00",
                "mapped_site_rows": 1,
                "unmapped_locations": [],
            }
            for company in companies
        ],
        "row_count": len(companies),
        "control_total": f"{len(companies) * 100:.2f}",
    }


def make_artifact(manifest: dict, **overrides: object) -> dict:
    artifact = {
        "artifact_type": APPROVAL_ARTIFACT_TYPE,
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "decision": "approved",
        "manifest_sha256": canonical_json_sha256(manifest),
        "year": manifest["year"],
        "month": manifest["month"],
        "companies": list(REQUIRED_COMPANIES),
        "known_groups_total": KNOWN_GROUPS_TOTAL,
        "resolved_groups_count": KNOWN_GROUPS_TOTAL,
        "unresolved_groups_count": 0,
        "reviewer": "synthetic-independent-reviewer",
        "reviewer_key_id": REVIEWER_KEY_ID,
        "approval_timestamp": "2099-07-01T10:00:00+03:00",
        "approval_reference": "synthetic-approval-reference",
    }
    artifact.update(overrides)
    artifact["signature"] = base64.b64encode(
        REVIEWER_PRIVATE_KEY.sign(canonical_json_bytes(artifact))
    ).decode("ascii")
    return artifact


def validate(manifest: dict, artifact: dict | None = None, *, operator: str = "synthetic-operator"):
    manifest_sha256 = canonical_json_sha256(manifest)
    return validate_approval_artifact(
        artifact or make_artifact(manifest),
        manifest=manifest,
        expected_manifest_sha256=manifest_sha256,
        applied_by=operator,
        trusted_reviewer_keys=TRUSTED_REVIEWER_KEYS,
    )


def test_apply_requires_manifest_hash_and_approval_artifact() -> None:
    with pytest.raises(SalaryImportApprovalError):
        require_apply_inputs(None, None)
    with pytest.raises(SalaryImportApprovalError):
        require_apply_inputs("a" * 64, None)
    with pytest.raises(SalaryImportApprovalError):
        require_apply_inputs(None, Path("approval.json"))


def test_tampered_manifest_or_expected_hash_fails_closed() -> None:
    manifest = make_manifest()
    artifact = make_artifact(manifest)
    tampered = dict(manifest)
    tampered["control_total"] = "101.00"
    with pytest.raises(SalaryImportApprovalError):
        validate_approval_artifact(
            artifact,
            manifest=tampered,
            expected_manifest_sha256=artifact["manifest_sha256"],
            applied_by="synthetic-operator",
            trusted_reviewer_keys=TRUSTED_REVIEWER_KEYS,
        )
    with pytest.raises(SalaryImportApprovalError):
        validate_approval_artifact(
            artifact,
            manifest=manifest,
            expected_manifest_sha256="c" * 64,
            applied_by="synthetic-operator",
            trusted_reviewer_keys=TRUSTED_REVIEWER_KEYS,
        )


@pytest.mark.parametrize(
    ("manifest", "artifact_overrides"),
    [
        (make_manifest(year=2098), {"year": 2099}),
        (make_manifest(companies=("Mobiup", "Other")), {}),
        (make_manifest(), {"year": 2098}),
        (make_manifest(), {"companies": ["Mobiup", "Other"]}),
    ],
)
def test_period_and_company_scope_are_exact(manifest: dict, artifact_overrides: dict) -> None:
    artifact = make_artifact(manifest, **artifact_overrides)
    with pytest.raises(SalaryImportApprovalError):
        validate(manifest, artifact)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("known_groups_total", 7),
        ("known_groups_total", 9),
        ("resolved_groups_count", 7),
        ("resolved_groups_count", 9),
        ("unresolved_groups_count", 1),
    ],
)
def test_known_group_resolution_is_exact(field: str, value: int) -> None:
    manifest = make_manifest()
    with pytest.raises(SalaryImportApprovalError):
        validate(manifest, make_artifact(manifest, **{field: value}))


def test_decision_must_be_explicitly_approved() -> None:
    manifest = make_manifest()
    with pytest.raises(SalaryImportApprovalError):
        validate(manifest, make_artifact(manifest, decision="pending"))


def test_signature_and_trusted_reviewer_key_are_mandatory() -> None:
    manifest = make_manifest()
    artifact = make_artifact(manifest)
    artifact["approval_reference"] = "tampered-after-signing"
    with pytest.raises(SalaryImportApprovalError, match="signature"):
        validate(manifest, artifact)
    with pytest.raises(SalaryImportApprovalError, match="not trusted"):
        validate_approval_artifact(
            make_artifact(manifest),
            manifest=manifest,
            expected_manifest_sha256=canonical_json_sha256(manifest),
            applied_by="synthetic-operator",
            trusted_reviewer_keys={"another-key": TRUSTED_REVIEWER_KEYS[REVIEWER_KEY_ID]},
        )


def test_reviewer_must_be_independent_after_normalization() -> None:
    manifest = make_manifest()
    with pytest.raises(SalaryImportApprovalError):
        validate(
            manifest,
            make_artifact(manifest, reviewer="Reviewer Name"),
            operator=" reviewer   name ",
        )
    with pytest.raises(SalaryImportApprovalError):
        validate(
            manifest,
            make_artifact(manifest, reviewer="  Synthetic   Operator "),
            operator="synthetic operator",
        )


def test_approval_rejects_private_identity_keys_or_values() -> None:
    manifest = make_manifest()
    with pytest.raises(SalaryImportApprovalError):
        validate(manifest, make_artifact(manifest, cnp="opaque-synthetic-private"))
    with pytest.raises(SalaryImportApprovalError):
        validate(manifest, make_artifact(manifest, approval_reference="opaque 1 2 3 4 5 6 7 8 9 0 1 2 3"))


def test_artifact_file_hash_is_recorded_without_loading_dotenv(tmp_path: Path) -> None:
    manifest = make_manifest()
    artifact = make_artifact(manifest)
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(artifact, sort_keys=True), encoding="utf-8")
    validated = load_and_validate_approval_artifact(
        path,
        manifest=manifest,
        expected_manifest_sha256=canonical_json_sha256(manifest),
        applied_by="synthetic-operator",
        trusted_reviewer_keys=TRUSTED_REVIEWER_KEYS,
    )
    assert len(validated.artifact_sha256) == 64
    assert validated.metadata["decision"] == "approved"
    compact_path = tmp_path / "approval-compact.json"
    compact_path.write_text(
        json.dumps(artifact, sort_keys=False, separators=(",", ":")),
        encoding="utf-8",
    )
    compact = load_and_validate_approval_artifact(
        compact_path,
        manifest=manifest,
        expected_manifest_sha256=canonical_json_sha256(manifest),
        applied_by="synthetic-operator",
        trusted_reviewer_keys=TRUSTED_REVIEWER_KEYS,
    )
    assert compact.artifact_sha256 == validated.artifact_sha256


def test_runtime_salary_surface_scan_passes_and_rejects_raw_identity(tmp_path: Path) -> None:
    scan_runtime_salary_surfaces(Path(__file__).resolve().parents[2])
    runtime = tmp_path / "backend" / "routers"
    runtime.mkdir(parents=True)
    (runtime / "salarii.py").write_text("def salary():\n    return {'cnp': 'forbidden'}\n", encoding="utf-8")
    with pytest.raises(SalaryImportApprovalError):
        scan_runtime_salary_surfaces(tmp_path)
    canonical_json_bytes,
