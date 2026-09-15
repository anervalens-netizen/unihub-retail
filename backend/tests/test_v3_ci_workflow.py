"""Regression for GitHub's ordered positive/negative changed-path matching."""
from fnmatch import fnmatchcase
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize("code", [
    None,
    "backend/routers/ai_assistant.py",
    "backend/db/migrations/087_change.sql",
    "backend/architecture_contract.json",
    "backend/requirements.txt",
    "backend/requirements.lock",
    ".github/workflows/v3-frontend-ci.yml",
])
def test_v3_ci_markdown_exclusion_is_ordered_and_does_not_hide_code(code):
    workflow = Path(__file__).resolve().parents[2] / ".github/workflows/v3-frontend-ci.yml"
    config = yaml.safe_load(workflow.read_text())
    trigger = config.get("on", config.get(True))["pull_request"]
    patterns = trigger["paths"]
    assert patterns[-1] == "!**/*.md"
    assert "paths-ignore" not in trigger
    changed = ["backend/ai_assistant/knowledge/BUSINESS.md"]
    if code:
        changed.append(code)
    selected = []
    for path in changed:
        included = False
        for pattern in patterns:
            negative = pattern.startswith("!")
            if fnmatchcase(path, pattern.lstrip("!")):
                included = not negative
        selected.append(included)
    assert any(selected) is (code is not None)
