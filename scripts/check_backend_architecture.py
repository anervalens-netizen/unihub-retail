#!/usr/bin/env python3
"""Enforce the Retail router/service/repository dependency direction and cycles."""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "backend"
LAYERS = ("routers", "services", "repositories", "domain")


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


def main() -> None:
    paths = sorted(path for path in ROOT.rglob("*.py") if "tests" not in path.parts and "venv" not in path.parts)
    modules = {module_name(path): path for path in paths}
    edges: dict[str, set[str]] = defaultdict(set)
    violations: list[str] = []
    for source, path in modules.items():
        source_layer = source.split(".", 1)[0]
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
    if violations:
        raise SystemExit("Backend architecture violations:\n  - " + "\n  - ".join(sorted(set(violations))))
    print(f"Backend architecture valid: {len(modules)} modules, acyclic dependency graph")


if __name__ == "__main__":
    main()
