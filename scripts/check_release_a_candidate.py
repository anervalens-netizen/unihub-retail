#!/usr/bin/env python3
"""Enforce the exact Release-A source/tooling scope and direct typecheck."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BASELINE = "0be82b430e55b7414babf470abe3fc5404b6cdc9"
COSIGN_VERSION = "v3.1.3"
COSIGN_LINUX_AMD64_SHA256 = "4629c757b7618056f8ddd7e2625ae9fdd94c0372a65049520bc7d9df9efc7f71"
EXPECTED_CHANGED_PATHS = {
    ".agent/PLANS.md",
    ".agent/contract-lock.json",
    ".github/workflows/ci.yml",
    "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql",
    "backend/db/migrations/README.md",
    "backend/db/migrations/manifest.json",
    "backend/scripts/run_outbox_slo_workload.py",
    "backend/scripts/run_retail_scale_profile.py",
    "backend/services/grile_pilot_v2.py",
    "backend/tests/test_release_a_schema_069.py",
    "backend/tests/test_release_contract_tooling_security.py",
    "docs/contracts/ai-governance-golden-v1.json",
    "docs/contracts/business-golden-v2.json",
    "docs/contracts/query-parameter-policy-v1.json",
    "docs/exec-plans/active/UR-CLOSE-20260812.md",
    "scripts/check_release_a_candidate.py",
    "scripts/release-b-authority-contract-v1.json",
    "scripts/frontend-critical-coverage.json",
    "scripts/python-complexity-contract-v1.json",
    "scripts/release-a-source-contract-v1.json",
    "scripts/run_local_quality_gate.sh",
    "scripts/run_outbox_slo_gate.py",
    "scripts/run_real_e2e.sh",
    "scripts/run_release_a_schema_gate.sh",
    "scripts/run_retail_scale_gate.sh",
    "scripts/run_structural_characterization.sh",
    "scripts/structural-characterization-baseline-v1.json",
    "scripts/target-mutation-contract-v2.json",
    "scripts/verify_deployed_release.sh",
    "scripts/verify_promtool_cache.sh",
    "ops/build-retail-release-artifact.sh",
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
EXPECTED_AUTHORITY_CRITERIA = {
    "T-09A-L",
    *(f"AC-{index:02d}" for index in range(1, 18)),
}
EXPECTED_RELEASE_A_AUTHORITIES = {
    "backend/scripts/run_outbox_slo_workload.py",
    "backend/scripts/run_retail_scale_profile.py",
    "backend/tests/test_release_contract_tooling_security.py",
    "ops/build-retail-release-artifact.sh",
    "scripts/check_release_a_candidate.py",
    "scripts/run_local_quality_gate.sh",
    "scripts/run_outbox_slo_gate.py",
    "scripts/run_real_e2e.sh",
    "scripts/run_release_a_schema_gate.sh",
    "scripts/run_retail_scale_gate.sh",
    "scripts/run_structural_characterization.sh",
    "scripts/structural-characterization-baseline-v1.json",
    "scripts/verify_deployed_release.sh",
    "scripts/verify_promtool_cache.sh",
}
EXPECTED_AUTHORITY_PATHS = {
    ".bandit-baseline.json",
    ".coveragerc",
    ".secrets.baseline",
    "backend/architecture_contract.json",
    "backend/db/migration_runner.py",
    "backend/requirements-dev.lock",
    "backend/requirements.lock",
    "backend/scripts/bootstrap_test_db.py",
    "backend/scripts/check_critical_coverage.py",
    "backend/scripts/oidc_e2e_stub.py",
    "backend/scripts/run_ai_forecast_backtest.py",
    "backend/scripts/run_import_overlap_gate.py",
    "backend/scripts/run_mixed_load_gate.py",
    "backend/scripts/run_outbox_slo_workload.py",
    "backend/scripts/run_retail_scale_profile.py",
    "backend/scripts/run_tests_isolated.sh",
    "backend/tests/conftest.py",
    "backend/tests/test_ai_forecast_asof_cohort.py",
    "backend/tests/test_ai_forecast_backtest.py",
    "backend/tests/test_ai_forecast_governance.py",
    "backend/tests/test_ai_forecast_import_contract.py",
    "backend/tests/test_ai_forecast_response_contract.py",
    "backend/tests/test_business_golden_contract.py",
    "backend/tests/test_grile_monthly.py",
    "backend/tests/test_grile_monthly_operations.py",
    "backend/tests/test_grile_monthly_state.py",
    "backend/tests/test_grile_outbox_delivery.py",
    "backend/tests/test_grile_pilot_v2.py",
    "backend/tests/test_grile_repository_contracts.py",
    "backend/tests/test_grile_v2_contract.py",
    "backend/tests/test_outbox_replay.py",
    "backend/tests/test_outbox_worker_faults.py",
    "backend/tests/test_release_a_schema_069.py",
    "backend/tests/test_release_contract_tooling_security.py",
    "backend/tests/test_target_allocator_exact.py",
    "backend/tests/test_target_allocator_properties.py",
    "backend/tests/test_telemetry_privacy_contract.py",
    "backend/tests/test_transactional_outbox.py",
    "e2e/frontend-lifecycle.spec.ts",
    "e2e/helpers.ts",
    "e2e/pwa-release-lifecycle.spec.ts",
    "e2e/real-auth-stack.spec.ts",
    "eslint.config.js",
    "ops/build-retail-release-artifact.sh",
    "ops/config/retail-env.schema.json",
    "ops/observability/retail-slo-rules.test.yml",
    "ops/test-deploy-retail-artifact.sh",
    "package-lock.json",
    "package.json",
    "playwright.browser-smoke.config.ts",
    "playwright.config.ts",
    "playwright.pwa-workbox.config.ts",
    "playwright.real.config.ts",
    "pytest.ini",
    "scripts/bundle-budget-baseline.json",
    "scripts/check_ai_forecast_governance.py",
    "scripts/check_backend_architecture.py",
    "scripts/check_bandit_waivers.py",
    "scripts/check_bundle_budget.mjs",
    "scripts/check_business_golden.py",
    "scripts/check_changed_function_complexity.py",
    "scripts/check_changed_line_coverage.py",
    "scripts/check_complexity_ratchet.py",
    "scripts/check_dependency_policy.mjs",
    "scripts/check_docs_contract.py",
    "scripts/check_env_contract.py",
    "scripts/check_frontend_critical_coverage.mjs",
    "scripts/check_frontend_structure_contract.mjs",
    "scripts/check_prometheus_contract.py",
    "scripts/check_python_complexity_contract.py",
    "scripts/check_query_parameter_contract.py",
    "scripts/check_release_a_candidate.py",
    "scripts/check_ts_function_complexity.cjs",
    "scripts/generate_retail_contract.py",
    "scripts/run_local_quality_gate.sh",
    "scripts/run_outbox_slo_gate.py",
    "scripts/run_pwa_release_lifecycle.sh",
    "scripts/run_real_e2e.sh",
    "scripts/run_release_a_schema_gate.sh",
    "scripts/run_retail_scale_gate.sh",
    "scripts/run_shellcheck.sh",
    "scripts/run_structural_characterization.sh",
    "scripts/run_target_allocator_contract.py",
    "scripts/run_targeted_mutation_tests.py",
    "scripts/structural-characterization-baseline-v1.json",
    "scripts/verify_deployed_release.sh",
    "scripts/verify_promtool_cache.sh",
    "scripts/verify_vendored_npm_packages.mjs",
    "src/components/GrileMonthlyPanel.test.tsx",
    "src/features/agent-evaluation/AgentEvaluationCritical.test.tsx",
    "src/features/agents/AgentsCriticalViews.test.tsx",
    "src/features/ai-forecast/AiForecastViews.test.tsx",
    "src/features/campaigns/CampaignCriticalViews.test.tsx",
    "src/features/dashboard/DashboardCriticalHooks.test.tsx",
    "src/features/dashboard/DashboardCriticalViews.test.tsx",
    "src/features/salary/SalaryCriticalViews.test.tsx",
    "src/features/settings/exports/controls.test.tsx",
    "src/features/target-calculator/TargetCriticalViews.test.tsx",
    "src/features/visits/VisitsCritical.test.tsx",
    "src/lib/pwaNavigation.ts",
    "src/test/PnlLayoutCritical.test.tsx",
    "src/test/frontendLifecycleContract.test.ts",
    "src/test/setup.ts",
    "tsconfig.json",
    "vite.config.ts",
    "vitest.config.ts",
}
EXPECTED_AUTHORITY_SET_NAMES = {
    "backend_test_suite",
    "e2e_test_suite",
    "frontend_test_suite",
    "shell_script_suite",
}
EXPECTED_SOURCE_SNAPSHOTS = {
    "outbox_acceptance_contract": {
        "commit": "ce61b725f0c83b3527bcd88e1b47a8e2c3795380",
        "ref": "refs/tags/ur-close-20260812-outbox-contract-v1",
        "tree": "ec1590144b44d47aa9d9d3603813870cae482293",
    },
    "release_b_integrated_preview": {
        "commit": "71c6ebb98cd5a30faf02a002c16ebe2919b2e595",
        "ref": "refs/tags/ur-close-20260812-preview-v1",
        "tree": "1e6c675f0c8c199b74be7fb70450f986a704cc9a",
    },
    "scale_authority": {
        "commit": "e2daba1b45ff12852629889e48f01a9eb3a8a643",
        "ref": "refs/tags/ur-close-20260812-scale-authority-v1",
        "tree": "7cc64e58957e2bb9edb0fddc805d447e055ca22a",
    },
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
    "backend/tests/test_release_contract_tooling_security.py",
    "scripts/verify_promtool_cache.sh",
    "scripts/release-b-authority-contract-v1.json",
    "ops/build-retail-release-artifact.sh",
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


def git_path_identity(commit: str, path: str) -> tuple[str, str]:
    fields = git("ls-tree", commit, "--", path).split()
    if len(fields) < 4:
        return "", ""
    payload = subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f"{commit}:{path}"]
    )
    return fields[0], sha256_bytes(payload)


def verify_source_snapshots(
    *, require_ancestors: bool, verify_remote: bool = False
) -> dict[str, Any]:
    verified: dict[str, Any] = {}
    for name, expected in EXPECTED_SOURCE_SNAPSHOTS.items():
        commit = expected["commit"]
        ref = expected["ref"]
        tree = expected["tree"]
        if git("rev-parse", f"{ref}^{{commit}}") != commit:
            raise ValueError(f"Release-B source snapshot ref drift: {name}")
        if verify_remote:
            remote_ref = subprocess.run(
                ["git", "-C", str(ROOT), "ls-remote", "--tags", "origin", ref],
                capture_output=True,
                text=True,
                check=False,
            )
            if (
                remote_ref.returncode != 0
                or remote_ref.stdout.strip() != f"{commit}\t{ref}"
            ):
                raise ValueError(f"Release-B source snapshot remote ref drift: {name}")
        if git("rev-parse", f"{commit}^{{tree}}") != tree:
            raise ValueError(f"Release-B source snapshot tree drift: {name}")
        ancestor = subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"],
            check=False,
        ).returncode == 0
        if require_ancestors and not ancestor:
            raise ValueError(f"Release-B source snapshot is not an ancestor: {name}")
        verified[name] = {
            "commit": commit,
            "ref": ref,
            "tree": tree,
            "candidate_ancestor": ancestor,
            "remote_ref_verified": verify_remote,
        }
    return verified


def authority_set_selected_paths(name: str) -> set[str]:
    tracked = set(git("ls-tree", "-r", "--name-only", "HEAD").splitlines())
    if name == "backend_test_suite":
        return {
            path
            for path in tracked
            if path.startswith("backend/tests/test_") and path.endswith(".py")
        }
    if name == "frontend_test_suite":
        return {
            path
            for path in tracked
            if path.startswith("src/")
            and (path.endswith(".test.ts") or path.endswith(".test.tsx"))
        }
    if name == "e2e_test_suite":
        return {
            path for path in tracked if path.startswith("e2e/") and path.endswith(".ts")
        }
    if name == "shell_script_suite":
        return {path for path in tracked if path.endswith(".sh")}
    raise ValueError(f"unknown Release-B authority set: {name}")


def verify_authority_sets(contract: dict[str, Any]) -> dict[str, Any]:
    sets = contract.get("authority_sets")
    if not isinstance(sets, list):
        raise ValueError("Release-B authority sets are absent")
    names = {str(item.get("name", "")) for item in sets if isinstance(item, dict)}
    if names != EXPECTED_AUTHORITY_SET_NAMES or len(sets) != len(names):
        raise ValueError("Release-B authority set inventory mismatch")
    evidence: list[dict[str, Any]] = []
    for authority_set in sorted(sets, key=lambda item: str(item.get("name", ""))):
        name = str(authority_set.get("name", ""))
        supports = authority_set.get("supports")
        entries = authority_set.get("entries")
        if (
            not isinstance(supports, list)
            or supports != sorted(set(supports))
            or not supports
            or not set(supports) <= EXPECTED_AUTHORITY_CRITERIA
            or not isinstance(entries, list)
            or not entries
        ):
            raise ValueError(f"Release-B authority set is invalid: {name}")
        selected = authority_set_selected_paths(name)
        declared = [str(entry.get("path", "")) for entry in entries if isinstance(entry, dict)]
        if declared != sorted(selected) or len(declared) != len(entries):
            raise ValueError(f"Release-B authority set path drift: {name}")
        verified_entries: list[dict[str, str]] = []
        for entry in entries:
            path = str(entry.get("path", ""))
            expected_digest = str(entry.get("sha256", ""))
            expected_mode = str(entry.get("git_mode", ""))
            source_name = entry.get("source_snapshot")
            if (
                not re.fullmatch(r"[0-9a-f]{64}", expected_digest)
                or expected_mode not in {"100644", "100755"}
                or (
                    source_name is not None
                    and (
                        not isinstance(source_name, str)
                        or source_name not in EXPECTED_SOURCE_SNAPSHOTS
                    )
                )
            ):
                raise ValueError(f"Release-B authority set entry is invalid: {name}:{path}")
            target = ROOT / path
            actual_mode, actual_digest = git_path_identity("HEAD", path)
            if (
                not target.is_file()
                or target.is_symlink()
                or actual_mode != expected_mode
                or actual_digest != expected_digest
                or sha256_bytes(target.read_bytes()) != expected_digest
            ):
                raise ValueError(f"Release-B authority set entry drift: {name}:{path}")
            if source_name is not None:
                source_commit = EXPECTED_SOURCE_SNAPSHOTS[source_name]["commit"]
                if git_path_identity(source_commit, path) != (expected_mode, expected_digest):
                    raise ValueError(
                        f"Release-B authority set source drift: {name}:{path}"
                    )
            verified_entries.append(
                {"path": path, "git_mode": actual_mode, "sha256": actual_digest}
            )
        evidence.append(
            {
                "name": name,
                "supports": supports,
                "entry_count": len(verified_entries),
                "inventory_sha256": sha256_bytes(
                    json.dumps(
                        verified_entries, sort_keys=True, separators=(",", ":")
                    ).encode()
                ),
            }
        )
    return {"set_count": len(evidence), "sets": evidence}


def verify_release_b_authorities() -> dict[str, Any]:
    contract = load_json(ROOT / "scripts/release-b-authority-contract-v1.json")
    if (
        contract.get("schema_version") != 2
        or contract.get("baseline_source_sha") != EXPECTED_BASELINE
        or contract.get("acceptance_criteria")
        != sorted(EXPECTED_AUTHORITY_CRITERIA)
        or contract.get("release_a_authorities")
        != sorted(EXPECTED_RELEASE_A_AUTHORITIES)
        or contract.get("source_snapshots") != EXPECTED_SOURCE_SNAPSHOTS
    ):
        raise ValueError("Release-B authority contract identity mismatch")
    entries = contract.get("authorities")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Release-B authority contract is empty")
    verified: list[dict[str, Any]] = []
    seen: set[str] = set()
    covered_criteria: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Release-B authority entry is invalid")
        path = str(entry.get("path", ""))
        expected_digest = str(entry.get("sha256", ""))
        expected_mode = str(entry.get("git_mode", ""))
        source_name = entry.get("source_snapshot")
        supports = entry.get("supports")
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or Path(path).as_posix() != path
            or ".." in Path(path).parts
            or ".git" in Path(path).parts
            or path in seen
            or not re.fullmatch(r"[0-9a-f]{64}", expected_digest)
            or expected_mode not in {"100644", "100755"}
            or not isinstance(supports, list)
            or not all(isinstance(value, str) for value in supports)
            or supports != sorted(set(supports))
            or not supports
            or not set(supports) <= EXPECTED_AUTHORITY_CRITERIA
            or (
                source_name is not None
                and (
                    not isinstance(source_name, str)
                    or source_name not in EXPECTED_SOURCE_SNAPSHOTS
                )
            )
        ):
            raise ValueError(f"Release-B authority entry is unsafe: {path}")
        seen.add(path)
        covered_criteria.update(supports)
        target = ROOT / path
        if not target.is_file() or target.is_symlink():
            raise ValueError(f"Release-B authority is missing or unsafe: {path}")
        actual_digest = sha256_bytes(target.read_bytes())
        tree_fields = git("ls-tree", "HEAD", "--", path).split()
        actual_mode = tree_fields[0] if len(tree_fields) >= 3 else ""
        if actual_digest != expected_digest or actual_mode != expected_mode:
            raise ValueError(f"Release-B authority drift: {path}")
        if source_name is not None:
            source_commit = EXPECTED_SOURCE_SNAPSHOTS[source_name]["commit"]
            if git_path_identity(source_commit, path) != (expected_mode, expected_digest):
                raise ValueError(f"Release-B authority source drift: {path}")
        verified.append(
            {
                "path": path,
                "sha256": actual_digest,
                "git_mode": actual_mode,
                "supports": supports,
            }
        )
    expected_paths = contract.get("required_paths")
    if expected_paths != sorted(EXPECTED_AUTHORITY_PATHS) or seen != EXPECTED_AUTHORITY_PATHS:
        raise ValueError("Release-B authority required-path inventory mismatch")
    if not EXPECTED_RELEASE_A_AUTHORITIES <= seen:
        raise ValueError("Release-B authority lost an A-side authority")
    if covered_criteria != EXPECTED_AUTHORITY_CRITERIA:
        raise ValueError("Release-B authority acceptance coverage mismatch")
    snapshots = verify_source_snapshots(require_ancestors=True)
    authority_sets = verify_authority_sets(contract)
    return {
        "contract_sha256": sha256_bytes(
            (ROOT / "scripts/release-b-authority-contract-v1.json").read_bytes()
        ),
        "authority_count": len(verified),
        "authorities": verified,
        "source_snapshots": snapshots,
        "authority_sets": authority_sets,
    }


def verify_release_a_authority_seed() -> dict[str, Any]:
    """Bind every new A-side B authority before Release A can be published."""
    contract = load_json(ROOT / "scripts/release-b-authority-contract-v1.json")
    if (
        contract.get("schema_version") != 2
        or contract.get("baseline_source_sha") != EXPECTED_BASELINE
        or contract.get("release_a_authorities")
        != sorted(EXPECTED_RELEASE_A_AUTHORITIES)
        or contract.get("source_snapshots") != EXPECTED_SOURCE_SNAPSHOTS
    ):
        raise ValueError("Release-A authority seed identity mismatch")
    entries = contract.get("authorities")
    if not isinstance(entries, list):
        raise ValueError("Release-A authority seed entries are absent")
    by_path = {
        str(entry.get("path", "")): entry
        for entry in entries
        if isinstance(entry, dict)
    }
    verified: list[dict[str, str]] = []
    for path in sorted(EXPECTED_RELEASE_A_AUTHORITIES):
        entry = by_path.get(path)
        if not isinstance(entry, dict):
            raise ValueError(f"Release-A authority seed is absent: {path}")
        expected_digest = str(entry.get("sha256", ""))
        expected_mode = str(entry.get("git_mode", ""))
        target = ROOT / path
        tree_fields = git("ls-tree", "HEAD", "--", path).split()
        actual_mode = tree_fields[0] if len(tree_fields) >= 3 else ""
        if (
            not target.is_file()
            or target.is_symlink()
            or sha256_bytes(target.read_bytes()) != expected_digest
            or actual_mode != expected_mode
        ):
            raise ValueError(f"Release-A authority seed drift: {path}")
        verified.append(
            {"path": path, "sha256": expected_digest, "git_mode": expected_mode}
        )
    return {
        "contract_sha256": sha256_bytes(
            (ROOT / "scripts/release-b-authority-contract-v1.json").read_bytes()
        ),
        "authority_count": len(verified),
        "authorities": verified,
    }


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
        "backend/tests/test_release_contract_tooling_security.py",
        "scripts/verify_promtool_cache.sh",
        "scripts/release-b-authority-contract-v1.json",
        "ops/build-retail-release-artifact.sh",
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
        "Generate exact-main Release-A schema evidence",
        "retail-release-a-schema-${{ github.sha }}",
        "RELEASE_A_EVIDENCE_DIR",
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
        "authorities": verify_release_b_authorities(),
    }


def verify_release_a_artifact(
    artifact_dir: Path,
    expected_sha: str,
    *,
    require_release_a_evidence: bool = True,
) -> dict[str, Any]:
    archive_name = f"retail-release-{expected_sha}.tar.gz"
    release_a_evidence_names = {
        "schema-gate.json",
        "release-a-candidate.json",
        "release-a-schema-empty.xml",
        "release-a-schema-restored.xml",
    }
    checksummed_names = {
        "SOURCE_SHA",
        archive_name,
        "SBOM.cdx.json",
        "SBOM.npm.cdx.json",
        "SBOM.python.cdx.json",
        "PROVENANCE.json",
        "RELEASE_MANIFEST.json",
    }
    if require_release_a_evidence:
        checksummed_names.update(release_a_evidence_names)
    required = {
        *checksummed_names,
        "SHA256SUMS",
        "RELEASE_MANIFEST.sigstore.json",
    }
    actual_names = {
        entry.name
        for entry in artifact_dir.iterdir()
        if entry.name not in {".", ".."}
    }
    if actual_names != required:
        raise ValueError(
            "Release-A artifact inventory mismatch; "
            f"missing={sorted(required - actual_names)}; "
            f"extra={sorted(actual_names - required)}"
        )
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
    release_a_evidence = manifest.get("releaseAEvidence")
    if require_release_a_evidence:
        if (
            not isinstance(release_a_evidence, dict)
            or release_a_evidence.get("sourceSha") != expected_sha
            or not re.fullmatch(
                r"[0-9]+", str(release_a_evidence.get("workflowRunId", ""))
            )
            or release_a_evidence.get("files")
            != {name: checksums[name] for name in sorted(release_a_evidence_names)}
        ):
            raise ValueError("Release-A signed evidence identity mismatch")
    elif release_a_evidence is not None or release_a_evidence_names & actual_names:
        raise ValueError("Release-B artifact unexpectedly contains Release-A evidence")
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
    if external.get("releaseAEvidence") != release_a_evidence:
        raise ValueError("Release-A provenance evidence binding mismatch")
    if not isinstance(resolved, list) or not any(
        isinstance(item, dict) and item.get("digest", {}).get("gitCommit") == expected_sha
        for item in resolved
    ):
        raise ValueError("Release-A provenance resolved dependency mismatch")
    cosign_path_text = shutil.which("cosign")
    if cosign_path_text is None:
        raise ValueError("trusted cosign is unavailable")
    cosign_path = Path(cosign_path_text).resolve()
    if (
        not cosign_path.is_file()
        or sha256_bytes(cosign_path.read_bytes()) != COSIGN_LINUX_AMD64_SHA256
    ):
        raise ValueError("cosign binary digest mismatch")
    cosign_version = subprocess.run(
        [str(cosign_path), "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if (
        cosign_version.returncode != 0
        or not re.search(
            rf"(?m)^GitVersion:\s*{re.escape(COSIGN_VERSION)}\s*$",
            cosign_version.stdout + cosign_version.stderr,
        )
    ):
        raise ValueError("cosign version mismatch")
    cosign_command = [
        str(cosign_path),
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
        "release_a_evidence": release_a_evidence,
    }


def tree_inventory(root: Path, *, exclude_dist: bool = False) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if exclude_dist and relative.parts and relative.parts[0] == "dist":
            continue
        if path.is_symlink():
            raise ValueError(f"artifact tree contains a symlink: {relative.as_posix()}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"artifact tree contains a special file: {relative.as_posix()}")
        mode = stat.S_IMODE(path.stat().st_mode)
        entries.append(
            {
                "path": relative.as_posix(),
                "sha256": sha256_bytes(path.read_bytes()),
                "git_mode": "100755" if mode & 0o111 else "100644",
            }
        )
    return entries


def extract_regular_tar(archive: tarfile.TarFile, destination: Path) -> None:
    members = archive.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not (member.isdir() or member.isfile())
        ):
            raise ValueError(f"release archive member is unsafe: {member.name}")
    archive.extractall(destination, members=members, filter="data")


def build_exact_checkout_frontend() -> dict[str, Any]:
    node_text = shutil.which("node")
    npm_text = shutil.which("npm")
    if node_text is None or npm_text is None:
        raise ValueError("trusted Node.js/npm runtime is unavailable")
    node_path = Path(node_text).resolve()
    npm_path = Path(npm_text).resolve()
    if ROOT in node_path.parents or ROOT in npm_path.parents:
        raise ValueError("Node.js/npm runtime must not resolve from the candidate tree")
    node_version = subprocess.run(
        [str(node_path), "--version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    npm_version = subprocess.run(
        [str(node_path), str(npm_path), "--version"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not re.fullmatch(r"v22\.\d+\.\d+", node_version):
        raise ValueError(f"artifact audit requires Node.js 22.x: {node_version!r}")
    if not re.fullmatch(r"10\.\d+\.\d+", npm_version):
        raise ValueError(f"artifact audit requires npm 10.x: {npm_version!r}")

    dist = ROOT / "dist"
    if dist.is_symlink():
        raise ValueError("exact-checkout dist path is a symlink")
    if dist.exists():
        shutil.rmtree(dist)
    environment = os.environ.copy()
    environment.update(
        {
            "npm_config_audit": "false",
            "npm_config_fund": "false",
            "npm_config_ignore_scripts": "true",
            "npm_config_offline": "true",
            "VITE_FRONTEND_GLITCHTIP_DSN": "",
        }
    )
    install_command = [
        str(node_path),
        str(npm_path),
        "ci",
        "--offline",
        "--ignore-scripts",
        "--include=dev",
    ]
    install = subprocess.run(
        install_command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if install.returncode != 0:
        raise ValueError("offline npm ci failed for exact-checkout artifact audit")
    vite_entry = ROOT / "node_modules" / "vite" / "bin" / "vite.js"
    if not vite_entry.is_file() or vite_entry.is_symlink():
        raise ValueError("locked Vite entrypoint is absent after offline npm ci")
    build_command = [str(node_path), str(vite_entry), "build"]
    build = subprocess.run(
        build_command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if build.returncode != 0:
        raise ValueError("fresh exact-checkout frontend build failed")
    if not (dist / "index.html").is_file() or dist.is_symlink():
        raise ValueError("fresh exact-checkout frontend build is absent")
    if git("status", "--porcelain"):
        raise ValueError("fresh frontend build changed tracked or untracked source state")
    return {
        "node_version": node_version,
        "node_sha256": sha256_bytes(node_path.read_bytes()),
        "npm_version": npm_version,
        "npm_sha256": sha256_bytes(npm_path.read_bytes()),
        "npm_ci_command": install_command,
        "npm_ci_output_sha256": sha256_bytes(
            (install.stdout + install.stderr).encode("utf-8")
        ),
        "build_command": build_command,
        "build_output_sha256": sha256_bytes(
            (build.stdout + build.stderr).encode("utf-8")
        ),
    }


def verify_artifact_checkout(
    artifact_dir: Path,
    expected_sha: str,
    artifact_phase: str,
    release_a_sha: str | None,
    release_a_artifact_dir: Path | None,
    output_path: Path,
) -> int:
    started = time.monotonic()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("artifact checkout SHA must be exact lowercase 40-char hex")
    if git("rev-parse", "HEAD") != expected_sha:
        raise ValueError("artifact audit checkout HEAD mismatch")
    if git("status", "--porcelain"):
        raise ValueError("artifact audit checkout must be clean including untracked files")
    if not artifact_dir.is_dir() or artifact_dir.is_symlink():
        raise ValueError("artifact directory is absent or unsafe")
    artifact = verify_release_a_artifact(
        artifact_dir,
        expected_sha,
        require_release_a_evidence=artifact_phase == "release-a",
    )
    archive_path = artifact_dir / artifact["archive"]
    frontend_build = build_exact_checkout_frontend()
    current_dist = ROOT / "dist"

    release_b_policy: dict[str, Any] | None = None
    if artifact_phase == "release-b":
        if release_a_sha is None or release_a_artifact_dir is None:
            raise ValueError("Release-B artifact audit requires Release-A SHA/artifact")
        release_a_evidence = release_a_artifact_dir / "schema-gate.json"
        with tempfile.TemporaryDirectory(prefix="retail-a-policy-") as policy_dir:
            policy_evidence = Path(policy_dir) / "release-a-policy.json"
            if verify_main_evidence(
                release_a_evidence,
                release_a_sha,
                expected_sha,
                release_a_artifact_dir,
                policy_evidence,
            ) != 0:
                raise ValueError("Release-B exact-main static policy verification failed")
            release_b_policy = load_json(policy_evidence)
    elif release_a_sha is not None or release_a_artifact_dir is not None:
        raise ValueError("Release-A artifact audit received unexpected Release-B inputs")

    with tempfile.TemporaryDirectory(prefix="retail-artifact-checkout-") as directory:
        work = Path(directory)
        git_source = work / "git-source"
        artifact_source = work / "artifact-source"
        git_source.mkdir()
        artifact_source.mkdir()
        git_archive = subprocess.run(
            ["git", "-C", str(ROOT), "archive", "--format=tar", expected_sha],
            check=True,
            capture_output=True,
        ).stdout
        with tarfile.open(fileobj=io.BytesIO(git_archive), mode="r:") as archive:
            extract_regular_tar(archive, git_source)
        with tarfile.open(archive_path, mode="r:gz") as archive:
            extract_regular_tar(archive, artifact_source)

        git_inventory = tree_inventory(git_source)
        artifact_inventory = tree_inventory(artifact_source, exclude_dist=True)
        if artifact_inventory != git_inventory:
            raise ValueError("signed archive tracked source differs from exact Git tree")
        archived_dist = artifact_source / "dist"
        if not (archived_dist / "index.html").is_file() or archived_dist.is_symlink():
            raise ValueError("signed archive frontend build is absent")
        checkout_dist_inventory = tree_inventory(current_dist)
        artifact_dist_inventory = tree_inventory(archived_dist)
        if artifact_dist_inventory != checkout_dist_inventory:
            raise ValueError("signed archive dist differs from exact-checkout tested build")

    output = {
        "schema_version": 1,
        "result": "PASS",
        "command": [
            "scripts/check_release_a_candidate.py",
            "--verify-artifact-checkout",
            str(artifact_dir),
            "--expected-sha",
            expected_sha,
            "--artifact-phase",
            artifact_phase,
            *(
                [
                    "--release-a-sha",
                    str(release_a_sha),
                    "--release-a-artifact-dir",
                    str(release_a_artifact_dir),
                ]
                if artifact_phase == "release-b"
                else []
            ),
            "--evidence",
            str(output_path),
        ],
        "checkout_sha": expected_sha,
        "checkout_tree": git("rev-parse", "HEAD^{tree}"),
        "artifact_phase": artifact_phase,
        "tracked_file_count": len(git_inventory),
        "tracked_tree_inventory_sha256": sha256_bytes(
            json.dumps(git_inventory, sort_keys=True, separators=(",", ":")).encode()
        ),
        "dist_file_count": len(checkout_dist_inventory),
        "dist_inventory_sha256": sha256_bytes(
            json.dumps(
                checkout_dist_inventory, sort_keys=True, separators=(",", ":")
            ).encode()
        ),
        "artifact": artifact,
        "frontend_build": frontend_build,
        "release_b_static_policy": release_b_policy,
        "duration_seconds": round(time.monotonic() - started, 6),
    }
    write_evidence(output_path, output)
    print(json.dumps({"result": "PASS", "artifact_sha": expected_sha}))
    return 0


def verify_lock(
    *, current_paths: set[str] | None = None
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    lock = load_json(ROOT / ".agent/contract-lock.json")
    if lock.get("revision") != 12 or lock.get("baseline_source_sha") != EXPECTED_BASELINE:
        raise ValueError("Release-A requires exact contract lock revision 12 and baseline")
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
        raise ValueError("revision-12 lock must have exactly one immutable lock commit")
    lock_commit = lock_commits[0]
    lock_parents = git("show", "-s", "--format=%P", lock_commit).split()
    if lock_parents != [content_commit]:
        raise ValueError("revision-12 lock commit must directly follow content commit")
    current_lock_blob = git("rev-parse", "HEAD:.agent/contract-lock.json")
    locked_blob = git("rev-parse", f"{lock_commit}:.agent/contract-lock.json")
    if current_lock_blob != locked_blob:
        raise ValueError("current revision-12 lock differs from its sole lock commit")
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
    expected_evidence_path = (release_a_artifact_dir / "schema-gate.json").resolve()
    if input_path.resolve() != expected_evidence_path:
        raise ValueError("Release-A evidence is not the signed artifact evidence")
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
    checks["signed_evidence_digest"] = (
        release_a_artifact["release_a_evidence"]["files"]["schema-gate.json"]
        == sha256_bytes(input_path.read_bytes())
    )
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
    parser.add_argument("--verify-artifact-checkout", type=Path)
    parser.add_argument("--artifact-phase", choices=("release-a", "release-b"))
    parser.add_argument("--expected-sha")
    parser.add_argument("--release-a-sha")
    parser.add_argument("--expected-candidate-sha")
    parser.add_argument("--release-a-artifact-dir", type=Path)
    args = parser.parse_args()
    evidence_path = args.evidence if args.evidence.is_absolute() else ROOT / args.evidence
    if args.verify_main_evidence is not None and args.verify_artifact_checkout is not None:
        parser.error("artifact-checkout and main-evidence verification are mutually exclusive")
    if args.verify_artifact_checkout is not None:
        if args.expected_sha is None or args.artifact_phase is None:
            parser.error(
                "--expected-sha and --artifact-phase are required with --verify-artifact-checkout"
            )
        artifact_dir = (
            args.verify_artifact_checkout
            if args.verify_artifact_checkout.is_absolute()
            else ROOT / args.verify_artifact_checkout
        )
        try:
            return verify_artifact_checkout(
                artifact_dir,
                args.expected_sha,
                args.artifact_phase,
                args.release_a_sha,
                (
                    args.release_a_artifact_dir
                    if args.release_a_artifact_dir is None
                    or args.release_a_artifact_dir.is_absolute()
                    else ROOT / args.release_a_artifact_dir
                ),
                evidence_path,
            )
        except (
            KeyError,
            OSError,
            subprocess.CalledProcessError,
            tarfile.TarError,
            ValueError,
        ) as exc:
            write_evidence(
                evidence_path,
                {"schema_version": 1, "result": "FAIL", "failures": [str(exc)]},
            )
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
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
    scope_ready = True
    try:
        if git("status", "--porcelain"):
            raise ValueError("worktree must be clean including untracked files")
        lock, locked_objects = verify_lock()
        evidence["contract_revision"] = lock["revision"]
        evidence["contract_content_commit"] = lock["contract_content_commit"]
        evidence["contract_lock_commit"] = lock["verified_lock_commit"]
        evidence["locked_objects"] = locked_objects
        evidence["changed_paths"] = verify_scope()
        evidence["source_transform"] = verify_source_transform()
        evidence["ci_typecheck_step_sha256"] = verify_ci_typecheck()
        evidence["release_a_authority_seed"] = verify_release_a_authority_seed()
    except (KeyError, OSError, subprocess.CalledProcessError, ValueError) as exc:
        scope_ready = False
        failures.append(str(exc))

    mypy_output = ""
    if scope_ready:
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
    else:
        evidence["mypy"] = {"executed": False, "reason": "scope_precondition_failed"}
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
