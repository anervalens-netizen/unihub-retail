#!/usr/bin/env python3
"""Verify the frozen query-parameter inventory against code and FastAPI runtime."""
from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _typed_schema(schema: dict[str, Any], expected_type: str) -> dict[str, Any] | None:
    if schema.get("type") == expected_type:
        return schema
    for keyword in ("anyOf", "oneOf"):
        for option in schema.get(keyword, []):
            if option.get("type") == expected_type:
                return option
    return None


def _operation_parameters(openapi: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    found: dict[tuple[str, str, str], dict[str, Any]] = {}
    for route, path_item in openapi["paths"].items():
        for method, operation in path_item.items():
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
                continue
            for parameter in operation.get("parameters", []):
                if parameter.get("in") != "query":
                    continue
                key = (method.upper(), route, parameter["name"])
                if key in found:
                    raise ValueError(f"duplicate OpenAPI query parameter: {key}")
                found[key] = parameter
    return found


def _policy_entries(policy: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    found: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in policy.get("parameters", []):
        key = (entry["method"].upper(), entry["path"], entry["parameter"])
        if key in found:
            raise ValueError(f"duplicate policy query parameter: {key}")
        found[key] = entry
    return found


def _schema_errors(
    key: tuple[str, str, str],
    schema: dict[str, Any],
    policy_name: str,
    policies: dict[str, Any],
) -> list[str]:
    definition = policies[policy_name]
    prefix = "/".join(key)
    errors: list[str] = []

    def expect_bound(schema_type: str, name: str, expected: Any) -> None:
        branch = _typed_schema(schema, schema_type)
        actual = None if branch is None else branch.get(name)
        if actual != expected:
            errors.append(f"{prefix}: {name} expected {expected!r}, got {actual!r}")

    if policy_name == "month_str":
        expect_bound("string", "pattern", definition["pattern"])
    elif policy_name in {
        "month_1_12",
        "year_2018_2100",
        "limit_1_100",
        "limit_1_500",
        "limit_1_2000",
        "offset_0_100000",
    }:
        expect_bound("integer", "minimum", definition["minimum"])
        expect_bound("integer", "maximum", definition["maximum"])
    elif policy_name in {"bounded_text_32", "bounded_text_120", "bounded_code_64"}:
        branch = _typed_schema(schema, "string")
        if branch is None or branch.get("minLength", 0) < definition["minLength"]:
            errors.append(f"{prefix}: string minimum is weaker than policy")
        if branch is None or branch.get("maxLength", float("inf")) > definition["maxLength"]:
            errors.append(f"{prefix}: string maximum is weaker than policy")
    elif policy_name in {"bounded_code_list_100x100", "bounded_list_100x100"}:
        branch = _typed_schema(schema, "array")
        if branch is None:
            errors.append(f"{prefix}: array schema missing")
        else:
            if branch.get("maxItems") != definition["maxItems"]:
                errors.append(f"{prefix}: maxItems is not {definition['maxItems']}")
            item = branch.get("items", {})
            for field in ("minLength", "maxLength"):
                if item.get(field) != definition["items"][field]:
                    errors.append(
                        f"{prefix}: items.{field} is not {definition['items'][field]}"
                    )
    elif policy_name == "bounded_month_window":
        integer = _typed_schema(schema, "integer")
        string = _typed_schema(schema, "string")
        valid_integer = integer is not None and integer.get("minimum", 0) >= 1 and integer.get("maximum", float("inf")) <= 24
        valid_string = string is not None and string.get("minLength", 0) >= 1 and string.get("maxLength", float("inf")) <= 120
        if not (valid_integer or valid_string):
            errors.append(f"{prefix}: bounded month window missing")
    elif policy_name == "finite_enum":
        branch = _typed_schema(schema, "string")
        values = [] if branch is None else branch.get("enum", [])
        pattern = None if branch is None else branch.get("pattern")
        if not values and pattern != "^(sales_value|units)$":
            errors.append(f"{prefix}: finite enum/pattern missing")
    elif policy_name == "boolean":
        if _typed_schema(schema, "boolean") is None:
            errors.append(f"{prefix}: boolean schema missing")
    elif policy_name == "iso_date":
        branch = _typed_schema(schema, "string")
        if branch is None or branch.get("format") != "date":
            errors.append(f"{prefix}: ISO date schema missing")
    elif policy_name == "bounded_integer_existing":
        branch = _typed_schema(schema, "integer")
        if branch is None or not all(isinstance(branch.get(name), (int, float)) for name in ("minimum", "maximum")):
            errors.append(f"{prefix}: finite integer minimum/maximum missing")
    else:
        errors.append(f"{prefix}: unsupported policy {policy_name}")
    return errors


def _router_prefix(tree: ast.Module) -> str:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "router" for target in node.targets):
            if isinstance(node.value, ast.Call):
                for keyword in node.value.keywords:
                    if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                        return str(keyword.value.value)
    return ""


def _static_query_inventory() -> set[tuple[str, str, str]]:
    found: set[tuple[str, str, str]] = set()
    for path in sorted((BACKEND / "routers").glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        prefix = _router_prefix(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            operations: list[tuple[str, str]] = []
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                method = decorator.func.attr.upper()
                if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
                    continue
                if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                    continue
                operations.append((method, prefix + str(decorator.args[0].value)))
            if not operations:
                continue
            positional = node.args.posonlyargs + node.args.args
            defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
            pairs = list(zip(positional, defaults, strict=True)) + list(zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True))
            for argument, default in pairs:
                if not isinstance(default, ast.Call):
                    continue
                function = default.func
                if not (isinstance(function, ast.Name) and function.id == "Query"):
                    continue
                for method, route in operations:
                    found.add((method, route, argument.arg))
    return found


def _valid_value(policy_name: str, schema: dict[str, Any]) -> str:
    if policy_name == "month_str":
        return "2026-08"
    if policy_name == "bounded_month_window":
        return "2026-08"
    if policy_name == "iso_date":
        return "2026-08-01"
    if policy_name == "boolean":
        return "true"
    if policy_name == "finite_enum":
        branch = _typed_schema(schema, "string") or {}
        values = branch.get("enum", [])
        return str(values[0] if values else "sales_value")
    if policy_name.startswith("year_"):
        return "2026"
    if policy_name.startswith("month_"):
        return "6"
    if policy_name.startswith("limit_"):
        return "1"
    if policy_name.startswith("offset_"):
        return "0"
    if policy_name == "bounded_integer_existing":
        branch = _typed_schema(schema, "integer") or {}
        return str(branch.get("minimum", 1))
    return "x"


def _invalid_values(policy_name: str, schema: dict[str, Any], definition: dict[str, Any]) -> list[list[str]]:
    if policy_name == "month_str":
        return [["2026-13"]]
    if policy_name == "bounded_month_window":
        branch = _typed_schema(schema, "integer")
        if branch is not None:
            return [[str(int(branch["minimum"]) - 1)], [str(int(branch["maximum"]) + 1)]]
        return [["invalid-month"], ["x" * 121]]
    if policy_name in {"month_1_12", "year_2018_2100", "limit_1_100", "limit_1_500", "limit_1_2000", "offset_0_100000"}:
        return [[str(int(definition["minimum"]) - 1)], [str(int(definition["maximum"]) + 1)]]
    if policy_name in {"bounded_text_32", "bounded_text_120", "bounded_code_64"}:
        return [[""], ["x" * (int(definition["maxLength"]) + 1)]]
    if policy_name in {"bounded_code_list_100x100", "bounded_list_100x100"}:
        return [["x"] * (int(definition["maxItems"]) + 1), ["x" * (int(definition["items"]["maxLength"]) + 1)]]
    if policy_name == "finite_enum":
        return [["__invalid_enum__"]]
    if policy_name == "boolean":
        return [["not-a-boolean"]]
    if policy_name == "iso_date":
        return [["not-a-date"]]
    if policy_name == "bounded_integer_existing":
        branch = _typed_schema(schema, "integer") or {}
        return [[str(int(branch["minimum"]) - 1)], [str(int(branch["maximum"]) + 1)]]
    raise ValueError(f"unsupported runtime policy: {policy_name}")


def _override_route_dependencies(app: Any) -> None:
    async def stub_dependency() -> None:
        return None

    for included in app.routes:
        router = getattr(included, "original_router", None)
        include_context = getattr(included, "include_context", None)
        for dependency in getattr(include_context, "dependencies", []):
            app.dependency_overrides[dependency.dependency] = stub_dependency
        for route in getattr(router, "routes", []):
            dependant = getattr(route, "dependant", None)
            if dependant is None:
                continue
            stack = list(dependant.dependencies)
            while stack:
                current = stack.pop()
                app.dependency_overrides[current.call] = stub_dependency
                stack.extend(current.dependencies)


async def _runtime_422_checks(
    app: Any,
    openapi: dict[str, Any],
    current: dict[tuple[str, str, str], dict[str, Any]],
    entries: dict[tuple[str, str, str], dict[str, Any]],
    policies: dict[str, Any],
) -> tuple[int, list[str]]:
    _override_route_dependencies(app)
    logging.getLogger("unihub.request").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    failures: list[str] = []
    checks = 0
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://contract.invalid") as client:
            for key, entry in entries.items():
                method, route, name = key
                operation = openapi["paths"][route][method.lower()]
                base_params: list[tuple[str, str]] = []
                for parameter in operation.get("parameters", []):
                    if parameter.get("in") != "query" or parameter["name"] == name or not parameter.get("required"):
                        continue
                    other_key = (method, route, parameter["name"])
                    other_entry = entries[other_key]
                    base_params.append(
                        (
                            parameter["name"],
                            _valid_value(other_entry["policy"], parameter["schema"]),
                        )
                    )
                runtime_path = re.sub(r"\{[^}]+\}", "contract", route)
                schema = current[key]["schema"]
                for invalid_group in _invalid_values(entry["policy"], schema, policies[entry["policy"]]):
                    checks += 1
                    params = list(base_params) + [(name, value) for value in invalid_group]
                    response = await client.request(method, runtime_path, params=params)
                    if response.status_code != 422:
                        failures.append(
                            f"{method} {route} {name}: expected 422, got {response.status_code}"
                        )
                        continue
                    try:
                        details = response.json().get("detail", [])
                    except (ValueError, AttributeError):
                        details = []
                    if not any(detail.get("loc", [])[:2] == ["query", name] for detail in details):
                        failures.append(f"{method} {route} {name}: 422 did not identify target query")
    finally:
        app.dependency_overrides.clear()
    return checks, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    policy_path = args.policy.resolve()
    policy = json.loads(policy_path.read_text())

    from main import app

    openapi = app.openapi()
    current = _operation_parameters(openapi)
    entries = _policy_entries(policy)
    policies = policy.get("policies", {})
    errors: list[str] = []
    if len(policies) != 17:
        errors.append(f"expected 17 policy definitions, found {len(policies)}")
    if len(entries) != 219:
        errors.append(f"expected 219 frozen entries, found {len(entries)}")
    missing = sorted(set(entries) - set(current))
    added = sorted(set(current) - set(entries))
    errors.extend(f"missing current parameter: {key}" for key in missing)
    errors.extend(f"unclassified current parameter: {key}" for key in added)
    for key in sorted(set(entries) & set(current)):
        entry = entries[key]
        if entry["policy"] not in policies:
            errors.append(f"{key}: unknown policy {entry['policy']}")
            continue
        if current[key].get("required", False) != entry["required"]:
            errors.append(f"{key}: required flag drift")
        errors.extend(_schema_errors(key, current[key]["schema"], entry["policy"], policies))
    static_queries = _static_query_inventory()
    static_unclassified = sorted(static_queries - set(entries))
    errors.extend(f"unclassified static Query call: {key}" for key in static_unclassified)

    runtime_checks = 0
    runtime_failures: list[str] = []
    if not errors:
        runtime_checks, runtime_failures = asyncio.run(
            _runtime_422_checks(app, openapi, current, entries, policies)
        )
        errors.extend(runtime_failures)

    evidence = {
        "schema": "unihub-query-parameter-contract-evidence-v1",
        "command": " ".join(sys.argv),
        "retail_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip(),
        "policy_sha256": _file_sha256(policy_path),
        "openapi_sha256": _canonical_sha256(openapi),
        "baseline_openapi_sha256": policy.get("baseline_openapi_sha256"),
        "thresholds": {
            "policy_definitions": 17,
            "frozen_parameters": 219,
            "unclassified": 0,
            "runtime_failures": 0,
        },
        "counts": {
            "policy_definitions": len(policies),
            "frozen_parameters": len(entries),
            "current_parameters": len(current),
            "static_query_calls": len(static_queries),
            "static_unclassified": len(static_unclassified),
            "runtime_422_checks": runtime_checks,
            "runtime_failures": len(runtime_failures),
        },
        "errors": errors,
        "duration_seconds": round(time.monotonic() - started, 3),
        "result": "PASS" if not errors else "FAIL",
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
