from __future__ import annotations

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def tracked_paths() -> set[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return {item.decode("utf-8", "surrogateescape") for item in raw.split(b"\0") if item}


def test_generated_report_directories_are_not_tracked() -> None:
    paths = tracked_paths()
    assert not any(path.startswith("reports/") for path in paths)
    assert not any(path.startswith("public.bak-") for path in paths)


def test_repository_ignore_rules_are_path_specific() -> None:
    lines = set((ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())
    assert "/reports/" in lines
    assert "/public.bak-*/" in lines
    assert "*.xlsx" not in lines
    assert "*.csv" not in lines
    assert "*.json" not in lines


def test_authoritative_docs_remain_tracked() -> None:
    paths = tracked_paths()
    assert any(path.startswith("docs/Campanii-promo/") for path in paths)
    assert any(path.startswith("docs/archive/") for path in paths)
