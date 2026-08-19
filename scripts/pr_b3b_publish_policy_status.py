#!/usr/bin/env python3
"""PR-B3b pr-deep-policy status publisher.

Reads the canonical policy decision JSON produced by
``pr_b3b_decide_policy.py`` and emits the GitHub commit-status
JSON body on stdout. The caller pipes that body into
``curl -d @<file>``.

The publication payload is derived ONLY from the decision JSON.
The publisher does NOT inspect the selector state directly; this
prevents the publish step from silently re-deriving or
downgrading a previously-decided policy_state.

CLI:

    pr_b3b_publish_policy_status.py \\
        <policy_decision.json> <head_sha> <base_sha> <repo> <github_token> <run_url>

Output:
    JSON object suitable for ``POST /repos/{repo}/statuses/{head_sha}``.
    Description carries the current base identity so pre-merge
    inspection is unambiguous.
"""
from __future__ import annotations

import json
import os
import sys


VALID_POLICY_STATES = {"success", "pending", "failure"}
CONTEXT = "retail/pr-deep-policy"


def _emit_error(msg: str) -> None:
    sys.stderr.write(f"::error::{msg}\n")


def main(argv: list) -> int:
    if len(argv) != 7:
        _emit_error(
            "usage: pr_b3b_publish_policy_status.py <policy_decision.json> "
            "<head_sha> <base_sha> <repo> <github_token> <run_url>"
        )
        return 1
    policy_path = argv[1]
    head_sha = argv[2]
    base_sha = argv[3]
    repo = argv[4]
    # token argv[5] intentionally unused at JSON-build time (only the
    # bash caller reads it via env to authorize curl).
    run_url = argv[6]

    try:
        with open(policy_path, "r", encoding="utf-8") as f:
            decision = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _emit_error(f"cannot parse policy decision JSON: {exc}")
        return 1
    if not isinstance(decision, dict):
        _emit_error("policy decision JSON root must be an object")
        return 1

    policy_state = decision.get("policy_state")
    if policy_state not in VALID_POLICY_STATES:
        _emit_error(
            f"policy_state {policy_state!r} is not one of "
            f"{sorted(VALID_POLICY_STATES)}"
        )
        return 1

    if decision.get("head_sha") != head_sha:
        _emit_error(
            "policy decision head_sha "
            f"{decision.get('head_sha')!r} != expected {head_sha!r}"
        )
        return 1
    if decision.get("base_sha") != base_sha:
        _emit_error(
            "policy decision base_sha "
            f"{decision.get('base_sha')!r} != expected {base_sha!r}"
        )
        return 1

    selector_state = decision.get("selector_state") or "UNKNOWN"
    short_head = head_sha[:12]
    short_base = base_sha[:12]

    if policy_state == "success":
        if selector_state in ("NO_ELIGIBLE_BACKEND_CHANGE", "SELECTED"):
            description = f"PR-DEEP not required head={short_head} base={short_base}"
        else:
            description = (
                f"PR-DEEP already certified head={short_head} base={short_base}"
            )
    elif policy_state == "pending":
        description = (
            f"PR-DEEP certification required head={short_head} base={short_base}"
        )
    else:
        description = (
            f"pr-deep-policy failure selector={selector_state} "
            f"head={short_head} base={short_base}"
        )

    body = {
        "state": policy_state,
        "description": description,
        "context": CONTEXT,
        "target_url": run_url,
    }
    json.dump(body, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))