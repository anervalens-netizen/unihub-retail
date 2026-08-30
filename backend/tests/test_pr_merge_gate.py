from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "pr_merge_gate.py"
WORKFLOW = ROOT / ".github" / "workflows" / "pr-merge-gate.yml"
MANIFEST = ROOT / ".github" / "governance" / "high-risk-paths.json"


def _load_helper():
    spec = importlib.util.spec_from_file_location("pr_merge_gate", HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    return module


def _check(name: str, head: str, *, conclusion: str = "success", status: str = "completed", ident: int = 1):
    return {
        "id": ident,
        "name": name,
        "head_sha": head,
        "status": status,
        "conclusion": conclusion,
        "completed_at": "2026-08-30T06:00:00Z" if status == "completed" else None,
        "started_at": "2026-08-30T05:59:00Z",
        "app": {"slug": "github-actions"},
    }


def _status(context: str, state: str, description: str, *, ident: int = 1):
    return {
        "id": ident,
        "context": context,
        "state": state,
        "description": description,
        "created_at": "2026-08-30T06:00:00Z",
        "updated_at": "2026-08-30T06:00:00Z",
    }


def _runtime_checks(m, head: str):
    return [
        _check(m.DOCS_CHECK, head, ident=1),
        _check(m.PR_FAST_CHECK, head, ident=2),
        _check(m.HIGH_RISK_CHECK, head, ident=3),
    ]


def test_workflow_is_trusted_control_plane_and_never_checks_out_candidate():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    on = data.get(True) or data.get("on") or {}
    assert set(on) == {"pull_request_target", "workflow_run", "status", "push"}
    assert on["pull_request_target"]["branches"] == ["main"]
    assert set(on["workflow_run"]["workflows"]) == {"CI", "docs-contract", "high-risk-governance"}
    assert on["push"]["branches"] == ["main"]
    assert data["permissions"] == {
        "contents": "read",
        "pull-requests": "read",
        "actions": "read",
        "checks": "read",
        "statuses": "write",
    }
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "github.event.pull_request.head.sha" not in text
    assert "github.event.pull_request.base.sha" in text
    assert "persist-credentials: false" in text
    assert "python3 scripts/pr_merge_gate.py" in text
    helper_text = HELPER.read_text(encoding="utf-8")
    assert 'GATE_CONTEXT = "retail/pr-merge-gate"' in helper_text


def test_trusted_actions_paths_events_and_marker_jobs_are_declared():
    m = _load_helper()
    assert m.DOCS_WORKFLOW_PATH.endswith("docs-contract.yml")
    assert m.PR_FAST_WORKFLOW_PATH.endswith("ci.yml")
    assert m.HIGH_RISK_WORKFLOW_PATH.endswith("high-risk-governance.yml")
    assert m.POLICY_WORKFLOW_PATH.endswith("pr-deep-policy.yml")
    assert m.DEEP_WORKFLOW_PATH.endswith("pr-deep.yml")
    policy = yaml.safe_load((ROOT / ".github/workflows/pr-deep-policy.yml").read_text())
    deep = yaml.safe_load((ROOT / ".github/workflows/pr-deep.yml").read_text())
    assert policy["jobs"]["marker"]["needs"] == "policy"
    assert "needs.policy.outputs.policy_state" in policy["jobs"]["marker"]["name"]
    assert "head=${{ github.event.pull_request.head.sha }}" in policy["jobs"]["marker"]["name"]
    assert "base=${{ github.event.pull_request.base.sha }}" in policy["jobs"]["marker"]["name"]
    assert deep["jobs"]["certification-marker"]["needs"] == "backend-deep"
    assert "${{ inputs.expected_head_sha }}" in deep["jobs"]["certification-marker"]["name"]
    assert "${{ inputs.expected_base_sha }}" in deep["jobs"]["certification-marker"]["name"]


def test_helper_is_governed_as_deploy_release_control_plane():
    import json

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    paths = manifest["categories"]["deploy-release-ci"]["paths"]
    assert "scripts/pr_merge_gate.py" in paths


def test_docs_only_succeeds_with_docs_authority_only():
    m = _load_helper()
    head, base = "a" * 40, "b" * 40
    decision = m.decide(
        pr_number=1,
        head_sha=head,
        base_sha=base,
        docs_only=True,
        checks=[_check(m.DOCS_CHECK, head)],
        statuses=[],
        workflow_evidence=_trusted_evidence(
            m, pr_number=1, head=head, base=base, docs=True
        ),
    )
    assert decision.state == "success"
    assert decision.reason == "docs-authority-passed"


def test_runtime_not_required_path_succeeds_only_on_current_head_and_base():
    m = _load_helper()
    head, base = "a" * 40, "b" * 40
    statuses = [
        _status(
            m.POLICY_CONTEXT,
            "success",
            f"PR-DEEP not required head={head[:12]} base={base[:12]}",
        )
    ]
    decision = m.decide(
        pr_number=2,
        head_sha=head,
        base_sha=base,
        docs_only=False,
        checks=_runtime_checks(m, head),
        statuses=statuses,
        workflow_evidence=_trusted_evidence(
            m, pr_number=2, head=head, base=base, policy_state="success"
        ),
    )
    assert decision.state == "success"
    assert decision.reason == "pr-deep-not-required"


def test_runtime_required_and_deep_passed_succeeds():
    m = _load_helper()
    head, base = "a" * 40, "b" * 40
    statuses = [
        _status(m.POLICY_CONTEXT, "success", f"PASS base={base}", ident=2),
        _status(m.DEEP_CONTEXT, "success", f"PASS base={base}", ident=3),
    ]
    decision = m.decide(
        pr_number=3,
        head_sha=head,
        base_sha=base,
        docs_only=False,
        checks=_runtime_checks(m, head),
        statuses=statuses,
        workflow_evidence=_trusted_evidence(
            m, pr_number=3, head=head, base=base, policy_state="pending", deep=True
        ),
    )
    assert decision.state == "success"
    assert decision.reason == "pr-deep-passed"


def test_stale_old_head_check_cannot_certify():
    m = _load_helper()
    head, base = "a" * 40, "b" * 40
    checks = _runtime_checks(m, head)
    checks[1] = _check(m.PR_FAST_CHECK, "c" * 40, ident=20)
    evidence = _trusted_evidence(
        m, pr_number=4, head=head, base=base, policy_state="success"
    )
    evidence[m.PR_FAST_WORKFLOW_PATH][0].jobs.clear()
    evidence[m.PR_FAST_WORKFLOW_PATH][0].jobs.append(checks[1])
    decision = m.decide(
        pr_number=4,
        head_sha=head,
        base_sha=base,
        docs_only=False,
        checks=checks,
        statuses=[],
        workflow_evidence=evidence,
    )
    assert decision.state == "failure"
    assert decision.reason == "stale-check-head:pr-fast"


def test_missing_normal_ci_stays_pending():
    m = _load_helper()
    head, base = "a" * 40, "b" * 40
    checks = [
        _check(m.DOCS_CHECK, head, ident=1),
        _check(m.HIGH_RISK_CHECK, head, ident=2),
    ]
    evidence = _trusted_evidence(
        m, pr_number=5, head=head, base=base, policy_state="success"
    )
    evidence[m.PR_FAST_WORKFLOW_PATH][0].jobs.clear()
    decision = m.decide(
        pr_number=5,
        head_sha=head,
        base_sha=base,
        docs_only=False,
        checks=checks,
        statuses=[],
        workflow_evidence=evidence,
    )
    assert decision.state == "pending"
    assert decision.reason == "missing-trusted-job:pr-fast"


def test_pending_policy_stays_pending():
    m = _load_helper()
    head, base = "a" * 40, "b" * 40
    decision = m.decide(
        pr_number=6,
        head_sha=head,
        base_sha=base,
        docs_only=False,
        checks=_runtime_checks(m, head),
        statuses=[_status(m.POLICY_CONTEXT, "pending", "PR-DEEP certification required")],
        workflow_evidence=_trusted_evidence(
            m, pr_number=6, head=head, base=base, policy_state="pending"
        ),
    )
    assert decision.state == "pending"
    assert decision.reason == "pr-deep-pending"


def test_required_deep_missing_stays_pending():
    m = _load_helper()
    head, base = "a" * 40, "b" * 40
    decision = m.decide(
        pr_number=7,
        head_sha=head,
        base_sha=base,
        docs_only=False,
        checks=_runtime_checks(m, head),
        statuses=[_status(m.POLICY_CONTEXT, "success", f"PASS base={base}")],
        workflow_evidence=_trusted_evidence(
            m, pr_number=7, head=head, base=base, policy_state="pending"
        ),
    )
    assert decision.state == "pending"
    assert decision.reason == "pr-deep-pending"


def test_mismatched_policy_base_cannot_certify():
    m = _load_helper()
    head, base, old_base = "a" * 40, "b" * 40, "c" * 40
    decision = m.decide(
        pr_number=8,
        head_sha=head,
        base_sha=base,
        docs_only=False,
        checks=_runtime_checks(m, head),
        statuses=[_status(m.POLICY_CONTEXT, "success", f"PASS base={old_base}")],
        workflow_evidence=_trusted_evidence(
            m, pr_number=8, head=head, base=base, policy_state="pending"
        ),
    )
    assert decision.state == "pending"
    assert decision.reason == "pr-deep-pending"


def test_old_base_deep_success_cannot_certify_current_base():
    m = _load_helper()
    head, base, old_base = "a" * 40, "b" * 40, "c" * 40
    evidence = _trusted_evidence(
        m, pr_number=9, head=head, base=base, policy_state="pending", deep=True
    )
    evidence[m.DEEP_WORKFLOW_PATH][0].jobs[0]["name"] = m._marker_name(
        m.DEEP_MARKER_PREFIX, state=None, pr_number=9, head_sha=head, base_sha=old_base
    )
    decision = m.decide(
        pr_number=9,
        head_sha=head,
        base_sha=base,
        docs_only=False,
        checks=_runtime_checks(m, head),
        statuses=[
            _status(m.POLICY_CONTEXT, "success", f"PASS base={base}", ident=2),
            _status(m.DEEP_CONTEXT, "success", f"PASS base={old_base}", ident=3),
        ],
        workflow_evidence=evidence,
    )
    assert decision.state == "pending"
    assert decision.reason == "pr-deep-pending"


def _trusted_run(m, path, event, pr_number, head, base, *, run_id=1, **overrides):
    run = {
        "id": run_id,
        "path": path,
        "event": event,
        "head_sha": head,
        "repository": {"full_name": "repo"},
        "head_repository": {"full_name": "repo"},
        "pull_requests": [{"number": pr_number, "base": {"sha": base}}],
        "created_at": "2026-08-30T05:00:00Z",
        "updated_at": "2026-08-30T06:00:00Z",
    }
    run.update(overrides)
    return run


def _trusted_evidence(m, *, pr_number, head, base, docs=True,
                      policy_state=None, deep=False, path=None, event=None):
    evidence = {}
    if docs:
        p = path or m.DOCS_WORKFLOW_PATH
        e = event or "pull_request"
        jobs = [_check(m.DOCS_CHECK, head)]
        evidence[p] = [m.WorkflowEvidence(
            _trusted_run(m, p, e, pr_number, head, base), jobs)]
    for name, p, e in ((m.PR_FAST_CHECK, m.PR_FAST_WORKFLOW_PATH, "pull_request"),
                       (m.HIGH_RISK_CHECK, m.HIGH_RISK_WORKFLOW_PATH, "pull_request_target")):
        jobs = [_check(name, head, ident=2)]
        evidence[p] = [m.WorkflowEvidence(_trusted_run(m, p, e, pr_number, head, base), jobs)]
    if policy_state is not None:
        p = m.POLICY_WORKFLOW_PATH
        name = m._marker_name(m.POLICY_MARKER_PREFIX, state=policy_state,
                              pr_number=pr_number, head_sha=head, base_sha=base)
        evidence[p] = [m.WorkflowEvidence(
            _trusted_run(m, p, "pull_request_target", pr_number, head, base, run_id=10),
            [{"id": 10, "name": name, "status": "completed", "conclusion": "success",
              "created_at": "2026-08-30T06:00:00Z", "updated_at": "2026-08-30T06:00:00Z"}])]
    if deep:
        p = m.DEEP_WORKFLOW_PATH
        evidence[p] = [m.WorkflowEvidence(
            _trusted_run(m, p, "workflow_dispatch", pr_number, "d" * 40, base,
                         run_id=20, head_branch="main", ref="refs/heads/main",
                         pull_requests=[]),
            [{"id": 20, "name": m._marker_name(m.DEEP_MARKER_PREFIX, state=None,
                                                   pr_number=pr_number, head_sha=head, base_sha=base),
              "status": "completed", "conclusion": "success",
              "created_at": "2026-08-30T06:00:00Z", "updated_at": "2026-08-30T06:00:00Z"}])]
    return evidence


def _decide_with_evidence(m, evidence, *, docs_only=False, head="a" * 40,
                          base="b" * 40, pr_number=42, statuses=None):
    return m.decide(pr_number=pr_number, head_sha=head, base_sha=base,
                    docs_only=docs_only,
                    checks=_runtime_checks(m, head),
                    statuses=statuses or [], workflow_evidence=evidence)


def test_provenance_adversarial_required_cases():
    """All authority paths require exact Actions provenance, not display data."""
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    # 1 docs-only exact success; 2 candidate same-name check alone is pending.
    assert _decide_with_evidence(m, _trusted_evidence(m, pr_number=pr, head=head, base=base,
                                                       policy_state=None), docs_only=True).state == "success"
    assert _decide_with_evidence(m, {}, docs_only=True).state == "pending"
    # 3 wrong path and 4 wrong event are not trusted runs.
    assert not m._run_matches(_trusted_run(m, "evil.yml", "pull_request", pr, head, base),
                              repo="repo", workflow_path=m.DOCS_WORKFLOW_PATH,
                              event="pull_request", pr_number=pr, head_sha=head, base_sha=base)
    assert not m._run_matches(_trusted_run(m, m.DOCS_WORKFLOW_PATH, "push", pr, head, base),
                              repo="repo", workflow_path=m.DOCS_WORKFLOW_PATH,
                              event="pull_request", pr_number=pr, head_sha=head, base_sha=base)
    # 5 wrong repository, 6 stale head, 7 stale base fail to match.
    assert not m._run_matches(_trusted_run(m, m.DOCS_WORKFLOW_PATH, "pull_request", pr, head, base,
                                           repository={"full_name": "attacker/repo"}),
                              repo="repo", workflow_path=m.DOCS_WORKFLOW_PATH,
                              event="pull_request", pr_number=pr, head_sha=head, base_sha=base)
    assert not m._run_matches(_trusted_run(m, m.DOCS_WORKFLOW_PATH, "pull_request", pr, "c" * 40, base),
                              repo="repo", workflow_path=m.DOCS_WORKFLOW_PATH,
                              event="pull_request", pr_number=pr, head_sha=head, base_sha=base)
    assert not m._run_matches(_trusted_run(m, m.DOCS_WORKFLOW_PATH, "pull_request", pr, head, base,
                                           base_sha="c" * 40),
                              repo="repo", workflow_path=m.DOCS_WORKFLOW_PATH,
                              event="pull_request", pr_number=pr, head_sha=head, base_sha=base)
    assert not m._run_matches(_trusted_run(m, m.DOCS_WORKFLOW_PATH, "pull_request", pr, head, base,
                                           pull_requests=[{"number": pr}]),
                              repo="repo", workflow_path=m.DOCS_WORKFLOW_PATH,
                              event="pull_request", pr_number=pr, head_sha=head, base_sha=base)
    # 8 runtime no-DEEP and 9 runtime exact trusted DEEP success.
    assert _decide_with_evidence(m, _trusted_evidence(m, pr_number=pr, head=head, base=base,
                                                       policy_state="success")).state == "success"
    assert _decide_with_evidence(m, _trusted_evidence(m, pr_number=pr, head=head, base=base,
                                                       policy_state="pending", deep=True)).state == "success"
    # 10 candidate statuses remain visibility only.
    assert _decide_with_evidence(m, {}, statuses=[_status(m.POLICY_CONTEXT, "success", "forged")]).state == "pending"
    # 11–14 exact marker identity rejects wrong path/event/head/base.
    for kwargs in ({"path": "wrong.yml"}, {"event": "push"}):
        deep_run = _trusted_run(m, m.DEEP_WORKFLOW_PATH, "workflow_dispatch", pr,
                                "d" * 40, base, head_branch="main",
                                ref="refs/heads/main", pull_requests=[])
        deep_run.update(kwargs)
        assert not m._run_matches(
            deep_run, repo="repo", workflow_path=m.DEEP_WORKFLOW_PATH,
            event="workflow_dispatch", pr_number=None, head_sha=None,
            base_sha=base, workflow_dispatch=True)
    for bad_name in (m._marker_name(m.DEEP_MARKER_PREFIX, state=None, pr_number=pr, head_sha="c" * 40, base_sha=base),
                     m._marker_name(m.DEEP_MARKER_PREFIX, state=None, pr_number=pr, head_sha=head, base_sha="c" * 40)):
        evidence = _trusted_evidence(m, pr_number=pr, head=head, base=base, policy_state="pending", deep=True)
        evidence[m.DEEP_WORKFLOW_PATH][0].jobs[0]["name"] = bad_name
        assert _decide_with_evidence(m, evidence).state == "pending"
    # 15 policy pending, 16 policy failure, 17 malformed state/name, 18 missing marker.
    assert _decide_with_evidence(m, _trusted_evidence(m, pr_number=pr, head=head, base=base,
                                                       policy_state="pending")).state == "pending"
    assert _decide_with_evidence(m, _trusted_evidence(m, pr_number=pr, head=head, base=base,
                                                       policy_state="failure")).state == "failure"
    malformed = _trusted_evidence(m, pr_number=pr, head=head, base=base, policy_state="pending")
    malformed[m.POLICY_WORKFLOW_PATH][0].jobs[0]["name"] = "pr-deep-policy marker state=bogus"
    assert _decide_with_evidence(m, malformed).state == "pending"
    missing = _trusted_evidence(m, pr_number=pr, head=head, base=base, policy_state="pending")
    missing[m.POLICY_WORKFLOW_PATH][0].jobs.clear()
    assert _decide_with_evidence(m, missing).state == "pending"
    # 19 forged candidate marker without trusted workflow is never authority.
    assert _decide_with_evidence(m, {}, statuses=[_status(m.POLICY_CONTEXT, "success", "forged")]).state == "pending"
    # 20 renamed code into docs cannot downgrade the PR to docs-only.
    assert not m._files_are_docs_only([
        {"filename": "docs/runtime.md", "status": "renamed",
         "previous_filename": "backend/runtime.py"}
    ])
    assert _decide_with_evidence(m, {}, docs_only=False).mode == "runtime"
    # 21 malformed trusted metadata fails closed and cannot grant success.
    malformed_run = _trusted_evidence(m, pr_number=pr, head=head, base=base, policy_state="success")
    malformed_run[m.POLICY_WORKFLOW_PATH][0].run.update(
        updated_at="not-a-timestamp", created_at="not-a-timestamp", started_at="not-a-timestamp"
    )
    assert _decide_with_evidence(m, malformed_run).state == "failure"


def test_unrelated_newer_dispatch_run_cannot_mask_exact_marker():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="pending", deep=True
    )
    evidence[m.DEEP_WORKFLOW_PATH].append(m.WorkflowEvidence(
        _trusted_run(m, m.DEEP_WORKFLOW_PATH, "workflow_dispatch", 999,
                     "d" * 40, base, run_id=21, head_branch="main",
                     ref="refs/heads/main", pull_requests=[],
                     updated_at="2026-08-30T07:00:00Z"),
        [],
    ))
    decision = _decide_with_evidence(m, evidence, pr_number=pr)
    assert decision.state == "success"
    assert decision.reason == "pr-deep-passed"


def test_exact_failed_marker_is_safely_attributable_failure():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="pending", deep=True
    )
    evidence[m.DEEP_WORKFLOW_PATH][0].jobs[0]["conclusion"] = "failure"
    decision = _decide_with_evidence(m, evidence, pr_number=pr)
    assert decision.state == "failure"


def test_not_required_status_with_wrong_head_prefix_cannot_certify():
    m = _load_helper()
    head, base = "a" * 40, "b" * 40
    decision = m.decide(
        pr_number=10,
        head_sha=head,
        base_sha=base,
        docs_only=False,
        checks=_runtime_checks(m, head),
        statuses=[
            _status(
                m.POLICY_CONTEXT,
                "success",
                f"PR-DEEP not required head={'c' * 12} base={base[:12]}",
            )
        ],
        workflow_evidence=_trusted_evidence(
            m, pr_number=10, head=head, base=base, policy_state="pending"
        ),
    )
    assert decision.state == "pending"
    assert decision.reason == "pr-deep-pending"
