#!/usr/bin/env python3
"""Require changed Python hotspots to stay small or strictly improve."""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class FunctionMetric:
    start: int
    end: int
    complexity: int


def complexity(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(child, (
            ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.TryStar,
            ast.With, ast.AsyncWith, ast.IfExp, ast.Assert, ast.comprehension,
            ast.Match, ast.ExceptHandler,
        )):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(1, len(child.values) - 1)
    return score


def functions(source: str, path: str) -> dict[str, FunctionMetric]:
    tree = ast.parse(source, filename=path)
    result: dict[str, FunctionMetric] = {}

    def visit(body: list[ast.stmt], prefix: tuple[str, ...] = ()) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, (*prefix, node.name))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                key = ".".join((*prefix, node.name))
                result[key] = FunctionMetric(
                    start=node.lineno, end=node.end_lineno or node.lineno,
                    complexity=complexity(node),
                )
                visit(node.body, (*prefix, node.name, "<locals>"))

    visit(tree.body)
    return result


def changed_python_lines(base: str) -> dict[str, set[int]]:
    output = subprocess.check_output(
        ["git", "diff", "--unified=0", "--diff-filter=AM", base, "--", "backend"],
        cwd=ROOT, text=True,
    )
    changed: dict[str, set[int]] = {}
    current: str | None = None
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


def base_source(base: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{base}:{path}"], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    return result.stdout if result.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--maximum", type=int, default=20)
    args = parser.parse_args()
    failures: list[str] = []
    checked = 0
    for path, changed in changed_python_lines(args.base).items():
        current = functions((ROOT / path).read_text(encoding="utf-8"), path)
        previous_text = base_source(args.base, path)
        previous = functions(previous_text, path) if previous_text is not None else {}
        for key, metric in current.items():
            if not changed.intersection(range(metric.start, metric.end + 1)):
                continue
            checked += 1
            old = previous.get(key)
            improved = old is not None and metric.complexity < old.complexity
            if metric.complexity > args.maximum and not improved:
                before = "new" if old is None else str(old.complexity)
                failures.append(
                    f"{path}::{key}: complexity {metric.complexity}, previous {before}; "
                    f"maximum {args.maximum} or strict reduction required"
                )
    if failures:
        print("Changed-function complexity gate failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Changed-function complexity gate passed: {checked} changed functions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
