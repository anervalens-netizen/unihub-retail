#!/usr/bin/env python3
"""Reject new oversized production modules/functions and freeze legacy hotspots."""
from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).with_name("complexity-ratchet.json")
SUFFIXES = {".py": "py", ".ts": "ts", ".tsx": "tsx"}
IGNORED_PARTS = {
    "tests",
    "__pycache__",
    "generated",
    "migrations",
    "venv",
    ".venv",
    "site-packages",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "playwright-report",
    "test-results",
}
TEST_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")


@dataclass(frozen=True, slots=True)
class PythonFunction:
    key: str
    path: str
    qualname: str
    line_count: int


def iter_production_files(root: Path) -> Iterator[Path]:
    """Yield production source files relative to one explicit repository root."""
    for base in (root / "backend", root / "src"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in SUFFIXES:
                continue
            relative = path.relative_to(root)
            if any(part in IGNORED_PARTS for part in relative.parts):
                continue
            if path.name.endswith(TEST_SUFFIXES):
                continue
            yield path


def line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def python_functions(path: Path, root: Path) -> list[PythonFunction]:
    relative = path.relative_to(root).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
    findings: list[PythonFunction] = []

    def walk(body: Iterable[ast.stmt], stack: tuple[str, ...] = ()) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                walk(node.body, (*stack, node.name))
                continue
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            qualname = ".".join((*stack, node.name))
            end_lineno = node.end_lineno or node.lineno
            findings.append(
                PythonFunction(
                    key=f"{relative}::{qualname}",
                    path=relative,
                    qualname=qualname,
                    line_count=end_lineno - node.lineno + 1,
                )
            )
            walk(node.body, (*stack, node.name, "<locals>"))

    walk(tree.body)
    return findings


def _mapping(config: dict[str, object], key: str) -> dict[str, object]:
    value = config.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"Invalid complexity ratchet mapping: {key}")
    return value


def evaluate(root: Path, config: dict[str, object]) -> list[str]:
    root = root.resolve()
    default_limits = _mapping(config, "default_max_lines")
    legacy_limits = _mapping(config, "legacy_max_lines")
    default_function_limit = int(config.get("default_max_python_function_lines", 120))
    legacy_function_limits = _mapping(config, "legacy_max_python_function_lines")

    observed_files: set[str] = set()
    observed_functions: set[str] = set()
    failures: list[str] = []

    for path in iter_production_files(root):
        relative = path.relative_to(root).as_posix()
        observed_files.add(relative)
        suffix = SUFFIXES[path.suffix]
        if suffix not in default_limits:
            raise ValueError(f"Missing default limit for {suffix}")
        default_limit = int(default_limits[suffix])
        legacy_value = legacy_limits.get(relative)
        legacy_limit = int(legacy_value) if legacy_value is not None else None
        allowed = legacy_limit if legacy_limit is not None else default_limit
        actual = line_count(path)
        if actual > allowed:
            failures.append(f"{relative}: {actual} lines > allowed {allowed}")
        elif legacy_limit is not None and actual < legacy_limit:
            if actual <= default_limit:
                failures.append(
                    f"{relative}: legacy file allowance {legacy_limit} is stale; remove it"
                )
            else:
                failures.append(
                    f"{relative}: legacy file allowance {legacy_limit} is stale; shrink it to {actual}"
                )

        if path.suffix != ".py":
            continue
        for function in python_functions(path, root):
            observed_functions.add(function.key)
            legacy_function_value = legacy_function_limits.get(function.key)
            legacy_function_limit = (
                int(legacy_function_value)
                if legacy_function_value is not None
                else None
            )
            function_allowed = (
                legacy_function_limit
                if legacy_function_limit is not None
                else default_function_limit
            )
            if function.line_count > function_allowed:
                failures.append(
                    f"{function.key}: {function.line_count} lines > allowed {function_allowed}"
                )
            elif (
                legacy_function_limit is not None
                and function.line_count < legacy_function_limit
            ):
                if function.line_count <= default_function_limit:
                    failures.append(
                        f"{function.key}: legacy function allowance "
                        f"{legacy_function_limit} is stale; remove it"
                    )
                else:
                    failures.append(
                        f"{function.key}: legacy function allowance "
                        f"{legacy_function_limit} is stale; shrink it to {function.line_count}"
                    )

    failures.extend(
        f"{path}: stale legacy file allowance"
        for path in sorted(set(legacy_limits) - observed_files)
    )
    failures.extend(
        f"{key}: stale legacy Python function allowance"
        for key in sorted(set(legacy_function_limits) - observed_functions)
    )
    return failures


def build_baseline(root: Path, *, file_limit: int, function_limit: int) -> dict[str, object]:
    """Build an exact legacy map; intended for deliberate ratchet maintenance."""
    root = root.resolve()
    legacy_files: dict[str, int] = {}
    legacy_functions: dict[str, int] = {}
    for path in iter_production_files(root):
        relative = path.relative_to(root).as_posix()
        actual = line_count(path)
        if actual > file_limit:
            legacy_files[relative] = actual
        if path.suffix == ".py":
            for function in python_functions(path, root):
                if function.line_count > function_limit:
                    legacy_functions[function.key] = function.line_count
    return {
        "version": 2,
        "default_max_lines": {"py": file_limit, "ts": file_limit, "tsx": file_limit},
        "legacy_max_lines": dict(sorted(legacy_files.items())),
        "default_max_python_function_lines": function_limit,
        "legacy_max_python_function_lines": dict(sorted(legacy_functions.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--file-limit", type=int, default=600)
    parser.add_argument("--function-limit", type=int, default=120)
    args = parser.parse_args()

    root = args.root.resolve()
    if args.write_baseline:
        baseline = build_baseline(
            root,
            file_limit=args.file_limit,
            function_limit=args.function_limit,
        )
        args.config.write_text(
            json.dumps(baseline, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote complexity baseline: {args.config}")
        return 0

    config = json.loads(args.config.read_text(encoding="utf-8"))
    failures = evaluate(root, config)
    if failures:
        print("Complexity ratchet failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Complexity ratchet passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
