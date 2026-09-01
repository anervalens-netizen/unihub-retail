from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "ops" / "k5-isolated-restore.sh"
EXPECTED_ENTRYPOINT_SHA256 = "5b63364fc6bbc2a40c75b6be77372d022f9b1515377da8a543716caaebc699fb"


def _fake_docker(tmp_path: Path, mode: str = "empty") -> Path:
    docker = tmp_path / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
mode=${DOCKER_TEST_MODE:-empty}
case "$mode:$1:$2" in
  api-fail:ps:-a|api-fail:volume:ls) exit 42 ;;
  *) exit 0 ;;
esac
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return docker


def _run_early_failure(
    tmp_path: Path,
    mode: str = "empty",
    backup_started: str = "2020-01-01T00:00:00Z",
    backup_completed: str = "2020-01-01T00:01:00Z",
) -> subprocess.CompletedProcess[str]:
    backup = tmp_path / "backup"
    work = tmp_path / "work"
    backup.mkdir()
    work.mkdir()
    evidence = tmp_path / "evidence.json"
    _fake_docker(tmp_path, mode)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    env["DOCKER_TEST_MODE"] = mode
    return subprocess.run(
        [
            "bash",
            str(ENTRYPOINT),
            "--backup-root",
            str(backup),
            "--stamp",
            "20260831_121759",
            "--source-repo",
            str(ROOT),
            "--source-sha",
            "9c9cb419b3497cfc4f6c92f907cf3b24f9240c23",
            "--github-main-sha",
            "9c9cb419b3497cfc4f6c92f907cf3b24f9240c23",
            "--backup-started-at",
            backup_started,
            "--backup-completed-at",
            backup_completed,
            "--evidence-out",
            str(evidence),
            "--work-root",
            str(work),
            "--execute-isolated-restore",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _shell_function_source(name: str, following: str) -> str:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index(chr(10) + f"{name}() {{") + 1
    end = text.index(chr(10) + "}" + chr(10) + following, start) + 2
    return text[start:end]


def _run_cleanup_probe(tmp_path: Path, mode: str, created: bool) -> tuple[subprocess.CompletedProcess[str], list[str], list[str]]:
    docker = tmp_path / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "${DOCKER_TEST_LOG:?}"
case "${DOCKER_TEST_MODE:-empty}:$1:$2" in
  listing-fail:ps:-a|listing-fail:volume:ls) exit 42 ;;
  listed:ps:-a)
    printf '%s\\n' "${DOCKER_CONTAINER_NAME:?}"
    exit 0
    ;;
  listed:volume:ls)
    printf '%s\\n' "${DOCKER_VOLUME_NAME:?}"
    exit 0
    ;;
  remove-fail:rm:-f|remove-fail:volume:rm) exit 42 ;;
  *) exit 0 ;;
esac
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    work = tmp_path / "k5-isolated-restore-probe"
    work.mkdir()
    (work / "source-before.tsv").write_text("", encoding="utf-8")
    state = tmp_path / "state.tsv"
    state.write_text("missing", encoding="utf-8")
    log = tmp_path / "docker.log"
    log.write_text("", encoding="utf-8")
    cleanup = _shell_function_source("cleanup", "trap cleanup EXIT")
    probe = f"""#!/usr/bin/env bash
set -u
CONTAINER=test-container
VOLUME=test-volume
CONTAINER_CREATED={1 if created else 0}
VOLUME_CREATED={1 if created else 0}
DOCKER_RM_STATUS=not-created
DOCKER_VOLUME_RM_STATUS=not-created
DOCKER_PS_STATUS=not-run
DOCKER_VOLUME_LS_STATUS=not-run
APP_PID=
WORK={work!s}
WORK_ROOT={tmp_path!s}
SOURCE_BACKUP_MUTATION=false
RESULT=pass
CLEANUP_STATUS=pending
FAILURE_REASON=
update_final_evidence() {{
  printf '%s\\t%s\\t%s\\t%s\\t%s\\n' \\
    "$DOCKER_RM_STATUS" "$DOCKER_VOLUME_RM_STATUS" "$DOCKER_PS_STATUS" \\
    "$DOCKER_VOLUME_LS_STATUS" "$CLEANUP_STATUS" >"$STATE_FILE"
}}
{cleanup}
true
cleanup
"""
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    env["DOCKER_TEST_MODE"] = mode
    env["DOCKER_TEST_LOG"] = str(log)
    env["DOCKER_CONTAINER_NAME"] = "test-container"
    env["DOCKER_VOLUME_NAME"] = "test-volume"
    env["STATE_FILE"] = str(state)
    completed = subprocess.run(
        ["bash", "-c", probe], check=False, capture_output=True, text=True, env=env
    )
    statuses = state.read_text(encoding="utf-8").strip().split(chr(9))
    calls = log.read_text(encoding="utf-8").splitlines()
    return completed, statuses, calls


def _success_evidence_python() -> str:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index('CURRENT_PHASE="evidence"')
    start = text.index("import json" + chr(10), start)
    end = text.index(chr(10) + "PY" + chr(10) + "capture_evidence_identity", start)
    return text[start:end]


def _success_evidence_fixture(tmp_path: Path) -> tuple[list[str], Path, tuple[int, int]]:
    evidence = tmp_path / "evidence.json"
    evidence.write_text("original\\n", encoding="utf-8")
    expected = tmp_path / "expected.tsv"
    expected.write_text(
        "postgres/unihub_20260831_121759.dump" + chr(9) + "a" * 64 + chr(10),
        encoding="utf-8",
    )
    migration = tmp_path / "migration-meta.json"
    migration.write_text(
        json.dumps({"head": "001_initial.sql", "manifestSha256": "b" * 64, "count": 0, "migrations": {}}),
        encoding="utf-8",
    )
    roles = tmp_path / "roles.txt"
    roles.write_text("", encoding="utf-8")
    restores = tmp_path / "restores.tsv"
    restores.write_text("", encoding="utf-8")
    business = tmp_path / "business.tsv"
    business.write_text("stores" + chr(9) + "3" + chr(10), encoding="utf-8")
    identity = os.stat(evidence).st_dev, os.stat(evidence).st_ino
    args = [
        str(evidence),
        str(identity[0]),
        str(identity[1]),
        "k5-test",
        "9c9cb419b3497cfc4f6c92f907cf3b24f9240c23",
        "9c9cb419b3497cfc4f6c92f907cf3b24f9240c23",
        "20260831_121759",
        "2020-01-01T00:00:00Z",
        "2020-01-01T00:01:00Z",
        "c" * 64,
        "a5de3ed7803253abcbde0aa66885de5380279f133ee01bd20fd4db5bf19599af",
        "2020-01-01T01:00:00Z",
        "3600",
        "3540",
        "2020-01-01T01:00:00Z",
        "2020-01-01T01:00:01Z",
        "1",
        "postgres:18-alpine",
        "sha256:" + "d" * 64,
        "k5-test-pg",
        "55433",
        str(expected),
        str(migration),
        str(roles),
        str(restores),
        "1",
        str(business),
        "e" * 64,
        "Python 3.12",
        "9899",
    ]
    return args, evidence, identity


def test_k5_restore_entrypoint_has_valid_bash_syntax() -> None:
    completed = subprocess.run(
        ["bash", "-n", str(ENTRYPOINT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_k5_restore_entrypoint_digest_is_bound() -> None:
    assert hashlib.sha256(ENTRYPOINT.read_bytes()).hexdigest() == EXPECTED_ENTRYPOINT_SHA256


def test_k5_restore_entrypoint_requires_explicit_execution_acknowledgement() -> None:
    completed = subprocess.run(
        ["bash", str(ENTRYPOINT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "--execute-isolated-restore is required" in completed.stderr


def test_k5_restore_entrypoint_help_is_non_mutating_and_describes_safety() -> None:
    completed = subprocess.run(
        ["bash", str(ENTRYPOINT), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "isolated-only" in completed.stdout
    assert "never runs migrations" in completed.stdout
    assert "127.0.0.1" in completed.stdout


@pytest.mark.parametrize("existing_kind", ["file", "symlink"])
def test_k5_restore_entrypoint_refuses_preexisting_evidence_without_mutation(
    tmp_path: Path, existing_kind: str
) -> None:
    evidence = tmp_path / "evidence.json"
    target = tmp_path / "target.json"
    original = b"stale evidence bytes\\x00\\xff\\n"
    target.write_bytes(original)
    if existing_kind == "file":
        evidence.write_bytes(original)
    else:
        evidence.symlink_to(target)
    backup = tmp_path / "backup"
    work = tmp_path / "work"
    backup.mkdir()
    work.mkdir()
    completed = subprocess.run(
        [
            "bash",
            str(ENTRYPOINT),
            "--backup-root",
            str(backup),
            "--stamp",
            "20260831_121759",
            "--source-repo",
            str(ROOT),
            "--source-sha",
            "9c9cb419b3497cfc4f6c92f907cf3b24f9240c23",
            "--github-main-sha",
            "9c9cb419b3497cfc4f6c92f907cf3b24f9240c23",
            "--backup-started-at",
            "2020-01-01T00:00:00Z",
            "--backup-completed-at",
            "2020-01-01T00:01:00Z",
            "--evidence-out",
            str(evidence),
            "--work-root",
            str(work),
            "--execute-isolated-restore",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "must not" in completed.stderr
    assert target.read_bytes() == original
    if existing_kind == "file":
        assert evidence.read_bytes() == original
    else:
        assert evidence.is_symlink()


def test_k5_restore_entrypoint_writes_isolated_parseable_failure_evidence(tmp_path: Path) -> None:
    completed = _run_early_failure(tmp_path)
    evidence = tmp_path / "evidence.json"
    assert completed.returncode != 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["result"] == "fail"
    assert payload["failurePhase"] == "generation-manifest"
    assert payload["failureReason"]
    assert payload["cleanupStatus"] == "pass"
    assert payload["exerciseId"].startswith("k5-20260831_121759-")


def test_k5_restore_entrypoint_does_not_consume_stale_temp_evidence(tmp_path: Path) -> None:
    stale = tmp_path / "evidence.json.tmp"
    stale.write_text(json.dumps({"result": "pass", "exerciseId": "stale"}), encoding="utf-8")
    completed = _run_early_failure(tmp_path)
    payload = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert completed.returncode != 0
    assert payload["result"] == "fail"
    assert payload["exerciseId"] != "stale"
    assert stale.read_text(encoding="utf-8") == '{"result": "pass", "exerciseId": "stale"}'


def test_k5_restore_entrypoint_requires_successful_docker_cleanup_listing(tmp_path: Path) -> None:
    completed = _run_early_failure(tmp_path, "api-fail")
    payload = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert completed.returncode != 0
    assert payload["result"] == "fail"
    assert payload["cleanupStatus"] == "fail"
    assert payload["dockerCleanup"]["containerListing"] == "fail"


@pytest.mark.parametrize(
    ("backup_started", "backup_completed", "reason"),
    [
        (
            "2020-01-02T00:00:00Z",
            "2020-01-01T00:00:00Z",
            "backup completion precedes backup start",
        ),
        (
            "2099-01-01T00:00:00Z",
            "2099-01-01T00:01:00Z",
            "backup completion follows reference failure",
        ),
    ],
)
def test_k5_restore_entrypoint_rejects_impossible_backup_time_order(
    tmp_path: Path, backup_started: str, backup_completed: str, reason: str
) -> None:
    completed = _run_early_failure(tmp_path, backup_started=backup_started, backup_completed=backup_completed)
    payload = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert completed.returncode != 0
    assert payload["result"] == "fail"
    assert payload["failurePhase"] == "timestamp-validation"
    assert reason in completed.stderr
    assert reason in payload["failureReason"]


def test_k5_restore_entrypoint_accepts_valid_backup_time_order(tmp_path: Path) -> None:
    completed = _run_early_failure(
        tmp_path,
        backup_started="2020-01-01T00:00:00Z",
        backup_completed="2020-01-01T00:01:00Z",
    )
    payload = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert completed.returncode != 0
    assert payload["failurePhase"] == "generation-manifest"
    assert "generation manifest not found" in payload["failureReason"]


def test_k5_restore_entrypoint_uses_ordered_timestamps_and_monotonic_rto() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "backup completion precedes backup start" in text
    assert "backup completion follows reference failure" in text
    assert "RESTORE_STARTED_MONOTONIC_NS" in text
    assert "READY_MONOTONIC_NS" in text
    assert "monotonic RTO elapsed time was negative" in text
    assert "(elapsed_ns + 999_999_999) // 1_000_000_000" in text
    assert "max(0" not in text


def test_k5_restore_entrypoint_uses_hashed_lock_for_default_runtime() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "--require-hashes -r \"$SOURCE_DIR/backend/requirements.lock\"" in text
    assert '"$SOURCE_DIR/backend/requirements.txt"' not in text


def test_k5_restore_entrypoint_covers_certified_acceptance_contract() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")

    required_markers = (
        "--stamp",
        "--source-sha",
        "--github-main-sha",
        "--backup-started-at",
        "--backup-completed-at",
        "--execute-isolated-restore",
        "generation_${STAMP}.sha256",
        "sha256sum",
        "127.0.0.1:${PG_PORT}:5432",
        "pg_restore -U postgres --no-owner --no-acl --exit-on-error",
        "PRAGMA integrity_check",
        "SELECT filename, checksum FROM schema_migrations ORDER BY filename;",
        "business-integrity counts are not reproducible",
        "uvicorn main:app",
        "/livez",
        "/health",
        "/readyz",
        "conservative-generation-age-upper-bound",
        "monotonic-from-payload-transfer-start-to-restored-service-acceptance",
        '"cleanupStatus": "pending"',
        "a5de3ed7803253abcbde0aa66885de5380279f133ee01bd20fd4db5bf19599af",
    )
    for marker in required_markers:
        assert marker in text

    forbidden_markers = (
        "systemctl restart",
        "systemctl stop",
        "run_migrations",
        "alembic upgrade",
        "docker inspect {{.Config.Env}}",
        "0.0.0.0:${PG_PORT}",
    )
    for marker in forbidden_markers:
        assert marker not in text


def test_success_evidence_replacement_checks_identity_and_captures_after_replace(
    tmp_path: Path,
) -> None:
    args, evidence, original_identity = _success_evidence_fixture(tmp_path)
    text = ENTRYPOINT.read_text(encoding="utf-8")
    evidence_start = text.index('CURRENT_PHASE="evidence"')
    replacement = text.index("temporary.replace(path)", evidence_start)
    capture = text.index("PY\ncapture_evidence_identity", replacement)
    result = text.index('RESULT="pass"', capture)
    operation = _success_evidence_python()
    assert "expected = (int(expected_device), int(expected_inode))" in operation
    assert "if not path.exists()" in operation
    assert "stat.S_ISLNK" in operation
    assert ".success.{os.getpid()}.tmp" in operation
    assert replacement < capture < result

    completed = subprocess.run(
        [sys.executable, "-c", operation, *args],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["result"] == "pass"
    replaced_identity = os.stat(evidence).st_dev, os.stat(evidence).st_ino
    assert replaced_identity != original_identity
    assert not list(tmp_path.glob(".evidence.json.success.*.tmp"))


@pytest.mark.parametrize("replacement_kind", ["file", "symlink"])
def test_success_evidence_refuses_replaced_or_symlink_output(
    tmp_path: Path, replacement_kind: str
) -> None:
    args, evidence, _original_identity = _success_evidence_fixture(tmp_path)
    unexpected = tmp_path / "unexpected.json"
    unexpected.write_text("unexpected", encoding="utf-8")
    evidence.unlink()
    if replacement_kind == "symlink":
        evidence.symlink_to(unexpected)
    else:
        evidence.hardlink_to(unexpected)

    completed = subprocess.run(
        [sys.executable, "-c", _success_evidence_python(), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "evidence output" in completed.stderr
    assert unexpected.read_text(encoding="utf-8") == "unexpected"
    if replacement_kind == "symlink":
        assert evidence.is_symlink()
    else:
        assert evidence.read_text(encoding="utf-8") == "unexpected"
    assert not list(tmp_path.glob(".evidence.json.success.*.tmp"))


@pytest.mark.parametrize(
    ("mode", "created", "expected_rc", "expected_statuses"),
    [
        ("empty", False, 0, ["not-created", "not-created", "pass", "pass", "pass"]),
        ("empty", True, 0, ["pass", "pass", "pass", "pass", "pass"]),
        ("remove-fail", True, 1, ["fail", "fail", "pass", "pass", "fail"]),
        ("listing-fail", False, 1, ["not-created", "not-created", "fail", "fail", "fail"]),
        ("listed", False, 1, ["not-created", "not-created", "pass", "pass", "fail"]),
    ],
)
def test_cleanup_fake_docker_resource_lifecycle_is_fail_closed(
    tmp_path: Path,
    mode: str,
    created: bool,
    expected_rc: int,
    expected_statuses: list[str],
) -> None:
    completed, statuses, calls = _run_cleanup_probe(tmp_path, mode, created)
    assert completed.returncode == expected_rc, completed.stderr
    assert statuses == expected_statuses
    assert any(call.startswith("ps -a") for call in calls)
    assert any(call.startswith("volume ls") for call in calls)
    removal_calls = [call for call in calls if call.startswith("rm ") or call.startswith("volume rm")]
    if not created:
        assert removal_calls == []
    else:
        assert any(call.startswith("rm -f") for call in removal_calls)
        assert any(call.startswith("volume rm") for call in removal_calls)
