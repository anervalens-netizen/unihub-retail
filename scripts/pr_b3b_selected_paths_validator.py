#!/usr/bin/env python3
"""PR-B3b pr-fast selected-paths validator.

This script is invoked by the PR-B3b backend-affected-coverage
GitHub Actions step to validate the selected_tests[].file payload
produced by the trusted selector before it is converted into a
pytest argv and handed to the isolated-test runner.

Strict security/validation:
  - every selected path must be a string
  - must start with ``backend/tests/`` (case-sensitive, repo-relative)
  - must not contain traversal (``..``) or absolute components
  - must exist as a regular file at the exact PR HEAD checkout
  - must not be deleted in the candidate checkout
  - selection_count must agree with the parsed list length
  - reject duplicates

This script intentionally has zero project-side dependencies: it
only uses the Python standard library so it can be invoked from a
fresh, controlled environment.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _emit_error(msg: str) -> None:
    sys.stderr.write(f"::error::{msg}\n")


def main(argv: list) -> int:
    if len(argv) != 4:
        _emit_error(
            "usage: pr_b3b_selected_paths_validator.py "
            "<selector.json> <expected_head_sha> <output-paths-file>"
        )
        return 2
    payload_path, expected_head, out_path = argv[1:4]
    try:
        with open(payload_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _emit_error(f"cannot parse selector JSON: {exc}")
        return 2
    if payload.get("head_sha") != expected_head:
        _emit_error(
            f"identity mismatch: selector head_sha "
            f"{payload.get('head_sha')!r} != expected {expected_head!r}"
        )
        return 2
    sel = payload.get("selected_tests", [])
    if not isinstance(sel, list):
        _emit_error("selected_tests is not a list")
        return 2
    if payload.get("selection_count") != len(sel):
        _emit_error(
            "selection_count disagrees with selected_tests length"
        )
        return 2
    seen: set = set()
    lines: list = []
    head_repo = Path(os.environ.get("GITHUB_WORKSPACE", "/"))
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
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as exc:
        _emit_error(f"cannot write output paths file: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))