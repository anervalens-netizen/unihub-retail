#!/usr/bin/env python3
"""Validate faithful CycloneDX inventories before release packaging."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import re
import uuid
from pathlib import Path
from typing import Any


PYTHON_RUNTIME_TREE_PROPERTY = (
    "unihub:python-runtime:site-packages-tree-sha256:v1"
)


def _stable_runtime_file_bytes(path: Path) -> bytes:
    payload = path.read_bytes()
    if path.name != "RECORD":
        return payload
    lines: list[str] = []
    for line in payload.decode("utf-8").splitlines():
        fields = line.split(",")
        if fields[0].startswith("../../../bin/"):
            continue
        lines.append(",".join(fields))
    return ("\n".join(lines) + "\n").encode()


def bind_python_runtime_tree(path: Path, runtime_venv: Path) -> str:
    site_packages = runtime_venv / "lib/python3.12/site-packages"
    if (
        not runtime_venv.is_dir()
        or runtime_venv.is_symlink()
        or not site_packages.is_dir()
        or site_packages.is_symlink()
    ):
        raise ValueError("runtime venv/site-packages is absent or unsafe")
    canonical = lambda value: re.sub(r"[-_.]+", "-", value).lower()
    distributions = {
        canonical(dist.metadata["Name"]): dist
        for dist in importlib.metadata.distributions(path=[str(site_packages)])
        if dist.metadata.get("Name")
    }
    if not distributions:
        raise ValueError("runtime venv distribution inventory is empty")
    claimed: set[Path] = set()
    record_failures: list[str] = []
    for name, dist in sorted(distributions.items()):
        for file in dist.files or ():
            target = Path(dist.locate_file(file))
            try:
                resolved = target.resolve()
                if not resolved.is_relative_to(site_packages.resolve()):
                    continue
            except (OSError, ValueError):
                record_failures.append(f"{name}:{file}:unsafe_path")
                continue
            claimed.add(resolved)
            if not target.is_file() or target.is_symlink():
                record_failures.append(f"{name}:{file}:missing_or_unsafe")
                continue
            if file.hash is None:
                file_path = Path(str(file))
                if file_path.name != "RECORD" and file_path.suffix != ".pyc":
                    record_failures.append(f"{name}:{file}:unhashed")
                continue
            if file.hash.mode != "sha256":
                record_failures.append(f"{name}:{file}:unsupported_hash")
                continue
            actual = base64.urlsafe_b64encode(
                hashlib.sha256(target.read_bytes()).digest()
            ).decode().rstrip("=")
            if actual != file.hash.value:
                record_failures.append(f"{name}:{file}:hash_mismatch")
    pyc_files = [item for item in site_packages.rglob("*.pyc") if item.is_file()]
    symlinks = [item for item in site_packages.rglob("*") if item.is_symlink()]
    unowned = [
        item
        for item in site_packages.rglob("*")
        if item.is_file()
        and not item.is_symlink()
        and item.suffix != ".pyc"
        and item.resolve() not in claimed
    ]
    if record_failures or pyc_files or symlinks or unowned:
        raise ValueError(
            "runtime venv RECORD/tree is unsafe: "
            f"record={record_failures[:5]}, pyc={len(pyc_files)}, "
            f"symlinks={len(symlinks)}, unowned={len(unowned)}"
        )
    entries = [
        [
            str(item.relative_to(site_packages)),
            hashlib.sha256(_stable_runtime_file_bytes(item)).hexdigest(),
        ]
        for item in sorted(site_packages.rglob("*"))
        if item.is_file() and not item.is_symlink() and item.suffix != ".pyc"
    ]
    digest = hashlib.sha256(
        json.dumps(entries, separators=(",", ":")).encode()
    ).hexdigest()
    payload = json.loads(path.read_text(encoding="utf-8"))
    metadata = payload.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("Python SBOM metadata is invalid")
    properties = metadata.setdefault("properties", [])
    if not isinstance(properties, list) or any(
        isinstance(item, dict) and item.get("name") == PYTHON_RUNTIME_TREE_PROPERTY
        for item in properties
    ):
        raise ValueError("Python runtime tree property is invalid or duplicated")
    properties.append({"name": PYTHON_RUNTIME_TREE_PROPERTY, "value": digest})
    properties.sort(key=lambda item: str(item.get("name", "")))
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return digest


def clean_python_runtime_cache(runtime_venv: Path) -> int:
    site_packages = runtime_venv / "lib/python3.12/site-packages"
    if not site_packages.is_dir() or site_packages.is_symlink():
        raise ValueError("runtime site-packages is absent or unsafe")
    removed = 0
    cache_directories: list[Path] = []
    for item in sorted(site_packages.rglob("*"), reverse=True):
        if item.is_symlink():
            continue
        if item.is_file() and item.suffix == ".pyc":
            item.unlink()
            removed += 1
        elif item.is_dir() and item.name == "__pycache__":
            cache_directories.append(item)
    for directory in sorted(
        cache_directories, key=lambda item: len(item.parts), reverse=True
    ):
        try:
            directory.rmdir()
        except OSError:
            pass
    if any(item.is_file() for item in site_packages.rglob("*.pyc")):
        raise ValueError("runtime bytecode cleanup is incomplete")
    return removed


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
    parser.add_argument("--runtime-venv", type=Path)
    parser.add_argument("--clean-runtime-pyc", action="store_true")
    args = parser.parse_args()
    if args.runtime_venv is not None:
        if args.ecosystem != "pypi":
            parser.error("--runtime-venv is valid only for the pypi SBOM")
        if args.clean_runtime_pyc:
            clean_python_runtime_cache(args.runtime_venv)
        bind_python_runtime_tree(args.path, args.runtime_venv)
    elif args.clean_runtime_pyc:
        parser.error("--clean-runtime-pyc requires --runtime-venv")
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
