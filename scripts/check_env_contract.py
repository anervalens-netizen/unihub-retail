#!/usr/bin/env python3
"""Reject drift between Retail env use, schema and process templates."""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "ops/config/retail-env.schema.json"
TEMPLATES = (
    ROOT / ".env.example",
    ROOT / "ops/config/.env.web.example",
    ROOT / "ops/config/.env.operations-worker.example",
    ROOT / "ops/config/.env.salary-export-worker.example",
    ROOT / "ops/config/.env.import-worker.example",
    ROOT / "ops/config/.env.migrations.example",
    ROOT / "ops/config/.env.frontend.example",
)
FRONTEND_ENV_FILES = (
    ROOT / "vite.config.ts",
    ROOT / "src/api/client.ts",
    ROOT / "src/main.tsx",
)


def _module_string_constants(tree: ast.AST) -> dict[str, str]:
    """Resolve same-module top-level string assignments without executing code.

    Only module-level ``NAME = "literal"`` assignments are accepted. Conditional
    branches, function-local bindings, imports, type annotations and any
    expression that is not a plain string literal are deliberately rejected.
    """

    constants: dict[str, str] = {}
    for node in getattr(tree, "body", []) or []:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            constants[target.id] = value.value
    return constants


def _resolve_constant_arg(
    first: ast.AST, constants: dict[str, str]
) -> str | None:
    """Return the string value for a direct literal or a same-module constant."""

    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    if isinstance(first, ast.Name) and first.id in constants:
        return constants[first.id]
    return None


def _python_env_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    constants = _module_string_constants(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        first = node.args[0]
        resolved = _resolve_constant_arg(first, constants)
        if resolved is None:
            continue
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "os"
            and function.attr == "getenv"
        ) or (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Attribute)
            and isinstance(function.value.value, ast.Name)
            and function.value.value.id == "os"
            and function.value.attr == "environ"
            and function.attr == "get"
        ):
            names.add(resolved)
    return names


def _used_env_names() -> set[str]:
    names: set[str] = set()
    for path in (ROOT / "backend").rglob("*.py"):
        if any(part in {"venv", "tests", "__pycache__", ".mypy_cache"} for part in path.parts):
            continue
        names.update(_python_env_names(path))
    pattern = re.compile(r"(?:import\.meta\.env|process\.env|env)\.([A-Z][A-Z0-9_]*)")
    for path in FRONTEND_ENV_FILES:
        names.update(pattern.findall(path.read_text(encoding="utf-8")))
    names.discard("MODE")  # Built-in Vite environment value.
    return names


def _validate_value(name: str, value: str, definition: dict[str, Any]) -> str | None:
    if value == "":
        return None
    allowed = definition.get("enum")
    if isinstance(allowed, list) and value not in allowed:
        return f"{name}: value is outside enum"
    pattern = definition.get("pattern")
    if isinstance(pattern, str) and re.search(pattern, value) is None:
        return f"{name}: value does not match schema"
    return None


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    properties: dict[str, dict[str, Any]] = schema["properties"]
    errors: list[str] = []
    template_names: set[str] = set()
    for template in TEMPLATES:
        values = dotenv_values(template, interpolate=True)
        for name, raw_value in values.items():
            template_names.add(name)
            if name not in properties:
                errors.append(f"{template.relative_to(ROOT)}: unknown variable {name}")
                continue
            issue = _validate_value(name, raw_value or "", properties[name])
            if issue:
                errors.append(f"{template.relative_to(ROOT)}: {issue}")

    used = _used_env_names()
    unknown = sorted(used - properties.keys())
    if unknown:
        errors.append("runtime variables missing from schema: " + ", ".join(unknown))
    documented = template_names | {
        name for name, definition in properties.items()
        if any(key.startswith("x-") for key in definition)
    }
    undocumented = sorted(used - documented)
    if undocumented:
        errors.append("runtime variables missing from templates: " + ", ".join(undocumented))

    example = dotenv_values(ROOT / ".env.example")
    if not str(example["DATABASE_URL"]).startswith("postgresql://unihub_web:"):
        errors.append(".env.example DATABASE_URL must use unihub_web")
    if not str(example["MIGRATION_DATABASE_URL"]).startswith(
        "postgresql://unihub_migration_runner:"
    ):
        errors.append(".env.example migration principal is stale")
    if "RUNTIME_DATABASE_URL" in example or "SYNC_TL_ASSIGNMENTS_ON_BOOT" in example:
        errors.append(".env.example retains a provisioning-only or dead variable")

    if errors:
        print("Environment contract failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        f"Environment contract valid: {len(properties)} variables, "
        f"{len(TEMPLATES)} templates, one python-dotenv parser"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
