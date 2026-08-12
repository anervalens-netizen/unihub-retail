#!/usr/bin/env python3
"""Run locked Target mutations and the deterministic 200-row p95 gate."""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MUTATIONS = {
    "money_half_up",
    "floor_strict",
    "cap_strict",
    "budget_floor_inclusive",
    "budget_cap_inclusive",
    "active_floor_strict",
    "active_cap_strict",
    "zero_reserve_boundary",
    "fractional_remainder_descending",
    "site_code_tiebreak",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _function_segment(source: str, function_name: str) -> tuple[int, int]:
    tree = ast.parse(source)
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"function selector {function_name!r} matched {len(matches)} times")
    node = matches[0]
    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[: node.lineno - 1])
    end = sum(len(line) for line in lines[: node.end_lineno])
    return start, end


def _text_mutation(source: str, mutation: dict[str, Any]) -> str:
    start, end = _function_segment(source, str(mutation["function"]))
    segment = source[start:end]
    selector = str(mutation["selector"])
    if segment.count(selector) != 1:
        raise RuntimeError(
            f"mutation {mutation['id']} selector matched {segment.count(selector)} times"
        )
    return source[:start] + segment.replace(selector, str(mutation["replacement"]), 1) + source[end:]


class _SortKeyMutator(ast.NodeTransformer):
    def __init__(self, mutation_id: str, function_name: str) -> None:
        self.mutation_id = mutation_id
        self.function_name = function_name
        self.in_function = False
        self.matches = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        was_in_function = self.in_function
        self.in_function = node.name == self.function_name
        transformed = self.generic_visit(node)
        self.in_function = was_in_function
        return transformed

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if not self.in_function or not isinstance(node.func, ast.Name) or node.func.id != "sorted":
            return node
        key = next((keyword.value for keyword in node.keywords if keyword.arg == "key"), None)
        if not isinstance(key, ast.Lambda) or not isinstance(key.body, ast.Tuple):
            return node
        if len(key.body.elts) != 3:
            return node
        rendered = [ast.unparse(item) for item in key.body.elts]
        if rendered != ["-candidate[0]", "candidate[1]", "candidate[2]"]:
            return node
        index = 0 if self.mutation_id == "fractional_remainder_descending" else 1
        replacement = "candidate[0]" if index == 0 else "candidate[2]"
        key.body.elts[index] = ast.copy_location(ast.parse(replacement, mode="eval").body, key.body.elts[index])
        self.matches += 1
        return node


def _ast_mutation(source: str, mutation: dict[str, Any]) -> str:
    tree = ast.parse(source)
    mutator = _SortKeyMutator(str(mutation["id"]), str(mutation["function"]))
    mutated = mutator.visit(tree)
    if mutator.matches != 1:
        raise RuntimeError(
            f"mutation {mutation['id']} AST selector matched {mutator.matches} times"
        )
    ast.fix_missing_locations(mutated)
    return ast.unparse(mutated) + "\n"


def _mutated_source(source: str, mutation: dict[str, Any]) -> str:
    if "selector" in mutation:
        return _text_mutation(source, mutation)
    if "ast_selector" in mutation:
        return _ast_mutation(source, mutation)
    raise RuntimeError(f"mutation {mutation['id']} has no selector")


def _run_mutation(
    source: str,
    test_source: str,
    mutation: dict[str, Any],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"target-mutation-{mutation['id']}-") as raw_dir:
        temp = Path(raw_dir)
        package = temp / "backend/services/target_calculator"
        tests = temp / "backend/tests"
        package.mkdir(parents=True)
        tests.mkdir(parents=True)
        (temp / "backend/services/__init__.py").write_text("", encoding="utf-8")
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "calculations.py").write_text(
            _mutated_source(source, mutation),
            encoding="utf-8",
        )
        (tests / "test_target_allocator_exact.py").write_text(test_source, encoding="utf-8")
        test_id = (
            "backend/tests/test_target_allocator_exact.py::"
            + str(mutation["killing_test"])
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                test_id,
            ],
            cwd=temp,
            env={**os.environ, "PYTHONPATH": str(temp / "backend")},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        combined = (result.stdout + "\n" + result.stderr).strip()
        killed = result.returncode == 1 and "1 failed" in combined and "ERROR" not in combined
        return {
            "id": mutation["id"],
            "killing_test": mutation["killing_test"],
            "returncode": result.returncode,
            "killed": killed,
            "output_tail": combined[-800:],
        }


def _benchmark(seed: int) -> dict[str, Any]:
    from services.target_calculator.calculations import allocate_with_bounds

    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for index in range(200):
        floor = Decimal(rng.randint(0, 5_000_000)) / 100
        rows.append(
            {
                "site_code": f"BENCH-{index:03d}",
                "calculated_weight": Decimal(rng.randint(0, 100_000)),
                "floor_target": floor,
                "cap_target": floor + Decimal(rng.randint(0, 5_000_000)) / 100,
                "flags": [],
            }
        )
    floor_total = sum((row["floor_target"] for row in rows), Decimal())
    cap_total = sum((row["cap_target"] for row in rows), Decimal())
    budget = ((floor_total + cap_total) / 2).quantize(Decimal("0.01"))

    def sample() -> int:
        candidate = deepcopy(rows)
        started = time.perf_counter_ns()
        allocated, warnings = allocate_with_bounds(candidate, budget)
        elapsed = time.perf_counter_ns() - started
        if warnings or sum((row["proposed_target"] for row in allocated), Decimal()) != budget:
            raise RuntimeError("benchmark allocation contract failed")
        return elapsed

    for _ in range(20):
        sample()
    samples_ns = sorted(sample() for _ in range(200))
    p95_ns = samples_ns[math.ceil(0.95 * len(samples_ns)) - 1]
    return {
        "rows": 200,
        "warmups": 20,
        "samples": 200,
        "nearest_rank": 190,
        "p95_ms": p95_ns / 1_000_000,
        "limit_ms": 100,
        "passed": p95_ns < 100_000_000,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    mutations = contract.get("mutations")
    if not isinstance(mutations, list):
        raise SystemExit("mutation contract must contain a mutations list")
    mutation_ids = [str(item.get("id")) for item in mutations]
    if len(mutation_ids) != 10 or set(mutation_ids) != EXPECTED_MUTATIONS:
        raise SystemExit("mutation contract IDs differ from the locked ten")

    source_path = ROOT / str(contract["source"])
    exact_test_path = ROOT / "backend/tests/test_target_allocator_exact.py"
    source = source_path.read_text(encoding="utf-8")
    test_source = exact_test_path.read_text(encoding="utf-8")
    results = [_run_mutation(source, test_source, mutation) for mutation in mutations]
    benchmark = _benchmark(args.seed)
    killed = sum(bool(result["killed"]) for result in results)
    passed = killed == 10 and benchmark["passed"]
    evidence = {
        "schema_version": 1,
        "result": "PASS" if passed else "FAIL",
        "seed": args.seed,
        "source": str(source_path.relative_to(ROOT)),
        "source_sha256": _sha256(source_path),
        "contract": str(args.contract),
        "contract_sha256": _sha256(args.contract),
        "mutations_total": 10,
        "mutations_killed": killed,
        "mutation_score_percent": killed * 10,
        "mutations": results,
        "benchmark": benchmark,
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"result": evidence["result"], "mutations_killed": killed, "p95_ms": benchmark["p95_ms"]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
