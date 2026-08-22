#!/usr/bin/env python3
"""Create or verify the canonical annotated Git tag for a promoted Retail release.

D3 contract:
- a production tag is created only after the deploy workflow job succeeds;
- tag name is deterministic: production/<D2 releaseId>;
- the annotated tag points to the exact source commit;
- the annotation preserves the signed candidate identity plus the first
  successful CI/deploy workflow run IDs;
- an existing canonical tag is immutable: exact identity matches are
  idempotent, while lightweight/conflicting/malformed tags fail closed.

The caller supplies a short-lived GitHub token with Contents: write. This
module uses only the GitHub Git database REST endpoints and never shells out to
git or gh.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

SHA40_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
MIGRATION_RE = re.compile(r"[0-9]{3}_[A-Za-z0-9_]+\.sql")
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
RUN_ID_RE = re.compile(r"[0-9]+")
RELEASE_PREFIX = "retail-release-"
TAG_NAMESPACE = "production/"
TAG_KIND = "unihub-retail-production-promotion"
TAG_SCHEMA_VERSION = 1

JsonDict = dict[str, Any]
RequestFn = Callable[[str, str, str, JsonDict | None], JsonDict]


class GitHubApiError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GitHub API HTTP {status}: {message}")
        self.status = status
        self.message = message


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def validate_release_identity(
    *,
    source_sha: str,
    release_id: str,
    migration_head: str,
    artifact_sha256: str,
    sbom_sha256: str,
) -> dict[str, str]:
    if SHA40_RE.fullmatch(source_sha) is None:
        raise ValueError("source SHA must be exactly 40 lowercase hex characters")
    expected_release_id = f"{RELEASE_PREFIX}{source_sha}"
    if release_id != expected_release_id:
        raise ValueError("releaseId must equal retail-release-<source SHA>")
    if MIGRATION_RE.fullmatch(migration_head) is None:
        raise ValueError("migrationHead is not a canonical migration filename")
    if SHA256_RE.fullmatch(artifact_sha256) is None:
        raise ValueError("artifactSha256 must be exactly 64 lowercase hex characters")
    if SHA256_RE.fullmatch(sbom_sha256) is None:
        raise ValueError("sbomSha256 must be exactly 64 lowercase hex characters")
    return {
        "sourceSha": source_sha,
        "releaseId": release_id,
        "migrationHead": migration_head,
        "artifactSha256": artifact_sha256,
        "sbomSha256": sbom_sha256,
    }


def production_tag_name(identity: dict[str, str]) -> str:
    release_id = identity["releaseId"]
    source_sha = identity["sourceSha"]
    if release_id != f"{RELEASE_PREFIX}{source_sha}":
        raise ValueError("release identity is internally inconsistent")
    return f"{TAG_NAMESPACE}{release_id}"


def _validate_run_id(value: str, name: str) -> str:
    if RUN_ID_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must contain decimal digits only")
    return value


def build_tag_message(
    identity: dict[str, str], *, ci_run_id: str, deploy_run_id: str
) -> str:
    _validate_run_id(ci_run_id, "ciRunId")
    _validate_run_id(deploy_run_id, "deployRunId")
    payload: dict[str, Any] = {
        "schemaVersion": TAG_SCHEMA_VERSION,
        "kind": TAG_KIND,
        **identity,
        "ciRunId": ci_run_id,
        "deployRunId": deploy_run_id,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"


def verify_tag_message(message: Any, identity: dict[str, str]) -> dict[str, Any]:
    text = _require_string(message, "annotated tag message")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("annotated tag message is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("annotated tag message root must be an object")

    expected_keys = {
        "schemaVersion",
        "kind",
        "sourceSha",
        "releaseId",
        "migrationHead",
        "artifactSha256",
        "sbomSha256",
        "ciRunId",
        "deployRunId",
    }
    if set(payload) != expected_keys:
        raise ValueError("annotated tag message has an unexpected field set")
    if payload.get("schemaVersion") != TAG_SCHEMA_VERSION:
        raise ValueError("annotated tag schemaVersion is unsupported")
    if payload.get("kind") != TAG_KIND:
        raise ValueError("annotated tag kind is invalid")
    for key, expected in identity.items():
        if payload.get(key) != expected:
            raise ValueError(f"annotated tag identity mismatch: {key}")
    _validate_run_id(_require_string(payload.get("ciRunId"), "ciRunId"), "ciRunId")
    _validate_run_id(_require_string(payload.get("deployRunId"), "deployRunId"), "deployRunId")
    return payload


def _request_json(
    method: str, path: str, token: str, payload: JsonDict | None = None
) -> JsonDict:
    if not token:
        raise ValueError("GitHub token is required")
    url = f"https://api.github.com/{path.lstrip('/')}"
    body = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "unihub-retail-production-tag-writer",
    }
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except OSError:
            detail = exc.reason or "HTTP error"
        raise GitHubApiError(exc.code, detail[:2000]) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API request failed: {exc.reason}") from exc
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub API returned malformed JSON") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("GitHub API returned a non-object response")
    return decoded


def _tag_ref_path(repository: str, tag_name: str) -> str:
    ref = urllib.parse.quote(f"tags/{tag_name}", safe="/")
    return f"repos/{repository}/git/ref/{ref}"


def _verify_existing_tag(
    *,
    repository: str,
    tag_name: str,
    identity: dict[str, str],
    token: str,
    ref_payload: JsonDict,
    request: RequestFn,
) -> None:
    ref_object = ref_payload.get("object")
    if not isinstance(ref_object, dict):
        raise ValueError("production tag ref has no Git object")
    if ref_object.get("type") != "tag":
        raise ValueError("canonical production tag must be annotated, not lightweight")
    tag_object_sha = _require_string(ref_object.get("sha"), "tag object SHA")
    if SHA40_RE.fullmatch(tag_object_sha) is None:
        raise ValueError("annotated tag object SHA is invalid")

    tag_payload = request(
        "GET", f"repos/{repository}/git/tags/{tag_object_sha}", token, None
    )
    if tag_payload.get("sha") != tag_object_sha:
        raise ValueError("annotated tag object SHA mismatch")
    if tag_payload.get("tag") != tag_name:
        raise ValueError("annotated tag name mismatch")
    target = tag_payload.get("object")
    if not isinstance(target, dict):
        raise ValueError("annotated tag target is missing")
    if target.get("type") != "commit":
        raise ValueError("canonical production tag must target a commit")
    if target.get("sha") != identity["sourceSha"]:
        raise ValueError("canonical production tag points to the wrong source SHA")
    verify_tag_message(tag_payload.get("message"), identity)


def _get_existing_ref(
    *, repository: str, tag_name: str, token: str, request: RequestFn
) -> JsonDict | None:
    try:
        return request("GET", _tag_ref_path(repository, tag_name), token, None)
    except GitHubApiError as exc:
        if exc.status == 404:
            return None
        raise


def ensure_production_tag(
    *,
    repository: str,
    token: str,
    identity: dict[str, str],
    ci_run_id: str,
    deploy_run_id: str,
    request: RequestFn = _request_json,
) -> tuple[str, str]:
    if REPOSITORY_RE.fullmatch(repository) is None:
        raise ValueError("repository must use owner/name form")
    _validate_run_id(ci_run_id, "ciRunId")
    _validate_run_id(deploy_run_id, "deployRunId")
    tag_name = production_tag_name(identity)

    existing = _get_existing_ref(
        repository=repository, tag_name=tag_name, token=token, request=request
    )
    if existing is not None:
        _verify_existing_tag(
            repository=repository,
            tag_name=tag_name,
            identity=identity,
            token=token,
            ref_payload=existing,
            request=request,
        )
        return "existing", tag_name

    message = build_tag_message(
        identity, ci_run_id=ci_run_id, deploy_run_id=deploy_run_id
    )
    tag_object = request(
        "POST",
        f"repos/{repository}/git/tags",
        token,
        {
            "tag": tag_name,
            "message": message,
            "object": identity["sourceSha"],
            "type": "commit",
        },
    )
    tag_object_sha = _require_string(tag_object.get("sha"), "created tag object SHA")
    if SHA40_RE.fullmatch(tag_object_sha) is None:
        raise ValueError("created annotated tag object SHA is invalid")

    try:
        request(
            "POST",
            f"repos/{repository}/git/refs",
            token,
            {"ref": f"refs/tags/{tag_name}", "sha": tag_object_sha},
        )
    except GitHubApiError as exc:
        if exc.status != 422:
            raise
        # A concurrent/retried promotion may have won the immutable ref race.
        # Accept it only after the same strict identity verification.

    final_ref = _get_existing_ref(
        repository=repository, tag_name=tag_name, token=token, request=request
    )
    if final_ref is None:
        raise RuntimeError("production tag ref was not created")
    _verify_existing_tag(
        repository=repository,
        tag_name=tag_name,
        identity=identity,
        token=token,
        ref_payload=final_ref,
        request=request,
    )
    return "created", tag_name


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--migration-head", required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--sbom-sha256", required=True)
    parser.add_argument("--ci-run-id", required=True)
    parser.add_argument("--deploy-run-id", required=True)
    args = parser.parse_args()

    try:
        identity = validate_release_identity(
            source_sha=args.source_sha,
            release_id=args.release_id,
            migration_head=args.migration_head,
            artifact_sha256=args.artifact_sha256,
            sbom_sha256=args.sbom_sha256,
        )
        status, tag_name = ensure_production_tag(
            repository=args.repository,
            token=os.environ.get("GITHUB_TOKEN", ""),
            identity=identity,
            ci_run_id=args.ci_run_id,
            deploy_run_id=args.deploy_run_id,
        )
    except (GitHubApiError, OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(f"production-tag: {status}: {tag_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
