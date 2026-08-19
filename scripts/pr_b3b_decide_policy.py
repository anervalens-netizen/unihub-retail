#!/usr/bin/env python3
"""PR-B3b pr-deep-policy machine-readable decision helper.

Invoked from .github/workflows/pr-deep-policy.yml to produce ONE
canonical policy decision JSON document. The publish step consumes
ONLY this file; it MUST NOT reconstruct the decision from selector
state.

CLI:

    pr_b3b_decide_policy.py \\
        <selector.json> <expected_head_sha> <expected_base_sha> \\
        <merge_base_sha> <selector_rc> <repo> <github_token>

Output:
    machine-readable JSON to stdout, with fields:

      selector_state       canonical state from the trusted selector
      selector_rc          exit code captured from the trusted selector
      policy_state         success | pending | failure
      reason               short machine-readable reason string
      head_sha             exact expected PR HEAD SHA
      base_sha             exact expected PR BASE SHA
      merge_base_sha       exact computed MERGE_BASE
      decision_timestamp   ISO-8601 UTC timestamp of the decision

Policy table:

  NO_ELIGIBLE_BACKEND_CHANGE | SELECTED                 -> success
  ESCALATION_REQUIRED + valid current-base PR-DEEP success -> success
  ESCALATION_REQUIRED without valid cert                  -> pending
  ERROR / identity mismatch / malformed result            -> failure

A previous PR-DEEP certification is accepted only when ALL hold:
   - context == retail/pr-deep
   - state   == success
   - sha     == exact current PR HEAD
   - description EXACTLY == "PASS base=<40-char expected_base_sha>"

A success for the same HEAD but a different (older) base SHA is
STALE and MUST NOT count. Base advancement invalidates previous
PR-DEEP certification even if HEAD did not move.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PR_DEEP_CONTEXT = "retail/pr-deep"


def _emit_error(msg: str) -> None:
    sys.stderr.write(f"::error::{msg}\n")


def _check_sha(value, name: str) -> bool:
    if not isinstance(value, str) or not SHA_RE.match(value):
        _emit_error(f"{name} is not a 40-char lowercase hex SHA: {value!r}")
        return False
    return True


def _load_selector(payload_path: str) -> dict:
    try:
        with open(payload_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot parse selector JSON: {exc}")
    if not isinstance(data, dict):
        raise ValueError("selector JSON root must be an object")
    return data


def _fetch_existing_statuses(repo: str, sha: str, token: str) -> list:
    """Fetch existing statuses for ``sha``. Returns an empty list on
    network / parse / auth errors so the caller can treat the run
    as "no matching certification" rather than crashing.
    """
    url = f"https://api.github.com/repos/{repo}/commits/{sha}/statuses"
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "unihub-retail-pr-deep-policy",
        },
    )
    try:
        with urlopen(req, timeout=15) as resp:
            body = resp.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        sys.stderr.write(f"::warning::status fetch failed: {exc}\n")
        return []
    try:
        statuses = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(statuses, list):
        return []
    return statuses


def _find_pr_deep_success(statuses: list, head_sha: str, base_sha: str) -> bool:
    """Return True iff a same-head, current-base, success status exists.

    The status description must EXACTLY equal
    ``"PASS base=<40-char expected_base_sha>"`` so an older cert for
    the same HEAD but a different base SHA is rejected.
    """
    expected_desc = f"PASS base={base_sha}"
    for s in statuses:
        if s.get("context") != PR_DEEP_CONTEXT:
            continue
        if s.get("state") != "success":
            continue
        if s.get("sha") != head_sha:
            continue
        if s.get("description") != expected_desc:
            continue
        return True
    return False


def main(argv: list) -> int:
    if len(argv) != 8:
        _emit_error(
            "usage: pr_b3b_decide_policy.py <selector.json> "
            "<expected_head_sha> <expected_base_sha> <merge_base_sha> "
            "<selector_rc> <repo> <github_token>"
        )
        return 1
    payload_path = argv[1]
    expected_head = argv[2]
    expected_base = argv[3]
    merge_base = argv[4]
    rc_arg = argv[5]
    repo = argv[6]
    token = argv[7]

    if not _check_sha(expected_head, "expected_head_sha"):
        return 1
    if not _check_sha(expected_base, "expected_base_sha"):
        return 1
    if not _check_sha(merge_base, "merge_base_sha"):
        return 1
    try:
        selector_rc = int(rc_arg)
    except (TypeError, ValueError):
        _emit_error(f"selector_rc is not an integer: {rc_arg!r}")
        return 1

    decision = {
        "selector_state": None,
        "selector_rc": selector_rc,
        "policy_state": "failure",
        "reason": "uninitialized",
        "head_sha": expected_head,
        "base_sha": expected_base,
        "merge_base_sha": merge_base,
        "decision_timestamp": (
            datetime.datetime.now(datetime.timezone.utc).isoformat()
        ),
    }

    try:
        payload = _load_selector(payload_path)
    except ValueError as exc:
        decision["reason"] = f"selector JSON malformed: {exc}"
        json.dump(decision, sys.stdout)
        sys.stdout.write("\n")
        return 0

    # Identity checks
    if payload.get("head_sha") != expected_head:
        decision["reason"] = (
            f"selector head_sha {payload.get('head_sha')!r} "
            f"!= expected {expected_head!r}"
        )
        json.dump(decision, sys.stdout)
        sys.stdout.write("\n")
        return 0
    if payload.get("base_sha") != expected_base:
        decision["reason"] = (
            f"selector base_sha {payload.get('base_sha')!r} "
            f"!= expected {expected_base!r}"
        )
        json.dump(decision, sys.stdout)
        sys.stdout.write("\n")
        return 0

    state = payload.get("state")
    decision["selector_state"] = state

    if state == "NO_ELIGIBLE_BACKEND_CHANGE" or state == "SELECTED":
        decision["policy_state"] = "success"
        decision["reason"] = f"selector state {state}; PR-DEEP not required"
        json.dump(decision, sys.stdout)
        sys.stdout.write("\n")
        return 0

    if state == "ESCALATION_REQUIRED":
        statuses = _fetch_existing_statuses(repo, expected_head, token)
        if _find_pr_deep_success(statuses, expected_head, expected_base):
            decision["policy_state"] = "success"
            decision["reason"] = (
                "PR-DEEP already certified for exact head "
                f"{expected_head[:12]} and exact base {expected_base[:12]}"
            )
            json.dump(decision, sys.stdout)
            sys.stdout.write("\n")
            return 0
        decision["policy_state"] = "pending"
        decision["reason"] = (
            "PR-DEEP certification required for exact head "
            f"{expected_head[:12]} and exact base {expected_base[:12]}"
        )
        json.dump(decision, sys.stdout)
        sys.stdout.write("\n")
        return 0

    decision["policy_state"] = "failure"
    decision["reason"] = f"selector state {state!r} is not a known canonical state"
    json.dump(decision, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))