#!/usr/bin/env python3
"""Require coverage for executable source lines changed against a base commit.

PR-B2 implementation contract:

  * Active coverage lanes:
      backend lane active iff --backend-json is supplied
      frontend lane active iff --frontend-lcov is supplied
    At least one of the two MUST be supplied; if both are absent the
    gate fails with a clear error rather than silently passing.

  * Fail-closed on missing coverage record:
      For every eligible changed source path whose lane is ACTIVE,
      the coverage report MUST contain a valid record for that path.
      An eligible changed file that disappears from coverage is a
      FAIL, not a silent PASS. This catches unexecuted source that
      would otherwise hide a regression.

  * Malformed coverage records FAIL:
      Backend JSON: each file record must carry the expected shape
      (executed_lines / missing_lines keys); empty payload is rejected.
      LCOV: SF records may validly contain zero DA entries; malformed DA
      and structurally ambiguous records (nested/unterminated SF,
      duplicate normalized SF or duplicate DA lines, invalid DA line
      numbers or hit counts) fail closed.

  * Comments / non-instrumented lines:
      A valid coverage record with NO intersection between changed
      lines and instrumented lines for that file is treated as
      "no changed executable lines" -> PASSes that file without
      contributing to the percentage calculation. The file must
      STILL be present in the coverage report, otherwise the gate
      fails closed (above).

  * Frontend exclusions (preserved from PR-B1):
      - tests (.test.) and src/test/
      - generated contracts and runtime schemas
      - declaration files (*.d.ts) are not executable coverage source

  * Rename safety:
      git diff --unified=0 --diff-filter=AM --no-renames <base>
      A pure rename becomes deletion + add at the destination; the
      destination is evaluated as an added file and cannot silently
      disappear.

This script does not modify thresholds, contract logic, or the shared
coverage exclusion list beyond the explicit PR-B2 rules above.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

# Frontend source eligibility (preserved from PR-B1, plus declaration-file exclusion).
FRONTEND_GENERATED_EXACT = frozenset({
    "src/api/generated/contracts.ts",
    "src/api/generated/runtime-schemas.ts",
})


# ---------------------------------------------------------------------------
# Testability surface
# ---------------------------------------------------------------------------
# --root lets tests run the gate against a temporary git repo. Production
# CLI usage continues to default to the script parent and is unchanged.


def _resolve_root(root):
    if root is None:
        return ROOT
    p = Path(root).resolve()
    if not p.is_dir():
        raise ValueError(f"--root path is not a directory: {p}")
    return p


# ---------------------------------------------------------------------------
# Diff helper (same fail-closed and rename-safety rules as the function gate).
# ---------------------------------------------------------------------------


def _validate_base(base, root):
    subprocess.run(
        ["git", "rev-parse", "--verify", f"{base}^{{commit}}"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def changed_lines(base, root=ROOT):
    """Return {path: {added_line_numbers}} for changed files.

    Uses --diff-filter=AM --no-renames so a pure rename/move becomes
    delete+add at the destination; the destination is evaluated as an
    added file and cannot silently disappear through rename classification.
    """
    output = subprocess.check_output(
        [
            "git",
            "diff",
            "--unified=0",
            "--diff-filter=AM",
            "--no-renames",
            base,
            "--",
        ],
        cwd=root,
        text=True,
    )
    result = {}
    current = None
    for line in output.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            continue
        match = HUNK.match(line)
        if current is None or match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        result.setdefault(current, set()).update(range(start, start + count))
    return result


# ---------------------------------------------------------------------------
# Eligibility predicates
# ---------------------------------------------------------------------------


def is_eligible_backend(name):
    if not (name.startswith("backend/") and name.endswith(".py")):
        return False
    if any(part in name for part in ("/tests/", "/scripts/", "/venv/")):
        return False
    return True


def is_eligible_frontend(name):
    if not (name.startswith("src/") and name.endswith((".ts", ".tsx"))):
        return False
    if ".test." in name or name.startswith("src/test/"):
        return False
    if name in FRONTEND_GENERATED_EXACT:
        return False
    if name.endswith(".d.ts"):
        return False
    return True


def lane_of(name):
    """Return "backend", "frontend", or None for an eligible file name."""
    if is_eligible_backend(name):
        return "backend"
    if is_eligible_frontend(name):
        return "frontend"
    return None


# ---------------------------------------------------------------------------
# Coverage parsers (fail-closed on malformed input)
# ---------------------------------------------------------------------------


class CoverageParseError(ValueError):
    """Raised when a coverage report is malformed. The gate fails closed."""


def _load_python_coverage(path, root):
    """Parse coverage.py JSON; return {repo_relative_path: {line: bool_hit}}.

    Strict-shape validation: each file record MUST carry both
    `executed_lines` AND `missing_lines`, and both values MUST be lists.
    Empty lists are valid (a file with no executable/instrumented lines).
    Null, string, dict, or other types are rejected so we can distinguish
    a malformed record from a legitimate empty one. Each list element
    MUST be a real JSON integer (``type(entry) is int``, so bool/str/float
    are rejected) with value >= 1. A normalized path that collides with
    an earlier record (e.g. ``foo.py`` vs ``backend/foo.py``) is rejected,
    and a line appearing in BOTH lists makes the record ambiguous and is
    rejected.
    """
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CoverageParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CoverageParseError("top-level JSON must be an object")
    files = payload.get("files")
    if not isinstance(files, dict):
        raise CoverageParseError("missing or invalid `files` object")

    result = {}
    for raw_name, details in files.items():
        if not isinstance(details, dict):
            raise CoverageParseError(
                f"file record for {raw_name!r} is not an object"
            )
        if "executed_lines" not in details:
            raise CoverageParseError(
                f"file record for {raw_name!r} is missing executed_lines"
            )
        if "missing_lines" not in details:
            raise CoverageParseError(
                f"file record for {raw_name!r} is missing missing_lines"
            )
        executed = details["executed_lines"]
        missing = details["missing_lines"]
        if not isinstance(executed, list):
            raise CoverageParseError(
                f"file record for {raw_name!r} executed_lines is not a list"
            )
        if not isinstance(missing, list):
            raise CoverageParseError(
                f"file record for {raw_name!r} missing_lines is not a list"
            )
        covered_lines: set[int] = set()
        for entry in executed:
            if type(entry) is not int or entry < 1:
                raise CoverageParseError(
                    f"file record for {raw_name!r} executed_lines entry {entry!r} "
                    "is not a positive JSON integer (type(entry) is int, >= 1)"
                )
            covered_lines.add(entry)
        missing_lines: set[int] = set()
        for entry in missing:
            if type(entry) is not int or entry < 1:
                raise CoverageParseError(
                    f"file record for {raw_name!r} missing_lines entry {entry!r} "
                    "is not a positive JSON integer (type(entry) is int, >= 1)"
                )
            missing_lines.add(entry)
        name = str(raw_name).replace("\\", "/")
        if not name.startswith("backend/"):
            name = f"backend/{name}"
        if name in result:
            raise CoverageParseError(
                f"duplicate normalized coverage path {name!r} (from {raw_name!r})"
            )
        overlap = covered_lines & missing_lines
        if overlap:
            raise CoverageParseError(
                f"file record for {raw_name!r} has line(s) in both "
                f"executed_lines and missing_lines: {sorted(overlap)}"
            )
        record: dict[int, bool] = {}
        for line in covered_lines | missing_lines:
            record[line] = line in covered_lines
        result[name] = record
    return result


def _normalize_sf_path(raw, root):
    """Normalize an LCOV SF path deterministically relative to root.

    Absolute paths resolve and become repo-relative when they live under
    root. Relative paths are interpreted relative to root, NEVER relative
    to the caller's current working directory. Paths that resolve outside
    root keep their resolved absolute form, so they can never be rewritten
    (via a broad ``lstrip("./")`` or similar) into a plausible repo source.
    """
    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _load_frontend_coverage(path, root):
    """Parse an LCOV file; return {repo_relative_path: {line: bool_hit}}.

    Strict-but-proportionate validation:
      - SF path must be non-empty and normalized deterministically
        relative to ``root`` (relative SF paths are root-relative, never
        cwd-relative; outside-root paths are kept as non-matching
        absolute keys instead of being rewritten into repo paths).
      - A normalized SF path may appear at most once: duplicate
        normalized SF records FAIL closed (no silent first/last-wins).
      - DA must parse; line number >= 1, hit count >= 0, and a line may
        not repeat within one SF record.
      - A new SF cannot appear before the previous record closes.
      - Every SF must terminate with `end_of_record`.
      - Records with zero DA lines (LF:0 / LH:0 / no DA) ARE valid
        when they represent a source file with no executable/instrumented
        lines. They are stored as empty dicts and handled by eligibility
        logic.
    """
    result: dict[str, dict[int, bool]] = {}
    current_path: str | None = None
    current_record: dict[int, bool] | None = None
    open_records = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("SF:"):
            if current_record is not None:
                raise CoverageParseError(
                    "nested SF: new record before previous end_of_record"
                )
            raw = line[3:].strip()
            if not raw:
                raise CoverageParseError("SF record has empty path")
            current_path = _normalize_sf_path(raw, root)
            if current_path in result:
                raise CoverageParseError(
                    f"duplicate normalized SF path {current_path!r} (from {raw!r})"
                )
            current_record = {}
            result[current_path] = current_record
            open_records += 1
            continue
        if current_record is None:
            # Lines outside any SF (TN:, VER:, comments, etc.) are ignored.
            continue
        if line.startswith("DA:"):
            payload = line[3:]
            parts = payload.split(",")
            if len(parts) < 2:
                raise CoverageParseError(
                    f"malformed DA record in {current_path!r}: {raw_line!r}"
                )
            try:
                number = int(parts[0])
                hits = int(parts[1])
            except ValueError as exc:
                raise CoverageParseError(
                    f"malformed DA number/hits in {current_path!r}: {raw_line!r}"
                ) from exc
            if number < 1:
                raise CoverageParseError(
                    f"DA line number must be >= 1 in {current_path!r}: {raw_line!r}"
                )
            if hits < 0:
                raise CoverageParseError(
                    f"DA hit count must be >= 0 in {current_path!r}: {raw_line!r}"
                )
            if number in current_record:
                raise CoverageParseError(
                    f"duplicate DA for line {number} in {current_path!r}"
                )
            current_record[number] = hits > 0
            continue
        if line == "end_of_record":
            current_record = None
            current_path = None
            open_records -= 1
    if open_records > 0:
        raise CoverageParseError(
            "LCOV ended with unterminated record(s)"
        )
    return result


# ---------------------------------------------------------------------------
# Pure evaluator
# ---------------------------------------------------------------------------


def evaluate(
    base,
    *,
    backend_json=None,
    frontend_lcov=None,
    minimum=80.0,
    root=None,
):
    """Pure evaluator. Returns (returncode, summary_message).

    Used by tests; CLI wraps this. The summary is also printed by this
    function so the CLI gets the same output as the tests.
    """
    resolved = _resolve_root(root)

    backend_active = backend_json is not None
    frontend_active = frontend_lcov is not None
    if not backend_active and not frontend_active:
        return (
            1,
            "must supply --backend-json and/or --frontend-lcov",
        )

    try:
        _validate_base(base, resolved)
    except subprocess.CalledProcessError as exc:
        return (
            1,
            f"invalid base commit {base!r} (rc={exc.returncode})",
        )

    backend_cov = {}
    if backend_active:
        try:
            backend_cov = _load_python_coverage(Path(backend_json), resolved)
        except CoverageParseError as exc:
            return (1, f"cannot parse --backend-json: {exc}")
        except (OSError, UnicodeDecodeError) as exc:
            return (1, f"cannot read --backend-json: {exc}")

    frontend_cov = {}
    if frontend_active:
        try:
            frontend_cov = _load_frontend_coverage(Path(frontend_lcov), resolved)
        except CoverageParseError as exc:
            return (1, f"cannot parse --frontend-lcov: {exc}")
        except (OSError, UnicodeDecodeError) as exc:
            return (1, f"cannot read --frontend-lcov: {exc}")

    try:
        changed = changed_lines(base, resolved)
    except subprocess.CalledProcessError as exc:
        return (1, f"git diff failed (rc={exc.returncode})")

    failures = []
    relevant = []  # (name, line, hit)
    for name, lines_set in changed.items():
        lane = lane_of(name)
        if lane is None:
            continue
        if lane == "backend":
            if not backend_active:
                continue
            cov = backend_cov
        else:
            if not frontend_active:
                continue
            cov = frontend_cov

        if name not in cov:
            failures.append(
                f"{name}: eligible changed source absent from active coverage report"
            )
            continue
        record = cov[name]
        # Parser already validated record is a dict. A record may be
        # legitimately empty (zero executable/instrumented lines); that
        # means no changed executable lines and the file PASSes by
        # contributing nothing to the percentage.
        if not isinstance(record, dict):
            failures.append(
                f"{name}: malformed active coverage record"
            )
            continue
        for line in sorted(lines_set):
            if line in record:
                relevant.append((name, line, record[line]))

    if failures:
        for failure in failures:
            print(f"- {failure}")
        return (1, f"{len(failures)} active-lane failure(s)")

    if not relevant:
        return (0, "no changed executable lines in this lane")

    covered = sum(1 for _, _, hit in relevant if hit)
    percent = covered * 100 / len(relevant)
    uncovered = [f"{name}:{line}" for name, line, hit in relevant if not hit]
    summary = (
        f"{covered}/{len(relevant)} = {percent:.2f}% (minimum {minimum:.2f}%)"
    )
    if uncovered:
        print("Uncovered changed lines: " + ", ".join(uncovered[:40]))
    return (0 if percent >= minimum else 1, summary)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--backend-json", type=Path, default=None)
    parser.add_argument("--frontend-lcov", type=Path, default=None)
    parser.add_argument("--minimum", type=float, default=80.0)
    parser.add_argument(
        "--root",
        default=None,
        help="Path to the git working tree root. Defaults to the script parent.",
    )
    args = parser.parse_args(argv)

    try:
        rc, summary = evaluate(
            args.base,
            backend_json=args.backend_json,
            frontend_lcov=args.frontend_lcov,
            minimum=args.minimum,
            root=args.root,
        )
    except ValueError as exc:
        print(f"Changed-line coverage gate failed: {exc}")
        return 1

    if rc == 0:
        print(f"Changed-line coverage gate passed: {summary}")
        return 0
    print(f"Changed-line coverage gate failed: {summary}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
