from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "release_authority_d4",
    ROOT / "scripts/check_release_authority.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_release_contract(root: Path, note: str) -> None:
    docs_dir = root / "docs"
    release_dir = docs_dir / "releases"
    release_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "README.md").write_text(
        "RELEASE_MANIFEST.json\n"
        "render_production_release_notes.py\n"
        "production/retail-release-\n",
        encoding="utf-8",
    )
    (release_dir / "v9.9.9.md").write_text(note, encoding="utf-8")


def test_historical_release_note_contract_passes(tmp_path: Path) -> None:
    write_release_contract(
        tmp_path,
        "> **Historical release note — not production authority.**\nHistorical evidence.\n",
    )
    assert MODULE.narrative_release_errors(tmp_path) == []


def test_release_note_without_historical_banner_is_rejected(tmp_path: Path) -> None:
    write_release_contract(tmp_path, "# v9.9.9\nProduction release.\n")
    errors = MODULE.narrative_release_errors(tmp_path)
    assert len(errors) == 1
    assert "must be explicitly historical" in errors[0]


def test_historical_note_cannot_redeclare_canonical_identity(tmp_path: Path) -> None:
    write_release_contract(
        tmp_path,
        "> **Historical release note — not production authority.**\n"
        "Canonical identity: annotated tag `v9.9.9`.\n",
    )
    errors = MODULE.narrative_release_errors(tmp_path)
    assert len(errors) == 1
    assert "cannot declare a canonical identity" in errors[0]


def test_canonical_docs_index_requires_machine_authority_and_renderer(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "README.md").write_text("historical notes only\n", encoding="utf-8")
    errors = MODULE.narrative_release_errors(tmp_path)
    assert len(errors) == 3
    assert any("RELEASE_MANIFEST.json" in error for error in errors)
    assert any("render_production_release_notes.py" in error for error in errors)
    assert any("production/retail-release-" in error for error in errors)


def test_missing_canonical_docs_index_is_rejected(tmp_path: Path) -> None:
    errors = MODULE.narrative_release_errors(tmp_path)
    assert errors == ["docs/README.md: derived release narrative contract is missing"]
