#!/usr/bin/env python3
"""Deterministic D2 release candidate identity helpers.

The signed RELEASE_MANIFEST.json remains candidate authority. This module only
adds/verifies deterministic identity fields derived from already-produced build
artifacts and the immutable migration manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from typing import Any

SHA40_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
MIGRATION_RE = re.compile(r"(?P<id>[0-9]{3})_[A-Za-z0-9_]+\.sql")


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"unsafe JSON input: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _sha256(path: pathlib.Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"unsafe digest input: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migration_head(repo: pathlib.Path) -> str:
    manifest_path = repo / "backend/db/migrations/manifest.json"
    payload = _read_json(manifest_path)
    migrations = payload.get("migrations")
    if payload.get("version") != 1 or not isinstance(migrations, dict) or not migrations:
        raise ValueError("migration manifest is missing or invalid")

    parsed: list[tuple[int, str]] = []
    seen_ids: set[int] = set()
    for name, digest in migrations.items():
        if not isinstance(name, str) or not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise ValueError("migration manifest entry is invalid")
        match = MIGRATION_RE.fullmatch(name)
        if match is None:
            raise ValueError(f"migration filename is non-canonical: {name}")
        migration_id = int(match.group("id"))
        if migration_id in seen_ids:
            raise ValueError(f"duplicate migration id: {migration_id:03d}")
        seen_ids.add(migration_id)
        parsed.append((migration_id, name))
    parsed.sort()
    return parsed[-1][1]


def expected_release_id(source_sha: str) -> str:
    if SHA40_RE.fullmatch(source_sha) is None:
        raise ValueError("source SHA must be 40 lowercase hex characters")
    return f"retail-release-{source_sha}"


def enrich_manifest(repo: pathlib.Path, manifest_path: pathlib.Path) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    source_sha = manifest.get("sourceSha")
    archive = manifest.get("archive")
    digests = manifest.get("sha256")
    if not isinstance(source_sha, str) or SHA40_RE.fullmatch(source_sha) is None:
        raise ValueError("release manifest sourceSha is invalid")
    if not isinstance(archive, str) or pathlib.PurePosixPath(archive).name != archive:
        raise ValueError("release manifest archive is invalid")
    if not isinstance(digests, dict):
        raise ValueError("release manifest sha256 inventory is invalid")
    artifact_sha256 = digests.get(archive)
    sbom_sha256 = digests.get("SBOM.cdx.json")
    if not isinstance(artifact_sha256, str) or SHA256_RE.fullmatch(artifact_sha256) is None:
        raise ValueError("release manifest artifact digest is missing or invalid")
    if not isinstance(sbom_sha256, str) or SHA256_RE.fullmatch(sbom_sha256) is None:
        raise ValueError("release manifest aggregate SBOM digest is missing or invalid")

    manifest["releaseId"] = expected_release_id(source_sha)
    manifest["migrationHead"] = migration_head(repo)
    manifest["artifactSha256"] = artifact_sha256
    manifest["sbomSha256"] = sbom_sha256
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return manifest


def verify_manifest(
    repo: pathlib.Path,
    manifest_path: pathlib.Path,
    expected_sha: str,
    expected_artifact_sha256: str,
) -> dict[str, str]:
    if SHA40_RE.fullmatch(expected_sha) is None:
        raise ValueError("expected source SHA is invalid")
    if SHA256_RE.fullmatch(expected_artifact_sha256) is None:
        raise ValueError("expected artifact digest is invalid")

    manifest = _read_json(manifest_path)
    archive = manifest.get("archive")
    digests = manifest.get("sha256")
    if manifest.get("schemaVersion") != 1:
        raise ValueError("release manifest schemaVersion is unsupported")
    if manifest.get("sourceSha") != expected_sha:
        raise ValueError("release manifest source SHA mismatch")
    if not isinstance(archive, str) or pathlib.PurePosixPath(archive).name != archive:
        raise ValueError("release manifest archive is invalid")
    if not isinstance(digests, dict):
        raise ValueError("release manifest sha256 inventory is invalid")

    sbom_sha256 = digests.get("SBOM.cdx.json")
    if manifest.get("releaseId") != expected_release_id(expected_sha):
        raise ValueError("release manifest releaseId mismatch")
    if manifest.get("migrationHead") != migration_head(repo):
        raise ValueError("release manifest migration head mismatch")
    if manifest.get("artifactSha256") != expected_artifact_sha256:
        raise ValueError("release manifest explicit artifact digest mismatch")
    if digests.get(archive) != expected_artifact_sha256:
        raise ValueError("release manifest archive digest mismatch")
    if not isinstance(sbom_sha256, str) or SHA256_RE.fullmatch(sbom_sha256) is None:
        raise ValueError("release manifest aggregate SBOM digest is missing or invalid")
    if manifest.get("sbomSha256") != sbom_sha256:
        raise ValueError("release manifest explicit SBOM digest mismatch")

    sbom_path = manifest_path.parent / "SBOM.cdx.json"
    if _sha256(sbom_path) != sbom_sha256:
        raise ValueError("release manifest aggregate SBOM file digest mismatch")

    return {
        "CANDIDATE_SOURCE_SHA": expected_sha,
        "CANDIDATE_RELEASE_ID": expected_release_id(expected_sha),
        "CANDIDATE_MIGRATION_HEAD": str(manifest["migrationHead"]),
        "CANDIDATE_ARTIFACT_SHA256": expected_artifact_sha256,
        "CANDIDATE_SBOM_SHA256": sbom_sha256,
    }


def _write_env(path: pathlib.Path, values: dict[str, str]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"identity output already exists: {path}")
    for key, value in values.items():
        if "\n" in value or "\r" in value or "=" in key:
            raise ValueError("unsafe identity env value")
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    enrich = subparsers.add_parser("enrich-manifest")
    enrich.add_argument("--repo", required=True, type=pathlib.Path)
    enrich.add_argument("--manifest", required=True, type=pathlib.Path)

    verify = subparsers.add_parser("verify-manifest")
    verify.add_argument("--repo", required=True, type=pathlib.Path)
    verify.add_argument("--manifest", required=True, type=pathlib.Path)
    verify.add_argument("--expected-sha", required=True)
    verify.add_argument("--expected-artifact-sha256", required=True)
    verify.add_argument("--env-output", required=True, type=pathlib.Path)

    args = parser.parse_args()
    try:
        if args.command == "enrich-manifest":
            enrich_manifest(args.repo, args.manifest)
        else:
            values = verify_manifest(
                args.repo,
                args.manifest,
                args.expected_sha,
                args.expected_artifact_sha256,
            )
            _write_env(args.env_output, values)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
