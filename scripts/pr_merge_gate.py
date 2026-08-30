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
GITHUB_ACTIONS_APP = "github-actions"
PAGE_SIZE = 100
MAX_PR_FILES = 3000


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


def _required_check_state(
    checks: list[dict[str, Any]], *, expected_name: str, head_sha: str
) -> tuple[str, str]:
    latest = _latest([c for c in checks if c.get("name") == expected_name])
    if latest is None:
        return "pending", f"missing-check:{expected_name}"
    if latest.get("head_sha") != head_sha:
        return "failure", f"stale-check-head:{expected_name}"
    app = latest.get("app")
    if not isinstance(app, dict) or app.get("slug") != GITHUB_ACTIONS_APP:
        return "failure", f"untrusted-check-app:{expected_name}"
    if latest.get("status") != "completed":
        return "pending", f"check-pending:{expected_name}"
    if latest.get("conclusion") == "success":
        return "success", f"check-success:{expected_name}"
    return "failure", f"check-{latest.get('conclusion') or 'unknown'}:{expected_name}"


def _latest_status_for(
    statuses: list[dict[str, Any]], *, context: str, head_sha: str
) -> dict[str, Any] | None:
    candidates = []
    for status in statuses:
        if not isinstance(status, dict):
            return None
        if status.get("context") != context:
            continue
        if status.get("sha") is not None and status.get("sha") != head_sha:
            return None
        candidates.append(status)
    return _latest(candidates)


def _policy_state(
    statuses: list[dict[str, Any]], *, head_sha: str, base_sha: str
) -> tuple[str, str]:
    latest = _latest_status_for(statuses, context=POLICY_CONTEXT, head_sha=head_sha)
    if latest is None:
        return "pending", "missing-pr-deep-policy"
    state = latest.get("state")
    description = latest.get("description")
    if state == "pending":
        return "pending", "pr-deep-policy-pending"
    if state in {"failure", "error"}:
        return "failure", f"pr-deep-policy-{state}"
    if state != "success" or not isinstance(description, str):
        return "failure", "malformed-pr-deep-policy"

    pass_desc = f"PASS base={base_sha}"
    no_deep = f"PR-DEEP not required head={head_sha[:12]} base={base_sha[:12]}"
    if description == no_deep:
        return "success", "pr-deep-not-required"
    if description != pass_desc:
        if description.startswith("PASS base=") or description.startswith(
            "PR-DEEP not required head="
        ):
            return "pending", "stale-pr-deep-policy-base"
        return "failure", "malformed-pr-deep-policy-success"

    deep = _latest_status_for(statuses, context=DEEP_CONTEXT, head_sha=head_sha)
    if deep is None:
        return "pending", "missing-pr-deep"
    if deep.get("state") == "pending":
        return "pending", "pr-deep-pending"
    if deep.get("state") in {"failure", "error"}:
        return "failure", f"pr-deep-{deep.get('state')}"
    if deep.get("state") != "success":
        return "failure", "malformed-pr-deep"
    if deep.get("description") != pass_desc:
        desc = deep.get("description")
        if isinstance(desc, str) and desc.startswith("PASS base="):
            return "pending", "stale-pr-deep-base"
        return "failure", "malformed-pr-deep-success"
    return "success", "pr-deep-passed"


def decide(
    *,
    pr_number: int,
    head_sha: str,
    base_sha: str,
    docs_only: bool,
    checks: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
) -> Decision:
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number < 1:
        raise GateError("invalid PR number")
    if not _valid_sha(head_sha) or not _valid_sha(base_sha):
        raise GateError("invalid head/base SHA")
    mode = "docs-only" if docs_only else "runtime"
    required = [DOCS_CHECK] if docs_only else [DOCS_CHECK, PR_FAST_CHECK, HIGH_RISK_CHECK]
    for name in required:
        state, reason = _required_check_state(checks, expected_name=name, head_sha=head_sha)
        if state != "success":
            return Decision(state, reason, mode, head_sha, base_sha, pr_number)
    if docs_only:
        return Decision("success", "docs-authority-passed", mode, head_sha, base_sha, pr_number)
    state, reason = _policy_state(statuses, head_sha=head_sha, base_sha=base_sha)
    return Decision(state, reason, mode, head_sha, base_sha, pr_number)


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


def _changed_files(repo: str, token: str, number: int) -> list[str]:
    files = []
    for page in range(1, 31):
        query = urllib.parse.urlencode({"per_page": PAGE_SIZE, "page": page})
        data = _api_json(_repo_url(repo, f"/pulls/{number}/files?{query}"), token)
        if not isinstance(data, list) or any(not isinstance(x, dict) for x in data):
            raise GateError("PR files response malformed")
        for item in data:
            path = item.get("filename")
            if not isinstance(path, str) or not path:
                raise GateError("invalid PR filename")
            files.append(path)
            if len(files) >= MAX_PR_FILES:
                raise GateError("3000-file completeness ceiling reached")
        if len(data) < PAGE_SIZE:
            break
    if not files:
        raise GateError("open PR has no changed files")
    return files


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
    decision = decide(
        pr_number=number,
        head_sha=head_sha,
        base_sha=base_sha,
        docs_only=all(p.endswith(".md") or p.startswith("docs/") for p in files),
        checks=_check_runs(repo, token, head_sha),
        statuses=_statuses(repo, token, head_sha),
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
