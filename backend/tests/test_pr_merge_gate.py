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
    )
    assert decision.state == "success"
    assert decision.reason == "pr-deep-passed"


def test_stale_old_head_check_cannot_certify():
    m = _load_helper()
    head, base = "a" * 40, "b" * 40
    checks = _runtime_checks(m, head)
    checks[1] = _check(m.PR_FAST_CHECK, "c" * 40, ident=20)
    decision = m.decide(
        pr_number=4,
        head_sha=head,
        base_sha=base,
        docs_only=False,
        checks=checks,
        statuses=[],
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
    decision = m.decide(
        pr_number=5,
        head_sha=head,
        base_sha=base,
        docs_only=False,
        checks=checks,
        statuses=[],
    )
    assert decision.state == "pending"
    assert decision.reason == "missing-check:pr-fast"


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
    )
    assert decision.state == "pending"
    assert decision.reason == "pr-deep-policy-pending"


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
    )
    assert decision.state == "pending"
    assert decision.reason == "missing-pr-deep"


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
    )
    assert decision.state == "pending"
    assert decision.reason == "stale-pr-deep-policy-base"


def test_old_base_deep_success_cannot_certify_current_base():
    m = _load_helper()
    head, base, old_base = "a" * 40, "b" * 40, "c" * 40
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
    )
    assert decision.state == "pending"
    assert decision.reason == "stale-pr-deep-base"


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
    )
    assert decision.state == "pending"
    assert decision.reason == "stale-pr-deep-policy-base"
