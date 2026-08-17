#!/usr/bin/env python3
"""is_high_risk_category_touched.py

PR-fast deploy-sandbox classifier.

Decides whether the exact-SHA deploy and rollback sandbox step must run on a
PR-fast pull_request run.

Contract:
    0   = TOUCHED        (the PR diff touches any path in the BASE deploy-release-ci
                          category OR in the sandbox direct-input supplement)
    10  = NOT_TOUCHED    (cleanly classified; no relevant change)
    20  = ERROR          (any failure: bad input, missing BASE manifest,
                          malformed manifest, unknown category, bad base SHA,
                          git merge-base failure, git diff failure, exception)

Source of truth:
    - The deploy-release-ci path list is loaded from the PR BASE SHA
      (`git show <PR_BASE_SHA>:.github/governance/high-risk-paths.json`),
      NOT from the PR HEAD. This prevents a PR that edits the governance
      manifest from weakening its own sandbox classification.
    - The sandbox direct-input supplement is a fixed inline tuple below.

The classifier itself is itself governed by deploy-release-ci: any change to
`scripts/is_high_risk_category_touched.py` is therefore a deploy-release-ci
high-risk PR change (see .github/governance/high-risk-paths.json).

Deterministic matching only:
    exact:  changed_path == entry
    prefix: entry.endswith("/") AND changed_path.startswith(entry)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

MANIFEST_PATH = ".github/governance/high-risk-paths.json"

# Sandbox-direct inputs that are NOT in deploy-release-ci but are read by the
# sandbox or its direct callees. Pure runtime-CI semantics, NOT governance.
# Update on any new tracked input added to ops/test-deploy-retail-artifact.sh
# or its direct callees ops/deploy-retail-artifact.sh and ops/build-retail-release-artifact.sh.
SANDBOX_DIRECT_INPUT_SUPPLEMENT = (
    "package.json",
    "package-lock.json",
    "unihub-worker.service",
    "ops/observability/retail-process-scrape.yml",
    "ops/observability/retail-slo-rules.yml",
    "backend/requirements.lock",
    "scripts/validate_release_sbom.py",
)

EXIT_TOUCHED = 0
EXIT_NOT_TOUCHED = 10
EXIT_ERROR = 20


def _fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(EXIT_ERROR)


def _run(args, cwd=None):
    """Run subprocess with timeout, return CompletedProcess or raise on error."""
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def _is_prefix(entry: str) -> bool:
    return entry.endswith("/")


def _match(changed: str, entry: str) -> bool:
    if _is_prefix(entry):
        return changed.startswith(entry)
    return changed == entry


def _load_base_manifest(repo_root: pathlib.Path, base_sha: str) -> dict:
    """Load the manifest from the PR BASE SHA via `git show`.

    Trust anchor: PR_BASE_SHA, NOT HEAD. A PR that modifies the governance
    manifest cannot weaken its own sandbox classification.
    """
    if not base_sha:
        _fail("empty --base-sha")
    if not re.fullmatch(r"[0-9a-f]{7,64}", base_sha):
        _fail(f"--base-sha is not a valid git object id: {base_sha!r}")
    out = _run(["git", "show", f"{base_sha}:{MANIFEST_PATH}"], cwd=repo_root)
    if out.returncode != 0:
        _fail(
            f"cannot read BASE manifest {MANIFEST_PATH} from {base_sha}: "
            f"{out.stderr.strip()}"
        )
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError as e:
        _fail(f"BASE manifest is not valid JSON: {e}")
    if not isinstance(data, dict):
        _fail("BASE manifest root must be a JSON object")
    cats = data.get("categories")
    if not isinstance(cats, dict) or not cats:
        _fail("BASE manifest must define a non-empty 'categories' object")
    return data


def _category_paths(manifest: dict, category: str) -> list:
    cats = manifest.get("categories", {})
    if category not in cats:
        _fail(f"unknown category in BASE manifest: {category}")
    body = cats[category]
    if not isinstance(body, dict):
        _fail(f"manifest category '{category}' must be an object")
    paths = body.get("paths")
    if (
        not isinstance(paths, list)
        or not paths
        or not all(isinstance(x, str) and x for x in paths)
    ):
        _fail(
            f"manifest category '{category}' must have a non-empty "
            f"'paths' list of strings"
        )
    for entry in paths:
        if any(c in entry for c in ("*", "?", "[", "]")):
            _fail(
                f"manifest category '{category}' uses glob syntax: {entry!r}"
            )
    return paths


def _changed_files(repo_root: pathlib.Path, merge_base: str, head_sha: str) -> list:
    """Return changed files from merge_base..head_sha, --no-renames."""
    out = _run(
        ["git", "diff", "--name-only", "--no-renames", f"{merge_base}..{head_sha}"],
        cwd=repo_root,
    )
    if out.returncode != 0:
        _fail(f"git diff failed (rc={out.returncode}): {out.stderr.strip()}")
    files = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    seen, deduped = set(), []
    for f in files:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    return deduped


def _resolve_merge_base(repo_root: pathlib.Path, base_sha: str, head_sha: str) -> str:
    out = _run(["git", "merge-base", base_sha, head_sha], cwd=repo_root)
    if out.returncode != 0:
        _fail(
            f"git merge-base failed (rc={out.returncode}): {out.stderr.strip()}"
        )
    result = out.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{7,64}", result):
        _fail(f"git merge-base returned invalid SHA: {result!r}")
    return result


def _resolve_head(repo_root: pathlib.Path) -> str:
    out = _run(["git", "rev-parse", "HEAD"], cwd=repo_root)
    if out.returncode != 0:
        _fail(f"git rev-parse HEAD failed: {out.stderr.strip()}")
    head = out.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{7,64}", head):
        _fail(f"git rev-parse HEAD returned invalid SHA: {head!r}")
    return head


def _match_any(changed: str, entries) -> bool:
    for entry in entries:
        if _match(changed, entry):
            return True
    return False


def _classify(manifest: dict, supplement, changed_files: list, category: str) -> int:
    manifest_paths = _category_paths(manifest, category)
    for f in changed_files:
        if _match_any(f, manifest_paths):
            return EXIT_TOUCHED
        if _match_any(f, supplement):
            return EXIT_TOUCHED
    return EXIT_NOT_TOUCHED


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="deploy-release-ci")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    repo_root = pathlib.Path(args.repo_root).resolve()
    try:
        manifest = _load_base_manifest(repo_root, args.base_sha)
        head_sha = _resolve_head(repo_root)
        merge_base = _resolve_merge_base(repo_root, args.base_sha, head_sha)
        changed = _changed_files(repo_root, merge_base, head_sha)
    except SystemExit:
        raise
    except Exception as e:
        _fail(f"unexpected error: {e!r}")
    return _classify(manifest, SANDBOX_DIRECT_INPUT_SUPPLEMENT, changed, args.category)


if __name__ == "__main__":
    sys.exit(main())

