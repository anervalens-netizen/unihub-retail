from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "release_authority",
    ROOT / "scripts/check_release_authority.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

repository_metadata_errors = MODULE.repository_metadata_errors
canonical_authority_errors = MODULE.canonical_authority_errors


def _repo(tmp_path: Path, files: dict[str, object]) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for relative, payload in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            payload if isinstance(payload, str) else json.dumps(payload),
            encoding="utf-8",
        )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    return tmp_path


def test_allows_unrelated_current_metadata(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "business/current.json": {
                "status": "current",
                "generation": "g1",
                "resource_id": "inventory-feed",
            }
        },
    )
    assert repository_metadata_errors(repo) == []


def test_allows_false_like_current_flags(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "business/disabled.json": {
                "current": False,
                "latest": "false",
                "artifact_sha256": "domain-artifact-not-release-authority",
            }
        },
    )
    assert repository_metadata_errors(repo) == []


def test_allows_existing_non_identity_release_labels(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            ".github/governance/high-risk-paths.json": {"deployReleaseCi": True},
            "scripts/frontend-critical-coverage.json": {
                "oldRelease": 1,
                "newRelease": 2,
            },
            "scripts/python-complexity-contract-v2.json": {"releaseBGates": []},
            "package-lock.json": {"nodeModulesNodeReleases": {}},
            "history/notes.json": {"release_notes": "historical prose"},
        },
    )
    assert repository_metadata_errors(repo) == []


def test_rejects_non_markdown_release_docs_metadata(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "docs/releases/latest.json": {"version": "v9"},
            "docs/releases/nested/current.yaml": "version: v9\n",
        },
    )
    errors = repository_metadata_errors(repo)
    assert len(errors) == 2
    assert all("Markdown-only historical evidence" in error for error in errors)


def test_rejects_current_release_paths_for_any_extension(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "config/current-release.yaml": "version: v9\n",
            "config/latestRelease.toml": 'version = "v9"\n',
            "config/currentQARelease.txt": "v9\n",
        },
    )
    errors = repository_metadata_errors(repo)
    assert len(errors) == 3
    assert all("current/latest release metadata path" in error for error in errors)


def test_rejects_plural_nested_current_release_paths(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "config/releases/latest.json": {"version": "v9"},
            "config/releases/current/metadata.json": {"version": "v9"},
        },
    )
    assert len(repository_metadata_errors(repo)) == 2


def test_rejects_camel_and_acronym_current_release_paths(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "config/currentRelease.json": {"version": "v9"},
            "config/latestRelease.json": {"version": "v9"},
            "config/currentQARelease.json": {"version": "v9"},
        },
    )
    assert len(repository_metadata_errors(repo)) == 3


def test_rejects_qualified_current_release_path(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {"config/current-production-release.json": {"version": "v9"}},
    )
    assert len(repository_metadata_errors(repo)) == 1


def test_rejects_release_identity_keys_without_status_dependency(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "config/name.json": {"release_name": "v9"},
            "config/version.json": {"release_version": "v9"},
            "config/status.json": {"release_status": "current"},
            "config/current.json": {"current_release": "v9"},
            "config/metadata.json": {
                "release_metadata": {"version": "v9", "status": "current"}
            },
            "config/container.json": {"release": {"version": "v9"}},
        },
    )
    assert len(repository_metadata_errors(repo)) == 6


def test_rejects_namespaced_release_identity_keys(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "config/version.json": {
                "status": "current",
                "production_release_version": "v9",
            },
            "config/status.json": {
                "production_release_status": "current",
                "artifact_sha256": "abc",
            },
        },
    )
    errors = repository_metadata_errors(repo)
    assert len(errors) >= 2
    assert any("productionreleaseversion" in error for error in errors)
    assert any("productionreleasestatus" in error for error in errors)


def test_rejects_release_identity_even_when_marked_historical(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "history/version.json": {
                "release_name": "v8.0.0",
                "status": "historical",
            }
        },
    )
    errors = repository_metadata_errors(repo)
    assert len(errors) == 1
    assert "releasename" in errors[0]


def test_scans_json_extensions_case_insensitively(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {"config/authority.JSON": {"release_name": "v99"}},
    )
    errors = repository_metadata_errors(repo)
    assert len(errors) == 1
    assert errors[0].startswith("config/authority.JSON:")


def test_rejects_current_support_identity_across_nested_objects(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "nested/source.json": {
                "status": "current",
                "metadata": {"source_sha": "abc"},
            },
            "nested/artifact.json": {
                "current": "v9",
                "metadata": {"artifact_sha256": "def"},
            },
            "nested/sbom.json": {
                "latest": {"id": "candidate"},
                "metadata": {"sbom_hash": "ghi"},
            },
        },
    )
    errors = repository_metadata_errors(repo)
    assert len(errors) == 3


def test_support_identity_matching_respects_key_boundaries(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "business/current.json": {
                "status": "current",
                "resource_id": "inventory-feed",
                "sourcecode_version": "v1",
            }
        },
    )
    assert repository_metadata_errors(repo) == []


def test_canonical_docs_require_manifest_authority_marker(tmp_path: Path) -> None:
    for relative in MODULE.CANONICAL_DOCS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("RELEASE_MANIFEST.json is authoritative.\n")
    assert canonical_authority_errors(tmp_path) == []


def test_canonical_docs_reject_retired_pointer(tmp_path: Path) -> None:
    for relative in MODULE.CANONICAL_DOCS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("RELEASE_MANIFEST.json is authoritative.\n")
    (tmp_path / "README.md").write_text(
        "RELEASE_MANIFEST.json is authoritative; see releases/current.json.\n"
    )
    errors = canonical_authority_errors(tmp_path)
    assert len(errors) == 1
    assert "retired" in errors[0]
