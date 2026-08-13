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


for _startup_variable in (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONINSPECT",
    "MYPYPATH",
    "MYPY_CONFIG_FILE",
    "NODE_OPTIONS",
    "NODE_PATH",
    "BASH_ENV",
    "ENV",
    "CDPATH",
    "GLOBIGNORE",
):
    os.environ.pop(_startup_variable, None)
os.environ.update({"PYTHONNOUSERSITE": "1", "PYTHONSAFEPATH": "1"})


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BASELINE = "0be82b430e55b7414babf470abe3fc5404b6cdc9"
COSIGN_VERSION = "v3.1.3"
COSIGN_LINUX_AMD64_SHA256 = "4629c757b7618056f8ddd7e2625ae9fdd94c0372a65049520bc7d9df9efc7f71"
NODE_LINUX_X64_SHA256 = "81925c0995b5c1427b5d538e6a90ca2fdc4daffb786b09af749beaf7369d4e90"
NPM_CLI_SHA256 = "8e5f6f3429f8cdbe693cdc29904e9d5a7b127a494bd15c804bd54c7403bfcbe7"
NODE_LINUX_X64_PATH = Path("/opt/codex-desktop/resources/node-runtime/bin/node")
NPM_CLI_PATH = Path(
    "/opt/codex-desktop/resources/node-runtime/lib/node_modules/npm/bin/npm-cli.js"
)
FRONTEND_BUILD_INPUT_ENV = "VITE_FRONTEND_GLITCHTIP_DSN"
PYTHON_BASE_PATH = Path("/usr/bin/python3.12")
PYTHON_BASE_SHA256 = "1643dacd9feaedc58f3cc581e4d22577dfe25c09b10282936186ccf0f2e61118"
PYTHON_SYSTEM_SITECUSTOMIZE_PATH = Path("/usr/lib/python3.12/sitecustomize.py")
PYTHON_SYSTEM_SITECUSTOMIZE_RESOLVED = Path("/etc/python3.12/sitecustomize.py")
PYTHON_SYSTEM_SITECUSTOMIZE_SHA256 = "43d81125d92376b1a69d53a71126a041cc9a18d8080e92dea0a2ae23be138b1e"
PYTHON_SITE_PACKAGES_RELATIVE = "venv/lib/python3.12/site-packages"
PYTHON_SITE_PACKAGES = ROOT / "backend" / PYTHON_SITE_PACKAGES_RELATIVE
PYTHON_SITE_PACKAGES_SHA256 = "81524f503c2b5b2e66bba0ab4cf434e53f79f3fbcd390f6e3aba884acb50848d"
PYTHON_RUNTIME_TREE_PROPERTY = "unihub:python-runtime:site-packages-tree-sha256:v1"
PYTHON_RUNTIME_SUPPLY_NAME = "PYTHON_RUNTIME_SUPPLY.json"
PYTHON_RUNTIME_REQUIREMENTS_NAME = "PYTHON_RUNTIME_REQUIREMENTS.lock"
PYTHON_RUNTIME_WHEELS_NAME = "PYTHON_RUNTIME_WHEELS.tar.gz"
GH_PATH = Path("/usr/bin/gh")
GH_DELL_SHA256 = "2fd925d68889746976958342fb749bf102bc7dc8bcba3abfa533a80ad7791673"
GITHUB_REPOSITORY = "anervalens-netizen/unihub-retail"
TASK_A_BRANCH = "codex/retail-definitive-closure-rev27"
TASK_B_BRANCH = "codex/retail-definitive-closure-b-20260813"
RELEASE_A_PR_NUMBER = 152
RELEASE_A_PREDECESSOR_PR_NUMBER = 151
RELEASE_A_PREDECESSOR_BRANCH = "codex/retail-definitive-closure-20260812"
RELEASE_A_PREDECESSOR_HEAD_SHA = "95154037c78c4bb11e0892327315507e16e603f3"
RELEASE_A_PREDECESSOR_MERGE_SHA = "ad83c7a850f637d475907e80c8e06c62fdfeba66"
EXPECTED_CHANGED_PATHS = {
    ".agent/PLANS.md",
    ".agent/contract-lock.json",
    ".github/workflows/ci.yml",
    ".github/workflows/deploy.yml",
    "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql",
    "backend/db/migrations/README.md",
    "backend/db/migrations/manifest.json",
    "backend/scripts/run_tests_isolated.sh",
    "backend/scripts/outbox_slo_workload_engine.py",
    "backend/scripts/run_outbox_slo_workload.py",
    "backend/scripts/run_import_overlap_gate.py",
    "backend/scripts/run_retail_scale_profile.py",
    "backend/services/grile_pilot_v2.py",
    "backend/services/grile_pilot_v2_sync.py",
    "backend/tests/test_migration_runner_db.py",
    "backend/tests/test_release_a_schema_069.py",
    "backend/tests/test_release_contract_tooling_security.py",
    "docs/contracts/ai-governance-golden-v1.json",
    "docs/contracts/business-golden-v2.json",
    "docs/contracts/query-parameter-policy-v1.json",
    "docs/exec-plans/active/UR-CLOSE-20260812.md",
    "scripts/check_release_a_candidate.py",
    "scripts/complexity-ratchet.json",
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
    "scripts/validate_release_sbom.py",
    "scripts/verify_deployed_release.sh",
    "scripts/verify_promtool_cache.sh",
    "ops/build-retail-release-artifact.sh",
    "ops/config/retail-env.schema.json",
    "ops/deploy-retail-artifact.sh",
    "ops/test-deploy-retail-artifact.sh",
}
EXPECTED_TYPECHECK_STEP = """      - name: Python typecheck
        run: |
          set +e
          venv/bin/python -I -m mypy . --ignore-missing-imports --explicit-package-bases \\
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
    ".github/workflows/deploy.yml",
    "backend/scripts/run_tests_isolated.sh",
    "backend/scripts/outbox_slo_workload_engine.py",
    "backend/scripts/run_outbox_slo_workload.py",
    "backend/scripts/run_import_overlap_gate.py",
    "backend/scripts/run_retail_scale_profile.py",
    "backend/tests/test_release_contract_tooling_security.py",
    "ops/build-retail-release-artifact.sh",
    "ops/config/retail-env.schema.json",
    "ops/deploy-retail-artifact.sh",
    "ops/test-deploy-retail-artifact.sh",
    "scripts/check_release_a_candidate.py",
    "scripts/run_local_quality_gate.sh",
    "scripts/run_outbox_slo_gate.py",
    "scripts/run_real_e2e.sh",
    "scripts/run_release_a_schema_gate.sh",
    "scripts/run_retail_scale_gate.sh",
    "scripts/run_structural_characterization.sh",
    "scripts/structural-characterization-baseline-v1.json",
    "scripts/validate_release_sbom.py",
    "scripts/verify_deployed_release.sh",
    "scripts/verify_frontend_rum_build.mjs",
    "scripts/verify_promtool_cache.sh",
}
EXPECTED_AUTHORITY_PATHS = {
    ".github/workflows/deploy.yml",
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
    "backend/scripts/outbox_slo_workload_engine.py",
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
    "ops/deploy-retail-artifact.sh",
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
    "scripts/validate_release_sbom.py",
    "scripts/verify_deployed_release.sh",
    "scripts/verify_frontend_rum_build.mjs",
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
        "commit": "c8031175abc035671bff04143cdc3eb0cb92303f",
        "ref": "refs/tags/ur-close-20260812-preview-v4-content",
        "tree": "c13556d3f647c1e1052b561af9d36bcfee887ca0",
    },
    "scale_authority": {
        "commit": "e2daba1b45ff12852629889e48f01a9eb3a8a643",
        "ref": "refs/tags/ur-close-20260812-scale-authority-v1",
        "tree": "7cc64e58957e2bb9edb0fddc805d447e055ca22a",
    },
}
PYTHON_CLOSURE_ANCHOR = """      - name: Python complexity ratchet
        working-directory: .
        run: backend/venv/bin/python -I scripts/check_complexity_ratchet.py
"""
PYTHON_CLOSURE_INSERT = """
      - name: Python complexity closure contract
        working-directory: .
        run: |
          backend/venv/bin/python -I scripts/check_python_complexity_contract.py \\
            --contract scripts/python-complexity-contract-v1.json \\
            --evidence test-results/python-complexity-contract.json
"""
FRONTEND_STRUCTURE_ANCHOR = """      - name: TypeScript complexity ratchet
        run: |
          "$RETAIL_NODE" scripts/check_ts_function_complexity.cjs
"""
FRONTEND_STRUCTURE_INSERT = """
      - name: Frontend structure closure contract
        run: |
          "$RETAIL_NODE" scripts/check_frontend_structure_contract.mjs \\
            --manifest scripts/frontend-critical-coverage.json \\
            --evidence test-results/frontend-structure-contract.json
"""
FRONTEND_COVERAGE_ANCHOR = """      - name: Unit tests with global coverage floor
        run: |
          "$RETAIL_NODE" "$RETAIL_NPM_CLI" run test:coverage
"""
FRONTEND_COVERAGE_INSERT = """
      - name: Frontend critical coverage closure contract
        run: |
          "$RETAIL_NODE" scripts/check_frontend_critical_coverage.mjs \\
            --manifest scripts/frontend-critical-coverage.json \\
            --coverage coverage/coverage-final.json \\
            --evidence test-results/frontend-critical-coverage.json
"""
RELEASE_B_REQUIRED_CI_TOKENS = (
    "scripts/verify_promtool_cache.sh prepare",
    "promtool-cache-${{ github.sha }}",
    "Generate exact-main Release-A schema evidence",
    "retail-release-a-schema-${{ github.sha }}",
    "retail-frontend-build-input-${{ github.sha }}",
    "FRONTEND_BUILD_INPUT_SHA256_FILE",
    "release_a_sha",
    "release_a_run_id",
    "Download exact Release-A artifact for Release-B policy proof",
    "Rebuild exact main and audit signed artifact",
    "--frontend-rum-dsn-from-environment",
    "ARTIFACT_AUDIT_RUN_ID",
    "ARTIFACT_AUDIT_RUN_ATTEMPT",
    "ARTIFACT_AUDIT_WORKFLOW_SHA",
    "retail-artifact-audit-${{ github.sha }}",
    "RELEASE_A_EVIDENCE_DIR",
    '--cache-dir "${RUNNER_TOOL_CACHE}/unihub-prometheus"',
    "--sha256 \"$PROMETHEUS_SHA256\"",
    "scripts/check_complexity_ratchet.py",
    "scripts/check_python_complexity_contract.py",
    "scripts/check_frontend_critical_coverage.mjs",
    "scripts/check_frontend_structure_contract.mjs",
    "ops/build-retail-release-artifact.sh \"$GITHUB_SHA\" release-artifact",
    "retail-release-${{ github.sha }}",
)
RELEASE_B_EVIDENCE_CURRENT_PATHS = {
    ".github/workflows/deploy.yml",
    ".agent/PLANS.md",
    "docs/exec-plans/active/UR-CLOSE-20260812.md",
    "scripts/check_release_a_candidate.py",
    "scripts/release-a-source-contract-v1.json",
    "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql",
    "backend/db/migrations/manifest.json",
    "backend/db/migrations/README.md",
    "backend/tests/test_migration_runner_db.py",
    "backend/tests/test_release_a_schema_069.py",
    "backend/tests/test_release_contract_tooling_security.py",
    "backend/scripts/outbox_slo_workload_engine.py",
    "backend/scripts/run_import_overlap_gate.py",
    "scripts/verify_promtool_cache.sh",
    "scripts/release-b-authority-contract-v1.json",
    "ops/build-retail-release-artifact.sh",
    "ops/config/retail-env.schema.json",
    "ops/deploy-retail-artifact.sh",
    "ops/test-deploy-retail-artifact.sh",
}
RELEASE_B_IMMUTABLE_CURRENT_PATHS = {
    ".github/workflows/deploy.yml",
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
    "backend/tests/test_migration_runner_db.py",
    "backend/tests/test_release_a_schema_069.py",
    "backend/tests/test_release_contract_tooling_security.py",
    "backend/scripts/outbox_slo_workload_engine.py",
    "scripts/verify_promtool_cache.sh",
    "scripts/release-b-authority-contract-v1.json",
    "ops/build-retail-release-artifact.sh",
    "ops/config/retail-env.schema.json",
    "ops/deploy-retail-artifact.sh",
    "ops/test-deploy-retail-artifact.sh",
}
RELEASE_B_IMMUTABLE_FROM_A_PATHS = {
    ".agent/contract-lock.json",
    "backend/services/grile_pilot_v2.py",
}
RELEASE_B_MUTABLE_PATHS = {
    "backend/repositories/transactional_outbox.py",
    "backend/services/outbox_worker.py",
    "backend/services/outbox_replay.py",
    "backend/services/grile_outbox_delivery.py",
    "backend/scripts/replay_outbox_event.py",
    "backend/services/sales_generation_flow.py",
    "backend/worker.py",
    "backend/services/sales_artifacts.py",
    "backend/services/promo_generation_publisher.py",
    "backend/services/promo_generation_migration.py",
    "backend/services/promo_generation_migration_hash.py",
    "backend/services/dashboard_specials_config.py",
    "backend/services/jobs.py",
    "backend/services/job_publication.py",
    "backend/services/campaign_reporting_worker.py",
    "backend/services/grile_pilot_v2_runtime.py",
    "backend/services/grile_pilot_v2_sync.py",
    "backend/services/imports.py",
    "backend/architecture_contract.json",
    "APP_ARCHITECTURE.md",
    "README.md",
    "docs/RUNBOOK-campanii-promo-incentive-concursuri.md",
    "docs/operations/retail-slo-readiness.md",
}
RELEASE_B_IMPLEMENTATION_PATHS = {
    "backend/repositories/transactional_outbox.py",
    "backend/services/outbox_worker.py",
    "backend/services/outbox_replay.py",
    "backend/services/grile_outbox_delivery.py",
    "backend/scripts/replay_outbox_event.py",
    "backend/services/sales_generation_flow.py",
    "backend/worker.py",
    "backend/services/sales_artifacts.py",
    "backend/services/promo_generation_publisher.py",
    "backend/services/promo_generation_migration.py",
    "backend/services/promo_generation_migration_hash.py",
    "backend/services/dashboard_specials_config.py",
    "backend/services/jobs.py",
    "backend/services/job_publication.py",
    "backend/services/campaign_reporting_worker.py",
    "backend/services/grile_pilot_v2_runtime.py",
    "backend/services/grile_pilot_v2_sync.py",
    "backend/services/imports.py",
}
RELEASE_B_MUTABLE_TEST_PATHS = {
    "backend/tests/test_campaign_reporting_job_publication.py",
    "backend/tests/test_grile_outbox_delivery.py",
    "backend/tests/test_grile_pilot_v2_sync.py",
    "backend/tests/test_import_service.py",
    "backend/tests/test_imports_coverage.py",
    "backend/tests/test_outbox_worker_faults.py",
    "backend/tests/test_promo_generation_migration.py",
    "backend/tests/test_transactional_outbox.py",
    "backend/tests/test_sales_promotion_worker.py",
    "backend/tests/test_worker_config.py",
}
RELEASE_B_SPECIAL_PATHS = {
    ".github/workflows/ci.yml",
    "scripts/complexity-ratchet.json",
    "scripts/ts-function-complexity-ratchet.json",
}
RELEASE_B_OUTBOX_UNIQUE_PATHS = {
    "backend/tests/test_grile_outbox_delivery.py",
    "backend/tests/test_outbox_replay.py",
    "backend/tests/test_outbox_worker_faults.py",
    "backend/tests/test_transactional_outbox.py",
}
RELEASE_B_SCALE_UNIQUE_PATHS = {
    "backend/scripts/run_retail_scale_profile.py",
    "scripts/run_retail_scale_gate.sh",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def is_canonical_venv_bin_pyc(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and len(path.parts) == 6
        and path.parts[:5] == ("..", "..", "..", "bin", "__pycache__")
        and path.suffix == ".pyc"
    )


def is_canonical_generated_pyc(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and len(path.parts) >= 2
        and path.parts[-2] == "__pycache__"
        and path.suffix == ".pyc"
        and (".." not in path.parts or is_canonical_venv_bin_pyc(value))
    )


def canonical_python_record_bytes(payload: bytes) -> bytes:
    lines: list[str] = []
    for line in payload.decode("utf-8").splitlines():
        fields = line.split(",")
        if len(fields) != 3:
            raise ValueError("Python RECORD row must contain exactly three fields")
        if is_canonical_generated_pyc(fields[0]):
            continue
        if fields[0].startswith("../../../bin/"):
            fields[1:] = ["<venv-script>", "<size>"]
        lines.append(",".join(fields))
    return ("\n".join(lines) + "\n").encode()


def verify_python_runtime() -> dict[str, str]:
    executable = Path(sys.executable)
    if (
        not executable.is_file()
        or executable.resolve() != PYTHON_BASE_PATH
        or not PYTHON_BASE_PATH.is_file()
        or sha256_bytes(PYTHON_BASE_PATH.read_bytes()) != PYTHON_BASE_SHA256
        or not (sys.flags.isolated and sys.flags.no_site)
    ):
        raise ValueError(
            "checker Python must be pinned and started with -I -S"
        )
    return {
        "invoked_path": str(executable),
        "resolved_path": str(PYTHON_BASE_PATH),
        "sha256": PYTHON_BASE_SHA256,
    }


def verify_backend_python_environment() -> dict[str, Any]:
    import base64
    import importlib.metadata

    verified_backend_python()
    site_packages = PYTHON_SITE_PACKAGES
    config_path = ROOT / "backend/venv/pyvenv.cfg"
    lock_path = ROOT / "backend/requirements-dev.lock"
    if (
        not config_path.is_file()
        or config_path.is_symlink()
        or not lock_path.is_file()
        or lock_path.is_symlink()
        or not PYTHON_SYSTEM_SITECUSTOMIZE_PATH.is_file()
        or PYTHON_SYSTEM_SITECUSTOMIZE_PATH.resolve()
        != PYTHON_SYSTEM_SITECUSTOMIZE_RESOLVED
        or sha256_bytes(PYTHON_SYSTEM_SITECUSTOMIZE_PATH.read_bytes())
        != PYTHON_SYSTEM_SITECUSTOMIZE_SHA256
    ):
        raise ValueError("backend Python environment inputs are unsafe")
    config = {
        key.strip().lower(): value.strip().lower()
        for line in config_path.read_text(encoding="utf-8").splitlines()
        if "=" in line
        for key, value in (line.split("=", 1),)
    }
    expected_config = {
        "home": "/usr/bin",
        "include-system-site-packages": "false",
        "version": "3.12.3",
        "executable": "/usr/bin/python3.12",
        "command": (
            "/usr/bin/python3.12 -m venv "
            f"{(ROOT / 'backend/venv').as_posix().lower()}"
        ),
    }
    if config != expected_config:
        raise ValueError("backend pyvenv.cfg identity mismatch")
    canonical = lambda value: re.sub(r"[-_.]+", "-", value).lower()
    expected: dict[str, str] = {}
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^ ;\\]+)", line)
        if match:
            expected[canonical(match.group(1))] = match.group(2)
    distributions = {
        canonical(dist.metadata["Name"]): dist
        for dist in importlib.metadata.distributions(path=[str(site_packages)])
        if dist.metadata.get("Name")
    }
    bootstrap = {"pip", "setuptools", "wheel"}
    versions = {name: dist.version for name, dist in distributions.items()}
    if (
        not expected
        or set(expected) - set(distributions)
        or any(versions.get(name) != version for name, version in expected.items())
        or set(distributions) - set(expected) - bootstrap
    ):
        raise ValueError("backend Python distribution inventory mismatch")
    claimed: set[Path] = set()
    record_failures: list[str] = []
    venv_bin = (ROOT / "backend/venv/bin").resolve()
    for name, dist in sorted(distributions.items()):
        for file in dist.files or ():
            target = Path(str(dist.locate_file(file)))
            try:
                resolved = target.resolve()
                in_site_packages = resolved.is_relative_to(site_packages.resolve())
            except (OSError, ValueError):
                record_failures.append(f"{name}:{file}:unsafe_path")
                continue
            if is_canonical_generated_pyc(str(file)):
                if not in_site_packages and not (
                    is_canonical_venv_bin_pyc(str(file))
                    and resolved.is_relative_to(venv_bin)
                ):
                    record_failures.append(f"{name}:{file}:unsafe_path")
                continue
            if not in_site_packages:
                continue
            claimed.add(resolved)
            if not target.is_file() or target.is_symlink():
                record_failures.append(f"{name}:{file}:missing_or_unsafe")
                continue
            if file.hash is None:
                if Path(str(file)).name != "RECORD" and Path(str(file)).suffix != ".pyc":
                    record_failures.append(f"{name}:{file}:unhashed")
                continue
            if file.hash.mode != "sha256":
                record_failures.append(f"{name}:{file}:unsupported_hash")
                continue
            actual = base64.urlsafe_b64encode(
                hashlib.sha256(target.read_bytes()).digest()
            ).decode().rstrip("=")
            if actual != file.hash.value:
                record_failures.append(f"{name}:{file}:hash_mismatch")
    venv_root = ROOT / "backend/venv"
    pyc = [path for path in venv_root.rglob("*.pyc") if path.is_file()]
    symlinks = [path for path in site_packages.rglob("*") if path.is_symlink()]
    unowned = [
        path
        for path in site_packages.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.suffix != ".pyc"
        and path.resolve() not in claimed
    ]

    def stable_bytes(path: Path) -> bytes:
        payload = path.read_bytes()
        if path.name != "RECORD":
            return payload
        return canonical_python_record_bytes(payload)

    tree_entries = [
        [
            str(path.relative_to(site_packages)),
            hashlib.sha256(stable_bytes(path)).hexdigest(),
        ]
        for path in sorted(site_packages.rglob("*"))
        if path.is_file() and not path.is_symlink() and path.suffix != ".pyc"
    ]
    tree_digest = sha256_bytes(
        json.dumps(tree_entries, separators=(",", ":")).encode()
    )
    if record_failures or pyc or symlinks or unowned or tree_digest != PYTHON_SITE_PACKAGES_SHA256:
        raise ValueError("backend Python RECORD/tree identity mismatch")
    return {
        "lock_sha256": sha256_bytes(lock_path.read_bytes()),
        "distribution_count": len(expected),
        "site_packages_file_count": len(tree_entries),
        "site_packages_sha256": tree_digest,
        "system_sitecustomize_sha256": PYTHON_SYSTEM_SITECUSTOMIZE_SHA256,
    }


def verified_backend_python() -> Path:
    executable = ROOT / "backend/venv/bin/python"
    if (
        not executable.is_file()
        or not os.access(executable, os.X_OK)
        or executable.resolve() != PYTHON_BASE_PATH
        or sha256_bytes(PYTHON_BASE_PATH.read_bytes()) != PYTHON_BASE_SHA256
        or not PYTHON_SITE_PACKAGES.is_dir()
        or PYTHON_SITE_PACKAGES.is_symlink()
    ):
        raise ValueError("backend venv Python is not rooted in the pinned interpreter")
    return PYTHON_BASE_PATH


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


def python_runtime_tree_digest_from_sbom(python_sbom: dict[str, Any]) -> str:
    metadata = python_sbom.get("metadata")
    properties = metadata.get("properties") if isinstance(metadata, dict) else None
    runtime_tree_values = [
        str(item.get("value", ""))
        for item in properties
        if isinstance(item, dict)
        and item.get("name") == PYTHON_RUNTIME_TREE_PROPERTY
    ] if isinstance(properties, list) else []
    if len(runtime_tree_values) != 1 or not re.fullmatch(
        r"[0-9a-f]{64}", runtime_tree_values[0]
    ):
        raise ValueError("signed Python SBOM lacks exact runtime tree identity")
    return runtime_tree_values[0]


def verify_python_runtime_supply(
    artifact_dir: Path,
    checksums: dict[str, str],
    expected_sha: str,
    runtime_tree_sha256: str,
) -> dict[str, Any]:
    supply = load_json(artifact_dir / PYTHON_RUNTIME_SUPPLY_NAME)
    expected_keys = {
        "schemaVersion",
        "python",
        "requirements",
        "sitePackages",
        "sbom",
        "bootstrapDistributions",
        "wheelArchive",
        "wheels",
    }
    if set(supply) != expected_keys or supply.get("schemaVersion") != 1:
        raise ValueError("Python runtime supply schema is not exact")
    if supply.get("python") != {
        "path": str(PYTHON_BASE_PATH),
        "sha256": PYTHON_BASE_SHA256,
        "version": "3.12.3",
    }:
        raise ValueError("Python runtime supply interpreter identity mismatch")
    requirements = supply.get("requirements")
    if requirements != {
        "name": PYTHON_RUNTIME_REQUIREMENTS_NAME,
        "sha256": checksums[PYTHON_RUNTIME_REQUIREMENTS_NAME],
    }:
        raise ValueError("Python runtime supply requirements identity mismatch")
    tracked_requirements = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "show",
            f"{expected_sha}:backend/requirements.lock",
        ],
        check=True,
        capture_output=True,
    ).stdout
    if (artifact_dir / PYTHON_RUNTIME_REQUIREMENTS_NAME).read_bytes() != tracked_requirements:
        raise ValueError("Python runtime supply requirements differ from source SHA")
    if supply.get("sitePackages") != {
        "property": PYTHON_RUNTIME_TREE_PROPERTY,
        "sha256": runtime_tree_sha256,
    }:
        raise ValueError("Python runtime supply tree identity mismatch")
    if supply.get("sbom") != {
        "name": "SBOM.python.cdx.json",
        "sha256": checksums["SBOM.python.cdx.json"],
    }:
        raise ValueError("Python runtime supply SBOM identity mismatch")
    if supply.get("bootstrapDistributions") != {"pip": "24.0"}:
        raise ValueError("Python runtime supply bootstrap inventory mismatch")

    wheel_archive = supply.get("wheelArchive")
    wheels = supply.get("wheels")
    if not isinstance(wheel_archive, dict) or not isinstance(wheels, list):
        raise ValueError("Python runtime wheel inventory is malformed")
    file_count = wheel_archive.get("fileCount")
    total_bytes = wheel_archive.get("totalBytes")
    if (
        set(wheel_archive) != {"name", "sha256", "fileCount", "totalBytes"}
        or wheel_archive.get("name") != PYTHON_RUNTIME_WHEELS_NAME
        or wheel_archive.get("sha256") != checksums[PYTHON_RUNTIME_WHEELS_NAME]
        or not isinstance(file_count, int)
        or isinstance(file_count, bool)
        or not 1 <= file_count <= 512
        or not isinstance(total_bytes, int)
        or isinstance(total_bytes, bool)
        or not 1 <= total_bytes <= 536_870_912
        or len(wheels) != file_count
    ):
        raise ValueError("Python runtime wheel archive identity mismatch")
    expected_wheels: dict[str, tuple[str, int]] = {}
    for item in wheels:
        if (
            not isinstance(item, dict)
            or set(item) != {"name", "sha256", "size"}
            or re.fullmatch(r"[A-Za-z0-9_.+-]+\.whl", str(item.get("name", "")))
            is None
            or re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))) is None
            or not isinstance(item.get("size"), int)
            or isinstance(item.get("size"), bool)
            or item["size"] <= 0
            or item["name"] in expected_wheels
        ):
            raise ValueError("Python runtime wheel entry is invalid")
        expected_wheels[item["name"]] = (item["sha256"], item["size"])
    if [item["name"] for item in wheels] != sorted(expected_wheels):
        raise ValueError("Python runtime wheel inventory is not canonical")
    if sum(size for _digest, size in expected_wheels.values()) != total_bytes:
        raise ValueError("Python runtime wheel byte total mismatch")

    observed_wheels: dict[str, tuple[str, int]] = {}
    with tarfile.open(artifact_dir / PYTHON_RUNTIME_WHEELS_NAME, mode="r:gz") as archive:
        for member in archive.getmembers():
            normalized = PurePosixPath(member.name.removeprefix("./"))
            if not normalized.parts:
                continue
            if member.isdir() and normalized.as_posix() == ".":
                continue
            if (
                not member.isfile()
                or len(normalized.parts) != 1
                or normalized.name not in expected_wheels
                or normalized.name in observed_wheels
            ):
                raise ValueError("Python runtime wheel archive member is unsafe")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("Python runtime wheel archive member is unreadable")
            payload = stream.read(expected_wheels[normalized.name][1] + 1)
            observed_wheels[normalized.name] = (sha256_bytes(payload), len(payload))
    if observed_wheels != expected_wheels:
        raise ValueError("Python runtime wheel archive content mismatch")
    return {
        "requirements_sha256": checksums[PYTHON_RUNTIME_REQUIREMENTS_NAME],
        "runtime_tree_sha256": runtime_tree_sha256,
        "wheel_archive_sha256": checksums[PYTHON_RUNTIME_WHEELS_NAME],
        "wheel_file_count": file_count,
        "wheel_total_bytes": total_bytes,
    }


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


def git_diff_paths(before: str, after: str) -> set[str]:
    output = git("diff", "--no-renames", "--name-only", before, after)
    return set(filter(None, output.splitlines()))


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
        # Freeze the whole pytest tree, not only top-level test_*.py files.
        # This is deliberately a superset of pytest's recursive
        # test_*.py/*_test.py discovery and also binds conftest/helpers/data.
        return {path for path in tracked if path.startswith("backend/tests/")}
    if name == "frontend_test_suite":
        return {
            path
            for path in tracked
            if path.startswith("src/")
            and (path.endswith(".test.ts") or path.endswith(".test.tsx"))
        }
    if name == "e2e_test_suite":
        # Playwright discovers multiple JS/TS extensions recursively. Binding
        # the complete e2e tree also freezes helpers and future fixture files.
        return {path for path in tracked if path.startswith("e2e/")}
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


def verify_release_b_runtime_composition(
    expected_release_a_sha: str, immutable_current: set[str]
) -> dict[str, Any]:
    preview_sha = EXPECTED_SOURCE_SNAPSHOTS["release_b_integrated_preview"]["commit"]
    outbox_sha = EXPECTED_SOURCE_SNAPSHOTS["outbox_acceptance_contract"]["commit"]
    scale_sha = EXPECTED_SOURCE_SNAPSHOTS["scale_authority"]["commit"]
    preview_delta = git_diff_paths(EXPECTED_BASELINE, preview_sha)
    outbox_unique = git_diff_paths(EXPECTED_BASELINE, outbox_sha) - preview_delta
    scale_unique = git_diff_paths(EXPECTED_BASELINE, scale_sha) - preview_delta
    if len(preview_delta) != 308:
        raise ValueError("Release-B preview topology drift")
    if outbox_unique != RELEASE_B_OUTBOX_UNIQUE_PATHS:
        raise ValueError("Release-B outbox snapshot topology drift")
    if scale_unique != RELEASE_B_SCALE_UNIQUE_PATHS:
        raise ValueError("Release-B scale snapshot topology drift")

    preview_exclusions = (
        immutable_current
        | RELEASE_B_IMMUTABLE_FROM_A_PATHS
        | RELEASE_B_SPECIAL_PATHS
        | RELEASE_B_MUTABLE_PATHS
        | RELEASE_B_MUTABLE_TEST_PATHS
    )
    frozen_preview_paths = preview_delta - preview_exclusions
    if len(frozen_preview_paths) != 272:
        raise ValueError("Release-B frozen preview topology drift")
    frozen_preview: list[dict[str, str]] = []
    for path in sorted(frozen_preview_paths):
        expected_mode, expected_digest = git_path_identity(preview_sha, path)
        actual_mode, actual_digest = git_path_identity("HEAD", path)
        if (
            expected_mode not in {"100644", "100755"}
            or (actual_mode, actual_digest) != (expected_mode, expected_digest)
        ):
            raise ValueError(f"Release-B frozen preview runtime drift: {path}")
        frozen_preview.append(
            {"path": path, "git_mode": expected_mode, "sha256": expected_digest}
        )

    actual_delta = git_diff_paths(expected_release_a_sha, "HEAD")
    allowed_delta = (
        preview_delta
        | RELEASE_B_OUTBOX_UNIQUE_PATHS
        | RELEASE_B_SCALE_UNIQUE_PATHS
        | RELEASE_B_MUTABLE_PATHS
        | RELEASE_B_MUTABLE_TEST_PATHS
        | RELEASE_B_SPECIAL_PATHS
    )
    unexpected_delta = sorted(actual_delta - allowed_delta)
    if unexpected_delta:
        raise ValueError(f"Release-B unexpected path mutation: {unexpected_delta}")
    missing_mutable = sorted(RELEASE_B_MUTABLE_PATHS - actual_delta)
    if missing_mutable:
        raise ValueError(f"Release-B required implementation path is unchanged: {missing_mutable}")
    for path in sorted(RELEASE_B_MUTABLE_PATHS):
        actual_mode, actual_digest = git_path_identity("HEAD", path)
        preview_mode, preview_digest = git_path_identity(preview_sha, path)
        if actual_mode != "100644" or not actual_digest:
            raise ValueError(f"Release-B mutable path is missing or unsafe: {path}")
        if (
            path in RELEASE_B_IMPLEMENTATION_PATHS
            and (actual_mode, actual_digest) == (preview_mode, preview_digest)
        ):
            raise ValueError(f"Release-B mutable path did not change from preview: {path}")
    missing_mutable_tests = sorted(RELEASE_B_MUTABLE_TEST_PATHS - actual_delta)
    if missing_mutable_tests:
        raise ValueError(
            f"Release-B required authority test is unchanged: {missing_mutable_tests}"
        )
    for path in sorted(RELEASE_B_MUTABLE_TEST_PATHS):
        actual_mode, actual_digest = git_path_identity("HEAD", path)
        preview_mode, preview_digest = git_path_identity(preview_sha, path)
        if actual_mode != "100644" or not actual_digest:
            raise ValueError(f"Release-B mutable test is missing or unsafe: {path}")
        if (actual_mode, actual_digest) == (preview_mode, preview_digest):
            raise ValueError(f"Release-B mutable test did not change from preview: {path}")

    release_a_immutable: list[dict[str, str]] = []
    for path in sorted(RELEASE_B_IMMUTABLE_FROM_A_PATHS):
        expected_mode, expected_digest = git_path_identity(expected_release_a_sha, path)
        actual_mode, actual_digest = git_path_identity("HEAD", path)
        if (
            expected_mode != "100644"
            or not expected_digest
            or (actual_mode, actual_digest) != (expected_mode, expected_digest)
        ):
            raise ValueError(f"Release-B changed immutable Release-A path: {path}")
        release_a_immutable.append(
            {"path": path, "git_mode": expected_mode, "sha256": expected_digest}
        )
    release_a_lock_digest = next(
        item["sha256"]
        for item in release_a_immutable
        if item["path"] == ".agent/contract-lock.json"
    )
    return {
        "preview_delta_count": len(preview_delta),
        "frozen_preview_count": len(frozen_preview),
        "frozen_preview": frozen_preview,
        "outbox_unique_paths": sorted(outbox_unique),
        "scale_unique_paths": sorted(scale_unique),
        "mutable_paths": sorted(RELEASE_B_MUTABLE_PATHS),
        "mutable_test_paths": sorted(RELEASE_B_MUTABLE_TEST_PATHS),
        "candidate_delta_paths": sorted(actual_delta),
        "unexpected_delta_paths": unexpected_delta,
        "release_a_immutable": release_a_immutable,
        "release_a_lock_sha256": release_a_lock_digest,
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

    for path in RELEASE_B_IMMUTABLE_CURRENT_PATHS:
        expected_digest = locked_by_path.get(path, {}).get("sha256")
        if expected_digest is None or sha256_bytes((ROOT / path).read_bytes()) != expected_digest:
            raise ValueError(f"Release-B immutable contract drift: {path}")

    runtime_composition = verify_release_b_runtime_composition(
        expected_release_a_sha, RELEASE_B_IMMUTABLE_CURRENT_PATHS
    )

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
    missing_ci = [token for token in RELEASE_B_REQUIRED_CI_TOKENS if token not in workflow]
    if missing_ci:
        raise ValueError(f"Release-B CI lost required semantics: {missing_ci}")
    if "prometheus/releases/download" in workflow or "curl " in workflow[workflow.index("Operational configuration validation"):workflow.index("Exact-SHA deploy and rollback sandbox")]:
        raise ValueError("Release-B operational CI retains an unbounded direct download")
    return {
        "candidate_sha": expected_candidate_sha,
        "candidate_tree": git("rev-parse", "HEAD^{tree}"),
        "release_a_is_ancestor": True,
        "immutable_paths": sorted(RELEASE_B_IMMUTABLE_CURRENT_PATHS),
        "runtime_composition": runtime_composition,
        "ratchets": ratchet_evidence,
        "ci_sha256": sha256_bytes(workflow.encode("utf-8")),
        "ci_exact_three_gate_transform": True,
        "ci_required_tokens": list(RELEASE_B_REQUIRED_CI_TOKENS),
        "ci_direct_mypy": True,
        "ci_direct_prometheus_download": False,
        "authorities": verify_release_b_authorities(),
    }


def verify_release_a_artifact(
    artifact_dir: Path,
    expected_sha: str,
    *,
    require_release_a_evidence: bool = True,
    expected_frontend_build_input_sha256: str | None = None,
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
        PYTHON_RUNTIME_SUPPLY_NAME,
        PYTHON_RUNTIME_REQUIREMENTS_NAME,
        PYTHON_RUNTIME_WHEELS_NAME,
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
    frontend_build_input = manifest.get("frontendBuildInput")
    if (
        not isinstance(frontend_build_input, dict)
        or frontend_build_input.get("name") != FRONTEND_BUILD_INPUT_ENV
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(frontend_build_input.get("sha256", ""))
        )
        or (
            expected_frontend_build_input_sha256 is not None
            and frontend_build_input.get("sha256")
            != expected_frontend_build_input_sha256
        )
    ):
        raise ValueError("Release artifact frontend build-input identity mismatch")
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
    python_sbom = load_json(artifact_dir / "SBOM.python.cdx.json")
    python_runtime_tree_sha256 = python_runtime_tree_digest_from_sbom(python_sbom)
    python_runtime_supply = verify_python_runtime_supply(
        artifact_dir,
        checksums,
        expected_sha,
        python_runtime_tree_sha256,
    )
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
    run_details = predicate.get("runDetails") if isinstance(predicate, dict) else None
    external = build_definition.get("externalParameters") if isinstance(build_definition, dict) else None
    resolved = build_definition.get("resolvedDependencies") if isinstance(build_definition, dict) else None
    if not isinstance(external, dict) or external.get("sourceSha") != expected_sha:
        raise ValueError("Release-A provenance external source SHA mismatch")
    if external.get("releaseAEvidence") != release_a_evidence:
        raise ValueError("Release-A provenance evidence binding mismatch")
    if external.get("frontendBuildInput") != frontend_build_input:
        raise ValueError("Release artifact provenance frontend build-input mismatch")
    if not isinstance(resolved, list) or not any(
        isinstance(item, dict) and item.get("digest", {}).get("gitCommit") == expected_sha
        for item in resolved
    ):
        raise ValueError("Release-A provenance resolved dependency mismatch")
    builder_id = (
        run_details.get("builder", {}).get("id")
        if isinstance(run_details, dict)
        else None
    )
    invocation_id = (
        run_details.get("metadata", {}).get("invocationId")
        if isinstance(run_details, dict)
        else None
    )
    expected_builder_id = (
        "github-actions://anervalens-netizen/unihub-retail/"
        f".github/workflows/ci.yml@{expected_sha}"
    )
    if builder_id != expected_builder_id or not isinstance(
        invocation_id, str
    ) or not invocation_id:
        raise ValueError("Release-A provenance run identity is absent")
    if require_release_a_evidence:
        if not isinstance(release_a_evidence, dict):
            raise ValueError("Release-A signed evidence is absent")
        release_a_run_id = str(release_a_evidence["workflowRunId"])
        if not re.fullmatch(
            rf"https://github\.com/{re.escape(GITHUB_REPOSITORY)}/actions/runs/"
            rf"{re.escape(release_a_run_id)}/attempts/[1-9][0-9]*",
            invocation_id,
        ):
            raise ValueError(
                "Release-A signed evidence run differs from artifact provenance"
            )
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
        "--certificate-github-workflow-sha",
        expected_sha,
        "--certificate-github-workflow-repository",
        GITHUB_REPOSITORY,
        "--certificate-github-workflow-ref",
        "refs/heads/main",
        "--certificate-github-workflow-trigger",
        "workflow_dispatch",
        "--certificate-github-workflow-name",
        "CI",
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
        "frontend_build_input": frontend_build_input,
        "python_runtime_tree_sha256": python_runtime_tree_sha256,
        "python_runtime_supply": python_runtime_supply,
        "builder_id": builder_id,
        "invocation_id": invocation_id,
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


def build_exact_checkout_frontend(rum_dsn: str) -> dict[str, Any]:
    node_path = NODE_LINUX_X64_PATH.resolve()
    npm_path = NPM_CLI_PATH.resolve()
    if not node_path.is_file() or not npm_path.is_file():
        raise ValueError("trusted Node.js/npm runtime is unavailable")
    if ROOT in node_path.parents or ROOT in npm_path.parents:
        raise ValueError("Node.js/npm runtime must not resolve from the candidate tree")
    if (
        sha256_bytes(node_path.read_bytes()) != NODE_LINUX_X64_SHA256
        or sha256_bytes(npm_path.read_bytes()) != NPM_CLI_SHA256
    ):
        raise ValueError("artifact audit Node.js/npm executable digest mismatch")
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
    for key in ("NODE_OPTIONS", "NODE_PATH"):
        environment.pop(key, None)
    environment.update(
        {
            "npm_config_audit": "false",
            "npm_config_fund": "false",
            "npm_config_ignore_scripts": "true",
            "npm_config_offline": "true",
            FRONTEND_BUILD_INPUT_ENV: rum_dsn,
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
        "frontend_build_input_sha256": sha256_bytes(rum_dsn.encode("utf-8")),
    }


def verify_artifact_checkout(
    artifact_dir: Path,
    expected_sha: str,
    artifact_phase: str,
    release_a_sha: str | None,
    release_a_artifact_dir: Path | None,
    rum_dsn: str,
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
    rum_dsn_sha256 = sha256_bytes(rum_dsn.encode("utf-8"))
    workflow_run_id = os.environ.get("ARTIFACT_AUDIT_RUN_ID", "")
    workflow_run_attempt = os.environ.get("ARTIFACT_AUDIT_RUN_ATTEMPT", "")
    workflow_sha = os.environ.get("ARTIFACT_AUDIT_WORKFLOW_SHA", "")
    if (
        not re.fullmatch(r"[1-9][0-9]*", workflow_run_id)
        or not re.fullmatch(r"[1-9][0-9]*", workflow_run_attempt)
        or workflow_sha != expected_sha
    ):
        raise ValueError("exact GitHub workflow run identity is required for artifact audit")
    artifact = verify_release_a_artifact(
        artifact_dir,
        expected_sha,
        require_release_a_evidence=artifact_phase == "release-a",
        expected_frontend_build_input_sha256=rum_dsn_sha256,
    )
    expected_invocation_id = (
        "https://github.com/anervalens-netizen/unihub-retail/actions/runs/"
        f"{workflow_run_id}/attempts/{workflow_run_attempt}"
    )
    if artifact["invocation_id"] != expected_invocation_id:
        raise ValueError("artifact provenance does not match the audit workflow run")
    archive_path = artifact_dir / artifact["archive"]
    frontend_build = build_exact_checkout_frontend(rum_dsn)
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
            "--frontend-rum-dsn-from-environment",
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
        "workflow_run": {
            "repository": "anervalens-netizen/unihub-retail",
            "run_id": workflow_run_id,
            "run_attempt": workflow_run_attempt,
            "workflow_sha": workflow_sha,
        },
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


def verify_signed_artifact_audit(
    audit_dir: Path,
    artifact_dir: Path,
    expected_sha: str,
    artifact_phase: str,
    expected_workflow_run_id: str,
    output_path: Path,
) -> int:
    started = time.monotonic()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("signed artifact-audit SHA is invalid")
    if not audit_dir.is_dir() or audit_dir.is_symlink():
        raise ValueError("signed artifact-audit directory is absent or unsafe")
    names = {item.name for item in audit_dir.iterdir()}
    if names != {"artifact-checkout.json", "artifact-checkout.sigstore.json"}:
        raise ValueError("signed artifact-audit inventory mismatch")
    audit_path = audit_dir / "artifact-checkout.json"
    bundle_path = audit_dir / "artifact-checkout.sigstore.json"
    if any(not path.is_file() or path.is_symlink() for path in (audit_path, bundle_path)):
        raise ValueError("signed artifact-audit files are absent or unsafe")

    cosign_text = shutil.which("cosign")
    if cosign_text is None:
        raise ValueError("trusted cosign is unavailable")
    cosign_path = Path(cosign_text).resolve()
    if (
        not cosign_path.is_file()
        or sha256_bytes(cosign_path.read_bytes()) != COSIGN_LINUX_AMD64_SHA256
    ):
        raise ValueError("cosign binary digest mismatch")
    signature_command = [
        str(cosign_path),
        "verify-blob",
        str(audit_path),
        "--bundle",
        str(bundle_path),
        "--certificate-identity",
        "https://github.com/anervalens-netizen/unihub-retail/.github/workflows/ci.yml@refs/heads/main",
        "--certificate-oidc-issuer",
        "https://token.actions.githubusercontent.com",
        "--certificate-github-workflow-sha",
        expected_sha,
        "--certificate-github-workflow-repository",
        GITHUB_REPOSITORY,
        "--certificate-github-workflow-ref",
        "refs/heads/main",
        "--certificate-github-workflow-trigger",
        "workflow_dispatch",
        "--certificate-github-workflow-name",
        "CI",
    ]
    signature = subprocess.run(
        signature_command, capture_output=True, text=True, check=False
    )
    if signature.returncode != 0:
        raise ValueError("signed artifact-audit Sigstore verification failed")

    audit = load_json(audit_path)
    artifact = verify_release_a_artifact(
        artifact_dir,
        expected_sha,
        require_release_a_evidence=artifact_phase == "release-a",
    )
    expected_tree = git("rev-parse", f"{expected_sha}^{{tree}}")
    frontend_build = audit.get("frontend_build")
    audit_artifact = audit.get("artifact")
    release_b_policy = audit.get("release_b_static_policy")
    workflow_run = audit.get("workflow_run")
    run_attempt = (
        str(workflow_run.get("run_attempt", ""))
        if isinstance(workflow_run, dict)
        else ""
    )
    expected_invocation_id = (
        "https://github.com/anervalens-netizen/unihub-retail/actions/runs/"
        f"{expected_workflow_run_id}/attempts/{run_attempt}"
    )
    if (
        audit.get("schema_version") != 1
        or audit.get("result") != "PASS"
        or audit.get("checkout_sha") != expected_sha
        or audit.get("checkout_tree") != expected_tree
        or audit.get("artifact_phase") != artifact_phase
        or not re.fullmatch(r"[1-9][0-9]*", expected_workflow_run_id)
        or not isinstance(workflow_run, dict)
        or workflow_run
        != {
            "repository": "anervalens-netizen/unihub-retail",
            "run_id": expected_workflow_run_id,
            "run_attempt": run_attempt,
            "workflow_sha": expected_sha,
        }
        or not re.fullmatch(r"[1-9][0-9]*", run_attempt)
        or artifact["invocation_id"] != expected_invocation_id
        or not isinstance(frontend_build, dict)
        or frontend_build.get("frontend_build_input_sha256")
        != artifact["frontend_build_input"]["sha256"]
        or not isinstance(audit_artifact, dict)
        or audit_artifact.get("archive_sha256") != artifact["archive_sha256"]
        or audit_artifact.get("release_manifest_sha256")
        != artifact["release_manifest_sha256"]
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(audit.get("tracked_tree_inventory_sha256", ""))
        )
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(audit.get("dist_inventory_sha256", ""))
        )
        or int(audit.get("tracked_file_count", 0)) <= 0
        or int(audit.get("dist_file_count", 0)) <= 0
        or (
            artifact_phase == "release-b"
            and (
                not isinstance(release_b_policy, dict)
                or release_b_policy.get("result") != "PASS"
                or release_b_policy.get("expected_release_b_sha") != expected_sha
            )
        )
        or (artifact_phase == "release-a" and release_b_policy is not None)
    ):
        raise ValueError("signed artifact-audit content binding mismatch")

    output = {
        "schema_version": 1,
        "result": "PASS",
        "expected_sha": expected_sha,
        "expected_tree": expected_tree,
        "artifact_phase": artifact_phase,
        "workflow_run_id": expected_workflow_run_id,
        "workflow_run_attempt": run_attempt,
        "artifact_archive_sha256": artifact["archive_sha256"],
        "artifact_audit_sha256": sha256_bytes(audit_path.read_bytes()),
        "artifact_audit_bundle_sha256": sha256_bytes(bundle_path.read_bytes()),
        "frontend_build_input_sha256": artifact["frontend_build_input"]["sha256"],
        "sigstore_command": signature_command,
        "sigstore_output_sha256": sha256_bytes(
            (signature.stdout + signature.stderr).encode("utf-8")
        ),
        "duration_seconds": round(time.monotonic() - started, 6),
    }
    write_evidence(output_path, output)
    print(json.dumps({"result": "PASS", "artifact_audit_sha": expected_sha}))
    return 0


def verify_release_a_merge_topology(
    release_a_pr_sha: str, release_a_sha: str
) -> dict[str, Any]:
    predecessor_parents = git(
        "show", "-s", "--format=%P", RELEASE_A_PREDECESSOR_MERGE_SHA
    ).split()
    release_a_parents = git("show", "-s", "--format=%P", release_a_sha).split()
    if predecessor_parents != [EXPECTED_BASELINE, RELEASE_A_PREDECESSOR_HEAD_SHA]:
        raise ValueError("Release-A predecessor merge topology mismatch")
    if release_a_parents != [RELEASE_A_PREDECESSOR_MERGE_SHA, release_a_pr_sha]:
        raise ValueError("final Release-A merge topology mismatch")
    return {
        "predecessor_pr": RELEASE_A_PREDECESSOR_PR_NUMBER,
        "predecessor_branch": RELEASE_A_PREDECESSOR_BRANCH,
        "predecessor_head_sha": RELEASE_A_PREDECESSOR_HEAD_SHA,
        "predecessor_merge_sha": RELEASE_A_PREDECESSOR_MERGE_SHA,
        "predecessor_parents": predecessor_parents,
        "release_a_parents": release_a_parents,
    }


def verify_github_release_runs(
    *,
    release_a_pr: int,
    release_b_pr: int,
    release_a_pr_sha: str,
    release_b_pr_sha: str,
    release_a_sha: str,
    release_b_sha: str,
    release_a_pr_run_id: str,
    release_b_pr_run_id: str,
    release_a_run_id: str,
    release_b_run_id: str,
    output_path: Path,
) -> int:
    started = time.monotonic()
    sha_values = (
        release_a_pr_sha,
        release_b_pr_sha,
        release_a_sha,
        release_b_sha,
    )
    run_ids = (
        release_a_pr_run_id,
        release_b_pr_run_id,
        release_a_run_id,
        release_b_run_id,
    )
    if (
        release_a_pr != RELEASE_A_PR_NUMBER
        or release_b_pr <= 0
        or release_b_pr == release_a_pr
        or any(not re.fullmatch(r"[0-9a-f]{40}", value) for value in sha_values)
        or any(not re.fullmatch(r"[1-9][0-9]*", value) for value in run_ids)
        or release_a_sha == release_b_sha
    ):
        raise ValueError("GitHub release-run identities are invalid")
    if git("rev-parse", "HEAD") != release_b_sha or git("status", "--porcelain"):
        raise ValueError("GitHub evidence must be verified from clean exact MAIN_B_SHA")
    release_a_topology = verify_release_a_merge_topology(
        release_a_pr_sha, release_a_sha
    )
    if subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "merge-base",
            "--is-ancestor",
            release_a_sha,
            release_b_sha,
        ],
        check=False,
    ).returncode:
        raise ValueError("MAIN_A_SHA is not an ancestor of MAIN_B_SHA")
    if (
        not GH_PATH.is_file()
        or sha256_bytes(GH_PATH.read_bytes()) != GH_DELL_SHA256
    ):
        raise ValueError("GitHub CLI is not the pinned Dell binary")
    gh_version = subprocess.run(
        [str(GH_PATH), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if gh_version.returncode or not gh_version.stdout.startswith("gh version 2.45.0 "):
        raise ValueError("GitHub CLI version mismatch")

    raw_hashes: dict[str, str] = {}

    def api(label: str, endpoint: str) -> dict[str, Any]:
        environment = os.environ.copy()
        environment.pop("GH_HOST", None)
        environment.update(
            {"GH_PAGER": "cat", "NO_COLOR": "1", "GH_PROMPT_DISABLED": "1"}
        )
        result = subprocess.run(
            [
                str(GH_PATH),
                "api",
                "--hostname",
                "github.com",
                "--method",
                "GET",
                endpoint,
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise ValueError(f"GitHub API query failed: {label}")
        raw_hashes[label] = sha256_bytes(result.stdout.encode("utf-8"))
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise ValueError(f"GitHub API response is invalid: {label}")
        return value

    run_specs = {
        "release_a_pr": (
            release_a_pr_run_id,
            release_a_pr_sha,
            "pull_request",
            TASK_A_BRANCH,
            release_a_pr,
        ),
        "release_a_main": (
            release_a_run_id,
            release_a_sha,
            "workflow_dispatch",
            "main",
            None,
        ),
        "release_b_pr": (
            release_b_pr_run_id,
            release_b_pr_sha,
            "pull_request",
            TASK_B_BRANCH,
            release_b_pr,
        ),
        "release_b_main": (
            release_b_run_id,
            release_b_sha,
            "workflow_dispatch",
            "main",
            None,
        ),
    }
    run_evidence: dict[str, dict[str, Any]] = {}
    repository_api_url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}"
    for label, (run_id, sha, event, branch, expected_pr) in run_specs.items():
        value = api(label, f"repos/{GITHUB_REPOSITORY}/actions/runs/{run_id}")
        repository = value.get("repository")
        head_repository = value.get("head_repository")
        associated_pulls = value.get("pull_requests")
        if (
            value.get("id") != int(run_id)
            or value.get("head_sha") != sha
            or value.get("head_branch") != branch
            or value.get("event") != event
            or value.get("status") != "completed"
            or value.get("conclusion") != "success"
            or value.get("path") != ".github/workflows/ci.yml"
            or not isinstance(value.get("run_attempt"), int)
            or value["run_attempt"] < 1
            or not isinstance(repository, dict)
            or repository.get("full_name") != GITHUB_REPOSITORY
            or not isinstance(head_repository, dict)
            or head_repository.get("full_name") != GITHUB_REPOSITORY
        ):
            raise ValueError(f"GitHub workflow run identity mismatch: {label}")
        if expected_pr is not None:
            if not isinstance(associated_pulls, list) or len(associated_pulls) != 1:
                raise ValueError(
                    f"GitHub workflow run PR association mismatch: {label}"
                )
            associated_pull = associated_pulls[0]
            if not isinstance(associated_pull, dict):
                raise ValueError(
                    f"GitHub workflow run PR association mismatch: {label}"
                )
            associated_head = associated_pull.get("head", {})
            associated_base = associated_pull.get("base", {})
            associated_head_repo = (
                associated_head.get("repo", {})
                if isinstance(associated_head, dict)
                else {}
            )
            associated_base_repo = (
                associated_base.get("repo", {})
                if isinstance(associated_base, dict)
                else {}
            )
            if (
                associated_pull.get("number") != expected_pr
                or associated_pull.get("url")
                != f"{repository_api_url}/pulls/{expected_pr}"
                or not isinstance(associated_head, dict)
                or associated_head.get("sha") != sha
                or associated_head.get("ref") != branch
                or not isinstance(associated_head_repo, dict)
                or associated_head_repo.get("url") != repository_api_url
                or not isinstance(associated_base, dict)
                or associated_base.get("ref") != "main"
                or not isinstance(associated_base_repo, dict)
                or associated_base_repo.get("url") != repository_api_url
            ):
                raise ValueError(
                    f"GitHub workflow run PR association mismatch: {label}"
                )
        run_evidence[label] = {
            "run_id": int(run_id),
            "run_attempt": value["run_attempt"],
            "head_sha": sha,
            "head_branch": branch,
            "event": event,
            "status": "completed",
            "conclusion": "success",
            "html_url": value.get("html_url"),
            "pull_request_number": expected_pr,
        }

    pull_specs = {
        "release_a_predecessor": (
            RELEASE_A_PREDECESSOR_PR_NUMBER,
            RELEASE_A_PREDECESSOR_BRANCH,
            RELEASE_A_PREDECESSOR_HEAD_SHA,
            RELEASE_A_PREDECESSOR_MERGE_SHA,
        ),
        "release_a": (release_a_pr, TASK_A_BRANCH, release_a_pr_sha, release_a_sha),
        "release_b": (release_b_pr, TASK_B_BRANCH, release_b_pr_sha, release_b_sha),
    }
    pull_evidence: dict[str, dict[str, Any]] = {}
    for label, (number, branch, head_sha, merge_sha) in pull_specs.items():
        value = api(label, f"repos/{GITHUB_REPOSITORY}/pulls/{number}")
        head = value.get("head")
        base = value.get("base")
        if (
            value.get("number") != number
            or value.get("state") != "closed"
            or value.get("draft") is not False
            or not value.get("merged_at")
            or value.get("merge_commit_sha") != merge_sha
            or not isinstance(head, dict)
            or head.get("ref") != branch
            or head.get("sha") != head_sha
            or not isinstance(base, dict)
            or base.get("ref") != "main"
        ):
            raise ValueError(f"GitHub pull-request identity mismatch: {label}")
        pull_evidence[label] = {
            "number": number,
            "head_ref": branch,
            "head_sha": head_sha,
            "merge_sha": merge_sha,
            "state": "MERGED",
            "html_url": value.get("html_url"),
        }

    remote_main = api("remote_main", f"repos/{GITHUB_REPOSITORY}/git/ref/heads/main")
    remote_object = remote_main.get("object")
    if (
        remote_main.get("ref") != "refs/heads/main"
        or not isinstance(remote_object, dict)
        or remote_object.get("type") != "commit"
        or remote_object.get("sha") != release_b_sha
    ):
        raise ValueError("live GitHub refs/heads/main differs from MAIN_B_SHA")

    output = {
        "schema_version": 1,
        "result": "PASS",
        "repository": GITHUB_REPOSITORY,
        "python_runtime": verify_python_runtime(),
        "gh": {
            "path": str(GH_PATH),
            "sha256": GH_DELL_SHA256,
            "version": gh_version.stdout.splitlines()[0],
        },
        "release_a_sha": release_a_sha,
        "release_b_sha": release_b_sha,
        "release_a_topology": release_a_topology,
        "remote_main": release_b_sha,
        "pull_requests": pull_evidence,
        "workflow_runs": run_evidence,
        "raw_response_sha256": raw_hashes,
        "duration_seconds": round(time.monotonic() - started, 6),
    }
    write_evidence(output_path, output)
    print(json.dumps({"result": "PASS", "github_main_sha": release_b_sha}))
    return 0


def verify_lock(
    *, current_paths: set[str] | None = None
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    lock = load_json(ROOT / ".agent/contract-lock.json")
    if lock.get("revision") != 28 or lock.get("baseline_source_sha") != EXPECTED_BASELINE:
        raise ValueError("Release-A requires exact contract lock revision 28 and baseline")
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
        raise ValueError("revision-28 lock must have exactly one immutable lock commit")
    lock_commit = lock_commits[0]
    lock_parents = git("show", "-s", "--format=%P", lock_commit).split()
    if lock_parents != [content_commit]:
        raise ValueError("revision-28 lock commit must directly follow content commit")
    current_lock_blob = git("rev-parse", "HEAD:.agent/contract-lock.json")
    locked_blob = git("rev-parse", f"{lock_commit}:.agent/contract-lock.json")
    if current_lock_blob != locked_blob:
        raise ValueError("current revision-28 lock differs from its sole lock commit")
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


def verify_source_transform() -> dict[str, Any]:
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
    whitespace_path = "backend/services/grile_pilot_v2_sync.py"
    preview_commit = EXPECTED_SOURCE_SNAPSHOTS["release_b_integrated_preview"][
        "commit"
    ]
    whitespace_baseline_payload = subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f"{EXPECTED_BASELINE}:{whitespace_path}"]
    )
    whitespace_preview_payload = subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f"{preview_commit}:{whitespace_path}"]
    )
    whitespace_current_payload = (ROOT / whitespace_path).read_bytes()
    if whitespace_current_payload != whitespace_preview_payload:
        raise ValueError("Grile sync whitespace normalization differs from preview")
    baseline_mode, _baseline_digest = git_path_identity(
        EXPECTED_BASELINE, whitespace_path
    )
    preview_mode, _preview_digest = git_path_identity(
        preview_commit, whitespace_path
    )
    index_fields = git("ls-files", "-s", "--", whitespace_path).split()
    result_mode = index_fields[0] if len(index_fields) >= 4 else ""
    if (baseline_mode, preview_mode, result_mode) != ("100644",) * 3:
        raise ValueError("Grile sync whitespace normalization mode mismatch")
    baseline_lines = whitespace_baseline_payload.splitlines(keepends=True)
    current_lines = whitespace_current_payload.splitlines(keepends=True)
    if [line for line in baseline_lines if line.strip()] != [
        line for line in current_lines if line.strip()
    ]:
        raise ValueError("Grile sync normalization changed nonblank source")
    deleted_blank_lines = len(baseline_lines) - len(current_lines)
    if deleted_blank_lines != 5:
        raise ValueError("Grile sync normalization must delete exactly five blank lines")
    whitespace_checks = {
        "path": whitespace_path,
        "baseline_git_mode": baseline_mode,
        "baseline_git_blob": git(
            "rev-parse", f"{EXPECTED_BASELINE}:{whitespace_path}"
        ),
        "baseline_sha256": sha256_bytes(whitespace_baseline_payload),
        "preview_git_mode": preview_mode,
        "result_git_mode": result_mode,
        "result_git_blob": git("hash-object", whitespace_path),
        "result_sha256": sha256_bytes(whitespace_current_payload),
        "deleted_blank_lines": deleted_blank_lines,
        "runtime_effect": "none",
    }
    expected_whitespace_checks = {
        "path": whitespace_path,
        "baseline_git_mode": "100644",
        "baseline_git_blob": "27c05c7388cd134aebeae9b98efeb86f4831c77f",
        "baseline_sha256": "ac31c6551e61c1cc8e59731488dfe44b2468f37b00bc5a88933f6fd88aaa1f60",
        "preview_git_mode": "100644",
        "result_git_mode": "100644",
        "result_git_blob": "00a8f3ab186f2e600d5d810640c85a796a65a359",
        "result_sha256": "0e2aad80ca331ca5b713f9ab3adb42b72b7c08ed3aab971d94b7033b11319c46",
        "deleted_blank_lines": 5,
        "runtime_effect": "none",
    }
    if whitespace_checks != expected_whitespace_checks:
        raise ValueError("Grile sync whitespace normalization identity mismatch")
    return {
        "path": path,
        **checks,
        "whitespace_normalization": whitespace_checks,
    }


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
    python = verified_backend_python()
    site_packages = PYTHON_SITE_PACKAGES_RELATIVE
    command = [
        "/usr/bin/python3.12",
        "-B",
        "-I",
        "-S",
        "-c",
        (
            "import runpy,sys; "
            f"sys.path.insert(0,{site_packages!r}); "
            "sys.argv=['mypy',*sys.argv[1:]]; "
            "runpy.run_module('mypy',run_name='__main__')"
        ),
        ".",
        "--ignore-missing-imports",
        "--explicit-package-bases",
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
        }
    )
    for key in ("MYPYPATH", "MYPY_CONFIG_FILE"):
        environment.pop(key, None)
    result = subprocess.run(
        [str(python), *command[1:]],
        cwd=ROOT / "backend",
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return command, result


def expected_direct_mypy_command() -> list[str]:
    site_packages = PYTHON_SITE_PACKAGES_RELATIVE
    return [
        "cd",
        "backend",
        "&&",
        str(PYTHON_BASE_PATH),
        "-B",
        "-I",
        "-S",
        "-c",
        (
            "import runpy,sys; "
            f"sys.path.insert(0,{site_packages!r}); "
            "sys.argv=['mypy',*sys.argv[1:]]; "
            "runpy.run_module('mypy',run_name='__main__')"
        ),
        ".",
        "--ignore-missing-imports",
        "--explicit-package-bases",
    ]


def release_a_evidence_logical_path(release_a_sha: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", release_a_sha):
        raise ValueError("Release-A SHA must be exact lowercase 40-char hex")
    return f"test-results/closure/{release_a_sha}/release-a/schema-gate.json"


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
            release_a_evidence_logical_path(expected_sha),
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
    identity_dicts = [entry for entry in identity_entries if isinstance(entry, dict)]
    checks["database_identities"] = (
        len(identity_entries) == 3
        and len(identity_dicts) == 3
        and len({entry.get("database_name") for entry in identity_dicts}) == 3
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
        python_environment = candidate.get("python_environment")
        python_environment_post_mypy = candidate.get(
            "python_environment_post_mypy"
        )
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
            and isinstance(python_environment, dict)
            and python_environment_post_mypy == python_environment
        )
        candidate_locked_objects = candidate.get("locked_objects")
        checks["candidate_locked_objects"] = (
            isinstance(candidate_locked_objects, list)
            and len(candidate_locked_objects) == len(locked_by_path)
            and {
                (item.get("path"), item.get("git_blob"), item.get("sha256"))
                for item in candidate_locked_objects
                if isinstance(item, dict)
            }
            == {
                (item["path"], item["git_blob"], item["sha256"])
                for item in locked_by_path.values()
            }
        )
        source_transform = candidate.get("source_transform")
        locked_source = locked_by_path["scripts/release-a-source-contract-v1.json"]
        whitespace_normalization = (
            source_transform.get("whitespace_normalization")
            if isinstance(source_transform, dict)
            else None
        )
        checks["candidate_source_transform"] = (
            isinstance(source_transform, dict)
            and source_transform.get("path") == "backend/services/grile_pilot_v2.py"
            and source_transform.get("baseline_git_blob") == "299a6130c8226f2f6de7c239ccfb59bbfb8cae8c"
            and source_transform.get("baseline_sha256")
            == "e781187478527d41a607d90081e786ed7816cdf89b57fe39aca2872c1d1010b6"
            and source_transform.get("result_git_blob") == "9cc93035b4a39144faa503cd94144f3e57f7ff8f"
            and source_transform.get("result_sha256") == "b63686dc43a1541dc1d4aebdbd52bf6efb5c545d231aacf2d8e5a85b25922f6a"
            and whitespace_normalization
            == {
                "path": "backend/services/grile_pilot_v2_sync.py",
                "baseline_git_mode": "100644",
                "baseline_git_blob": "27c05c7388cd134aebeae9b98efeb86f4831c77f",
                "baseline_sha256": "ac31c6551e61c1cc8e59731488dfe44b2468f37b00bc5a88933f6fd88aaa1f60",
                "preview_git_mode": "100644",
                "result_git_mode": "100644",
                "result_git_blob": "00a8f3ab186f2e600d5d810640c85a796a65a359",
                "result_sha256": "0e2aad80ca331ca5b713f9ab3adb42b72b7c08ed3aab971d94b7033b11319c46",
                "deleted_blank_lines": 5,
                "runtime_effect": "none",
            }
            and locked_source.get("sha256")
            == "feb14f72f7a637733c75b79649113d7973615185466f7a9399e43541d1d2e4ed"
        )
        checks["candidate_mypy_command"] = (
            isinstance(mypy, dict)
            and mypy.get("command") == expected_direct_mypy_command()
        )
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
    parser.add_argument("--verify-signed-artifact-audit", type=Path)
    parser.add_argument("--verify-github-release-runs", action="store_true")
    parser.add_argument("--verify-python-environment", action="store_true")
    parser.add_argument("--artifact-phase", choices=("release-a", "release-b"))
    parser.add_argument("--expected-sha")
    parser.add_argument("--release-a-sha")
    parser.add_argument("--expected-candidate-sha")
    parser.add_argument("--release-a-artifact-dir", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--frontend-rum-dsn-from-environment", action="store_true")
    parser.add_argument("--expected-workflow-run-id")
    parser.add_argument("--release-a-pr", type=int)
    parser.add_argument("--release-b-pr", type=int)
    parser.add_argument("--release-a-pr-sha")
    parser.add_argument("--release-b-pr-sha")
    parser.add_argument("--release-a-pr-run-id")
    parser.add_argument("--release-b-pr-run-id")
    parser.add_argument("--release-a-run-id")
    parser.add_argument("--release-b-run-id")
    args = parser.parse_args()
    evidence_path = args.evidence if args.evidence.is_absolute() else ROOT / args.evidence
    selected_modes = sum(
        bool(value)
        for value in (
            args.verify_main_evidence,
            args.verify_artifact_checkout,
            args.verify_signed_artifact_audit,
            args.verify_github_release_runs,
            args.verify_python_environment,
        )
    )
    if selected_modes > 1:
        parser.error("artifact/main evidence verification modes are mutually exclusive")
    try:
        python_runtime = verify_python_runtime()
    except (OSError, ValueError) as exc:
        write_evidence(
            evidence_path,
            {"schema_version": 1, "result": "FAIL", "failures": [str(exc)]},
        )
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if args.verify_python_environment:
        try:
            environment = verify_backend_python_environment()
            write_evidence(
                evidence_path,
                {
                    "schema_version": 1,
                    "result": "PASS",
                    "python_runtime": python_runtime,
                    "python_environment": environment,
                },
            )
            print(json.dumps({"result": "PASS", **environment}, sort_keys=True))
            return 0
        except (OSError, ValueError) as exc:
            write_evidence(
                evidence_path,
                {"schema_version": 1, "result": "FAIL", "failures": [str(exc)]},
            )
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
    if args.verify_github_release_runs:
        required = (
            args.release_a_pr,
            args.release_b_pr,
            args.release_a_pr_sha,
            args.release_b_pr_sha,
            args.release_a_sha,
            args.expected_sha,
            args.release_a_pr_run_id,
            args.release_b_pr_run_id,
            args.release_a_run_id,
            args.release_b_run_id,
        )
        if any(value is None for value in required):
            parser.error(
                "all Release-A/B PR, SHA and workflow-run identities are required with --verify-github-release-runs"
            )
        try:
            return verify_github_release_runs(
                release_a_pr=int(args.release_a_pr),
                release_b_pr=int(args.release_b_pr),
                release_a_pr_sha=str(args.release_a_pr_sha),
                release_b_pr_sha=str(args.release_b_pr_sha),
                release_a_sha=str(args.release_a_sha),
                release_b_sha=str(args.expected_sha),
                release_a_pr_run_id=str(args.release_a_pr_run_id),
                release_b_pr_run_id=str(args.release_b_pr_run_id),
                release_a_run_id=str(args.release_a_run_id),
                release_b_run_id=str(args.release_b_run_id),
                output_path=evidence_path,
            )
        except (
            KeyError,
            OSError,
            subprocess.CalledProcessError,
            ValueError,
        ) as exc:
            write_evidence(
                evidence_path,
                {"schema_version": 1, "result": "FAIL", "failures": [str(exc)]},
            )
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
    if args.verify_signed_artifact_audit is not None:
        if (
            args.expected_sha is None
            or args.artifact_phase is None
            or args.artifact_dir is None
            or args.expected_workflow_run_id is None
        ):
            parser.error(
                "--expected-sha, --artifact-phase, --artifact-dir and --expected-workflow-run-id are required with --verify-signed-artifact-audit"
            )
        audit_dir = (
            args.verify_signed_artifact_audit
            if args.verify_signed_artifact_audit.is_absolute()
            else ROOT / args.verify_signed_artifact_audit
        )
        artifact_dir = (
            args.artifact_dir
            if args.artifact_dir.is_absolute()
            else ROOT / args.artifact_dir
        )
        try:
            return verify_signed_artifact_audit(
                audit_dir,
                artifact_dir,
                args.expected_sha,
                args.artifact_phase,
                args.expected_workflow_run_id,
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
    if args.verify_artifact_checkout is not None:
        if (
            args.expected_sha is None
            or args.artifact_phase is None
            or not args.frontend_rum_dsn_from_environment
        ):
            parser.error(
                "--expected-sha, --artifact-phase and --frontend-rum-dsn-from-environment are required with --verify-artifact-checkout"
            )
        rum_dsn = os.environ.get(FRONTEND_BUILD_INPUT_ENV, "")
        if not rum_dsn or "\n" in rum_dsn or "\r" in rum_dsn:
            parser.error("exact non-empty frontend RUM build input is required")
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
                rum_dsn,
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
        "python_runtime": python_runtime,
    }
    failures: list[str] = []
    scope_ready = True
    try:
        if git("status", "--porcelain"):
            raise ValueError("worktree must be clean including untracked files")
        evidence["python_environment"] = verify_backend_python_environment()
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
        _command, mypy = run_direct_mypy()
        mypy_output = mypy.stdout + mypy.stderr
        evidence["mypy"] = {
            "command": expected_direct_mypy_command(),
            "exit_code": mypy.returncode,
            "output_sha256": sha256_bytes(mypy_output.encode("utf-8")),
            "success_marker": "Success: no issues found" in mypy_output,
            "shadow_or_substitution": False,
        }
        if mypy.returncode != 0 or "Success: no issues found" not in mypy_output:
            failures.append("direct unshadowed full mypy failed")
        try:
            post_mypy_environment = verify_backend_python_environment()
            evidence["python_environment_post_mypy"] = post_mypy_environment
            if post_mypy_environment != evidence["python_environment"]:
                failures.append("direct mypy changed the verified Python environment")
        except (KeyError, OSError, subprocess.CalledProcessError, ValueError) as exc:
            failures.append(f"post-mypy Python environment verification failed: {exc}")
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
