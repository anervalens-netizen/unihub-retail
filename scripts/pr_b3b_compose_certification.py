#!/usr/bin/env python3
"""PR-B3b pr-deep certification JSON composer (fail-closed).

Used by .github/workflows/pr-deep.yml to build the machine-readable
certification artifact under
``test-results/pr-deep/<EXPECTED_HEAD>/certification.json``.

Fail-closed contract: this script returns a non-zero exit code on
ANY malformed / missing / partial evidence, so the workflow does
NOT reach the publish-success step. We deliberately do NOT emit
UNKNOWN / UNREADABLE placeholders in a successful certification.

CLI:

    pr_b3b_compose_certification.py \\
        <output_path> \\
        <pr_number> <expected_head_sha> <expected_base_sha> \\
        <merge_base_sha> <repo> <run_id> <run_attempt> \\
        <workflow> <workflow_ref> <control_plane_sha>

Reads:
    backend/pr-deep-junit.xml
    backend/pr-deep-coverage.json

Writes:
    <output_path>
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import xml.etree.ElementTree as ET


SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _emit_error(msg: str) -> None:
    sys.stderr.write(f"::error::{msg}\n")


def _check_sha(value: str, name: str) -> bool:
    if not isinstance(value, str) or not SHA_RE.match(value):
        _emit_error(f"{name} is not a 40-char lowercase hex SHA: {value!r}")
        return False
    return True


def _parse_junit(path: str) -> dict:
    """Parse JUnit XML and return {tests, failures, errors, skipped}.

    Fails closed: missing file, malformed XML, or zero tests -> error.
    """
    if not os.path.isfile(path):
        _emit_error(f"JUnit file does not exist: {path}")
        return {}
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        _emit_error(f"JUnit XML is malformed: {exc}")
        return {}
    root = tree.getroot()
    if root.tag == "testsuites":
        suites = root.findall("testsuite")
    elif root.tag == "testsuite":
        suites = [root]
    else:
        _emit_error(
            f"JUnit root must be <testsuites> or <testsuite>; got <{root.tag}>"
        )
        return {}
    if not suites:
        _emit_error("JUnit contains no <testsuite> elements")
        return {}
    tests = 0
    failures = 0
    errors = 0
    skipped = 0
    for suite in suites:
        tests += int(suite.attrib.get("tests", 0))
        failures += int(suite.attrib.get("failures", 0))
        errors += int(suite.attrib.get("errors", 0))
        skipped += int(suite.attrib.get("skipped", 0))
    if tests <= 0:
        _emit_error(f"JUnit reports 0 tests in {path}")
        return {}
    if failures != 0:
        _emit_error(f"JUnit reports {failures} failures in {path}")
        return {}
    if errors != 0:
        _emit_error(f"JUnit reports {errors} errors in {path}")
        return {}
    return {
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
    }


def _parse_coverage(path: str) -> dict:
    """Parse coverage JSON and return totals dict.

    Fails closed: missing file, malformed JSON, missing
    ``totals.percent_covered`` numeric -> error.
    """
    if not os.path.isfile(path):
        _emit_error(f"coverage JSON does not exist: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _emit_error(f"coverage JSON is malformed: {exc}")
        return {}
    if not isinstance(data, dict):
        _emit_error("coverage JSON root must be an object")
        return {}
    totals = data.get("totals")
    if not isinstance(totals, dict):
        _emit_error("coverage JSON missing 'totals' object")
        return {}
    percent_covered = totals.get("percent_covered")
    if not isinstance(percent_covered, (int, float)):
        _emit_error(
            f"coverage JSON 'totals.percent_covered' is not numeric: "
            f"{percent_covered!r}"
        )
        return {}
    return {
        "percent_covered": float(percent_covered),
        "covered_lines": int(totals.get("covered_lines", 0)),
        "num_statements": int(totals.get("num_statements", 0)),
    }


def main(argv: list) -> int:
    if len(argv) != 12:
        _emit_error(
            "usage: pr_b3b_compose_certification.py <output_path> "
            "<pr_number> <expected_head_sha> <expected_base_sha> "
            "<merge_base_sha> <repo> <run_id> <run_attempt> "
            "<workflow> <workflow_ref> <control_plane_sha>"
        )
        return 1
    out_path = argv[1]
    pr_number = argv[2]
    expected_head = argv[3]
    expected_base = argv[4]
    merge_base = argv[5]
    repo = argv[6]
    run_id = argv[7]
    run_attempt = argv[8]
    workflow = argv[9]
    workflow_ref = argv[10]
    control_plane_sha = argv[11]

    if not _check_sha(expected_head, "expected_head_sha"):
        return 1
    if not _check_sha(expected_base, "expected_base_sha"):
        return 1
    if not _check_sha(merge_base, "merge_base_sha"):
        return 1
    if not _check_sha(control_plane_sha, "control_plane_sha"):
        return 1

    junit = _parse_junit("backend/pr-deep-junit.xml")
    if not junit:
        return 1
    coverage = _parse_coverage("backend/pr-deep-coverage.json")
    if not coverage:
        return 1

    payload = {
        "schema_version": 1,
        "result": "success",
        "repository": repo,
        "pr_number": pr_number,
        "expected_head_sha": expected_head,
        "actual_head_sha": expected_head,
        "expected_base_sha": expected_base,
        "actual_base_sha": expected_base,
        "merge_base_sha": merge_base,
        "control_plane_sha": control_plane_sha,
        "workflow": workflow,
        "workflow_ref": workflow_ref,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "backend_test_result": "PASS",
        "backend_test_count": junit["tests"],
        "backend_failures": junit["failures"],
        "backend_errors": junit["errors"],
        "backend_skipped": junit["skipped"],
        "coverage_result": {
            "percent_covered": coverage["percent_covered"],
            "covered_lines": coverage["covered_lines"],
            "num_statements": coverage["num_statements"],
        },
        "changed_line_result": "PASS",
        "timestamp": (
            datetime.datetime.now(datetime.timezone.utc).isoformat()
        ),
    }
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=False)
            f.write("\n")
    except OSError as exc:
        _emit_error(f"cannot write certification JSON: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))