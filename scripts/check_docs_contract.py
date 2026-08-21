#!/usr/bin/env python3
"""Fail-closed documentation catalog, link and staleness verifier."""
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    # Compatibility-only argument for callers predating D1. Release identity is
    # verified by scripts/check_release_authority.py, not repository pointers.
    parser.add_argument("--release", type=Path, required=False, help=argparse.SUPPRESS)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()

    started = time.monotonic()
    catalog_path = args.catalog.resolve()
    catalog = json.loads(catalog_path.read_text())
    entries = catalog.get("entries", [])
    errors: list[str] = []

    actual_docs = {
        str(path.relative_to(ROOT))
        for path in (ROOT / "docs").rglob("*.md")
    }
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

    errors.extend(
        f"uncataloged Markdown: {path}"
        for path in sorted(actual_docs - set(catalog_paths))
    )
    errors.extend(
        f"stale catalog path: {path}"
        for path in sorted(set(catalog_paths) - actual_docs)
    )

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

    scanned = [
        ROOT / path for path in sorted(actual_docs)
    ] + [ROOT / "README.md", ROOT / "APP_ARCHITECTURE.md"]
    for path in scanned:
        errors.extend(_check_links(path))

    release_entries = [
        entry
        for entry in entries
        if str(entry.get("canonical_key", "")).startswith("release.")
        or "release" in entry.get("applies_to", [])
    ]
    for entry in release_entries:
        if entry.get("status") not in {"historical", "superseded"}:
            errors.append(
                f"{entry.get('path')}: release documentation must be historical/superseded"
            )

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
            errors.append(
                f"docs/README.md missing required active category link {target}"
            )

    evidence = {
        "schema": "unihub-docs-contract-evidence-v1",
        "command": " ".join(sys.argv),
        "retail_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "catalog_sha256": _sha256(catalog_path),
        "release_identity_authority": (
            "signed RELEASE_MANIFEST.json + deploy promotion record"
        ),
        "counts": {
            "markdown_files": len(actual_docs),
            "catalog_entries": len(entries),
            "active_entries": sum(
                entry.get("status") in ACTIVE_STATUSES for entry in entries
            ),
            "links_scanned": sum(
                len(LINK_RE.findall(path.read_text())) for path in scanned
            ),
            "errors": len(errors),
        },
        "thresholds": {
            "catalog_coverage_percent": 100,
            "active_max_age_days": 180,
            "errors": 0,
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
