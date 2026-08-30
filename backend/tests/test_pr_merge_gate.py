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


def _check(name: str, head: str, *, conclusion: str = "success", status: str = "completed", ident: int = 1, run_id: int = 1):
    return {
        "id": ident,
        "run_id": run_id,
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
    assert set(on["workflow_run"]["workflows"]) == {"CI", "docs-contract", "high-risk-governance", "pr-deep-policy", "pr-deep"}
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
        repo="repo",
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
        repo="repo",
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
        repo="repo",
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
    checks[1] = _check(m.PR_FAST_CHECK, "c" * 40, ident=20, run_id=2)
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
        repo="repo",
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
        repo="repo",
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
        repo="repo",
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
        repo="repo",
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
        repo="repo",
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
        repo="repo",
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
        run = _trusted_run(m, p, e, pr_number, head, base)
        jobs = [_check(m.DOCS_CHECK, head, run_id=run["id"])]
        evidence[p] = [m.WorkflowEvidence(run, jobs)]
    for name, p, e in ((m.PR_FAST_CHECK, m.PR_FAST_WORKFLOW_PATH, "pull_request"),
                       (m.HIGH_RISK_CHECK, m.HIGH_RISK_WORKFLOW_PATH, "pull_request_target")):
        run = _trusted_run(m, p, e, pr_number, head, base, run_id=2)
        jobs = [_check(name, head, ident=2, run_id=run["id"])]
        evidence[p] = [m.WorkflowEvidence(run, jobs)]
    if policy_state is not None:
        p = m.POLICY_WORKFLOW_PATH
        name = m._marker_name(m.POLICY_MARKER_PREFIX, state=policy_state,
                              pr_number=pr_number, head_sha=head, base_sha=base)
        run = _trusted_run(m, p, "pull_request_target", pr_number, head, base, run_id=10)
        evidence[p] = [m.WorkflowEvidence(
            run,
            [{"id": 10, "run_id": 10, "name": name, "head_sha": head,
              "status": "completed", "conclusion": "success",
              "created_at": "2026-08-30T06:00:00Z", "updated_at": "2026-08-30T06:00:00Z"}])]
    if deep:
        p = m.DEEP_WORKFLOW_PATH
        run = _trusted_run(m, p, "workflow_dispatch", pr_number, "d" * 40, base,
                           run_id=20, head_branch="main", ref="refs/heads/main",
                           pull_requests=[])
        evidence[p] = [m.WorkflowEvidence(
            run,
            [{"id": 20, "run_id": 20,
              "name": m._marker_name(m.DEEP_MARKER_PREFIX, state=None,
                                      pr_number=pr_number, head_sha=head, base_sha=base),
              "head_sha": "d" * 40, "status": "completed", "conclusion": "success",
              "created_at": "2026-08-30T06:00:00Z", "updated_at": "2026-08-30T06:00:00Z"}])]
    return evidence


def _decide_with_evidence(m, evidence, *, docs_only=False, head="a" * 40,
                          base="b" * 40, pr_number=42, statuses=None, repo="repo",
                          changed_paths=None):
    return m.decide(pr_number=pr_number, head_sha=head, base_sha=base,
                    docs_only=docs_only,
                    checks=_runtime_checks(m, head),
                    statuses=statuses or [], workflow_evidence=evidence, repo=repo,
                    changed_paths=changed_paths)


def test_provenance_adversarial_required_cases():
    """All authority paths require exact Actions provenance, not display data."""
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    # 1 docs-only exact success; 2 candidate same-name check alone is pending.
    assert _decide_with_evidence(m, _trusted_evidence(m, pr_number=pr, head=head, base=base,
                                                       policy_state=None), docs_only=True).state == "success"
    assert _decide_with_evidence(m, {}, docs_only=True).state == "pending"
    # 3–7 canonical-key evidence with wrong path/event/repository/head/base/PR
    # metadata must be rejected by production decide(), not just a helper.
    bad_runs = [
        _trusted_run(m, "evil.yml", "pull_request", pr, head, base),
        _trusted_run(m, m.DOCS_WORKFLOW_PATH, "push", pr, head, base),
        _trusted_run(m, m.DOCS_WORKFLOW_PATH, "pull_request", pr, head, base,
                     repository={"full_name": "attacker/repo"}),
        _trusted_run(m, m.DOCS_WORKFLOW_PATH, "pull_request", pr, "c" * 40, base),
        _trusted_run(m, m.DOCS_WORKFLOW_PATH, "pull_request", pr, head, base,
                     base_sha="c" * 40),
        _trusted_run(m, m.DOCS_WORKFLOW_PATH, "pull_request", pr, head, base,
                     pull_requests=[{"number": pr}]),
    ]
    for bad_run in bad_runs:
        bad = _trusted_evidence(m, pr_number=pr, head=head, base=base, policy_state=None)
        bad[m.DOCS_WORKFLOW_PATH][0] = m.WorkflowEvidence(
            bad_run, [_check(m.DOCS_CHECK, head, run_id=bad_run["id"])])
        assert _decide_with_evidence(m, bad, docs_only=True).state != "success"
    # 8 runtime no-DEEP and 9 runtime exact trusted DEEP success.
    assert _decide_with_evidence(m, _trusted_evidence(m, pr_number=pr, head=head, base=base,
                                                       policy_state="success")).state == "success"
    assert _decide_with_evidence(m, _trusted_evidence(m, pr_number=pr, head=head, base=base,
                                                       policy_state="pending", deep=True)).state == "success"
    # 10 candidate statuses remain visibility only.
    assert _decide_with_evidence(m, {}, statuses=[_status(m.POLICY_CONTEXT, "success", "forged")]).state == "pending"
    # 11–14 exact marker identity rejects wrong path/event/head/base.
    for kwargs in ({"path": "wrong.yml"}, {"event": "push"}):
        deep = _trusted_evidence(m, pr_number=pr, head=head, base=base,
                                 policy_state="pending", deep=True)
        deep_run = deep[m.DEEP_WORKFLOW_PATH][0].run
        deep_run.update(kwargs)
        assert _decide_with_evidence(m, deep).state != "success"
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
        repo="repo",
        workflow_evidence=_trusted_evidence(
            m, pr_number=10, head=head, base=base, policy_state="pending"
        ),
    )
    assert decision.state == "pending"
    assert decision.reason == "pr-deep-pending"


def test_missing_job_and_marker_provenance_cannot_grant_success():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    missing_job = _trusted_evidence(m, pr_number=pr, head=head, base=base, policy_state=None)
    del missing_job[m.DOCS_WORKFLOW_PATH][0].jobs[0]["run_id"]
    assert _decide_with_evidence(m, missing_job, docs_only=True).state != "success"

    missing_marker = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="pending", deep=True
    )
    del missing_marker[m.DEEP_WORKFLOW_PATH][0].jobs[0]["head_sha"]
    assert _decide_with_evidence(m, missing_marker).state != "success"


def test_workflow_evidence_resolves_only_current_check_hint(monkeypatch):
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    exact = _trusted_run(
        m, m.DOCS_WORKFLOW_PATH, "pull_request", pr, head, base, run_id=500,
        repository={"full_name": "owner/repo"},
        head_repository={"full_name": "owner/repo"},
    )
    calls = []

    def fake_api(url, token):
        del token
        calls.append(url)
        if url.endswith("/actions/runs/500"):
            return exact
        assert url.endswith("/actions/runs/500/jobs?per_page=100&page=1")
        return {"jobs": [_check(m.DOCS_CHECK, head, run_id=500)]}

    monkeypatch.setattr(m, "_api_json", fake_api)
    evidence = m._workflow_evidence(
        "owner/repo", "token", workflow_path=m.DOCS_WORKFLOW_PATH,
        event="pull_request", pr_number=pr, head_sha=head, base_sha=base,
        hints=[{"name": m.DOCS_CHECK, "head_sha": head,
                "details_url": "https://github.com/owner/repo/actions/runs/500/job/9"}],
    )
    assert len(evidence) == 1
    assert len(calls) == 2
    assert not any("workflows/" in url for url in calls)


def test_workflow_evidence_rejects_malformed_external_and_wrong_repo_hints(monkeypatch):
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    calls = []
    monkeypatch.setattr(m, "_api_json", lambda url, token: calls.append(url))
    hints = [
        {"head_sha": head, "details_url": "https://evil.example/repo/actions/runs/1"},
        {"head_sha": head, "details_url": "https://github.com/other/repo/actions/runs/2"},
        {"head_sha": head, "details_url": "https://github.com/owner/repo/actions/runs/not-a-number"},
        {"head_sha": head, "details_url": "https://github.com/owner/repo/actions/runs/3?redirect=evil"},
        {"head_sha": "c" * 40, "details_url": "https://github.com/owner/repo/actions/runs/4"},
    ]
    assert m._workflow_evidence(
        "owner/repo", "token", workflow_path=m.DOCS_WORKFLOW_PATH,
        event="pull_request", pr_number=pr, head_sha=head, base_sha=base,
        hints=hints,
    ) == []
    assert calls == []


def test_workflow_evidence_has_small_hint_bound_without_history_fallback(monkeypatch):
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    calls = []

    def fake_api(url, token):
        del token
        calls.append(url)
        return _trusted_run(m, "wrong.yml", "pull_request", pr, head, base, run_id=1)

    monkeypatch.setattr(m, "_api_json", fake_api)
    hints = [
        {"head_sha": head,
         "details_url": f"https://github.com/owner/repo/actions/runs/{i}"}
        for i in range(1, 10_001)
    ]
    assert m._workflow_evidence(
        "owner/repo", "token", workflow_path=m.DOCS_WORKFLOW_PATH,
        event="pull_request", pr_number=pr, head_sha=head, base_sha=base,
        hints=hints,
    ) == []
    assert len(calls) == m.MAX_WORKFLOW_HINTS
    assert not any("workflows/" in url for url in calls)


def test_workflow_dispatch_evidence_uses_exact_candidate_status_url(monkeypatch):
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    run = _trusted_run(
        m, m.DEEP_WORKFLOW_PATH, "workflow_dispatch", pr, "d" * 40, base,
        run_id=700, head_branch="main", pull_requests=[],
        repository={"full_name": "owner/repo"},
        head_repository={"full_name": "owner/repo"},
    )
    calls = []

    def fake_api(url, token):
        del token
        calls.append(url)
        if url.endswith("/actions/runs/700"):
            return run
        return {"jobs": [{"id": 1, "run_id": 700, "head_sha": "d" * 40,
                          "name": m._marker_name(m.DEEP_MARKER_PREFIX, state=None,
                                                   pr_number=pr, head_sha=head, base_sha=base),
                          "status": "completed", "conclusion": "success",
                          "created_at": "2026-08-30T06:00:00Z",
                          "updated_at": "2026-08-30T06:00:00Z"}]}

    monkeypatch.setattr(m, "_api_json", fake_api)
    evidence = m._workflow_evidence(
        "owner/repo", "token", workflow_path=m.DEEP_WORKFLOW_PATH,
        event="workflow_dispatch", pr_number=pr, head_sha=head, base_sha=base,
        workflow_dispatch=True, hint_context=m.DEEP_CONTEXT,
        hints=[{"context": m.DEEP_CONTEXT, "sha": head, "state": "failure",
                 "target_url": "https://github.com/owner/repo/actions/runs/700"}],
    )
    assert len(evidence) == 1
    assert calls == ["https://api.github.com/repos/owner/repo/actions/runs/700",
                     "https://api.github.com/repos/owner/repo/actions/runs/700/jobs?per_page=100&page=1"]
def test_older_exact_marker_survives_newer_stale_marker():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="pending", deep=True
    )
    newer = _trusted_run(
        m, m.DEEP_WORKFLOW_PATH, "workflow_dispatch", pr, "d" * 40, base,
        run_id=21, head_branch="main", ref="refs/heads/main", pull_requests=[],
        updated_at="2026-08-30T07:00:00Z",
    )
    evidence[m.DEEP_WORKFLOW_PATH].append(m.WorkflowEvidence(
        newer,
        [{"id": 21, "run_id": 21,
          "name": m._marker_name(m.DEEP_MARKER_PREFIX, state=None, pr_number=pr,
                                  head_sha="c" * 40, base_sha=base),
          "head_sha": "d" * 40, "status": "completed", "conclusion": "success",
          "created_at": "2026-08-30T07:00:00Z", "updated_at": "2026-08-30T07:00:00Z"}],
    ))
    decision = _decide_with_evidence(m, evidence, pr_number=pr)
    assert decision.state == "success"
    assert decision.reason == "pr-deep-passed"


def test_newer_same_name_malformed_marker_blocks_older_exact_marker():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    for kind in ("policy", "deep"):
        evidence = _trusted_evidence(
            m, pr_number=pr, head=head, base=base,
            policy_state="success" if kind == "policy" else "pending",
            deep=kind == "deep",
        )
        path = m.POLICY_WORKFLOW_PATH if kind == "policy" else m.DEEP_WORKFLOW_PATH
        prefix = m.POLICY_MARKER_PREFIX if kind == "policy" else m.DEEP_MARKER_PREFIX
        event = "pull_request_target" if kind == "policy" else "workflow_dispatch"
        run_head = head if kind == "policy" else "d" * 40
        run = _trusted_run(
            m, path, event, pr, run_head, base, run_id=30,
            head_branch="main" if kind == "deep" else None,
            ref="refs/heads/main" if kind == "deep" else None,
            pull_requests=[] if kind == "deep" else [{"number": pr, "base": {"sha": base}}],
            updated_at="2026-08-30T07:00:00Z",
        )
        marker = {"id": 30, "run_id": 30,
                  "name": m._marker_name(prefix, state="success" if kind == "policy" else None,
                                           pr_number=pr, head_sha=head, base_sha=base),
                  "head_sha": "c" * 40, "status": "completed", "conclusion": "success",
                  "created_at": "2026-08-30T07:00:00Z", "updated_at": "2026-08-30T07:00:00Z"}
        evidence[path].append(m.WorkflowEvidence(run, [marker]))
        assert _decide_with_evidence(m, evidence, pr_number=pr).state == "failure"

        for malformed_field in ("run_id", "head_sha"):
            evidence = _trusted_evidence(
                m, pr_number=pr, head=head, base=base,
                policy_state="success" if kind == "policy" else "pending",
                deep=kind == "deep",
            )
            run = _trusted_run(
                m, path, event, pr, run_head, base, run_id=31,
                head_branch="main" if kind == "deep" else None,
                ref="refs/heads/main" if kind == "deep" else None,
                pull_requests=[] if kind == "deep" else [{"number": pr, "base": {"sha": base}}],
                updated_at="2026-08-30T07:00:00Z",
            )
            marker = {"id": 31, "run_id": 31,
                      "name": m._marker_name(prefix, state="success" if kind == "policy" else None,
                                               pr_number=pr, head_sha=head, base_sha=base),
                      "head_sha": run_head, "status": "completed", "conclusion": "success",
                      "created_at": "2026-08-30T07:00:00Z", "updated_at": "2026-08-30T07:00:00Z"}
            marker.pop(malformed_field)
            evidence[path].append(m.WorkflowEvidence(run, [marker]))
            assert _decide_with_evidence(m, evidence, pr_number=pr).state == "failure"


def test_trusted_workflow_dispatch_without_ref_field_can_certify():
    """Real workflow-runs REST responses do not expose the workflow ``ref``
    key. A legitimate trusted PR-DEEP run therefore arrives without one and
    must still certify when every other exact invariant passes."""
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="pending", deep=True
    )
    run = evidence[m.DEEP_WORKFLOW_PATH][0].run
    run.pop("ref", None)
    assert "ref" not in run
    assert run.get("head_branch") == "main"
    decision = _decide_with_evidence(m, evidence, pr_number=pr)
    assert decision.state == "success"
    assert decision.reason == "pr-deep-passed"


def test_workflow_dispatch_with_non_main_head_branch_is_rejected():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="pending", deep=True
    )
    evidence[m.DEEP_WORKFLOW_PATH][0].run["head_branch"] = "feature/evil"
    assert _decide_with_evidence(m, evidence, pr_number=pr).state != "success"


def test_workflow_dispatch_with_missing_head_branch_is_rejected():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="pending", deep=True
    )
    evidence[m.DEEP_WORKFLOW_PATH][0].run.pop("head_branch", None)
    assert _decide_with_evidence(m, evidence, pr_number=pr).state != "success"


def test_workflow_dispatch_with_malformed_head_branch_is_rejected():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="pending", deep=True
    )
    evidence[m.DEEP_WORKFLOW_PATH][0].run["head_branch"] = "Main"  # wrong case
    assert _decide_with_evidence(m, evidence, pr_number=pr).state != "success"


def test_pr_merge_gate_workflow_run_trusted_sources_include_marker_workflows():
    """The merge gate must reevaluate after the trusted marker-producing
    workflows finish, so the ``workflow_run`` trigger must list them
    explicitly. Without this, an early visibility status can leave the gate
    permanently pending until the next unrelated event."""
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    on = data.get(True) or data.get("on") or {}
    sources = set(on["workflow_run"]["workflows"])
    assert "pr-deep-policy" in sources
    assert "pr-deep" in sources
    # Sanity check: the existing sources are preserved.
    assert {"CI", "docs-contract", "high-risk-governance"} <= sources


def test_candidate_modifying_pr_fast_authority_workflow_fails_closed():
    """A PR that touches ``.github/workflows/ci.yml`` cannot use the
    ``pr-fast`` check as merge authority — the workflow itself would be
    candidate-controlled. The gate must fail closed with a deterministic
    reason rather than invent a self-certification fallback."""
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="success"
    )
    decision = _decide_with_evidence(
        m, evidence,
        changed_paths={m.PR_FAST_WORKFLOW_PATH, "backend/foo.py"},
    )
    assert decision.state == "failure"
    assert decision.reason == f"candidate-modifies-authority-workflow:{m.PR_FAST_WORKFLOW_PATH}"


def test_candidate_modifying_docs_authority_workflow_fails_closed():
    """Same guarantee for ``.github/workflows/docs-contract.yml``: the
    docs-authority check must not be granted when the candidate owns the
    workflow definition itself."""
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(m, pr_number=pr, head=head, base=base)
    decision = _decide_with_evidence(
        m, evidence,
        docs_only=True,
        changed_paths={"docs/runtime.md", m.DOCS_WORKFLOW_PATH},
    )
    assert decision.state == "failure"
    assert decision.reason == f"candidate-modifies-authority-workflow:{m.DOCS_WORKFLOW_PATH}"


def test_candidate_renaming_pr_fast_authority_workflow_away_fails_closed():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="success"
    )
    # previous_filename == authority path → rename-away must still trip guard.
    decision = _decide_with_evidence(
        m, evidence,
        changed_paths={m.PR_FAST_WORKFLOW_PATH, "backend/renamed_ci.yml"},
    )
    assert decision.state == "failure"
    assert decision.reason == f"candidate-modifies-authority-workflow:{m.PR_FAST_WORKFLOW_PATH}"


def test_candidate_renaming_into_pr_fast_authority_workflow_fails_closed():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="success"
    )
    # filename == authority path → rename-into must trip the guard.
    decision = _decide_with_evidence(
        m, evidence,
        changed_paths={m.PR_FAST_WORKFLOW_PATH},
    )
    assert decision.state == "failure"
    assert decision.reason == f"candidate-modifies-authority-workflow:{m.PR_FAST_WORKFLOW_PATH}"


def test_candidate_renaming_docs_authority_workflow_away_fails_closed():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(m, pr_number=pr, head=head, base=base)
    # previous_filename == authority path → rename-away must still trip guard.
    decision = _decide_with_evidence(
        m, evidence,
        docs_only=True,
        changed_paths={m.DOCS_WORKFLOW_PATH, "backend/old_docs.yml"},
    )
    assert decision.state == "failure"
    assert decision.reason == f"candidate-modifies-authority-workflow:{m.DOCS_WORKFLOW_PATH}"


def test_candidate_renaming_into_docs_authority_workflow_fails_closed():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(m, pr_number=pr, head=head, base=base)
    # filename == authority path → rename-into must trip the guard.
    decision = _decide_with_evidence(
        m, evidence,
        docs_only=True,
        changed_paths={m.DOCS_WORKFLOW_PATH},
    )
    assert decision.state == "failure"
    assert decision.reason == f"candidate-modifies-authority-workflow:{m.DOCS_WORKFLOW_PATH}"


def test_candidate_authority_guard_uses_rename_aware_normalization():
    """End-to-end: pass raw PR-file dicts through ``_normalize_changed_paths``
    so a rename-away (previous_filename = authority path) surfaces in the
    guard, even though the new filename is something benign."""
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="success"
    )
    files = [
        {"filename": "backend/renamed.yml", "status": "renamed",
         "previous_filename": m.PR_FAST_WORKFLOW_PATH},
    ]
    changed_paths = m._normalize_changed_paths(files)
    assert m.PR_FAST_WORKFLOW_PATH in changed_paths
    decision = _decide_with_evidence(m, evidence, changed_paths=changed_paths)
    assert decision.state == "failure"
    assert decision.reason == f"candidate-modifies-authority-workflow:{m.PR_FAST_WORKFLOW_PATH}"


def test_candidate_modifying_high_risk_workflow_does_not_fail_on_authority_rule():
    """``high-risk-governance`` is a trusted ``pull_request_target`` workflow
    that runs against the base checkout, so changing it on the candidate
    must not trigger the candidate-controlled authority guard."""
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="success"
    )
    decision = _decide_with_evidence(
        m, evidence,
        changed_paths={m.HIGH_RISK_WORKFLOW_PATH, "backend/foo.py"},
    )
    assert decision.state == "success"


def test_candidate_modifying_pr_deep_policy_does_not_fail_on_authority_rule():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="pending", deep=True
    )
    decision = _decide_with_evidence(
        m, evidence,
        changed_paths={m.POLICY_WORKFLOW_PATH, "scripts/x.py"},
    )
    assert decision.state == "success"
    assert decision.reason == "pr-deep-passed"


def test_candidate_modifying_pr_deep_does_not_fail_on_authority_rule():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="pending", deep=True
    )
    decision = _decide_with_evidence(
        m, evidence,
        changed_paths={m.DEEP_WORKFLOW_PATH, "scripts/x.py"},
    )
    assert decision.state == "success"
    assert decision.reason == "pr-deep-passed"


def test_normalize_changed_paths_is_rename_aware():
    m = _load_helper()
    files = [
        {"filename": "backend/x.py"},
        {"filename": "backend/y.py", "status": "renamed",
         "previous_filename": ".github/workflows/ci.yml"},
        {"filename": ".github/workflows/docs-contract.yml", "status": "renamed",
         "previous_filename": "docs/old.md"},
        {"filename": "docs/k.md"},
    ]
    normalized = m._normalize_changed_paths(files)
    assert ".github/workflows/ci.yml" in normalized
    assert ".github/workflows/docs-contract.yml" in normalized
    assert "backend/x.py" in normalized
    assert "backend/y.py" in normalized
    assert "docs/old.md" in normalized
    assert "docs/k.md" in normalized


def test_normalize_changed_paths_handles_none_or_empty_input():
    m = _load_helper()
    assert m._normalize_changed_paths(None) == set()
    assert m._normalize_changed_paths([]) == set()


def test_existing_pr_fast_success_with_unchanged_authority_workflow_preserved():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(
        m, pr_number=pr, head=head, base=base, policy_state="success"
    )
    decision = _decide_with_evidence(
        m, evidence, changed_paths={"backend/foo.py"}
    )
    assert decision.state == "success"
    assert decision.reason == "pr-deep-not-required"


def test_existing_docs_authority_success_with_unchanged_authority_workflow_preserved():
    m = _load_helper()
    head, base, pr = "a" * 40, "b" * 40, 42
    evidence = _trusted_evidence(m, pr_number=pr, head=head, base=base, policy_state=None)
    decision = _decide_with_evidence(
        m, evidence, docs_only=True, changed_paths={"docs/x.md"}
    )
    assert decision.state == "success"
    assert decision.reason == "docs-authority-passed"


def test_candidate_authority_rule_only_blocks_candidate_controlled_paths():
    m = _load_helper()
    # Sanity: the exact set the guard relies on must contain the two
    # candidate-controlled authority workflows and nothing else.
    assert m.CANDIDATE_CONTROLLED_AUTHORITY_WORKFLOWS == frozenset({
        m.DOCS_WORKFLOW_PATH,
        m.PR_FAST_WORKFLOW_PATH,
    })
    assert m.HIGH_RISK_WORKFLOW_PATH not in m.CANDIDATE_CONTROLLED_AUTHORITY_WORKFLOWS
    assert m.POLICY_WORKFLOW_PATH not in m.CANDIDATE_CONTROLLED_AUTHORITY_WORKFLOWS
    assert m.DEEP_WORKFLOW_PATH not in m.CANDIDATE_CONTROLLED_AUTHORITY_WORKFLOWS
