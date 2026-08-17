#!/usr/bin/env python3
"""Shared Python AST-complexity metric.

This module freezes the existing Python complexity-proxy measurement.
It contains METRIC IMPLEMENTATION ONLY:

  - COUNTED_NODES  : the AST node types whose presence increments the score
  - score(node)    : return the complexity_proxy of a single AST node
  - FunctionMetric : dataclass describing one function measurement
  - function_metrics(source, path) : enumerate FunctionMetric for one source
  - iter_python_files(root)       : yield eligible backend/*.py paths
  - collect_metrics(root)         : enumerate FunctionMetric for the tree

There is no CI policy, no threshold, no contract logic, no git policy here.
PR-B2 and later may consume this module; PR-B1 introduces it.

The metric is preserved verbatim from scripts/check_python_complexity_contract.py
and scripts/check_changed_function_complexity.py at exact-main
76a71d9bcf339385712ae1207824624af603a12f.

Algorithm:

    score(node) = 1
    for each descendant d in ast.walk(node):
        if type(d).__name__ in COUNTED_NODES:
            score += 1
        elif isinstance(d, ast.BoolOp):
            score += max(1, len(d.values) - 1)

Notes:

  - ast.walk descends into nested function/class bodies by design.
    This is preserved. Do not silently "fix" this in a future revision;
    any change here requires a contract bump.
  - The starting value is 1 for every counted function.
  - BoolOp contributes max(1, len(values) - 1) so a 2-arg AND/OR gives 1,
    a 3-arg AND/OR gives 2, etc.
  - This is NOT textbook cyclomatic complexity; the document
    docs/contracts/python-complexity-contract-v2.md explains the difference.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


# Node type names whose presence increments the score by exactly 1.
# The list matches the literal set used in scripts/check_python_complexity_contract.py
# and scripts/check_changed_function_complexity.py at exact-main
# 76a71d9bcf339385712ae1207824624af603a12f.
#
# In Python 3.8+ ast.comprehension is a real class; in 3.9+ it remains so.
# Both implementations use ast.comprehension directly.
COUNTED_NODES: tuple[str, ...] = (
    "If",
    "For",
    "AsyncFor",
    "While",
    "Try",
    "TryStar",
    "With",
    "AsyncWith",
    "IfExp",
    "Assert",
    "comprehension",
    "Match",
    "ExceptHandler",
)


@dataclass(frozen=True, slots=True)
class FunctionMetric:
    """One function's measured record.

    path        : repo-relative POSIX path (e.g., backend/foo/bar.py)
    function    : dotted name, including Class.method and nested <locals>
    start_line  : 1-based inclusive
    end_line    : 1-based inclusive
    line_count  : end_line - start_line + 1
    complexity_proxy : the score returned by score(node)
    """

    path: str
    function: str
    start_line: int
    end_line: int
    line_count: int
    complexity_proxy: int


def score(node: ast.AST) -> int:
    """Return the complexity_proxy of ``node``.

    Walks descendants with ast.walk (descends into nested function/class
    bodies). Starts at 1; increments by 1 for each descendant whose
    type name is in COUNTED_NODES; for BoolOp descendants, increments
    by max(1, len(values) - 1).

    Pure function; no global state.
    """
    if node is None:
        raise TypeError("score() requires an AST node")
    total = 1
    for child in ast.walk(node):
        cls_name = type(child).__name__
        if cls_name in COUNTED_NODES:
            total += 1
            continue
        if isinstance(child, ast.BoolOp):
            total += max(1, len(child.values) - 1)
    return total


def function_metrics(source: str, path: str) -> list[FunctionMetric]:
    """Parse ``source`` and return one FunctionMetric per function found.

    Identity rules:
      - Top-level functions use their bare name.
      - Class methods use ``ClassName.method``.
      - Nested functions use ``outer.<locals>.inner``.
      - Async functions are treated identically to sync functions.

    start_line uses ``node.lineno``; end_line uses ``node.end_lineno``
    (falling back to ``lineno`` if missing). This matches the existing
    scripts/check_python_complexity_contract.py semantics exactly.
    """
    tree = ast.parse(source, filename=path)
    out: list[FunctionMetric] = []

    def visit(body: Iterable[ast.stmt], prefix: tuple[str, ...] = ()) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, (*prefix, node.name))
                continue
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            function = ".".join((*prefix, node.name))
            end_line = node.end_lineno or node.lineno
            out.append(
                FunctionMetric(
                    path=path,
                    function=function,
                    start_line=node.lineno,
                    end_line=end_line,
                    line_count=end_line - node.lineno + 1,
                    complexity_proxy=score(node),
                )
            )
            visit(node.body, (*prefix, node.name, "<locals>"))

    visit(tree.body)
    return out


# Path part exclusions for iter_python_files. Matches the existing
# scripts/check_python_complexity_contract.py exactly.
EXCLUDED_PARTS: frozenset[str] = frozenset({"tests", "venv", ".venv", "__pycache__"})


def iter_python_files(root: Path) -> Iterator[Path]:
    """Yield backend/*.py files eligible for measurement.

    Eligibility rules (identical to the existing contract check):
      - Path is a regular file.
      - Path is under root/backend/.
      - No path part is in EXCLUDED_PARTS.

    Yields paths in sorted order.
    """
    backend = root / "backend"
    if not backend.is_dir():
        return
    for path in sorted(backend.rglob("*.py")):
        relative = path.relative_to(root)
        if path.is_file() and not any(part in EXCLUDED_PARTS for part in relative.parts):
            yield path


def collect_metrics(root: Path) -> list[FunctionMetric]:
    """Measure every eligible backend file and return all FunctionMetrics."""
    out: list[FunctionMetric] = []
    for path in iter_python_files(root):
        out.extend(
            function_metrics(
                path.read_text(encoding="utf-8"),
                path.relative_to(root).as_posix(),
            )
        )
    return out


__all__ = [
    "COUNTED_NODES",
    "EXCLUDED_PARTS",
    "FunctionMetric",
    "collect_metrics",
    "function_metrics",
    "iter_python_files",
    "score",
]
