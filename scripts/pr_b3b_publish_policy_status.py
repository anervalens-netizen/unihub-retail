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

Defense-in-depth: the publisher validates the *machine* contract
of the decision JSON (schema_version, canonical selector_state,
selector_rc consistency with selector_state, policy_state
membership, head/base identity, merge_base_sha syntax) so a
forged or malformed decision file fails the publish step before
any status is POSTed. The publisher does NOT duplicate the actual
policy decision (it consumes policy_state from the trusted
decision).

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
import re
import sys


SCHEMA_VERSION_SUPPORTED = 1
VALID_POLICY_STATES = {"success", "pending", "failure"}
VALID_SELECTOR_STATES = {
    "NO_ELIGIBLE_BACKEND_CHANGE",
    "SELECTED",
    "ESCALATION_REQUIRED",
    "ERROR",
}
SELECTOR_RC_FOR_STATE = {
    "NO_ELIGIBLE_BACKEND_CHANGE": 0,
    "SELECTED": 0,
    "ESCALATION_REQUIRED": 2,
    "ERROR": 3,
}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CONTEXT = "retail/pr-deep-policy"


def _emit_error(msg: str) -> None:
    sys.stderr.write(f"::error::{msg}\n")


def _check_sha(value, name: str) -> bool:
    if not isinstance(value, str) or not _SHA_RE.match(value):
        _emit_error(f"{name} is not a 40-char lowercase hex SHA: {value!r}")
        return False
    return True


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

    if not _check_sha(head_sha, "expected head_sha"):
        return 1
    if not _check_sha(base_sha, "expected base_sha"):
        return 1

    try:
        with open(policy_path, "r", encoding="utf-8") as f:
            decision = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _emit_error(f"cannot parse policy decision JSON: {exc}")
        return 1
    if not isinstance(decision, dict):
        _emit_error("policy decision JSON root must be an object")
        return 1

    # schema_version
    schema_version = decision.get("schema_version")
    if schema_version != SCHEMA_VERSION_SUPPORTED:
        _emit_error(
            f"policy decision schema_version {schema_version!r} is not "
            f"supported (expected {SCHEMA_VERSION_SUPPORTED})"
        )
        return 1

    # policy_state canonical
    policy_state = decision.get("policy_state")
    if policy_state not in VALID_POLICY_STATES:
        _emit_error(
            f"policy_state {policy_state!r} is not one of "
            f"{sorted(VALID_POLICY_STATES)}"
        )
        return 1

    # selector_state canonical
    selector_state = decision.get("selector_state")
    if selector_state not in VALID_SELECTOR_STATES:
        _emit_error(
            f"selector_state {selector_state!r} is not one of "
            f"{sorted(VALID_SELECTOR_STATES)}"
        )
        return 1

    # selector_rc consistent with selector_state
    selector_rc = decision.get("selector_rc")
    expected_rc = SELECTOR_RC_FOR_STATE[selector_state]
    if not isinstance(selector_rc, int) or isinstance(selector_rc, bool):
        _emit_error(
            f"selector_rc {selector_rc!r} is not an integer"
        )
        return 1
    if selector_rc != expected_rc:
        _emit_error(
            f"selector_rc {selector_rc!r} is inconsistent with "
            f"selector_state {selector_state!r} (expected {expected_rc})"
        )
        return 1

    # head_sha / base_sha identity
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

    # merge_base_sha is a 40-char lowercase hex SHA (even when empty
    # in an error state — empty is rejected here because publishers
    # are not invoked in ERROR paths)
    merge_base_sha = decision.get("merge_base_sha")
    if not _check_sha(merge_base_sha, "policy decision merge_base_sha"):
        return 1

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
