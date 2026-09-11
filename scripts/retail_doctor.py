#!/usr/bin/env python3
"""Read-only local setup diagnostics for UniHub Retail.

No database connection, migration execution, service mutation, or dotenv value
output is performed. Existing repository validators remain authoritative.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
VENV_PYTHON = BACKEND_DIR / "venv" / "bin" / "python"
CONFIG_CHECKER = ROOT / "scripts" / "check_env_contract.py"
DEFAULT_ENV_FILE = ROOT / ".env"
NODE_MAJOR = 22
MIN_PYTHON = (3, 12)
COMMAND_TIMEOUT_SECONDS = 30

MIGRATION_STATIC_CHECK = "\n".join(
    (
        "import sys",
        f"sys.path.insert(0, {str(BACKEND_DIR)!r})",
        "from db.migration_runner import load_migration_manifest, verify_migration_files",
        "manifest = load_migration_manifest()",
        "verify_migration_files(manifest)",
        "print(f'Migration manifest/files valid: {len(manifest.checksums)} entries')",
    )
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _run_command(args: Sequence[str]) -> CommandOutcome:
    try:
        completed = subprocess.run(
            list(args),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandOutcome(127, stderr=str(exc))
    return CommandOutcome(completed.returncode, completed.stdout, completed.stderr)


def _compact_output(outcome: CommandOutcome) -> str:
    parts = [part.strip() for part in (outcome.stdout, outcome.stderr) if part.strip()]
    text = "; ".join(parts).replace("\n", "; ")
    return text[:800] if text else f"exit={outcome.returncode}"


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _check_repository() -> CheckResult:
    branch = _run_command(("git", "branch", "--show-current"))
    head = _run_command(("git", "rev-parse", "HEAD"))
    tree = _run_command(("git", "rev-parse", "HEAD^{tree}"))
    status = _run_command(("git", "status", "--porcelain"))
    outcomes = (branch, head, tree, status)
    failed = next((item for item in outcomes if item.returncode != 0), None)
    if failed is not None:
        return CheckResult("repository", "fail", _compact_output(failed))
    dirty_count = sum(bool(line.strip()) for line in status.stdout.splitlines())
    branch_name = branch.stdout.strip() or "DETACHED"
    detail = (
        f"branch={branch_name} head={head.stdout.strip()[:12]} "
        f"tree={tree.stdout.strip()[:12]} dirty={dirty_count}"
    )
    return CheckResult("repository", "warn" if dirty_count else "pass", detail)


def _check_python() -> CheckResult:
    version = sys.version_info
    rendered = f"{version.major}.{version.minor}.{version.micro}"
    if (version.major, version.minor) < MIN_PYTHON:
        return CheckResult("python", "fail", f"{rendered}; requires Python 3.12+")
    return CheckResult("python", "pass", rendered)


def _check_node() -> CheckResult:
    if shutil.which("node") is None:
        return CheckResult("node", "fail", "missing; requires Node.js 22")
    outcome = _run_command(("node", "--version"))
    match = re.fullmatch(r"v?(\d+)(?:\.\d+){1,2}", outcome.stdout.strip())
    if outcome.returncode != 0 or match is None:
        return CheckResult("node", "fail", _compact_output(outcome))
    if int(match.group(1)) != NODE_MAJOR:
        return CheckResult("node", "fail", f"{outcome.stdout.strip()}; requires major 22")
    return CheckResult("node", "pass", outcome.stdout.strip())


def _check_npm() -> CheckResult:
    if shutil.which("npm") is None:
        return CheckResult("npm", "fail", "missing")
    outcome = _run_command(("npm", "--version"))
    return CheckResult("npm", "pass" if outcome.returncode == 0 else "fail", _compact_output(outcome))


def _check_docker() -> CheckResult:
    if shutil.which("docker") is None:
        return CheckResult("docker", "warn", "missing; required for isolated backend tests")
    outcome = _run_command(("docker", "--version"))
    return CheckResult("docker", "pass" if outcome.returncode == 0 else "warn", _compact_output(outcome))


def _check_required_path(name: str, path: Path, missing_detail: str) -> CheckResult:
    if path.exists():
        return CheckResult(name, "pass", _display_path(path))
    return CheckResult(name, "fail", missing_detail)


def _check_env_file(path: Path) -> CheckResult:
    if path.is_file():
        return CheckResult("env-file", "pass", _display_path(path))
    return CheckResult(
        "env-file",
        "fail",
        f"missing {_display_path(path)}; copy .env.example and add local-only credentials",
    )


def _check_config_contract() -> CheckResult:
    if not VENV_PYTHON.is_file():
        return CheckResult("config-contract", "warn", "not run because backend/venv is missing")
    outcome = _run_command((str(VENV_PYTHON), str(CONFIG_CHECKER)))
    return CheckResult(
        "config-contract",
        "pass" if outcome.returncode == 0 else "fail",
        _compact_output(outcome),
    )


def _check_migration_manifest() -> CheckResult:
    if not VENV_PYTHON.is_file():
        return CheckResult("migration-manifest", "warn", "not run because backend/venv is missing")
    outcome = _run_command((str(VENV_PYTHON), "-c", MIGRATION_STATIC_CHECK))
    return CheckResult(
        "migration-manifest",
        "pass" if outcome.returncode == 0 else "fail",
        _compact_output(outcome),
    )


def collect_checks(env_file: Path = DEFAULT_ENV_FILE) -> list[CheckResult]:
    return [
        _check_repository(),
        _check_python(),
        _check_node(),
        _check_npm(),
        _check_docker(),
        _check_required_path(
            "backend-venv",
            VENV_PYTHON,
            "missing backend/venv; follow LOCAL_SETUP.md backend dependency steps",
        ),
        _check_required_path("node-modules", ROOT / "node_modules", "missing node_modules; run npm ci"),
        _check_env_file(env_file),
        _check_config_contract(),
        _check_migration_manifest(),
    ]


def _summary(checks: Sequence[CheckResult]) -> dict[str, int]:
    return {status: sum(check.status == status for check in checks) for status in ("pass", "warn", "fail")}


def _render_text(checks: Sequence[CheckResult]) -> None:
    for check in checks:
        print(f"{check.status.upper():4} {check.name}: {check.detail}")
    summary = _summary(checks)
    print(f"summary: {summary['pass']} pass, {summary['warn']} warn, {summary['fail']} fail")


def _render_json(checks: Sequence[CheckResult]) -> None:
    summary = _summary(checks)
    print(
        json.dumps(
            {
                "ok": summary["fail"] == 0,
                "root": str(ROOT),
                "summary": summary,
                "checks": [asdict(check) for check in checks],
            },
            indent=2,
            sort_keys=True,
        )
    )


def _env_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="dotenv path to check for presence only; values are never printed",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable diagnostics")
    args = parser.parse_args(argv)
    checks = collect_checks(_env_path(args.env_file))
    _render_json(checks) if args.json else _render_text(checks)
    return 1 if any(check.status == "fail" for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
