from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "docs_contract",
    ROOT / "scripts/check_docs_contract.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
release_pointer_errors = MODULE._release_pointer_errors
markdown_link_targets = MODULE._markdown_link_targets


def _repo(tmp_path: Path, files: dict[str, object]) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for relative, payload in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    return tmp_path


def test_release_pointer_guard_allows_unrelated_current_metadata(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"business/current.json": {"status": "current", "generation": "g1"}})
    assert release_pointer_errors(repo) == []


def test_release_pointer_guard_rejects_renamed_pointer_under_release_docs(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "docs/releases/latest.json": {
                "release_name": "v9.0.0",
                "evidence_document": "docs/releases/v9.0.0.md",
                "status": "current",
            }
        },
    )
    errors = release_pointer_errors(repo)
    assert len(errors) == 1
    assert errors[0].startswith("docs/releases/latest.json:")


def test_release_pointer_guard_rejects_plural_nested_release_paths(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "docs/releases/current/metadata.json": {"version": "v9"},
            "config/releases/latest.json": {"version": "v9"},
        },
    )
    errors = release_pointer_errors(repo)
    assert len(errors) == 2
    assert errors[0].startswith("config/releases/latest.json:")
    assert errors[1].startswith("docs/releases/current/metadata.json:")


def test_release_pointer_guard_rejects_pointer_anywhere_in_repository(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "docs/current-release.json": {
                "release_name": "v9.0.0",
                "evidence_document": "docs/releases/v9.0.0.md",
                "status": "current",
            },
            "nested/metadata.json": {"wrapper": {"status": "current", "sourceSha": "abc123"}},
        },
    )
    errors = release_pointer_errors(repo)
    assert len(errors) == 2
    assert errors[0].startswith("docs/current-release.json:")
    assert errors[1].startswith("nested/metadata.json:")


def test_release_pointer_guard_propagates_current_semantics_across_nested_objects(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {"nested/metadata.json": {"status": "current", "metadata": {"source_sha": "abc123"}}},
    )
    errors = release_pointer_errors(repo)
    assert len(errors) == 1
    assert errors[0].startswith("nested/metadata.json:")


def test_release_pointer_guard_rejects_current_release_filename_with_generic_payload(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"docs/current-release.json": {"version": "v9.9.9"}})
    errors = release_pointer_errors(repo)
    assert len(errors) == 1
    assert errors[0].startswith("docs/current-release.json:")


def test_release_pointer_guard_rejects_nonhistorical_release_identity_without_current_status(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"config/release-info.json": {"release_name": "v9.9.9"}})
    errors = release_pointer_errors(repo)
    assert len(errors) == 1
    assert errors[0].startswith("config/release-info.json:")


def test_release_pointer_guard_rejects_current_release_key_without_status(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "docs/current-release.json": {
                "current_release": "v9.9.9",
                "evidence_document": "docs/releases/v2.1.0.md",
            }
        },
    )
    errors = release_pointer_errors(repo)
    assert len(errors) == 1
    assert errors[0].startswith("docs/current-release.json:")


def test_release_pointer_guard_allows_historical_release_metadata(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"history/release.json": {"release_name": "v8.0.0", "status": "historical"}})
    assert release_pointer_errors(repo) == []


def test_markdown_link_targets_include_inline_and_reference_style() -> None:
    text = "[inline](docs/catalog.json)\n[release][release-ref]\n[release-ref]: config/current.json\n"
    assert markdown_link_targets(text) == ["docs/catalog.json", "config/current.json"]
