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
    assert 'git("status", "--porcelain")' in checker
    assert "--untracked-files=no" not in checker
    assert "status --porcelain" in schema_gate
    assert "PYTHONNOUSERSITE=1" in schema_gate
    assert "PYTHONSAFEPATH=1" in schema_gate
    assert "unset MYPYPATH MYPY_CONFIG_FILE" in schema_gate


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
    assert len(real_contract["authorities"]) == len(checker.EXPECTED_AUTHORITY_PATHS) == 45
    monkeypatch.setattr(checker, "EXPECTED_RELEASE_A_AUTHORITIES", set())
    monkeypatch.setattr(checker, "EXPECTED_AUTHORITY_PATHS", {"authority.py"})
    authority = tmp_path / "authority.py"
    authority.write_text("print('real gate')\n", encoding="utf-8")
    digest = hashlib.sha256(authority.read_bytes()).hexdigest()
    contract = {
        "schema_version": 1,
        "baseline_source_sha": checker.EXPECTED_BASELINE,
        "acceptance_criteria": sorted(checker.EXPECTED_AUTHORITY_CRITERIA),
        "release_a_authorities": [],
        "required_paths": ["authority.py"],
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
        lambda *args, **_kwargs: "100644 blob authority.py"
        if args[:3] == ("ls-tree", "HEAD", "--")
        else "",
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
