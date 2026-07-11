from __future__ import annotations

import stat
from pathlib import Path

from scripts.match_agent_codes_to_salary_names import (
    DEFAULT_OUTPUT,
    REPO_ROOT,
    _open_private_csv,
)


def test_default_output_is_outside_reports_and_under_ignored_outputs() -> None:
    expected = REPO_ROOT / "backend" / "outputs" / "agent_code_name_matches.csv"
    assert DEFAULT_OUTPUT == expected
    assert "reports" not in DEFAULT_OUTPUT.relative_to(REPO_ROOT).parts
    assert DEFAULT_OUTPUT.relative_to(REPO_ROOT).parts[:2] == ("backend", "outputs")


def test_private_csv_writer_enforces_owner_only_permissions(tmp_path: Path) -> None:
    output = tmp_path / "report.csv"
    with _open_private_csv(output) as handle:
        handle.write("header\n")
    assert output.read_text(encoding="utf-8") == "header\n"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
