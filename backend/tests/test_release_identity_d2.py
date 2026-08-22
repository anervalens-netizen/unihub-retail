from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[2] / "scripts/release_identity.py"
SPEC = importlib.util.spec_from_file_location("release_identity", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
release_identity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_identity)

SOURCE_SHA = "a" * 40
ARCHIVE_SHA = "b" * 64


def write_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    migration_dir = repo / "backend/db/migrations"
    migration_dir.mkdir(parents=True)
    migration_payload = {
        "version": 1,
        "baseline": {"file": "schema_v2.sql", "sha256": "c" * 64, "incorporated_through": "001_first.sql"},
        "migrations": {
            "001_first.sql": "d" * 64,
            "069_final_head.sql": "e" * 64,
        },
    }
    (migration_dir / "manifest.json").write_text(json.dumps(migration_payload), encoding="utf-8")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    sbom = bundle / "SBOM.cdx.json"
    sbom.write_text('{"bomFormat":"CycloneDX"}\n', encoding="utf-8")
    sbom_sha = hashlib.sha256(sbom.read_bytes()).hexdigest()
    manifest = bundle / "RELEASE_MANIFEST.json"
    manifest.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "sourceSha": SOURCE_SHA,
                "archive": f"retail-release-{SOURCE_SHA}.tar.gz",
                "sha256": {
                    f"retail-release-{SOURCE_SHA}.tar.gz": ARCHIVE_SHA,
                    "SBOM.cdx.json": sbom_sha,
                },
            }
        ),
        encoding="utf-8",
    )
    return repo, manifest


def test_enrich_manifest_adds_deterministic_d2_identity(tmp_path: Path) -> None:
    repo, manifest_path = write_repo(tmp_path)
    manifest = release_identity.enrich_manifest(repo, manifest_path)
    assert manifest["releaseId"] == f"retail-release-{SOURCE_SHA}"
    assert manifest["migrationHead"] == "069_final_head.sql"
    assert manifest["artifactSha256"] == ARCHIVE_SHA
    assert manifest["sbomSha256"] == manifest["sha256"]["SBOM.cdx.json"]


def test_verify_manifest_returns_promotion_identity(tmp_path: Path) -> None:
    repo, manifest_path = write_repo(tmp_path)
    release_identity.enrich_manifest(repo, manifest_path)
    values = release_identity.verify_manifest(repo, manifest_path, SOURCE_SHA, ARCHIVE_SHA)
    assert values == {
        "CANDIDATE_SOURCE_SHA": SOURCE_SHA,
        "CANDIDATE_RELEASE_ID": f"retail-release-{SOURCE_SHA}",
        "CANDIDATE_MIGRATION_HEAD": "069_final_head.sql",
        "CANDIDATE_ARTIFACT_SHA256": ARCHIVE_SHA,
        "CANDIDATE_SBOM_SHA256": json.loads(manifest_path.read_text())["sbomSha256"],
    }


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("releaseId", "retail-release-" + "f" * 40, "releaseId mismatch"),
        ("migrationHead", "068_old.sql", "migration head mismatch"),
        ("artifactSha256", "f" * 64, "explicit artifact digest mismatch"),
        ("sbomSha256", "f" * 64, "explicit SBOM digest mismatch"),
    ],
)
def test_verify_manifest_rejects_tampered_d2_identity(
    tmp_path: Path, field: str, replacement: str, message: str
) -> None:
    repo, manifest_path = write_repo(tmp_path)
    release_identity.enrich_manifest(repo, manifest_path)
    payload = json.loads(manifest_path.read_text())
    payload[field] = replacement
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        release_identity.verify_manifest(repo, manifest_path, SOURCE_SHA, ARCHIVE_SHA)


def test_verify_manifest_rejects_changed_aggregate_sbom(tmp_path: Path) -> None:
    repo, manifest_path = write_repo(tmp_path)
    release_identity.enrich_manifest(repo, manifest_path)
    (manifest_path.parent / "SBOM.cdx.json").write_text('{"tampered":true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="aggregate SBOM file digest mismatch"):
        release_identity.verify_manifest(repo, manifest_path, SOURCE_SHA, ARCHIVE_SHA)


def test_migration_head_is_derived_not_hardcoded(tmp_path: Path) -> None:
    repo, _ = write_repo(tmp_path)
    path = repo / "backend/db/migrations/manifest.json"
    payload = json.loads(path.read_text())
    payload["migrations"]["070_next.sql"] = "f" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert release_identity.migration_head(repo) == "070_next.sql"
