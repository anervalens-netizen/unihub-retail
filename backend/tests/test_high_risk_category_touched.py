"""Durable tests for scripts/is_high_risk_category_touched.py.

These tests run the production classifier directly against synthetic git
histories so the 15-case proof cannot disappear after merge.

The classifier's contract:
    0   = TOUCHED
    10  = NOT_TOUCHED
    20  = ERROR
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import textwrap

import pytest

CLASSIFIER = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "scripts"
    / "is_high_risk_category_touched.py"
)


def _python_isolated():
    return "/usr/bin/python3.12"


def _run(args, cwd, check=True):
    cp = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    return cp


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a minimal git repo with the production manifest and a clean base."""
    repo = tmp_path / "repo"
    repo.mkdir()
    cp = _run(["git", "init", "--quiet", "--initial-branch=main"], repo)
    assert cp.returncode == 0, cp.stderr
    cp = _run(["git", "config", "user.name", "Test"], repo)
    cp = _run(["git", "config", "user.email", "test@example.invalid"], repo)
    # Copy the real production manifest from the repo.
    src = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / ".github"
        / "governance"
        / "high-risk-paths.json"
    )
    (repo / ".github" / "governance").mkdir(parents=True)
    shutil.copy(src, repo / ".github" / "governance" / "high-risk-paths.json")
    cp = _run(["git", "add", "."], repo)
    cp = _run(["git", "commit", "--quiet", "-m", "base"], repo)
    assert cp.returncode == 0, cp.stderr
    yield repo


def _classifier(repo, base_sha=None, category="deploy-release-ci"):
    base = base_sha or _run(["git", "rev-parse", "HEAD~"], repo).stdout.strip()
    cp = _run(
        [
            _python_isolated(),
            "-I",
            str(CLASSIFIER),
            "--category",
            category,
            "--base-sha",
            base,
            "--repo-root",
            str(repo),
        ],
        repo,
    )
    return cp


def _commit(repo, files_map, msg="change"):
    for path, content in files_map.items():
        p = repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    cp = _run(["git", "add", "."], repo)
    assert cp.returncode == 0
    cp = _run(["git", "commit", "--quiet", "-m", msg], repo)
    assert cp.returncode == 0, cp.stderr


# ---------------------------------------------------------------------------
# Positive TOUCHED cases (exit 0) - manifest category paths
# ---------------------------------------------------------------------------


def test_workflow_path_touched(tmp_repo):
    _commit(tmp_repo, {".github/workflows/ci.yml": "# changed"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0, f"stdout={cp.stdout!r} stderr={cp.stderr!r}"
    assert cp.returncode == 0


def test_deploy_script_touched(tmp_repo):
    _commit(tmp_repo, {"ops/deploy-retail-artifact.sh": "# changed"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0


def test_build_script_touched(tmp_repo):
    _commit(tmp_repo, {"ops/build-retail-release-artifact.sh": "# changed"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0


def test_provisioning_script_touched(tmp_repo):
    _commit(tmp_repo, {"ops/provision-retail-service-identities.sh": "# changed"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0


def test_caddy_path_touched(tmp_repo):
    _commit(tmp_repo, {"ops/caddy/retail.caddy": "# changed"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0


def test_systemd_path_touched(tmp_repo):
    _commit(tmp_repo, {"ops/systemd/unihub-backend.service": "[Unit]"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0


def test_governance_path_touched(tmp_repo):
    _commit(tmp_repo, {".github/governance/high-risk-paths.json": "{}"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0


# ---------------------------------------------------------------------------
# Positive TOUCHED cases (exit 0) - sandbox direct-input supplement
# ---------------------------------------------------------------------------


def test_supplement_package_json(tmp_repo):
    _commit(tmp_repo, {"package.json": "{}"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0


def test_supplement_package_lock_json(tmp_repo):
    _commit(tmp_repo, {"package-lock.json": "{}"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0


def test_supplement_unihub_worker_service(tmp_repo):
    _commit(tmp_repo, {"unihub-worker.service": "[Unit]"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0


def test_supplement_retail_slo_rules(tmp_repo):
    _commit(tmp_repo, {"ops/observability/retail-slo-rules.yml": "# changed"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0


def test_supplement_retail_process_scrape(tmp_repo):
    _commit(tmp_repo, {"ops/observability/retail-process-scrape.yml": "# changed"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0


def test_supplement_backend_requirements_lock(tmp_repo):
    _commit(tmp_repo, {"backend/requirements.lock": "# changed"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0


def test_supplement_validate_release_sbom(tmp_repo):
    _commit(tmp_repo, {"scripts/validate_release_sbom.py": "# changed"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0


# ---------------------------------------------------------------------------
# NOT_TOUCHED (exit 10) - ordinary backend / docs changes
# ---------------------------------------------------------------------------


def test_backend_only_not_touched(tmp_repo):
    _commit(tmp_repo, {"backend/main.py": "# changed"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 10


def test_docs_only_not_touched(tmp_repo):
    _commit(tmp_repo, {"docs/engineering/pr-fast-lane.md": "# changed"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 10


def test_random_src_file_not_touched(tmp_repo):
    _commit(tmp_repo, {"src/features/foo/Foo.tsx": "// changed"})
    cp = _classifier(tmp_repo)
    assert cp.returncode == 10


# ---------------------------------------------------------------------------
# Governed rename to non-governed path - --no-renames exposes old path
# ---------------------------------------------------------------------------


def test_rename_away_from_governed_path_still_touched(tmp_repo):
    # Create a governed file at base
    _commit(tmp_repo, {".github/workflows/ci.yml": "original"}, msg="add ci.yml")
    # Now rename it in a new commit
    (tmp_repo / "somethingelse").mkdir(exist_ok=True)
    cp = _run(
        ["git", "mv", ".github/workflows/ci.yml", "somethingelse/ci.yml"], tmp_repo
    )
    assert cp.returncode == 0
    cp = _run(["git", "commit", "--quiet", "-m", "rename away"], tmp_repo)
    assert cp.returncode == 0
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0, (
        f"--no-renames must expose the old path; got rc={cp.returncode} "
        f"stdout={cp.stdout!r} stderr={cp.stderr!r}"
    )


# ---------------------------------------------------------------------------
# BASE-manifest trust test - PR removes a path from HEAD manifest but BASE
# still has it. Classifier must use BASE, so it still returns TOUCHED.
# ---------------------------------------------------------------------------


def test_head_manifest_weakening_does_not_skip(tmp_repo):
    # 1) Make a backend-only change (would normally be NOT_TOUCHED)
    _commit(tmp_repo, {"backend/main.py": "# changed"}, msg="backend only")
    # 2) On HEAD, edit the manifest to REMOVE the deploy script path
    manifest_path = tmp_repo / ".github" / "governance" / "high-risk-paths.json"
    manifest = json.loads(manifest_path.read_text())
    paths = manifest["categories"]["deploy-release-ci"]["paths"]
    paths.remove("ops/deploy-retail-artifact.sh")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    cp = _run(["git", "add", ".github/governance/high-risk-paths.json"], tmp_repo)
    cp = _run(["git", "commit", "--quiet", "-m", "weaken manifest"], tmp_repo)
    assert cp.returncode == 0
    # 3) Classifier MUST still report TOUCHED via the supplement or another
    # deploy-release-ci path because the BASE manifest still contains
    # deploy-retail-artifact.sh.
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0, (
        "trust anchor violated: classifier used HEAD manifest and "
        "incorrectly skipped; got rc="
        f"{cp.returncode} stdout={cp.stdout!r} stderr={cp.stderr!r}"
    )


# ---------------------------------------------------------------------------
# ERROR cases (exit 20)
# ---------------------------------------------------------------------------


def test_invalid_base_sha_is_error(tmp_repo):
    cp = _classifier(tmp_repo, base_sha="not-a-sha")
    assert cp.returncode == 20


def test_missing_base_manifest_is_error(tmp_repo):
    # Remove the manifest from the BASE commit
    cp = _run(
        ["git", "rm", "-q", ".github/governance/high-risk-paths.json"], tmp_repo
    )
    cp = _run(["git", "commit", "--quiet", "-m", "remove manifest"], tmp_repo)
    assert cp.returncode == 0
    # Now create an unrelated change so there's a HEAD~ to point at
    _commit(tmp_repo, {"backend/main.py": "# changed"}, msg="backend only")
    cp = _classifier(tmp_repo)
    assert cp.returncode == 20


def test_malformed_base_manifest_is_error(tmp_repo):
    manifest_path = tmp_repo / ".github" / "governance" / "high-risk-paths.json"
    manifest_path.write_text("{ not valid json")
    cp = _run(["git", "add", "."], tmp_repo)
    cp = _run(["git", "commit", "--quiet", "-m", "break manifest"], tmp_repo)
    assert cp.returncode == 0
    _commit(tmp_repo, {"backend/main.py": "# changed"}, msg="backend only")
    cp = _classifier(tmp_repo)
    assert cp.returncode == 20


def test_unknown_category_is_error(tmp_repo):
    _commit(tmp_repo, {"backend/main.py": "# changed"}, msg="backend only")
    cp = _classifier(tmp_repo, category="not-a-real-category")
    assert cp.returncode == 20


def test_glob_in_manifest_is_error(tmp_repo):
    manifest_path = tmp_repo / ".github" / "governance" / "high-risk-paths.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["categories"]["deploy-release-ci"]["paths"].append("ops/*.sh")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    cp = _run(["git", "add", "."], tmp_repo)
    cp = _run(["git", "commit", "--quiet", "-m", "add glob"], tmp_repo)
    assert cp.returncode == 0
    _commit(tmp_repo, {"backend/main.py": "# changed"}, msg="backend only")
    cp = _classifier(tmp_repo)
    assert cp.returncode == 20


def test_empty_base_sha_is_error(tmp_repo):
    cp = _classifier(tmp_repo, base_sha="")
    assert cp.returncode == 20


# ---------------------------------------------------------------------------
# PR-B3: complexity / ratchet authority files classify as deploy-release-ci
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "authority_path",
    [
        "scripts/check_python_complexity_contract.py",
        "scripts/python-complexity-contract-v2.json",
        "scripts/_python_complexity.py",
        "scripts/check_changed_function_complexity.py",
        "scripts/check_changed_line_coverage.py",
        "scripts/check_complexity_ratchet.py",
        "scripts/complexity-ratchet.json",
    ],
)
def test_authority_paths_classify_as_deploy_release_ci(tmp_repo, authority_path):
    """Each complexity / ratchet authority file, when modified in a PR,
    must trigger the deploy-release-ci classifier (rc 0 TOUCHED)."""
    _commit(tmp_repo, {authority_path: "# authority change"}, msg=f"touch {authority_path}")
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0, (
        f"{authority_path}: classifier did not classify as deploy-release-ci. "
        f"rc={cp.returncode} stdout={cp.stdout!r} stderr={cp.stderr!r}"
    )


# ---------------------------------------------------------------------------
# PR-B3b: B3/E2 selector + coverage / test-infrastructure trust surfaces
# classified as deploy-release-ci by A3
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "selector_or_coverage_path",
    [
        "scripts/pr_fast_select_tests.py",
        ".coveragerc",
        "backend/scripts/run_tests_isolated.sh",
        "backend/scripts/bootstrap_test_db.py",
        "backend/conftest.py",
        "backend/tests/conftest.py",
    ],
)
def test_selector_and_test_infra_paths_classify_as_deploy_release_ci(
        tmp_repo, selector_or_coverage_path):
    """PR-B3b part 2: the B3/E2 selector and the documented coverage /
    test-infrastructure trust surfaces must classify as
    deploy-release-ci so the A3 trusted `pull_request_target` workflow
    sees them as control-plane changes."""
    _commit(
        tmp_repo,
        {selector_or_coverage_path: "# b3b authority change"},
        msg=f"touch {selector_or_coverage_path}",
    )
    cp = _classifier(tmp_repo)
    assert cp.returncode == 0, (
        f"{selector_or_coverage_path}: classifier did not classify as "
        f"deploy-release-ci. rc={cp.returncode} stdout={cp.stdout!r} "
        f"stderr={cp.stderr!r}"
    )

