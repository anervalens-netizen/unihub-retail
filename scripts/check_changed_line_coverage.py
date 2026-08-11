#!/usr/bin/env python3
"""Require coverage for executable source lines changed against a base commit."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines(base: str) -> dict[str, set[int]]:
    output = subprocess.check_output(
        ["git", "diff", "--unified=0", "--diff-filter=AM", base, "--"],
        cwd=ROOT,
        text=True,
    )
    result: dict[str, set[int]] = {}
    current: str | None = None
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


def python_coverage(path: Path) -> dict[str, dict[int, bool]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[int, bool]] = {}
    for raw_name, details in payload.get("files", {}).items():
        name = raw_name.replace("\\", "/")
        if not name.startswith("backend/"):
            name = f"backend/{name}"
        covered = {int(line) for line in details.get("executed_lines", [])}
        missing = {int(line) for line in details.get("missing_lines", [])}
        result[name] = {line: line in covered for line in covered | missing}
    return result


def frontend_coverage(path: Path) -> dict[str, dict[int, bool]]:
    result: dict[str, dict[int, bool]] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("SF:"):
            raw = Path(line[3:])
            try:
                current = raw.resolve().relative_to(ROOT).as_posix()
            except ValueError:
                current = raw.as_posix().removeprefix("./")
            result.setdefault(current, {})
        elif current is not None and line.startswith("DA:"):
            number, hits, *_ = line[3:].split(",")
            result[current][int(number)] = int(hits) > 0
    return result


def include_source(name: str) -> bool:
    if name.startswith("backend/") and name.endswith(".py"):
        return not any(part in name for part in ("/tests/", "/scripts/", "/venv/"))
    if name.startswith("src/") and name.endswith((".ts", ".tsx")):
        return not (
            ".test." in name
            or name.startswith("src/test/")
            or name in {
                "src/api/generated/contracts.ts",
                "src/api/generated/runtime-schemas.ts",
            }
        )
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--backend-json", type=Path)
    parser.add_argument("--frontend-lcov", type=Path)
    parser.add_argument("--minimum", type=float, default=80.0)
    args = parser.parse_args()
    coverage: dict[str, dict[int, bool]] = {}
    if args.backend_json:
        coverage.update(python_coverage(args.backend_json))
    if args.frontend_lcov:
        coverage.update(frontend_coverage(args.frontend_lcov))

    relevant: list[tuple[str, int, bool]] = []
    for name, lines in changed_lines(args.base).items():
        if not include_source(name) or name not in coverage:
            continue
        for number in sorted(lines & coverage[name].keys()):
            relevant.append((name, number, coverage[name][number]))

    if not relevant:
        print("Changed-line coverage: no changed executable lines in this lane")
        return 0
    covered = sum(item[2] for item in relevant)
    percent = covered * 100 / len(relevant)
    missing = [f"{name}:{line}" for name, line, hit in relevant if not hit]
    print(
        f"Changed-line coverage: {covered}/{len(relevant)} = {percent:.2f}% "
        f"(minimum {args.minimum:.2f}%)"
    )
    if missing:
        print("Uncovered changed lines: " + ", ".join(missing[:40]))
    return 0 if percent >= args.minimum else 1


if __name__ == "__main__":
    raise SystemExit(main())
