#!/usr/bin/env python3
"""Trusted exact-HEAD/base aggregate merge-gate evaluator."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
GATE_CONTEXT = "retail/pr-merge-gate"
POLICY_CONTEXT = "retail/pr-deep-policy"
DEEP_CONTEXT = "retail/pr-deep"
DOCS_CHECK = "Validate release authority and docs"
PR_FAST_CHECK = "pr-fast"
HIGH_RISK_CHECK = "Validate high-risk PR governance"
PAGE_SIZE = 100
MAX_WORKFLOW_RUN_PAGES = 100
MAX_WORKFLOW_JOB_PAGES = 100
MAX_PR_FILES = 3000

# Required checks are accepted only from the immutable workflow files below.
# A display name/context is deliberately insufficient evidence: the Actions
# run and job metadata must bind the result to this repository, workflow path,
# event, PR, and exact PR identities.
DOCS_WORKFLOW_PATH = ".github/workflows/docs-contract.yml"
PR_FAST_WORKFLOW_PATH = ".github/workflows/ci.yml"
HIGH_RISK_WORKFLOW_PATH = ".github/workflows/high-risk-governance.yml"
POLICY_WORKFLOW_PATH = ".github/workflows/pr-deep-policy.yml"
DEEP_WORKFLOW_PATH = ".github/workflows/pr-deep.yml"
POLICY_MARKER_PREFIX = "pr-deep-policy marker"
DEEP_MARKER_PREFIX = "pr-deep marker"

_REQUIRED_WORKFLOWS = {
    DOCS_CHECK: (DOCS_WORKFLOW_PATH, "pull_request"),
    PR_FAST_CHECK: (PR_FAST_WORKFLOW_PATH, "pull_request"),
    HIGH_RISK_CHECK: (HIGH_RISK_WORKFLOW_PATH, "pull_request_target"),
}


@dataclass(frozen=True)
class WorkflowEvidence:
    run: dict[str, Any]
    jobs: list[dict[str, Any]]


class GateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Decision:
    state: str
    reason: str
    mode: str
    head_sha: str
    base_sha: str
    pr_number: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "state": self.state,
            "reason": self.reason,
            "mode": self.mode,
            "head_sha": self.head_sha,
            "base_sha": self.base_sha,
            "pr_number": self.pr_number,
        }


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def _parse_ts(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(dt.timezone.utc) if parsed.tzinfo else None


def _sort_key(item: dict[str, Any]) -> tuple[dt.datetime, dt.datetime, int] | None:
    primary = (
        _parse_ts(item.get("updated_at"))
        or _parse_ts(item.get("completed_at"))
        or _parse_ts(item.get("created_at"))
        or _parse_ts(item.get("started_at"))
    )
    secondary = (
        _parse_ts(item.get("created_at"))
        or _parse_ts(item.get("started_at"))
        or dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    )
    raw_id = item.get("id")
    if primary is None:
        return None
    if isinstance(raw_id, bool) or (raw_id is not None and not isinstance(raw_id, int)):
        return None
    return primary, secondary, raw_id if raw_id is not None else -1


def _latest(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    keyed = []
    for item in items:
        if not isinstance(item, dict):
            return None
        key = _sort_key(item)
        if key is None:
            return None
        keyed.append((key, item))
    if not keyed:
        return None
    keyed.sort(key=lambda pair: pair[0], reverse=True)
    return keyed[0][1]


def _marker_name(prefix: str, *, state: str | None, pr_number: int, head_sha: str, base_sha: str) -> str:
    if prefix == POLICY_MARKER_PREFIX:
        return f"{prefix} state={state} head={head_sha} base={base_sha}"
    return f"{prefix} pr={pr_number} head={head_sha} base={base_sha}"


def _run_repo(run: dict[str, Any], key: str) -> str | None:
    value = run.get(key)
    return value.get("full_name") if isinstance(value, dict) else None


def _valid_run_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _run_has_pr(run: dict[str, Any], pr_number: int) -> bool:
    pull_requests = run.get("pull_requests")
    if not isinstance(pull_requests, list):
        return False
    return any(
        isinstance(pr, dict)
        and pr.get("number") == pr_number
        and not isinstance(pr.get("number"), bool)
        for pr in pull_requests
    )


def _run_has_base(run: dict[str, Any], base_sha: str) -> bool:
    # The workflow-run PR association must carry the base SHA. Without it,
    # this API response cannot distinguish a same-head run from a run created
    # before the PR base advanced, so fail closed.
    explicit = run.get("base_sha")
    if explicit is not None:
        return _valid_sha(explicit) and explicit == base_sha
    pull_requests = run.get("pull_requests")
    if isinstance(pull_requests, list):
        for pr in pull_requests:
            if not isinstance(pr, dict):
                continue
            base = pr.get("base")
            if isinstance(base, dict) and _valid_sha(base.get("sha")):
                if base.get("sha") == base_sha:
                    return True
    # A workflow run without a base identity cannot prove it was created for
    # the current PR base. Fail closed rather than accepting a stale run.
    return False


def _run_matches(
    run: dict[str, Any], *, repo: str, workflow_path: str, event: str,
    pr_number: int | None, head_sha: str | None, base_sha: str | None,
    workflow_dispatch: bool = False,
) -> bool:
    if not isinstance(run, dict):
        return False
    if run.get("path") != workflow_path or run.get("event") != event:
        return False
    if _run_repo(run, "repository") != repo or _run_repo(run, "head_repository") != repo:
        return False
    if not _valid_run_id(run.get("id")) or not _valid_sha(run.get("head_sha")):
        return False
    if workflow_dispatch:
        if run.get("head_branch") != "main" or run.get("ref") != "refs/heads/main":
            return False
    elif (
        pr_number is None
        or not _run_has_pr(run, pr_number)
        or not _run_has_base(run, base_sha or "")
    ):
        return False
    if head_sha is not None and run.get("head_sha") != head_sha:
        return False
    return True


def _run_provenance_valid(
    run: Any, *, repo: str, workflow_path: str, event: str,
    pr_number: int, head_sha: str, base_sha: str,
    workflow_dispatch: bool = False,
) -> bool:
    """Validate run identity again at the authority boundary.

    The API fetch filters runs, but ``decide`` also accepts injected evidence
    from callers and must never trust the dictionary key as provenance.
    """
    if not _run_matches(
        run,
        repo=repo,
        workflow_path=workflow_path,
        event=event,
        pr_number=None if workflow_dispatch else pr_number,
        head_sha=None if workflow_dispatch else head_sha,
        base_sha=base_sha if workflow_dispatch else base_sha,
        workflow_dispatch=workflow_dispatch,
    ):
        return False
    pull_requests = run.get("pull_requests")
    if not isinstance(pull_requests, list):
        return False
    if workflow_dispatch:
        # Dispatch runs normally have no PR association. If GitHub provides
        # one, it must not contradict the exact certification inputs.
        for pr in pull_requests:
            if not isinstance(pr, dict):
                return False
            if pr.get("number") != pr_number or isinstance(pr.get("number"), bool):
                return False
            base = pr.get("base")
            if not isinstance(base, dict) or not _valid_sha(base.get("sha")) or base.get("sha") != base_sha:
                return False
            associated_head = pr.get("head", {}).get("sha") if isinstance(pr.get("head"), dict) else None
            if associated_head is not None and associated_head != head_sha:
                return False
    else:
        # Every PR association returned for a pull_request run must be
        # structurally complete; accepting one good association beside a
        # malformed one would make provenance dependent on API ordering.
        matching = []
        for pr in pull_requests:
            if not isinstance(pr, dict) or not isinstance(pr.get("number"), int) or isinstance(pr.get("number"), bool):
                return False
            pr_base = pr.get("base")
            if not isinstance(pr_base, dict) or not _valid_sha(pr_base.get("sha")):
                return False
            if pr.get("number") == pr_number:
                matching.append(pr)
        if len(matching) != 1 or matching[0]["base"]["sha"] != base_sha:
            return False
    explicit_base = run.get("base_sha")
    if explicit_base is not None and (not _valid_sha(explicit_base) or explicit_base != base_sha):
        return False
    return True


def _job_provenance_valid(job: Any, *, run: dict[str, Any]) -> bool:
    if not isinstance(job, dict):
        return False
    run_id = run.get("id")
    return (
        _valid_run_id(run_id)
        and _valid_run_id(job.get("run_id"))
        and job.get("run_id") == run_id
        and _valid_sha(run.get("head_sha"))
        and _valid_sha(job.get("head_sha"))
        and job.get("head_sha") == run.get("head_sha")
    )


def _workflow_job_state(
    evidence: list[WorkflowEvidence], *, job_name: str, expected_head: str,
) -> tuple[str, str]:
    if not evidence:
        return "pending", f"missing-trusted-workflow:{job_name}"
    runs = [e.run for e in evidence]
    latest_run = _latest(runs)
    if latest_run is None:
        return "failure", f"malformed-trusted-workflow:{job_name}"
    selected = next(e for e in evidence if e.run is latest_run)
    if any(not isinstance(job, dict) for job in selected.jobs):
        return "failure", f"malformed-trusted-job:{job_name}"
    jobs = [job for job in selected.jobs if job.get("name") == job_name]
    if not jobs:
        return "pending", f"missing-trusted-job:{job_name}"
    latest_job = _latest(jobs)
    if latest_job is None:
        return "failure", f"malformed-trusted-job:{job_name}"
    if not _job_provenance_valid(latest_job, run=latest_run):
        if latest_job.get("run_id") != latest_run.get("id"):
            return "failure", f"untrusted-job-run:{job_name}"
        if latest_job.get("head_sha") != expected_head:
            return "failure", f"stale-check-head:{job_name}"
        return "failure", f"malformed-trusted-job:{job_name}"
    if latest_job.get("head_sha") != expected_head:
        return "failure", f"stale-check-head:{job_name}"
    if latest_job.get("status") != "completed":
        return "pending", f"check-pending:{job_name}"
    if latest_job.get("conclusion") == "success":
        return "success", f"check-success:{job_name}"
    return "failure", f"check-{latest_job.get('conclusion') or 'unknown'}:{job_name}"


def _trusted_marker_state(
    evidence: list[WorkflowEvidence], *, prefix: str, pr_number: int,
    head_sha: str, base_sha: str,
) -> tuple[str, str]:
    """Read only an exact marker, ignoring unrelated dispatch runs.

    A workflow_dispatch listing can contain runs for many PRs. Selecting the
    newest run before matching its deterministic marker would let an unrelated
    run mask an older exact certification. Conversely, a failure is actionable
    only when the exact marker identifies this PR/head/base in that run.
    """
    if not evidence:
        return "pending", f"missing-trusted-marker:{prefix}"
    expected_names = {
        _marker_name(prefix, state=state, pr_number=pr_number, head_sha=head_sha, base_sha=base_sha)
        for state in ("success", "pending", "failure")
    }
    exact: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    malformed_exact = False
    for item in evidence:
        if not isinstance(item.run, dict) or any(not isinstance(job, dict) for job in item.jobs):
            malformed_exact = True
            continue
        matching = [job for job in item.jobs if job.get("name") in expected_names]
        if matching:
            if _sort_key(item.run) is None or any(
                not _job_provenance_valid(job, run=item.run) for job in matching
            ):
                malformed_exact = True
            else:
                exact.append((item.run, matching))
    if not exact:
        if malformed_exact:
            return "failure", f"malformed-trusted-workflow:{prefix}"
        return "pending", f"missing-trusted-marker:{prefix}"
    exact.sort(
        key=lambda item: _sort_key(item[0]) or (
            dt.datetime.min.replace(tzinfo=dt.timezone.utc),
            dt.datetime.min.replace(tzinfo=dt.timezone.utc),
            -1,
        ),
        reverse=True,
    )
    latest_run, matching = exact[0]
    if len(matching) > 1:
        return "failure", f"ambiguous-trusted-marker:{prefix}"
    marker = matching[0]
    if not _job_provenance_valid(marker, run=latest_run):
        if marker.get("run_id") != latest_run.get("id"):
            return "failure", f"untrusted-marker-run:{prefix}"
        return "failure", f"malformed-trusted-marker:{prefix}"
    if marker.get("status") != "completed":
        return "pending", f"marker-pending:{prefix}"
    if marker.get("conclusion") != "success":
        return "failure", f"marker-{marker.get('conclusion') or 'unknown'}:{prefix}"
    name = marker["name"]
    if prefix == POLICY_MARKER_PREFIX:
        state = next(state for state in ("success", "pending", "failure") if f" state={state} " in name)
        return state, f"trusted-{prefix}-{state}"
    return "success", f"trusted-{prefix}-passed"


def _trusted_policy_state(
    evidence: list[WorkflowEvidence], *, pr_number: int, head_sha: str, base_sha: str
) -> tuple[str, str]:
    return _trusted_marker_state(
        evidence,
        prefix=POLICY_MARKER_PREFIX,
        pr_number=pr_number,
        head_sha=head_sha,
        base_sha=base_sha,
    )


def _validated_workflow_evidence(
    evidence: Any, *, repo: str, workflow_path: str, event: str,
    pr_number: int, head_sha: str, base_sha: str,
    workflow_dispatch: bool = False,
) -> tuple[list[WorkflowEvidence], str | None]:
    """Revalidate caller-supplied evidence independently of its map key."""
    if evidence is None:
        return [], None
    if not isinstance(evidence, list):
        return [], f"malformed-trusted-workflow:{workflow_path}"
    for item in evidence:
        if not isinstance(item, WorkflowEvidence):
            return [], f"malformed-trusted-workflow:{workflow_path}"
        if not _run_provenance_valid(
            item.run,
            repo=repo,
            workflow_path=workflow_path,
            event=event,
            pr_number=pr_number,
            head_sha=head_sha,
            base_sha=base_sha,
            workflow_dispatch=workflow_dispatch,
        ):
            return [], f"malformed-trusted-workflow:{workflow_path}"
        if any(not isinstance(job, dict) for job in item.jobs):
            return [], f"malformed-trusted-job:{workflow_path}"
    return evidence, None


def decide(
    *,
    pr_number: int,
    head_sha: str,
    base_sha: str,
    docs_only: bool,
    checks: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
    workflow_evidence: dict[str, list[WorkflowEvidence]] | None = None,
    repo: str | None = None,
) -> Decision:
    """Evaluate only Actions run/job evidence.

    ``checks`` and ``statuses`` are retained as visibility inputs for callers
    and compatibility with the status publisher, but are intentionally never
    consulted for authority.  Omitting trusted evidence therefore fails
    closed as pending rather than allowing a candidate-controlled check or
    status to certify the PR.
    """
    del checks, statuses
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number < 1:
        raise GateError("invalid PR number")
    if not _valid_sha(head_sha) or not _valid_sha(base_sha):
        raise GateError("invalid head/base SHA")
    mode = "docs-only" if docs_only else "runtime"
    if not isinstance(repo, str) or not repo:
        return Decision("failure", "missing-trusted-repository", mode, head_sha, base_sha, pr_number)
    evidence = workflow_evidence if isinstance(workflow_evidence, dict) else {}
    required = [DOCS_CHECK] if docs_only else [DOCS_CHECK, PR_FAST_CHECK, HIGH_RISK_CHECK]
    validated: dict[str, list[WorkflowEvidence]] = {}
    for name in required:
        path, event = _REQUIRED_WORKFLOWS[name]
        trusted, error = _validated_workflow_evidence(
            evidence.get(path), repo=repo, workflow_path=path, event=event,
            pr_number=pr_number, head_sha=head_sha, base_sha=base_sha,
        )
        if error:
            return Decision("failure", error, mode, head_sha, base_sha, pr_number)
        validated[path] = trusted
        state, reason = _workflow_job_state(
            trusted, job_name=name, expected_head=head_sha
        )
        if state != "success":
            return Decision(state, reason, mode, head_sha, base_sha, pr_number)
    if docs_only:
        return Decision("success", "docs-authority-passed", mode, head_sha, base_sha, pr_number)

    policy_evidence, error = _validated_workflow_evidence(
        evidence.get(POLICY_WORKFLOW_PATH), repo=repo,
        workflow_path=POLICY_WORKFLOW_PATH, event="pull_request_target",
        pr_number=pr_number, head_sha=head_sha, base_sha=base_sha,
    )
    if error:
        return Decision("failure", error, mode, head_sha, base_sha, pr_number)
    state, reason = _trusted_policy_state(
        policy_evidence,
        pr_number=pr_number,
        head_sha=head_sha,
        base_sha=base_sha,
    )
    if state == "success":
        return Decision("success", "pr-deep-not-required", mode, head_sha, base_sha, pr_number)
    if state == "failure":
        return Decision(state, reason, mode, head_sha, base_sha, pr_number)

    deep_evidence, error = _validated_workflow_evidence(
        evidence.get(DEEP_WORKFLOW_PATH), repo=repo,
        workflow_path=DEEP_WORKFLOW_PATH, event="workflow_dispatch",
        pr_number=pr_number, head_sha=head_sha, base_sha=base_sha,
        workflow_dispatch=True,
    )
    if error:
        return Decision("failure", error, mode, head_sha, base_sha, pr_number)
    deep_state, deep_reason = _trusted_marker_state(
        deep_evidence,
        prefix=DEEP_MARKER_PREFIX,
        pr_number=pr_number,
        head_sha=head_sha,
        base_sha=base_sha,
    )
    if deep_state == "success":
        return Decision("success", "pr-deep-passed", mode, head_sha, base_sha, pr_number)
    if deep_state == "failure":
        return Decision("failure", deep_reason, mode, head_sha, base_sha, pr_number)
    return Decision("pending", "pr-deep-pending", mode, head_sha, base_sha, pr_number)


def _api_json(url: str, token: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "unihub-retail-pr-merge-gate",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise GateError(f"GitHub API read failed: {exc}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"GitHub API returned malformed JSON: {exc}") from exc


def _post_status(*, repo: str, token: str, sha: str, state: str, description: str, target_url: str) -> None:
    if not _valid_sha(sha):
        raise GateError("refusing to publish to invalid SHA")
    body = json.dumps(
        {
            "state": state,
            "context": GATE_CONTEXT,
            "description": description[:140],
            "target_url": target_url,
        }
    ).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/statuses/{sha}",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "unihub-retail-pr-merge-gate",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise GateError(f"GitHub status publish failed: {exc}") from exc


def _repo_url(repo: str, path: str) -> str:
    return f"https://api.github.com/repos/{repo}{path}"


def _fetch_pr(repo: str, token: str, number: int) -> dict[str, Any]:
    data = _api_json(_repo_url(repo, f"/pulls/{number}"), token)
    if not isinstance(data, dict):
        raise GateError("PR response is not an object")
    return data


def _list_open_prs(repo: str, token: str) -> list[dict[str, Any]]:
    out = []
    for page in range(1, 101):
        query = urllib.parse.urlencode(
            {"state": "open", "base": "main", "per_page": PAGE_SIZE, "page": page}
        )
        data = _api_json(_repo_url(repo, f"/pulls?{query}"), token)
        if not isinstance(data, list) or any(not isinstance(x, dict) for x in data):
            raise GateError("open PR response malformed")
        out.extend(data)
        if len(data) < PAGE_SIZE:
            return out
    raise GateError("open PR pagination exceeded safe bound")


def _resolve_pr_by_head(repo: str, token: str, head_sha: str) -> dict[str, Any] | None:
    matches = []
    for pr in _list_open_prs(repo, token):
        head, base = pr.get("head"), pr.get("base")
        if isinstance(head, dict) and isinstance(base, dict) and head.get("sha") == head_sha and base.get("ref") == "main":
            matches.append(pr)
    if len(matches) > 1:
        raise GateError(f"ambiguous open PR mapping for head {head_sha}")
    return matches[0] if matches else None


def _validate_current_pr(pr: dict[str, Any], *, repo: str, expected_head: str | None) -> tuple[int, str, str]:
    number, head, base = pr.get("number"), pr.get("head"), pr.get("base")
    if pr.get("state") != "open" or not isinstance(number, int) or isinstance(number, bool):
        raise GateError("PR is not a valid open PR")
    if not isinstance(head, dict) or not isinstance(base, dict) or base.get("ref") != "main":
        raise GateError("PR head/base metadata invalid")
    head_repo, base_repo = head.get("repo"), base.get("repo")
    if not isinstance(head_repo, dict) or not isinstance(base_repo, dict) or head_repo.get("full_name") != repo or base_repo.get("full_name") != repo:
        raise GateError("cross-repository PR unsupported")
    head_sha, base_sha = head.get("sha"), base.get("sha")
    if not _valid_sha(head_sha) or not _valid_sha(base_sha):
        raise GateError("PR head/base SHA malformed")
    if expected_head is not None and head_sha != expected_head:
        raise GateError("event head is stale")
    return number, head_sha, base_sha


def _changed_files(repo: str, token: str, number: int) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for page in range(1, 31):
        query = urllib.parse.urlencode({"per_page": PAGE_SIZE, "page": page})
        data = _api_json(_repo_url(repo, f"/pulls/{number}/files?{query}"), token)
        if not isinstance(data, list) or any(not isinstance(x, dict) for x in data):
            raise GateError("PR files response malformed")
        for item in data:
            path = item.get("filename")
            if not isinstance(path, str) or not path:
                raise GateError("invalid PR filename")
            if item.get("status") == "renamed" and not isinstance(item.get("previous_filename"), str):
                raise GateError("renamed PR file is missing previous_filename")
            files.append(item)
            if len(files) >= MAX_PR_FILES:
                raise GateError("3000-file completeness ceiling reached")
        if len(data) < PAGE_SIZE:
            break
    if not files:
        raise GateError("open PR has no changed files")
    return files


def _docs_path(path: str) -> bool:
    return path.endswith(".md") or path.startswith("docs/")


def _files_are_docs_only(files: list[dict[str, Any]]) -> bool:
    if not files:
        return False
    for item in files:
        path = item.get("filename")
        if not isinstance(path, str) or not _docs_path(path):
            return False
        if item.get("status") == "renamed":
            previous = item.get("previous_filename")
            if not isinstance(previous, str) or not _docs_path(previous):
                return False
    return True


def _check_runs(repo: str, token: str, head_sha: str) -> list[dict[str, Any]]:
    data = _api_json(_repo_url(repo, f"/commits/{head_sha}/check-runs?per_page=100&filter=latest"), token)
    runs = data.get("check_runs") if isinstance(data, dict) else None
    if not isinstance(runs, list) or any(not isinstance(x, dict) for x in runs):
        raise GateError("check-runs response malformed")
    return runs


def _statuses(repo: str, token: str, head_sha: str) -> list[dict[str, Any]]:
    data = _api_json(_repo_url(repo, f"/commits/{head_sha}/statuses?per_page=100"), token)
    if not isinstance(data, list) or any(not isinstance(x, dict) for x in data):
        raise GateError("statuses response malformed")
    return data


def _workflow_evidence(
    repo: str, token: str, *, workflow_path: str, event: str,
    pr_number: int | None, head_sha: str | None, base_sha: str | None,
    workflow_dispatch: bool = False,
) -> list[WorkflowEvidence]:
    workflow_id = urllib.parse.quote(workflow_path, safe="")
    runs: list[dict[str, Any]] = []
    for page in range(1, MAX_WORKFLOW_RUN_PAGES + 1):
        query = urllib.parse.urlencode({"event": event, "per_page": PAGE_SIZE, "page": page})
        data = _api_json(_repo_url(repo, f"/actions/workflows/{workflow_id}/runs?{query}"), token)
        page_runs = data.get("workflow_runs") if isinstance(data, dict) else None
        if not isinstance(page_runs, list) or any(not isinstance(run, dict) for run in page_runs):
            raise GateError(f"workflow runs response malformed: {workflow_path}")
        runs.extend(page_runs)
        if len(page_runs) < PAGE_SIZE:
            break
    else:
        raise GateError(f"workflow runs pagination exceeded safe bound: {workflow_path}")

    candidates = [
        run for run in runs
        if _run_matches(
            run,
            repo=repo,
            workflow_path=workflow_path,
            event=event,
            pr_number=pr_number,
            head_sha=None if workflow_dispatch else head_sha,
            base_sha=None if workflow_dispatch else base_sha,
            workflow_dispatch=workflow_dispatch,
        )
    ]
    evidence: list[WorkflowEvidence] = []
    for run in candidates:
        run_id = run.get("id")
        if not _valid_run_id(run_id):
            raise GateError(f"trusted workflow run id malformed: {workflow_path}")
        jobs: list[dict[str, Any]] = []
        for page in range(1, MAX_WORKFLOW_JOB_PAGES + 1):
            jobs_data = _api_json(
                _repo_url(repo, f"/actions/runs/{run_id}/jobs?per_page={PAGE_SIZE}&page={page}"),
                token,
            )
            page_jobs = jobs_data.get("jobs") if isinstance(jobs_data, dict) else None
            if not isinstance(page_jobs, list) or any(not isinstance(job, dict) for job in page_jobs):
                raise GateError(f"workflow jobs response malformed: {workflow_path}")
            jobs.extend(page_jobs)
            if len(page_jobs) < PAGE_SIZE:
                break
        else:
            raise GateError(f"workflow jobs pagination exceeded safe bound: {workflow_path}")
        evidence.append(WorkflowEvidence(run=run, jobs=jobs))
    return evidence


def _description(decision: Decision) -> str:
    prefix = "PASS" if decision.state == "success" else ("WAIT" if decision.state == "pending" else "FAIL")
    return f"{prefix} {decision.mode} {decision.reason} base={decision.base_sha[:12]}"


def _candidate_sha(event_name: str, event: dict[str, Any]) -> str | None:
    if event_name == "pull_request_target":
        pr = event.get("pull_request")
        head = pr.get("head") if isinstance(pr, dict) else None
        return head.get("sha") if isinstance(head, dict) and _valid_sha(head.get("sha")) else None
    if event_name == "workflow_run":
        run = event.get("workflow_run")
        return run.get("head_sha") if isinstance(run, dict) and _valid_sha(run.get("head_sha")) else None
    if event_name == "status" and _valid_sha(event.get("sha")):
        return event["sha"]
    return None


def _evaluate_one(*, repo: str, token: str, target_url: str, pr: dict[str, Any], expected_head: str | None) -> Decision:
    number, head_sha, base_sha = _validate_current_pr(pr, repo=repo, expected_head=expected_head)
    files = _changed_files(repo, token, number)
    docs_only = _files_are_docs_only(files)
    # These endpoints remain visibility-only. Authority is fetched from the
    # Actions workflow-run/job API below and never inferred from names alone.
    checks = _check_runs(repo, token, head_sha)
    statuses = _statuses(repo, token, head_sha)
    evidence: dict[str, list[WorkflowEvidence]] = {}
    required = [DOCS_CHECK] if docs_only else [DOCS_CHECK, PR_FAST_CHECK, HIGH_RISK_CHECK]
    for check_name in required:
        path, event = _REQUIRED_WORKFLOWS[check_name]
        evidence[path] = _workflow_evidence(
            repo, token, workflow_path=path, event=event,
            pr_number=number, head_sha=head_sha, base_sha=base_sha,
        )
    if not docs_only:
        evidence[POLICY_WORKFLOW_PATH] = _workflow_evidence(
            repo, token, workflow_path=POLICY_WORKFLOW_PATH,
            event="pull_request_target", pr_number=number,
            head_sha=head_sha, base_sha=base_sha,
        )
        policy_state, _ = _trusted_policy_state(
            evidence[POLICY_WORKFLOW_PATH], pr_number=number,
            head_sha=head_sha, base_sha=base_sha,
        )
        if policy_state == "pending":
            evidence[DEEP_WORKFLOW_PATH] = _workflow_evidence(
                repo, token, workflow_path=DEEP_WORKFLOW_PATH,
                event="workflow_dispatch", pr_number=None,
                head_sha=None, base_sha=base_sha, workflow_dispatch=True,
            )
    decision = decide(
        pr_number=number,
        head_sha=head_sha,
        base_sha=base_sha,
        docs_only=docs_only,
        checks=checks,
        statuses=statuses,
        workflow_evidence=evidence,
        repo=repo,
    )
    _post_status(repo=repo, token=token, sha=head_sha, state=decision.state, description=_description(decision), target_url=target_url)
    return decision


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    event_name = os.environ.get("GITHUB_EVENT_NAME", "").strip()
    event_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
    target_url = os.environ.get("GATE_RUN_URL", "").strip()
    if not repo or "/" not in repo or not token or not target_url:
        print("::error::required GitHub environment missing", file=sys.stderr)
        return 1
    event: dict[str, Any] = {}
    fallback_sha = None
    try:
        with open(event_path, encoding="utf-8") as handle:
            event = json.load(handle)
        if not isinstance(event, dict):
            raise GateError("event payload is not an object")
        fallback_sha = _candidate_sha(event_name, event)

        if event_name == "push":
            if event.get("ref") != "refs/heads/main":
                raise GateError("push is not main")
            results = []
            for pr in _list_open_prs(repo, token):
                try:
                    number, head_sha, base_sha = _validate_current_pr(pr, repo=repo, expected_head=None)
                except GateError:
                    continue
                _post_status(
                    repo=repo,
                    token=token,
                    sha=head_sha,
                    state="pending",
                    description=f"WAIT base-advanced recertify base={base_sha[:12]}",
                    target_url=target_url,
                )
                results.append({"pr_number": number, "head_sha": head_sha, "base_sha": base_sha})
            print(json.dumps({"mode": "main-push-invalidate", "results": results}, sort_keys=True))
            return 0

        if event_name == "pull_request_target":
            pr_event = event.get("pull_request")
            number = pr_event.get("number") if isinstance(pr_event, dict) else None
            if not isinstance(number, int) or isinstance(number, bool):
                raise GateError("event PR number invalid")
            pr = _fetch_pr(repo, token, number)
            expected_head = fallback_sha
        elif event_name == "workflow_run":
            run = event.get("workflow_run")
            if not isinstance(run, dict) or run.get("status") != "completed":
                return 0
            expected_head = run.get("head_sha")
            if not _valid_sha(expected_head):
                raise GateError("workflow_run head invalid")
            pr = _resolve_pr_by_head(repo, token, expected_head)
            if pr is None:
                print("No matching open PR; no-op.")
                return 0
        elif event_name == "status":
            if event.get("context") not in {POLICY_CONTEXT, DEEP_CONTEXT}:
                print("Unrelated status; no-op.")
                return 0
            expected_head = event.get("sha")
            if not _valid_sha(expected_head):
                raise GateError("status SHA invalid")
            pr = _resolve_pr_by_head(repo, token, expected_head)
            if pr is None:
                print("No matching open PR; no-op.")
                return 0
        else:
            raise GateError(f"unsupported event {event_name!r}")

        decision = _evaluate_one(repo=repo, token=token, target_url=target_url, pr=pr, expected_head=expected_head)
        print(json.dumps(decision.as_dict(), sort_keys=True))
        return 1 if decision.state == "failure" else 0
    except (GateError, OSError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        if fallback_sha and event_name != "push":
            try:
                _post_status(repo=repo, token=token, sha=fallback_sha, state="failure", description="FAIL merge-gate evaluator error", target_url=target_url)
            except GateError as publish_exc:
                print(f"::error::{publish_exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
