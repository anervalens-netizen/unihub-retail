from __future__ import annotations

from pathlib import Path

import yaml


WORKTREE = Path(__file__).resolve().parents[2]
PR_DEEP_YML = WORKTREE / ".github" / "workflows" / "pr-deep.yml"


def _pr_deep_jobs():
    data = yaml.safe_load(PR_DEEP_YML.read_text(encoding="utf-8"))
    jobs = data.get("jobs") or {}
    assert isinstance(jobs, dict)
    return jobs


def test_pr_deep_action_steps_do_not_use_working_directory() -> None:
    data = yaml.safe_load(PR_DEEP_YML.read_text(encoding="utf-8"))
    for job_name, job in (data.get("jobs") or {}).items():
        for step in job.get("steps", []):
            if "uses" in step:
                assert "working-directory" not in step, (
                    f"GitHub Actions action step {job_name}/{step.get('name', step['uses'])!r} "
                    "must not define working-directory"
                )


def test_pr_deep_certification_signal_job_exists() -> None:
    jobs = _pr_deep_jobs()
    assert "certification-signal" in jobs, (
        "pr-deep.yml must declare a trusted post-marker `certification-signal` job"
    )


def test_pr_deep_certification_signal_depends_on_marker() -> None:
    jobs = _pr_deep_jobs()
    signal = jobs["certification-signal"]
    needs = signal.get("needs")
    assert needs == "certification-marker", (
        f"certification-signal must depend on certification-marker, got: {needs!r}"
    )
    if_cond = signal.get("if") or ""
    assert "needs.certification-marker.result" in if_cond and "success" in if_cond, (
        "certification-signal must run only after certification-marker succeeded"
    )


def test_pr_deep_certification_signal_does_not_check_out_candidate_code() -> None:
    jobs = _pr_deep_jobs()
    signal_steps = jobs["certification-signal"].get("steps", [])
    for step in signal_steps:
        uses = step.get("uses", "")
        assert "actions/checkout" not in uses, (
            "certification-signal must never checkout candidate code"
        )
        run_text = step.get("run") or ""
        assert "actions/checkout" not in run_text, (
            "certification-signal must never invoke checkout via shell"
        )


def test_pr_deep_certification_signal_validates_inputs() -> None:
    jobs = _pr_deep_jobs()
    steps = jobs["certification-signal"].get("steps", [])
    validate = next(
        (s for s in steps if (s.get("name") or "").startswith("Validate trusted signal inputs")),
        None,
    )
    assert validate is not None, "signal job must include input validation step"
    env = validate.get("env") or {}
    assert "REF" in env and "PR_NUMBER" in env and "HEAD_SHA" in env and "BASE_SHA" in env
    run = validate.get("run") or ""
    assert "refs/heads/main" in run, "signal must validate github.ref == refs/heads/main"
    assert "^[0-9]+$" in run, "signal must validate pr_number is numeric"
    assert "[0-9a-f]{40}" in run, "signal must validate both SHAs are 40-char hex"


def test_pr_deep_certification_signal_publishes_on_expected_head_sha() -> None:
    jobs = _pr_deep_jobs()
    steps = jobs["certification-signal"].get("steps", [])
    publish = next(
        (
            s for s in steps
            if (s.get("name") or "").startswith(
                "Re-publish retail/pr-deep = success on candidate head"
            )
        ),
        None,
    )
    assert publish is not None, "signal job must include the re-publication step"
    env = publish.get("env") or {}
    # Must target the trusted dispatch input HEAD, not github.sha.
    assert env.get("HEAD_SHA") == "${{ inputs.expected_head_sha }}", (
        "signal must publish to inputs.expected_head_sha, not github.sha"
    )
    assert env.get("BASE_SHA") == "${{ inputs.expected_base_sha }}"
    run = publish.get("run") or ""
    assert '"retail/pr-deep"' in run, "signal must publish context retail/pr-deep"
    assert "PASS base=" in run, "signal must publish PASS base= description"
    assert "expected_base_sha" not in run, (
        "description must inline the actual BASE_SHA, not dispatch input expression"
    )
    # Run URL must point at this trusted PR-DEEP workflow run.
    assert "github.run_id" in (env.get("RUN_URL") or "")
