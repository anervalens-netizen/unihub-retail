#!/usr/bin/env python3
"""Enforce Retail backend architecture boundaries and direct-DB exception ratchets."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1] / "backend"
REPO_ROOT = ROOT.parent
LAYERS = ("routers", "services", "repositories", "domain")
CONTRACT_PATH = ROOT / "architecture_contract.json"
DIRECT_DB_BASELINE_PATH = ROOT / "architecture_direct_db_baseline_v1.json"
DIRECT_DB_BASELINE_SHA256 = "769041fb94bc302a4d0295822d4a1060f2628d6b11e277595bdc6cac3d1a980c"
DIRECT_DB_CATEGORIES = (
    "query_services",
    "transaction_scripts",
    "orchestration_boundaries",
)
DB_METHODS = {
    "acquire", "copy_records_to_table", "execute", "executemany", "fetch",
    "fetchrow", "fetchval", "transaction",
}
SQL_START = re.compile(
    r"(?:^|\n)\s*(?:WITH|SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|REFRESH)\b",
    re.IGNORECASE,
)


def module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def direct_database_access(path: Path) -> bool:
    """Detect SQL literals and asyncpg-style calls, excluding unrelated APIs."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and SQL_START.search(node.value):
            return True
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in DB_METHODS:
            continue
        receiver = ast.unparse(node.func.value)
        if receiver in {
            "pool", "conn", "connection", "self.pool", "self._pool",
            "self.repo.pool", "context.repo.pool", "active_pool",
        } or receiver.endswith(("_pool", ".pool")):
            return True
    return False


def _category_map(raw: Any, *, label: str) -> tuple[dict[str, str], list[str]]:
    violations: list[str] = []
    if not isinstance(raw, dict):
        return {}, [f"{label} service_data_access must be an object"]

    actual_categories = set(raw)
    expected_categories = set(DIRECT_DB_CATEGORIES)
    missing = sorted(expected_categories - actual_categories)
    extra = sorted(actual_categories - expected_categories)
    if missing:
        violations.append(f"{label} missing data-access categories: " + ", ".join(missing))
    if extra:
        violations.append(f"{label} has unknown data-access categories: " + ", ".join(extra))

    module_categories: dict[str, str] = {}
    for category in DIRECT_DB_CATEGORIES:
        modules = raw.get(category, [])
        if not isinstance(modules, list) or any(not isinstance(module, str) or not module for module in modules):
            violations.append(f"{label} category {category} must be a list of non-empty module names")
            continue
        if len(modules) != len(set(modules)):
            violations.append(f"{label} category {category} contains duplicate module entries")
        for module in modules:
            previous = module_categories.get(module)
            if previous is not None and previous != category:
                violations.append(
                    f"{label} data-access module {module} appears in multiple categories: "
                    f"{previous}, {category}"
                )
            else:
                module_categories[module] = category
    return module_categories, violations


def _git_text(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _ci_previous_contract() -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """Load the exact previous architecture contract in CI, failing closed on lookup errors."""
    event_name = os.environ.get("GITHUB_EVENT_NAME")
    if not event_name:
        return None, None, []

    previous_sha: str | None = None
    try:
        if event_name == "pull_request":
            event_path = os.environ.get("GITHUB_EVENT_PATH")
            if not event_path:
                return None, None, ["GITHUB_EVENT_PATH missing for architecture ratchet"]
            event = json.loads(Path(event_path).read_text(encoding="utf-8"))
            previous_sha = event.get("pull_request", {}).get("base", {}).get("sha")
            if not isinstance(previous_sha, str) or re.fullmatch(r"[0-9a-f]{40}", previous_sha) is None:
                return None, None, ["pull request base SHA missing or invalid for architecture ratchet"]
        elif event_name == "workflow_dispatch":
            previous_sha = os.environ.get("EXACT_MAIN_FIRST_PARENT") or _git_text("rev-parse", "HEAD^1").strip()
            if re.fullmatch(r"[0-9a-f]{40}", previous_sha) is None:
                return None, None, ["previous main SHA missing or invalid for architecture ratchet"]
        else:
            return None, None, []

        raw = _git_text("show", f"{previous_sha}:backend/architecture_contract.json")
        previous_contract = json.loads(raw)
        if not isinstance(previous_contract, dict):
            return None, previous_sha, ["previous architecture contract must be an object"]
        return previous_contract, previous_sha, []
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        return None, previous_sha, [
            f"unable to load previous architecture contract at {previous_sha or 'unknown'}: "
            f"{type(exc).__name__}"
        ]


def evaluate_data_access_ratchet(
    contract: dict[str, Any],
    baseline: dict[str, Any],
    *,
    previous_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Require direct-DB exceptions to shrink monotonically from the pinned baseline."""
    violations: list[str] = []
    if baseline.get("version") != 1:
        violations.append("direct DB architecture baseline version must be 1")

    current_map, current_violations = _category_map(
        contract.get("service_data_access"),
        label="current architecture contract",
    )
    baseline_map, baseline_violations = _category_map(
        baseline.get("service_data_access"),
        label="direct DB architecture baseline",
    )
    violations.extend(current_violations)
    violations.extend(baseline_violations)

    expected_count = baseline.get("baseline_exception_count")
    if not isinstance(expected_count, int) or expected_count < 0:
        violations.append("direct DB architecture baseline_exception_count must be a non-negative integer")
    elif expected_count != len(baseline_map):
        violations.append(
            "direct DB architecture baseline_exception_count does not match baseline modules: "
            f"{expected_count} != {len(baseline_map)}"
        )

    for module, current_category in sorted(current_map.items()):
        baseline_category = baseline_map.get(module)
        if baseline_category is None:
            violations.append(f"new direct DB architecture exception is not in pinned baseline: {module}")
        elif baseline_category != current_category:
            violations.append(
                f"direct DB architecture exception category changed for {module}: "
                f"{baseline_category} -> {current_category}"
            )

    previous_map: dict[str, str] | None = None
    retired_since_previous: list[str] = []
    if previous_contract is not None:
        previous_map, previous_violations = _category_map(
            previous_contract.get("service_data_access"),
            label="previous architecture contract",
        )
        violations.extend(previous_violations)
        for module, current_category in sorted(current_map.items()):
            previous_category = previous_map.get(module)
            if previous_category is None:
                violations.append(
                    f"direct DB architecture exception added since previous contract: {module}"
                )
            elif previous_category != current_category:
                violations.append(
                    f"direct DB architecture exception category changed since previous contract for {module}: "
                    f"{previous_category} -> {current_category}"
                )
        retired_since_previous = sorted(set(previous_map) - set(current_map))

    retired = sorted(set(baseline_map) - set(current_map))
    return {
        "violations": sorted(set(violations)),
        "current_modules": set(current_map),
        "baseline_modules": set(baseline_map),
        "previous_modules": set(previous_map or {}),
        "retired_modules": retired,
        "retired_since_previous": retired_since_previous,
    }


def main() -> None:
    paths = sorted(path for path in ROOT.rglob("*.py") if "tests" not in path.parts and "venv" not in path.parts)
    modules = {module_name(path): path for path in paths}
    edges: dict[str, set[str]] = defaultdict(set)
    violations: list[str] = []

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    baseline_bytes = DIRECT_DB_BASELINE_PATH.read_bytes()
    actual_baseline_sha256 = hashlib.sha256(baseline_bytes).hexdigest()
    if actual_baseline_sha256 != DIRECT_DB_BASELINE_SHA256:
        violations.append(
            "direct DB architecture baseline digest mismatch: "
            f"{actual_baseline_sha256} != {DIRECT_DB_BASELINE_SHA256}"
        )
    baseline = json.loads(baseline_bytes.decode("utf-8"))
    previous_contract, previous_sha, previous_violations = _ci_previous_contract()
    violations.extend(previous_violations)
    ratchet = evaluate_data_access_ratchet(
        contract,
        baseline,
        previous_contract=previous_contract,
    )
    violations.extend(ratchet["violations"])
    allowed_data_access = ratchet["current_modules"]

    for source, path in modules.items():
        source_layer = source.split(".", 1)[0]
        accesses_database = direct_database_access(path)
        if source_layer == "routers" and accesses_database:
            violations.append(f"{source} contains direct database access")
        if source_layer == "services" and accesses_database and source not in allowed_data_access:
            violations.append(f"{source} has unclassified direct database access")
        for target in imports(path):
            candidate = target
            while candidate and candidate not in modules:
                candidate = candidate.rpartition(".")[0]
            if candidate:
                edges[source].add(candidate)
            target_layer = target.split(".", 1)[0]
            if source_layer == "routers" and target_layer == "repositories":
                violations.append(f"{source} imports concrete {target}")
            if source_layer == "repositories" and target_layer in {"routers", "services"}:
                violations.append(f"{source} imports higher layer {target}")
            if source_layer == "services" and target_layer == "routers":
                violations.append(f"{source} imports HTTP layer {target}")
            if source_layer == "domain" and target_layer in {"routers", "services", "repositories"}:
                violations.append(f"{source} domain imports infrastructure {target}")

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> None:
        if node in visiting:
            start = stack.index(node)
            violations.append("dependency cycle: " + " -> ".join(stack[start:] + [node]))
            return
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)
        for target in sorted(edges[node]):
            visit(target)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for module in sorted(modules):
        visit(module)
    for module in sorted(allowed_data_access):
        path = modules.get(module)
        if path is None:
            violations.append(f"architecture allowlist references missing module {module}")
        elif not direct_database_access(path):
            violations.append(f"stale data-access allowlist entry {module}")
    if violations:
        raise SystemExit("Backend architecture violations:\n  - " + "\n  - ".join(sorted(set(violations))))

    baseline_count = len(ratchet["baseline_modules"])
    current_count = len(allowed_data_access)
    retired_count = len(ratchet["retired_modules"])
    previous_label = f", previous {previous_sha[:12]}" if previous_sha else ""
    print(
        f"Backend architecture valid: {len(modules)} modules, acyclic graph, "
        f"direct DB exceptions {current_count}/{baseline_count}, retired {retired_count}"
        f"{previous_label}"
    )


if __name__ == "__main__":
    main()
