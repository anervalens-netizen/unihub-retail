#!/usr/bin/env python3
"""Enforce the exact Release-A source/tooling scope and direct typecheck."""

from __future__ import annotations

import argparse
import hashlib
import json
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
RELEASE_B_EVIDENCE_CURRENT_PATHS = {
    ".agent/PLANS.md",
    "docs/exec-plans/active/UR-CLOSE-20260812.md",
    "scripts/check_release_a_candidate.py",
    "scripts/release-a-source-contract-v1.json",
    "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql",
    "backend/db/migrations/manifest.json",
    "backend/db/migrations/README.md",
    "backend/tests/test_release_a_schema_069.py",
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


def verify_lock(
    *, current_paths: set[str] | None = None
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    lock = load_json(ROOT / ".agent/contract-lock.json")
    if lock.get("revision") != 9 or lock.get("baseline_source_sha") != EXPECTED_BASELINE:
        raise ValueError("Release-A requires exact contract lock revision 9 and baseline")
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
        raise ValueError("revision-9 lock must have exactly one immutable lock commit")
    lock_commit = lock_commits[0]
    lock_parents = git("show", "-s", "--format=%P", lock_commit).split()
    if lock_parents != [content_commit]:
        raise ValueError("revision-9 lock commit must directly follow content commit")
    current_lock_blob = git("rev-parse", "HEAD:.agent/contract-lock.json")
    locked_blob = git("rev-parse", f"{lock_commit}:.agent/contract-lock.json")
    if current_lock_blob != locked_blob:
        raise ValueError("current revision-9 lock differs from its sole lock commit")
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
    output_path: Path,
) -> int:
    started = time.monotonic()
    evidence = load_json(input_path)
    lock, locked_objects = verify_lock(current_paths=RELEASE_B_EVIDENCE_CURRENT_PATHS)
    if len(expected_sha) != 40 or git("rev-parse", expected_sha) != expected_sha:
        raise ValueError("expected Release-A SHA is not an exact commit")
    expected_tree = git("rev-parse", f"{expected_sha}^{{tree}}")
    lock_commit = str(lock["verified_lock_commit"])
    checks: dict[str, bool] = {
        "result_pass": evidence.get("result") == "PASS",
        "release_a_sha": evidence.get("release_a_sha") == expected_sha,
        "candidate_tree": evidence.get("candidate_tree") == expected_tree,
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
    checks["database_identities"] = (
        len(identity_entries) == 3
        and all(isinstance(entry, dict) for entry in identity_entries)
        and len({entry.get("database_name") for entry in identity_entries}) == 3
    )
    locked_by_path = {item["path"]: item for item in locked_objects}
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
            and set(candidate.get("changed_paths", [])) == EXPECTED_CHANGED_PATHS
            and isinstance(mypy, dict)
            and mypy.get("exit_code") == 0
            and mypy.get("success_marker") is True
            and mypy.get("shadow_or_substitution") is False
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
            junit_ok = totals == {"tests": 6, "failures": 0, "errors": 0, "skipped": 0}
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
            "--evidence",
            str(output_path),
        ],
        "expected_release_a_sha": expected_sha,
        "expected_release_a_tree": expected_tree,
        "contract_content_commit": lock["contract_content_commit"],
        "contract_lock_commit": lock_commit,
        "source_evidence_sha256": sha256_bytes(input_path.read_bytes()),
        "checks": checks,
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
    args = parser.parse_args()
    evidence_path = args.evidence if args.evidence.is_absolute() else ROOT / args.evidence
    if args.verify_main_evidence is not None:
        if args.expected_sha is None:
            parser.error("--expected-sha is required with --verify-main-evidence")
        input_path = (
            args.verify_main_evidence
            if args.verify_main_evidence.is_absolute()
            else ROOT / args.verify_main_evidence
        )
        try:
            return verify_main_evidence(input_path, args.expected_sha, evidence_path)
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
