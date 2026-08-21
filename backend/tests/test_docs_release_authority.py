from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("docs_contract", ROOT / "scripts/check_docs_contract.py")
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


def test_release_pointer_guard_rejects_release_docs_pointer(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"docs/releases/latest.json": {"version": "v9"}})
    assert len(release_pointer_errors(repo)) == 1


def test_release_pointer_guard_rejects_plural_nested_release_paths(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "docs/releases/current/metadata.json": {"version": "v9"},
            "config/releases/latest.json": {"version": "v9"},
        },
    )
    assert len(release_pointer_errors(repo)) == 2


def test_release_pointer_guard_rejects_camel_and_acronym_current_release_paths(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "docs/currentRelease.json": {"version": "v9"},
            "config/latestRelease.json": {"version": "v9"},
            "config/currentQARelease.json": {"version": "v9"},
        },
    )
    assert len(release_pointer_errors(repo)) == 3


def test_release_pointer_guard_rejects_qualified_current_release_paths(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"config/current-production-release.json": {"version": "v9"}})
    assert len(release_pointer_errors(repo)) == 1


def test_release_pointer_guard_rejects_current_release_filename_with_generic_payload(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"docs/current-release.json": {"version": "v9.9.9"}})
    assert len(release_pointer_errors(repo)) == 1


def test_release_pointer_guard_reserves_any_release_key(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "history/metadata.json": {"release_name": "v8.0.0", "status": "historical"},
            "config/version.json": {"release_version": "v9"},
            "config/notes.json": {"release_notes": "text"},
        },
    )
    errors = release_pointer_errors(repo)
    assert len(errors) == 3
    assert all("keys containing 'release' are reserved" in error for error in errors)


def test_release_pointer_guard_scans_json_extension_case_insensitively(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"config/authority.JSON": {"release_name": "v99"}})
    errors = release_pointer_errors(repo)
    assert len(errors) == 1
    assert errors[0].startswith("config/authority.JSON:")


def test_release_pointer_guard_rejects_nested_current_support_metadata(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"nested/metadata.json": {"status": "current", "metadata": {"source_sha": "abc"}}})
    errors = release_pointer_errors(repo)
    assert len(errors) == 1
    assert "sourcesha" in errors[0]


def test_release_pointer_guard_allows_historical_generic_metadata(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"history/version.json": {"version": "v8.0.0", "status": "historical"}})
    assert release_pointer_errors(repo) == []


def test_markdown_link_targets_include_inline_reference_and_html() -> None:
    text = (
        "[inline](docs/catalog.json)\n"
        "[release][release-ref]\n"
        "[release-ref]: config/current.json\n"
        '<a href="config/pointer.json">pointer</a>\n'
    )
    assert markdown_link_targets(text) == [
        "docs/catalog.json",
        "config/current.json",
        "config/pointer.json",
    ]


def test_markdown_link_targets_preserve_angle_bracket_spaces() -> None:
    text = '[current]: <config/current release.json> "title"\n[inline](<config/current release.json>)\n'
    assert markdown_link_targets(text) == ["config/current release.json", "config/current release.json"]


def test_markdown_link_targets_preserve_parentheses_inside_angle_brackets() -> None:
    text = "[settings](<config/settings (prod).json>)\n"
    assert markdown_link_targets(text) == ["config/settings (prod).json"]
