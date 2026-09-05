from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_python_requirement_locks.py"
DEPENDENCY_POLICY_PATH = REPO_ROOT / "scripts" / "check_dependency_policy.mjs"


def _load_checker() -> Any:
    spec = importlib.util.spec_from_file_location("check_python_requirement_locks", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Any, module)


CHECKER = _load_checker()


def _write(root: Path, rel: str, content: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, lock: str) -> None:
    monkeypatch.setattr(CHECKER, "ROOT", tmp_path)
    _write(tmp_path, "source.txt", source)
    _write(tmp_path, "lock.txt", lock)
    CHECKER.verify("source.txt", "lock.txt")


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _run_pr_diff_policy(tmp_path: Path, changed_paths: list[str]) -> subprocess.CompletedProcess[str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo, "package.json", json.dumps({"overrides": {"nanoid": "3.3.18"}}) + "\n")
    _write(
        repo,
        "package-lock.json",
        json.dumps({"packages": {"node_modules/nanoid": {"version": "3.3.18"}}}) + "\n",
    )
    script_target = repo / "scripts" / "check_dependency_policy.mjs"
    script_target.parent.mkdir(parents=True)
    shutil.copy2(DEPENDENCY_POLICY_PATH, script_target)

    requirement_paths = (
        "backend/requirements.txt",
        "backend/requirements.lock",
        "backend/requirements-dev.txt",
        "backend/requirements-dev.lock",
    )
    for rel in requirement_paths:
        _write(repo, rel, "base\n")

    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "dependency-policy-test@example.invalid")
    _git(repo, "config", "user.name", "dependency-policy-test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")

    for rel in changed_paths:
        path = repo / rel
        if path.exists():
            path.write_text(path.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
        else:
            _write(repo, rel, "changed\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate")

    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"pull_request": {"base": {"sha": base_sha}}}),
        encoding="utf-8",
    )
    node = os.environ.get("RETAIL_NODE") or shutil.which("node")
    if not node:
        raise RuntimeError("node runtime is required for dependency-policy subprocess tests")
    env = os.environ.copy()
    env["GITHUB_EVENT_PATH"] = str(event_path)
    return subprocess.run(
        [node, "scripts/check_dependency_policy.mjs", "--pr-diff-only"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_source_rejects_nested_requirement_directive(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.txt", "-r other.txt\n")
    with pytest.raises(SystemExit, match="nested requirement directives"):
        CHECKER.load_source(path)


def test_source_skips_false_marker(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.txt", "demo==1.0; python_version < '1'\n")
    assert CHECKER.load_source(path) == {}


def test_source_rejects_duplicate_canonical_names(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.txt", "Demo_Pkg==1.0\ndemo-pkg==1.0\n")
    with pytest.raises(SystemExit, match="duplicate direct requirement for demo-pkg"):
        CHECKER.load_source(path)


def test_source_rejects_invalid_requirement(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.txt", "not a valid requirement ???\n")
    with pytest.raises(SystemExit, match="invalid requirement"):
        CHECKER.load_source(path)


def test_source_rejects_direct_url(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.txt", "demo @ https://example.invalid/demo.whl\n")
    with pytest.raises(SystemExit, match="direct URL requirements are not supported"):
        CHECKER.load_source(path)


def test_lock_rejects_invalid_version(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.lock", "demo==not_a_version \\\n")
    with pytest.raises(SystemExit, match="invalid pinned version for demo"):
        CHECKER.load_lock(path)


def test_lock_rejects_conflicting_pins(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.lock", "demo==1.0 \\\ndemo==2.0 \\\n")
    with pytest.raises(SystemExit, match="conflicting pins for demo"):
        CHECKER.load_lock(path)


def test_lock_accepts_active_environment_marker(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.lock", 'demo==1.0 ; python_version >= "3" \\\n')
    pins = CHECKER.load_lock(path)
    assert pins["demo"][0] == CHECKER.Version("1.0")
    assert pins["demo"][2] == frozenset({'python_version >= "3"'})


def test_lock_skips_inactive_environment_marker(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.lock", 'demo==1.0 ; python_version < "1" \\\n')
    assert CHECKER.load_lock(path) == {}


def test_lock_rejects_invalid_environment_marker(tmp_path: Path) -> None:
    path = _write(tmp_path, "requirements.lock", 'demo==1.0 ; python_version >>> "3" \\\n')
    with pytest.raises(SystemExit, match="invalid environment marker for demo"):
        CHECKER.load_lock(path)


def test_verify_rejects_missing_direct_requirement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit, match="missing direct requirement demo"):
        _verify(tmp_path, monkeypatch, "demo==1.0\n", "other==1.0 \\\n")


def test_verify_rejects_version_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit, match="does not satisfy"):
        _verify(tmp_path, monkeypatch, "demo>=2.0\n", "demo==1.0 \\\n")


def test_verify_rejects_missing_requested_extra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit, match="missing requested extras speed"):
        _verify(tmp_path, monkeypatch, "demo[speed]==1.0\n", "demo==1.0 \\\n")


def test_verify_accepts_matching_or_superset_extras(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _verify(tmp_path, monkeypatch, "demo[speed]==1.0\n", "demo[speed,security]==1.0 \\\n")


def test_verify_accepts_matching_active_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _verify(
        tmp_path,
        monkeypatch,
        'demo==1.0; python_version >= "3"\n',
        'demo==1.0 ; python_version >= "3" \\\n',
    )


def test_verify_rejects_marker_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit, match="marker mismatch"):
        _verify(
            tmp_path,
            monkeypatch,
            'demo==1.0; python_version >= "3"\n',
            'demo==1.0 ; python_version >= "2" \\\n',
        )


@pytest.mark.parametrize(
    ("changed_paths", "missing_lock"),
    [
        (["backend/requirements.txt"], "backend/requirements.lock"),
        (
            ["backend/requirements.txt", "backend/requirements.lock"],
            "backend/requirements-dev.lock",
        ),
        (["backend/requirements-dev.txt"], "backend/requirements-dev.lock"),
    ],
)
def test_pr_diff_policy_rejects_missing_generated_lock(
    tmp_path: Path,
    changed_paths: list[str],
    missing_lock: str,
) -> None:
    completed = _run_pr_diff_policy(tmp_path, changed_paths)
    assert completed.returncode != 0
    assert missing_lock in completed.stderr


def test_pr_diff_policy_accepts_all_required_generated_locks(tmp_path: Path) -> None:
    completed = _run_pr_diff_policy(
        tmp_path,
        [
            "backend/requirements.txt",
            "backend/requirements.lock",
            "backend/requirements-dev.txt",
            "backend/requirements-dev.lock",
        ],
    )
    assert completed.returncode == 0, completed.stderr
    assert "runtime-lock-check=required" in completed.stdout


def test_pr_diff_policy_skips_runtime_lock_for_unrelated_change(tmp_path: Path) -> None:
    completed = _run_pr_diff_policy(tmp_path, ["frontend.ts"])
    assert completed.returncode == 0, completed.stderr
    assert "runtime-lock-check=skipped" in completed.stdout
