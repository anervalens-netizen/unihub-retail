from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / ".github" / "governance" / "pr_merge_gate_workflow_run_bridge.py"
WORKFLOW = ROOT / ".github" / "workflows" / "pr-merge-gate.yml"


def _load_helper():
    spec = importlib.util.spec_from_file_location("pr_merge_gate_workflow_run_bridge", HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(m, *, repo: str = "owner/repo", run_id: int = 700):
    return {
        "id": run_id,
        "path": m.DEEP_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": "d" * 40,
        "repository": {"full_name": repo},
        "head_repository": {"full_name": repo},
    }


def _marker(m, *, run_id: int = 700, pr: int = 240, head: str = "a" * 40,
            base: str = "b" * 40):
    return {
        "run_id": run_id,
        "head_sha": "d" * 40,
        "name": f"pr-deep marker pr={pr} head={head} base={base}",
        "status": "completed",
        "conclusion": "success",
    }


def _pr(*, repo: str = "owner/repo", pr: int = 240, head: str = "a" * 40,
        base: str = "b" * 40):
    return {
        "number": pr,
        "state": "open",
        "head": {"sha": head, "repo": {"full_name": repo}},
        "base": {"ref": "main", "sha": base, "repo": {"full_name": repo}},
    }


def _install_api(monkeypatch, m, *, run=None, jobs=None, pr=None, repo="owner/repo", run_id=700):
    run = run or _run(m, repo=repo, run_id=run_id)
    jobs = jobs or [_marker(m, run_id=run_id)]
    pr = pr or _pr(repo=repo)
    calls = []

    def fake_api(url, token):
        assert token == "token"
        calls.append(url)
        if url == f"https://api.github.com/repos/{repo}/actions/runs/{run_id}":
            return run
        if url == f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100&page=1":
            return {"jobs": jobs}
        if url == f"https://api.github.com/repos/{repo}/pulls/240":
            return pr
        raise AssertionError(f"unexpected API call: {url}")

    monkeypatch.setattr(m, "_api_json", fake_api)
    return calls


def test_workflow_wires_trusted_bridge_before_evaluator():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["evaluate"]["steps"]
    names = [step.get("name") for step in steps]
    bridge_index = names.index("Resolve trusted PR-DEEP workflow_run candidate")
    evaluate_index = names.index("Evaluate exact-HEAD merge gate")
    assert bridge_index < evaluate_index
    assert steps[bridge_index]["if"] == "github.event_name == 'workflow_run'"
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "python3 .github/governance/pr_merge_gate_workflow_run_bridge.py" in text
    assert "GITHUB_EVENT_NAME=status" in text
    assert 'GITHUB_EVENT_PATH="$BRIDGE_EVENT_PATH"' in text


def test_valid_trusted_pr_deep_completion_bridges_exact_candidate(monkeypatch):
    m = _load_helper()
    calls = _install_api(monkeypatch, m)
    event = {"workflow_run": {"id": 700, "path": m.DEEP_WORKFLOW_PATH}}
    assert m.bridge_event(event, repo="owner/repo", token="token") == {
        "context": "retail/pr-deep",
        "sha": "a" * 40,
    }
    assert calls == [
        "https://api.github.com/repos/owner/repo/actions/runs/700",
        "https://api.github.com/repos/owner/repo/actions/runs/700/jobs?per_page=100&page=1",
        "https://api.github.com/repos/owner/repo/pulls/240",
    ]


def test_main_writes_synthetic_status_event(monkeypatch, tmp_path):
    m = _load_helper()
    _install_api(monkeypatch, m)
    source = tmp_path / "workflow-run.json"
    target = tmp_path / "candidate-event.json"
    source.write_text(
        json.dumps({"workflow_run": {"id": 700, "path": m.DEEP_WORKFLOW_PATH}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(source))
    monkeypatch.setenv("BRIDGE_EVENT_PATH", str(target))
    assert m.main() == 0
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "context": "retail/pr-deep",
        "sha": "a" * 40,
    }


def test_non_pr_deep_workflow_run_is_not_bridged(monkeypatch):
    m = _load_helper()

    def no_api(*args, **kwargs):
        raise AssertionError("non-PR-DEEP workflow_run must not call API")

    monkeypatch.setattr(m, "_api_json", no_api)
    event = {"workflow_run": {"id": 701, "path": ".github/workflows/ci.yml"}}
    assert m.bridge_event(event, repo="owner/repo", token="token") is None


def test_stale_current_pr_base_fails_closed(monkeypatch):
    m = _load_helper()
    _install_api(monkeypatch, m, pr=_pr(base="c" * 40))
    event = {"workflow_run": {"id": 700, "path": m.DEEP_WORKFLOW_PATH}}
    with pytest.raises(m.BridgeError, match="head/base advanced"):
        m.bridge_event(event, repo="owner/repo", token="token")


def test_duplicate_certification_markers_fail_closed(monkeypatch):
    m = _load_helper()
    marker = _marker(m)
    _install_api(monkeypatch, m, jobs=[marker, dict(marker)])
    event = {"workflow_run": {"id": 700, "path": m.DEEP_WORKFLOW_PATH}}
    with pytest.raises(m.BridgeError, match="exactly one"):
        m.bridge_event(event, repo="owner/repo", token="token")


def test_marker_wrong_run_provenance_fails_closed(monkeypatch):
    m = _load_helper()
    marker = _marker(m)
    marker["run_id"] = 999
    _install_api(monkeypatch, m, jobs=[marker])
    event = {"workflow_run": {"id": 700, "path": m.DEEP_WORKFLOW_PATH}}
    with pytest.raises(m.BridgeError, match="provenance/outcome invalid"):
        m.bridge_event(event, repo="owner/repo", token="token")


def test_dispatch_from_non_main_branch_fails_closed(monkeypatch):
    m = _load_helper()
    run = _run(m)
    run["head_branch"] = "feature/evil"
    _install_api(monkeypatch, m, run=run)
    event = {"workflow_run": {"id": 700, "path": m.DEEP_WORKFLOW_PATH}}
    with pytest.raises(m.BridgeError, match="not bound to main"):
        m.bridge_event(event, repo="owner/repo", token="token")
