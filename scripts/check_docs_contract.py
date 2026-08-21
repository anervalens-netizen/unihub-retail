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
INLINE_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]*)\)")
REFERENCE_LINK_RE = re.compile(r"(?m)^\s*\[[^\]]+\]:\s*(.+?)\s*$")
FORBIDDEN_RELEASE_IDENTITY_KEYS = {
    "release",
    "releaseid",
    "releasename",
    "releasetag",
    "semanticrelease",
    "currentrelease",
    "latestrelease",
    "releasecurrent",
    "releaselatest",
}
RELEASE_SUPPORT_KEYS = {
    "artifact",
    "artifactdigest",
    "evidencedocument",
    "rollbackidentity",
    "sbomdigest",
    "sourcesha",
}
CURRENT_FLAG_KEYS = {"current", "iscurrent", "latest", "islatest"}
CURRENT_RELEASE_PATH_MARKERS = {
    "currentrelease",
    "currentreleases",
    "latestrelease",
    "latestreleases",
    "releasecurrent",
    "releasescurrent",
    "releaselatest",
    "releaseslatest",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _markdown_destination(raw: str) -> str:
    """Extract one Markdown link destination while preserving spaces inside <...>."""
    raw = raw.strip()
    if not raw:
        return ""
    if raw.startswith("<"):
        end = raw.find(">", 1)
        if end != -1:
            return raw[1:end].strip()
        return raw[1:].strip()
    return raw.split(maxsplit=1)[0].strip()


def _markdown_link_targets(text: str) -> list[str]:
    targets: list[str] = []
    for raw in INLINE_LINK_RE.findall(text):
        target = _markdown_destination(raw)
        if target:
            targets.append(target)
    for raw in REFERENCE_LINK_RE.findall(text):
        target = _markdown_destination(raw)
        if target:
            targets.append(target)
    return targets


def _check_links(path: Path) -> list[str]:
    errors: list[str] = []
    for raw_target in _markdown_link_targets(path.read_text()):
        target = raw_target.strip()
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


def _compact_path(value: str) -> str:
    # Stripping separators also normalizes snake/kebab/dotted paths; lowercasing
    # makes camelCase variants such as currentRelease collapse to currentrelease.
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _release_pointer_errors(root: Path) -> list[str]:
    """Reject tracked JSON that could become a repository-owned release authority."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.json"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    errors: list[str] = []
    for raw_path in filter(None, result.stdout.split("\0")):
        path = root / raw_path
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue

        compact_path = _compact_path(raw_path)
        if any(marker in compact_path for marker in CURRENT_RELEASE_PATH_MARKERS):
            errors.append(
                f"{raw_path}: repository-managed current/latest release path is prohibited; "
                "release identity must come from signed CI/deploy evidence"
            )
            continue

        all_items: list[tuple[str, object]] = []
        for node in _iter_dicts(payload):
            all_items.extend((_normalized_key(key), value) for key, value in node.items())

        normalized_keys = {key for key, _ in all_items}
        forbidden_identity_keys = normalized_keys & FORBIDDEN_RELEASE_IDENTITY_KEYS
        if forbidden_identity_keys:
            errors.append(
                f"{raw_path}: repository-managed release identity keys are prohibited "
                f"({', '.join(sorted(forbidden_identity_keys))}); "
                "release identity must come from signed CI/deploy evidence"
            )
            continue

        support_keys = normalized_keys & RELEASE_SUPPORT_KEYS
        statuses = {
            value.casefold()
            for key, value in all_items
            if key == "status" and isinstance(value, str)
        }
        current_flag = any(
            key in CURRENT_FLAG_KEYS
            and (value is True or (isinstance(value, str) and value.casefold() in {"true", "current", "latest"}))
            for key, value in all_items
        )
        current_semantics = "current" in statuses or "latest" in statuses or current_flag
        if current_semantics and support_keys:
            errors.append(
                f"{raw_path}: current/latest metadata cannot carry release-support identity fields "
                f"({', '.join(sorted(support_keys))}); "
                "release identity must come from signed CI/deploy evidence"
            )
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
        for path in release_docs_dir.rglob("*")
        if path.is_file() and path.suffix.lower() != ".md"
    )
    for path in repository_release_metadata:
        errors.append(
            f"{path}: docs/releases is Markdown-only historical evidence; "
            "repository-managed release metadata/pointers are prohibited"
        )
    errors.extend(_release_pointer_errors(ROOT))

    release_entries = [
        entry
        for entry in entries
        if str(entry.get("canonical_key", "")).startswith("release.")
        or "release" in entry.get("applies_to", [])
    ]
    for entry in release_entries:
        if entry.get("status") not in {"historical", "superseded"}:
            errors.append(f"{entry.get('path')}: release documentation must be historical/superseded, not current authority")

    canonical_docs = (ROOT / "README.md", ROOT / "APP_ARCHITECTURE.md", ROOT / "docs/README.md")
    allowed_canonical_json_links = {(ROOT / "docs/catalog.json").resolve()}
    for path in canonical_docs:
        text = path.read_text()
        if "releases/current.json" in text:
            errors.append(f"{path.relative_to(ROOT)} references retired release pointer")
        for target in _markdown_link_targets(text):
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target = unquote(target.split("#", 1)[0].split("?", 1)[0])
            resolved = (path.parent / target).resolve()
            if resolved.suffix.casefold() == ".json" and resolved not in allowed_canonical_json_links:
                errors.append(
                    f"{path.relative_to(ROOT)} links repository JSON {target}; "
                    "canonical docs may not delegate current release authority to repository metadata"
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
            "links_scanned": sum(len(_markdown_link_targets(path.read_text())) for path in scanned),
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
