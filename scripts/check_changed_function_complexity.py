#!/usr/bin/env python3
"""Require changed Python hotspots to stay small or strictly improve.

This script is the changed-function incremental complexity gate.

PR-B2 implementation contract:

  * The complexity metric is consumed from scripts/_python_complexity.py
    (the shared L1 module). The script owns NO copy of the AST scoring
    algorithm; there is exactly one metric implementation in the repo.

  * Changed files are obtained with:

        git diff --unified=0 --diff-filter=AM --no-renames <base> -- backend

    A pure rename or move therefore becomes deletion + addition at the
    destination path. The destination is evaluated as an added file; it
    cannot silently disappear through rename classification.

  * Fail-closed behavior on:
      - invalid base commit (validated up front with git rev-parse --verify)
      - git diff failure (subprocess error propagates)
      - unreadable changed Python source (raises, no broad except)
      - invalid Python syntax (ast.parse raises; reported per file)

  * Policy is preserved verbatim from PR-B1:
      - --maximum (default 20)
      - strict-improvement semantics: a previously existing hotspot
        passes only if its complexity is STRICTLY reduced; equal or
        worsening fails. This PR does not touch the threshold or the
        strict-improvement rule.

This script does not modify the L1 module, the contract, or the
thresholds. It only repairs the implementation integrity of this gate.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
L1_PATH = Path(__file__).with_name("_python_complexity.py")
_L1_MODNAME = "_unihub_python_complexity_l1"


# ---------------------------------------------------------------------------
# Testability surface
# ---------------------------------------------------------------------------
#
# ``--root`` lets tests run the gate against a temporary git repo with the
# same directory layout (temp/backend/, etc.). Production CLI usage
# continues to default to the script's parent and is therefore unchanged.


def _resolve_root(root):
    """Resolve the root for diff / source I/O. None means default ROOT."""
    if root is None:
        return ROOT
    p = Path(root).resolve()
    if not p.is_dir():
        raise ValueError(f"--root path is not a directory: {p}")
    return p


# ---------------------------------------------------------------------------
# L1 loading
# ---------------------------------------------------------------------------


class L1LoadError(RuntimeError):
    """Raised when L1 cannot be loaded. The gate fails closed."""


def _load_l1() -> Any:
    """Load scripts/_python_complexity.py via importlib.

    Same trusted-sibling pattern as scripts/check_python_complexity_contract.py.
    Path is resolved via Path(__file__).with_name(...) so cwd is irrelevant.
    On any loader exception the sys.modules entry is cleaned up and the
    exception is re-raised.
    """
    if not L1_PATH.is_file():
        raise L1LoadError(f"L1 module not found at {L1_PATH}")
    spec = importlib.util.spec_from_file_location(_L1_MODNAME, str(L1_PATH))
    if spec is None or spec.loader is None:
        raise L1LoadError(f"could not build import spec for {L1_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_L1_MODNAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_L1_MODNAME, None)
        raise
    required = {
        "ALGORITHM_NAME",
        "ALGORITHM_VERSION",
        "COUNTED_NODES",
        "FunctionMetric",
        "algorithm_spec",
        "collect_metrics",
        "function_metrics",
        "score",
    }
    missing = required - set(dir(module))
    if missing:
        sys.modules.pop(_L1_MODNAME, None)
        raise L1LoadError(f"L1 missing required names: {sorted(missing)}")
    return module


# ---------------------------------------------------------------------------
# Diff / source helpers
# ---------------------------------------------------------------------------


def _validate_base(base, root=ROOT):
    """Verify the base commit resolves in this repository.

    Raises subprocess.CalledProcessError on failure; the gate is fail-closed
    on invalid base.
    """
    subprocess.run(
        ["git", "rev-parse", "--verify", f"{base}^{{commit}}"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def changed_python_lines(base, root=ROOT):
    """Return {path: {added_line_numbers}} for changed backend Python files.

    Uses --diff-filter=AM --no-renames so a pure rename/move becomes
    delete+add at the destination; the destination is therefore evaluated
    as an added file instead of silently disappearing.

    base must already be validated by _validate_base.
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
            "backend",
        ],
        cwd=root,
        text=True,
    )
    changed = {}
    current = None
    for line in output.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            continue
        match = HUNK.match(line)
        if current is not None and current.endswith(".py") and match:
            start = int(match.group(1))
            count = int(match.group(2) or "1")
            changed.setdefault(current, set()).update(range(start, start + count))
    return changed


def base_source(base, path, root=ROOT):
    """Return the source text of path at base, or None if absent.

    None legitimately represents an added file (no previous version).
    """
    result = subprocess.run(
        ["git", "show", f"{base}:{path}"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return result.stdout if result.returncode == 0 else None


def _read_function_metrics(l1, source, path):
    """Parse and enumerate function metrics for one source.

    Raises SyntaxError on invalid Python; the caller must report it.
    """
    return l1.function_metrics(source, path)


# ---------------------------------------------------------------------------
# Main gate
# ---------------------------------------------------------------------------


def _evaluate_file(l1, base, path, changed, maximum, root=ROOT):
    """Evaluate one changed file.

    Returns (violations, count_of_changed_functions_seen).
    """
    violations = []
    seen = 0

    try:
        current_text = (root / path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        violations.append(f"{path}: cannot read changed source: {exc}")
        return violations, seen

    try:
        current_metrics = _read_function_metrics(l1, current_text, path)
    except SyntaxError as exc:
        violations.append(
            f"{path}: invalid Python syntax at line {exc.lineno}: {exc.msg}"
        )
        return violations, seen

    previous_text = base_source(base, path, root)
    previous_metrics = {}
    if previous_text is not None:
        # The previous version exists. If L1 cannot parse it, that is a
        # base integrity failure: we MUST NOT silently treat it as
        # "no previous" because that would let a complex current function
        # escape evaluation. Fail the file clearly instead.
        try:
            previous_metrics = {
                m.function: m
                for m in _read_function_metrics(l1, previous_text, path)
            }
        except SyntaxError as exc:
            violations.append(
                f"{path}: base source has invalid Python syntax at line {exc.lineno}: {exc.msg}"
            )
            return violations, seen

    for metric in current_metrics:
        if not changed.intersection(range(metric.start_line, metric.end_line + 1)):
            continue
        seen += 1
        old = previous_metrics.get(metric.function)
        improved = old is not None and metric.complexity_proxy < old.complexity_proxy
        if metric.complexity_proxy > maximum and not improved:
            before = "new" if old is None else str(old.complexity_proxy)
            violations.append(
                f"{path}::{metric.function}: complexity {metric.complexity_proxy}, "
                f"previous {before}; maximum {maximum} or strict reduction required"
            )

    return violations, seen


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--maximum", type=int, default=20)
    parser.add_argument(
        "--root",
        default=None,
        help="Path to the git working tree root. Defaults to the script parent.",
    )
    args = parser.parse_args(argv)

    try:
        resolved = _resolve_root(args.root)
    except ValueError as exc:
        print(f"Changed-function complexity gate failed: {exc}")
        return 1

    try:
        l1 = _load_l1()
    except L1LoadError as exc:
        print(f"Changed-function complexity gate failed: L1 unavailable: {exc}")
        return 1

    # Fail closed on invalid base commit (raises CalledProcessError).
    try:
        _validate_base(args.base, resolved)
    except subprocess.CalledProcessError as exc:
        print(
            f"Changed-function complexity gate failed: invalid base commit "
            f"{args.base!r} (rc={exc.returncode})"
        )
        return 1

    failures = []
    checked = 0
    try:
        for path, changed in changed_python_lines(args.base, resolved).items():
            file_failures, seen = _evaluate_file(
                l1, args.base, path, changed, args.maximum, resolved
            )
            failures.extend(file_failures)
            checked += seen
    except subprocess.CalledProcessError as exc:
        print(
            f"Changed-function complexity gate failed: git diff failed (rc={exc.returncode})"
        )
        return 1

    if failures:
        print("Changed-function complexity gate failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Changed-function complexity gate passed: {checked} changed functions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
