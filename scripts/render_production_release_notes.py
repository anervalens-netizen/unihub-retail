#!/usr/bin/env python3
"""Render a human-readable production release view from verified D2 promotion state.

This renderer does not discover or select a "current" release. The caller must
supply the exact root-owned D2 ``release.env`` handle that it intends to view.
The machine-readable promotion record remains authoritative; Markdown emitted by
this script is presentation only.
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

SHA40_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
MIGRATION_RE = re.compile(r"[0-9]{3}_[A-Za-z0-9_]+\.sql")
UTC_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
RELEASE_PREFIX = "retail-release-"
TAG_PREFIX = "production/"

REQUIRED_FIELDS = (
    "PROMOTION_SCHEMA_VERSION",
    "RELEASE_ID",
    "SOURCE_SHA",
    "MIGRATION_HEAD",
    "ARTIFACT_SHA256",
    "SBOM_SHA256",
    "PREDECESSOR_RELEASE_ID",
    "PREDECESSOR_SHA",
    "ROLLBACK_RELEASE_ID",
    "ROLLBACK_SHA",
    "DEPLOYED_AT_UTC",
    "OLD_SHA",
    "NEW_SHA",
    "STATE",
    "UPDATED_AT",
)


def parse_release_env(path: Path) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"release.env is missing or unsafe: {path}")

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line:
            continue
        if "=" not in raw_line:
            raise ValueError(f"release.env line {line_number} is not KEY=value")
        key, value = raw_line.split("=", 1)
        if not key or re.fullmatch(r"[A-Z0-9_]+", key) is None:
            raise ValueError(f"release.env line {line_number} has an invalid key")
        if key in values:
            raise ValueError(f"release.env contains duplicate field: {key}")
        values[key] = value

    required = set(REQUIRED_FIELDS)
    missing = sorted(required - set(values))
    if missing:
        raise ValueError(f"release.env is missing required field(s): {', '.join(missing)}")
    unknown = sorted(set(values) - required)
    if unknown:
        raise ValueError(f"release.env contains unknown schema-v1 field(s): {', '.join(unknown)}")
    return values


def _require_sha(value: str, field: str) -> None:
    if SHA40_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be exactly 40 lowercase hex characters")


def _require_sha256(value: str, field: str) -> None:
    if SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be exactly 64 lowercase hex characters")


def _require_utc(value: str, field: str) -> None:
    if UTC_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must use canonical UTC format YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid UTC timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError(f"{field} is not canonical UTC")


def validate_deployed_promotion(values: dict[str, str]) -> dict[str, str]:
    if values["PROMOTION_SCHEMA_VERSION"] != "1":
        raise ValueError("PROMOTION_SCHEMA_VERSION must be exactly 1")
    if values["STATE"] != "deployed":
        raise ValueError("production narrative requires STATE=deployed")

    for field in ("SOURCE_SHA", "OLD_SHA", "NEW_SHA", "PREDECESSOR_SHA", "ROLLBACK_SHA"):
        _require_sha(values[field], field)
    _require_sha256(values["ARTIFACT_SHA256"], "ARTIFACT_SHA256")
    _require_sha256(values["SBOM_SHA256"], "SBOM_SHA256")
    if MIGRATION_RE.fullmatch(values["MIGRATION_HEAD"]) is None:
        raise ValueError("MIGRATION_HEAD is not a canonical migration filename")
    _require_utc(values["DEPLOYED_AT_UTC"], "DEPLOYED_AT_UTC")
    _require_utc(values["UPDATED_AT"], "UPDATED_AT")

    source_sha = values["SOURCE_SHA"]
    old_sha = values["OLD_SHA"]
    if values["NEW_SHA"] != source_sha:
        raise ValueError("NEW_SHA must equal SOURCE_SHA")
    if values["RELEASE_ID"] != f"{RELEASE_PREFIX}{source_sha}":
        raise ValueError("RELEASE_ID must equal retail-release-SOURCE_SHA")
    if values["PREDECESSOR_SHA"] != old_sha:
        raise ValueError("PREDECESSOR_SHA must equal OLD_SHA")
    if values["ROLLBACK_SHA"] != old_sha:
        raise ValueError("ROLLBACK_SHA must equal OLD_SHA")
    if values["PREDECESSOR_RELEASE_ID"] != f"{RELEASE_PREFIX}{old_sha}":
        raise ValueError("PREDECESSOR_RELEASE_ID must equal retail-release-PREDECESSOR_SHA")
    if values["ROLLBACK_RELEASE_ID"] != f"{RELEASE_PREFIX}{old_sha}":
        raise ValueError("ROLLBACK_RELEASE_ID must equal retail-release-ROLLBACK_SHA")
    return values


def render_markdown(values: dict[str, str]) -> str:
    values = validate_deployed_promotion(values)
    tag = f"{TAG_PREFIX}{values['RELEASE_ID']}"
    lines = [
        "# UniHub Retail production deployment view",
        "",
        "> **Generated view — not production authority.** This Markdown is derived from an exact D2 `release.env` promotion record. The machine-readable promotion record remains authoritative; the signed candidate identity remains `RELEASE_MANIFEST.json`.",
        "",
        "| Field | Verified value |",
        "| --- | --- |",
        f"| Promotion state | `{values['STATE']}` |",
        f"| Release ID | `{values['RELEASE_ID']}` |",
        f"| Source SHA | `{values['SOURCE_SHA']}` |",
        f"| Canonical production tag | `{tag}` |",
        f"| Migration head | `{values['MIGRATION_HEAD']}` |",
        f"| Artifact SHA-256 | `{values['ARTIFACT_SHA256']}` |",
        f"| SBOM SHA-256 | `{values['SBOM_SHA256']}` |",
        f"| Deployed at UTC | `{values['DEPLOYED_AT_UTC']}` |",
        f"| Predecessor release | `{values['PREDECESSOR_RELEASE_ID']}` |",
        f"| Predecessor SHA | `{values['PREDECESSOR_SHA']}` |",
        f"| Rollback release | `{values['ROLLBACK_RELEASE_ID']}` |",
        f"| Rollback SHA | `{values['ROLLBACK_SHA']}` |",
        "",
        "The canonical D3 tag is immutable promotion-history evidence. It does not replace the D2 deployment state and this rendered view does not select or declare a repository-managed `current`/`latest` release.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_env", type=Path, help="Exact D2 release.env promotion record")
    args = parser.parse_args()
    try:
        values = validate_deployed_promotion(parse_release_env(args.release_env))
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    print(render_markdown(values), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
