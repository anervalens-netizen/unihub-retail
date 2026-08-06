#!/usr/bin/env python3
"""Generate the offline Retail OpenAPI snapshot and TypeScript contract index."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUTPUT = ROOT / "src" / "api" / "generated"
OPENAPI_PATH = OUTPUT / "openapi.json"
TYPES_PATH = OUTPUT / "contracts.ts"
DECIMAL_PATTERN_PREFIX = "^(?!^[-+.]*$)"


def schema_ref(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("$ref"), str):
        return value["$ref"].rsplit("/", 1)[-1]
    return None


def is_decimal_schema(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("type") == "string"
        and isinstance(value.get("pattern"), str)
        and value["pattern"].startswith(DECIMAL_PATTERN_PREFIX)
    )


def contains_decimal_schema(value: Any) -> bool:
    if is_decimal_schema(value):
        return True
    if not isinstance(value, dict):
        return False
    return any(contains_decimal_schema(item) for item in value.get("anyOf", []))


def ts_type(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "unknown"
    ref = schema_ref(schema)
    if ref:
        return f"Retail{ref}"
    if is_decimal_schema(schema):
        return "RetailDecimal"
    if "oneOf" in schema or "anyOf" in schema:
        key = "oneOf" if "oneOf" in schema else "anyOf"
        values = [ts_type(item) for item in schema.get(key, [])]
        return " | ".join(dict.fromkeys(values)) or "unknown"
    if "allOf" in schema:
        return " & ".join(ts_type(item) for item in schema.get("allOf", [])) or "unknown"
    if "enum" in schema:
        values = [json.dumps(item, ensure_ascii=False) for item in schema["enum"]]
        return " | ".join(values) or "never"
    if schema.get("type") == "array" and isinstance(schema.get("prefixItems"), list):
        return f"[{', '.join(ts_type(item) for item in schema['prefixItems'])}]"
    if schema.get("type") == "array":
        prefix_items = schema.get("prefixItems")
        if isinstance(prefix_items, list):
            item_types = [ts_type(item) for item in prefix_items]
            return f"[{', '.join(item_types)}]"
        return f"Array<{ts_type(schema.get('items', {}))}>"
    if schema.get("type") == "object" or "properties" in schema:
        additional = schema.get("additionalProperties")
        if additional is not None:
            return f"Record<string, {ts_type(additional) if isinstance(additional, dict) else 'unknown'}>"
        return "Record<string, unknown>"
    return {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "null": "null",
    }.get(schema.get("type"), "unknown")


def operation_id(method: str, path: str, operation: dict[str, Any]) -> str:
    value = operation.get("operationId")
    if isinstance(value, str) and value:
        return value
    fallback = re.sub(r"[^A-Za-z0-9]+", "_", f"{method}_{path}").strip("_")
    return fallback.lower()


def validate_operations(schema: dict[str, Any]) -> list[tuple[str, str, str, dict[str, Any]]]:
    operations: list[tuple[str, str, str, dict[str, Any]]] = []
    seen: dict[str, str] = {}
    for path in sorted(schema.get("paths", {})):
        for method in sorted(schema["paths"][path]):
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head"}:
                continue
            operation = schema["paths"][path][method]
            identifier = operation_id(method.lower(), path, operation)
            previous = seen.get(identifier)
            if previous is not None:
                raise RuntimeError(f"duplicate operation_id {identifier}: {previous} and {method} {path}")
            seen[identifier] = f"{method.upper()} {path}"
            operations.append((identifier, method.lower(), path, operation))
    return operations


def response_type(response: dict[str, Any]) -> str:
    content = response.get("content", {})
    if any(
        isinstance(value, dict)
        and value.get("schema", {}).get("format") == "binary"
        for value in content.values()
    ):
        return "Blob"
    if "application/json" in content:
        return ts_type(content["application/json"].get("schema", {}))
    if "application/octet-stream" in content or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in content:
        return "Blob"
    return "void"


def generate_types(schema: dict[str, Any], operations: list[tuple[str, str, str, dict[str, Any]]], digest: str) -> str:
    decimal_keys = sorted({
        property_name
        for definition in schema.get("components", {}).get("schemas", {}).values()
        for property_name, property_schema in definition.get("properties", {}).items()
        if contains_decimal_schema(property_schema)
    })
    lines = [
        "/* GENERATED FILE. Run npm run contracts:generate; do not edit manually. */",
        f"export const RETAIL_OPENAPI_SHA256 = {digest!r} as const; // pragma: allowlist secret",
        "",
        "export type RetailDecimal = string & { readonly __retailDecimal: unique symbol };",
        "",
        "export const RETAIL_DECIMAL_KEYS = new Set<string>([",
        *[f"  {json.dumps(key)}," for key in decimal_keys],
        "]);",
        "",
    ]
    for name in sorted(schema.get("components", {}).get("schemas", {})):
        definition = schema["components"]["schemas"][name]
        if "enum" in definition:
            lines.append(f"export type Retail{name} = {ts_type(definition)};")
            lines.append("")
            continue
        properties = definition.get("properties", {})
        required = set(definition.get("required", []))
        if not properties:
            lines.append(f"export type Retail{name} = {ts_type(definition)};")
            lines.append("")
            continue
        lines.append(f"export interface Retail{name} {{")
        for prop in sorted(properties):
            optional = "" if prop in required else "?"
            lines.append(f"  {json.dumps(prop)}{optional}: {ts_type(properties[prop])};")
        lines.extend(["}", ""])

    lines.append("export type RetailOperationId =")
    for index, (identifier, _method, _path, _operation) in enumerate(operations):
        suffix = ";" if index == len(operations) - 1 else " |"
        lines.append(f"  {identifier!r}{suffix}")
    lines.append("")
    lines.append("export interface RetailOperationResponses {")
    for identifier, _method, _path, operation in operations:
        responses = operation.get("responses", {})
        lines.append(f"  {identifier!r}: {{")
        for status, response in sorted(responses.items()):
            lines.append(f"    {status!r}: {response_type(response)};")
        lines.extend(["  }", ""])
    lines.append("}")
    lines.append("")
    lines.append("export const RETAIL_OPERATION_ROUTES = {")
    for identifier, method, path, _operation in operations:
        lines.append(f"  {identifier!r}: {{ method: {method!r}, path: {path!r} }},")
    lines.append("} as const;")
    return "\n".join(lines) + "\n"


def build_schema() -> dict[str, Any]:
    sys.path.insert(0, str(BACKEND))
    from main import app  # pylint: disable=import-outside-toplevel

    schema = app.openapi()
    operations = validate_operations(schema)
    for identifier, _method, _path, operation in operations:
        operation["operationId"] = identifier
    return schema


def main() -> int:
    schema = build_schema()
    encoded = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    operations = validate_operations(schema)
    types = generate_types(schema, operations, digest)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if "--check" in sys.argv:
        if not OPENAPI_PATH.exists() or OPENAPI_PATH.read_text(encoding="utf-8") != encoded:
            print(f"Contract drift: {OPENAPI_PATH}", file=sys.stderr)
            return 1
        if not TYPES_PATH.exists() or TYPES_PATH.read_text(encoding="utf-8") != types:
            print(f"Contract drift: {TYPES_PATH}", file=sys.stderr)
            return 1
        print(f"Retail contract is current ({digest})")
        return 0
    OPENAPI_PATH.write_text(encoded, encoding="utf-8")
    TYPES_PATH.write_text(types, encoding="utf-8")
    print(f"Generated Retail contract ({len(operations)} operations, {digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
