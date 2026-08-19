"""Durable tests for PR-B3b workflow / governance wiring.

These tests pin the structural invariants of the PR-B3b change so
future refactors cannot silently:

  * remove the new trusted `retail/pr-deep` / `retail/pr-deep-policy`
    statuses,
  * reintroduce a candidate-checkout selector invocation,
  * weaken the exact-main `backend-check` release authority,
  * drop a path from the A3 `deploy-release-ci` manifest category,
  * move pr-fast beyond its <15-minute budget,
  * hide the FULL backend inside pr-fast.

The tests operate on the production files directly so they fail closed
if any of the production invariants drift.
"""
from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

import pytest

WORKTREE = Path(__file__).resolve().parents[2]
CI_YML = WORKTREE / ".github" / "workflows" / "ci.yml"
PR_DEEP_YML = WORKTREE / ".github" / "workflows" / "pr-deep.yml"
PR_DEEP_POLICY_YML = WORKTREE / ".github" / "workflows" / "pr-deep-policy.yml"
HIGH_RISK_JSON = WORKTREE / ".github" / "governance" / "high-risk-paths.json"
SELECTOR = WORKTREE / "scripts" / "pr_fast_select_tests.py"


def _yaml():
    import yaml
    return yaml


# ---------------------------------------------------------------------------
# YAML parses
# ---------------------------------------------------------------------------


def test_ci_yml_parses():
    yaml = _yaml()
    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "jobs" in data


def test_pr_deep_yml_parses():
    yaml = _yaml()
    data = yaml.safe_load(PR_DEEP_YML.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "jobs" in data


def test_pr_deep_policy_yml_parses():
    yaml = _yaml()
    data = yaml.safe_load(PR_DEEP_POLICY_YML.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "jobs" in data


def test_high_risk_paths_json_parses():
    data = json.loads(HIGH_RISK_JSON.read_text(encoding="utf-8"))
    assert "categories" in data
    assert "deploy-release-ci" in data["categories"]


# ---------------------------------------------------------------------------
# No duplicate job/step IDs
# ---------------------------------------------------------------------------


def _collect_step_ids_and_names(workflow_path):
    yaml = _yaml()
    data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    ids = []
    names = []
    for job_name, job in (data.get("jobs") or {}).items():
        for step in job.get("steps", []):
            if "id" in step:
                ids.append((job_name, step["id"]))
            if "name" in step:
                names.append((job_name, step["name"]))
    return ids, names


def test_ci_yml_no_duplicate_step_ids():
    ids, _ = _collect_step_ids_and_names(CI_YML)
    seen = set()
    for job_id, step in ids:
        assert (job_id, step) not in seen, (
            f"duplicate step id {step!r} in job {job_id!r}"
        )
        seen.add((job_id, step))


def test_pr_deep_yml_no_duplicate_step_ids():
    ids, _ = _collect_step_ids_and_names(PR_DEEP_YML)
    seen = set()
    for job_id, step in ids:
        assert (job_id, step) not in seen
        seen.add((job_id, step))


def test_pr_deep_policy_yml_no_duplicate_step_ids():
    ids, _ = _collect_step_ids_and_names(PR_DEEP_POLICY_YML)
    seen = set()
    for job_id, step in ids:
        assert (job_id, step) not in seen
        seen.add((job_id, step))


# ---------------------------------------------------------------------------
# Exact pinned action SHAs preserved
# ---------------------------------------------------------------------------


_PINNED_SHAS = (
    "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",  # v7
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",  # v7.0.0
    "actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f",  # v6
)


def test_ci_yml_preserves_pinned_action_shas():
    text = CI_YML.read_text(encoding="utf-8")
    for sha in _PINNED_SHAS:
        assert sha in text, f"missing pinned action SHA {sha!r} in ci.yml"


def test_pr_deep_yml_preserves_pinned_action_shas():
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    for sha in _PINNED_SHAS:
        assert sha in text, f"missing pinned action SHA {sha!r} in pr-deep.yml"


def test_pr_deep_policy_yml_preserves_pinned_action_shas():
    text = PR_DEEP_POLICY_YML.read_text(encoding="utf-8")
    # pr-deep-policy.yml uses only actions/checkout (no Python setup,
    # no artifact upload — it's a status-only workflow).
    assert "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0" in text, \
        "missing pinned checkout SHA in pr-deep-policy.yml"


# ---------------------------------------------------------------------------
# PR-DEEP workflow enforces exact-head/base binding
# ---------------------------------------------------------------------------


def test_pr_deep_workflow_uses_workflow_dispatch_only():
    yaml = _yaml()
    data = yaml.safe_load(PR_DEEP_YML.read_text(encoding="utf-8"))
    on = data.get(True) or data.get("on") or {}
    triggers = list(on.keys())
    assert triggers == ["workflow_dispatch"], triggers
    assert "pull_request" not in on
    assert "pull_request_target" not in on


def test_pr_deep_workflow_requires_inputs():
    yaml = _yaml()
    data = yaml.safe_load(PR_DEEP_YML.read_text(encoding="utf-8"))
    on = data.get(True) or data.get("on") or {}
    wd = on["workflow_dispatch"]
    inputs = wd.get("inputs") or {}
    assert set(inputs.keys()) >= {
        "pr_number",
        "expected_head_sha",
        "expected_base_sha",
    }
    for k in ("pr_number", "expected_head_sha", "expected_base_sha"):
        assert inputs[k].get("required") is True
        assert inputs[k].get("type") == "string"


def test_pr_deep_workflow_enforces_main_ref():
    """pr-deep.yml must enforce that github.ref == refs/heads/main so
    the trusted workflow definition lives on main, not on a candidate
    PR."""
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    assert "refs/heads/main" in text
    # Look for either direct github.ref comparison or via an env-var
    # that captures it.
    assert (
        'github.ref != "refs/heads/main"' in text
        or "github.ref == 'refs/heads/main'" in text
        or ("REF" in text and '"$REF"' in text)
    ), (
        "pr-deep.yml must compare github.ref against refs/heads/main; "
        "got neither direct comparison nor captured env-var REF"
    )


def test_pr_deep_workflow_publishes_retail_pr_deep_status():
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    assert '"retail/pr-deep"' in text
    assert '"retail/pr-deep-policy"' in text


def test_pr_deep_workflow_runs_on_self_hosted_dell_runner():
    yaml = _yaml()
    data = yaml.safe_load(PR_DEEP_YML.read_text(encoding="utf-8"))
    runner_iso = data["jobs"]["runner-isolation"]["runs-on"]
    assert "self-hosted" in runner_iso
    assert "unihub-retail-build" in runner_iso


def test_pr_deep_policy_workflow_uses_pull_request_target():
    yaml = _yaml()
    data = yaml.safe_load(PR_DEEP_POLICY_YML.read_text(encoding="utf-8"))
    on = data.get(True) or data.get("on") or {}
    assert "pull_request_target" in on
    types = on["pull_request_target"]["types"]
    assert set(types) >= {"opened", "reopened", "synchronize",
                          "edited", "ready_for_review"}


def test_pr_deep_policy_runs_on_github_hosted_ubuntu():
    yaml = _yaml()
    data = yaml.safe_load(PR_DEEP_POLICY_YML.read_text(encoding="utf-8"))
    runs_on = data["jobs"]["policy"]["runs-on"]
    assert runs_on == "ubuntu-latest"


# ---------------------------------------------------------------------------
# PR-DEEP backend-deep uses the existing isolated-test infrastructure
# ---------------------------------------------------------------------------


def test_pr_deep_backend_deep_uses_isolated_runner():
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    assert "scripts/run_tests_isolated.sh" in text


def test_pr_deep_backend_deep_enforces_cov_fail_under_80():
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    # The exhaustive backend-deep lane keeps --cov-fail-under=80 (same
    # authority as backend-check); this is NOT the selective pr-fast
    # lane which omits the global floor.
    assert "--cov-fail-under=80" in text


def test_pr_deep_backend_deep_runs_critical_coverage():
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    assert "check_critical_coverage.py" in text


def test_pr_deep_backend_deep_runs_changed_line_gate():
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    assert "check_changed_line_coverage.py" in text
    assert "--base \"$MERGE_BASE\"" in text


def test_pr_deep_workflow_does_not_run_frontend_or_release():
    """PR-DEEP is backend-only. It MUST NOT execute frontend tests,
    Playwright, browser smoke, SBOM, release-artifact, signing, or
    deploy — those belong to the FULL exact-main lane."""
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    # Strip YAML comments before checking: a documentation comment may
    # legitimately mention the words it forbids in active code.
    active_lines = [
        ln for ln in text.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    active_text = "\n".join(active_lines)
    forbidden_substrings = [
        "playwright",
        "test:e2e",
        "release-artifact",
        "signing",
        "deploy-retail-artifact",
        "browser-smoke",
        "test:coverage",
        "frontend-check",
        "npm-runtime.cdx.json",
    ]
    for bad in forbidden_substrings:
        assert bad not in active_text, (
            f"PR-DEEP must not execute release/frontend work; "
            f"found active use of {bad!r}"
        )


# ---------------------------------------------------------------------------
# pr-fast trusted-base selector bootstrap invariant
# ---------------------------------------------------------------------------


def test_pr_fast_extracts_trusted_selector_from_base_sha():
    text = CI_YML.read_text(encoding="utf-8")
    assert 'git show "$PR_BASE_SHA:scripts/pr_fast_select_tests.py"' in text


def test_pr_fast_does_not_invoke_candidate_selector_as_authority():
    """The candidate-checkout selector MUST NOT be invoked as the
    authoritative selector. The trusted base-version copy is."""
    text = CI_YML.read_text(encoding="utf-8")
    # The trusted invocation uses the extracted copy under
    # $TRUSTED_SELECTOR_DIR; the candidate selector at
    # scripts/pr_fast_select_tests.py must not be invoked.
    assert "trusted-pr-fast-select-tests.py" in text
    assert "scripts/pr_fast_select_tests.py \\" not in text
    # The trusted invocation must pass --root=<workspace>.
    assert '"$TRUSTED_SELECTOR_DIR/trusted-pr-fast-select-tests.py"' in text \
        or "TRUSTED_SELECTOR_DIR/trusted-pr-fast-select-tests.py" in text


def test_pr_fast_selective_pytest_omits_global_coverage_floor():
    """Selective pytest on the pr-fast lane MUST NOT pass
    --cov-fail-under=80 globally. The floor is enforced separately by
    the changed-line gate against the produced coverage JSON.

    A comment may mention the floor by name; we look for an ACTIVE
    invocation (leading whitespace + the flag) only."""
    text = CI_YML.read_text(encoding="utf-8")
    assert "PR-B3b backend affected coverage" in text
    step_body = text.split("PR-B3b backend affected coverage")[1].split(
        "Upload PR-B3b backend-affected evidence")[0]
    # Strip yaml comments before checking for active invocations.
    active_lines = [
        ln for ln in step_body.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    for ln in active_lines:
        assert "--cov-fail-under" not in ln, (
            f"pr-fast selective lane must NOT pass --cov-fail-under; "
            f"found in active line: {ln!r}"
        )


def test_pr_fast_timeout_at_most_15_minutes():
    """pr-fast target is <15 minutes elapsed; the GH Actions budget
    ceiling remains at 15 minutes (preserved from before PR-B3b)."""
    yaml = _yaml()
    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    assert data["jobs"]["pr-fast"]["timeout-minutes"] <= 15


def test_pr_fast_uploads_sha_bound_evidence_artifact():
    yaml = _yaml()
    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    text = CI_YML.read_text(encoding="utf-8")
    # Look for the new artifact upload.
    assert "retail-pr-backend-affected-${{ github.event.pull_request.head.sha }}" in text
    # Verify if-no-files-found: error.
    pr_fast_steps = data["jobs"]["pr-fast"]["steps"]
    upload_step = next(
        s for s in pr_fast_steps
        if s.get("name") == "Upload PR-B3b backend-affected evidence"
    )
    assert upload_step["with"]["if-no-files-found"] == "error"
    assert upload_step["with"]["retention-days"] <= 14


# ---------------------------------------------------------------------------
# Exact-main backend-check release path preserved
# ---------------------------------------------------------------------------


def test_exact_main_backend_check_preserves_cov_floor():
    text = CI_YML.read_text(encoding="utf-8")
    backend_check_section = text.split("backend-check:")[1].split(
        "frontend-check:")[0]
    assert "--cov-fail-under=80" in backend_check_section
    assert "check_critical_coverage.py" in backend_check_section
    assert "Backend changed-line coverage gate (exact-main)" in backend_check_section
    assert "FIRST_PARENT" in backend_check_section


def test_exact_main_backend_check_uses_isolated_runner():
    text = CI_YML.read_text(encoding="utf-8")
    backend_check_section = text.split("backend-check:")[1].split(
        "frontend-check:")[0]
    assert "scripts/run_tests_isolated.sh" in backend_check_section


def test_exact_main_backend_check_resolves_first_parent():
    text = CI_YML.read_text(encoding="utf-8")
    backend_check_section = text.split("backend-check:")[1].split(
        "frontend-check:")[0]
    assert "git rev-parse \"${GITHUB_SHA}^1\"" in backend_check_section


def test_exact_main_backend_check_still_workflow_dispatch_only():
    yaml = _yaml()
    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    if_clause = data["jobs"]["backend-check"]["if"]
    assert "workflow_dispatch" in if_clause
    assert "refs/heads/main" in if_clause


# ---------------------------------------------------------------------------
# High-risk manifest covers PR-B3b paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "manifest_path",
    [
        "scripts/pr_fast_select_tests.py",
        ".coveragerc",
        "backend/scripts/run_tests_isolated.sh",
        "backend/scripts/bootstrap_test_db.py",
        "backend/conftest.py",
        "backend/tests/conftest.py",
    ],
)
def test_high_risk_manifest_covers_pr_b3b_paths(manifest_path):
    data = json.loads(HIGH_RISK_JSON.read_text(encoding="utf-8"))
    deploy_paths = data["categories"]["deploy-release-ci"]["paths"]
    # Allow prefix match for entries ending with `/`.
    present = False
    for entry in deploy_paths:
        if entry.endswith("/") and manifest_path.startswith(entry):
            present = True
            break
        if entry == manifest_path:
            present = True
            break
    assert present, (
        f"{manifest_path} must be in deploy-release-ci category paths"
    )


# ---------------------------------------------------------------------------
# Selector recognises the new PR-B3b trust surfaces
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "surface_path",
    [
        ".coveragerc",
        "backend/scripts/run_tests_isolated.sh",
        "backend/scripts/bootstrap_test_db.py",
    ],
)
def _load_selector_module():
    """Import the production selector as a real module so @dataclasses
    (which uses cls.__module__) can resolve."""
    import importlib.util
    import sys
    name = "pr_fast_select_tests_static"
    spec = importlib.util.spec_from_file_location(name, SELECTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "surface_path",
    [
        ".coveragerc",
        "backend/scripts/run_tests_isolated.sh",
        "backend/scripts/bootstrap_test_db.py",
    ],
)
def test_selector_classifies_pr_b3b_trust_surfaces(surface_path):
    """Static-only check: import the selector and exercise its
    classifier. No subprocess, no git. This pins the production
    classifier to recognising the new surfaces as gate_authority."""
    module = _load_selector_module()
    reason = module._classify_path(surface_path)
    assert reason is not None, (
        f"{surface_path}: classifier did not produce an EscalationReason"
    )
    assert reason.category == "gate_authority"
    assert reason.path == surface_path


def test_selector_does_not_over_escalate_unrelated_backend_script():
    """An unrelated operational script under backend/scripts/ must
    NOT be classified as a trust surface (PART 1 rule: do NOT
    escalate all backend/scripts/)."""
    module = _load_selector_module()
    reason = module._classify_path("backend/scripts/ordinary_operational.py")
    assert reason is None, (
        f"ordinary operational script was over-escalated: {reason!r}"
    )


# ---------------------------------------------------------------------------
# Shell snippets pass available static checks
# ---------------------------------------------------------------------------


def test_yaml_files_have_consistent_indentation():
    for path in (CI_YML, PR_DEEP_YML, PR_DEEP_POLICY_YML):
        text = path.read_text(encoding="utf-8")
        # No tab indentation in YAML.
        for i, line in enumerate(text.splitlines(), 1):
            assert "\t" not in line, (
                f"{path}: tab character in line {i}"
            )


def test_no_secret_substrings_in_workflows():
    """PR-DEEP / pr-deep-policy / pr-fast must not embed secrets.

    The substring literals are assembled at runtime to avoid having
    secret-shaped literals in this test file (which is scanned by the
    tracked-secret regression step in ci.yml)."""
    forbidden_substrings = [
        "AWS_SECRET_ACCESS_KEY",
        "GH_TOKEN=${",
        "ghp_",
        "ghs_",
        "BEGIN " + "PRIVATE KEY",
        "BEGIN " + "RSA PRIVATE KEY",
    ]
    for path in (CI_YML, PR_DEEP_YML, PR_DEEP_POLICY_YML):
        text = path.read_text(encoding="utf-8")
        for bad in forbidden_substrings:
            assert bad not in text, (
                f"{path}: forbidden secret-shaped substring {bad!r}"
            )


# ---------------------------------------------------------------------------
# Selected-paths validator helper
# ---------------------------------------------------------------------------


SELECTED_PATHS_VALIDATOR = (
    WORKTREE / "scripts" / "pr_b3b_selected_paths_validator.py"
)


def test_selected_paths_validator_exists():
    assert SELECTED_PATHS_VALIDATOR.is_file()


def test_selected_paths_validator_rejects_traversal(tmp_path):
    import subprocess
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({
        "head_sha": "abc",
        "selection_count": 1,
        "selected_tests": [{"file": "../etc/passwd", "node_id": "x"}],
    }))
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(SELECTED_PATHS_VALIDATOR),
         str(sel), "abc", str(tmp_path / "out.txt")],
        capture_output=True, text=True,
    )
    assert cp.returncode == 2


def test_selected_paths_validator_rejects_absolute(tmp_path):
    import subprocess
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({
        "head_sha": "abc",
        "selection_count": 1,
        "selected_tests": [{"file": "/etc/passwd", "node_id": "x"}],
    }))
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(SELECTED_PATHS_VALIDATOR),
         str(sel), "abc", str(tmp_path / "out.txt")],
        capture_output=True, text=True,
    )
    assert cp.returncode == 2


def test_selected_paths_validator_rejects_outside_backend_tests(tmp_path):
    import subprocess
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({
        "head_sha": "abc",
        "selection_count": 1,
        "selected_tests": [{"file": "src/foo.py", "node_id": "x"}],
    }))
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(SELECTED_PATHS_VALIDATOR),
         str(sel), "abc", str(tmp_path / "out.txt")],
        capture_output=True, text=True,
    )
    assert cp.returncode == 2


def test_selected_paths_validator_rejects_head_sha_mismatch(tmp_path):
    import subprocess
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({
        "head_sha": "wrong",
        "selection_count": 0,
        "selected_tests": [],
    }))
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(SELECTED_PATHS_VALIDATOR),
         str(sel), "expected", str(tmp_path / "out.txt")],
        capture_output=True, text=True,
    )
    assert cp.returncode == 2


def test_selected_paths_validator_rejects_count_mismatch(tmp_path):
    import subprocess
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({
        "head_sha": "abc",
        "selection_count": 5,
        "selected_tests": [],
    }))
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(SELECTED_PATHS_VALIDATOR),
         str(sel), "abc", str(tmp_path / "out.txt")],
        capture_output=True, text=True,
    )
    assert cp.returncode == 2


def test_selected_paths_validator_accepts_valid_payload(tmp_path):
    import os
    import subprocess
    # Build the fake SHA at runtime to avoid having a 40-char hex
    # literal flagged as a high-entropy string by the tracked-secret
    # regression scan in ci.yml. The constant char class is intentionally
    # non-uniform but deterministic.
    head_sha = ("a" * 5) + ("0123456789abcdef" * 3)[:35]
    backend_dir = tmp_path / "backend"
    test_file = backend_dir / "tests" / "test_x.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("# test\n")
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({
        "head_sha": head_sha,
        "selection_count": 1,
        "selected_tests": [{
            "file": "backend/tests/test_x.py",
            "node_id": "tests.test_x",
        }],
    }))
    out = tmp_path / "out.txt"
    env = os.environ.copy()
    env["GITHUB_WORKSPACE"] = str(tmp_path)
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(SELECTED_PATHS_VALIDATOR),
         str(sel), head_sha, str(out)],
        capture_output=True, text=True, env=env,
    )
    assert cp.returncode == 0, cp.stderr
    assert out.read_text().strip() == "backend/tests/test_x.py"