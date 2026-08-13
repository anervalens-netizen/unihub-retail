#!/usr/bin/env python3
"""Enforce the exact Release-A source/tooling scope and direct typecheck."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


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
MUTABLE_CURRENT_LOCK_PATHS = {
    "docs/exec-plans/active/UR-CLOSE-20260812.md",
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


def verify_lock() -> tuple[dict[str, Any], list[dict[str, str]]]:
    lock = load_json(ROOT / ".agent/contract-lock.json")
    if lock.get("revision") != 8 or lock.get("baseline_source_sha") != EXPECTED_BASELINE:
        raise ValueError("Release-A requires exact contract lock revision 8 and baseline")
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
        raise ValueError("revision-8 lock must have exactly one immutable lock commit")
    lock_commit = lock_commits[0]
    lock_parents = git("show", "-s", "--format=%P", lock_commit).split()
    if lock_parents != [content_commit]:
        raise ValueError("revision-8 lock commit must directly follow content commit")
    current_lock_blob = git("rev-parse", "HEAD:.agent/contract-lock.json")
    locked_blob = git("rev-parse", f"{lock_commit}:.agent/contract-lock.json")
    if current_lock_blob != locked_blob:
        raise ValueError("current revision-8 lock differs from its sole lock commit")
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
        if path not in MUTABLE_CURRENT_LOCK_PATHS:
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


def main() -> int:
    started = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence_path = args.evidence if args.evidence.is_absolute() else ROOT / args.evidence
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
