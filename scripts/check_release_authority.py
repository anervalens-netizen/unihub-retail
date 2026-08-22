#!/usr/bin/env python3
"""Reject repository-managed current release identity and competing narratives.

The authoritative candidate identity is generated and signed by CI as
RELEASE_MANIFEST.json. Promotion state is deploy evidence. Tracked repository
metadata or prose must not recreate a competing current-release authority.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_KEYS = {"current", "iscurrent", "latest", "islatest"}
CURRENT_STATUSES = {"current", "latest"}
RELEASE_MARKERS = {
    "artifact", "authority", "candidate", "commit", "current", "data", "deploy",
    "descriptor", "digest", "document", "evidence", "hash", "id", "identity",
    "info", "latest", "manifest", "metadata", "migration", "name", "payload",
    "pointer", "predecessor", "provenance", "record", "ref", "rollback", "sbom",
    "sha", "sha256", "source", "status", "tag", "version",
}
NAMESPACED_RELEASE_IDENTITY_MARKERS = RELEASE_MARKERS - {"deploy", "data", "document", "migration"}
SUPPORT_NAMESPACES = {
    "artifact", "deploy", "evidence", "manifest", "migration", "predecessor",
    "provenance", "rollback", "sbom", "source",
}
IDENTITY_DETAILS = {
    "at", "commit", "digest", "hash", "id", "name", "ref", "sha", "sha256",
    "tag", "time", "timestamp", "version",
}
CANONICAL_DOCS = (
    Path("README.md"),
    Path("APP_ARCHITECTURE.md"),
    Path("docs/README.md"),
)
REQUIRED_AUTHORITY_MARKER = "RELEASE_MANIFEST.json"
RETIRED_POINTER_MARKER = "releases/current.json"
RELEASE_NOTES_INDEX = Path("docs/releases/README.md")
HISTORICAL_RELEASE_MARKER = "Historical release note — not production authority."
DERIVED_RENDERER_MARKER = "render_production_release_notes.py"
PRODUCTION_TAG_MARKER = "production/retail-release-"
COMPETING_CANONICAL_PHRASE = "Canonical identity:"


def _normalized(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _tokens(value: object) -> set[str]:
    text = str(value)
    camel_split = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", text
    )
    return {
        token.casefold()
        for token in re.split(r"[^A-Za-z0-9]+", camel_split)
        if token
    }


def _meaningful(value: object) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value.strip().casefold() not in {"", "false", "no", "none", "null", "off"}
    return True


def _is_release_identity_key(key: object) -> bool:
    normalized = _normalized(key)
    tokens = _tokens(key)
    release_tokens = {"release", "releases"} & tokens
    if normalized in {"release", "releases"}:
        return True
    if release_tokens and NAMESPACED_RELEASE_IDENTITY_MARKERS & tokens:
        return True
    if normalized.startswith(
        ("currentrelease", "latestrelease", "iscurrentrelease", "islatestrelease")
    ):
        return True
    return any(
        normalized.startswith(prefix + marker)
        for prefix in ("release", "releases")
        for marker in RELEASE_MARKERS
    )


def _is_support_identity_key(key: object) -> bool:
    normalized = _normalized(key)
    tokens = _tokens(key)
    if SUPPORT_NAMESPACES & tokens:
        return True
    return any(
        normalized.startswith(namespace + detail)
        for namespace in SUPPORT_NAMESPACES
        for detail in IDENTITY_DETAILS
    )


def _node_is_current(node: dict[object, object]) -> bool:
    for key, value in node.items():
        normalized = _normalized(key)
        if normalized == "status" and isinstance(value, str):
            if value.strip().casefold() in CURRENT_STATUSES:
                return True
        if normalized in CURRENT_KEYS and _meaningful(value):
            return True
    return False


def _scan_json_tree(
    value: object,
    raw_path: str,
    errors: list[str],
    *,
    inherited_current: bool = False,
) -> None:
    if isinstance(value, list):
        for child in value:
            _scan_json_tree(child, raw_path, errors, inherited_current=inherited_current)
        return
    if not isinstance(value, dict):
        return

    current = inherited_current or _node_is_current(value)
    release_keys = sorted({_normalized(key) for key in value if _is_release_identity_key(key)})
    if release_keys:
        errors.append(
            f"{raw_path}: tracked JSON cannot carry release identity keys "
            f"({', '.join(release_keys)}); use signed CI/deploy evidence"
        )
    if current:
        support_keys = sorted({_normalized(key) for key in value if _is_support_identity_key(key)})
        if support_keys:
            errors.append(
                f"{raw_path}: current/latest metadata cannot carry release-support "
                f"identity keys ({', '.join(support_keys)}); use signed CI/deploy evidence"
            )
    for child in value.values():
        _scan_json_tree(child, raw_path, errors, inherited_current=current)


def _current_release_path(raw_path: str) -> bool:
    path_tokens = _tokens(raw_path)
    if {"current", "latest"} & path_tokens and {"release", "releases"} & path_tokens:
        return True
    for part in Path(raw_path).parts:
        normalized = _normalized(part)
        if normalized.startswith(("current", "latest")) and normalized.endswith(("release", "releases")):
            return True
        if normalized.startswith(("release", "releases")) and normalized.endswith(("current", "latest")):
            return True
    return False


def _tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True, text=True
    )
    return [path for path in result.stdout.split("\0") if path]


def repository_metadata_errors(root: Path) -> list[str]:
    errors: list[str] = []
    for raw_path in _tracked_files(root):
        relative = Path(raw_path)
        if relative.parts[:2] == ("docs", "releases") and relative.suffix.casefold() != ".md":
            errors.append(
                f"{raw_path}: docs/releases is Markdown-only historical evidence; "
                "repository-managed release metadata is prohibited"
            )
            continue
        if _current_release_path(raw_path):
            errors.append(
                f"{raw_path}: tracked current/latest release metadata path is prohibited; "
                "use signed CI/deploy evidence"
            )
            continue
        if relative.suffix.casefold() != ".json":
            continue
        path = root / relative
        try:
            payload = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        _scan_json_tree(payload, raw_path, errors)
    return errors


def narrative_release_errors(root: Path) -> list[str]:
    errors: list[str] = []
    index = root / RELEASE_NOTES_INDEX
    if not index.is_file():
        errors.append(f"{RELEASE_NOTES_INDEX}: derived release narrative contract is missing")
    else:
        text = index.read_text(encoding="utf-8")
        for marker in (REQUIRED_AUTHORITY_MARKER, DERIVED_RENDERER_MARKER, PRODUCTION_TAG_MARKER):
            if marker not in text:
                errors.append(f"{RELEASE_NOTES_INDEX}: must name {marker}")

    releases_dir = root / "docs/releases"
    if releases_dir.is_dir():
        for path in sorted(releases_dir.glob("*.md")):
            if path.name == "README.md":
                continue
            text = path.read_text(encoding="utf-8")
            relative = path.relative_to(root)
            if HISTORICAL_RELEASE_MARKER not in text:
                errors.append(f"{relative}: tracked release note must be explicitly historical")
            if COMPETING_CANONICAL_PHRASE in text:
                errors.append(
                    f"{relative}: historical release note cannot declare a canonical identity"
                )
    return errors


def canonical_authority_errors(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in CANONICAL_DOCS:
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}: canonical release-authority document is missing")
            continue
        text = path.read_text()
        if REQUIRED_AUTHORITY_MARKER not in text:
            errors.append(
                f"{relative}: must name {REQUIRED_AUTHORITY_MARKER} as release identity authority"
            )
        if RETIRED_POINTER_MARKER in text:
            errors.append(f"{relative}: references retired {RETIRED_POINTER_MARKER}")
    return errors


def release_authority_errors(root: Path = ROOT) -> list[str]:
    return (
        repository_metadata_errors(root)
        + narrative_release_errors(root)
        + canonical_authority_errors(root)
    )


def main() -> int:
    errors = release_authority_errors(ROOT)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("release-authority: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
