#!/usr/bin/env python3
"""Validate the single machine authority for tracked-document lifecycle/status.

This checker is intentionally separate from release identity and live runtime
health. `docs/catalog.json` owns only tracked-document lifecycle. Runtime
readiness remains observable through /readyz and Prometheus, while release
identity remains governed by the signed candidate/promotion chain.
"""
from __future__ import annotations

from pathlib import Path


CATALOG_VERSION = 2
STATUS_AUTHORITY = {
    "schema_version": 1,
    "kind": "tracked-document-lifecycle",
    "authoritative_field": "entries[].status",
    "states": ["active", "historical", "superseded"],
    "live_runtime": "/readyz + Prometheus machine signals",
    "audit_log": "GitHub issue #159 is chronology/evidence only",
    "rule": "Markdown status labels are snapshots, never current authority",
}
HISTORICAL_STATUS_MARKER = "Historical status snapshot — not current status authority."
READINESS_CONTRACT_MARKER = "Operational readiness contract — not a current health declaration."
HISTORICAL_STATUS_SNAPSHOTS = (
    Path("docs/exec-plans/completed/UR-CLOSE-20260812.md"),
    Path("docs/operations/RETAIL_9_5_FINAL_HANDOFF.md"),
)
READINESS_CONTRACT = Path("docs/operations/retail-slo-readiness.md")
INDEX = Path("docs/README.md")
INDEX_MARKERS = (
    "catalog.json",
    "entries[].status",
    "/readyz",
    "Prometheus",
    "RELEASE_MANIFEST.json",
    "Issue #159",
)


def status_authority_errors(root: Path, catalog: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(catalog, dict):
        return ["docs/catalog.json: root must be an object"]

    if catalog.get("version") != CATALOG_VERSION:
        errors.append(f"docs/catalog.json: version must be {CATALOG_VERSION}")
    if catalog.get("status_authority") != STATUS_AUTHORITY:
        errors.append("docs/catalog.json: status_authority contract is missing or invalid")

    entries = catalog.get("entries")
    if not isinstance(entries, list):
        return errors + ["docs/catalog.json: entries must be an array"]

    by_path: dict[str, dict] = {}
    for index, raw_entry in enumerate(entries):
        if not isinstance(raw_entry, dict):
            errors.append(f"entry {index}: must be an object")
            continue
        path = raw_entry.get("path")
        if isinstance(path, str):
            by_path[path] = raw_entry

    for path, entry in by_path.items():
        status = entry.get("status")
        if path.startswith("docs/exec-plans/active/") and status != "active":
            errors.append(f"{path}: active exec-plan path must have status=active")
        if path.startswith("docs/exec-plans/completed/") and status not in {
            "historical",
            "superseded",
        }:
            errors.append(
                f"{path}: completed exec-plan path must be historical/superseded"
            )

    for relative in HISTORICAL_STATUS_SNAPSHOTS:
        entry = by_path.get(str(relative))
        if entry is None:
            errors.append(f"{relative}: status snapshot is missing from catalog")
            continue
        if entry.get("status") not in {"historical", "superseded"}:
            errors.append(f"{relative}: status snapshot must not be active")
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}: historical status snapshot is missing")
            continue
        if HISTORICAL_STATUS_MARKER not in path.read_text(encoding="utf-8"):
            errors.append(f"{relative}: historical status marker is missing")

    readiness_entry = by_path.get(str(READINESS_CONTRACT))
    if readiness_entry is None:
        errors.append(f"{READINESS_CONTRACT}: readiness contract is missing from catalog")
    elif readiness_entry.get("status") != "active":
        errors.append(f"{READINESS_CONTRACT}: readiness contract must remain active")

    readiness_path = root / READINESS_CONTRACT
    if not readiness_path.is_file():
        errors.append(f"{READINESS_CONTRACT}: readiness contract is missing")
    elif READINESS_CONTRACT_MARKER not in readiness_path.read_text(encoding="utf-8"):
        errors.append(f"{READINESS_CONTRACT}: live-health boundary marker is missing")

    index_path = root / INDEX
    if not index_path.is_file():
        errors.append(f"{INDEX}: canonical docs index is missing")
    else:
        index_text = index_path.read_text(encoding="utf-8")
        for marker in INDEX_MARKERS:
            if marker not in index_text:
                errors.append(f"{INDEX}: missing status-authority boundary marker {marker}")

    return errors
