#!/usr/bin/env python3
"""Resolve a trusted PR-DEEP workflow_run completion to its candidate PR."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEEP_WORKFLOW_PATH = ".github/workflows/pr-deep.yml"
DEEP_MARKER_RE = re.compile(
    r"^pr-deep marker pr=(?P<pr>[1-9][0-9]*) "
    r"head=(?P<head>[0-9a-f]{40}) base=(?P<base>[0-9a-f]{40})$"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PAGE_SIZE = 100
MAX_JOB_PAGES = 10
DEFAULT_OUTPUT = "/tmp/pr-merge-gate-candidate-event.json"


class BridgeError(RuntimeError):
    pass


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def _repo_name(value: Any) -> str | None:
    return value.get("full_name") if isinstance(value, dict) else None


def _api_json(url: str, token: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "unihub-retail-pr-merge-gate-bridge",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise BridgeError(f"GitHub API read failed: {exc}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError(f"GitHub API returned malformed JSON: {exc}") from exc


def _repo_url(repo: str, suffix: str) -> str:
    return f"https://api.github.com/repos/{repo}{suffix}"


def _trusted_dispatch_run(run: Any, *, repo: str, expected_id: int) -> dict[str, Any]:
    if not isinstance(run, dict) or run.get("id") != expected_id:
        raise BridgeError("PR-DEEP workflow run identity mismatch")
    if run.get("path") != DEEP_WORKFLOW_PATH or run.get("event") != "workflow_dispatch":
        raise BridgeError("workflow_run is not trusted PR-DEEP dispatch")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise BridgeError("trusted PR-DEEP dispatch did not complete successfully")
    if run.get("head_branch") != "main" or not _valid_sha(run.get("head_sha")):
        raise BridgeError("trusted PR-DEEP dispatch is not bound to main")
    if _repo_name(run.get("repository")) != repo or _repo_name(run.get("head_repository")) != repo:
        raise BridgeError("trusted PR-DEEP dispatch repository mismatch")
    return run


def _workflow_jobs(repo: str, token: str, *, run_id: int) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for page in range(1, MAX_JOB_PAGES + 1):
        data = _api_json(
            _repo_url(repo, f"/actions/runs/{run_id}/jobs?per_page={PAGE_SIZE}&page={page}"),
            token,
        )
        page_jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(page_jobs, list) or any(not isinstance(job, dict) for job in page_jobs):
            raise BridgeError("PR-DEEP jobs response malformed")
        jobs.extend(page_jobs)
        if len(page_jobs) < PAGE_SIZE:
            return jobs
    raise BridgeError("PR-DEEP jobs pagination exceeded safe bound")


def _marker_identity(run: dict[str, Any], jobs: list[dict[str, Any]]) -> tuple[int, str, str]:
    matches: list[tuple[dict[str, Any], re.Match[str]]] = []
    for job in jobs:
        name = job.get("name")
        match = DEEP_MARKER_RE.fullmatch(name) if isinstance(name, str) else None
        if match is not None:
            matches.append((job, match))
    if len(matches) != 1:
        raise BridgeError("expected exactly one trusted PR-DEEP certification marker")
    job, match = matches[0]
    if (
        job.get("run_id") != run.get("id")
        or job.get("head_sha") != run.get("head_sha")
        or job.get("status") != "completed"
        or job.get("conclusion") != "success"
    ):
        raise BridgeError("trusted PR-DEEP certification marker provenance/outcome invalid")
    return int(match.group("pr")), match.group("head"), match.group("base")


def _validate_current_pr(
    pr: Any, *, repo: str, pr_number: int, head_sha: str, base_sha: str
) -> None:
    if not isinstance(pr, dict) or pr.get("number") != pr_number or pr.get("state") != "open":
        raise BridgeError("certified PR is no longer the expected open PR")
    head, base = pr.get("head"), pr.get("base")
    if not isinstance(head, dict) or not isinstance(base, dict) or base.get("ref") != "main":
        raise BridgeError("certified PR head/base metadata invalid")
    if _repo_name(head.get("repo")) != repo or _repo_name(base.get("repo")) != repo:
        raise BridgeError("certified PR repository mismatch")
    if head.get("sha") != head_sha or base.get("sha") != base_sha:
        raise BridgeError("certified PR head/base advanced after PR-DEEP")


def bridge_event(event: Any, *, repo: str, token: str) -> dict[str, str] | None:
    if not isinstance(event, dict):
        raise BridgeError("workflow_run event payload is not an object")
    event_run = event.get("workflow_run")
    if not isinstance(event_run, dict):
        raise BridgeError("workflow_run event is missing workflow_run")
    if event_run.get("path") != DEEP_WORKFLOW_PATH:
        return None
    run_id = event_run.get("id")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
        raise BridgeError("workflow_run PR-DEEP run id invalid")
    run = _api_json(_repo_url(repo, f"/actions/runs/{run_id}"), token)
    run = _trusted_dispatch_run(run, repo=repo, expected_id=run_id)
    jobs = _workflow_jobs(repo, token, run_id=run_id)
    pr_number, head_sha, base_sha = _marker_identity(run, jobs)
    pr = _api_json(_repo_url(repo, f"/pulls/{pr_number}"), token)
    _validate_current_pr(
        pr,
        repo=repo,
        pr_number=pr_number,
        head_sha=head_sha,
        base_sha=base_sha,
    )
    return {"context": "retail/pr-deep", "sha": head_sha}


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    event_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
    output_path = os.environ.get("BRIDGE_EVENT_PATH", DEFAULT_OUTPUT).strip()
    if not repo or "/" not in repo or not token or not event_path or not output_path:
        print("::error::required bridge environment missing", file=sys.stderr)
        return 1
    target = Path(output_path)
    try:
        target.unlink(missing_ok=True)
        with open(event_path, encoding="utf-8") as handle:
            event = json.load(handle)
        bridged = bridge_event(event, repo=repo, token=token)
        if bridged is None:
            print("No PR-DEEP workflow_run bridge required.")
            return 0
        target.write_text(json.dumps(bridged, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Bridged trusted PR-DEEP completion to candidate {bridged['sha']}.")
        return 0
    except (BridgeError, OSError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
