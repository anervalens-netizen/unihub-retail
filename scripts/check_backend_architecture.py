#!/usr/bin/env python3
"""Enforce the Retail router/service/repository dependency direction and cycles."""
from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "backend"
LAYERS = ("routers", "services", "repositories", "domain")
CONTRACT_PATH = ROOT / "architecture_contract.json"
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


def main() -> None:
    paths = sorted(path for path in ROOT.rglob("*.py") if "tests" not in path.parts and "venv" not in path.parts)
    modules = {module_name(path): path for path in paths}
    edges: dict[str, set[str]] = defaultdict(set)
    violations: list[str] = []
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    categories = contract["service_data_access"]
    allowed_data_access = {
        module
        for modules_in_category in categories.values()
        for module in modules_in_category
    }
    duplicates = [
        module
        for module in allowed_data_access
        if sum(module in group for group in categories.values()) != 1
    ]
    if duplicates:
        violations.append("data-access modules have multiple categories: " + ", ".join(sorted(duplicates)))
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
    print(
        f"Backend architecture valid: {len(modules)} modules, acyclic graph, "
        f"{len(allowed_data_access)} classified hybrid data-access modules"
    )


if __name__ == "__main__":
    main()
