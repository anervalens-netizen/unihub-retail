#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_THRESHOLDS = BACKEND_DIR / "critical_coverage_thresholds.json"


@dataclass(frozen=True)
class CoverageResult:
    module: str
    covered: float | None
    threshold: float

    @property
    def passed(self) -> bool:
        return self.covered is not None and self.covered >= self.threshold


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def evaluate_coverage(
    report: dict[str, Any],
    thresholds: dict[str, Any],
) -> list[CoverageResult]:
    files = report.get("files")
    if not isinstance(files, dict):
        raise ValueError("Coverage report does not contain a files object")

    results: list[CoverageResult] = []
    for module, raw_threshold in sorted(thresholds.items()):
        threshold = float(raw_threshold)
        details = files.get(module)
        covered: float | None = None
        if isinstance(details, dict):
            summary = details.get("summary")
            if isinstance(summary, dict) and "percent_covered" in summary:
                covered = float(summary["percent_covered"])
        results.append(
            CoverageResult(
                module=module,
                covered=covered,
                threshold=threshold,
            )
        )
    return results


def print_results(results: list[CoverageResult]) -> None:
    print("Critical module coverage:")
    for result in results:
        covered = "MISSING" if result.covered is None else f"{result.covered:.2f}%"
        status = "PASS" if result.passed else "FAIL"
        print(
            f"  {status:4}  {result.module:<38} "
            f"{covered:>8}  minimum {result.threshold:.2f}%"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail when a critical module drops below its coverage floor."
    )
    parser.add_argument("report", type=Path, help="coverage.py JSON report")
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=DEFAULT_THRESHOLDS,
        help=f"threshold map (default: {DEFAULT_THRESHOLDS})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = load_json(args.report)
    thresholds = load_json(args.thresholds)
    results = evaluate_coverage(report, thresholds)
    print_results(results)
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
