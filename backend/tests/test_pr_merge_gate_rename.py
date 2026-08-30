from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "pr_merge_gate.py"


def _load_helper():
    spec = importlib.util.spec_from_file_location("pr_merge_gate_rename", HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_docs_classifier_fails_closed_on_runtime_to_docs_rename():
    m = _load_helper()
    assert not m._files_are_docs_only(
        [
            {
                "filename": "docs/legacy.md",
                "status": "renamed",
                "previous_filename": "backend/legacy.py",
            }
        ]
    )


def test_docs_classifier_accepts_rename_fully_inside_docs_surface():
    m = _load_helper()
    assert m._files_are_docs_only(
        [
            {
                "filename": "docs/new-name.md",
                "status": "renamed",
                "previous_filename": "docs/old-name.md",
            }
        ]
    )
