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

control_plane_sha semantics (deliberately narrow — DO NOT widen):

  - ``control_plane_sha`` is the exact ``github.sha`` value of the
    ``pr-deep`` workflow at dispatch time — i.e. the main commit
    that supplied the trusted PR-DEEP workflow definition on
    ``refs/heads/main``. It is recorded so pre-merge inspection can
    see which main commit was the source of the trusted workflow
    definition that ran this certification.
  - It is NOT a byte-level attestation of every helper source
    executed during backend verification. PR-B3b does NOT build a
    SHA256 manifest/attestation framework; PR-DEEP makes no claim
    that the executed ``scripts/pr_b3b_*.py``, the selector, the
    coverage gate, or any other control-plane helper is byte-equal
    to that commit's working tree.
  - Control-plane changes (governance, workflows, selector, gate,
    coverage, isolated-test runner) remain subject to A3
    governance, adversarial review and the post-merge exact-main
    FULL checkpoint.
"""
from __future__ import annotations

import datetime
import json
import math
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


def _parse_non_negative_int(value, name: str) -> int | None:
    """Return a non-negative int or None.

    Rejects bool (which is an int subclass in Python). Rejects None,
    non-numeric strings, NaN/Infinity, and negative values. Emits an
    ::error:: explaining the rejection.
    """
    if isinstance(value, bool):
        _emit_error(f"{name} must not be a bool: {value!r}")
        return None
    if isinstance(value, int):
        v = value
    elif isinstance(value, str):
        try:
            v = int(value)
        except (TypeError, ValueError):
            _emit_error(f"{name} is not an integer: {value!r}")
            return None
    else:
        _emit_error(f"{name} is not an integer: {value!r}")
        return None
    if v < 0:
        _emit_error(f"{name} is negative: {v}")
        return None
    return v


def _parse_junit(path: str) -> dict:
    """Parse JUnit XML and return {tests, failures, errors, skipped}.

    Fails closed: missing file, malformed XML, zero tests, failures,
    errors, or non-numeric/non-negative attribute -> error.
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
        t = _parse_non_negative_int(
            suite.attrib.get("tests", 0),
            f"JUnit tests attribute in {path}",
        )
        if t is None:
            return {}
        f = _parse_non_negative_int(
            suite.attrib.get("failures", 0),
            f"JUnit failures attribute in {path}",
        )
        if f is None:
            return {}
        e = _parse_non_negative_int(
            suite.attrib.get("errors", 0),
            f"JUnit errors attribute in {path}",
        )
        if e is None:
            return {}
        s = _parse_non_negative_int(
            suite.attrib.get("skipped", 0),
            f"JUnit skipped attribute in {path}",
        )
        if s is None:
            return {}
        tests += t
        failures += f
        errors += e
        skipped += s
    if tests <= 0:
        _emit_error(f"JUnit reports 0 tests in {path}")
        return {}
    if failures != 0:
        _emit_error(f"JUnit reports {failures} failures in {path}")
        return {}
    if errors != 0:
        _emit_error(f"JUnit reports {errors} errors in {path}")
        return {}
    if skipped > tests:
        _emit_error(
            f"JUnit reports skipped={skipped} > tests={tests} in {path}"
        )
        return {}
    return {
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
    }


def _parse_percent_covered(value, name: str) -> float | None:
    """Return a finite float in [0, 100] or None.

    Rejects bool, NaN, Infinity, and out-of-range values.
    """
    if isinstance(value, bool):
        _emit_error(f"{name} must not be a bool: {value!r}")
        return None
    if not isinstance(value, (int, float)):
        _emit_error(f"{name} is not numeric: {value!r}")
        return None
    f = float(value)
    if not math.isfinite(f):
        _emit_error(f"{name} is not finite: {value!r}")
        return None
    if f < 0.0 or f > 100.0:
        _emit_error(f"{name} is out of range [0, 100]: {f}")
        return None
    return f


def _parse_coverage(path: str) -> dict:
    """Parse coverage JSON and return totals dict.

    Fails closed: missing file, malformed JSON, malformed counters,
    out-of-range percent_covered, non-finite numerics.
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
    if "percent_covered" not in totals:
        _emit_error("coverage JSON missing 'totals.percent_covered'")
        return {}
    percent_covered = _parse_percent_covered(
        totals["percent_covered"], "totals.percent_covered"
    )
    if percent_covered is None:
        return {}
    if "covered_lines" not in totals:
        _emit_error("coverage JSON missing 'totals.covered_lines'")
        return {}
    if "num_statements" not in totals:
        _emit_error("coverage JSON missing 'totals.num_statements'")
        return {}
    covered_lines = _parse_non_negative_int(
        totals["covered_lines"], "totals.covered_lines"
    )
    if covered_lines is None:
        return {}
    num_statements = _parse_non_negative_int(
        totals["num_statements"], "totals.num_statements"
    )
    if num_statements is None:
        return {}
    if covered_lines > num_statements:
        _emit_error(
            f"totals.covered_lines={covered_lines} > "
            f"totals.num_statements={num_statements}"
        )
        return {}
    return {
        "percent_covered": percent_covered,
        "covered_lines": covered_lines,
        "num_statements": num_statements,
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
            json.dump(payload, f, indent=2, sort_keys=False, allow_nan=False)
            f.write("\n")
    except OSError as exc:
        _emit_error(f"cannot write certification JSON: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))