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
from html.parser import HTMLParser
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
REFERENCE_LINK_RE = re.compile(r"(?m)^\s*\[[^\]]+\]:\s*(.+?)\s*$")
CURRENT_FLAG_KEYS = {"current", "iscurrent", "latest", "islatest"}
HISTORICAL_STATUSES = {"historical", "superseded"}
RELEASE_IDENTITY_MARKERS = {
    "candidate",
    "commit",
    "current",
    "digest",
    "hash",
    "id",
    "latest",
    "name",
    "ref",
    "sha",
    "sha256",
    "tag",
    "version",
}
CURRENT_IDENTITY_NAMESPACES = {
    "artifact",
    "deploy",
    "evidence",
    "manifest",
    "migration",
    "predecessor",
    "provenance",
    "rollback",
    "sbom",
    "source",
}
IDENTITY_DETAIL_TOKENS = {
    "at",
    "commit",
    "digest",
    "hash",
    "id",
    "name",
    "ref",
    "sha",
    "sha256",
    "tag",
    "time",
    "timestamp",
    "version",
}


class _HrefCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        for name, value in attrs:
            if name.casefold() == "href" and value:
                self.targets.append(value.strip())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _markdown_destination(raw: str) -> str:
    """Extract one Markdown destination while preserving spaces inside <...>."""
    raw = raw.strip()
    if not raw:
        return ""
    if raw.startswith("<"):
        end = raw.find(">", 1)
        if end != -1:
            return raw[1:end].strip()
        return raw[1:].strip()
    return raw.split(maxsplit=1)[0].strip()


def _inline_link_targets(text: str) -> list[str]:
    """Parse inline Markdown destinations without truncating angle-bracket paths."""
    targets: list[str] = []
    cursor = 0
    while True:
        marker = text.find("](", cursor)
        if marker == -1:
            break
        index = marker + 2
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break

        if text[index] == "<":
            end = index + 1
            escaped = False
            while end < len(text):
                char = text[end]
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == ">":
                    break
                end += 1
            if end < len(text) and text[end] == ">":
                target = text[index + 1 : end].strip()
                if target:
                    targets.append(target)
                cursor = end + 1
                continue

        chars: list[str] = []
        depth = 0
        escaped = False
        end = index
        while end < len(text):
            char = text[end]
            if escaped:
                chars.append(char)
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "(":
                depth += 1
                chars.append(char)
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
                chars.append(char)
            elif char.isspace() and depth == 0:
                break
            else:
                chars.append(char)
            end += 1
        target = "".join(chars).strip()
        if target:
            targets.append(target)
        cursor = max(end + 1, marker + 2)
    return targets


def _strip_markdown_code(text: str) -> str:
    """Blank fenced and inline code while preserving line structure."""
    visible_lines: list[str] = []
    fence_char: str | None = None
    fence_len = 0

    for line in text.splitlines(keepends=True):
        indent = len(line) - len(line.lstrip(" "))
        stripped = line[indent:] if indent <= 3 else line
        fence = re.match(r"(`{3,}|~{3,})", stripped) if indent <= 3 else None

        if fence_char is not None:
            if (
                fence
                and fence.group(1)[0] == fence_char
                and len(fence.group(1)) >= fence_len
            ):
                fence_char = None
                fence_len = 0
            visible_lines.append("\n" if line.endswith("\n") else "")
            continue

        if fence:
            fence_char = fence.group(1)[0]
            fence_len = len(fence.group(1))
            visible_lines.append("\n" if line.endswith("\n") else "")
            continue

        visible_lines.append(line)

    visible = "".join(visible_lines)
    output: list[str] = []
    index = 0
    while index < len(visible):
        if visible[index] != "`":
            output.append(visible[index])
            index += 1
            continue

        run_end = index
        while run_end < len(visible) and visible[run_end] == "`":
            run_end += 1
        delimiter = visible[index:run_end]
        close = visible.find(delimiter, run_end)
        if close == -1:
            output.append(delimiter)
            index = run_end
            continue

        segment = visible[index : close + len(delimiter)]
        output.extend("\n" if char == "\n" else " " for char in segment)
        index = close + len(delimiter)

    return "".join(output)


def _markdown_link_targets(text: str) -> list[str]:
    visible = _strip_markdown_code(text)
    targets = _inline_link_targets(visible)
    for raw in REFERENCE_LINK_RE.findall(visible):
        target = _markdown_destination(raw)
        if target:
            targets.append(target)
    html_links = _HrefCollector()
    html_links.feed(visible)
    targets.extend(html_links.targets)
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


def _identifier_tokens(value: object) -> set[str]:
    text = str(value)
    camel_split = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
        " ",
        text,
    )
    return {token.casefold() for token in re.split(r"[^A-Za-z0-9]+", camel_split) if token}


def _path_tokens(value: str) -> set[str]:
    return _identifier_tokens(value)


def _compact_path(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _release_identity_key(normalized: str, tokens: set[str]) -> bool:
    release_tokens = {"release", "releases"} & tokens
    if release_tokens:
        if tokens == {"release"}:
            return True
        return bool(RELEASE_IDENTITY_MARKERS & tokens)

    compact_markers = tuple(sorted(RELEASE_IDENTITY_MARKERS, key=len, reverse=True))
    if normalized == "release":
        return True
    if normalized.startswith(("currentrelease", "latestrelease")):
        return True
    return any(
        normalized.startswith(prefix + marker)
        for prefix in ("release", "releases")
        for marker in compact_markers
    )


def _current_support_identity_key(normalized: str, tokens: set[str]) -> bool:
    if CURRENT_IDENTITY_NAMESPACES & tokens:
        return True
    return any(
        normalized.startswith(namespace + detail)
        for namespace in CURRENT_IDENTITY_NAMESPACES
        for detail in IDENTITY_DETAIL_TOKENS
    )


def _node_statuses(node: dict[object, object]) -> set[str]:
    return {
        value.casefold()
        for key, value in node.items()
        if _normalized_key(key) == "status" and isinstance(value, str)
    }


def _node_current_flag(node: dict[object, object]) -> bool:
    return any(
        _normalized_key(key) in CURRENT_FLAG_KEYS
        and (
            value is True
            or (isinstance(value, str) and value.casefold() in {"true", "current", "latest"})
        )
        for key, value in node.items()
    )


def _scan_release_metadata(
    value: object,
    raw_path: str,
    errors: list[str],
    *,
    inherited_current: bool = False,
    inherited_historical: bool = False,
) -> None:
    if isinstance(value, list):
        for child in value:
            _scan_release_metadata(
                child,
                raw_path,
                errors,
                inherited_current=inherited_current,
                inherited_historical=inherited_historical,
            )
        return
    if not isinstance(value, dict):
        return

    statuses = _node_statuses(value)
    local_current = bool({"current", "latest"} & statuses) or _node_current_flag(value)
    local_historical = bool(HISTORICAL_STATUSES & statuses)
    if local_current and local_historical:
        errors.append(
            f"{raw_path}: conflicting current/latest and historical/superseded metadata is prohibited; "
            "release authority state must be unambiguous"
        )

    # Current semantics take precedence and propagate fail-closed. A nested
    # historical marker cannot launder exact identity under a current parent.
    current = inherited_current or local_current
    historical = (inherited_historical or local_historical) and not current

    items = [
        (_normalized_key(key), _identifier_tokens(key), child)
        for key, child in value.items()
    ]

    release_identity_keys = {
        normalized
        for normalized, tokens, _ in items
        if _release_identity_key(normalized, tokens)
    }
    if release_identity_keys and not historical:
        errors.append(
            f"{raw_path}: repository-managed release identity keys are prohibited "
            f"({', '.join(sorted(release_identity_keys))}); "
            "release identity must come from signed CI/deploy evidence"
        )

    if current:
        current_identity_keys = {
            normalized
            for normalized, tokens, _ in items
            if _current_support_identity_key(normalized, tokens)
        }
        if current_identity_keys:
            errors.append(
                f"{raw_path}: current/latest metadata cannot carry release-support identity namespaces "
                f"({', '.join(sorted(current_identity_keys))}); "
                "release identity must come from signed CI/deploy evidence"
            )

    for _, _, child in items:
        _scan_release_metadata(
            child,
            raw_path,
            errors,
            inherited_current=current,
            inherited_historical=historical,
        )


def _release_pointer_errors(root: Path) -> list[str]:
    """Reject tracked JSON that could become a repository-owned release authority."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    errors: list[str] = []
    for raw_path in filter(None, result.stdout.split("\0")):
        if Path(raw_path).suffix.casefold() != ".json":
            continue
        path = root / raw_path
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue

        path_tokens = _path_tokens(raw_path)
        compact_parts = [_compact_path(part) for part in Path(raw_path).parts]
        current_release_path = (
            bool({"current", "latest"} & path_tokens)
            and bool({"release", "releases"} & path_tokens)
        ) or any(
            (
                (part.startswith("current") or part.startswith("latest"))
                and "release" in part
            )
            or (
                (part.startswith("release") or part.startswith("releases"))
                and ("current" in part or "latest" in part)
            )
            for part in compact_parts
        )
        if current_release_path:
            errors.append(
                f"{raw_path}: repository-managed current/latest release path is prohibited; "
                "release identity must come from signed CI/deploy evidence"
            )
            continue

        _scan_release_metadata(payload, raw_path, errors)
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
