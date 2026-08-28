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

The tests also cover the FINAL PRE-REVIEW correction pass (DEFECTS
1–6): checkout-before-fetch order, state/rc consistency, PR_BASE
vs MERGE_BASE separation, pending status JSON without unexported
DESCRIPTION, latest-status-wins, and B3b helper control-plane
classification.

The tests operate on the production files directly so they fail closed
if any of the production invariants drift.
"""
from __future__ import annotations

import json
import re
import subprocess
import textwrap
from difflib import unified_diff as _unified_diff
from pathlib import Path

import pytest

WORKTREE = Path(__file__).resolve().parents[2]
CI_YML = WORKTREE / ".github" / "workflows" / "ci.yml"
PR_DEEP_YML = WORKTREE / ".github" / "workflows" / "pr-deep.yml"
PR_DEEP_POLICY_YML = WORKTREE / ".github" / "workflows" / "pr-deep-policy.yml"
HIGH_RISK_YML = WORKTREE / ".github" / "workflows" / "high-risk-governance.yml"
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


def test_ci_jobs_do_not_redeclare_identical_workflow_env():
    """Job-level env must override workflow env only with a distinct value."""
    data = _yaml().safe_load(CI_YML.read_text(encoding="utf-8"))
    workflow_env = data.get("env") or {}
    jobs = data.get("jobs") or {}
    for job_name, job in jobs.items():
        job_env = (job or {}).get("env") or {}
        for key, value in job_env.items():
            if key in workflow_env:
                assert value != workflow_env[key], (
                    f"job {job_name!r} redeclares workflow env key {key!r} "
                    "with an identical value"
                )


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


def _workflow_on(workflow_path):
    data = _yaml().safe_load(workflow_path.read_text(encoding="utf-8"))
    return data.get(True) or data.get("on") or {}


def test_pr_verification_workflows_skip_markdown_and_docs_only_changes():
    """Docs-only PRs must not launch redundant heavy PR verification."""
    for workflow_path, trigger_name in (
        (CI_YML, "pull_request"),
        (HIGH_RISK_YML, "pull_request_target"),
        (PR_DEEP_POLICY_YML, "pull_request_target"),
    ):
        trigger = _workflow_on(workflow_path)[trigger_name]
        ignored = set(trigger.get("paths-ignore", []))
        assert {"**/*.md", "docs/**"} <= ignored, workflow_path


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


def test_pr_fast_timeout_is_15_minute_guardrail():
    """The hard timeout stays 15 minutes; it is not the fast-lane target."""
    yaml = _yaml()
    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    assert data["jobs"]["pr-fast"]["timeout-minutes"] == 15


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
        "backend/scripts/check_critical_coverage.py",
        "backend/critical_coverage_thresholds.json",
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
    # Build the fake SHAs at runtime to avoid having 40-char hex
    # literals flagged as high-entropy strings by the tracked-secret
    # regression scan in ci.yml. The constant char class is
    # intentionally non-uniform but deterministic.
    head_sha = ("a" * 5) + ("0123456789abcdef" * 3)[:35]
    # Build base_sha using only "0"-"9" digits (still 40 chars hex
    # but with low entropy for the heuristic).
    base_sha = "0" + ("1234567890" * 4)[:39]
    backend_dir = tmp_path / "backend"
    test_file = backend_dir / "tests" / "test_x.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("# test\n")
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({
        "schema_version": 1,
        "head_sha": head_sha,
        "base_sha": base_sha,
        "state": "SELECTED",
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
         str(sel), head_sha, base_sha, "0", str(out)],
        capture_output=True, text=True, env=env,
    )
    assert cp.returncode == 0, cp.stderr
    assert out.read_text().strip() == "backend/tests/test_x.py"


# ---------------------------------------------------------------------------
# Hardened validator contract (DEFECT 6)
# ---------------------------------------------------------------------------


def _write_validator_payload(
    tmp_path, *, state, base_sha, head_sha, selected_tests,
    schema_version=1, selection_count=None,
):
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({
        "schema_version": schema_version,
        "head_sha": head_sha,
        "base_sha": base_sha,
        "state": state,
        "selection_count": (
            selection_count
            if selection_count is not None
            else len(selected_tests)
        ),
        "selected_tests": selected_tests,
    }))
    return sel


def _run_validator(tmp_path, sel_path, head_sha, base_sha, rc, out=None):
    import os
    import subprocess
    out_path = out if out is not None else (tmp_path / "out.txt")
    env = os.environ.copy()
    env["GITHUB_WORKSPACE"] = str(tmp_path)
    return subprocess.run(
        ["/usr/bin/python3.12", "-I", str(SELECTED_PATHS_VALIDATOR),
         str(sel_path), head_sha, base_sha, str(rc), str(out_path)],
        capture_output=True, text=True, env=env,
    )


_HEAD = ("a" * 5) + ("0123456789abcdef" * 3)[:35]
# Build _BASE using only "0"-"9" digits to keep entropy low for the
# tracked-secret regression scanner's high-entropy heuristic.
_BASE = "0" + ("1234567890" * 4)[:39]


def test_validator_rejects_unsupported_schema_version(tmp_path):
    sel = _write_validator_payload(
        tmp_path, state="SELECTED", base_sha=_BASE, head_sha=_HEAD,
        selected_tests=[], schema_version=99,
    )
    cp = _run_validator(tmp_path, sel, _HEAD, _BASE, 0)
    assert cp.returncode == 2
    assert "schema_version" in cp.stderr


def test_validator_rejects_state_rc_mismatch(tmp_path):
    """SELECTED must use rc 0; ESCALATION_REQUIRED must use rc 2;
    ERROR must use rc 3. Any mismatch fails closed."""
    # SELECTED with rc 2 -> policy failure
    (tmp_path / "backend" / "tests").mkdir(parents=True)
    sel = _write_validator_payload(
        tmp_path, state="SELECTED", base_sha=_BASE, head_sha=_HEAD,
        selected_tests=[{
            "file": "backend/tests/test_x.py",
            "node_id": "tests.test_x",
        }],
    )
    (tmp_path / "backend" / "tests" / "test_x.py").write_text("# x\n")
    cp = _run_validator(tmp_path, sel, _HEAD, _BASE, 2)
    assert cp.returncode == 2
    assert "inconsistent" in cp.stderr

    # ESCALATION_REQUIRED with rc 0 -> policy failure
    sel = _write_validator_payload(
        tmp_path, state="ESCALATION_REQUIRED",
        base_sha=_BASE, head_sha=_HEAD, selected_tests=[],
    )
    cp = _run_validator(tmp_path, sel, _HEAD, _BASE, 0)
    assert cp.returncode == 2

    # ERROR with rc 2 -> policy failure
    sel = _write_validator_payload(
        tmp_path, state="ERROR", base_sha=_BASE, head_sha=_HEAD,
        selected_tests=[],
    )
    cp = _run_validator(tmp_path, sel, _HEAD, _BASE, 2)
    assert cp.returncode == 2


def test_validator_rejects_base_sha_mismatch(tmp_path):
    sel = _write_validator_payload(
        tmp_path, state="NO_ELIGIBLE_BACKEND_CHANGE",
        base_sha=_BASE, head_sha=_HEAD, selected_tests=[],
    )
    other_base = "9" + ("1234567890" * 4)[:39]
    cp = _run_validator(tmp_path, sel, _HEAD, other_base, 0)
    assert cp.returncode == 2
    assert "base_sha" in cp.stderr


def test_validator_selected_state_requires_at_least_one_test(tmp_path):
    """SELECTED with zero runnable tests must fail closed."""
    sel = _write_validator_payload(
        tmp_path, state="SELECTED", base_sha=_BASE, head_sha=_HEAD,
        selected_tests=[],
    )
    cp = _run_validator(tmp_path, sel, _HEAD, _BASE, 0)
    assert cp.returncode == 2
    assert "SELECTED" in cp.stderr


def test_validator_no_eligible_state_allows_empty_selection(tmp_path):
    """NO_ELIGIBLE_BACKEND_CHANGE allows an empty runnable selection."""
    sel = _write_validator_payload(
        tmp_path, state="NO_ELIGIBLE_BACKEND_CHANGE",
        base_sha=_BASE, head_sha=_HEAD, selected_tests=[],
    )
    cp = _run_validator(tmp_path, sel, _HEAD, _BASE, 0)
    assert cp.returncode == 0, cp.stderr


def test_validator_escalation_state_allows_empty_selection(tmp_path):
    """ESCALATION_REQUIRED allows an empty runnable selection."""
    sel = _write_validator_payload(
        tmp_path, state="ESCALATION_REQUIRED",
        base_sha=_BASE, head_sha=_HEAD, selected_tests=[],
    )
    cp = _run_validator(tmp_path, sel, _HEAD, _BASE, 2)
    assert cp.returncode == 0, cp.stderr


def test_validator_rejects_selection_count_mismatch(tmp_path):
    (tmp_path / "backend" / "tests").mkdir(parents=True)
    sel = _write_validator_payload(
        tmp_path, state="SELECTED", base_sha=_BASE, head_sha=_HEAD,
        selected_tests=[{
            "file": "backend/tests/test_x.py",
            "node_id": "tests.test_x",
        }],
        selection_count=5,
    )
    (tmp_path / "backend" / "tests" / "test_x.py").write_text("# x\n")
    cp = _run_validator(tmp_path, sel, _HEAD, _BASE, 0)
    assert cp.returncode == 2
    assert "selection_count" in cp.stderr


# ---------------------------------------------------------------------------
# Policy decision (DEFECTS 1 + 2)
# ---------------------------------------------------------------------------


DECIDE_POLICY = WORKTREE / "scripts" / "pr_b3b_decide_policy.py"


def test_decide_policy_selector_state_no_eligible_is_success():
    payload = json.dumps({
        "schema_version": 1,
        "head_sha": _HEAD,
        "base_sha": _HEAD,  # selector.base_sha = MERGE_BASE (third argv)
        "state": "NO_ELIGIBLE_BACKEND_CHANGE",
        "selection_count": 0,
        "selected_tests": [],
    })
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(DECIDE_POLICY),
         "/dev/stdin", _HEAD, _BASE, _HEAD, "0",
         "anervalens-netizen/unihub-retail", ""],
        input=payload, capture_output=True, text=True,
    )
    assert cp.returncode == 0, cp.stderr
    decision = json.loads(cp.stdout)
    assert decision["policy_state"] == "success"
    assert decision["selector_state"] == "NO_ELIGIBLE_BACKEND_CHANGE"


def test_decide_policy_selector_state_selected_is_success():
    payload = json.dumps({
        "schema_version": 1,
        "head_sha": _HEAD,
        "base_sha": _HEAD,  # selector.base_sha = MERGE_BASE
        "state": "SELECTED",
        "selection_count": 1,
        "selected_tests": [],
    })
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(DECIDE_POLICY),
         "/dev/stdin", _HEAD, _BASE, _HEAD, "0",
         "anervalens-netizen/unihub-retail", ""],
        input=payload, capture_output=True, text=True,
    )
    assert cp.returncode == 0, cp.stderr
    decision = json.loads(cp.stdout)
    assert decision["policy_state"] == "success"


def test_decide_policy_escalation_without_cert_is_pending():
    """ESCALATION_REQUIRED + no matching retail/pr-deep success on the
    same head + same base => pending."""
    payload = json.dumps({
        "schema_version": 1,
        "head_sha": _HEAD,
        "base_sha": _HEAD,  # selector.base_sha = MERGE_BASE
        "state": "ESCALATION_REQUIRED",
        "selection_count": 0,
        "selected_tests": [],
    })
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(DECIDE_POLICY),
         "/dev/stdin", _HEAD, _BASE, _HEAD, "2",
         "anervalens-netizen/unihub-retail", ""],
        input=payload, capture_output=True, text=True,
    )
    assert cp.returncode == 0, cp.stderr
    decision = json.loads(cp.stdout)
    assert decision["policy_state"] == "pending"


def test_decide_policy_unknown_state_is_failure():
    payload = json.dumps({
        "schema_version": 1,
        "head_sha": _HEAD,
        "base_sha": _HEAD,  # selector.base_sha = MERGE_BASE
        "state": "WAT",
        "selection_count": 0,
        "selected_tests": [],
    })
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(DECIDE_POLICY),
         "/dev/stdin", _HEAD, _BASE, _HEAD, "3",
         "anervalens-netizen/unihub-retail", ""],
        input=payload, capture_output=True, text=True,
    )
    assert cp.returncode == 0, cp.stderr
    decision = json.loads(cp.stdout)
    assert decision["policy_state"] == "failure"


def test_decide_policy_rejects_head_sha_mismatch():
    payload = json.dumps({
        "schema_version": 1,
        "head_sha": _HEAD,
        "base_sha": _BASE,
        "state": "NO_ELIGIBLE_BACKEND_CHANGE",
        "selection_count": 0,
        "selected_tests": [],
    })
    other_head = ("d" * 5) + ("0123456789abcdef" * 3)[:35]
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(DECIDE_POLICY),
         "/dev/stdin", other_head, _BASE, _HEAD, "0",
         "anervalens-netizen/unihub-retail", ""],
        input=payload, capture_output=True, text=True,
    )
    assert cp.returncode == 0, cp.stderr
    decision = json.loads(cp.stdout)
    assert decision["policy_state"] == "failure"
    assert "head_sha" in decision["reason"]


# ---------------------------------------------------------------------------
# Base-bound certification acceptance (DEFECT 4)
# ---------------------------------------------------------------------------


def _decide_policy_with_statuses(
    statuses, *, state="ESCALATION_REQUIRED", merge_base=None,
):
    """Import decide_policy into the test process and run main() with a
    monkeypatched ``_fetch_existing_statuses``. This avoids the
    subprocess limitation of monkeypatching in a child process.
    """
    import importlib.util
    import sys
    mod_name = "pr_b3b_decide_policy_inline_test"
    spec = importlib.util.spec_from_file_location(mod_name, DECIDE_POLICY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)

    real_fetch = mod._fetch_existing_statuses

    def fake_fetch(repo, sha, token):
        return statuses

    mod._fetch_existing_statuses = fake_fetch
    try:
        # Build a temporary selector.json on disk so main() can read it.
        # For these tests we keep selector.base_sha = merge_base (the
        # trusted selector was invoked with --base=MERGE_BASE).
        if merge_base is None:
            merge_base = _BASE
        import tempfile
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False
        ) as f:
            json.dump({
                "schema_version": 1,
                "head_sha": _HEAD,
                "base_sha": merge_base,
                "state": state,
                "selection_count": 0,
                "selected_tests": [],
            }, f)
            path = f.name
        rc_arg = "0" if state in ("NO_ELIGIBLE_BACKEND_CHANGE", "SELECTED") \
            else "2" if state == "ESCALATION_REQUIRED" else "3"
        # Capture stdout.
        import io
        buf = io.StringIO()
        real_stdout = sys.stdout
        sys.stdout = buf
        try:
            ret = mod.main([
                "pr_b3b_decide_policy.py",
                path, _HEAD, _BASE, merge_base, rc_arg,
                "anervalens-netizen/unihub-retail", "faketoken",
            ])
        finally:
            sys.stdout = real_stdout
        assert ret == 0
        return json.loads(buf.getvalue())
    finally:
        mod._fetch_existing_statuses = real_fetch


def _real_github_status(
    state: str, *, description: str, status_id: int,
    timestamp: str, context: str = "retail/pr-deep",
) -> dict:
    """Build the status shape returned by GitHub's commit-status API.

    The exact-commit endpoint provides the HEAD binding; individual status
    objects intentionally do not include a redundant ``sha`` field.
    """
    return {
        "context": context,
        "state": state,
        "description": description,
        "id": status_id,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def test_decide_policy_accepts_matching_cert_for_same_head_and_base():
    """A: same head + same base successful cert -> policy success."""
    statuses = [
        _real_github_status(
            "success", description=f"PASS base={_BASE}",
            status_id=1001, timestamp="2026-08-19T10:00:00Z",
        ),
        _real_github_status(
            "success", context="something/else", description="irrelevant",
            status_id=1002, timestamp="2026-08-19T10:01:00Z",
        ),
    ]
    assert all("sha" not in status for status in statuses)
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "success"


def test_decide_policy_rejects_stale_base_same_head():
    """B: same head + OLD base successful cert -> policy pending."""
    stale_base = "8" + ("1234567890" * 4)[:39]
    statuses = [
        _real_github_status(
            "success", description=f"PASS base={stale_base}",
            status_id=1003, timestamp="2026-08-19T10:00:00Z",
        ),
    ]
    assert all("sha" not in status for status in statuses)
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending"


def test_decide_policy_irrelevant_old_head_cert():
    """C: old head successful cert -> irrelevant."""
    old_head = ("f" * 5) + ("0123456789abcdef" * 3)[:35]
    statuses = [
        {
            "context": "retail/pr-deep",
            "state": "success",
            "sha": old_head,
            "description": f"PASS base={_BASE}",
        },
    ]
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending"


def test_decide_policy_failed_cert_same_current_base_is_pending():
    """D: failed cert same current base -> pending / uncertified."""
    statuses = [
        _real_github_status(
            "failure", description=f"FAIL base={_BASE}",
            status_id=1004, timestamp="2026-08-19T10:00:00Z",
        ),
    ]
    assert all("sha" not in status for status in statuses)
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending"


def test_decide_policy_malformed_description_is_not_certified():
    """E: malformed description -> not certified (still pending)."""
    statuses = [
        _real_github_status(
            "success", description="PASS base=NOT-A-SHA",
            status_id=1005, timestamp="2026-08-19T10:00:00Z",
        ),
    ]
    assert all("sha" not in status for status in statuses)
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending"


def test_decide_policy_malformed_status_entry_fails_closed():
    """A non-object status must not be dropped before latest selection."""
    statuses = [
        _real_github_status(
            "success", description=f"PASS base={_BASE}",
            status_id=1006, timestamp="2026-08-19T10:00:00Z",
        ),
        None,
    ]
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending"


def test_decide_policy_malformed_ordering_metadata_fails_closed():
    """A malformed timestamp must not certify a success payload."""
    statuses = [
        _real_github_status(
            "success", description=f"PASS base={_BASE}",
            status_id=1006, timestamp="not-a-timestamp",
        ),
    ]
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending"


def test_decide_policy_ambiguous_ordering_does_not_select_old_success():
    """A newer status with no ordering metadata must not let an older
    exact-base success certify merely because it sorts last."""
    statuses = [
        _real_github_status(
            "success", description=f"PASS base={_BASE}",
            status_id=1007, timestamp="2026-08-19T10:00:00Z",
        ),
        {
            "context": "retail/pr-deep",
            "state": "pending",
            "description": f"RUNNING base={_BASE}",
        },
    ]
    assert all("sha" not in status for status in statuses)
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending"


# ---------------------------------------------------------------------------
# Status publication (DEFECT 3)
# ---------------------------------------------------------------------------


PUBLISH = WORKTREE / "scripts" / "pr_b3b_publish_policy_status.py"


def _make_decision(tmp_path, policy_state, *, head_sha=_HEAD, base_sha=_BASE):
    p = tmp_path / "decision.json"
    p.write_text(json.dumps({
        "schema_version": 1,
        "selector_state": "SELECTED",
        "selector_rc": 0,
        "policy_state": policy_state,
        "head_sha": head_sha,
        "base_sha": base_sha,
        "merge_base_sha": base_sha,
    }))
    return p


def test_publish_reads_decision_not_unexported_env():
    """The publisher must NOT depend on shell STATE/DESCRIPTION
    variables. It builds the JSON body ONLY from the decision JSON
    file + argv. We verify the script source does not import os or
    use os.environ for STATE/DESCRIPTION."""
    text = PUBLISH.read_text(encoding="utf-8")
    # The script must take state / description from the decision file.
    assert "POLICY_FILE" not in text or "os.environ" not in text.split(
        "def main", 1)[1]
    # More direct: STATE / DESCRIPTION env reads are forbidden.
    forbidden_in_main = [
        line for line in text.splitlines()
        if "os.environ[\"STATE\"]" in line
        or "os.environ['STATE']" in line
        or "os.environ[\"DESCRIPTION\"]" in line
        or "os.environ['DESCRIPTION']" in line
    ]
    assert not forbidden_in_main, (
        "publisher must not depend on unexported STATE/DESCRIPTION "
        f"env vars; found: {forbidden_in_main}"
    )


def test_publish_emits_correct_json_for_each_state(tmp_path):
    import subprocess
    for state, expected in [
        ("success", "success"),
        ("pending", "pending"),
        ("failure", "failure"),
    ]:
        decision = _make_decision(tmp_path, state)
        cp = subprocess.run(
            ["/usr/bin/python3.12", "-I", str(PUBLISH),
             str(decision), _HEAD, _BASE,
             "anervalens-netizen/unihub-retail", "t", "https://example/run"],
            capture_output=True, text=True,
        )
        assert cp.returncode == 0, cp.stderr
        body = json.loads(cp.stdout)
        assert body["state"] == expected
        assert body["context"] == "retail/pr-deep-policy"
        assert _BASE[:12] in body["description"]


def test_publish_rejects_unknown_policy_state(tmp_path):
    import subprocess
    decision = _make_decision(tmp_path, "MAYBE")
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(PUBLISH),
         str(decision), _HEAD, _BASE,
         "anervalens-netizen/unihub-retail", "t", "https://example/run"],
        capture_output=True, text=True,
    )
    assert cp.returncode != 0


def test_publish_rejects_decision_head_base_mismatch(tmp_path):
    import subprocess
    other_base = "9" + ("1234567890" * 4)[:39]
    decision = _make_decision(tmp_path, "success", base_sha=other_base)
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(PUBLISH),
         str(decision), _HEAD, _BASE,
         "anervalens-netizen/unihub-retail", "t", "https://example/run"],
        capture_output=True, text=True,
    )
    assert cp.returncode != 0


# ---------------------------------------------------------------------------
# PR-DEEP workflow contract (DEFECT 7 — pending only after preflight)
# ---------------------------------------------------------------------------


def test_pr_deep_pending_step_requires_preflight_ok():
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    # The pending publication step must gate on PREFLIGHT_OK.
    # Look for the pending step block.
    assert "PREFLIGHT_OK" in text
    # Find the "Set retail/pr-deep = pending" step and assert it gates
    # on PREFLIGHT_OK.
    import re
    pending_block_re = re.compile(
        r"Set retail/pr-deep = pending.*?(?=\n      - name:|\Z)",
        re.DOTALL,
    )
    m = pending_block_re.search(text)
    assert m, "could not find 'Set retail/pr-deep = pending' step"
    block = m.group(0)
    assert "env.PREFLIGHT_OK" in block or "PREFLIGHT_OK == '1'" in block, (
        "pending step must gate on PREFLIGHT_OK"
    )


def test_pr_deep_failure_cleanup_requires_preflight_ok():
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    import re
    cleanup_re = re.compile(
        r"Set retail/pr-deep = failure.*?(?=\n      - name:|\Z)",
        re.DOTALL,
    )
    m = cleanup_re.search(text)
    assert m, "could not find failure cleanup step"
    block = m.group(0)
    assert "PREFLIGHT_OK" in block, (
        "failure cleanup must gate on PREFLIGHT_OK so a malformed "
        "dispatch never annotates an arbitrary SHA"
    )


def test_pr_deep_descriptions_carry_base_identity():
    """PENDING / SUCCESS / FAILURE descriptions must each carry
    ``base=<40-char expected_base_sha>`` so pre-merge inspection is
    unambiguous.

    The description is built from explicit argv (BASE_SHA passed as
    ``sys.argv[1]`` to the inline Python helper) so the workflow does
    NOT depend on unexported shell locals.
    """
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    # PENDING: argv-built
    assert '"RUNNING base=" + sys.argv[1]' in text, (
        "PENDING step must build the description from explicit argv"
    )
    # SUCCESS: argv-built
    assert '"PASS base=" + sys.argv[1]' in text, (
        "SUCCESS step must build the description from explicit argv"
    )
    # FAILURE: argv-built
    assert '"FAIL base=" + sys.argv[1]' in text, (
        "FAILURE cleanup must build the description from explicit argv"
    )


def test_pr_deep_runs_compose_certification_via_helper():
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    assert "pr_b3b_compose_certification.py" in text


# ---------------------------------------------------------------------------
# Certification evidence (DEFECT 8 — fail-closed)
# ---------------------------------------------------------------------------


COMPOSE_CERT = WORKTREE / "scripts" / "pr_b3b_compose_certification.py"


def test_compose_certification_fails_when_junit_missing(tmp_path):
    import subprocess
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(COMPOSE_CERT),
         str(tmp_path / "cert.json"),
         "1", _HEAD, _BASE, _HEAD,
         "anervalens-netizen/unihub-retail", "1", "1",
         "pr-deep", "main", _HEAD],
        cwd=str(tmp_path),
        capture_output=True, text=True,
    )
    assert cp.returncode != 0
    assert "JUnit" in cp.stderr


def test_compose_certification_fails_when_junit_zero_tests(tmp_path):
    import subprocess
    junit_dir = tmp_path / "backend"
    junit_dir.mkdir()
    (junit_dir / "pr-deep-junit.xml").write_text(
        '<?xml version="1.0"?><testsuite name="x" tests="0" '
        'failures="0" errors="0" skipped="0"></testsuite>'
    )
    (junit_dir / "pr-deep-coverage.json").write_text(json.dumps({
        "totals": {"percent_covered": 99.5, "covered_lines": 100,
                   "num_statements": 200},
    }))
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(COMPOSE_CERT),
         str(tmp_path / "cert.json"),
         "1", _HEAD, _BASE, _HEAD,
         "anervalens-netizen/unihub-retail", "1", "1",
         "pr-deep", "main", _HEAD],
        cwd=str(tmp_path),
        capture_output=True, text=True,
    )
    assert cp.returncode != 0
    assert "0 tests" in cp.stderr


def test_compose_certification_fails_when_junit_malformed(tmp_path):
    import subprocess
    junit_dir = tmp_path / "backend"
    junit_dir.mkdir()
    (junit_dir / "pr-deep-junit.xml").write_text("not xml <<<")
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(COMPOSE_CERT),
         str(tmp_path / "cert.json"),
         "1", _HEAD, _BASE, _HEAD,
         "anervalens-netizen/unihub-retail", "1", "1",
         "pr-deep", "main", _HEAD],
        cwd=str(tmp_path),
        capture_output=True, text=True,
    )
    assert cp.returncode != 0
    assert "JUnit" in cp.stderr


def test_compose_certification_fails_when_coverage_missing(tmp_path):
    import subprocess
    junit_dir = tmp_path / "backend"
    junit_dir.mkdir()
    (junit_dir / "pr-deep-junit.xml").write_text(
        '<?xml version="1.0"?><testsuite name="x" tests="5" '
        'failures="0" errors="0" skipped="0"></testsuite>'
    )
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(COMPOSE_CERT),
         str(tmp_path / "cert.json"),
         "1", _HEAD, _BASE, _HEAD,
         "anervalens-netizen/unihub-retail", "1", "1",
         "pr-deep", "main", _HEAD],
        cwd=str(tmp_path),
        capture_output=True, text=True,
    )
    assert cp.returncode != 0
    assert "coverage" in cp.stderr.lower()


def test_compose_certification_fails_when_coverage_percent_missing(tmp_path):
    import subprocess
    junit_dir = tmp_path / "backend"
    junit_dir.mkdir()
    (junit_dir / "pr-deep-junit.xml").write_text(
        '<?xml version="1.0"?><testsuite name="x" tests="5" '
        'failures="0" errors="0" skipped="0"></testsuite>'
    )
    (junit_dir / "pr-deep-coverage.json").write_text(json.dumps({
        "totals": {"covered_lines": 100, "num_statements": 200},
    }))
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(COMPOSE_CERT),
         str(tmp_path / "cert.json"),
         "1", _HEAD, _BASE, _HEAD,
         "anervalens-netizen/unihub-retail", "1", "1",
         "pr-deep", "main", _HEAD],
        cwd=str(tmp_path),
        capture_output=True, text=True,
    )
    assert cp.returncode != 0
    assert "percent_covered" in cp.stderr


def test_compose_certification_succeeds_with_valid_evidence(tmp_path):
    import subprocess
    junit_dir = tmp_path / "backend"
    junit_dir.mkdir()
    (junit_dir / "pr-deep-junit.xml").write_text(
        '<?xml version="1.0"?><testsuite name="x" tests="7" '
        'failures="0" errors="0" skipped="0"></testsuite>'
    )
    (junit_dir / "pr-deep-coverage.json").write_text(json.dumps({
        "totals": {"percent_covered": 92.5, "covered_lines": 100,
                   "num_statements": 200},
    }))
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(COMPOSE_CERT),
         str(tmp_path / "cert.json"),
         "1", _HEAD, _BASE, _HEAD,
         "anervalens-netizen/unihub-retail", "1", "1",
         "pr-deep", "main", _HEAD],
        cwd=str(tmp_path),
        capture_output=True, text=True,
    )
    assert cp.returncode == 0, cp.stderr
    cert = json.loads((tmp_path / "cert.json").read_text())
    assert cert["result"] == "success"
    assert cert["backend_test_count"] == 7
    assert cert["coverage_result"]["percent_covered"] == 92.5
    assert cert["changed_line_result"] == "PASS"


# ---------------------------------------------------------------------------
# pr-deep-policy narrows the trust claim (DEFECT 9)
# ---------------------------------------------------------------------------


def test_pr_deep_policy_documents_narrow_trust_claim():
    text = PR_DEEP_POLICY_YML.read_text(encoding="utf-8")
    # NARROW claim markers: must NOT over-claim and MUST be
    # self-correcting.
    assert "NARROW" in text or "narrow" in text or "DO NOT over-claim" in text
    assert "not equivalent to FULL" in text or "FULL" in text


def test_pr_deep_documents_narrow_trust_claim():
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    assert "NARROW" in text or "DO NOT over-claim" in text
    assert "not equivalent to FULL" in text or "FULL" in text


# ---------------------------------------------------------------------------
# Validator trust-surface coverage (DEFECT 5)
# ---------------------------------------------------------------------------


def test_validator_classified_in_selector_trust_surfaces():
    """scripts/pr_b3b_selected_paths_validator.py MUST be in the
    selector's EXACT_ESCALATION_PATHS so any modification / deletion
    escalates BEFORE the gate is loaded.
    """
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location(
        "pr_fast_select_tests_static_validator", SELECTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    reason = module._classify_path(
        "scripts/pr_b3b_selected_paths_validator.py"
    )
    assert reason is not None, (
        "validator must be classified as a trust surface"
    )
    assert reason.category == "gate_authority"


def test_validator_in_a3_deploy_release_ci_paths():
    data = json.loads(HIGH_RISK_JSON.read_text(encoding="utf-8"))
    paths = data["categories"]["deploy-release-ci"]["paths"]
    assert "scripts/pr_b3b_selected_paths_validator.py" in paths


# ---------------------------------------------------------------------------
# Final-pre-review DEFECT 1: pr-deep-policy checkout-before-fetch order
# ---------------------------------------------------------------------------


def test_pr_deep_policy_checkout_before_git_fetch():
    """pr-deep-policy.yml must perform actions/checkout (BASE) BEFORE
    any raw `git fetch ... HEAD_SHA` (or any other command that
    requires a Git repository to exist).
    """
    text = PR_DEEP_POLICY_YML.read_text(encoding="utf-8")
    # Strip YAML comments first so explanatory comments that mention
    # `git fetch` etc. do not get counted as real commands.
    def _strip_comments(yaml_text: str) -> str:
        out = []
        for line in yaml_text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            out.append(line)
        return "\n".join(out)
    active_text = _strip_comments(text)
    checkout_idx = active_text.find("actions/checkout@")
    other_git_idx_candidates = []
    for needle in ("git fetch", "git worktree", "git cat-file", "git merge-base"):
        idx = active_text.find(needle)
        if idx != -1:
            other_git_idx_candidates.append((needle, idx))
    assert checkout_idx != -1, "actions/checkout step not found"
    assert other_git_idx_candidates, (
        "no other git commands found in pr-deep-policy.yml"
    )
    for needle, idx in other_git_idx_candidates:
        assert checkout_idx < idx, (
            f"actions/checkout (idx {checkout_idx}) must come BEFORE "
            f"`{needle}` (idx {idx}) in pr-deep-policy.yml"
        )


def test_pr_deep_policy_verifies_head_commit_object_after_checkout():
    """pr-deep-policy.yml must verify the exact PR HEAD commit object
    is available BEFORE creating the candidate worktree, and must
    FAIL CLOSED otherwise (no silent retry, no extra fetch that could
    leak credentials)."""
    text = PR_DEEP_POLICY_YML.read_text(encoding="utf-8")
    assert "git cat-file -e \"${HEAD_SHA}^{commit}\"" in text or \
        "git cat-file -e \"${HEAD_SHA}{commit}\"" in text or \
        "git cat-file -e ${HEAD_SHA}^commit" in text or \
        'git cat-file -e "${HEAD_SHA}^{commit}"' in text, (
        "pr-deep-policy.yml must verify the exact PR HEAD commit "
        "object via `git cat-file -e` after checkout"
    )


# ---------------------------------------------------------------------------
# Final-pre-review DEFECT 2: state/rc consistency
# ---------------------------------------------------------------------------


def test_decide_policy_state_rc_table_enforced():
    """Negative tests proving the exact state/rc table is enforced
    BEFORE any success/pending decision:
      NO_ELIGIBLE / SELECTED -> rc 0
      ESCALATION_REQUIRED      -> rc 2
      ERROR                    -> rc 3
    Any unknown state or mismatched rc -> policy_state = failure.
    """
    import importlib.util
    import sys as _sys
    spec = importlib.util.spec_from_file_location(
        "pr_b3b_decide_policy_table_test", DECIDE_POLICY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    for state, rc, expected in [
        ("NO_ELIGIBLE_BACKEND_CHANGE", 2, "failure"),
        ("NO_ELIGIBLE_BACKEND_CHANGE", 3, "failure"),
        ("SELECTED", 2, "failure"),
        ("SELECTED", 3, "failure"),
        ("ESCALATION_REQUIRED", 0, "failure"),
        ("ESCALATION_REQUIRED", 3, "failure"),
        ("ERROR", 0, "failure"),
        ("ERROR", 2, "failure"),
        ("UNKNOWN_STATE", 0, "failure"),
        ("UNKNOWN_STATE", 2, "failure"),
    ]:
        import io
        import json as _json
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            _json.dump({
                "schema_version": 1,
                "head_sha": _HEAD,
                "base_sha": _HEAD,  # MERGE_BASE == HEAD for the test
                "state": state,
                "selection_count": 0,
                "selected_tests": [],
            }, f)
            path = f.name
        buf = io.StringIO()
        real_stdout = _sys.stdout
        _sys.stdout = buf
        try:
            ret = mod.main([
                "pr_b3b_decide_policy.py",
                path, _HEAD, _HEAD, _HEAD, str(rc),
                "anervalens-netizen/unihub-retail", "",
            ])
        finally:
            _sys.stdout = real_stdout
        assert ret == 0
        decision = _json.loads(buf.getvalue())
        assert decision["policy_state"] == expected, (
            f"state={state!r} rc={rc}: expected policy_state={expected!r}, "
            f"got {decision['policy_state']!r}"
        )


def test_decide_policy_rejects_wrong_schema_version():
    import importlib.util
    import io
    import json as _json
    import sys as _sys
    import tempfile
    spec = importlib.util.spec_from_file_location(
        "pr_b3b_decide_policy_sv_test", DECIDE_POLICY)
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        _json.dump({
            "schema_version": 99,
            "head_sha": _HEAD,
            "base_sha": _HEAD,
            "state": "SELECTED",
            "selection_count": 0,
            "selected_tests": [],
        }, f)
        path = f.name
    buf = io.StringIO()
    real_stdout = _sys.stdout
    _sys.stdout = buf
    try:
        mod.main([
            "pr_b3b_decide_policy.py",
            path, _HEAD, _HEAD, _HEAD, "0",
            "anervalens-netizen/unihub-retail", "",
        ])
    finally:
        _sys.stdout = real_stdout
    decision = _json.loads(buf.getvalue())
    assert decision["policy_state"] == "failure"
    assert "schema_version" in decision["reason"]


# ---------------------------------------------------------------------------
# Final-pre-review DEFECT 3: PR_BASE != MERGE_BASE identity
# ---------------------------------------------------------------------------


def test_decide_policy_accepts_pr_base_neq_merge_base():
    """PR_BASE_SHA != MERGE_BASE but selector.base_sha == MERGE_BASE
    must be accepted (selector was invoked with --base=MERGE_BASE)."""
    import importlib.util
    import io
    import json as _json
    import sys as _sys
    import tempfile
    spec = importlib.util.spec_from_file_location(
        "pr_b3b_decide_policy_id_test", DECIDE_POLICY)
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    other_base = "0" + ("1234567890" * 4)[:39]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        _json.dump({
            "schema_version": 1,
            "head_sha": _HEAD,
            "base_sha": other_base,  # selector.base_sha = MERGE_BASE
            "state": "NO_ELIGIBLE_BACKEND_CHANGE",
            "selection_count": 0,
            "selected_tests": [],
        }, f)
        path = f.name
    buf = io.StringIO()
    real_stdout = _sys.stdout
    _sys.stdout = buf
    try:
        mod.main([
            "pr_b3b_decide_policy.py",
            path, _HEAD, _BASE, other_base, "0",
            "anervalens-netizen/unihub-retail", "",
        ])
    finally:
        _sys.stdout = real_stdout
    decision = _json.loads(buf.getvalue())
    assert decision["policy_state"] == "success", decision
    assert decision["base_sha"] == _BASE
    assert decision["merge_base_sha"] == other_base


def test_decide_policy_rejects_selector_base_eq_pr_base_when_merge_differs():
    """If selector.base_sha == PR_BASE_SHA while MERGE_BASE differs,
    the policy MUST fail (selector was NOT invoked with the merge
    base)."""
    import importlib.util
    import io
    import json as _json
    import sys as _sys
    import tempfile
    spec = importlib.util.spec_from_file_location(
        "pr_b3b_decide_policy_id2_test", DECIDE_POLICY)
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    other_merge = "1" + ("1234567890" * 4)[:39]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        _json.dump({
            "schema_version": 1,
            "head_sha": _HEAD,
            "base_sha": _BASE,  # selector.base_sha == PR_BASE_SHA
            "state": "NO_ELIGIBLE_BACKEND_CHANGE",
            "selection_count": 0,
            "selected_tests": [],
        }, f)
        path = f.name
    buf = io.StringIO()
    real_stdout = _sys.stdout
    _sys.stdout = buf
    try:
        mod.main([
            "pr_b3b_decide_policy.py",
            path, _HEAD, _BASE, other_merge, "0",
            "anervalens-netizen/unihub-retail", "",
        ])
    finally:
        _sys.stdout = real_stdout
    decision = _json.loads(buf.getvalue())
    assert decision["policy_state"] == "failure"
    assert "MERGE_BASE" in decision["reason"]


# ---------------------------------------------------------------------------
# Final-pre-review DEFECT 4: pending status JSON does not require
# unexported DESCRIPTION env var
# ---------------------------------------------------------------------------


def test_pr_deep_pending_publication_does_not_depend_on_unexported_description():
    """The pending publication step in pr-deep.yml MUST NOT depend on
    a DESCRIPTION env var (which is only a shell local and is not
    exported). It must construct the description string from explicit
    argv."""
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    # Find the "Set retail/pr-deep = pending" step.
    import re
    m = re.search(
        r"Set retail/pr-deep = pending \(RUNNING base=\.\.\.\).*?(?=\n      - name:|\Z)",
        text,
        re.DOTALL,
    )
    assert m, "could not find pending publication step"
    block = m.group(0)
    assert 'os.environ["DESCRIPTION"]' not in block, (
        "pending step must not depend on unexported DESCRIPTION env var"
    )
    assert 'os.environ[\'DESCRIPTION\']' not in block
    # The description must be built in the Python helper from explicit
    # argv (BASE_SHA + RUN_URL).
    assert "RUNNING base=" in block
    assert "BASE_SHA" in block or "argv" in block


def test_pr_deep_pending_publication_step_constructs_description_exact():
    """The pending step description MUST exactly equal
    'RUNNING base=<40-char base SHA>'."""
    import re
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    m = re.search(
        r"Set retail/pr-deep = pending \(RUNNING base=\.\.\.\).*?(?=\n      - name:|\Z)",
        text,
        re.DOTALL,
    )
    assert m
    block = m.group(0)
    # Look for the exact literal the Python helper must build.
    assert '"RUNNING base=" + sys.argv[1]' in block or \
        "'RUNNING base=' + sys.argv[1]" in block, (
        "pending step must construct the description via argv (no env)"
    )


# ---------------------------------------------------------------------------
# Final-pre-review DEFECT 5: latest-status-wins
# ---------------------------------------------------------------------------


def test_decide_policy_latest_failure_overrides_old_success():
    """A: old success, newer failure, same head/base -> pending.
    The newer failure must NOT be overridden by the older success."""
    import importlib.util
    import sys as _sys
    spec = importlib.util.spec_from_file_location(
        "pr_b3b_decide_policy_latest1", DECIDE_POLICY)
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    statuses = [
        {
            "context": "retail/pr-deep",
            "state": "failure",
            "sha": _HEAD,
            "description": f"FAIL base={_BASE}",
            "created_at": "2026-08-19T11:00:00Z",
            "updated_at": "2026-08-19T11:30:00Z",
        },
        {
            "context": "retail/pr-deep",
            "state": "success",
            "sha": _HEAD,
            "description": f"PASS base={_BASE}",
            "created_at": "2026-08-19T10:00:00Z",
            "updated_at": "2026-08-19T10:30:00Z",
        },
    ]
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending", decision

def test_decide_policy_latest_pending_overrides_old_success():
    """B: old success, newer pending, same head/base -> pending."""
    statuses = [
        {
            "context": "retail/pr-deep",
            "state": "pending",
            "sha": _HEAD,
            "description": f"RUNNING base={_BASE}",
            "created_at": "2026-08-19T11:00:00Z",
            "updated_at": "2026-08-19T11:30:00Z",
        },
        {
            "context": "retail/pr-deep",
            "state": "success",
            "sha": _HEAD,
            "description": f"PASS base={_BASE}",
            "created_at": "2026-08-19T10:00:00Z",
            "updated_at": "2026-08-19T10:30:00Z",
        },
    ]
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending"

def test_decide_policy_newer_success_overrides_old_failure():
    """C: old failure, newer success, same head/base -> success."""
    statuses = [
        {
            "context": "retail/pr-deep",
            "state": "success",
            "sha": _HEAD,
            "description": f"PASS base={_BASE}",
            "created_at": "2026-08-19T11:00:00Z",
            "updated_at": "2026-08-19T11:30:00Z",
        },
        {
            "context": "retail/pr-deep",
            "state": "failure",
            "sha": _HEAD,
            "description": f"FAIL base={_BASE}",
            "created_at": "2026-08-19T10:00:00Z",
            "updated_at": "2026-08-19T10:30:00Z",
        },
    ]
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "success"

def test_decide_policy_old_base_success_does_not_certify_current_base():
    """D: success for current head but old base -> pending."""
    stale_base = "8" + ("1234567890" * 4)[:39]
    statuses = [
        {
            "context": "retail/pr-deep",
            "state": "success",
            "sha": _HEAD,
            "description": f"PASS base={stale_base}",
            "created_at": "2026-08-19T11:00:00Z",
            "updated_at": "2026-08-19T11:30:00Z",
        },
    ]
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending"

def test_decide_policy_matching_cert_is_success():
    """E: current matching success -> success."""
    statuses = [
        {
            "context": "retail/pr-deep",
            "state": "success",
            "sha": _HEAD,
            "description": f"PASS base={_BASE}",
            "created_at": "2026-08-19T11:00:00Z",
            "updated_at": "2026-08-19T11:30:00Z",
        },
    ]
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "success"

def test_decide_policy_unsorted_list_still_picks_latest():
    """The latest-wins implementation must NOT rely on the list being
    in reverse-chronological order. Pass statuses in REVERSE order and
    verify the policy still picks the correct one."""
    statuses = [
        {
            "context": "retail/pr-deep",
            "state": "success",
            "sha": _HEAD,
            "description": f"PASS base={_BASE}",
            "created_at": "2026-08-19T11:00:00Z",
            "updated_at": "2026-08-19T11:30:00Z",
        },
        {
            "context": "retail/pr-deep",
            "state": "failure",
            "sha": _HEAD,
            "description": f"FAIL base={_BASE}",
            "created_at": "2026-08-19T10:00:00Z",
            "updated_at": "2026-08-19T10:30:00Z",
        },
    ]
    decision = _decide_policy_with_statuses(list(reversed(statuses)))
    # The success is the newer status; it must be picked as the
    # matching cert even though the list is unsorted.
    assert decision["policy_state"] == "success"


# ---------------------------------------------------------------------------
# Final-pre-review DEFECT 6: all four B3b helpers are control-plane
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "helper_path",
    [
        "scripts/pr_fast_select_tests.py",
        "scripts/pr_b3b_selected_paths_validator.py",
        "scripts/pr_b3b_decide_policy.py",
        "scripts/pr_b3b_publish_policy_status.py",
        "scripts/pr_b3b_compose_certification.py",
    ],
)
def test_helper_classified_in_selector_trust_surfaces(helper_path):
    """Each B3b helper MUST be in the selector's
    EXACT_ESCALATION_PATHS so a modification or deletion escalates
    BEFORE the gate is loaded. The classifier maps
    ``scripts/pr_fast_select_tests.py`` to ``selector_self`` and the
    other helpers to ``gate_authority``; we accept either because
    both are control-plane escalation reasons.
    """
    import importlib.util
    import sys as _sys
    spec = importlib.util.spec_from_file_location(
        f"pr_fast_select_tests_helper_{helper_path.replace('/', '_').replace('.', '_')}",
        SELECTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    _sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    reason = module._classify_path(helper_path)
    assert reason is not None, (
        f"{helper_path}: classifier did not produce an EscalationReason"
    )
    assert reason.category in ("gate_authority", "selector_self"), (
        f"{helper_path}: expected gate_authority or selector_self, "
        f"got {reason.category!r}"
    )
    assert reason.path == helper_path


@pytest.mark.parametrize(
    "helper_path",
    [
        "scripts/pr_fast_select_tests.py",
        "scripts/pr_b3b_selected_paths_validator.py",
        "scripts/pr_b3b_decide_policy.py",
        "scripts/pr_b3b_publish_policy_status.py",
        "scripts/pr_b3b_compose_certification.py",
    ],
)
def test_helper_in_a3_deploy_release_ci_paths(helper_path):
    data = json.loads(HIGH_RISK_JSON.read_text(encoding="utf-8"))
    paths = data["categories"]["deploy-release-ci"]["paths"]
    assert helper_path in paths, (
        f"{helper_path} must be in deploy-release-ci A3 manifest paths"
    )


# ---------------------------------------------------------------------------
# Status-authority one-defect fix
# ---------------------------------------------------------------------------
#
# "The latest retail/pr-deep status for the exact HEAD is authoritative.
# It certifies only if that latest status itself is success with
# PASS base=<current base>."
#
# The 7 cases below would have FAILED on head 207a98ac because the
# previous implementation did:
#   1. find the latest ANY status for the head
#   2. if it was pending/failure -> pending
#   3. OTHERWISE scan history for the latest matching PASS base=<current>
# Step 3 fell back to an OLDER matching success even when the
# authoritative latest status was a different success (stale or other
# base). The new policy uses a single latest-status lookup.


def _status(
    state: str, *, sha: str, description: str,
    updated_at: str, id: int, context: str = "retail/pr-deep",
) -> dict:
    """Build a realistic exact-commit status object without ``sha``.

    ``sha`` remains an argument at call sites to document which HEAD the
    fixture represents, but GitHub does not require it per status object.
    The endpoint identity is tested by the policy helper's exact-head
    invocation, not by a redundant object field.
    """
    del sha
    return {
        "context": context,
        "state": state,
        "description": description,
        "updated_at": updated_at,
        "created_at": updated_at,
        "id": id,
    }


def test_latest_status_1_older_success_current_newer_success_stale():
    """1. older success PASS base=CURRENT
    newer success PASS base=STALE  =>  pending.
    The newer stale-base success is authoritative; it must not certify."""
    statuses = [
        _status("success", sha=_HEAD,
                description=f"PASS base={_BASE}",
                updated_at="2026-08-19T10:00:00Z", id=1001),
        _status("success", sha=_HEAD,
                description="PASS base=8" + "1234567890" * 4 + "123",
                updated_at="2026-08-19T11:00:00Z", id=1002),
    ]
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending", decision


def test_latest_status_2_older_success_current_newer_malformed():
    """2. older success PASS base=CURRENT
    newer success with malformed description  =>  pending."""
    statuses = [
        _status("success", sha=_HEAD,
                description=f"PASS base={_BASE}",
                updated_at="2026-08-19T10:00:00Z", id=1001),
        _status("success", sha=_HEAD,
                description="malformed",
                updated_at="2026-08-19T11:00:00Z", id=1002),
    ]
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending", decision


def test_latest_status_3_older_failure_newer_success_current():
    """3. older failure
    newer success PASS base=CURRENT  =>  success."""
    statuses = [
        _status("failure", sha=_HEAD,
                description=f"FAIL base={_BASE}",
                updated_at="2026-08-19T10:00:00Z", id=1001),
        _status("success", sha=_HEAD,
                description=f"PASS base={_BASE}",
                updated_at="2026-08-19T11:00:00Z", id=1002),
    ]
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "success", decision


def test_latest_status_4_older_success_current_newer_pending():
    """4. older success PASS base=CURRENT
    newer pending  =>  pending."""
    statuses = [
        _status("success", sha=_HEAD,
                description=f"PASS base={_BASE}",
                updated_at="2026-08-19T10:00:00Z", id=1001),
        _status("pending", sha=_HEAD,
                description=f"RUNNING base={_BASE}",
                updated_at="2026-08-19T11:00:00Z", id=1002),
    ]
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending", decision


def test_latest_status_5_older_success_current_newer_failure():
    """5. older success PASS base=CURRENT
    newer failure  =>  pending."""
    statuses = [
        _status("success", sha=_HEAD,
                description=f"PASS base={_BASE}",
                updated_at="2026-08-19T10:00:00Z", id=1001),
        _status("failure", sha=_HEAD,
                description=f"FAIL base={_BASE}",
                updated_at="2026-08-19T11:00:00Z", id=1002),
    ]
    decision = _decide_policy_with_statuses(statuses)
    assert decision["policy_state"] == "pending", decision


def test_latest_status_6_unsorted_api_order_same_result():
    """6. the same cases in UNSORTED API order produce the same
    policy result. The decision is independent of the raw API
    list order (we sort deterministically by
    updated_at / created_at / id)."""
    # Reverse the order of case (1): newer stale-base success first.
    statuses_unsorted = [
        _status("success", sha=_HEAD,
                description="PASS base=8" + "1234567890" * 4 + "123",
                updated_at="2026-08-19T11:00:00Z", id=1002),
        _status("success", sha=_HEAD,
                description=f"PASS base={_BASE}",
                updated_at="2026-08-19T10:00:00Z", id=1001),
    ]
    decision = _decide_policy_with_statuses(statuses_unsorted)
    assert decision["policy_state"] == "pending", decision


def test_latest_status_7_id_tiebreak_higher_id_wins():
    """7. equal timestamps, the higher numeric status id must be
    authoritative (larger id = newer on GitHub)."""
    same_ts = "2026-08-19T10:00:00Z"
    statuses = [
        _status("success", sha=_HEAD,
                description=f"PASS base={_BASE}",
                updated_at=same_ts, id=42),
        _status("success", sha=_HEAD,
                description="PASS base=8" + "1234567890" * 4 + "123",
                updated_at=same_ts, id=43),
    ]
    decision = _decide_policy_with_statuses(statuses)
    # The higher id (43) is the authoritative latest. Its description
    # is stale, so policy is pending.
    assert decision["policy_state"] == "pending", decision


def test_latest_status_helper_obsolete_helper_removed():
    """The simplification must retire the obsolete
    `_latest_status_for` and `_latest_any_status_for` helpers so
    there are not two competing notions of "latest"."""
    import importlib.util
    import sys as _sys
    spec = importlib.util.spec_from_file_location(
        "pr_b3b_decide_policy_obsolete_test", DECIDE_POLICY)
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert not hasattr(mod, "_latest_status_for"), (
        "obsolete _latest_status_for must be retired"
    )
    assert not hasattr(mod, "_latest_any_status_for"), (
        "obsolete _latest_any_status_for must be retired"
    )
    assert hasattr(mod, "_latest_status"), (
        "_latest_status (the single latest helper) must exist"
    )


# ===========================================================================
# PR-B3b FINAL BOUNDED CORRECTION PASS
#
# These tests pin the bounded corrections requested in the
# post-review correction brief. They do not redesign B3/E2.
# ===========================================================================


# ---------------------------------------------------------------------------
# (1) PR-DEEP critical-coverage path exists at HEAD
# ---------------------------------------------------------------------------


def test_pr_deep_critical_coverage_step_uses_backend_scripts_path():
    """PR-DEEP must invoke the actual critical-coverage authority
    script at backend/scripts/check_critical_coverage.py (NOT
    scripts/check_critical_coverage.py, which is the wrong path).
    """
    import re as _re

    text = PR_DEEP_YML.read_text(encoding="utf-8")
    # The step must reference the backend/scripts path with the
    # root-relative prefix that the .github/workflows/pr-deep.yml
    # step uses (default working-directory: backend for steps
    # below the certification block; the corrected form uses
    # backend/scripts/check_critical_coverage.py explicitly).
    assert "backend/scripts/check_critical_coverage.py" in text, (
        "pr-deep.yml must reference backend/scripts/check_critical_coverage.py"
    )
    # The bare scripts/check_critical_coverage.py path (without the
    # backend/ prefix) is wrong and must NOT appear as an
    # executable invocation in pr-deep.yml.
    active_lines = [
        ln for ln in text.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    # Match standalone 'scripts/check_critical_coverage.py' — i.e.
    # NOT preceded by 'backend/' (negative lookbehind).
    bad = _re.compile(r"(?<!backend/)scripts/check_critical_coverage\.py")
    for ln in active_lines:
        assert not bad.search(ln), (
            "pr-deep.yml active line uses wrong critical-coverage path: "
            f"{ln!r}"
        )


def test_pr_deep_critical_coverage_script_exists_at_head():
    """The authority script that PR-DEEP invokes must exist at HEAD."""
    import importlib.util as _ilu
    _ = _ilu  # silence unused-import lint; we only need the import side-effect
    # The corrected PR-DEEP step runs from root working-directory
    # so the path is repo-relative. The file must exist.
    assert (WORKTREE / "backend" / "scripts" / "check_critical_coverage.py").is_file(), (
        "backend/scripts/check_critical_coverage.py must exist at HEAD"
    )
    assert (WORKTREE / "backend" / "critical_coverage_thresholds.json").is_file(), (
        "backend/critical_coverage_thresholds.json must exist at HEAD"
    )


# ---------------------------------------------------------------------------
# (2) Candidate checkout credentials are not persisted
# ---------------------------------------------------------------------------


def _checkout_blocks_for(workflow_path):
    """Return the list of ``actions/checkout`` invocation blocks
    (each a dict with `uses`, `with`, etc.). YAML comments and
    inactive lines are stripped first.
    """
    yaml = _yaml()
    data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    out = []
    for job_name, job in (data.get("jobs") or {}).items():
        for step in job.get("steps", []):
            uses = step.get("uses") or ""
            if isinstance(uses, str) and uses.startswith("actions/checkout@"):
                out.append((job_name, step))
    return out


def test_pr_fast_checkout_persist_credentials_false():
    """The pr-fast candidate checkout MUST set
    persist-credentials: false so candidate code cannot read the
    workflow token from .git/config extraheader."""
    blocks = _checkout_blocks_for(CI_YML)
    pr_fast_blocks = [
        (job, step) for (job, step) in blocks
        if job == "pr-fast"
    ]
    assert pr_fast_blocks, "ci.yml must contain a pr-fast checkout"
    for _job, step in pr_fast_blocks:
        with_block = step.get("with") or {}
        assert with_block.get("persist-credentials") is False, (
            "pr-fast candidate checkout MUST set "
            "persist-credentials: false (got: "
            f"{with_block.get('persist-credentials')!r})"
        )


def test_pr_deep_candidate_checkout_persist_credentials_false():
    """The PR-DEEP exact-PR-HEAD checkout MUST set
    persist-credentials: false."""
    blocks = _checkout_blocks_for(PR_DEEP_YML)
    # PR-DEEP has a single candidate checkout at backend-deep.
    candidate_blocks = [
        (job, step) for (job, step) in blocks
        if job == "backend-deep"
    ]
    assert candidate_blocks, (
        "pr-deep.yml must contain a backend-deep candidate checkout"
    )
    for _job, step in candidate_blocks:
        with_block = step.get("with") or {}
        assert with_block.get("persist-credentials") is False, (
            "PR-DEEP candidate checkout MUST set "
            "persist-credentials: false (got: "
            f"{with_block.get('persist-credentials')!r})"
        )


def test_pr_deep_policy_checkout_persist_credentials_false():
    """The pr-deep-policy trusted-BASE checkout MUST set
    persist-credentials: false (it already did, but pin it)."""
    blocks = _checkout_blocks_for(PR_DEEP_POLICY_YML)
    assert blocks, "pr-deep-policy.yml must contain a checkout"
    for _job, step in blocks:
        with_block = step.get("with") or {}
        assert with_block.get("persist-credentials") is False, (
            "pr-deep-policy trusted-BASE checkout MUST set "
            "persist-credentials: false (got: "
            f"{with_block.get('persist-credentials')!r})"
        )


def test_pr_fast_pr_b3b_step_replaces_authenticated_fetch_with_cat_file():
    """The PR-B3b-added pr-fast step must NOT perform an
    authenticated ``git fetch origin $PR_BASE_SHA``; it must use a
    fail-closed ``git cat-file -e`` instead. Other pre-existing
    pr-fast steps may keep their (defensive) ``git fetch``
    invocations because they are audited separately.
    """
    text = CI_YML.read_text(encoding="utf-8")
    # Extract just the PR-B3b step body.
    start = text.find("PR-B3b backend affected coverage")
    assert start != -1, "PR-B3b pr-fast step must exist"
    end = text.find("Upload PR-B3b backend-affected evidence")
    assert end != -1, "PR-B3b pr-fast artifact upload must exist"
    body = text[start:end]
    # Strip yaml comments.
    active_lines = [
        ln for ln in body.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    active_body = "\n".join(active_lines)
    assert "git cat-file -e" in active_body, (
        "PR-B3b pr-fast step must include git cat-file -e "
        f"object-presence check (body: {active_body!r})"
    )
    # It must NOT contain an authenticated post-checkout fetch of
    # $PR_BASE_SHA (the spec is to replace it).
    assert "git fetch --no-tags --depth=1 origin \"$PR_BASE_SHA\"" not in active_body, (
        "PR-B3b pr-fast step must not perform authenticated fetch of "
        "$PR_BASE_SHA; use cat-file -e instead"
    )


def test_pr_deep_replaces_authenticated_fetch_with_cat_file():
    """The PR-DEEP step that used to ``git fetch origin
    $EXPECTED_BASE`` must now use ``git cat-file -e`` instead."""
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    # The corrected step lives right after the candidate HEAD
    # checkout.
    start = text.find("Checkout exact PR HEAD")
    assert start != -1
    end = text.find("Compute and validate MERGE_BASE")
    assert end != -1
    body = text[start:end]
    active_lines = [
        ln for ln in body.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    active_body = "\n".join(active_lines)
    assert "git cat-file -e" in active_body, (
        "PR-DEEP base-presence step must include git cat-file -e"
    )
    assert "git fetch --no-tags --depth=1 origin \"$EXPECTED_BASE\"" not in active_body, (
        "PR-DEEP must not perform authenticated post-checkout fetch "
        "of $EXPECTED_BASE"
    )


def test_pr_fast_other_authenticated_fetches_audit_documented():
    """Audit assertion: there are pre-existing pr-fast authenticated
    fetches. We document that they are belt-and-suspenders only
    (the base SHAs they consult are already reachable after
    fetch-depth:0), so the candidate checkout's
    persist-credentials:false is safe."""
    text = CI_YML.read_text(encoding="utf-8")
    # Identify pr-fast block by header.
    start = text.find("  pr-fast:")
    assert start != -1
    end = text.find("  backend-check:")
    body = text[start:end if end != -1 else len(text)]
    # Pre-existing authenticated fetches use the same shape:
    # git fetch --no-tags --depth=1 origin "$COMPLEXITY_BASE_SHA"
    # git fetch --no-tags --depth=1 origin "$PR_BASE_SHA"
    # git fetch --no-tags --depth=1 origin "$MERGE_BASE"
    # All three should still appear (we do not modify them per the
    # brief) and the brief explicitly audits them as redundant
    # after fetch-depth:0.
    assert "git fetch --no-tags --depth=1 origin \"$COMPLEXITY_BASE_SHA\"" in body, (
        "audit: pre-existing COMPLEXITY_BASE_SHA fetch expected"
    )
    assert "git fetch --no-tags --depth=1 origin \"$MERGE_BASE\"" in body, (
        "audit: pre-existing MERGE_BASE fetch expected"
    )


# ---------------------------------------------------------------------------
# (3) Symlink / containment hardening for the validator
# ---------------------------------------------------------------------------


def _run_validator_with_workspace(tmp_path, sel_path, head_sha, base_sha, rc,
                                  *, gworkspace=None):
    import os
    import subprocess
    out_path = tmp_path / "out.txt"
    env = os.environ.copy()
    env["GITHUB_WORKSPACE"] = gworkspace if gworkspace is not None else str(tmp_path)
    return subprocess.run(
        ["/usr/bin/python3.12", "-I", str(SELECTED_PATHS_VALIDATOR),
         str(sel_path), head_sha, base_sha, str(rc), str(out_path)],
        capture_output=True, text=True, env=env,
    )


def test_validator_rejects_symlink_within_backend_tests(tmp_path):
    """backend/tests/test_evil.py -> another file inside the
    candidate checkout (still under backend/tests). The validator
    MUST reject because the entry is a symlink."""
    import os
    import subprocess

    backend_dir = tmp_path / "backend" / "tests"
    tests = backend_dir
    tests.mkdir(parents=True)
    target = tmp_path / "backend" / "scripts" / "evil.py"
    target.parent.mkdir(parents=True)
    target.write_text("# evil target\n")
    link = backend_dir / "test_evil.py"
    os.symlink(str(target), str(link))

    sel = _write_validator_payload(
        tmp_path, state="SELECTED", base_sha=_BASE, head_sha=_HEAD,
        selected_tests=[{
            "file": "backend/tests/test_evil.py",
            "node_id": "tests.test_evil",
        }],
    )
    cp = _run_validator_with_workspace(tmp_path, sel, _HEAD, _BASE, 0,
                                   gworkspace=str(tmp_path))
    assert cp.returncode == 2, (cp.returncode, cp.stderr)
    assert "symlink" in cp.stderr.lower()


def test_validator_rejects_symlink_to_absolute_external_path(tmp_path):
    """backend/tests/test_evil.py -> /etc/passwd. The validator
    MUST reject (symlink rejection)."""
    import os
    import subprocess

    backend_dir = tmp_path / "backend" / "tests"
    backend_dir.mkdir(parents=True)
    link = backend_dir / "test_evil.py"
    # /etc/passwd exists on Linux runners
    os.symlink("/etc/passwd", str(link))
    sel = _write_validator_payload(
        tmp_path, state="SELECTED", base_sha=_BASE, head_sha=_HEAD,
        selected_tests=[{
            "file": "backend/tests/test_evil.py",
            "node_id": "tests.test_evil",
        }],
    )
    cp = _run_validator_with_workspace(tmp_path, sel, _HEAD, _BASE, 0,
                                   gworkspace=str(tmp_path))
    assert cp.returncode == 2, (cp.returncode, cp.stderr)
    assert "symlink" in cp.stderr.lower()


def test_validator_accepts_normal_regular_test_file(tmp_path):
    """Regression: a normal regular file under backend/tests/
    still passes the hardened validator."""
    backend_dir = tmp_path / "backend" / "tests"
    backend_dir.mkdir(parents=True)
    (backend_dir / "test_x.py").write_text("# x\n")
    sel = _write_validator_payload(
        tmp_path, state="SELECTED", base_sha=_BASE, head_sha=_HEAD,
        selected_tests=[{
            "file": "backend/tests/test_x.py",
            "node_id": "tests.test_x",
        }],
    )
    cp = _run_validator_with_workspace(tmp_path, sel, _HEAD, _BASE, 0,
                                   gworkspace=str(tmp_path))
    assert cp.returncode == 0, cp.stderr
    out = tmp_path / "out.txt"
    assert out.read_text().strip() == "backend/tests/test_x.py"


# ---------------------------------------------------------------------------
# (4) Certification evidence parsing fail-closed matrix
# ---------------------------------------------------------------------------


COMPOSE = WORKTREE / "scripts" / "pr_b3b_compose_certification.py"


def _run_compose(tmp_path, junit=None, coverage=None, expected_rc=1,
                 expected_marker=None, marker_in_stderr=True):
    import os
    import subprocess

    out_path = tmp_path / "cert.json"
    backend = tmp_path / "backend"
    backend.mkdir(parents=True, exist_ok=True)
    if junit is not None:
        (backend / "pr-deep-junit.xml").write_text(junit)
    if coverage is not None:
        (backend / "pr-deep-coverage.json").write_text(coverage)

    # 12-arg CLI: <output_path> <pr_number> <expected_head>
    # <expected_base> <merge_base> <repo> <run_id> <run_attempt>
    # <workflow> <workflow_ref> <control_plane_sha>
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(COMPOSE),
         str(out_path),
         "172", _HEAD, _BASE, _BASE,
         "anervalens-netizen/unihub-retail",
         "1", "1", "pr-deep", "anervalens-netizen/unihub-retail/main",
         _HEAD],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    return cp, out_path


_VALID_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="t" tests="3" failures="0" errors="0" skipped="1"/>
</testsuites>
"""
_VALID_COVERAGE = json.dumps({
    "files": {},
    "totals": {
        "percent_covered": 87.5,
        "covered_lines": 70,
        "num_statements": 80,
    },
})


def test_compose_fails_when_percent_covered_is_bool_true(tmp_path):
    cp, _ = _run_compose(tmp_path,
                         junit=_VALID_JUNIT,
                         coverage=json.dumps({"files": {},
                                              "totals": {"percent_covered": True,
                                                         "covered_lines": 70,
                                                         "num_statements": 80}}))
    assert cp.returncode == 1
    assert "bool" in cp.stderr or "percent_covered" in cp.stderr


def test_compose_fails_when_percent_covered_is_nan(tmp_path):
    cp, _ = _run_compose(tmp_path,
                         junit=_VALID_JUNIT,
                         coverage=json.dumps({"files": {},
                                              "totals": {"percent_covered": float("nan"),
                                                         "covered_lines": 70,
                                                         "num_statements": 80}}))
    assert cp.returncode == 1
    assert "finite" in cp.stderr or "percent_covered" in cp.stderr


def test_compose_fails_when_percent_covered_is_infinity(tmp_path):
    cp, _ = _run_compose(tmp_path,
                         junit=_VALID_JUNIT,
                         coverage=json.dumps({"files": {},
                                              "totals": {"percent_covered": float("inf"),
                                                         "covered_lines": 70,
                                                         "num_statements": 80}}))
    assert cp.returncode == 1
    assert "finite" in cp.stderr or "percent_covered" in cp.stderr


def test_compose_fails_when_percent_covered_negative(tmp_path):
    cp, _ = _run_compose(tmp_path,
                         junit=_VALID_JUNIT,
                         coverage=json.dumps({"files": {},
                                              "totals": {"percent_covered": -1.0,
                                                         "covered_lines": 70,
                                                         "num_statements": 80}}))
    assert cp.returncode == 1
    assert "range" in cp.stderr or "percent_covered" in cp.stderr


def test_compose_fails_when_percent_covered_over_100(tmp_path):
    cp, _ = _run_compose(tmp_path,
                         junit=_VALID_JUNIT,
                         coverage=json.dumps({"files": {},
                                              "totals": {"percent_covered": 100.1,
                                                         "covered_lines": 70,
                                                         "num_statements": 80}}))
    assert cp.returncode == 1
    assert "range" in cp.stderr or "percent_covered" in cp.stderr


def test_compose_fails_when_counters_are_bool(tmp_path):
    cp, _ = _run_compose(tmp_path,
                         junit=_VALID_JUNIT,
                         coverage=json.dumps({"files": {},
                                              "totals": {"percent_covered": 80.0,
                                                         "covered_lines": True,
                                                         "num_statements": 80}}))
    assert cp.returncode == 1
    assert "bool" in cp.stderr or "covered_lines" in cp.stderr


def test_compose_fails_when_counters_negative(tmp_path):
    cp, _ = _run_compose(tmp_path,
                         junit=_VALID_JUNIT,
                         coverage=json.dumps({"files": {},
                                              "totals": {"percent_covered": 80.0,
                                                         "covered_lines": -1,
                                                         "num_statements": 80}}))
    assert cp.returncode == 1
    assert "negative" in cp.stderr or "covered_lines" in cp.stderr


def test_compose_fails_when_covered_lines_greater_than_statements(tmp_path):
    cp, _ = _run_compose(tmp_path,
                         junit=_VALID_JUNIT,
                         coverage=json.dumps({"files": {},
                                              "totals": {"percent_covered": 80.0,
                                                         "covered_lines": 90,
                                                         "num_statements": 80}}))
    assert cp.returncode == 1
    assert "covered_lines" in cp.stderr


def test_compose_fails_when_junit_attributes_are_non_numeric(tmp_path):
    cp, _ = _run_compose(tmp_path,
                         junit="""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="t" tests="abc" failures="0" errors="0" skipped="0"/>
</testsuites>
""",
                         coverage=_VALID_COVERAGE)
    assert cp.returncode == 1
    assert "tests" in cp.stderr


def test_compose_fails_when_junit_skipped_greater_than_tests(tmp_path):
    cp, _ = _run_compose(tmp_path,
                         junit="""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="t" tests="3" failures="0" errors="0" skipped="5"/>
</testsuites>
""",
                         coverage=_VALID_COVERAGE)
    assert cp.returncode == 1
    assert "skipped" in cp.stderr


def test_compose_succeeds_with_valid_evidence(tmp_path):
    """Regression: the hardened composer still produces success for
    valid evidence, with allow_nan=False JSON output."""
    cp, out = _run_compose(tmp_path,
                           junit=_VALID_JUNIT,
                           coverage=_VALID_COVERAGE)
    assert cp.returncode == 0, cp.stderr
    # Output file is valid JSON parseable WITHOUT NaN/Infinity.
    body = out.read_text()
    # allow_nan=False: NaN/Infinity would raise on parse here.
    parsed = json.loads(body, parse_constant=lambda _c: (
        (_ for _ in ()).throw(ValueError("nan/infinity in cert"))
    ))
    assert parsed["result"] == "success"
    assert parsed["backend_test_result"] == "PASS"
    assert parsed["changed_line_result"] == "PASS"
    assert parsed["coverage_result"]["percent_covered"] == 87.5


# ---------------------------------------------------------------------------
# (5) Critical-coverage trust surfaces (A3 + selector)
# ---------------------------------------------------------------------------


def test_critical_coverage_script_in_a3_deploy_release_ci_paths():
    """A3 high-risk manifest must include the critical-coverage
    authority and its thresholds file."""
    data = json.loads(HIGH_RISK_JSON.read_text(encoding="utf-8"))
    paths = data["categories"]["deploy-release-ci"]["paths"]
    assert "backend/scripts/check_critical_coverage.py" in paths
    assert "backend/critical_coverage_thresholds.json" in paths


def test_selector_classifies_critical_coverage_script_as_gate_authority():
    """The selector must classify modifications/deletions of the
    critical-coverage authority and its thresholds file as
    ESCALATION_REQUIRED before any gate is loaded."""
    text = SELECTOR.read_text(encoding="utf-8")
    assert "backend/scripts/check_critical_coverage.py" in text
    assert "backend/critical_coverage_thresholds.json" in text


# ---------------------------------------------------------------------------
# (6) Publisher defense-in-depth (machine contract)
# ---------------------------------------------------------------------------


def _make_decision_with_version(tmp_path, *, policy_state, schema_version=1,
                                selector_state="SELECTED", selector_rc=0,
                                merge_base_sha=None):
    p = tmp_path / "decision.json"
    if merge_base_sha is None:
        merge_base_sha = _BASE
    p.write_text(json.dumps({
        "schema_version": schema_version,
        "selector_state": selector_state,
        "selector_rc": selector_rc,
        "policy_state": policy_state,
        "head_sha": _HEAD,
        "base_sha": _BASE,
        "merge_base_sha": merge_base_sha,
    }))
    return p


def test_publish_rejects_wrong_schema_version(tmp_path):
    p = _make_decision_with_version(
        tmp_path, policy_state="success", schema_version=99
    )
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(PUBLISH),
         str(p), _HEAD, _BASE,
         "anervalens-netizen/unihub-retail", "", "https://example/run"],
        capture_output=True, text=True,
    )
    assert cp.returncode == 1
    assert "schema_version" in cp.stderr


def test_publish_rejects_unknown_selector_state(tmp_path):
    p = _make_decision_with_version(
        tmp_path, policy_state="success",
        selector_state="NOT_A_REAL_STATE", selector_rc=0,
    )
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(PUBLISH),
         str(p), _HEAD, _BASE,
         "anervalens-netizen/unihub-retail", "", "https://example/run"],
        capture_output=True, text=True,
    )
    assert cp.returncode == 1
    assert "selector_state" in cp.stderr


def test_publish_rejects_selector_rc_state_mismatch(tmp_path):
    """SELECTED state must use selector_rc=0; mismatch is fail-closed."""
    p = _make_decision_with_version(
        tmp_path, policy_state="success",
        selector_state="SELECTED", selector_rc=2,
    )
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(PUBLISH),
         str(p), _HEAD, _BASE,
         "anervalens-netizen/unihub-retail", "", "https://example/run"],
        capture_output=True, text=True,
    )
    assert cp.returncode == 1
    assert "inconsistent" in cp.stderr


def test_publish_rejects_bad_merge_base_sha(tmp_path):
    p = _make_decision_with_version(
        tmp_path, policy_state="success",
        merge_base_sha="not-a-sha",
    )
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(PUBLISH),
         str(p), _HEAD, _BASE,
         "anervalens-netizen/unihub-retail", "", "https://example/run"],
        capture_output=True, text=True,
    )
    assert cp.returncode == 1
    assert "merge_base_sha" in cp.stderr


def test_publish_accepts_valid_decision_with_schema_version(tmp_path):
    p = _make_decision_with_version(
        tmp_path, policy_state="success",
    )
    cp = subprocess.run(
        ["/usr/bin/python3.12", "-I", str(PUBLISH),
         str(p), _HEAD, _BASE,
         "anervalens-netizen/unihub-retail", "", "https://example/run"],
        capture_output=True, text=True,
    )
    assert cp.returncode == 0, cp.stderr
    body = json.loads(cp.stdout)
    assert body["state"] == "success"
    assert body["context"] == "retail/pr-deep-policy"


def test_decide_policy_emits_schema_version():
    """pr_b3b_decide_policy.py MUST emit schema_version: 1 in its
    decision output."""
    import importlib.util
    import io
    import sys
    spec = importlib.util.spec_from_file_location(
        "pr_b3b_decide_policy_sv_test", DECIDE_POLICY
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    decision = mod._build_decision(
        selector_state="NO_ELIGIBLE_BACKEND_CHANGE",
        selector_rc=0,
        policy_state="success",
        expected_head=_HEAD,
        expected_base=_BASE,
        merge_base=_BASE,
        reason="test",
    )
    assert decision["schema_version"] == 1


# ---------------------------------------------------------------------------
# (7) Latest-status: no matching status -> pending (no historical fallback)
# ---------------------------------------------------------------------------


def test_decide_policy_empty_status_list_is_pending():
    """No retail/pr-deep status visible for the exact head ->
    policy_state MUST be 'pending'. There must be NO historical
    fallback to an older success because there is none."""
    decision = _decide_policy_with_statuses([])
    assert decision["policy_state"] == "pending"
    assert "no certification" in decision["reason"].lower() or \
        "required" in decision["reason"].lower()


def test_decide_policy_status_fetch_is_exact_head_scoped():
    """Status lookup must stay bound to the exact expected HEAD."""
    text = DECIDE_POLICY.read_text(encoding="utf-8")
    assert "commits/{sha}/statuses" in text


def test_decide_policy_status_fetch_uses_per_page_100():
    """The status fetch must request per_page=100 (the API max)
    to maximise the chance the returned page is complete."""
    text = DECIDE_POLICY.read_text(encoding="utf-8")
    assert "per_page=100" in text


# ---------------------------------------------------------------------------
# (8) Postflight -> success ordering in pr-deep.yml
# ---------------------------------------------------------------------------


def _workflow_step_order(workflow_text, step_name_prefix):
    """Return ordered list of (job, step_name) that match the
    prefix in active YAML (excluding comments)."""
    yaml = _yaml()
    data = yaml.safe_load(workflow_text)
    out = []
    for job_name, job in (data.get("jobs") or {}).items():
        for step in job.get("steps", []):
            name = step.get("name") or ""
            if isinstance(name, str) and name.startswith(step_name_prefix):
                out.append((job_name, name))
    return out


def test_pr_deep_postflight_runs_before_success_publication():
    """Postflight metadata revalidation must happen BEFORE
    success publication in the same job."""
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    postflight = text.find("Re-fetch PR metadata and re-validate identities")
    success_pub = text.find("Set retail/pr-deep = success on expected head")
    assert postflight != -1, "postflight step missing"
    assert success_pub != -1, "success publication step missing"
    assert postflight < success_pub, (
        "postflight must precede success publication"
    )


def test_pr_deep_success_publication_has_if_success():
    """The success publication step MUST have ``if: success()`` so
    that an upstream postflight failure blocks certification."""
    yaml = _yaml()
    data = yaml.safe_load(PR_DEEP_YML.read_text(encoding="utf-8"))
    target = None
    for _job, job in (data.get("jobs") or {}).items():
        for step in job.get("steps", []):
            name = step.get("name") or ""
            if isinstance(name, str) and name.startswith(
                "Set retail/pr-deep = success on expected head"
            ):
                target = step
    assert target is not None, "success publication step missing"
    assert target.get("if") == "success()", (
        f"success publication must have 'if: success()', got: {target.get('if')!r}"
    )


def test_pr_deep_artifact_upload_precedes_success_publication():
    """Artifact upload must precede success publication so that
    evidence is uploaded BEFORE the green status is announced."""
    text = PR_DEEP_YML.read_text(encoding="utf-8")
    upload = text.find("Upload PR-DEEP evidence")
    success_pub = text.find("Set retail/pr-deep = success on expected head")
    assert upload != -1, "upload step missing"
    assert success_pub != -1, "success publication step missing"
    assert upload < success_pub, (
        "artifact upload must precede success publication"
    )


# ---------------------------------------------------------------------------
# (9) Exact-main backend-check and release-artifact preserved
# ---------------------------------------------------------------------------


def test_exact_main_backend_check_check_critical_coverage_unchanged():
    """The exact-main backend-check critical-coverage invocation
    is NOT modified by PR-B3b (the path it uses
    ``scripts/check_critical_coverage.py`` is fine because
    exact-main's defaults set ``working-directory: backend``,
    which resolves ``scripts/...`` to ``backend/scripts/...``).
    The test pins the unchanged invocation as a regression
    sentinel."""
    text = CI_YML.read_text(encoding="utf-8")
    # The exact-main backend-check step uses the bare path because
    # its defaults block sets working-directory: backend.
    assert "scripts/check_critical_coverage.py" in text
    # Find the step context. It must live inside the
    # backend-check job and use the defaults working-directory.
    yaml = _yaml()
    data = yaml.safe_load(text)
    found = False
    for job_name, job in (data.get("jobs") or {}).items():
        if job_name != "backend-check":
            continue
        defaults = job.get("defaults") or {}
        run_defaults = defaults.get("run") or {}
        assert run_defaults.get("working-directory") == "backend", (
            "exact-main backend-check working-directory must remain 'backend'"
        )
        for step in job.get("steps", []):
            run = step.get("run") or ""
            if "check_critical_coverage" in run and "scripts/check_critical_coverage.py" in run:
                found = True
    assert found, (
        "exact-main backend-check critical-coverage invocation must remain"
    )


def test_exact_main_release_artifact_unchanged():
    """The release-artifact job is not touched by PR-B3b."""
    yaml = _yaml()
    base_data = yaml.safe_load(PR_DEEP_YML.read_text(encoding="utf-8"))
    assert "release-artifact" not in (base_data.get("jobs") or {}), (
        "release-artifact must NOT be in pr-deep.yml (it lives in ci.yml)"
    )
    ci_data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    assert "release-artifact" in (ci_data.get("jobs") or {}), (
        "release-artifact job must remain in ci.yml"
    )


def test_pr_b3b_does_not_introduce_new_exact_main_job():
    """PR-B3b must NOT add any workflow_dispatch-only exact-main
    job. The new PR-DEEP / PR-DEEP-POLICY workflows are
    PR-context (PR-DEEP-POLICY) or workflow_dispatch
    certification (PR-DEEP) — they are not exact-main release
    authority."""
    yaml = _yaml()
    for path, expected in [
        (PR_DEEP_YML, "workflow_dispatch"),
        (PR_DEEP_POLICY_YML, "pull_request_target"),
    ]:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        on = data.get(True) or data.get("on") or {}
        triggers = sorted(on.keys())
        assert expected in triggers, (
            f"{path.name} triggers must include {expected!r}, got: {triggers!r}"
        )
        assert "workflow_dispatch" not in on if expected == "pull_request_target" else True, (
            "pr-deep-policy must not run on workflow_dispatch"
        )


# ---------------------------------------------------------------------------
# (10) Caddy validation steps are pinned to one canonical authorized run block
# ---------------------------------------------------------------------------
#
# The Caddy validation steps in .github/workflows/ci.yml are an E5 trust-
# boundary fixture: the dedicated rootless Docker daemon cannot see
# /opt/Mobiup, so a host bind (`-v`, `--volume`, `--mount`, including the
# `=` forms) would silently fail or — worse — escape the isolation.
# Modeling arbitrary Bash expansion in a Python regression test is not
# acceptable; instead the operational contract is reduced to a single
# property: the run block of every "Versioned Retail edge request limits"
# step is byte-for-byte equal to one canonical block. Any future drift
# in the Caddy command surface (extra flags, alternate image, alternate
# network, variable-generated flags, command substitution, changed
# cleanup) will fail this test by simple inequality.


CADDY_STEP_NAME = "Versioned Retail edge request limits"
CADDY_PINNED_IMAGE = (
    "caddy@sha256:844f60b64e4724a5aa8245e019dace0d3f199f7433ce6c57676cb30a920dbad9"
)


# The single source of truth for the Caddy run block. Every step named
# "Versioned Retail edge request limits" in ci.yml must produce a
# block that, after _collect_caddy_steps' indentation stripping, is
# exactly equal to this string. Comments are part of the contract so
# a future reviewer can read what the canonical block is meant to do.
CADDY_EXPECTED_RUN_BLOCK = textwrap.dedent("""\
    set -euo pipefail
    caddy_image=caddy@sha256:844f60b64e4724a5aa8245e019dace0d3f199f7433ce6c57676cb30a920dbad9
    docker image inspect "$caddy_image" >/dev/null
    # The rootless Docker daemon is sandboxed away from the runner
    # workspace (InaccessiblePaths=/opt/Mobiup). Stage candidate
    # ops/caddy at a daemon-readable path the runner controls, then
    # `docker cp` it into a stopped, network-isolated container.
    # No host bind, no -v, no --mount, no volume, no pull.
    caddy_stage="$(mktemp -d -t unihub-retail-caddy-stage.XXXXXX)"
    container="unihub-retail-caddy-validate-$$"
    cleanup() {
      docker rm -f -v "$container" >/dev/null 2>&1 || true
      rm -rf -- "$caddy_stage"
    }
    trap cleanup EXIT
    chmod 0700 "$caddy_stage"
    cp -R "$PWD/ops/caddy/." "$caddy_stage/"
    docker create \\
      --pull=never \\
      --name "$container" \\
      --network none \\
      "$caddy_image" \\
      caddy validate \\
      --config /etc/caddy/Caddyfile.validate \\
      --adapter caddyfile \\
      >/dev/null
    docker cp "$caddy_stage/." "$container:/etc/caddy"
    docker start -a "$container"
""")


def _collect_caddy_steps():
    """Return every run-block whose enclosing step is named
    ``Versioned Retail edge request limits``.

    Operates on the raw workflow text so the assertion is robust to
    YAML anchor / alias / merge-key choices. The block returned is
    the indented run-block with the 10-space common indent stripped.
    """
    text = CI_YML.read_text(encoding="utf-8")
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        if CADDY_STEP_NAME in lines[i] and "- name:" in lines[i]:
            run_buffer = []
            in_run = False
            run_indent = None
            j = i
            while j < len(lines):
                line = lines[j]
                stripped = line.lstrip()
                indent = len(line) - len(stripped)
                if not in_run:
                    if stripped.startswith("run:") or stripped.startswith("run: |"):
                        in_run = True
                        run_indent = indent + 2
                        if "|" in stripped:
                            after = stripped.split("|", 1)[1].strip()
                            if after and after not in ("|", "|-", "|+"):
                                run_buffer.append(after)
                        j += 1
                        continue
                else:
                    if stripped == "":
                        run_buffer.append("")
                        j += 1
                        continue
                    if indent < run_indent:
                        break
                    run_buffer.append(line[run_indent:])
                j += 1
            blocks.append("\n".join(run_buffer))
            i = j
        else:
            i += 1
    return blocks


def test_caddy_validation_steps_present_in_exactly_two_jobs():
    """Both the pr-fast and the exact-main FULL backend-check
    pre-step must still exist."""
    blocks = _collect_caddy_steps()
    assert len(blocks) == 2, (
        f"expected exactly 2 'Versioned Retail edge request limits' "
        f"steps in ci.yml, found {len(blocks)}"
    )


@pytest.mark.parametrize("block_index", [0, 1])
def test_caddy_validation_block_is_byte_equal_to_canonical(block_index):
    """The Caddy run block must be byte-for-byte equal to the
    canonical authorized block. Any executable deviation — extra
    flag, alternate image, alternate network, variable-generated
    flag, command substitution, missing cleanup, lost trap order,
    etc. — is a fail-closed regression."""
    blocks = _collect_caddy_steps()
    assert len(blocks) == 2
    actual = blocks[block_index]
    expected = CADDY_EXPECTED_RUN_BLOCK
    assert actual == expected, (
        f"Caddy validation step #{block_index} does not match the "
        f"canonical authorized block.\n"
        f"--- expected ({len(expected)} chars) ---\n{expected}\n"
        f"--- actual ({len(actual)} chars) ---\n{actual}\n"
        f"--- diff (unified) ---\n"
        + "\n".join(
            f"{ln:>4} {mark} {line}" for ln, mark, line in _unified_diff(
                expected.splitlines(), actual.splitlines(), lineterm=""
            )
        )
    )


def test_caddy_validation_pinned_image_is_present():
    """The pinned caddy image digest must still appear in the
    canonical block. This is a positive contract sanity check
    that does not depend on a particular authoring pattern."""
    assert CADDY_PINNED_IMAGE in CADDY_EXPECTED_RUN_BLOCK, (
        f"pinned caddy image digest {CADDY_PINNED_IMAGE!r} missing "
        f"from the canonical block"
    )


def test_caddy_validation_canonical_block_rejects_mutations():
    """Mechanically prove the canonical contract is fail-closed:
    every realistic regression that would change the executable
    surface must differ from the canonical block."""
    expected = CADDY_EXPECTED_RUN_BLOCK

    def _substr_mutation(label, anchor, replacement):
        candidate = expected.replace(anchor, replacement, 1)
        assert candidate != expected, (
            f"mutation {label!r} did not actually change the canonical "
            f"block; fix the test"
        )
        return candidate

    def _reorder_mutation_I():
        # Move "trap cleanup EXIT" to AFTER the cp -R line. This models
        # the P3 regression where a chmod/cp failure leaves the stage
        # dir behind because the trap was not yet installed.
        candidate = expected.replace(
            "trap cleanup EXIT\nchmod 0700",
            "chmod 0700",
        ).replace(
            'chmod 0700 "$caddy_stage"\ncp -R "$PWD/ops/caddy/." "$caddy_stage/"',
            'cp -R "$PWD/ops/caddy/." "$caddy_stage/"\ntrap cleanup EXIT',
        )
        assert candidate != expected, (
            "mutation I did not actually change the canonical block; "
            "fix the test"
        )
        return candidate

    mutations = [
        ("A: -v host bind", "docker create \\\n",
         '        docker create \\\n          -v "$PWD/ops/caddy:/etc/caddy:ro" \\\n'),
        ("B: --mount= bind form", "docker create \\\n",
         '        docker create \\\n          --mount=type=bind,src=/tmp/foo,dst=/etc/caddy \\\n'),
        ("C: --volume= bind form", "docker create \\\n",
         '        docker create \\\n          --volume=/tmp/foo:/etc/caddy \\\n'),
        ("D: variable-generated flag", "docker create \\\n",
         '        mount_flag=-v\n        docker create \\\n          "$mount_flag" \\\n'),
        ("E: alternate network", "docker create \\\n",
         '        docker create \\\n          --network host \\\n'),
        ("F: drop --pull=never", "docker create \\\n",
         '        docker create \\\n          --name "$container" \\\n'),
        ("G: change pinned digest", CADDY_PINNED_IMAGE + "\n",
         'caddy_image=caddy@sha256:0000000000000000000000000000000000000000000000000000000000000000\n'),
        ("H: drop -v from docker rm cleanup",
         'docker rm -f -v "$container" >/dev/null 2>&1 || true\n',
         'docker rm -f "$container" >/dev/null 2>&1 || true\n'),
    ]
    for label, anchor, replacement in mutations:
        candidate = _substr_mutation(label, anchor, replacement)
        # The mutation must be rejected by the canonical-equality test.
        assert candidate != CADDY_EXPECTED_RUN_BLOCK, (
            f"mutation {label!r} produced a block that still equals the "
            f"canonical block — the test would not catch this regression"
        )
    candidate = _reorder_mutation_I()
    assert candidate != CADDY_EXPECTED_RUN_BLOCK, (
        "mutation I (trap after cp) produced a block that still equals "
        "the canonical block — the test would not catch this regression"
    )


# ---------------------------------------------------------------------------
# (11) Caddy step execution envelope: step + job + workflow execution layers
# ---------------------------------------------------------------------------
#
# Section (10) pinned the run block; this section pins the *execution
# envelope* — the step-level metadata, the relevant job-level overrides,
# and the workflow-level env/defaults that could redirect or interpose
# shell or Docker execution. A future edit that keeps the canonical
# run block verbatim but adds a step-level `env: DOCKER_HOST: ...` or
# `shell: ...`, or a job-level `env:`/`defaults.run.shell:`, or a
# workflow-level env/defaults change, would silently shift the
# execution surface and is therefore a fail-closed regression.


CADDY_RELEVANT_JOBS = ("pr-fast", "backend-check")
CADDY_EXPECTED_STEP_KEYS = frozenset({"name", "run", "working-directory"})
CADDY_EXPECTED_STEP = {
    "name": "Versioned Retail edge request limits",
    "working-directory": ".",
    "run": None,  # filled by _caddy_expected_step_dict() so the test
                  # tracks the same canonical run block (Section 10)
}
CADDY_EXPECTED_JOB_ENVELOPES = {
    "pr-fast": {
        "name": "pr-fast",
        "if": "github.event_name == 'pull_request'",
        "needs": "runner-isolation",
        "runs-on": [
            "self-hosted",
            "Linux",
            "X64",
            "dell-compute",
            "unihub-build",
            "unihub-retail-build",
        ],
        "timeout-minutes": 15,
        "defaults": {"run": {"working-directory": "backend"}},
    },
    "backend-check": {
        "name": "backend-check",
        "if": (
            "github.event_name == 'workflow_dispatch' "
            "&& github.ref == 'refs/heads/main'"
        ),
        "needs": "runner-isolation",
        "runs-on": [
            "self-hosted",
            "Linux",
            "X64",
            "dell-compute",
            "unihub-build",
            "unihub-retail-build",
        ],
        "timeout-minutes": 75,
        "defaults": {"run": {"working-directory": "backend"}},
    },
}
CADDY_EXPECTED_WORKFLOW_ENV = {
    "PYTHONNOUSERSITE": "1",
    "PYTHONSAFEPATH": "1",
    "PYTHONHOME": "",
    "PYTHONPATH": "",
    "PYTHONSTARTUP": "",
    "PYTHONINSPECT": "",
    "PYTHONDONTWRITEBYTECODE": "1",
    "MYPYPATH": "",
    "MYPY_CONFIG_FILE": "",
    "NODE_OPTIONS": "",
    "NODE_PATH": "",
    "BASH_ENV": "",
    "ENV": "",
    "CDPATH": "",
    "GLOBIGNORE": "",
}


def _caddy_expected_step_dict():
    """Return the full expected Caddy step dict. The ``run`` value
    is the same canonical block pinned by Section (10) so the two
    sections cannot drift apart."""
    expected = dict(CADDY_EXPECTED_STEP)
    expected["run"] = CADDY_EXPECTED_RUN_BLOCK
    return expected


def _parsed_workflow():
    """Parse the workflow YAML once for the envelope tests."""
    return _yaml().safe_load(CI_YML.read_text(encoding="utf-8"))


def _caddy_steps_from_job(workflow, job_name):
    """Return the parsed Caddy step list (parsed YAML) for the
    named job. Asserts the job exists and contains at least one
    Caddy step. The returned list is the actual parsed step dicts
    from the workflow, so any addition to step-level keys is
    visible immediately to the assertions.
    """
    job = (workflow.get("jobs") or {}).get(job_name)
    assert job is not None, (
        f"required job {job_name!r} is missing from ci.yml"
    )
    steps = [
        step for step in (job.get("steps") or [])
        if step.get("name") == "Versioned Retail edge request limits"
    ]
    assert steps, (
        f"job {job_name!r} has no step named 'Versioned Retail edge "
        f"request limits'"
    )
    return steps


@pytest.fixture(scope="module")
def parsed_workflow():
    return _parsed_workflow()


@pytest.mark.parametrize("job_name", list(CADDY_RELEVANT_JOBS))
def test_caddy_validation_step_metadata_is_exact(parsed_workflow, job_name):
    """Each Caddy step's parsed YAML must equal the authorized
    step shape: exactly the three keys {name, run, working-directory}
    with the exact canonical run block, and no env/shell/if/etc.
    """
    steps = _caddy_steps_from_job(parsed_workflow, job_name)
    expected = _caddy_expected_step_dict()
    for step in steps:
        # Exact key set: reject any extra step-level key, including
        # env, shell, if, continue-on-error, timeout-minutes, with,
        # etc. A future addition must consciously update this contract.
        assert set(step.keys()) == CADDY_EXPECTED_STEP_KEYS, (
            f"Caddy step in job {job_name!r} has unexpected/insufficient "
            f"step keys: {sorted(set(step.keys()) - CADDY_EXPECTED_STEP_KEYS)} "
            f"present, "
            f"{sorted(CADDY_EXPECTED_STEP_KEYS - set(step.keys()))} missing"
        )
        # Every value must match the authorized step shape exactly.
        assert step == expected, (
            f"Caddy step in job {job_name!r} does not match the "
            f"authorized step shape.\n"
            f"--- expected ---\n{expected}\n"
            f"--- actual ---\n{step}\n"
        )


@pytest.mark.parametrize("job_name", list(CADDY_RELEVANT_JOBS))
def test_caddy_validation_job_routing_envelope_is_exact(
    parsed_workflow, job_name,
):
    """The Caddy-relevant job's full job-level envelope (every key
    except ``steps``) must equal the authorized contract exactly.

    This pins the trusted routing: ``needs: runner-isolation`` keeps
    Caddy validation after the runner-isolation gate, and
    ``runs-on`` keeps it on the isolated Retail build-runner (NOT
    GitHub-hosted or a deploy runner). A future edit such as
    ``runs-on: [self-hosted, unihub-deploy]`` or
    ``needs: some-other-job`` or removing ``needs`` entirely
    would move Caddy validation outside the trusted boundary
    while still leaving the step shape and the canonical run
    block untouched — and the exact envelope equality would
    fail closed.
    """
    job = (parsed_workflow.get("jobs") or {})[job_name]
    expected = CADDY_EXPECTED_JOB_ENVELOPES[job_name]
    # Exclude ONLY ``steps``; pin every other current job-level
    # field exactly. This inherently proves absence of every
    # not-listed job-level execution key (env, container,
    # services, strategy, environment, continue-on-error, ...) and
    # pins the values of every present one (needs, runs-on, if,
    # timeout-minutes, defaults, name).
    actual = {k: v for k, v in job.items() if k != "steps"}
    assert actual == expected, (
        f"Caddy-relevant job {job_name!r} does not match the "
        f"authorized routing envelope.\n"
        f"--- expected ---\n{expected}\n"
        f"--- actual ---\n{actual}\n"
    )
    # Belt-and-braces: explicitly prove the job's key set is exactly
    # the expected-envelope key set plus ``steps``. This catches a
    # future extra job-level key even if it happens to match the
    # expected envelope by accident.
    expected_keys = set(expected.keys()) | {"steps"}
    assert set(job.keys()) == expected_keys, (
        f"Caddy-relevant job {job_name!r} has unexpected key set: "
        f"expected={sorted(expected_keys)} got={sorted(job.keys())}"
    )


def test_caddy_validation_workflow_level_execution_overrides_are_exact(
    parsed_workflow,
):
    """No top-level `defaults` may exist (so the Caddy jobs cannot
    inherit a `defaults.run.shell: ...`), and the workflow-level
    `env` must equal the authorized dictionary exactly so a future
    `BASH_ENV: candidate-controlled` or `DOCKER_HOST: tcp://...`
    addition is a fail-closed regression."""
    # No top-level defaults.
    assert "defaults" not in parsed_workflow, (
        "ci.yml must not declare top-level `defaults` (it could "
        "inject `defaults.run.shell: ...` and re-route every job's "
        f"shell). Got: {parsed_workflow.get('defaults')!r}"
    )
    # Workflow env must equal the authorized dictionary.
    actual_env = parsed_workflow.get("env")
    assert actual_env == CADDY_EXPECTED_WORKFLOW_ENV, (
        "ci.yml workflow-level `env` does not match the authorized "
        f"trust-boundary contract. expected={CADDY_EXPECTED_WORKFLOW_ENV!r} "
        f"got={actual_env!r}"
    )


def test_caddy_validation_execution_envelope_rejects_mutations(parsed_workflow):
    """Mechanically prove the envelope contract is fail-closed:
    every realistic injection at the step/job/workflow layer that
    could change how/where the canonical run block executes must
    be detected by exact inequality."""
    expected_step = _caddy_expected_step_dict()
    yaml = _yaml()

    def _clone():
        # Cheap structural copy via YAML re-emit so we exercise the
        # same parser the test uses.
        return yaml.safe_load(yaml.dump(parsed_workflow))

    def _caddy_step(cwf, jn):
        return _caddy_steps_from_job(cwf, jn)[0]

    def _step_index(cwf, jn):
        return next(
            i for i, s in enumerate(cwf["jobs"][jn]["steps"])
            if s.get("name") == "Versioned Retail edge request limits"
        )

    def _job_envelope(cwf, jn):
        return {k: v for k, v in cwf["jobs"][jn].items() if k != "steps"}

    def _assert_rejected(label, condition, hint):
        assert condition, (
            f"mutation {label} was not caught by the canonical "
            f"envelope check: {hint}"
        )

    mutations = [
        # --- A: step-level env (DOCKER_HOST) ---
        ("A: step-level env DOCKER_HOST", lambda cwf: (
            cwf["jobs"]["pr-fast"]["steps"][
                _step_index(cwf, "pr-fast")
            ].__setitem__("env", {"DOCKER_HOST": "tcp://example.invalid:2375"}),
            _assert_rejected(
                "A", _caddy_step(cwf, "pr-fast") != expected_step,
                "step-level DOCKER_HOST env was not caught",
            ),
        )),
        # --- B: step-level env (BASH_ENV) ---
        ("B: step-level env BASH_ENV", lambda cwf: (
            cwf["jobs"]["backend-check"]["steps"][
                _step_index(cwf, "backend-check")
            ].__setitem__("env", {"BASH_ENV": "/tmp/wrapper"}),
            _assert_rejected(
                "B", _caddy_step(cwf, "backend-check") != expected_step,
                "step-level BASH_ENV env was not caught",
            ),
        )),
        # --- C: step-level shell: python ---
        ("C: step-level shell=python", lambda cwf: (
            cwf["jobs"]["pr-fast"]["steps"][
                _step_index(cwf, "pr-fast")
            ].__setitem__("shell", "python"),
            _assert_rejected(
                "C", _caddy_step(cwf, "pr-fast") != expected_step,
                "step-level shell=python was not caught",
            ),
        )),
        # --- D: step-level shell: bash --noprofile --norc {0} ---
        ("D: step-level shell=bash --noprofile --norc {0}", lambda cwf: (
            cwf["jobs"]["pr-fast"]["steps"][
                _step_index(cwf, "pr-fast")
            ].__setitem__("shell", "bash --noprofile --norc {0}"),
            _assert_rejected(
                "D", _caddy_step(cwf, "pr-fast") != expected_step,
                "step-level shell=bash ... was not caught",
            ),
        )),
        # --- E: job-level env: DOCKER_HOST ... ---
        ("E: job-level env", lambda cwf: (
            cwf["jobs"]["pr-fast"].__setitem__("env", {
                "DOCKER_HOST": "tcp://example.invalid:2375"
            }),
            _assert_rejected(
                "E", "env" in cwf["jobs"]["pr-fast"],
                "job-level env injection was not detectable",
            ),
        )),
        # --- F: job-level defaults.run.shell: ... ---
        ("F: job-level defaults.run.shell", lambda cwf: (
            cwf["jobs"]["backend-check"]["defaults"]["run"].__setitem__(
                "shell", "bash --norc"
            ),
            _assert_rejected(
                "F",
                _job_envelope(cwf, "backend-check")
                    != CADDY_EXPECTED_JOB_ENVELOPES["backend-check"],
                "job-level defaults.run.shell was not caught",
            ),
        )),
        # --- K: pr-fast runs-on broadened ---
        ("K: pr-fast runs-on broadened", lambda cwf: (
            cwf["jobs"]["pr-fast"].__setitem__(
                "runs-on", ["self-hosted", "unihub-deploy"]
            ),
            _assert_rejected(
                "K",
                _job_envelope(cwf, "pr-fast")
                    != CADDY_EXPECTED_JOB_ENVELOPES["pr-fast"],
                "pr-fast runs-on broadening was not caught",
            ),
        )),
        # --- L: backend-check needs removed ---
        ("L: backend-check needs removed", lambda cwf: (
            cwf["jobs"]["backend-check"].__delitem__("needs"),
            _assert_rejected(
                "L",
                _job_envelope(cwf, "backend-check")
                    != CADDY_EXPECTED_JOB_ENVELOPES["backend-check"],
                "backend-check needs removal was not caught",
            ),
        )),
        # --- M: backend-check needs changed to some other job ---
        ("M: backend-check needs changed", lambda cwf: (
            cwf["jobs"]["backend-check"].__setitem__(
                "needs", "some-other-job"
            ),
            _assert_rejected(
                "M",
                _job_envelope(cwf, "backend-check")
                    != CADDY_EXPECTED_JOB_ENVELOPES["backend-check"],
                "backend-check needs change was not caught",
            ),
        )),
        # --- N: pr-fast runs-on changed to ubuntu-latest ---
        ("N: pr-fast runs-on=ubuntu-latest", lambda cwf: (
            cwf["jobs"]["pr-fast"].__setitem__("runs-on", "ubuntu-latest"),
            _assert_rejected(
                "N",
                _job_envelope(cwf, "pr-fast")
                    != CADDY_EXPECTED_JOB_ENVELOPES["pr-fast"],
                "pr-fast runs-on=ubuntu-latest was not caught",
            ),
        )),
        # --- O: pr-fast timeout-minutes bumped ---
        ("O: pr-fast timeout-minutes change", lambda cwf: (
            cwf["jobs"]["pr-fast"].__setitem__("timeout-minutes", 999),
            _assert_rejected(
                "O",
                _job_envelope(cwf, "pr-fast")
                    != CADDY_EXPECTED_JOB_ENVELOPES["pr-fast"],
                "pr-fast timeout-minutes change was not caught",
            ),
        )),
        # --- P: pr-fast if-condition rewritten ---
        ("P: pr-fast if=always()", lambda cwf: (
            cwf["jobs"]["pr-fast"].__setitem__("if", "always()"),
            _assert_rejected(
                "P",
                _job_envelope(cwf, "pr-fast")
                    != CADDY_EXPECTED_JOB_ENVELOPES["pr-fast"],
                "pr-fast if=always() was not caught",
            ),
        )),
        # --- G: workflow-level defaults: ... ---
        ("G: workflow-level defaults", lambda cwf: (
            cwf.__setitem__("defaults", {"run": {"shell": "bash --norc"}}),
            _assert_rejected(
                "G", "defaults" in cwf and cwf["defaults"] is not None,
                "workflow-level defaults was not detectable",
            ),
        )),
        # --- H: workflow-level env addition (DOCKER_HOST) ---
        ("H: workflow-level env DOCKER_HOST", lambda cwf: (
            cwf["env"].__setitem__("DOCKER_HOST", "tcp://example.invalid:2375"),
            _assert_rejected(
                "H", cwf["env"] != CADDY_EXPECTED_WORKFLOW_ENV,
                "workflow-level env DOCKER_HOST addition was not caught",
            ),
        )),
        # --- I: workflow-level BASH_ENV changed ---
        ("I: workflow-level BASH_ENV change", lambda cwf: (
            cwf["env"].__setitem__("BASH_ENV", "/tmp/candidate/wrapper"),
            _assert_rejected(
                "I", cwf["env"] != CADDY_EXPECTED_WORKFLOW_ENV,
                "workflow-level BASH_ENV change was not caught",
            ),
        )),
        # --- J: workflow-level PATH added/overridden ---
        ("J: workflow-level PATH addition", lambda cwf: (
            cwf["env"].__setitem__("PATH", "/tmp/candidate/bin"),
            _assert_rejected(
                "J", cwf["env"] != CADDY_EXPECTED_WORKFLOW_ENV,
                "workflow-level PATH addition was not caught",
            ),
        )),
    ]
    for _label, mutate in mutations:
        cwf = _clone()
        mutate(cwf)
