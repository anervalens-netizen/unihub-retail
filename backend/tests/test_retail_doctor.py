from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "retail_doctor.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("retail_doctor", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


def test_env_presence_never_exposes_file_contents(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OIDC_CLIENT_SECRET=do-not-print-this\n", encoding="utf-8")

    result = MODULE._check_env_file(env_file)

    assert result.status == "pass"
    assert "do-not-print-this" not in result.detail
    assert "OIDC_CLIENT_SECRET" not in result.detail


def test_missing_env_is_a_setup_failure(tmp_path: Path) -> None:
    result = MODULE._check_env_file(tmp_path / "missing.env")

    assert result.status == "fail"
    assert ".env.example" in result.detail


def test_config_contract_reuses_existing_checker(monkeypatch: Any, tmp_path: Path) -> None:
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    seen: list[tuple[str, ...]] = []

    def fake_run(args: tuple[str, ...]) -> Any:
        seen.append(tuple(args))
        return MODULE.CommandOutcome(0, "Environment contract valid: 1 variables", "")

    monkeypatch.setattr(MODULE, "VENV_PYTHON", python)
    monkeypatch.setattr(MODULE, "_run_command", fake_run)

    result = MODULE._check_config_contract()

    assert result.status == "pass"
    assert seen == [(str(python), str(MODULE.CONFIG_CHECKER))]


def test_migration_check_reuses_static_manifest_validators(
    monkeypatch: Any, tmp_path: Path
) -> None:
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    seen: list[tuple[str, ...]] = []

    def fake_run(args: tuple[str, ...]) -> Any:
        seen.append(tuple(args))
        return MODULE.CommandOutcome(0, "Migration manifest/files valid: 70 entries", "")

    monkeypatch.setattr(MODULE, "VENV_PYTHON", python)
    monkeypatch.setattr(MODULE, "_run_command", fake_run)

    result = MODULE._check_migration_manifest()

    assert result.status == "pass"
    assert len(seen) == 1
    command = seen[0]
    assert command[:2] == (str(python), "-c")
    assert "load_migration_manifest" in command[2]
    assert "verify_migration_files" in command[2]
    assert "run_migrations" not in command[2]
    assert "verify_migrations_current" not in command[2]


def test_dirty_worktree_is_warning_not_failure(monkeypatch: Any) -> None:
    outputs = {
        ("git", "branch", "--show-current"): "v3/example\n",
        ("git", "rev-parse", "HEAD"): "a" * 40 + "\n",
        ("git", "rev-parse", "HEAD^{tree}"): "b" * 40 + "\n",
        ("git", "status", "--porcelain"): " M LOCAL_SETUP.md\n?? scratch.txt\n",
    }

    def fake_run(args: tuple[str, ...]) -> Any:
        return MODULE.CommandOutcome(0, outputs[tuple(args)], "")

    monkeypatch.setattr(MODULE, "_run_command", fake_run)

    result = MODULE._check_repository()

    assert result.status == "warn"
    assert "dirty=2" in result.detail
    assert "head=aaaaaaaaaaaa" in result.detail
    assert "tree=bbbbbbbbbbbb" in result.detail


def test_node_major_must_match_setup_contract(monkeypatch: Any) -> None:
    monkeypatch.setattr(MODULE.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        MODULE,
        "_run_command",
        lambda args: MODULE.CommandOutcome(0, "v23.1.0\n", ""),
    )

    result = MODULE._check_node()

    assert result.status == "fail"
    assert "requires major 22" in result.detail


def test_main_warns_without_failing(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(
        MODULE,
        "collect_checks",
        lambda env_file: [
            MODULE.CheckResult("one", "pass", "ok"),
            MODULE.CheckResult("two", "warn", "optional"),
        ],
    )

    exit_code = MODULE.main(["--json"])
    payload = capsys.readouterr().out

    assert exit_code == 0
    assert '"ok": true' in payload


def test_main_fails_when_any_setup_check_fails(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(
        MODULE,
        "collect_checks",
        lambda env_file: [MODULE.CheckResult("one", "fail", "missing")],
    )

    exit_code = MODULE.main(["--json"])
    payload = capsys.readouterr().out

    assert exit_code == 1
    assert '"ok": false' in payload
