#!/usr/bin/env python3
"""Verify the frozen Python AST-complexity contract without rewriting it."""
from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Iterable, Iterator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = Path(__file__).with_name("python-complexity-contract-v1.json")
EXCLUDED_PARTS = {"tests", "venv", ".venv", "__pycache__"}
COUNTED_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.TryStar,
    ast.With,
    ast.AsyncWith,
    ast.IfExp,
    ast.Assert,
    ast.comprehension,
    ast.Match,
    ast.ExceptHandler,
)


@dataclass(frozen=True, slots=True)
class FunctionMetric:
    path: str
    function: str
    start_line: int
    end_line: int
    line_count: int
    complexity_proxy: int


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _complexity(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(child, COUNTED_NODES):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(1, len(child.values) - 1)
    return score


def _function_metrics(path: Path, root: Path) -> list[FunctionMetric]:
    relative = path.relative_to(root).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
    result: list[FunctionMetric] = []

    def visit(body: Iterable[ast.stmt], prefix: tuple[str, ...] = ()) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, (*prefix, node.name))
                continue
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            function = ".".join((*prefix, node.name))
            end_line = node.end_lineno or node.lineno
            result.append(
                FunctionMetric(
                    path=relative,
                    function=function,
                    start_line=node.lineno,
                    end_line=end_line,
                    line_count=end_line - node.lineno + 1,
                    complexity_proxy=_complexity(node),
                )
            )
            visit(node.body, (*prefix, node.name, "<locals>"))

    visit(tree.body)
    return result


def iter_python_files(root: Path) -> Iterator[Path]:
    backend = root / "backend"
    for path in sorted(backend.rglob("*.py")):
        relative = path.relative_to(root)
        if path.is_file() and not any(part in EXCLUDED_PARTS for part in relative.parts):
            yield path


def collect_metrics(root: Path) -> list[FunctionMetric]:
    return [
        metric
        for path in iter_python_files(root)
        for metric in _function_metrics(path, root)
    ]


def _contract_payload(contract: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in contract.items() if key != "contract_payload_sha256"}


def _git_sha(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def evaluate(root: Path, contract: dict[str, object]) -> dict[str, object]:
    expected_payload_sha = str(contract.get("contract_payload_sha256") or "")
    actual_payload_sha = canonical_sha256(_contract_payload(contract))
    violations: list[str] = []
    if not expected_payload_sha or actual_payload_sha != expected_payload_sha:
        violations.append("contract payload digest mismatch")

    metrics = collect_metrics(root)
    by_identity = {(item.path, item.function): item for item in metrics}
    entries = contract.get("entries")
    gates = contract.get("release_b_gates")
    if not isinstance(entries, list) or not isinstance(gates, dict):
        raise ValueError("Invalid Python complexity contract structure")
    locked = {
        (str(entry["path"]), str(entry["function"])): entry
        for entry in entries
        if isinstance(entry, dict)
    }
    at_least_20 = [item for item in metrics if item.complexity_proxy >= 20]
    at_least_30 = [item for item in metrics if item.complexity_proxy >= 30]
    new_at_least_20 = [
        item for item in at_least_20 if (item.path, item.function) not in locked
    ]
    wp11_violations = [
        item
        for identity, entry in locked.items()
        if bool(entry.get("wp11_mandatory_below_20"))
        and (item := by_identity.get(identity)) is not None
        and item.complexity_proxy >= 20
    ]
    mandatory_30_violations = [
        item
        for identity, entry in locked.items()
        if bool(entry.get("mandatory_below_30"))
        and (item := by_identity.get(identity)) is not None
        and item.complexity_proxy >= 30
    ]
    maximum = max((item.complexity_proxy for item in metrics), default=0)
    limits = {
        "complexity_proxy_gte_20": int(gates["complexity_proxy_gte_20_maximum"]),
        "complexity_proxy_gte_30": int(gates["complexity_proxy_gte_30_maximum"]),
        "maximum_complexity_proxy": int(gates["maximum_complexity_proxy"]),
        "new_function_complexity_proxy": int(gates["new_function_complexity_proxy_maximum"]),
        "wp11_locked_entries": int(gates["wp11_locked_entries_maximum"]),
    }
    if len(at_least_20) > limits["complexity_proxy_gte_20"]:
        violations.append(
            f"complexity_proxy >=20 count {len(at_least_20)} > {limits['complexity_proxy_gte_20']}"
        )
    if len(at_least_30) > limits["complexity_proxy_gte_30"]:
        violations.append(
            f"complexity_proxy >=30 count {len(at_least_30)} > {limits['complexity_proxy_gte_30']}"
        )
    if maximum > limits["maximum_complexity_proxy"]:
        violations.append(
            f"maximum complexity_proxy {maximum} > {limits['maximum_complexity_proxy']}"
        )
    violations.extend(
        f"new function {item.path}::{item.function} complexity_proxy "
        f"{item.complexity_proxy} > {limits['new_function_complexity_proxy']}"
        for item in new_at_least_20
    )
    violations.extend(
        f"WP-11 entry {item.path}::{item.function} complexity_proxy "
        f"{item.complexity_proxy} > {limits['wp11_locked_entries']}"
        for item in wp11_violations
    )
    violations.extend(
        f"mandatory entry {item.path}::{item.function} complexity_proxy "
        f"{item.complexity_proxy} >=30"
        for item in mandatory_30_violations
    )
    return {
        "result": "PASS" if not violations else "FAIL",
        "source_sha": _git_sha(root),
        "contract_payload_sha256": actual_payload_sha,
        "expected_contract_payload_sha256": expected_payload_sha,
        "metrics": {
            "production_functions": len(metrics),
            "complexity_proxy_gte_20": len(at_least_20),
            "complexity_proxy_gte_30": len(at_least_30),
            "maximum_complexity_proxy": maximum,
            "new_function_gte_20": len(new_at_least_20),
            "wp11_locked_gte_20": len(wp11_violations),
            "mandatory_locked_gte_30": len(mandatory_30_violations),
        },
        "limits": limits,
        "gte_20_entries": [asdict(item) for item in at_least_20],
        "gte_30_entries": [asdict(item) for item in at_least_30],
        "new_gte_20_entries": [asdict(item) for item in new_at_least_20],
        "wp11_violations": [asdict(item) for item in wp11_violations],
        "mandatory_30_violations": [asdict(item) for item in mandatory_30_violations],
        "violations": violations,
    }


def _write_evidence(path: Path, evidence: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    evidence = evaluate(args.root.resolve(), contract)
    _write_evidence(args.evidence, evidence)
    metrics = evidence["metrics"]
    assert isinstance(metrics, dict)
    print(
        f"Python complexity contract {evidence['result']}: "
        f">=20 {metrics['complexity_proxy_gte_20']}, "
        f">=30 {metrics['complexity_proxy_gte_30']}, "
        f"max {metrics['maximum_complexity_proxy']}, "
        f"new>=20 {metrics['new_function_gte_20']}, "
        f"WP11>=20 {metrics['wp11_locked_gte_20']}"
    )
    for violation in evidence["violations"]:
        print(f"- {violation}")
    return 0 if evidence["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
