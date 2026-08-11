#!/usr/bin/env python3
"""Validate faithful CycloneDX inventories before release packaging."""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any


def validate(path: Path, ecosystem: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("bomFormat") != "CycloneDX" or payload.get("specVersion") not in {"1.5", "1.6", "1.7"}:
        raise ValueError(f"{path}: unsupported CycloneDX document")
    components = payload.get("components")
    dependencies = payload.get("dependencies")
    if not isinstance(components, list) or not components:
        raise ValueError(f"{path}: component inventory is empty")
    if not isinstance(dependencies, list) or not dependencies:
        raise ValueError(f"{path}: dependency graph is empty")
    refs = {
        component.get("bom-ref")
        for component in components
        if isinstance(component, dict) and isinstance(component.get("bom-ref"), str)
    }
    metadata_ref = payload.get("metadata", {}).get("component", {}).get("bom-ref")
    if isinstance(metadata_ref, str):
        refs.add(metadata_ref)
    for dependency in dependencies:
        if not isinstance(dependency, dict) or dependency.get("ref") not in refs:
            raise ValueError(f"{path}: dependency graph has an unknown source ref")
        if any(ref not in refs for ref in dependency.get("dependsOn", [])):
            raise ValueError(f"{path}: dependency graph has an unknown target ref")
    purl_prefix = f"pkg:{ecosystem}/"
    ecosystem_components = [
        component for component in components
        if isinstance(component, dict) and str(component.get("purl", "")).startswith(purl_prefix)
    ]
    if not ecosystem_components:
        raise ValueError(f"{path}: no {ecosystem} PURLs")
    for component in ecosystem_components:
        purl = str(component["purl"])
        if "node_modules" in purl or not component.get("name") or not component.get("version"):
            raise ValueError(f"{path}: invalid component identity {purl}")
        scope = component.get("scope")
        if scope not in {None, "required", "optional", "excluded"}:
            raise ValueError(f"{path}: invalid component scope {scope}")
    return payload


def _has_hashes(component: dict[str, Any]) -> bool:
    candidates = list(component.get("hashes", []))
    for reference in component.get("externalReferences", []):
        if isinstance(reference, dict):
            candidates.extend(reference.get("hashes", []))
    return any(
        isinstance(item, dict) and item.get("alg") and item.get("content")
        for item in candidates
    )


def validate_aggregate(path: Path, expected_sha: str | None) -> dict[str, Any]:
    payload = validate(path, "npm")
    validate(path, "pypi")
    serial_number = payload.get("serialNumber")
    if not isinstance(serial_number, str) or not serial_number.startswith("urn:uuid:"):
        raise ValueError(f"{path}: aggregate serialNumber is missing")
    try:
        uuid.UUID(serial_number.removeprefix("urn:uuid:"))
    except ValueError as exc:
        raise ValueError(f"{path}: aggregate serialNumber is invalid") from exc

    root = payload.get("metadata", {}).get("component", {})
    root_ref = root.get("bom-ref")
    if (
        root.get("type") != "application"
        or root.get("name") != "unihub-retail"
        or not isinstance(root_ref, str)
        or root.get("purl") != root_ref
    ):
        raise ValueError(f"{path}: aggregate application identity is invalid")
    if expected_sha is not None and root.get("version") != expected_sha:
        raise ValueError(f"{path}: aggregate source SHA mismatch")

    compositions = payload.get("compositions", [])
    if not any(
        isinstance(item, dict)
        and item.get("aggregate") == "complete"
        and root_ref in item.get("assemblies", [])
        for item in compositions
    ):
        raise ValueError(f"{path}: aggregate completeness declaration is missing")

    refs: set[str] = set()
    for component in payload["components"]:
        if not isinstance(component, dict):
            raise ValueError(f"{path}: aggregate component is invalid")
        ref = component.get("bom-ref")
        purl = component.get("purl")
        if not isinstance(ref, str):
            raise ValueError(f"{path}: aggregate component bom-ref is missing")
        if ref in refs:
            raise ValueError(f"{path}: aggregate component bom-ref is duplicated: {ref}")
        if not isinstance(purl, str):
            raise ValueError(f"{path}: aggregate component PURL is missing: {ref}")
        refs.add(ref)
        if component.get("scope") not in {"required", "optional", "excluded"}:
            raise ValueError(f"{path}: aggregate component scope is missing: {purl}")
        if (
            component.get("type") != "application"
            and purl.startswith(("pkg:npm/", "pkg:pypi/"))
            and not _has_hashes(component)
        ):
            raise ValueError(f"{path}: aggregate component hash evidence is missing: {purl}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ecosystem", choices=("npm", "pypi", "aggregate"))
    parser.add_argument("path", type=Path)
    parser.add_argument("--expected-sha")
    args = parser.parse_args()
    payload = (
        validate_aggregate(args.path, args.expected_sha)
        if args.ecosystem == "aggregate"
        else validate(args.path, args.ecosystem)
    )
    print(
        f"CycloneDX {args.ecosystem} valid: {len(payload['components'])} components, "
        f"{len(payload['dependencies'])} graph nodes"
    )


if __name__ == "__main__":
    main()
