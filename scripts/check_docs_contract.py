#!/usr/bin/env python3
"""Fail-closed catalog, link, staleness and release-authority verifier."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FIELDS = {
    "path",
    "canonical_key",
    "status",
    "owner",
    "last_verified",
    "applies_to",
    "supersedes",
    "superseded_by",
    "evidence",
}
ACTIVE_STATUSES = {"active"}
ALL_STATUSES = ACTIVE_STATUSES | {"historical", "superseded"}
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
RELEASE_POINTER_MARKER_KEYS = {
    "artifact",
    "artifactdigest",
    "evidencedocument",
    "release",
    "releaseid",
    "releasename",
    "releasetag",
    "rollbackidentity",
    "sbomdigest",
    "semanticrelease",
    "sourcesha",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_links(path: Path) -> list[str]:
    errors: list[str] = []
    for raw_target in LINK_RE.findall(path.read_text()):
        target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        target = unquote(target.split("#", 1)[0].split("?", 1)[0])
        resolved = (path.parent / target).resolve()
        if not resolved.is_relative_to(ROOT) or not resolved.exists():
            errors.append(f"{path.relative_to(ROOT)}: broken relative link {raw_target}")
    return errors


def _iter_dicts(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _release_pointer_errors() -> list[str]:
    """Reject tracked JSON that can act as repository-owned current-release authority."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    errors: list[str] = []
    for raw_path in filter(None, result.stdout.split("\0")):
        path = ROOT / raw_path
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue

        path_tokens = {token for token in re.split(r"[/_.-]+", raw_path.casefold()) if token}
        release_named_current = "release" in path_tokens and bool({"current", "latest"} & path_tokens)

        for node in _iter_dicts(payload):
            status = node.get("status")
            if not isinstance(status, str) or status.casefold() != "current":
                continue
            normalized_keys = {_normalized_key(key) for key in node}
            marker_keys = normalized_keys & RELEASE_POINTER_MARKER_KEYS
            points_to_release_docs = any(
                isinstance(value, str)
                and (
                    value.casefold().replace("\\", "/").startswith("releases/")
                    or "docs/releases/" in value.casefold().replace("\\", "/")
                )
                for value in node.values()
            )
            if marker_keys or release_named_current or points_to_release_docs:
                reason = ", ".join(sorted(marker_keys)) if marker_keys else "release-oriented path/value"
                errors.append(
                    f"{raw_path}: repository-managed current-release pointer metadata is prohibited "
                    f"({reason}); release identity must come from signed CI/deploy evidence"
                )
                break
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    # Kept as a compatibility-only CLI argument for older callers. D1 retires
    # repository release pointers; this value is never an authority.
    parser.add_argument("--release", type=Path, required=False, help=argparse.SUPPRESS)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    catalog_path = args.catalog.resolve()
    catalog = json.loads(catalog_path.read_text())
    entries = catalog.get("entries", [])
    errors: list[str] = []

    actual_docs = {str(path.relative_to(ROOT)) for path in (ROOT / "docs").rglob("*.md")}
    catalog_paths: list[str] = []
    keys: list[str] = []
    by_key: dict[str, dict] = {}
    for index, entry in enumerate(entries):
        missing_fields = REQUIRED_FIELDS - set(entry)
        if missing_fields:
            errors.append(f"entry {index}: missing fields {sorted(missing_fields)}")
            continue
        path = str(entry["path"])
        key = str(entry["canonical_key"])
        catalog_paths.append(path)
        keys.append(key)
        by_key[key] = entry
        if entry["status"] not in ALL_STATUSES:
            errors.append(f"{path}: invalid status {entry['status']}")
        if not entry["owner"] or not entry["applies_to"] or not entry["evidence"]:
            errors.append(f"{path}: owner/applies_to/evidence must be nonempty")
        try:
            verified = date.fromisoformat(entry["last_verified"])
        except (TypeError, ValueError):
            errors.append(f"{path}: invalid last_verified")
        else:
            age = (date.today() - verified).days
            if entry["status"] in ACTIVE_STATUSES and not 0 <= age <= 180:
                errors.append(f"{path}: active metadata is {age} days old")
        if not (ROOT / path).is_file():
            errors.append(f"{path}: catalog target missing")

    if len(catalog_paths) != len(set(catalog_paths)):
        errors.append("duplicate catalog path")
    if len(keys) != len(set(keys)):
        errors.append("duplicate canonical_key")
    if catalog_paths != sorted(catalog_paths):
        errors.append("catalog paths are not sorted")
    errors.extend(f"uncataloged Markdown: {path}" for path in sorted(actual_docs - set(catalog_paths)))
    errors.extend(f"stale catalog path: {path}" for path in sorted(set(catalog_paths) - actual_docs))

    for entry in entries:
        key = entry.get("canonical_key")
        for predecessor in entry.get("supersedes", []):
            other = by_key.get(predecessor)
            if other is None or key not in other.get("superseded_by", []):
                errors.append(f"{key}: invalid supersedes relationship to {predecessor}")
        for successor in entry.get("superseded_by", []):
            other = by_key.get(successor)
            if other is None or key not in other.get("supersedes", []):
                errors.append(f"{key}: invalid superseded_by relationship to {successor}")

    scanned = [ROOT / path for path in sorted(actual_docs)] + [ROOT / "README.md", ROOT / "APP_ARCHITECTURE.md"]
    for path in scanned:
        errors.extend(_check_links(path))

    release_docs_dir = ROOT / "docs/releases"
    repository_release_metadata = sorted(
        path.relative_to(ROOT)
        for path in release_docs_dir.iterdir()
        if path.is_file() and path.suffix.lower() != ".md"
    )
    for path in repository_release_metadata:
        errors.append(
            f"{path}: repository-managed release metadata/pointers are prohibited; "
            "release identity must come from signed CI/deploy evidence"
        )
    errors.extend(_release_pointer_errors())

    release_entries = [
        entry
        for entry in entries
        if str(entry.get("canonical_key", "")).startswith("release.")
        or "release" in entry.get("applies_to", [])
    ]
    for entry in release_entries:
        if entry.get("status") not in {"historical", "superseded"}:
            errors.append(f"{entry.get('path')}: release documentation must be historical/superseded, not current authority")

    for path in (ROOT / "README.md", ROOT / "APP_ARCHITECTURE.md", ROOT / "docs/README.md"):
        text = path.read_text()
        if "releases/current.json" in text:
            errors.append(f"{path.relative_to(ROOT)} references retired release pointer")

    required_index_links = {
        "../APP_ARCHITECTURE.md",
        "RUNBOOK-campanii-promo-incentive-concursuri.md",
        "adr/004-sales-row-multiplicity.md",
        "engineering/h01-salary-identity-privacy.md",
        "adr/006-verified-runtime-delivery.md",
        "operations/RETAIL_9_5_FINAL_HANDOFF.md",
    }
    index_text = (ROOT / "docs/README.md").read_text()
    for target in sorted(required_index_links):
        if target not in index_text:
            errors.append(f"docs/README.md missing required active category link {target}")

    evidence = {
        "schema": "unihub-docs-contract-evidence-v1",
        "command": " ".join(sys.argv),
        "retail_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip(),
        "catalog_sha256": _sha256(catalog_path),
        "release_identity_authority": "signed RELEASE_MANIFEST.json + deploy promotion record",
        "counts": {
            "markdown_files": len(actual_docs),
            "catalog_entries": len(entries),
            "active_entries": sum(entry.get("status") in ACTIVE_STATUSES for entry in entries),
            "links_scanned": sum(len(LINK_RE.findall(path.read_text())) for path in scanned),
            "errors": len(errors),
        },
        "thresholds": {"catalog_coverage_percent": 100, "active_max_age_days": 180, "errors": 0},
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
