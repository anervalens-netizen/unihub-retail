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

Latest-status-wins (one-defect fix):

  "The latest retail/pr-deep status for the exact HEAD is authoritative.
  It certifies only if that latest status itself is success with
  PASS base=<current base>."

  Concretely:

  - The latest status is selected deterministically by sorting on
    ``(updated_at, created_at, id)`` (descending) — we do NOT
    assume the API list is in reverse-chronological order. The
    numeric status ``id`` is a deterministic tie-breaker when
    timestamps are equal; if a safe ordering cannot be established
    we treat the result as uncertified (pending), never success.
  - The latest status itself must satisfy ALL:
      * context == "retail/pr-deep"
      * state   == "success"
      * sha     == exact current PR HEAD
      * description EXACTLY == "PASS base=<40-char expected_base_sha>"
    If any of these fail, policy_state = pending — an older
    matching success CANNOT count.
  - No status -> pending.
  - Latest pending -> pending.
  - Latest failure -> pending.
  - Latest success for stale / other base -> pending.
  - Latest success with malformed description -> pending.

There is intentionally ONE "latest" helper (`_latest_status`); the
obsolete `_latest_status_for` and `_latest_any_status_for` were
retired to prevent two competing notions of "latest".
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
    """Fetch existing statuses for ``sha``.

    Returns an empty list on network / parse / auth errors so the
    caller can treat the run as "no matching certification" rather
    than crashing. We request ``per_page=100`` (the API max) to
    maximise the chance the returned page is the complete list —
    GitHub's List commit statuses returns statuses in reverse
    chronological order, and the first entry is the latest one.
    The policy does NOT paginate to exhaustion: if the latest
    visible ``retail/pr-deep`` status is not a current-base
    success, policy_state becomes "pending", never "success".
    """
    url = (
        f"https://api.github.com/repos/{repo}/commits/{sha}/statuses"
        "?per_page=100"
    )
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
    # Each status entry must be a JSON object. Anything else (None,
    # string, list, scalar) is API/transport corruption; do NOT let
    # it reach the sort key.
    cleaned: list = []
    for s in statuses:
        if isinstance(s, dict):
            cleaned.append(s)
    return cleaned


def _status_sort_key(s: dict) -> tuple:
    """Return the deterministic sort key for a status.

    We sort by ``(updated_at, created_at, id)`` (descending) so the
    ordering is robust to:

    - API list NOT being in reverse-chronological order
      (we do NOT assume list order);
    - ``updated_at`` being absent on some entries (fall back to
      ``created_at``);
    - two entries with equal timestamps (use the numeric status ``id``
      as a deterministic tie-breaker — larger id wins because GitHub
      assigns strictly increasing ids to newer statuses).

    A status with NO timestamp AND NO id sorts to the very end (empty
    string for timestamps, -1 for id); such an entry cannot be
    authoritative because we cannot establish a safe ordering for it.
    """
    ts = s.get("updated_at") or s.get("created_at") or ""
    sid = s.get("id")
    try:
        sid_int = int(sid) if sid is not None else -1
    except (TypeError, ValueError):
        sid_int = -1
    return (ts, "", sid_int)


def _latest_status(statuses: list, head_sha: str) -> dict | None:
    """Pick the SINGLE latest authoritative status for the exact head.

    Filters by:

      - ``context == "retail/pr-deep"``
      - ``sha    == head_sha``

    then sorts by ``(updated_at, created_at, id)`` descending and
    returns the first entry. If no entry has a usable ``id`` or any
    timestamp, the sort still produces a stable answer (entries with
    no key sort to the end); the caller MUST verify the returned
    status itself is acceptable for certification.

    This is the ONLY "latest" helper used by the policy. There is
    intentionally no `_latest_matching_status` because accepting an
    older matching success when the latest status is a different
    success (or anything else) is a downgrade-by-history bug.
    """
    candidates = [
        s for s in statuses
        if s.get("context") == PR_DEEP_CONTEXT
        and s.get("sha") == head_sha
    ]
    if not candidates:
        return None
    # Sort by (updated_at, created_at, id) descending. The key is
    # built in _status_sort_key; we negate the numeric part so the
    # list is sorted in descending order overall.
    candidates.sort(
        key=lambda s: (
            s.get("updated_at") or s.get("created_at") or "",
            s.get("created_at") or "",
            s.get("id") if isinstance(s.get("id"), int) else -1,
        ),
        reverse=True,
    )
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
        "schema_version": SCHEMA_VERSION_SUPPORTED,
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
        # The latest retail/pr-deep status for the exact HEAD is
        # authoritative. It certifies ONLY if that latest status
        # itself is success with PASS base=<current base>. An older
        # matching success for the same head but a different base
        # SHA is STALE and does NOT count; an older success CANNOT
        # override a newer pending / failure.
        latest = _latest_status(statuses, expected_head)
        if latest is None:
            return _emit_decision(_build_decision(
                selector_state=state,
                selector_rc=selector_rc,
                policy_state="pending",
                expected_head=expected_head,
                expected_base=expected_base,
                merge_base=merge_base,
                reason=(
                    "PR-DEEP certification required for exact head "
                    f"{expected_head[:12]} and exact base "
                    f"{expected_base[:12]}"
                ),
            ))
        latest_state = latest.get("state")
        latest_desc = latest.get("description")
        expected_desc = f"PASS base={expected_base}"
        # The latest status itself must be a current-base success.
        if (
            latest_state == "success"
            and latest_desc == expected_desc
        ):
            return _emit_decision(_build_decision(
                selector_state=state,
                selector_rc=selector_rc,
                policy_state="success",
                expected_head=expected_head,
                expected_base=expected_base,
                merge_base=merge_base,
                reason=(
                    "latest retail/pr-deep status is a current-base "
                    f"success for head {expected_head[:12]} and base "
                    f"{expected_base[:12]}"
                ),
            ))
        # Otherwise: latest is pending / failure / success with stale
        # or malformed description. The cert is NOT valid.
        return _emit_decision(_build_decision(
            selector_state=state,
            selector_rc=selector_rc,
            policy_state="pending",
            expected_head=expected_head,
            expected_base=expected_base,
            merge_base=merge_base,
            reason=(
                f"latest retail/pr-deep status for head "
                f"{expected_head[:12]} is state={latest_state!r} "
                f"description={latest_desc!r}; not a current-base "
                "success"
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