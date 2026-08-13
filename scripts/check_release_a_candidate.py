#!/usr/bin/env python3
"""Enforce the exact Release-A source/tooling scope and direct typecheck."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BASELINE = "0be82b430e55b7414babf470abe3fc5404b6cdc9"
EXPECTED_CHANGED_PATHS = {
    ".agent/PLANS.md",
    ".agent/contract-lock.json",
    ".github/workflows/ci.yml",
    "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql",
    "backend/db/migrations/README.md",
    "backend/db/migrations/manifest.json",
    "backend/services/grile_pilot_v2.py",
    "backend/tests/test_release_a_schema_069.py",
    "docs/contracts/ai-governance-golden-v1.json",
    "docs/contracts/business-golden-v2.json",
    "docs/contracts/query-parameter-policy-v1.json",
    "docs/exec-plans/active/UR-CLOSE-20260812.md",
    "scripts/check_release_a_candidate.py",
    "scripts/frontend-critical-coverage.json",
    "scripts/python-complexity-contract-v1.json",
    "scripts/release-a-source-contract-v1.json",
    "scripts/run_real_e2e.sh",
    "scripts/run_release_a_schema_gate.sh",
    "scripts/target-mutation-contract-v2.json",
    "scripts/verify_promtool_cache.sh",
}
EXPECTED_TYPECHECK_STEP = """      - name: Python typecheck
        run: |
          set +e
          venv/bin/mypy . --ignore-missing-imports --explicit-package-bases \\
            > mypy-report.txt 2>&1
          status=$?
          cat mypy-report.txt
          exit $status
"""
EXPECTED_RELEASE_A_TESTS = {
    "test_069_is_additive_empty_and_old_ai_insert_remains_compatible",
    "test_069_seals_cohort_and_requires_exact_completed_run_lineage",
    "test_069_outbox_is_canonical_private_ordered_and_replayable",
    "test_069_runtime_roles_have_exact_producer_privileges",
    "test_release_a_runtime_starts_and_is_ready_on_069",
    "test_pre_069_manifest_is_refused_after_schema_upgrade",
}
PYTHON_CLOSURE_ANCHOR = """      - name: Python complexity ratchet
        working-directory: .
        run: backend/venv/bin/python scripts/check_complexity_ratchet.py
"""
PYTHON_CLOSURE_INSERT = """
      - name: Python complexity closure contract
        working-directory: .
        run: |
          backend/venv/bin/python scripts/check_python_complexity_contract.py \\
            --contract scripts/python-complexity-contract-v1.json \\
            --evidence test-results/python-complexity-contract.json
"""
FRONTEND_STRUCTURE_ANCHOR = """      - name: TypeScript complexity ratchet
        run: node scripts/check_ts_function_complexity.cjs
"""
FRONTEND_STRUCTURE_INSERT = """
      - name: Frontend structure closure contract
        run: |
          node scripts/check_frontend_structure_contract.mjs \\
            --manifest scripts/frontend-critical-coverage.json \\
            --evidence test-results/frontend-structure-contract.json
"""
FRONTEND_COVERAGE_ANCHOR = """      - name: Unit tests with global coverage floor
        run: npm run test:coverage
"""
FRONTEND_COVERAGE_INSERT = """
      - name: Frontend critical coverage closure contract
        run: |
          node scripts/check_frontend_critical_coverage.mjs \\
            --manifest scripts/frontend-critical-coverage.json \\
            --coverage coverage/coverage-final.json \\
            --evidence test-results/frontend-critical-coverage.json
"""
RELEASE_B_EVIDENCE_CURRENT_PATHS = {
    ".agent/PLANS.md",
    "docs/exec-plans/active/UR-CLOSE-20260812.md",
    "scripts/check_release_a_candidate.py",
    "scripts/release-a-source-contract-v1.json",
    "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql",
    "backend/db/migrations/manifest.json",
    "backend/db/migrations/README.md",
    "backend/tests/test_release_a_schema_069.py",
    "scripts/verify_promtool_cache.sh",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def is_submapping(candidate: Any, baseline: Any) -> bool:
    """Allow mappings to keep unchanged scalar values and monotonically delete keys."""
    if isinstance(baseline, dict):
        return isinstance(candidate, dict) and all(
            key in baseline and is_submapping(value, baseline[key])
            for key, value in candidate.items()
        )
    return candidate == baseline


def expected_release_b_workflow(baseline: str) -> str:
    result = baseline
    for anchor, insertion in (
        (PYTHON_CLOSURE_ANCHOR, PYTHON_CLOSURE_INSERT),
        (FRONTEND_STRUCTURE_ANCHOR, FRONTEND_STRUCTURE_INSERT),
        (FRONTEND_COVERAGE_ANCHOR, FRONTEND_COVERAGE_INSERT),
    ):
        if result.count(anchor) != 1:
            raise ValueError("Release-A CI anchor is not exact")
        result = result.replace(anchor, anchor + insertion)
    return result


def verify_release_b_mutation_policy(
    expected_candidate_sha: str,
    expected_release_a_sha: str,
    locked_by_path: dict[str, dict[str, str]],
) -> dict[str, Any]:
    if (
        len(expected_candidate_sha) != 40
        or git("rev-parse", expected_candidate_sha) != expected_candidate_sha
    ):
        raise ValueError("expected Release-B candidate SHA is not an exact commit")
    if git("rev-parse", "HEAD") != expected_candidate_sha:
        raise ValueError("Release-B verifier is not running at expected candidate HEAD")
    if git("status", "--porcelain"):
        raise ValueError("Release-B verifier requires a clean worktree including untracked files")
    if subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", expected_release_a_sha, "HEAD"],
        check=False,
    ).returncode != 0:
        raise ValueError("Release-A SHA is not an ancestor of Release-B candidate")

    immutable_current = {
        ".agent/PLANS.md",
        "docs/exec-plans/active/UR-CLOSE-20260812.md",
        "docs/contracts/query-parameter-policy-v1.json",
        "docs/contracts/business-golden-v2.json",
        "docs/contracts/ai-governance-golden-v1.json",
        "scripts/frontend-critical-coverage.json",
        "scripts/target-mutation-contract-v2.json",
        "scripts/python-complexity-contract-v1.json",
        "scripts/release-a-source-contract-v1.json",
        "scripts/check_release_a_candidate.py",
        "scripts/run_release_a_schema_gate.sh",
        "scripts/run_real_e2e.sh",
        "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql",
        "backend/db/migrations/manifest.json",
        "backend/db/migrations/README.md",
        "backend/tests/test_release_a_schema_069.py",
        "scripts/verify_promtool_cache.sh",
    }
    for path in immutable_current:
        expected_digest = locked_by_path.get(path, {}).get("sha256")
        if expected_digest is None or sha256_bytes((ROOT / path).read_bytes()) != expected_digest:
            raise ValueError(f"Release-B immutable contract drift: {path}")

    monotonic_ratchets = (
        (
            "scripts/complexity-ratchet.json",
            ("legacy_max_lines", "legacy_max_python_function_lines"),
        ),
        (
            "scripts/ts-function-complexity-ratchet.json",
            ("legacy_max_function_lines",),
        ),
    )
    ratchet_evidence: dict[str, Any] = {}
    content_commit = str(load_json(ROOT / ".agent/contract-lock.json")["contract_content_commit"])
    for path, legacy_keys in monotonic_ratchets:
        baseline = json.loads(
            subprocess.check_output(
                ["git", "-C", str(ROOT), "show", f"{content_commit}:{path}"]
            )
        )
        current = load_json(ROOT / path)
        nonlegacy_baseline = {key: value for key, value in baseline.items() if key not in legacy_keys}
        nonlegacy_current = {key: value for key, value in current.items() if key not in legacy_keys}
        if nonlegacy_current != nonlegacy_baseline:
            raise ValueError(f"Release-B ratchet policy drift outside legacy maps: {path}")
        counts: dict[str, dict[str, int]] = {}
        for key in legacy_keys:
            before = baseline.get(key)
            after = current.get(key)
            if not is_submapping(after, before):
                raise ValueError(f"Release-B ratchet added or changed a waiver: {path}:{key}")
            if after != {}:
                raise ValueError(f"Release-B ratchet did not finish empty: {path}:{key}")
            counts[key] = {"baseline": len(before), "candidate": len(after)}
        ratchet_evidence[path] = counts

    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    baseline_workflow = subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f"{content_commit}:.github/workflows/ci.yml"],
        text=True,
    )
    if workflow != expected_release_b_workflow(baseline_workflow):
        raise ValueError("Release-B CI is not the exact three-gate transform of Release-A CI")
    if workflow.count(EXPECTED_TYPECHECK_STEP) != 1:
        raise ValueError("Release-B CI changed direct mypy semantics")
    forbidden = ("--shadow-file", "mypy_shadow", "pilot_shadow")
    if any(token in workflow for token in forbidden):
        raise ValueError("Release-B CI reintroduced typecheck substitution")
    required_ci_tokens = (
        "scripts/verify_promtool_cache.sh prepare",
        "promtool-cache-${{ github.sha }}",
        '--cache-dir "${RUNNER_TOOL_CACHE}/unihub-prometheus"',
        "--sha256 \"$PROMETHEUS_SHA256\"",
        "scripts/check_complexity_ratchet.py",
        "scripts/check_python_complexity_contract.py",
        "scripts/check_frontend_critical_coverage.mjs",
        "scripts/check_frontend_structure_contract.mjs",
        "ops/build-retail-release-artifact.sh \"$GITHUB_SHA\" release-artifact",
        "retail-release-${{ github.sha }}",
        "SOURCE_SHA",
        "SHA256SUMS",
    )
    missing_ci = [token for token in required_ci_tokens if token not in workflow]
    if missing_ci:
        raise ValueError(f"Release-B CI lost required semantics: {missing_ci}")
    if "prometheus/releases/download" in workflow or "curl " in workflow[workflow.index("Operational configuration validation"):workflow.index("Exact-SHA deploy and rollback sandbox")]:
        raise ValueError("Release-B operational CI retains an unbounded direct download")
    return {
        "candidate_sha": expected_candidate_sha,
        "candidate_tree": git("rev-parse", "HEAD^{tree}"),
        "release_a_is_ancestor": True,
        "immutable_paths": sorted(immutable_current),
        "ratchets": ratchet_evidence,
        "ci_sha256": sha256_bytes(workflow.encode("utf-8")),
        "ci_exact_three_gate_transform": True,
        "ci_required_tokens": list(required_ci_tokens),
        "ci_direct_mypy": True,
        "ci_direct_prometheus_download": False,
    }


def verify_release_a_artifact(artifact_dir: Path, expected_sha: str) -> dict[str, Any]:
    archive_name = f"retail-release-{expected_sha}.tar.gz"
    checksummed_names = {
        "SOURCE_SHA",
        archive_name,
        "SBOM.cdx.json",
        "SBOM.npm.cdx.json",
        "SBOM.python.cdx.json",
        "PROVENANCE.json",
        "RELEASE_MANIFEST.json",
    }
    required = {
        *checksummed_names,
        "SHA256SUMS",
        "RELEASE_MANIFEST.sigstore.json",
    }
    missing = sorted(
        name
        for name in required
        if not (artifact_dir / name).is_file() or (artifact_dir / name).is_symlink()
    )
    if missing:
        raise ValueError(f"Release-A artifact evidence is incomplete: {missing}")
    if (artifact_dir / "SOURCE_SHA").read_text(encoding="utf-8").strip() != expected_sha:
        raise ValueError("Release-A artifact SOURCE_SHA mismatch")
    checksums: dict[str, str] = {}
    for line in (artifact_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise ValueError("Release-A artifact SHA256SUMS line is invalid")
        name = parts[1].lstrip("*")
        if Path(name).name != name or name in checksums:
            raise ValueError("Release-A artifact SHA256SUMS path is unsafe or duplicated")
        target = artifact_dir / name
        if (
            not target.is_file()
            or target.is_symlink()
            or sha256_bytes(target.read_bytes()) != parts[0]
        ):
            raise ValueError(f"Release-A artifact checksum mismatch: {name}")
        checksums[name] = parts[0]
    if set(checksums) != checksummed_names:
        raise ValueError("Release-A artifact SHA256SUMS inventory mismatch")
    manifest = load_json(artifact_dir / "RELEASE_MANIFEST.json")
    if manifest.get("schemaVersion") != 1 or manifest.get("sourceSha") != expected_sha:
        raise ValueError("Release-A release manifest source SHA mismatch")
    if manifest.get("archive") != archive_name:
        raise ValueError("Release-A release manifest archive is not checksummed")
    manifest_digests = manifest.get("sha256")
    expected_manifest_names = checksummed_names - {"RELEASE_MANIFEST.json"}
    if not isinstance(manifest_digests, dict) or set(manifest_digests) != expected_manifest_names:
        raise ValueError("Release-A release manifest checksum inventory mismatch")
    if any(manifest_digests[name] != checksums[name] for name in expected_manifest_names):
        raise ValueError("Release-A release manifest checksum mismatch")
    archive = artifact_dir / archive_name
    if not archive.is_file():
        raise ValueError("Release-A release archive is absent")
    archive_digest = sha256_bytes(archive.read_bytes())
    if archive_digest != checksums[archive_name]:
        raise ValueError("Release-A archive digest mismatch")
    provenance = load_json(artifact_dir / "PROVENANCE.json")
    sigstore_bundle = load_json(artifact_dir / "RELEASE_MANIFEST.sigstore.json")
    if not sigstore_bundle:
        raise ValueError("Release-A Sigstore bundle is empty")
    subjects = provenance.get("subject")
    if (
        provenance.get("_type") != "https://in-toto.io/Statement/v1"
        or provenance.get("predicateType") != "https://slsa.dev/provenance/v1"
        or not isinstance(subjects, list)
        or len(subjects) != 1
        or subjects[0].get("name") != archive_name
        or subjects[0].get("digest", {}).get("sha256") != archive_digest
    ):
        raise ValueError("Release-A provenance subject mismatch")
    predicate = provenance.get("predicate")
    build_definition = predicate.get("buildDefinition") if isinstance(predicate, dict) else None
    external = build_definition.get("externalParameters") if isinstance(build_definition, dict) else None
    resolved = build_definition.get("resolvedDependencies") if isinstance(build_definition, dict) else None
    if not isinstance(external, dict) or external.get("sourceSha") != expected_sha:
        raise ValueError("Release-A provenance external source SHA mismatch")
    if not isinstance(resolved, list) or not any(
        isinstance(item, dict) and item.get("digest", {}).get("gitCommit") == expected_sha
        for item in resolved
    ):
        raise ValueError("Release-A provenance resolved dependency mismatch")
    cosign_command = [
        os.environ.get("COSIGN_BIN", "cosign"),
        "verify-blob",
        str(artifact_dir / "RELEASE_MANIFEST.json"),
        "--bundle",
        str(artifact_dir / "RELEASE_MANIFEST.sigstore.json"),
        "--certificate-identity",
        "https://github.com/anervalens-netizen/unihub-retail/.github/workflows/ci.yml@refs/heads/main",
        "--certificate-oidc-issuer",
        "https://token.actions.githubusercontent.com",
    ]
    signature = subprocess.run(
        cosign_command,
        capture_output=True,
        text=True,
        check=False,
    )
    signature_output = signature.stdout + signature.stderr
    if signature.returncode != 0:
        raise ValueError("Release-A Sigstore verification failed")
    return {
        "directory": str(artifact_dir.resolve()),
        "source_sha": expected_sha,
        "archive": archive_name,
        "archive_sha256": archive_digest,
        "release_manifest_sha256": sha256_bytes(
            (artifact_dir / "RELEASE_MANIFEST.json").read_bytes()
        ),
        "provenance_sha256": sha256_bytes((artifact_dir / "PROVENANCE.json").read_bytes()),
        "sigstore_bundle_sha256": sha256_bytes(
            (artifact_dir / "RELEASE_MANIFEST.sigstore.json").read_bytes()
        ),
        "sigstore_verified": True,
        "sigstore_command": cosign_command,
        "sigstore_output_sha256": sha256_bytes(signature_output.encode("utf-8")),
        "checksummed_file_count": len(checksums),
    }


def verify_lock(
    *, current_paths: set[str] | None = None
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    lock = load_json(ROOT / ".agent/contract-lock.json")
    if lock.get("revision") != 10 or lock.get("baseline_source_sha") != EXPECTED_BASELINE:
        raise ValueError("Release-A requires exact contract lock revision 10 and baseline")
    content_commit = str(lock["contract_content_commit"])
    lock_commits = list(
        filter(
            None,
            git(
                "rev-list",
                "--reverse",
                f"{content_commit}..HEAD",
                "--",
                ".agent/contract-lock.json",
            ).splitlines(),
        )
    )
    if len(lock_commits) != 1:
        raise ValueError("revision-10 lock must have exactly one immutable lock commit")
    lock_commit = lock_commits[0]
    lock_parents = git("show", "-s", "--format=%P", lock_commit).split()
    if lock_parents != [content_commit]:
        raise ValueError("revision-10 lock commit must directly follow content commit")
    current_lock_blob = git("rev-parse", "HEAD:.agent/contract-lock.json")
    locked_blob = git("rev-parse", f"{lock_commit}:.agent/contract-lock.json")
    if current_lock_blob != locked_blob:
        raise ValueError("current revision-10 lock differs from its sole lock commit")
    lock["verified_lock_commit"] = lock_commit
    verified: list[dict[str, str]] = []
    locked_objects = [lock["plan"], *lock["assets"]]
    for item in locked_objects:
        path = str(item["path"])
        expected_blob = str(item["git_blob"])
        expected_digest = str(item["sha256"])
        actual_blob = git("rev-parse", f"{content_commit}:{path}")
        payload = subprocess.check_output(
            ["git", "-C", str(ROOT), "show", f"{content_commit}:{path}"]
        )
        actual_digest = sha256_bytes(payload)
        if actual_blob != expected_blob or actual_digest != expected_digest:
            raise ValueError(f"locked object mismatch: {path}")
        if current_paths is None or path in current_paths:
            current = (ROOT / path).read_bytes()
            if sha256_bytes(current) != expected_digest:
                raise ValueError(f"current locked asset drift: {path}")
        verified.append(
            {"path": path, "git_blob": actual_blob, "sha256": actual_digest}
        )
    return lock, verified


def verify_source_transform() -> dict[str, str]:
    contract = load_json(ROOT / "scripts/release-a-source-contract-v1.json")
    if contract.get("baseline_source_sha") != EXPECTED_BASELINE:
        raise ValueError("source transform baseline mismatch")
    changes = contract.get("changes")
    if not isinstance(changes, list) or len(changes) != 1:
        raise ValueError("source transform must contain exactly one change")
    change = changes[0]
    path = str(change["path"])
    if path != "backend/services/grile_pilot_v2.py":
        raise ValueError("unexpected Release-A application source path")
    baseline_payload = subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f"{EXPECTED_BASELINE}:{path}"]
    )
    current_payload = (ROOT / path).read_bytes()
    expected_text = baseline_payload.decode("utf-8")
    required_edits = change.get("required_edits")
    if not isinstance(required_edits, list) or len(required_edits) != 2:
        raise ValueError("source transform requires exactly two declared edits")
    replacement, insertion = required_edits
    before = str(replacement["before"])
    after = str(replacement["after"])
    occurrences = int(replacement["occurrences"])
    if expected_text.count(before) != occurrences:
        raise ValueError("source transform replacement occurrence mismatch")
    expected_text = expected_text.replace(before, after)
    anchor = str(insertion["after_anchor"])
    inserted = str(insertion["insert"])
    insert_occurrences = int(insertion["occurrences"])
    if expected_text.count(anchor) != insert_occurrences:
        raise ValueError("source transform insertion anchor occurrence mismatch")
    expected_text = expected_text.replace(anchor, anchor + inserted)
    if current_payload != expected_text.encode("utf-8"):
        raise ValueError("current source is not the exact declared baseline transform")
    baseline_blob = git("rev-parse", f"{EXPECTED_BASELINE}:{path}")
    current_blob = git("hash-object", path)
    checks = {
        "baseline_git_blob": baseline_blob,
        "baseline_sha256": sha256_bytes(baseline_payload),
        "result_git_blob": current_blob,
        "result_sha256": sha256_bytes(current_payload),
    }
    for key, actual in checks.items():
        if actual != str(change[key]):
            raise ValueError(f"source transform {key} mismatch")
    text = current_payload.decode("utf-8")
    if text.count("from typing import TYPE_CHECKING, Any") != 1:
        raise ValueError("TYPE_CHECKING typing import is not exact")
    if text.count("if TYPE_CHECKING:\n    from services.grile_pilot_v2_registry import PilotV2Sheet") != 1:
        raise ValueError("PilotV2Sheet type-only import is not exact")
    return {"path": path, **checks}


def verify_scope() -> list[str]:
    changed = set(
        filter(
            None,
            git("diff", "--name-only", EXPECTED_BASELINE, "HEAD").splitlines(),
        )
    )
    if changed != EXPECTED_CHANGED_PATHS:
        missing = sorted(EXPECTED_CHANGED_PATHS - changed)
        extra = sorted(changed - EXPECTED_CHANGED_PATHS)
        raise ValueError(f"Release-A path scope mismatch; missing={missing}; extra={extra}")
    return sorted(changed)


def verify_ci_typecheck() -> str:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    if workflow.count(EXPECTED_TYPECHECK_STEP) != 1:
        raise ValueError("CI direct mypy step differs from the frozen command")
    forbidden = ("--shadow-file", "mypy_shadow", "pilot_shadow")
    present = [token for token in forbidden if token in workflow]
    if present:
        raise ValueError(f"CI typecheck substitution is forbidden: {present}")
    return sha256_bytes(EXPECTED_TYPECHECK_STEP.encode("utf-8"))


def run_direct_mypy() -> tuple[list[str], subprocess.CompletedProcess[str]]:
    command = [
        "venv/bin/mypy",
        ".",
        "--ignore-missing-imports",
        "--explicit-package-bases",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT / "backend",
        capture_output=True,
        text=True,
        check=False,
    )
    return command, result


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_main_evidence(
    input_path: Path,
    expected_sha: str,
    expected_candidate_sha: str,
    release_a_artifact_dir: Path,
    output_path: Path,
) -> int:
    started = time.monotonic()
    evidence = load_json(input_path)
    lock, locked_objects = verify_lock(current_paths=RELEASE_B_EVIDENCE_CURRENT_PATHS)
    if len(expected_sha) != 40 or git("rev-parse", expected_sha) != expected_sha:
        raise ValueError("expected Release-A SHA is not an exact commit")
    expected_tree = git("rev-parse", f"{expected_sha}^{{tree}}")
    expected_evidence_path = (
        ROOT / "test-results" / "closure" / expected_sha / "release-a" / "schema-gate.json"
    ).resolve()
    if input_path.resolve() != expected_evidence_path:
        raise ValueError("Release-A evidence is not at the exact SHA-bound canonical path")
    lock_commit = str(lock["verified_lock_commit"])
    checks: dict[str, bool] = {
        "schema_version": evidence.get("schema_version") == 1,
        "result_pass": evidence.get("result") == "PASS",
        "baseline_sha": evidence.get("baseline_sha") == EXPECTED_BASELINE,
        "release_a_sha": evidence.get("release_a_sha") == expected_sha,
        "candidate_tree": evidence.get("candidate_tree") == expected_tree,
        "command": evidence.get("command")
        == [
            "scripts/run_release_a_schema_gate.sh",
            "--evidence",
            str(input_path),
        ],
        "changed_paths": evidence.get("changed_paths") == sorted(EXPECTED_CHANGED_PATHS),
        "changed_path_count": evidence.get("changed_path_count")
        == len(EXPECTED_CHANGED_PATHS),
        "contract_content_commit": evidence.get("contract_content_commit")
        == lock.get("contract_content_commit"),
        "contract_lock_commit": evidence.get("contract_lock_commit") == lock_commit,
        "main_contains_lock": subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", lock_commit, expected_sha],
            check=False,
        ).returncode
        == 0,
    }
    required_assertions = {
        "database_identities_distinct",
        "empty_database_initially_zero_tables",
        "empty_database_bootstrap_through_069",
        "sanitized_dump_restore",
        "restored_database_pre_upgrade_through_068",
        "restored_database_upgrade_068_to_069",
        "final_schema_ledgers_equal",
        "final_schema_catalogs_equal",
        "exact_source_transform",
        "direct_unshadowed_full_mypy",
        "release_a_runtime_ready_on_empty",
        "release_a_runtime_ready_on_restored",
        "pre_069_manifest_refused_on_empty",
        "pre_069_manifest_refused_on_restored",
        "outbox_inert",
    }
    assertions = evidence.get("assertions")
    checks["assertions"] = isinstance(assertions, dict) and {
        key for key, value in assertions.items() if value is True
    } == required_assertions
    database_paths = evidence.get("database_paths")
    identity_entries = []
    if isinstance(database_paths, dict):
        identity_entries = [
            database_paths.get(name)
            for name in ("baseline_068", "empty_initial", "restored_pre_upgrade")
        ]
    if isinstance(database_paths, dict):
        baseline = database_paths.get("baseline_068", {})
        empty_initial = database_paths.get("empty_initial", {})
        empty_final = database_paths.get("empty_final", {})
        restored_pre = database_paths.get("restored_pre_upgrade", {})
        restored_final = database_paths.get("restored_final", {})
    else:
        baseline = empty_initial = empty_final = restored_pre = restored_final = {}
    checks["database_identities"] = (
        len(identity_entries) == 3
        and all(isinstance(entry, dict) for entry in identity_entries)
        and len({entry.get("database_name") for entry in identity_entries}) == 3
        and empty_final.get("database_name") == empty_initial.get("database_name")
        and restored_final.get("database_name")
        == restored_pre.get("database_name")
    )
    checks["empty_initial_state"] = (
        empty_initial.get("public_table_count") == 0
        and empty_initial.get("migration_count") == 0
        and empty_initial.get("last_migration") is None
        and empty_initial.get("restored_marker_count") == 0
    )
    checks["baseline_068_state"] = (
        baseline.get("migration_count") == 68
        and baseline.get("last_migration") == "068_grile_v2_forecast_digest_authority.sql"
        and baseline.get("public_table_count", 0) > 0
        and bool(re.fullmatch(r"[0-9a-f]{64}", str(baseline.get("ledger_sha256", ""))))
    )
    checks["restored_pre_upgrade_state"] = (
        restored_pre.get("migration_count") == 68
        and restored_pre.get("last_migration") == "068_grile_v2_forecast_digest_authority.sql"
        and restored_pre.get("ledger_sha256") == baseline.get("ledger_sha256")
        and restored_pre.get("public_table_count") == baseline.get("public_table_count")
        and restored_pre.get("restored_marker_count") == 1
    )
    for label, final, marker_count in (
        ("empty", empty_final, 0),
        ("restored", restored_final, 1),
    ):
        checks[f"{label}_final_state"] = (
            final.get("migration_count") == 69
            and final.get("last_migration") == "069_ai_cohort_and_transactional_outbox.sql"
            and final.get("migration_069_checksum") == evidence.get("migration_069_sha256")
            and final.get("outbox_event_count") == 0
            and final.get("restored_marker_count") == marker_count
            and final.get("schema_catalog_entry_count", 0) > 0
            and bool(re.fullmatch(r"[0-9a-f]{64}", str(final.get("ledger_sha256", ""))))
            and bool(
                re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(final.get("schema_catalog_sha256", "")),
                )
            )
        )
    checks["final_ledgers_equal"] = (
        empty_final.get("ledger_sha256") == restored_final.get("ledger_sha256")
        and empty_final.get("ledger_sha256") is not None
    )
    checks["final_catalogs_equal"] = (
        empty_final.get("schema_catalog_sha256") == restored_final.get("schema_catalog_sha256")
        and empty_final.get("schema_catalog_sha256") is not None
    )
    locked_by_path = {item["path"]: item for item in locked_objects}
    release_b_policy = verify_release_b_mutation_policy(
        expected_candidate_sha,
        expected_sha,
        locked_by_path,
    )
    release_a_artifact = verify_release_a_artifact(release_a_artifact_dir, expected_sha)
    checks["release_b_candidate_identity"] = (
        release_b_policy["candidate_sha"] == expected_candidate_sha
        and release_b_policy["release_a_is_ancestor"] is True
    )
    immutable_files = {
        "migration_069_sha256": "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql",
        "manifest_sha256": "backend/db/migrations/manifest.json",
        "compatibility_test_sha256": "backend/tests/test_release_a_schema_069.py",
    }
    for evidence_key, relative_path in immutable_files.items():
        digest = sha256_bytes((ROOT / relative_path).read_bytes())
        checks[evidence_key] = (
            evidence.get(evidence_key) == digest
            and locked_by_path.get(relative_path, {}).get("sha256") == digest
        )
    artifact_files = {
        "candidate_gate_sha256": "release-a-candidate.json",
        "junit_empty_sha256": "release-a-schema-empty.xml",
        "junit_restored_sha256": "release-a-schema-restored.xml",
    }
    for evidence_key, filename in artifact_files.items():
        artifact = input_path.parent / filename
        checks[evidence_key] = artifact.is_file() and evidence.get(evidence_key) == sha256_bytes(
            artifact.read_bytes()
        )
    candidate_artifact = input_path.parent / "release-a-candidate.json"
    if candidate_artifact.is_file():
        candidate = load_json(candidate_artifact)
        mypy = candidate.get("mypy")
        checks["candidate_evidence_identity"] = (
            candidate.get("result") == "PASS"
            and candidate.get("candidate_sha") == expected_sha
            and candidate.get("candidate_tree") == expected_tree
            and candidate.get("contract_content_commit") == lock.get("contract_content_commit")
            and candidate.get("contract_lock_commit") == lock_commit
            and candidate.get("changed_paths") == sorted(EXPECTED_CHANGED_PATHS)
            and isinstance(mypy, dict)
            and mypy.get("exit_code") == 0
            and mypy.get("success_marker") is True
            and mypy.get("shadow_or_substitution") is False
        )
        locked_objects = candidate.get("locked_objects")
        checks["candidate_locked_objects"] = (
            isinstance(locked_objects, list)
            and len(locked_objects) == len(locked_by_path)
            and {
                (item.get("path"), item.get("git_blob"), item.get("sha256"))
                for item in locked_objects
                if isinstance(item, dict)
            }
            == {
                (item["path"], item["git_blob"], item["sha256"])
                for item in locked_by_path.values()
            }
        )
        source_transform = candidate.get("source_transform")
        locked_source = locked_by_path["scripts/release-a-source-contract-v1.json"]
        checks["candidate_source_transform"] = (
            isinstance(source_transform, dict)
            and source_transform.get("path") == "backend/services/grile_pilot_v2.py"
            and source_transform.get("baseline_git_blob") == "299a6130c8226f2f6de7c239ccfb59bbfb8cae8c"
            and source_transform.get("baseline_sha256")
            == "e781187478527d41a607d90081e786ed7816cdf89b57fe39aca2872c1d1010b6"
            and source_transform.get("result_git_blob") == "9cc93035b4a39144faa503cd94144f3e57f7ff8f"
            and source_transform.get("result_sha256") == "b63686dc43a1541dc1d4aebdbd52bf6efb5c545d231aacf2d8e5a85b25922f6a"
            and locked_source.get("sha256")
            == "feb14f72f7a637733c75b79649113d7973615185466f7a9399e43541d1d2e4ed"
        )
        checks["candidate_mypy_command"] = isinstance(mypy, dict) and mypy.get("command") == [
            "cd",
            "backend",
            "&&",
            "venv/bin/mypy",
            ".",
            "--ignore-missing-imports",
            "--explicit-package-bases",
        ]
        checks["candidate_mypy_output_hash"] = isinstance(mypy, dict) and bool(
            re.fullmatch(r"[0-9a-f]{64}", str(mypy.get("output_sha256", "")))
        )
        checks["candidate_ci_block_hash"] = candidate.get("ci_typecheck_step_sha256") == sha256_bytes(
            EXPECTED_TYPECHECK_STEP.encode("utf-8")
        )
    else:
        checks["candidate_evidence_identity"] = False
    for label in ("empty", "restored"):
        junit_path = input_path.parent / f"release-a-schema-{label}.xml"
        junit_ok = False
        if junit_path.is_file():
            root = ET.parse(junit_path).getroot()
            suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
            totals = {
                key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
                for key in ("tests", "failures", "errors", "skipped")
            }
            testcases = {
                (case.attrib.get("classname"), case.attrib.get("name"))
                for case in root.iter("testcase")
            }
            expected_cases = {
                ("backend.tests.test_release_a_schema_069", name)
                for name in EXPECTED_RELEASE_A_TESTS
            }
            junit_ok = (
                totals == {"tests": 6, "failures": 0, "errors": 0, "skipped": 0}
                and testcases == expected_cases
            )
        checks[f"junit_{label}_six_of_six"] = junit_ok
    checks["dump_sha256_shape"] = bool(
        re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("pre_069_dump_sha256", "")))
    )
    failures = sorted(key for key, passed in checks.items() if not passed)
    output = {
        "schema_version": 1,
        "result": "PASS" if not failures else "FAIL",
        "command": [
            "scripts/check_release_a_candidate.py",
            "--verify-main-evidence",
            str(input_path),
            "--expected-sha",
            expected_sha,
            "--expected-candidate-sha",
            expected_candidate_sha,
            "--release-a-artifact-dir",
            str(release_a_artifact_dir),
            "--evidence",
            str(output_path),
        ],
        "expected_release_a_sha": expected_sha,
        "expected_release_a_tree": expected_tree,
        "expected_release_b_sha": expected_candidate_sha,
        "expected_release_b_tree": release_b_policy["candidate_tree"],
        "contract_content_commit": lock["contract_content_commit"],
        "contract_lock_commit": lock_commit,
        "source_evidence_sha256": sha256_bytes(input_path.read_bytes()),
        "checks": checks,
        "release_b_policy": release_b_policy,
        "release_a_artifact": release_a_artifact,
        "failures": failures,
        "duration_seconds": round(time.monotonic() - started, 6),
    }
    write_evidence(output_path, output)
    if failures:
        print(f"FAIL: Release-A main evidence mismatches: {failures}", file=sys.stderr)
        return 1
    print(json.dumps({"result": "PASS", "release_a_sha": expected_sha}))
    return 0


def main() -> int:
    started = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--verify-main-evidence", type=Path)
    parser.add_argument("--expected-sha")
    parser.add_argument("--expected-candidate-sha")
    parser.add_argument("--release-a-artifact-dir", type=Path)
    args = parser.parse_args()
    evidence_path = args.evidence if args.evidence.is_absolute() else ROOT / args.evidence
    if args.verify_main_evidence is not None:
        if (
            args.expected_sha is None
            or args.expected_candidate_sha is None
            or args.release_a_artifact_dir is None
        ):
            parser.error(
                "--expected-sha, --expected-candidate-sha and --release-a-artifact-dir are required with --verify-main-evidence"
            )
        input_path = (
            args.verify_main_evidence
            if args.verify_main_evidence.is_absolute()
            else ROOT / args.verify_main_evidence
        )
        try:
            artifact_dir = (
                args.release_a_artifact_dir
                if args.release_a_artifact_dir.is_absolute()
                else ROOT / args.release_a_artifact_dir
            )
            return verify_main_evidence(
                input_path,
                args.expected_sha,
                args.expected_candidate_sha,
                artifact_dir,
                evidence_path,
            )
        except (KeyError, OSError, subprocess.CalledProcessError, ValueError) as exc:
            write_evidence(
                evidence_path,
                {"schema_version": 1, "result": "FAIL", "failures": [str(exc)]},
            )
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "baseline_sha": EXPECTED_BASELINE,
        "candidate_sha": git("rev-parse", "HEAD"),
        "candidate_tree": git("rev-parse", "HEAD^{tree}"),
        "result": "FAIL",
    }
    failures: list[str] = []
    try:
        if git("status", "--porcelain", "--untracked-files=no"):
            raise ValueError("tracked worktree must be clean")
        lock, locked_objects = verify_lock()
        evidence["contract_revision"] = lock["revision"]
        evidence["contract_content_commit"] = lock["contract_content_commit"]
        evidence["contract_lock_commit"] = lock["verified_lock_commit"]
        evidence["locked_objects"] = locked_objects
        evidence["changed_paths"] = verify_scope()
        evidence["source_transform"] = verify_source_transform()
        evidence["ci_typecheck_step_sha256"] = verify_ci_typecheck()
    except (KeyError, OSError, subprocess.CalledProcessError, ValueError) as exc:
        failures.append(str(exc))

    command, mypy = run_direct_mypy()
    mypy_output = mypy.stdout + mypy.stderr
    evidence["mypy"] = {
        "command": ["cd", "backend", "&&", *command],
        "exit_code": mypy.returncode,
        "output_sha256": sha256_bytes(mypy_output.encode("utf-8")),
        "success_marker": "Success: no issues found" in mypy_output,
        "shadow_or_substitution": False,
    }
    if mypy.returncode != 0 or "Success: no issues found" not in mypy_output:
        failures.append("direct unshadowed full mypy failed")
    evidence["failures"] = failures
    if not failures:
        evidence["result"] = "PASS"
    evidence["duration_seconds"] = round(time.monotonic() - started, 6)
    write_evidence(evidence_path, evidence)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        if mypy_output:
            print(mypy_output, file=sys.stderr, end="")
        return 1
    print(json.dumps({"result": "PASS", "candidate_sha": evidence["candidate_sha"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
