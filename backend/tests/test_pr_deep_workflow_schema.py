from __future__ import annotations

from pathlib import Path

import yaml


WORKTREE = Path(__file__).resolve().parents[2]
PR_DEEP_YML = WORKTREE / ".github" / "workflows" / "pr-deep.yml"


def test_pr_deep_action_steps_do_not_use_working_directory() -> None:
    data = yaml.safe_load(PR_DEEP_YML.read_text(encoding="utf-8"))
    for job_name, job in (data.get("jobs") or {}).items():
        for step in job.get("steps", []):
            if "uses" in step:
                assert "working-directory" not in step, (
                    f"GitHub Actions action step {job_name}/{step.get('name', step['uses'])!r} "
                    "must not define working-directory"
                )
