#!/usr/bin/env python3
"""PR-B3b pr-fast selected-paths validator (hardened contract).

This script is invoked by the PR-B3b backend-affected-coverage
GitHub Actions step to validate the canonical selector JSON before
its `selected_tests[].file` payload is converted into a pytest argv
and handed to the isolated-test runner.

It is also the control-plane authority for the pr-fast step's
identity and state assertions: a modification to this script MUST
escalate as a selector trust surface (see ``EXACT_ESCALATION_PATHS``
in scripts/pr_fast_select_tests.py + the ``deploy-release-ci`` A3
governance category).

CLI:

    pr_b3b_selected_paths_validator.py \
        <selector.json> \
        <expected_head_sha> \
        <expected_base_sha> \
        <selector_rc> \
        <output-paths-file>

Hardened contract (any failure -> rc 2, pr-fast gate failure):

  - ``schema_version`` MUST equal ``1`` (the only supported value).
  - selector ``head_sha`` MUST equal ``expected_head_sha`` exactly.
  - selector ``base_sha`` MUST equal ``expected_base_sha`` exactly.
  - selector ``state`` MUST be one of:
      NO_ELIGIBLE_BACKEND_CHANGE, SELECTED,
      ESCALATION_REQUIRED, ERROR.
  - selector ``state`` MUST be consistent with ``selector_rc``:
      NO_ELIGIBLE_BACKEND_CHANGE | SELECTED            -> rc 0
      ESCALATION_REQUIRED                              -> rc 2
      ERROR                                            -> rc 3
    Any mismatch is a policy failure.
  - ``selection_count`` MUST equal len(``selected_tests``).
  - Each ``selected_tests`` entry MUST be an object with a string
    ``file``; the file path:
      * must start with ``backend/tests/`` (case-sensitive)
      * must not contain traversal (``..``) or absolute components
      * must exist as a regular file at the exact PR HEAD checkout
      * must be unique within the list
  - For ESCALATION_REQUIRED and NO_ELIGIBLE_BACKEND_CHANGE, an empty
    runnable selection is valid; for SELECTED, at least one valid
    runnable test MUST exist.

The script intentionally has zero project-side dependencies: it
only uses the Python standard library so it can be invoked from a
fresh, controlled environment.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


SCHEMA_VERSION_SUPPORTED = 1
SELECTOR_RC_FOR_STATE = {
    "NO_ELIGIBLE_BACKEND_CHANGE": 0,
    "SELECTED": 0,
    "ESCALATION_REQUIRED": 2,
    "ERROR": 3,
}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _emit_error(msg: str) -> None:
    sys.stderr.write(f"::error::{msg}\n")


def _check_sha(value, name: str) -> bool:
    if not isinstance(value, str) or not _SHA_RE.match(value):
        _emit_error(f"{name} is not a 40-char lowercase hex SHA: {value!r}")
        return False
    return True


def _parse_rc(value: str) -> int | None:
    try:
        rc = int(value)
    except (TypeError, ValueError):
        _emit_error(f"selector_rc is not an integer: {value!r}")
        return None
    return rc


def main(argv: list) -> int:
    if len(argv) != 6:
        _emit_error(
            "usage: pr_b3b_selected_paths_validator.py "
            "<selector.json> <expected_head_sha> <expected_base_sha> "
            "<selector_rc> <output-paths-file>"
        )
        return 2
    payload_path, expected_head, expected_base, rc_arg, out_path = argv[1:6]
    if not _check_sha(expected_head, "expected_head_sha"):
        return 2
    if not _check_sha(expected_base, "expected_base_sha"):
        return 2
    selector_rc = _parse_rc(rc_arg)
    if selector_rc is None:
        return 2

    try:
        with open(payload_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _emit_error(f"cannot parse selector JSON: {exc}")
        return 2

    if not isinstance(payload, dict):
        _emit_error("selector JSON root must be an object")
        return 2

    # 1) schema_version
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION_SUPPORTED:
        _emit_error(
            f"selector schema_version {schema_version!r} is not supported "
            f"(expected {SCHEMA_VERSION_SUPPORTED})"
        )
        return 2

    # 2) identity
    actual_head = payload.get("head_sha")
    if not _check_sha(actual_head, "selector head_sha"):
        return 2
    if actual_head != expected_head:
        _emit_error(
            f"identity mismatch: selector head_sha "
            f"{actual_head!r} != expected {expected_head!r}"
        )
        return 2
    actual_base = payload.get("base_sha")
    if not _check_sha(actual_base, "selector base_sha"):
        return 2
    if actual_base != expected_base:
        _emit_error(
            f"identity mismatch: selector base_sha "
            f"{actual_base!r} != expected {expected_base!r}"
        )
        return 2

    # 3) canonical state
    state = payload.get("state")
    if state not in SELECTOR_RC_FOR_STATE:
        _emit_error(f"selector state {state!r} is not a known canonical state")
        return 2

    # 4) state/rc consistency
    expected_rc = SELECTOR_RC_FOR_STATE[state]
    if selector_rc != expected_rc:
        _emit_error(
            f"selector state {state!r} is inconsistent with selector_rc "
            f"{selector_rc} (expected {expected_rc})"
        )
        return 2

    # 5) selection_count
    sel = payload.get("selected_tests")
    if not isinstance(sel, list):
        _emit_error("selected_tests is not a list")
        return 2
    sel_count = payload.get("selection_count")
    if not isinstance(sel_count, int) or sel_count != len(sel):
        _emit_error(
            f"selection_count {sel_count!r} disagrees with "
            f"selected_tests length {len(sel)}"
        )
        return 2

    # 6) selected_tests shape + per-file security rules
    head_repo = Path(os.environ.get("GITHUB_WORKSPACE", "/"))
    seen: set = set()
    lines: list = []
    for entry in sel:
        if not isinstance(entry, dict):
            _emit_error("selected_tests entry is not an object")
            return 2
        rel = entry.get("file")
        if not isinstance(rel, str):
            _emit_error("selected path is not a string")
            return 2
        if ".." in Path(rel).parts or rel.startswith("/"):
            _emit_error(f"path traversal rejected: {rel}")
            return 2
        if not rel.startswith("backend/tests/"):
            _emit_error(
                f"selected path is not under backend/tests/: {rel}"
            )
            return 2
        if rel in seen:
            _emit_error(f"duplicate selected path: {rel}")
            return 2
        seen.add(rel)
        full = head_repo / rel
        if not full.is_file():
            _emit_error(f"selected path missing at HEAD: {rel}")
            return 2
        lines.append(rel)

    # 7) per-state runnable selection rule
    if state == "SELECTED" and not lines:
        _emit_error("SELECTED state requires at least one valid selected test")
        return 2

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as exc:
        _emit_error(f"cannot write output paths file: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))