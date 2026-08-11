#!/usr/bin/env python3
"""Validate faithful CycloneDX inventories before release packaging."""
from __future__ import annotations

import argparse
import json
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ecosystem", choices=("npm", "pypi"))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    payload = validate(args.path, args.ecosystem)
    print(
        f"CycloneDX {args.ecosystem} valid: {len(payload['components'])} components, "
        f"{len(payload['dependencies'])} graph nodes"
    )


if __name__ == "__main__":
    main()
