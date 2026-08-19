#!/usr/bin/env python3
"""PR-B3b pr-deep-policy machine-readable decision helper.

Invoked from .github/workflows/pr-deep-policy.yml to produce ONE
canonical policy decision JSON document. The publish step consumes
ONLY this file; it MUST NOT reconstruct the decision from selector
state.

CLI:

    pr_b3b_decide_policy.py \\
        <selector.json> <expected_head_sha> <expected_base_sha> <merge_base_sha> \\
        <selector_rc> <repo> <github_token>

Output:
    machine-readable JSON to stdout, with fields:

      selector_state       canonical state from the trusted selector
      selector_rc          exit code captured from the trusted selector
      policy_state         success | pending | failure
      reason               short machine-readable reason string
      head_sha             exact expected PR HEAD SHA
      base_sha             current PR BASE SHA, used for certification
                           binding (status description comparison)
      merge_base_sha       selector comparison base (may differ from
                           base_sha when main advances without a rebase)
      decision_timestamp   ISO-8601 UTC timestamp of the decision

Identity contract (DEFECT 3 — separation of PR_BASE vs MERGE_BASE):

  - selector.head_sha MUST equal expected_head_sha exactly.
  - selector.base_sha MUST equal merge_base_sha exactly (NOT the
    current PR BASE SHA). The trusted selector is invoked with
    --base=MERGE_BASE, so its base_sha is MERGE_BASE.
  - selector.schema_version MUST equal 1.

State/rc consistency (DEFECT 2 — enforced BEFORE any policy decision):

  - selector.state MUST be one of:
      NO_ELIGIBLE_BACKEND_CHANGE / SELECTED          -> rc 0
      ESCALATION_REQUIRED                            -> rc 2
      ERROR                                          -> rc 3
  - selector_rc MUST match the table exactly.
  - unknown state OR mismatched rc -> policy_state = failure.

Latest-status-wins (DEFECT 5):

  - The LATEST status for the exact HEAD is authoritative.
  - An older matching success for the same HEAD but a different
    base SHA is STALE and MUST NOT count.
  - An older success MUST NOT override a newer pending / failure.

A previous PR-DEEP certification is accepted only when ALL hold:
   - the LATEST relevant status for the exact HEAD is a success
   - context == retail/pr-deep
   - state   == success
   - sha     == exact current PR HEAD
   - description EXACTLY == "PASS base=<40-char expected_base_sha>"
   - the latest would be selected by sorting on
     `updated_at` / `created_at` (descending).
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PR_DEEP_CONTEXT = "retail/pr-deep"

SCHEMA_VERSION_SUPPORTED = 1
SELECTOR_RC_FOR_STATE = {
    "NO_ELIGIBLE_BACKEND_CHANGE": 0,
    "SELECTED": 0,
    "ESCALATION_REQUIRED": 2,
    "ERROR": 3,
}


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


def _status_timestamp(s: dict) -> str:
    """Return the most authoritative timestamp string for a status.
    GitHub returns ``updated_at`` (preferred) or ``created_at`` (fallback).
    Sorting on these strings is stable because both are ISO-8601.
    """
    return s.get("updated_at") or s.get("created_at") or ""


def _latest_status_for(statuses: list, head_sha: str, base_sha: str) -> dict | None:
    """Pick the LATEST status matching the exact head_sha + base_sha.

    Deterministic: we sort by ``updated_at`` / ``created_at`` (descending)
    and return the first one whose context, state, sha, and description
    match the current base. The raw API list is already in reverse
    chronological order, but we do NOT rely on that ordering; we sort
    ourselves to be deterministic.
    """
    expected_desc = f"PASS base={base_sha}"
    candidates = [
        s for s in statuses
        if s.get("context") == PR_DEEP_CONTEXT
        and s.get("sha") == head_sha
        and s.get("description") == expected_desc
    ]
    if not candidates:
        return None
    candidates.sort(key=_status_timestamp, reverse=True)
    return candidates[0]


def _latest_any_status_for(statuses: list, head_sha: str) -> dict | None:
    """Pick the LATEST status for the exact head_sha (any state).
    Used to ensure a newer pending / failure overrides an older
    success."""
    candidates = [
        s for s in statuses
        if s.get("context") == PR_DEEP_CONTEXT
        and s.get("sha") == head_sha
    ]
    if not candidates:
        return None
    candidates.sort(key=_status_timestamp, reverse=True)
    return candidates[0]


def _build_decision(
    *,
    selector_state,
    selector_rc,
    policy_state,
    expected_head,
    expected_base,
    merge_base,
    reason: str,
) -> dict:
    return {
        "selector_state": selector_state,
        "selector_rc": selector_rc,
        "policy_state": policy_state,
        "reason": reason,
        "head_sha": expected_head,
        "base_sha": expected_base,
        "merge_base_sha": merge_base,
        "decision_timestamp": (
            datetime.datetime.now(datetime.timezone.utc).isoformat()
        ),
    }


def _emit_decision(decision: dict) -> int:
    json.dump(decision, sys.stdout)
    sys.stdout.write("\n")
    return 0


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

    # ---------- 1. Load selector JSON ----------
    try:
        payload = _load_selector(payload_path)
    except ValueError as exc:
        return _emit_decision(_build_decision(
            selector_state=None,
            selector_rc=selector_rc,
            policy_state="failure",
            expected_head=expected_head,
            expected_base=expected_base,
            merge_base=merge_base,
            reason=f"selector JSON malformed: {exc}",
        ))

    # ---------- 2. schema_version ----------
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION_SUPPORTED:
        return _emit_decision(_build_decision(
            selector_state=payload.get("state"),
            selector_rc=selector_rc,
            policy_state="failure",
            expected_head=expected_head,
            expected_base=expected_base,
            merge_base=merge_base,
            reason=(
                f"selector schema_version {schema_version!r} is not "
                f"supported (expected {SCHEMA_VERSION_SUPPORTED})"
            ),
        ))

    # ---------- 3. Identity: head matches PR HEAD ----------
    actual_head = payload.get("head_sha")
    if not _check_sha(actual_head, "selector head_sha"):
        return _emit_decision(_build_decision(
            selector_state=payload.get("state"),
            selector_rc=selector_rc,
            policy_state="failure",
            expected_head=expected_head,
            expected_base=expected_base,
            merge_base=merge_base,
            reason="selector head_sha is not a 40-char hex SHA",
        ))
    if actual_head != expected_head:
        return _emit_decision(_build_decision(
            selector_state=payload.get("state"),
            selector_rc=selector_rc,
            policy_state="failure",
            expected_head=expected_head,
            expected_base=expected_base,
            merge_base=merge_base,
            reason=(
                f"selector head_sha {actual_head!r} != "
                f"expected {expected_head!r}"
            ),
        ))

    # ---------- 4. Identity: base matches MERGE_BASE ----------
    actual_base = payload.get("base_sha")
    if not _check_sha(actual_base, "selector base_sha"):
        return _emit_decision(_build_decision(
            selector_state=payload.get("state"),
            selector_rc=selector_rc,
            policy_state="failure",
            expected_head=expected_head,
            expected_base=expected_base,
            merge_base=merge_base,
            reason="selector base_sha is not a 40-char hex SHA",
        ))
    if actual_base != merge_base:
        return _emit_decision(_build_decision(
            selector_state=payload.get("state"),
            selector_rc=selector_rc,
            policy_state="failure",
            expected_head=expected_head,
            expected_base=expected_base,
            merge_base=merge_base,
            reason=(
                f"selector base_sha {actual_base!r} != "
                f"MERGE_BASE {merge_base!r} (selector was invoked with "
                f"--base=MERGE_BASE, not --base=PR_BASE_SHA)"
            ),
        ))

    state = payload.get("state")

    # ---------- 5. State/rc consistency (DEFECT 2) ----------
    if state not in SELECTOR_RC_FOR_STATE:
        return _emit_decision(_build_decision(
            selector_state=state,
            selector_rc=selector_rc,
            policy_state="failure",
            expected_head=expected_head,
            expected_base=expected_base,
            merge_base=merge_base,
            reason=f"selector state {state!r} is not a known canonical state",
        ))
    expected_rc = SELECTOR_RC_FOR_STATE[state]
    if selector_rc != expected_rc:
        return _emit_decision(_build_decision(
            selector_state=state,
            selector_rc=selector_rc,
            policy_state="failure",
            expected_head=expected_head,
            expected_base=expected_base,
            merge_base=merge_base,
            reason=(
                f"selector state {state!r} is inconsistent with "
                f"selector_rc {selector_rc} (expected {expected_rc})"
            ),
        ))

    # ---------- 6. Policy table (DEFECT 5) ----------
    if state == "NO_ELIGIBLE_BACKEND_CHANGE" or state == "SELECTED":
        return _emit_decision(_build_decision(
            selector_state=state,
            selector_rc=selector_rc,
            policy_state="success",
            expected_head=expected_head,
            expected_base=expected_base,
            merge_base=merge_base,
            reason=f"selector state {state}; PR-DEEP not required",
        ))

    if state == "ESCALATION_REQUIRED":
        statuses = _fetch_existing_statuses(repo, expected_head, token)
        # Deterministic: the LATEST status for the exact HEAD is
        # authoritative. An older matching success for the same HEAD
        # but a different base SHA is STALE and does NOT count; an
        # older success for the same base must NOT override a newer
        # pending / failure.
        latest = _latest_any_status_for(statuses, expected_head)
        if latest is not None:
            latest_state = latest.get("state")
            if latest_state in ("pending", "failure"):
                return _emit_decision(_build_decision(
                    selector_state=state,
                    selector_rc=selector_rc,
                    policy_state="pending",
                    expected_head=expected_head,
                    expected_base=expected_base,
                    merge_base=merge_base,
                    reason=(
                        f"latest retail/pr-deep status for head "
                        f"{expected_head[:12]} is {latest_state!r}; "
                        "an older success cannot override it"
                    ),
                ))
        # The latest status is a success (or no status exists).
        # Accept it ONLY if it matches the current head + current base
        # (PASS base=<current_base>).
        matching = _latest_status_for(
            statuses, expected_head, expected_base,
        )
        if matching is not None:
            return _emit_decision(_build_decision(
                selector_state=state,
                selector_rc=selector_rc,
                policy_state="success",
                expected_head=expected_head,
                expected_base=expected_base,
                merge_base=merge_base,
                reason=(
                    "PR-DEEP already certified for exact head "
                    f"{expected_head[:12]} and exact base "
                    f"{expected_base[:12]}"
                ),
            ))
        return _emit_decision(_build_decision(
            selector_state=state,
            selector_rc=selector_rc,
            policy_state="pending",
            expected_head=expected_head,
            expected_base=expected_base,
            merge_base=merge_base,
            reason=(
                "PR-DEEP certification required for exact head "
                f"{expected_head[:12]} and exact base {expected_base[:12]}"
            ),
        ))

    # Should be unreachable (state/rc consistency above covers all
    # known canonical states). Treat as failure.
    return _emit_decision(_build_decision(
        selector_state=state,
        selector_rc=selector_rc,
        policy_state="failure",
        expected_head=expected_head,
        expected_base=expected_base,
        merge_base=merge_base,
        reason=f"selector state {state!r} is not a known canonical state",
    ))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))