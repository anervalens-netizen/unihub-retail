from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_python_requirement_locks.py"


def _load_checker() -> Any:
    spec = importlib.util.spec_from_file_location("check_python_requirement_locks", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Any, module)


CHECKER = _load_checker()


def _write(root: Path, rel: str, content: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, lock: str) -> None:
    monkeypatch.setattr(CHECKER, "ROOT", tmp_path)
    _write(tmp_path, "source.txt", source)
    _write(tmp_path, "lock.txt", lock)
    CHECKER.verify("source.txt", "lock.txt")


def test_source_rejects_nested_requirement_directive(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.txt", "-r other.txt\n")
    with pytest.raises(SystemExit, match="nested requirement directives"):
        CHECKER.load_source(path)


def test_source_skips_false_marker(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.txt", "demo==1.0; python_version < '1'\n")
    assert CHECKER.load_source(path) == {}


def test_source_rejects_duplicate_canonical_names(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.txt", "Demo_Pkg==1.0\ndemo-pkg==1.0\n")
    with pytest.raises(SystemExit, match="duplicate direct requirement for demo-pkg"):
        CHECKER.load_source(path)


def test_source_rejects_invalid_requirement(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.txt", "not a valid requirement ???\n")
    with pytest.raises(SystemExit, match="invalid requirement"):
        CHECKER.load_source(path)


def test_source_rejects_direct_url(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.txt", "demo @ https://example.invalid/demo.whl\n")
    with pytest.raises(SystemExit, match="direct URL requirements are not supported"):
        CHECKER.load_source(path)


def test_lock_rejects_invalid_version(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.lock", "demo==not_a_version \\\n")
    with pytest.raises(SystemExit, match="invalid pinned version for demo"):
        CHECKER.load_lock(path)


def test_lock_rejects_conflicting_pins(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.lock", "demo==1.0 \\\ndemo==2.0 \\\n")
    with pytest.raises(SystemExit, match="conflicting pins for demo"):
        CHECKER.load_lock(path)


def test_verify_rejects_missing_direct_requirement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit, match="missing direct requirement demo"):
        _verify(tmp_path, monkeypatch, "demo==1.0\n", "other==1.0 \\\n")


def test_verify_rejects_version_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit, match="does not satisfy"):
        _verify(tmp_path, monkeypatch, "demo>=2.0\n", "demo==1.0 \\\n")


def test_verify_rejects_missing_requested_extra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit, match="missing requested extras speed"):
        _verify(tmp_path, monkeypatch, "demo[speed]==1.0\n", "demo==1.0 \\\n")


def test_verify_accepts_matching_or_superset_extras(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _verify(tmp_path, monkeypatch, "demo[speed]==1.0\n", "demo[speed,security]==1.0 \\\n")
