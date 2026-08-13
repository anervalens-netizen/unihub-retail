from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = ROOT / "scripts/check_release_a_candidate.py"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_candidate_checker", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_a_tooling_requires_clean_untracked_scope() -> None:
    checker = CHECKER_PATH.read_text(encoding="utf-8")
    schema_gate = (ROOT / "scripts/run_release_a_schema_gate.sh").read_text(
        encoding="utf-8"
    )
    structural_gate = (ROOT / "scripts/run_structural_characterization.sh").read_text(
        encoding="utf-8"
    )
    scale_gate = (ROOT / "scripts/run_retail_scale_gate.sh").read_text(
        encoding="utf-8"
    )
    local_gate = (ROOT / "scripts/run_local_quality_gate.sh").read_text(
        encoding="utf-8"
    )
    assert 'git("status", "--porcelain")' in checker
    assert "--untracked-files=no" not in checker
    assert "status --porcelain" in schema_gate
    assert "PYTHONNOUSERSITE=1" in schema_gate
    assert "PYTHONSAFEPATH=1" in schema_gate
    assert "unset MYPYPATH MYPY_CONFIG_FILE" in schema_gate
    for source in (schema_gate, structural_gate, scale_gate):
        assert "postgres@sha256:" in source
        assert "--pull=never" in source
        assert 'PYTHON_BASE="/usr/bin/python3.12"' in source
        assert "PYTHON_BASE_SHA256=" in source
    assert "valkey/valkey@sha256:" in schema_gate
    assert "UNIHUB_SCALE_PYTHON" not in scale_gate
    assert "UNIHUB_BACKEND_VENV" not in structural_gate
    assert "EXPECTED_NODE_SHA256" in local_gate
    assert "EXPECTED_NPM_CLI_SHA256" in local_gate
    assert 'PATH="$(dirname "$NODE"):' in local_gate
    assert "    export PATH" in local_gate


def test_release_a_checker_never_runs_mypy_after_scope_failure() -> None:
    checker = CHECKER_PATH.read_text(encoding="utf-8")
    assert "if scope_ready:\n        command, mypy = run_direct_mypy()" in checker
    assert '"reason": "scope_precondition_failed"' in checker


def test_release_a_gate_requires_fresh_canonical_evidence_and_authority_seed() -> None:
    checker = CHECKER_PATH.read_text(encoding="utf-8")
    schema_gate = (ROOT / "scripts/run_release_a_schema_gate.sh").read_text(
        encoding="utf-8"
    )
    assert "verify_release_a_authority_seed()" in checker
    assert "EXPECTED_RELEASE_A_AUTHORITIES" in checker
    assert 'EXPECTED_EVIDENCE_PATH="$ROOT_DIR/test-results/closure/$CURRENT_SHA/release-a/schema-gate.json"' in schema_gate
    assert "Release-A evidence path must be new" in schema_gate
    assert "realpath -m" in schema_gate


def test_promtool_cache_never_trusts_a_system_binary(tmp_path: Path) -> None:
    script = ROOT / "scripts/verify_promtool_cache.sh"
    source = script.read_text(encoding="utf-8")
    assert "command -v promtool" not in source
    assert 'source="system"' not in source
    evidence = tmp_path / "promtool.json"
    subprocess.run(
        [str(script), "self-test", "--evidence", str(evidence)],
        cwd=ROOT,
        check=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["result"] == "PASS"
    assert payload["cold_download_count"] == 1
    assert payload["warm_download_count"] == 0
    assert len(payload["archive_sha256"]) == 64
    assert len(payload["promtool_sha256"]) == 64


def test_release_b_workflow_is_only_the_three_frozen_insertions() -> None:
    checker = _load_checker()
    baseline = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    candidate = checker.expected_release_b_workflow(baseline)
    inserted_names = (
        "Python complexity closure contract",
        "Frontend structure closure contract",
        "Frontend critical coverage closure contract",
    )
    for name in inserted_names:
        assert name not in baseline
        assert candidate.count(name) == 1
    assert candidate.count(checker.EXPECTED_TYPECHECK_STEP) == 1
    assert candidate != checker.expected_release_b_workflow(candidate)


def test_release_b_authorities_reject_digest_or_mode_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checker = _load_checker()
    real_contract = json.loads(
        (ROOT / "scripts/release-b-authority-contract-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert real_contract["required_paths"] == sorted(checker.EXPECTED_AUTHORITY_PATHS)
    assert len(real_contract["authorities"]) == len(checker.EXPECTED_AUTHORITY_PATHS) == 106
    monkeypatch.setattr(checker, "EXPECTED_RELEASE_A_AUTHORITIES", set())
    monkeypatch.setattr(checker, "EXPECTED_AUTHORITY_PATHS", {"authority.py"})
    monkeypatch.setattr(checker, "EXPECTED_AUTHORITY_SET_NAMES", set())
    monkeypatch.setattr(checker, "EXPECTED_SOURCE_SNAPSHOTS", {})
    authority = tmp_path / "authority.py"
    authority.write_text("print('real gate')\n", encoding="utf-8")
    digest = hashlib.sha256(authority.read_bytes()).hexdigest()
    contract = {
        "schema_version": 2,
        "baseline_source_sha": checker.EXPECTED_BASELINE,
        "acceptance_criteria": sorted(checker.EXPECTED_AUTHORITY_CRITERIA),
        "release_a_authorities": [],
        "required_paths": ["authority.py"],
        "authority_sets": [],
        "source_snapshots": {},
        "authorities": [
            {
                "path": "authority.py",
                "sha256": digest,
                "git_mode": "100644",
                "supports": sorted(checker.EXPECTED_AUTHORITY_CRITERIA),
            }
        ],
    }
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/release-b-authority-contract-v1.json").write_text(
        json.dumps(contract), encoding="utf-8"
    )
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(
        checker,
        "git",
        lambda *args, **_kwargs: (
            "100644 blob authority.py"
            if args[:3] == ("ls-tree", "HEAD", "--")
            else ""
        ),
    )
    assert checker.verify_release_b_authorities()["authority_count"] == 1
    authority.write_text("print('no-op')\n", encoding="utf-8")
    with pytest.raises(ValueError, match="authority drift"):
        checker.verify_release_b_authorities()


def test_artifact_contract_binds_main_evidence_and_pinned_cosign() -> None:
    checker = CHECKER_PATH.read_text(encoding="utf-8")
    builder = (ROOT / "ops/build-retail-release-artifact.sh").read_text(
        encoding="utf-8"
    )
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for name in (
        "schema-gate.json",
        "release-a-candidate.json",
        "release-a-schema-empty.xml",
        "release-a-schema-restored.xml",
    ):
        assert name in checker
        assert name in builder
    assert "RELEASE_A_EVIDENCE_RUN_ID" in builder
    assert 'manifest["releaseAEvidence"]' in builder
    assert 'external.get("releaseAEvidence")' in checker
    assert "COSIGN_BIN" not in checker
    assert "COSIGN_LINUX_AMD64_SHA256" in checker
    assert "shutil.which(\"cosign\")" in checker
    assert "Generate exact-main Release-A schema evidence" in workflow
    assert "retail-release-a-schema-${{ github.sha }}" in workflow
    assert 'manifest["frontendBuildInput"]' not in builder
    assert '"frontendBuildInput": {' in builder
    assert "FRONTEND_BUILD_INPUT_SHA256_FILE" in builder
    assert "expected_frontend_build_input_sha256" in checker
    assert "retail-frontend-build-input-${{ github.sha }}" in workflow
    assert "VITE_FRONTEND_GLITCHTIP_DSN: ${{ secrets.VITE_GLITCHTIP_DSN }}" in workflow


def test_artifact_audit_runs_from_exact_checkout_and_compares_source_and_dist() -> None:
    checker = CHECKER_PATH.read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    plan = (ROOT / "docs/exec-plans/active/UR-CLOSE-20260812.md").read_text(
        encoding="utf-8"
    )
    assert "--verify-artifact-checkout" in checker
    assert "def build_exact_checkout_frontend(rum_dsn: str)" in checker
    assert '"npm_config_offline": "true"' in checker
    assert '"ci",\n        "--offline",\n        "--ignore-scripts"' in checker
    assert 'r"v22\\.\\d+\\.\\d+"' in checker
    assert "signed archive tracked source differs from exact Git tree" in checker
    assert "signed archive dist differs from exact-checkout tested build" in checker
    assert "--verify-signed-artifact-audit" in checker
    assert "artifact-checkout.sigstore.json" in checker
    assert "frontend_build_input_sha256" in checker
    assert "Rebuild exact main and audit signed artifact" in workflow
    assert "retail-artifact-audit-${{ github.sha }}" in workflow
    assert "--frontend-rum-dsn-from-environment" in workflow
    assert "ARTIFACT_AUDIT_RUN_ID: ${{ github.run_id }}" in workflow
    assert "ARTIFACT_AUDIT_RUN_ATTEMPT: ${{ github.run_attempt }}" in workflow
    assert "ARTIFACT_AUDIT_WORKFLOW_SHA: ${{ github.workflow_sha }}" in workflow
    assert "--expected-workflow-run-id" in checker
    assert "artifact provenance does not match the audit workflow run" in checker
    assert "clean detached" in plan and "exact-SHA Git checkout" in plan
    assert "unpacked artifact `git rev-parse HEAD`" not in plan


def test_release_b_authorities_bind_transitive_runners_and_durable_snapshots() -> None:
    checker = _load_checker()
    contract = json.loads(
        (ROOT / "scripts/release-b-authority-contract-v1.json").read_text(
            encoding="utf-8"
        )
    )
    for path in (
        "package.json",
        "backend/scripts/run_tests_isolated.sh",
        "playwright.browser-smoke.config.ts",
        "playwright.pwa-workbox.config.ts",
        "playwright.real.config.ts",
        "scripts/run_pwa_release_lifecycle.sh",
        "scripts/run_real_e2e.sh",
        "vitest.config.ts",
    ):
        assert path in checker.EXPECTED_AUTHORITY_PATHS
        assert path in contract["required_paths"]
    snapshots = contract["source_snapshots"]
    assert snapshots == checker.EXPECTED_SOURCE_SNAPSHOTS
    assert all(
        value["ref"].startswith("refs/tags/ur-close-20260812-")
        for value in snapshots.values()
    )
    verified = checker.verify_source_snapshots(
        require_ancestors=False, verify_remote=True
    )
    assert all(value["remote_ref_verified"] for value in verified.values())


def test_ac17_freezes_complete_invocation_and_three_way_ref_reconciliation() -> None:
    verifier = (ROOT / "scripts/verify_deployed_release.sh").read_text(
        encoding="utf-8"
    )
    plan = (ROOT / "docs/exec-plans/active/UR-CLOSE-20260812.md").read_text(
        encoding="utf-8"
    )
    for token in (
        "--main-a-sha",
        "--main-b-sha",
        "--release-a-artifact-dir",
        "--release-b-artifact-dir",
        "--release-a-evidence",
        "--release-b-archive-sha256",
        "--backup-handle",
        "--probe-month",
        "--manager-cookie-file",
        "--forbidden-cookie-file",
        "--release-a-pr",
        "--release-b-pr",
    ):
        assert token in verifier
        assert token in plan
    assert "refs-primary.json" in verifier
    assert "refs-dell.json" in verifier
    assert "refs-github.json" in verifier
    assert "codex/retail-definitive-closure-20260812" in verifier
    assert "ls-remote origin refs/heads/main" in verifier
    assert 'remote_lines != [f"{b}\\trefs/heads/main"]' in verifier
    assert "probe_authenticated_browser" in verifier
    assert '"browser.json"' in verifier
    assert "BROWSER_CHROME_SHA256" in verifier
    for marker in (
        "Sales Hub",
        "Grile V2 · pilot",
        "Calculator Target",
        "Statistici Salarii",
        "Import fișier vânzări",
        "Builder export Excel",
        "mobile-dashboard",
    ):
        assert marker in verifier
