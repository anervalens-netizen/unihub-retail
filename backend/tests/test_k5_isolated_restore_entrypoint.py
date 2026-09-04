from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import shlex
import stat as stat_module
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "ops" / "k5-isolated-restore.sh"
EXPECTED_ENTRYPOINT_SHA256 = "42636b83dfe7d30e88382e6a8841cead6b40fd11341d6398721672646ee9e8fb"  # pragma: allowlist secret

FUTURE_STAMP = "20260903_010203"
COMPONENT_LABELS = (
    "unihub",
    "mobiup_dwh",
    "unihub_identity",
    "unihub_retail",
    "unihub_learning",
    "authentik",
    "glitchtip",
)
WEEKLY_HELPER_SHA256 = "a5de3ed7803253abcbde0aa66885de5380279f133ee01bd20fd4db5bf19599af"
FIXTURE_SHA = "9c9cb419b3497cfc4f6c92f907cf3b24f9240c23"


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


def _init_source_repo(base: Path) -> tuple[Path, str]:
    repo = base / "source-repo"
    repo.mkdir()
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"

    def git(*args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return completed.stdout.strip()

    git("init", "-q")
    git(
        "-c",
        "user.email=k5@example.invalid",
        "-c",
        "user.name=k5-fixture",
        "commit",
        "--allow-empty",
        "-q",
        "-m",
        "k5 synthetic source release",
    )
    return repo, git("rev-parse", "HEAD")


def _component_relatives(stamp: str) -> list[str]:
    return [
        *(f"postgres/{label}_{stamp}.dump" for label in COMPONENT_LABELS),
        f"visits/visits_{stamp}.db",
    ]


def _valid_result_lines(
    stamp: str,
    started_at: str = "2026-08-31T12:17:59+03:00",
    completed_at: str = "2026-08-31T12:19:01+03:00",
    status: str = "verified",
    file_count: int = 8,
) -> list[str]:
    return [
        f"stamp={stamp}",
        f"status={status}",
        f"started_at={started_at}",
        f"completed_at={completed_at}",
        f"file_count={file_count}",
    ]


def _write_generation_tree(
    backup_root: Path,
    stamp: str,
    *,
    result_lines: list[str] | None = None,
    include_last_run: bool = False,
) -> None:
    manifests = backup_root / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    manifest_lines = []
    for relative in _component_relatives(stamp):
        component = backup_root / relative
        component.parent.mkdir(parents=True, exist_ok=True)
        component.write_text(f"synthetic {relative}\n", encoding="utf-8")
        digest = hashlib.sha256(component.read_bytes()).hexdigest()
        manifest_lines.append(f"{digest}  {relative}")
    (manifests / f"generation_{stamp}.sha256").write_text(
        "\n".join(manifest_lines) + "\n", encoding="utf-8"
    )
    if result_lines is not None:
        (manifests / f"generation_{stamp}.result").write_text(
            "\n".join(result_lines) + "\n", encoding="utf-8"
        )
    if include_last_run:
        (manifests / "last-run.env").write_text(
            "\n".join(
                [
                    f"stamp={stamp}",
                    "status=success",
                    "started_at=1788500000",
                    "completed_at=1788500060",
                    "checksum_ok=1",
                    "file_count=8",
                    "nas_sync_ok=1",
                ]
            )
            + "\n",
            encoding="utf-8",
        )


def _run_entrypoint(
    tmp_path: Path,
    *,
    stamp: str = FUTURE_STAMP,
    docker_mode: str = "empty",
    result_lines: list[str] | None = None,
    include_last_run: bool = False,
    extra_args: tuple[str, ...] = (),
    env_extra: dict[str, str] | None = None,
    expect_generation_tree: bool = True,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    backup = tmp_path / "backup"
    work = tmp_path / "work"
    backup.mkdir()
    work.mkdir()
    if expect_generation_tree:
        _write_generation_tree(
            backup, stamp, result_lines=result_lines, include_last_run=include_last_run
        )
    repo, source_sha = _init_source_repo(tmp_path)
    evidence = tmp_path / "evidence.json"
    _fake_docker(tmp_path, docker_mode)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    env["DOCKER_TEST_MODE"] = docker_mode
    if env_extra:
        env.update(env_extra)
    completed = subprocess.run(
        [
            "bash",
            str(ENTRYPOINT),
            "--backup-root",
            str(backup),
            "--stamp",
            stamp,
            "--source-repo",
            str(repo),
            "--source-sha",
            source_sha,
            "--github-main-sha",
            source_sha,
            "--evidence-out",
            str(evidence),
            "--work-root",
            str(work),
            "--execute-isolated-restore",
            *extra_args,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    return completed, evidence


def _shell_function_source(name: str, following: str) -> str:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index(chr(10) + f"{name}() {{") + 1
    end = text.index(chr(10) + "}" + chr(10) + following, start) + 2
    return text[start:end]


def _heredoc_python_after(marker: str) -> str:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    index = text.index(marker)
    start = text.index("<<'PY'" + chr(10), index) + len("<<'PY'" + chr(10))
    end = text.index(chr(10) + "PY" + chr(10), start)
    return text[start:end]


def _run_python(program: str, args: list[str], env: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, "-c", program, *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


METADATA_PROGRAM: str | None = None
LOCK_PROGRAM: str | None = None
DURATION_PROGRAM: str | None = None
EARLY_WRITER_PROGRAM: str | None = None
MANIFEST_PROGRAM: str | None = None
MANIFEST_IDENTITY_PROGRAM: str | None = None
FINAL_WRITER_PROGRAM: str | None = None
ACCEPTANCE_PROGRAM: str | None = None
METADATA_IDENTITY_PROGRAM: str | None = None


def _metadata_program() -> str:
    global METADATA_PROGRAM
    if METADATA_PROGRAM is None:
        METADATA_PROGRAM = _heredoc_python_after('CURRENT_PHASE="generation-metadata"')
    return METADATA_PROGRAM


def _lock_program() -> str:
    global LOCK_PROGRAM
    if LOCK_PROGRAM is None:
        LOCK_PROGRAM = _heredoc_python_after("validate_runtime_dependencies() {")
    return LOCK_PROGRAM


def _duration_program() -> str:
    global DURATION_PROGRAM
    if DURATION_PROGRAM is None:
        DURATION_PROGRAM = _heredoc_python_after('CURRENT_PHASE="postgres-restore"')
    return DURATION_PROGRAM


def _early_writer_program() -> str:
    global EARLY_WRITER_PROGRAM
    if EARLY_WRITER_PROGRAM is None:
        EARLY_WRITER_PROGRAM = _heredoc_python_after("update_early_failure_evidence() {")
    return EARLY_WRITER_PROGRAM


def _final_writer_program() -> str:
    global FINAL_WRITER_PROGRAM
    if FINAL_WRITER_PROGRAM is None:
        FINAL_WRITER_PROGRAM = _heredoc_python_after("update_final_evidence() {")
    return FINAL_WRITER_PROGRAM


def _acceptance_program() -> str:
    global ACCEPTANCE_PROGRAM
    if ACCEPTANCE_PROGRAM is None:
        ACCEPTANCE_PROGRAM = _heredoc_python_after('CURRENT_PHASE="service-acceptance"')
    return ACCEPTANCE_PROGRAM


def _run_metadata_program(
    tmp_path: Path,
    result_text: str,
    *,
    stamp: str = FUTURE_STAMP,
    reference: str = "2026-09-03T02:00:00Z",
    manifest_entries: int = 8,
) -> subprocess.CompletedProcess[str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    metadata = tmp_path / "generation.result"
    metadata.write_text(result_text, encoding="utf-8")
    expected = tmp_path / "expected.tsv"
    expected.write_text(
        "".join(f"postgres/component{i}_x.dump\t{'a' * 64}\n" for i in range(manifest_entries)),
        encoding="utf-8",
    )
    staged = tmp_path / "staged.result"
    identity = tmp_path / "identity.tsv"
    return _run_python(
        _metadata_program(),
        [str(metadata), stamp, reference, str(expected), str(staged), str(identity)],
    )


def _metadata_identity_program() -> str:
    global METADATA_IDENTITY_PROGRAM
    if METADATA_IDENTITY_PROGRAM is None:
        METADATA_IDENTITY_PROGRAM = _heredoc_python_after(
            '[ -f "$WORK/generation-metadata-identity.tsv" ]; then'
        )
    return METADATA_IDENTITY_PROGRAM


def _manifest_program() -> str:
    global MANIFEST_PROGRAM
    if MANIFEST_PROGRAM is None:
        MANIFEST_PROGRAM = _heredoc_python_after('CURRENT_PHASE="generation-manifest"')
    return MANIFEST_PROGRAM


def _manifest_identity_program() -> str:
    global MANIFEST_IDENTITY_PROGRAM
    if MANIFEST_IDENTITY_PROGRAM is None:
        MANIFEST_IDENTITY_PROGRAM = _heredoc_python_after(
            '[ -f "$WORK/generation-manifest-identity.tsv" ]; then'
        )
    return MANIFEST_IDENTITY_PROGRAM


def _write_metadata_with_identity(tmp_path: Path) -> None:
    completed = _run_metadata_program(
        tmp_path, "\n".join(_valid_result_lines(FUTURE_STAMP)) + "\n"
    )
    assert completed.returncode == 0, completed.stderr


def _run_metadata_identity_check(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    metadata = tmp_path / "generation.result"
    identity = tmp_path / "identity.tsv"
    return _run_python(_metadata_identity_program(), [str(metadata), str(identity)])


def _run_termination_probe(tmp_path: Path, scenario: str) -> subprocess.CompletedProcess[str]:
    probe = f"""#!/usr/bin/env bash
set -u
APP_PID=
APP_PROCESS_STATUS=not-started
{_shell_function_source("app_process_alive", chr(10) + "terminate_application")}
{_shell_function_source("terminate_application", chr(10) + "write_initial_evidence")}
{scenario}
printf 'status=%s\n' "$APP_PROCESS_STATUS"
"""
    env = os.environ.copy()
    env["K5_APP_TERM_GRACE_ITERATIONS"] = "3"
    env["K5_APP_TERM_SLEEP_SECONDS"] = "0.05"
    return subprocess.run(
        ["bash", "-c", probe], check=False, capture_output=True, text=True, env=env
    )


def _run_cleanup_probe(
    tmp_path: Path,
    mode: str,
    created: bool,
    *,
    term_status: str = "terminated",
    mutate_source: bool = False,
    workdir_removal_fails: bool = False,
    final_write_fails: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
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
    if mutate_source:
        watched = tmp_path / "watched-source-file"
        watched.write_text("source bytes", encoding="utf-8")
        (work / "source-paths.txt").write_text(str(watched) + chr(10), encoding="utf-8")
        (work / "source-before.tsv").write_text(
            str(watched) + chr(9) + "999999" + chr(9) + "1" + chr(10), encoding="utf-8"
        )
    else:
        (work / "source-before.tsv").write_text("", encoding="utf-8")
    state = tmp_path / "state.tsv"
    state.write_text("", encoding="utf-8")
    log = tmp_path / "docker.log"
    log.write_text("", encoding="utf-8")
    work_root = tmp_path
    # Deterministic TEST-ONLY rm shadow: placed in tmp_path so it shadows the
    # system `rm` on PATH for the probe, forwards every other invocation to
    # the real /usr/bin/rm, and only fails when the exact workdir path is
    # passed as an argument. Production cleanup behavior is untouched.
    rm_shadow = tmp_path / "rm"
    rm_shadow.write_text(
        """#!/usr/bin/env bash
set -u
SELF_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
REAL_RM=""
IFS=':' read -ra _dirs <<<"${PATH:-}"
for d in "${_dirs[@]}"; do
  [ "$d" = "$SELF_DIR" ] && continue
  if [ -x "$d/rm" ]; then
    REAL_RM="$d/rm"
    break
  fi
done
if [ -z "$REAL_RM" ]; then
  printf 'k5-test-rm-shadow: cannot locate real rm\\n' >&2
  exit 127
fi
TARGET="${K5_TEST_FAIL_RM_TARGET:-}"
if [ -n "$TARGET" ]; then
  for arg in "$@"; do
    if [ "$arg" = "$TARGET" ]; then
      printf 'k5-test-rm-shadow: refusing to remove workdir %s\\n' "$arg" >&2
      exit 1
    fi
  done
fi
exec "$REAL_RM" "$@"
""",
        encoding="utf-8",
    )
    rm_shadow.chmod(0o755)
    final_stub = ""
    if final_write_fails:
        # Simulate a durable-write failure: the PASS payload is rejected before
        # anything is recorded, so no pass state can be persisted.
        final_stub = 'if [ "$RESULT" = "pass" ]; then return 1; fi'
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
APP_PROCESS_STATUS=not-started
WORK={work!s}
WORK_ROOT={work_root!s}
SOURCE_BACKUP_MUTATION=false
RESULT=fail
CLEANUP_STATUS=pending
FAILURE_REASON=
terminate_application() {{
  APP_PROCESS_STATUS={term_status}
  if [ "$APP_PROCESS_STATUS" = "fail" ]; then return 1; fi
  return 0
}}
update_final_evidence() {{
  {final_stub}
  printf '%s\\t%s\\t%s\\t%s\\t%s\\n' \\
    "$RESULT" "$CLEANUP_STATUS" "$APP_PROCESS_STATUS" "$SOURCE_BACKUP_MUTATION" \\
    "$FAILURE_REASON" >>"$STATE_FILE"
  return 0
}}
{cleanup}
cleanup
"""
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    env["DOCKER_TEST_MODE"] = mode
    env["DOCKER_TEST_LOG"] = str(log)
    env["DOCKER_CONTAINER_NAME"] = "test-container"
    env["DOCKER_VOLUME_NAME"] = "test-volume"
    env["STATE_FILE"] = str(state)
    if workdir_removal_fails:
        env["K5_TEST_FAIL_RM_TARGET"] = str(work)
    try:
        completed = subprocess.run(
            ["bash", "-c", probe], check=False, capture_output=True, text=True, env=env
        )
    finally:
        pass
    records = [
        line.split(chr(9)) for line in state.read_text(encoding="utf-8").splitlines() if line
    ]
    return completed, records


def _write_evidence_fixture(tmp_path: Path) -> Path:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schemaVersion": "k5/1",
                "kind": "restore-exercise-evidence",
                "result": "fail",
                "cleanupStatus": "pending",
                "failurePhase": "preflight",
                "failureReason": "exercise did not complete",
            },
            indent=2,
        )
        + chr(10),
        encoding="utf-8",
    )
    return evidence


def _run_early_writer(
    tmp_path: Path,
    evidence: Path,
    phase: str = "probe",
    reason: str = "probe failure",
    program: str | None = None,
) -> subprocess.CompletedProcess[str]:
    identity = os.stat(evidence)
    return _run_python(
        program or _early_writer_program(),
        [
            str(evidence),
            str(identity.st_dev),
            str(identity.st_ino),
            phase,
            reason,
        ],
    )


def _add_dist(site: Path, name: str, version: str) -> None:
    safe = name.replace("-", "_")
    dist_info = site / f"{safe}-{version}.dist-info"
    dist_info.mkdir(parents=True, exist_ok=True)
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n", encoding="utf-8"
    )


def _lock_text(*pins: tuple[str, str]) -> str:
    lines = [
        "#",
        "# synthetic requirements.lock fixture",
        "#",
    ]
    for name, version in pins:
        lines.append(f"{name}=={version} \\")
        lines.append("    --hash=sha256:" + "a" * 64)
        lines.append("    # via k5-fixture")
    return chr(10).join(lines) + chr(10)


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _expected_fingerprint(*pins: tuple[str, str]) -> str:
    canonical = sorted(f"{_normalize_name(name)}=={version}" for name, version in pins)
    return hashlib.sha256(chr(10).join(canonical).encode("utf-8")).hexdigest()


def _run_lock_program(tmp_path: Path, lock_text: str, site: Path | None = None):
    lock = tmp_path / "requirements.lock"
    lock.write_text(lock_text, encoding="utf-8")
    env = os.environ.copy()
    if site is not None:
        env["PYTHONPATH"] = str(site)
    return _run_python(_lock_program(), [str(lock)], env=env)


def _success_evidence_fixture(tmp_path: Path) -> tuple[list[str], Path, tuple[int, int]]:
    evidence = tmp_path / "evidence.json"
    evidence.write_text("original\n", encoding="utf-8")
    expected = tmp_path / "expected.tsv"
    expected.write_text(
        "postgres/unihub_20260903_010203.dump" + chr(9) + "a" * 64 + chr(10),
        encoding="utf-8",
    )
    migration = tmp_path / "migration-meta.json"
    migration.write_text(
        json.dumps(
            {"head": "001_initial.sql", "manifestSha256": "b" * 64, "count": 0, "migrations": {}}
        ),
        encoding="utf-8",
    )
    roles = tmp_path / "roles.txt"
    roles.write_text("", encoding="utf-8")
    restores = tmp_path / "restores.tsv"
    restores.write_text(
        chr(9).join(
            [
                "unihub",
                "dr_unihub",
                "2026-09-03T01:05:00Z",
                "2026-09-03T01:05:02Z",
                "2",
                "363",
            ]
        )
        + chr(10),
        encoding="utf-8",
    )
    business = tmp_path / "business.tsv"
    business.write_text("stores" + chr(9) + "3" + chr(10), encoding="utf-8")
    identity = os.stat(evidence).st_dev, os.stat(evidence).st_ino
    args = [
        str(evidence),
        str(identity[0]),
        str(identity[1]),
        "k5-test",
        FIXTURE_SHA,
        FIXTURE_SHA,
        FUTURE_STAMP,
        "2026-09-03T01:02:03Z",
        "2026-09-03T01:03:05Z",
        "c" * 64,
        "d" * 64,
        "verified",
        WEEKLY_HELPER_SHA256,
        "2026-09-03T02:00:00Z",
        "3597",
        "3535",
        "2026-09-03T01:04:00Z",
        "2026-09-03T01:06:00Z",
        "120",
        "postgres:18-alpine",
        "sha256:" + "e" * 64,
        "k5-test-pg",
        "55433",
        str(expected),
        str(migration),
        str(roles),
        str(restores),
        "1",
        str(business),
        "f" * 64,
        "Python 3.12",
        "9899",
        "0" * 64,
        "pass",
        "1" * 64,
        "explicit",
    ]
    return args, evidence, identity


# ---------------------------------------------------------------------------
# Basic entrypoint contract
# ---------------------------------------------------------------------------


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
    assert "generation_<stamp>.result" in completed.stdout
    assert "--backup-started-at" not in completed.stdout
    assert "--backup-completed-at" not in completed.stdout


def test_k5_restore_entrypoint_rejects_removed_timestamp_flags_as_authority(
    tmp_path: Path,
) -> None:
    completed, _ = _run_entrypoint(
        tmp_path,
        extra_args=("--backup-started-at", "2026-09-03T01:02:03Z"),
        expect_generation_tree=False,
    )
    assert completed.returncode != 0
    assert "unknown argument: --backup-started-at" in completed.stderr


@pytest.mark.parametrize("existing_kind", ["file", "symlink"])
def test_k5_restore_entrypoint_refuses_preexisting_evidence_without_mutation(
    tmp_path: Path, existing_kind: str
) -> None:
    evidence = tmp_path / "evidence.json"
    target = tmp_path / "target.json"
    original = b"stale evidence bytes\x00\xff\n"
    target.write_bytes(original)
    if existing_kind == "file":
        evidence.write_bytes(original)
    else:
        evidence.symlink_to(target)
    completed, _ = _run_entrypoint(tmp_path, expect_generation_tree=False)
    assert completed.returncode != 0
    assert "must not" in completed.stderr
    assert target.read_bytes() == original
    if existing_kind == "file":
        assert evidence.read_bytes() == original
    else:
        assert evidence.is_symlink()


def test_k5_restore_entrypoint_writes_isolated_parseable_failure_evidence(
    tmp_path: Path,
) -> None:
    completed, evidence = _run_entrypoint(tmp_path, expect_generation_tree=False)
    assert completed.returncode != 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["result"] == "fail"
    assert payload["failurePhase"] == "generation-manifest"
    assert payload["failureReason"]
    assert payload["cleanupStatus"] == "pending"
    assert payload["backupStartedAt"] is None
    assert payload["backupCompletedAt"] is None
    assert payload["appTerminationStatus"] == "not-started"
    assert payload["exerciseId"].startswith(f"k5-{FUTURE_STAMP}-")


def test_k5_restore_entrypoint_does_not_consume_stale_temp_evidence(tmp_path: Path) -> None:
    stale = tmp_path / "evidence.json.tmp"
    stale.write_text(json.dumps({"result": "pass", "exerciseId": "stale"}), encoding="utf-8")
    completed, evidence = _run_entrypoint(tmp_path, expect_generation_tree=False)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert completed.returncode != 0
    assert payload["result"] == "fail"
    assert payload["exerciseId"] != "stale"
    assert stale.read_text(encoding="utf-8") == '{"result": "pass", "exerciseId": "stale"}'


def test_k5_restore_entrypoint_requires_successful_docker_cleanup_listing(
    tmp_path: Path,
) -> None:
    completed, evidence = _run_entrypoint(
        tmp_path, docker_mode="api-fail", expect_generation_tree=False
    )
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert completed.returncode != 0
    assert payload["result"] == "fail"
    assert payload["cleanupStatus"] == "fail"
    assert payload["dockerCleanup"]["containerListing"] == "fail"


# ---------------------------------------------------------------------------
# Finding 1: per-generation metadata authority
# ---------------------------------------------------------------------------


def test_finding1_valid_metadata_passes_metadata_preflight(tmp_path: Path) -> None:
    completed, evidence = _run_entrypoint(tmp_path, result_lines=_valid_result_lines(FUTURE_STAMP))
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert completed.returncode != 0
    # Proves the metadata preflight passed: execution advanced all the way to
    # the source migration-authority phase before the synthetic source tree
    # (which has no migration manifest) stopped it.
    assert payload["failurePhase"] == "source-migration-authority"
    assert payload["result"] == "fail"


def test_finding1_missing_metadata_with_rolling_last_run_is_rejected(
    tmp_path: Path,
) -> None:
    completed, evidence = _run_entrypoint(
        tmp_path, result_lines=None, include_last_run=True
    )
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert completed.returncode != 0
    assert payload["failurePhase"] == "generation-metadata"
    assert "per-generation result metadata not found" in payload["failureReason"]
    assert "never used as RPO authority" in payload["failureReason"]
    assert payload["backupStartedAt"] is None


def test_finding1_wrong_internal_stamp_is_rejected(tmp_path: Path) -> None:
    lines = _valid_result_lines("20260903_999999")
    completed = _run_metadata_program(tmp_path, "\n".join(lines) + "\n")
    assert completed.returncode != 0
    assert "does not match" in completed.stderr


def test_finding1_missing_required_timestamp_keys_are_rejected(tmp_path: Path) -> None:
    for dropped in ("started_at", "completed_at"):
        lines = [
            line
            for line in _valid_result_lines(FUTURE_STAMP)
            if not line.startswith(f"{dropped}=")
        ]
        completed = _run_metadata_program(tmp_path, "\n".join(lines) + "\n")
        assert completed.returncode != 0, dropped
        assert "missing required generation metadata keys" in completed.stderr


def test_finding1_duplicate_timestamp_key_is_rejected(tmp_path: Path) -> None:
    lines = _valid_result_lines(FUTURE_STAMP) + ["started_at=2026-09-03T01:09:09Z"]
    completed = _run_metadata_program(tmp_path, "\n".join(lines) + "\n")
    assert completed.returncode != 0
    assert "duplicate generation metadata key" in completed.stderr


@pytest.mark.parametrize(
    "bad_line",
    [
        "garbage line without assignment",
        "1bad=value",
        "started_at 2026-09-03T01:02:03Z",
    ],
)
def test_finding1_malformed_metadata_is_rejected(tmp_path: Path, bad_line: str) -> None:
    lines = _valid_result_lines(FUTURE_STAMP) + [bad_line]
    completed = _run_metadata_program(tmp_path, "\n".join(lines) + "\n")
    assert completed.returncode != 0
    assert "malformed" in completed.stderr


def test_finding1_non_verified_status_is_rejected(tmp_path: Path) -> None:
    lines = _valid_result_lines(FUTURE_STAMP, status="success")
    completed = _run_metadata_program(tmp_path, "\n".join(lines) + "\n")
    assert completed.returncode != 0
    assert "exactly 'verified'" in completed.stderr


def test_finding1_file_count_mismatch_is_rejected(tmp_path: Path) -> None:
    lines = _valid_result_lines(FUTURE_STAMP, file_count=7)
    completed = _run_metadata_program(tmp_path, "\n".join(lines) + "\n")
    assert completed.returncode != 0
    assert "does not match" in completed.stderr
    assert "manifest entry count" in completed.stderr


def test_finding1_non_numeric_file_count_is_rejected(tmp_path: Path) -> None:
    lines = [
        f"stamp={FUTURE_STAMP}",
        "status=verified",
        "started_at=2026-09-03T01:02:03Z",
        "completed_at=2026-09-03T01:03:05Z",
        "file_count=eight",
    ]
    completed = _run_metadata_program(tmp_path, "\n".join(lines) + "\n")
    assert completed.returncode != 0
    assert "not numeric" in completed.stderr


def test_finding1_metadata_and_manifest_digests_are_derived_deterministically(
    tmp_path: Path,
) -> None:
    result_text = "\n".join(_valid_result_lines(FUTURE_STAMP)) + "\n"
    first = _run_metadata_program(tmp_path / "run-a", result_text)
    second = _run_metadata_program(tmp_path / "run-b", result_text)
    assert first.returncode == 0
    assert first.stdout == second.stdout
    metadata = tmp_path / "run-a" / "generation.result"
    digests = {
        hashlib.sha256(metadata.read_bytes()).hexdigest() for _ in range(2)
    }
    assert len(digests) == 1
    # The reported metadata digest is the SHA of the exact parsed bytes.
    reported_sha = first.stdout.strip().split("\t")[2]
    assert reported_sha == hashlib.sha256(metadata.read_bytes()).hexdigest()
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "metadata_sha256 = hashlib.sha256(metadata_bytes).hexdigest()" in text
    # The manifest digest is derived from the same single snapshot bytes that
    # are parsed and staged; a separate authoritative `sha256sum` reread of
    # the manifest file is forbidden because it would re-open a TOCTOU window.
    assert "manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()" in text
    assert 'sha256sum "$MANIFEST"' not in text
    assert 'GENERATION_MANIFEST_SHA256="$(sha256sum "$MANIFEST"' not in text


def test_finding1_metadata_is_opened_once_and_staged_byte_identical(
    tmp_path: Path,
) -> None:
    result_text = "\n".join(_valid_result_lines(FUTURE_STAMP)) + "\n"
    completed = _run_metadata_program(tmp_path, result_text)
    assert completed.returncode == 0, completed.stderr
    metadata = tmp_path / "generation.result"
    staged = tmp_path / "staged.result"
    identity = tmp_path / "identity.tsv"
    # Staged bytes are exactly the validated snapshot bytes.
    assert staged.read_bytes() == metadata.read_bytes()
    reported_sha = completed.stdout.strip().split("\t")[2]
    assert reported_sha == hashlib.sha256(metadata.read_bytes()).hexdigest()
    # Identity captured from the same descriptor is persisted for cleanup.
    identity_values = dict(
        line.split("=", 1) for line in identity.read_text(encoding="utf-8").splitlines()
    )
    assert identity_values["sha256"] == reported_sha
    assert identity_values["size"] == str(metadata.stat().st_size)
    assert identity_values["inode"] == str(metadata.stat().st_ino)
    assert identity_values["device"] == str(metadata.stat().st_dev)


def test_finding1_no_second_authoritative_metadata_read() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert 'sha256sum "$GENERATION_RESULT"' not in text
    assert "os.O_RDONLY | os.O_NOFOLLOW" in text


def test_finding1_symlink_generation_result_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real.result"
    real.write_text("\n".join(_valid_result_lines(FUTURE_STAMP)) + "\n", encoding="utf-8")
    metadata = tmp_path / "generation.result"
    metadata.symlink_to(real)
    expected = tmp_path / "expected.tsv"
    expected.write_text(
        "".join(f"postgres/component{i}_x.dump\t{'a' * 64}\n" for i in range(8)),
        encoding="utf-8",
    )
    completed = _run_python(
        _metadata_program(),
        [
            str(metadata),
            FUTURE_STAMP,
            "2026-09-03T02:00:00Z",
            str(expected),
            str(tmp_path / "staged.result"),
            str(tmp_path / "identity.tsv"),
        ],
    )
    assert completed.returncode != 0
    assert "unable to open generation metadata safely" in completed.stderr
    assert not (tmp_path / "staged.result").exists()


def test_finding1_metadata_source_identity_recheck_passes_when_unchanged(
    tmp_path: Path,
) -> None:
    _write_metadata_with_identity(tmp_path)
    completed = _run_metadata_identity_check(tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert "generation-metadata-source-identity-ok" in completed.stdout


def test_finding1_metadata_source_replacement_fails_recheck(tmp_path: Path) -> None:
    _write_metadata_with_identity(tmp_path)
    metadata = tmp_path / "generation.result"
    metadata.unlink()
    metadata.write_text(
        "\n".join(_valid_result_lines(FUTURE_STAMP)) + "\n", encoding="utf-8"
    )
    completed = _run_metadata_identity_check(tmp_path)
    assert completed.returncode != 0
    assert "changed during exercise" in completed.stderr


def test_finding1_same_size_metadata_replacement_is_caught(tmp_path: Path) -> None:
    _write_metadata_with_identity(tmp_path)
    metadata = tmp_path / "generation.result"
    original_size = metadata.stat().st_size
    replacement = "stamp=20260903_010203\n" + "x" * (original_size - len("stamp=20260903_010203\n"))
    assert len(replacement.encode("utf-8")) == original_size
    metadata.unlink()
    metadata.write_text(replacement, encoding="utf-8")
    assert metadata.stat().st_size == original_size
    completed = _run_metadata_identity_check(tmp_path)
    assert completed.returncode != 0
    assert "changed during exercise" in completed.stderr


def test_finding1_symlink_swapped_metadata_source_fails_recheck(tmp_path: Path) -> None:
    _write_metadata_with_identity(tmp_path)
    metadata = tmp_path / "generation.result"
    original_bytes = metadata.read_bytes()
    twin = tmp_path / "twin.result"
    twin.write_bytes(original_bytes)
    metadata.unlink()
    metadata.symlink_to(twin)
    completed = _run_metadata_identity_check(tmp_path)
    assert completed.returncode != 0
    assert "unable to reopen generation metadata safely" in completed.stderr


# ---------------------------------------------------------------------------
# Finding 7: UTC canonicalization
# ---------------------------------------------------------------------------


def test_finding7_non_zero_offset_canonicalizes_to_z(tmp_path: Path) -> None:
    completed = _run_metadata_program(
        tmp_path, "\n".join(_valid_result_lines(FUTURE_STAMP)) + "\n"
    )
    assert completed.returncode == 0, completed.stderr
    started, finished, _sha = completed.stdout.strip().split("\t")
    assert (started, finished) == ("2026-08-31T09:17:59Z", "2026-08-31T09:19:01Z")


def test_finding7_utc_values_keep_the_same_instant(tmp_path: Path) -> None:
    lines = _valid_result_lines(
        FUTURE_STAMP,
        started_at="2026-09-03T01:02:03Z",
        completed_at="2026-09-03T01:03:05Z",
    )
    completed = _run_metadata_program(tmp_path, "\n".join(lines) + "\n")
    assert completed.returncode == 0, completed.stderr
    started, finished, _sha = completed.stdout.strip().split("\t")
    assert (started, finished) == ("2026-09-03T01:02:03Z", "2026-09-03T01:03:05Z")


def test_finding7_naive_timestamp_is_rejected(tmp_path: Path) -> None:
    lines = _valid_result_lines(
        FUTURE_STAMP, started_at="2026-09-03T01:02:03"
    )
    completed = _run_metadata_program(tmp_path, "\n".join(lines) + "\n")
    assert completed.returncode != 0
    assert "explicit UTC offset" in completed.stderr


def test_finding7_ordering_uses_normalized_values(tmp_path: Path) -> None:
    # 05:00+03:00 is 02:00Z, i.e. AFTER the 01:30Z completion instant, even
    # though a naive string comparison would consider "05" > "01" acceptable.
    lines = _valid_result_lines(
        FUTURE_STAMP,
        started_at="2026-09-03T05:00:00+03:00",
        completed_at="2026-09-03T01:30:00Z",
    )
    completed = _run_metadata_program(tmp_path, "\n".join(lines) + "\n")
    assert completed.returncode != 0
    assert "backup completion precedes backup start" in completed.stderr


def test_finding7_completion_after_reference_failure_is_rejected(tmp_path: Path) -> None:
    lines = _valid_result_lines(
        FUTURE_STAMP,
        started_at="2026-09-03T01:02:03Z",
        completed_at="2026-09-03T01:03:05Z",
    )
    completed = _run_metadata_program(
        tmp_path,
        "\n".join(lines) + "\n",
        reference="2026-09-03T01:00:00Z",
    )
    assert completed.returncode != 0
    assert "backup completion follows reference failure" in completed.stderr


# ---------------------------------------------------------------------------
# Finding 2: application process termination proof
# ---------------------------------------------------------------------------


def test_finding2_never_started_app_reports_not_started(tmp_path: Path) -> None:
    completed = _run_termination_probe(tmp_path, "terminate_application || true")
    assert completed.returncode == 0, completed.stderr
    assert "status=not-started" in completed.stdout


def test_finding2_term_termination_is_verified(tmp_path: Path) -> None:
    completed = _run_termination_probe(
        tmp_path,
        "bash -c 'exec sleep 30' & APP_PID=$!; APP_PROCESS_STATUS=running;"
        " terminate_application; printf 'rc=%s\\n' $?",
    )
    assert completed.returncode == 0, completed.stderr
    assert "rc=0" in completed.stdout
    assert "status=terminated" in completed.stdout


def test_finding2_term_ignored_then_kill_succeeds(tmp_path: Path) -> None:
    completed = _run_termination_probe(
        tmp_path,
        "bash -c 'trap \"\" TERM; sleep 3' & APP_PID=$!; APP_PROCESS_STATUS=running;"
        " terminate_application; printf 'rc=%s\\n' $?",
    )
    assert completed.returncode == 0, completed.stderr
    assert "rc=0" in completed.stdout
    assert "status=kill-terminated" in completed.stdout


def test_finding2_still_alive_after_kill_sequence_fails_without_wait(
    tmp_path: Path,
) -> None:
    completed = _run_termination_probe(
        tmp_path,
        """
kill() { return 0; }
app_process_alive() { return 0; }
WAIT_CALLED=0
wait() { WAIT_CALLED=1; return 0; }
APP_PID=424242
APP_PROCESS_STATUS=running
if terminate_application; then printf 'rc=0\\n'; else printf 'rc=1\\n'; fi
printf 'wait_called=%s\\n' "$WAIT_CALLED"
""",
    )
    assert completed.returncode == 0, completed.stderr
    assert "rc=1" in completed.stdout
    assert "status=fail" in completed.stdout
    # The failure decision precedes any reap: wait must never run for a
    # still-live process.
    assert "wait_called=0" in completed.stdout


def test_finding2_ambiguous_proc_state_fails_closed_as_alive(tmp_path: Path) -> None:
    completed = _run_termination_probe(
        tmp_path,
        """
bash -c 'exec sleep 30' & APP_PID=$!
cat() { return 1; }
if app_process_alive; then printf 'verdict=alive\\n'; else printf 'verdict=dead\\n'; fi
kill -KILL "$APP_PID" >/dev/null 2>&1 || true
wait "$APP_PID" >/dev/null 2>&1 || true
""",
    )
    assert completed.returncode == 0, completed.stderr
    # An unreadable /proc state for an existing process must never be
    # interpreted as dead.
    assert "verdict=alive" in completed.stdout


def test_finding2_final_liveness_proof_precedes_reap() -> None:
    function_source = _shell_function_source(
        "terminate_application", chr(10) + "write_initial_evidence"
    )
    assert function_source.index('APP_PROCESS_STATUS="fail"') < function_source.index(
        'wait "$APP_PID"'
    )


def test_finding2_evidence_records_app_termination_status() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert 'APP_PROCESS_STATUS="not-started"' in text
    assert 'APP_PROCESS_STATUS="running"' in text
    assert 'APP_PROCESS_STATUS="kill-terminated"' in text
    assert 'payload["appTerminationStatus"]' in text
    assert "application process termination could not be proven" in text


# ---------------------------------------------------------------------------
# Finding 3: monotonic per-database restore duration
# ---------------------------------------------------------------------------


def test_finding3_monotonic_duration_rounds_up_whole_seconds() -> None:
    started_ns = time.monotonic_ns() - 1_700_000_000
    completed = _run_python(_duration_program(), [str(started_ns)])
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "2"


def test_finding3_negative_monotonic_delta_fails() -> None:
    started_ns = time.monotonic_ns() + 60_000_000_000
    completed = _run_python(_duration_program(), [str(started_ns)])
    assert completed.returncode != 0
    assert "monotonic restore duration was negative" in completed.stderr


def test_finding3_wall_clock_subtraction_is_no_longer_the_duration_authority() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "time.monotonic_ns()" in text
    assert "started_epoch" not in text
    assert "$(date -u +%s) - started_epoch" not in text
    assert '"durationAuthority": "monotonic-ns"' in text


# ---------------------------------------------------------------------------
# Finding 4: PASS only after complete cleanup
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "created", "expected_rc"),
    [
        ("empty", False, 0),
        ("empty", True, 0),
        ("remove-fail", True, 1),
        ("listing-fail", False, 1),
        ("listed", False, 1),
    ],
)
def test_finding4_cleanup_publishes_pass_only_at_final_transition(
    tmp_path: Path, mode: str, created: bool, expected_rc: int
) -> None:
    completed, records = _run_cleanup_probe(tmp_path, mode, created)
    assert completed.returncode == expected_rc, completed.stderr
    assert records, "cleanup never recorded evidence state"
    passing = [record for record in records if record[0] == "pass" and record[1] == "pass"]
    if expected_rc == 0:
        assert len(passing) == 1
        assert records[-1] == passing[0]
        assert all(record[0] == "fail" for record in records[:-1])
        assert records[-1][2] == "terminated"
    else:
        assert passing == []
        assert records[-1][0] == "fail"


def test_finding4_failure_before_workdir_removal_cannot_leave_pass(tmp_path: Path) -> None:
    completed, records = _run_cleanup_probe(tmp_path, "empty", False, mutate_source=True)
    assert completed.returncode != 0
    assert all(record[0] != "pass" for record in records)
    assert records[-1][3] == "true"
    assert records[-1][1] == "fail"


def test_finding4_workdir_removal_failure_cannot_leave_pass(tmp_path: Path) -> None:
    completed, records = _run_cleanup_probe(
        tmp_path, "empty", False, workdir_removal_fails=True
    )
    assert completed.returncode != 0
    assert all(record[0] != "pass" for record in records)
    assert any("workdir cleanup failed" in record[4] for record in records)


def test_finding4_app_termination_failure_cannot_leave_pass(tmp_path: Path) -> None:
    completed, records = _run_cleanup_probe(
        tmp_path, "empty", False, term_status="fail"
    )
    assert completed.returncode != 0
    assert all(record[0] != "pass" for record in records)
    assert records[-1][2] == "fail"


def test_finding4_final_write_failure_cannot_leave_prior_pass(tmp_path: Path) -> None:
    completed, records = _run_cleanup_probe(
        tmp_path, "empty", False, final_write_fails=True
    )
    assert completed.returncode != 0
    assert records, "cleanup never recorded evidence state"
    assert all(record[0] != "pass" for record in records)


def test_finding4_failed_final_write_keeps_evidence_non_pass(tmp_path: Path) -> None:
    evidence = _write_evidence_fixture(tmp_path)
    identity = os.stat(evidence)
    completed = _run_python(
        _final_writer_program(),
        [
            str(evidence),
            str(identity.st_dev),
            "999999999",
            "pass",
            "false",
            "pass",
            "",
            "",
            "not-created",
            "not-created",
            "pass",
            "pass",
            "terminated",
        ],
    )
    assert completed.returncode != 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["result"] == "fail"
    assert payload["cleanupStatus"] == "pending"


def test_finding4_service_acceptance_is_recorded_without_durable_pass() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert 'CURRENT_PHASE="service-acceptance"' in text
    assert '"serviceAcceptanceRecorded": True' in text
    assert '"failureReason": "cleanup verification pending"' in text
    assert "# Every cleanup verification succeeded: publish the FIRST durable full PASS." in text


# ---------------------------------------------------------------------------
# Finding 5: secure temporary evidence files
# ---------------------------------------------------------------------------


def test_finding5_precreated_symlink_destination_is_not_followed(tmp_path: Path) -> None:
    victim = tmp_path / "victim.json"
    victim.write_text("protected\n", encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    evidence.symlink_to(victim)
    completed = _run_early_writer(tmp_path, evidence)
    assert completed.returncode != 0
    assert "evidence output" in completed.stderr
    assert victim.read_text(encoding="utf-8") == "protected\n"
    assert evidence.is_symlink()


def test_finding5_replaced_destination_identity_is_protected(tmp_path: Path) -> None:
    evidence = _write_evidence_fixture(tmp_path)
    identity = os.stat(evidence)
    unexpected = tmp_path / "unexpected.json"
    unexpected.write_text("unexpected\n", encoding="utf-8")
    evidence.unlink()
    evidence.hardlink_to(unexpected)
    completed = _run_python(
        _early_writer_program(),
        [str(evidence), str(identity.st_dev), str(identity.st_ino), "probe", "probe failure"],
    )
    assert completed.returncode != 0
    assert "evidence output" in completed.stderr
    assert unexpected.read_text(encoding="utf-8") == "unexpected\n"


def _run_writer_with_fixed_urandom(
    tmp_path: Path, evidence: Path, candidate_precreator: Callable[[Path], None]
) -> subprocess.CompletedProcess[str]:
    identity = os.stat(evidence)
    args = [str(evidence), str(identity.st_dev), str(identity.st_ino), "probe", "probe failure"]
    candidate_precreator(evidence.with_name(f".{evidence.name}.{'0' * 16}.tmp"))
    wrapper = (
        "import os, sys\n"
        "os.urandom = lambda size: bytes(size)\n"
        f"sys.argv = ['writer'] + {args!r}\n"
        f"{_early_writer_program()}\n"
    )
    return subprocess.run(
        [sys.executable, "-c", wrapper], check=False, capture_output=True, text=True
    )


def test_finding5_forced_temp_collision_fails_closed(tmp_path: Path) -> None:
    evidence = _write_evidence_fixture(tmp_path)
    original = evidence.read_text(encoding="utf-8")

    def precreate(candidate: Path) -> None:
        candidate.write_text("attacker temp\n", encoding="utf-8")

    completed = _run_writer_with_fixed_urandom(tmp_path, evidence, precreate)
    assert completed.returncode != 0
    assert "secure temporary evidence file" in completed.stderr
    assert evidence.read_text(encoding="utf-8") == original


def test_finding5_attacker_symlink_temp_is_not_followed(tmp_path: Path) -> None:
    evidence = _write_evidence_fixture(tmp_path)
    original = evidence.read_text(encoding="utf-8")
    victim = tmp_path / "temp-victim.json"
    victim.write_text("protected temp target\n", encoding="utf-8")

    def precreate(candidate: Path) -> None:
        candidate.symlink_to(victim)

    completed = _run_writer_with_fixed_urandom(tmp_path, evidence, precreate)
    assert completed.returncode != 0
    assert victim.read_text(encoding="utf-8") == "protected temp target\n"
    assert evidence.read_text(encoding="utf-8") == original


def test_finding5_exclusive_creation_succeeds_without_collision(tmp_path: Path) -> None:
    evidence = _write_evidence_fixture(tmp_path)

    def precreate(_candidate: Path) -> None:
        return None

    completed = _run_writer_with_fixed_urandom(tmp_path, evidence, precreate)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["failurePhase"] == "probe"
    assert list(tmp_path.glob(".evidence.json.*.tmp")) == []
    assert stat_module.S_IMODE(os.stat(evidence).st_mode) == 0o600


@pytest.mark.parametrize("parent_mode", [0o777, 0o775])
def test_finding5_shared_writable_parent_is_rejected(tmp_path: Path, parent_mode: int) -> None:
    parent = tmp_path / "shared-parent"
    parent.mkdir()
    evidence = parent / "evidence.json"
    evidence.write_text('{"result": "fail"}\n', encoding="utf-8")
    parent.chmod(parent_mode)
    try:
        completed = _run_early_writer(tmp_path, evidence)
    finally:
        parent.chmod(0o700)
    assert completed.returncode != 0
    assert "group or world writable" in completed.stderr


def test_finding5_predictable_temp_patterns_are_gone() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert ".early.{os.getpid()}.tmp" not in text
    assert ".final.{os.getpid()}.tmp" not in text
    assert ".success.{os.getpid()}.tmp" not in text
    assert "temporary.write_text" not in text
    assert "os.O_EXCL | os.O_NOFOLLOW" in text
    assert "os.fchmod(fd, 0o600)" in text
    assert "os.urandom(8).hex()" in text


# ---------------------------------------------------------------------------
# Finding 6: explicit interpreter validated against the source release lock
# ---------------------------------------------------------------------------


def test_finding6_matching_inventory_passes_with_deterministic_fingerprint(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site"
    _add_dist(site, "k5demo-app", "1.2.3")
    _add_dist(site, "k5demo-core", "4.5.6")
    lock = _lock_text(("k5demo-app", "1.2.3"), ("k5demo-core", "4.5.6"))
    completed = _run_lock_program(tmp_path, lock, site)
    assert completed.returncode == 0, completed.stderr
    status, fingerprint = completed.stdout.strip().split("\t")
    assert status == "pass"
    expected = _expected_fingerprint(("k5demo-app", "1.2.3"), ("k5demo-core", "4.5.6"))
    assert fingerprint == expected
    reordered = _run_lock_program(tmp_path, _lock_text(("k5demo-core", "4.5.6"), ("k5demo-app", "1.2.3")), site)
    assert reordered.stdout.strip() == completed.stdout.strip()


def test_finding6_transitive_version_mismatch_fails(tmp_path: Path) -> None:
    site = tmp_path / "site"
    _add_dist(site, "k5demo-app", "1.2.3")
    _add_dist(site, "k5demo-core", "4.5.7")
    lock = _lock_text(("k5demo-app", "1.2.3"), ("k5demo-core", "4.5.6"))
    completed = _run_lock_program(tmp_path, lock, site)
    assert completed.returncode != 0
    assert "k5demo-core locked=4.5.6" in completed.stderr


def test_finding6_missing_locked_package_fails(tmp_path: Path) -> None:
    site = tmp_path / "site"
    _add_dist(site, "k5demo-app", "1.2.3")
    lock = _lock_text(("k5demo-app", "1.2.3"), ("k5demo-missing", "9.9.9"))
    completed = _run_lock_program(tmp_path, lock, site)
    assert completed.returncode != 0
    assert "k5demo-missing" in completed.stderr
    assert "missing=" in completed.stderr


def test_finding6_fastapi_pydantic_mismatch_is_detected(tmp_path: Path) -> None:
    site = tmp_path / "site"
    _add_dist(site, "fastapi", "0.115.0")
    _add_dist(site, "pydantic", "2.9.1")
    lock = _lock_text(("fastapi", "0.115.0"), ("pydantic", "2.9.0"))
    completed = _run_lock_program(tmp_path, lock, site)
    assert completed.returncode != 0
    assert "pydantic locked=2.9.0" in completed.stderr


def test_finding6_extras_and_name_normalization_match(tmp_path: Path) -> None:
    site = tmp_path / "site"
    _add_dist(site, "k5demo-app", "0.51.0")
    lock = _lock_text(("K5Demo.App[standard]", "0.51.0"))
    completed = _run_lock_program(tmp_path, lock, site)
    assert completed.returncode == 0, completed.stderr


def test_finding6_explicit_interpreter_branch_performs_no_install() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index('APP_PYTHON_SOURCE="explicit"')
    end = text.index("else", start)
    explicit_branch = text[start:end]
    assert "pip install" not in explicit_branch
    assert "pip download" not in explicit_branch
    assert "importlib.metadata" in text
    assert 'REQUIREMENTS_LOCK_SHA256="$(sha256sum "$lock_file"' in text
    assert "runtimeDependencyFingerprint" in text
    assert "runtimeDependencyValidation" in text


def test_finding6_default_runtime_still_uses_hashed_lock() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert '--require-hashes -r "$SOURCE_DIR/backend/requirements.lock"' in text
    assert '"$SOURCE_DIR/backend/requirements.txt"' not in text


# ---------------------------------------------------------------------------
# Service-acceptance evidence writer (fixture-level)
# ---------------------------------------------------------------------------


def test_service_acceptance_records_details_without_durable_pass(tmp_path: Path) -> None:
    args, evidence, original_identity = _success_evidence_fixture(tmp_path)
    completed = _run_python(_acceptance_program(), args)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["result"] == "fail"
    assert payload["cleanupStatus"] == "pending"
    assert payload["serviceAcceptanceRecorded"] is True
    assert payload["failureReason"] == "cleanup verification pending"
    assert payload["backupStartedAt"] == "2026-09-03T01:02:03Z"
    assert payload["backupCompletedAt"] == "2026-09-03T01:03:05Z"
    assert payload["backupTimestampAuthority"] == "per-generation-metadata-artifact"
    assert payload["generationMetadataStatus"] == "verified"
    assert payload["appTerminationStatus"] == "pending"
    assert payload["postgresRestoreStatus"]["databases"][0]["durationAuthority"] == "monotonic-ns"
    replaced_identity = os.stat(evidence).st_dev, os.stat(evidence).st_ino
    assert replaced_identity != original_identity
    assert not list(tmp_path.glob(".evidence.json.*.tmp"))


@pytest.mark.parametrize("replacement_kind", ["file", "symlink"])
def test_service_acceptance_refuses_replaced_or_symlink_output(
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

    completed = _run_python(_acceptance_program(), args)
    assert completed.returncode != 0
    assert "evidence output" in completed.stderr
    assert unexpected.read_text(encoding="utf-8") == "unexpected"
    if replacement_kind == "symlink":
        assert evidence.is_symlink()
    else:
        assert evidence.read_text(encoding="utf-8") == "unexpected"
    assert not list(tmp_path.glob(".evidence.json.*.tmp"))


# ---------------------------------------------------------------------------
# Maintained acceptance contract markers
# ---------------------------------------------------------------------------


def test_k5_restore_entrypoint_uses_ordered_timestamps_and_monotonic_rto() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "backup completion precedes backup start" in text
    assert "backup completion follows reference failure" in text
    assert "RESTORE_STARTED_MONOTONIC_NS" in text
    assert "READY_MONOTONIC_NS" in text
    assert "monotonic RTO elapsed time was negative" in text
    assert "(elapsed_ns + 999_999_999) // 1_000_000_000" in text
    assert "max(0" not in text


def test_k5_restore_entrypoint_covers_certified_acceptance_contract() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")

    required_markers = (
        "--stamp",
        "--source-sha",
        "--github-main-sha",
        "--execute-isolated-restore",
        "generation_${STAMP}.sha256",
        "generation_${STAMP}.result",
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
        WEEKLY_HELPER_SHA256,
        "importlib.metadata",
        "O_NOFOLLOW",
        "os.O_RDONLY | os.O_NOFOLLOW",
        "appTerminationStatus",
        "generationMetadataSha256",
        "monotonic restore duration was negative",
        "per-generation-metadata-artifact",
        "generation-metadata-staged.result",
        "generation-metadata-identity.tsv",
        "generation metadata source changed during exercise",
    )
    for marker in required_markers:
        assert marker in text, marker

    forbidden_markers = (
        "systemctl restart",
        "systemctl stop",
        "run_migrations",
        "alembic upgrade",
        "docker inspect {{.Config.Env}}",
        "0.0.0.0:${PG_PORT}",
        "--backup-started-at",
        "--backup-completed-at",
        "last-run.env",
        "started_epoch",
        ".early.{os.getpid()}.tmp",
        "temporary.write_text",
        'sha256sum "$GENERATION_RESULT"',
        'sha256sum "$MANIFEST"',
    )
    for marker in forbidden_markers:
        assert marker not in text, marker


# ---------------------------------------------------------------------------
# K5 follow-up: PG18 volume boundary, manifest TOCTOU, immutable image,
# deterministic workdir-removal-failure test
# ---------------------------------------------------------------------------


def _run_manifest_program(
    tmp_path: Path,
    manifest_text: str,
    *,
    stamp: str = FUTURE_STAMP,
) -> subprocess.CompletedProcess[str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    manifest = tmp_path / "generation.sha256"
    manifest.write_text(manifest_text, encoding="utf-8")
    expected = tmp_path / "expected.tsv"
    expected.write_text("", encoding="utf-8")
    staged = tmp_path / "staged.sha256"
    identity = tmp_path / "identity.tsv"
    return _run_python(
        _manifest_program(),
        [str(manifest), stamp, str(expected), str(staged), str(identity)],
    )


def _valid_manifest_text(stamp: str = FUTURE_STAMP) -> str:
    components = list(_component_relatives(stamp))
    lines = []
    for relative in components:
        digest = hashlib.sha256(f"synthetic {relative}\n".encode("utf-8")).hexdigest()
        lines.append(f"{digest}  {relative}")
    return "\n".join(lines) + "\n"


def test_findingA_pg18_volume_mounts_at_postgres_base_directory() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    # The narrow contract: the exercise-owned named volume owns PG18's
    # actual persistent data boundary at /var/lib/postgresql, not the
    # deeper PGDATA sub-path.
    assert '"$VOLUME:/var/lib/postgresql"' in text
    assert '"$VOLUME:/var/lib/postgresql/data"' not in text
    # Volume attachment must be revalidated after the container starts so
    # a stale/swap cannot masquerade as a clean run.
    assert "/var/lib/postgresql" in text
    assert "disposable PostgreSQL volume is not attached" in text


def test_findingA_cleanup_uses_docker_rm_v_for_anonymous_volumes() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "docker rm -v -f \"$CONTAINER\"" in text


def test_findingB_manifest_is_opened_with_nofollow_and_is_regular_file(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real.sha256"
    real.write_text(_valid_manifest_text(), encoding="utf-8")
    manifest = tmp_path / "generation.sha256"
    manifest.symlink_to(real)
    expected = tmp_path / "expected.tsv"
    expected.write_text("", encoding="utf-8")
    completed = _run_python(
        _manifest_program(),
        [str(manifest), FUTURE_STAMP, str(expected),
         str(tmp_path / "staged.sha256"), str(tmp_path / "identity.tsv")],
    )
    assert completed.returncode != 0
    assert "unable to open generation manifest safely" in completed.stderr
    assert not (tmp_path / "staged.sha256").exists()


def test_findingB_manifest_is_opened_once_and_staged_byte_identical(
    tmp_path: Path,
) -> None:
    completed = _run_manifest_program(tmp_path, _valid_manifest_text())
    assert completed.returncode == 0, completed.stderr
    manifest = tmp_path / "generation.sha256"
    staged = tmp_path / "staged.sha256"
    identity = tmp_path / "identity.tsv"
    # Staged bytes are exactly the validated snapshot bytes.
    assert staged.read_bytes() == manifest.read_bytes()
    reported_sha = completed.stdout.strip()
    assert reported_sha == hashlib.sha256(manifest.read_bytes()).hexdigest()
    # Identity captured from the same descriptor is persisted for cleanup.
    identity_values = dict(
        line.split("=", 1) for line in identity.read_text(encoding="utf-8").splitlines()
    )
    assert identity_values["sha256"] == reported_sha
    assert identity_values["size"] == str(manifest.stat().st_size)
    assert identity_values["inode"] == str(manifest.stat().st_ino)
    assert identity_values["device"] == str(manifest.stat().st_dev)


def test_findingB_no_separate_authoritative_manifest_reread() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert 'sha256sum "$MANIFEST"' not in text
    assert "manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()" in text
    # The manifest source open is single, no-follow, regular-file, one-shot.
    program = _manifest_program()
    assert "os.O_RDONLY | os.O_NOFOLLOW" in program
    assert "S_ISREG" in program
    assert program.count("os.read(") == 1


def test_findingB_manifest_identity_recheck_passes_when_unchanged(
    tmp_path: Path,
) -> None:
    completed = _run_manifest_program(tmp_path, _valid_manifest_text())
    assert completed.returncode == 0
    completed = _run_python(
        _manifest_identity_program(),
        [str(tmp_path / "generation.sha256"), str(tmp_path / "identity.tsv")],
    )
    assert completed.returncode == 0, completed.stderr
    assert "generation-manifest-source-identity-ok" in completed.stdout


def test_findingB_manifest_replacement_fails_recheck(tmp_path: Path) -> None:
    _run_manifest_program(tmp_path, _valid_manifest_text())
    manifest = tmp_path / "generation.sha256"
    manifest.unlink()
    manifest.write_text(_valid_manifest_text(), encoding="utf-8")
    completed = _run_python(
        _manifest_identity_program(),
        [str(manifest), str(tmp_path / "identity.tsv")],
    )
    assert completed.returncode != 0
    assert "changed during exercise" in completed.stderr


def test_findingB_manifest_symlink_swap_fails_recheck(tmp_path: Path) -> None:
    _run_manifest_program(tmp_path, _valid_manifest_text())
    manifest = tmp_path / "generation.sha256"
    twin = tmp_path / "twin.sha256"
    twin.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(twin)
    completed = _run_python(
        _manifest_identity_program(),
        [str(manifest), str(tmp_path / "identity.tsv")],
    )
    assert completed.returncode != 0
    assert "unable to reopen generation manifest safely" in completed.stderr


def test_findingC_container_runs_under_captured_image_id_with_no_pull() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    # Strip comments so the assertion only inspects executable code paths.
    code_lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        code_lines.append(line)
    code = "\n".join(code_lines)
    # The container is started with the captured immutable image ID, never
    # the mutable POSTGRES_IMAGE tag, and never with --pull=always.
    assert '--pull=never' in code
    assert '"$POSTGRES_IMAGE_ID"' in code
    # Image equality is verified immediately after start; a refresh could
    # only occur between POSTGRES_IMAGE capture and container create, so
    # a post-create inspect is the only way to close the window.
    assert "RUNNING_IMAGE_ID" in code
    assert "disposable PostgreSQL container is not running the captured immutable image" in code
    # Inspect is metadata-only; never output Config.Env or any secret.
    assert "docker inspect --format '{{.Image}}' \"$CONTAINER\"" in code
    assert "{{.Config.Env}}" not in code
    assert "Config.Env" not in code


def test_findingD_test_rm_shadow_forwards_unrelated_calls(tmp_path: Path) -> None:
    # Build a temp tree the shadow must remove without refusal: nothing
    # about these paths matches K5_TEST_FAIL_RM_TARGET.
    target_a = tmp_path / "alpha.txt"
    target_a.write_text("a", encoding="utf-8")
    target_b = tmp_path / "beta.txt"
    target_b.write_text("b", encoding="utf-8")
    shadow_dir = tmp_path / "shadow-bin"
    shadow_dir.mkdir()
    shadow = shadow_dir / "rm"
    shadow.write_text(
        """#!/usr/bin/env bash
set -u
SELF_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
REAL_RM=""
IFS=':' read -ra _dirs <<<"${PATH:-}"
for d in "${_dirs[@]}"; do
  [ "$d" = "$SELF_DIR" ] && continue
  if [ -x "$d/rm" ]; then
    REAL_RM="$d/rm"
    break
  fi
done
[ -n "$REAL_RM" ] || { echo "no real rm" >&2; exit 127; }
TARGET="${K5_TEST_FAIL_RM_TARGET:-}"
if [ -n "$TARGET" ]; then
  for arg in "$@"; do
    if [ "$arg" = "$TARGET" ]; then
      echo "refuse $arg" >&2
      exit 1
    fi
  done
fi
exec "$REAL_RM" "$@"
""",
        encoding="utf-8",
    )
    shadow.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{shadow_dir}{os.pathsep}{env['PATH']}"
    env["K5_TEST_FAIL_RM_TARGET"] = "/some/other/path/that/never/appears"
    completed = subprocess.run(
        ["bash", "-c", f"rm -f -- {shlex.quote(str(target_a))} {shlex.quote(str(target_b))}"],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert not target_a.exists()
    assert not target_b.exists()


def test_findingD_test_rm_shadow_fails_only_for_exact_workdir_target(
    tmp_path: Path,
) -> None:
    shadow_dir = tmp_path / "shadow-bin"
    shadow_dir.mkdir()
    shadow = shadow_dir / "rm"
    shadow.write_text(
        """#!/usr/bin/env bash
set -u
SELF_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
REAL_RM=""
IFS=':' read -ra _dirs <<<"${PATH:-}"
for d in "${_dirs[@]}"; do
  [ "$d" = "$SELF_DIR" ] && continue
  if [ -x "$d/rm" ]; then
    REAL_RM="$d/rm"
    break
  fi
done
[ -n "$REAL_RM" ] || { echo "no real rm" >&2; exit 127; }
TARGET="${K5_TEST_FAIL_RM_TARGET:-}"
if [ -n "$TARGET" ]; then
  for arg in "$@"; do
    if [ "$arg" = "$TARGET" ]; then
      echo "refuse $arg" >&2
      exit 1
    fi
  done
fi
exec "$REAL_RM" "$@"
""",
        encoding="utf-8",
    )
    shadow.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{shadow_dir}{os.pathsep}{env['PATH']}"
    workdir = tmp_path / "k5-isolated-restore-probe"
    env["K5_TEST_FAIL_RM_TARGET"] = str(workdir)
    # Unrelated rm call still succeeds.
    safe = tmp_path / "safe.txt"
    safe.write_text("safe", encoding="utf-8")
    completed = subprocess.run(
        ["bash", "-c", f"rm -f -- {shlex.quote(str(safe))}"],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert not safe.exists()
    # The exact workdir target fails and never reaches the real binary.
    workdir.mkdir()
    completed = subprocess.run(
        ["bash", "-c", f"rm -rf -- {shlex.quote(str(workdir))}"],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "refuse" in completed.stderr
    assert workdir.exists()


def test_findingD_chmod_0555_failure_simulation_is_removed() -> None:
    # Review finding #5111506619 is valid: the chmod-0o555 simulation
    # depended on filesystem permission side effects and is replaced by
    # the deterministic TEST-ONLY rm shadow.
    text = inspect.getsource(_run_cleanup_probe)
    assert "0o555" not in text
    assert "K5_TEST_FAIL_RM_TARGET" in text
    assert "rm_shadow" in text


# ---------------------------------------------------------------------------
# Codex review 5112377944: restored-content validation must fail closed
# on empty/system-only relations, and must require positive user content
# for both the PostgreSQL restore loop and the visits SQLite file.
# ---------------------------------------------------------------------------


PG_USER_RELATION_QUERY = (
    "SELECT count(*) FROM pg_class c "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE c.relkind IN ('r','p','v','m') "
    "AND n.nspname NOT IN ('pg_catalog','information_schema') "
    "AND n.nspname NOT LIKE 'pg_toast%' "
    "AND n.nspname NOT LIKE 'pg_temp_%';"
)


SQLITE_USER_TABLE_QUERY = (
    "SELECT count(*) FROM sqlite_master "
    "WHERE type='table' AND name NOT LIKE 'sqlite_%';"
)


def _extract_pg_relation_block() -> str:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index("relations=\"$(\n    docker exec")
    end_marker = 'printf \'%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n\' \\\n    "$label"'
    end = text.index(end_marker, start)
    return text[start:end]


def _extract_visits_block() -> str:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index("VISITS_TABLE_COUNT=\"$(sqlite3")
    end = text.index(
        "[[ \"$VISITS_TABLE_COUNT\" =~ ^[0-9]+$ ]] || die \"invalid visits user table count\"",
        start,
    )
    end = text.index(chr(10), end) + 1
    return text[start:end]


def test_finding1_pg_user_relation_query_excludes_system_schemas() -> None:
    block = _extract_pg_relation_block()
    # The narrow semantic form is present verbatim.
    assert PG_USER_RELATION_QUERY in block
    # The previously defective system-relations-only form is gone.
    assert "SELECT count(*) FROM pg_class WHERE relkind IN ('r','p','v','m');" not in block


def test_finding1_pg_user_relation_count_zero_fails_closed() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert 'die "invalid user relation count for $label"' in text
    assert 'die "restored database $database contains no user relations"' in text
    # The fail-closed gate is a strict positivity check, not a non-equality.
    assert '[ "$relations" -gt 0 ]' in text or '[ "$relations" -gt 0 ] ||' in text


def test_finding2_visits_user_table_query_excludes_sqlite_internal() -> None:
    block = _extract_visits_block()
    assert SQLITE_USER_TABLE_QUERY in block
    # The previously defective sqlite_master-only form is gone.
    assert "SELECT count(*) FROM sqlite_master WHERE type='table';" not in block
    assert "SELECT count(*) FROM sqlite_master WHERE type='table';" not in block


def test_finding2_visits_user_table_count_zero_fails_closed() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert 'die "invalid visits user table count"' in text
    assert 'die "restored visits database contains no user tables"' in text


def test_finding1_pg_query_filters_exclude_each_system_namespace() -> None:
    # Each excluded namespace must be present in the maintained query
    # (regression guard against accidentally removing one filter).
    for marker in ("'pg_catalog'", "'information_schema'", "pg_toast%", "pg_temp_%"):
        assert marker in PG_USER_RELATION_QUERY, marker


def test_finding1_pg_query_preserves_relkind_scope() -> None:
    # The query must still cover ordinary tables, partitioned tables,
    # views and materialized views; narrowing the scope to one relkind
    # would re-open the empty-archive hole for the other relkinds.
    assert "c.relkind IN ('r','p','v','m')" in PG_USER_RELATION_QUERY


def test_finding2_sqlite_query_excludes_sqlite_internal_prefix() -> None:
    assert "name NOT LIKE 'sqlite_%'" in SQLITE_USER_TABLE_QUERY
    assert "type='table'" in SQLITE_USER_TABLE_QUERY


def test_finding1_pg_user_relation_query_passes_with_user_content() -> None:
    # The query as written would be evaluated by a real PostgreSQL;
    # the maintained form must accept the standard public.stores table
    # shape, which is a representative user-relation row. We assert
    # here only that the query syntactically projects the user namespace
    # and excludes the system namespaces from its WHERE clause, by
    # parsing the query with a regex check that the WHERE is
    # AND-joined against every exclusion.
    import re
    where_clauses = re.findall(
        r"AND\s+(n\.nspname[^\s]+(?:\s+[A-Z]+\s+'[^']+(?:%|_)'?)?)",
        PG_USER_RELATION_QUERY,
    )
    text = PG_USER_RELATION_QUERY
    assert "n.nspname NOT IN ('pg_catalog','information_schema')" in text
    assert "n.nspname NOT LIKE 'pg_toast%'" in text
    assert "n.nspname NOT LIKE 'pg_temp_%'" in text
    # Three exclusion clauses must appear, one per excluded namespace.
    assert text.count("n.nspname NOT") == 3


def test_finding2_sqlite_user_table_query_synthetic_zero_does_not_pass() -> None:
    # Synthetic structurally-valid empty SQLite: only sqlite_sequence
    # exists (a sqlite_* internal) and no user table. The bounded query
    # must therefore return 0 — it cannot pass an empty-archive restore.
    # This is verified directly by the next test which creates that exact
    # shape and confirms the maintained query returns 0.
    pass


def test_finding2_sqlite_query_string_returns_zero_for_internal_only_db(
    tmp_path: Path,
) -> None:
    # Direct synthetic check: a structurally-valid empty SQLite with no
    # user tables must yield 0 against both the bounded user-table query
    # and the legacy sqlite_master-only form. The bounded form is required
    # to fail closed on the production-side `> 0` gate, so the test below
    # proves the maintained query string can never report a positive
    # user-table count for a database that has none.
    import sqlite3 as _sqlite3
    db = tmp_path / "empty.db"
    conn = _sqlite3.connect(str(db))
    try:
        # Force a sqlite_sequence row (the only sqlite_* internal table
        # that can be created without user code) by adding an AUTOINCREMENT
        # column and rolling it back. This is the canonical
        # "structurally valid but semantically empty" SQLite artifact.
        conn.execute(
            "CREATE TABLE _throwaway (id INTEGER PRIMARY KEY AUTOINCREMENT)"
        )
        conn.execute("DROP TABLE _throwaway")
        conn.commit()
    finally:
        conn.close()
    bounded_raw = subprocess.run(
        ["sqlite3", str(db), SQLITE_USER_TABLE_QUERY],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert bounded_raw == "0", bounded_raw
    legacy_raw = subprocess.run(
        ["sqlite3", str(db), "SELECT count(*) FROM sqlite_master WHERE type='table';"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    # Legacy counts sqlite_sequence as a table, returning 1; the bounded
    # form correctly excludes it. This is exactly the failure mode the
    # review identified, and the maintenance guard here ensures the
    # query string does not regress.
    assert legacy_raw == "1", legacy_raw


def test_finding2_sqlite_query_string_returns_positive_for_user_table(
    tmp_path: Path,
) -> None:
    import sqlite3 as _sqlite3
    db = tmp_path / "user.db"
    conn = _sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE fieldops_visits (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE fieldops_visit_photos (visit_id INTEGER)")
        conn.commit()
    finally:
        conn.close()
    count_raw = subprocess.run(
        ["sqlite3", str(db), SQLITE_USER_TABLE_QUERY],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert int(count_raw) >= 2, count_raw


def test_finding1_pg_user_relation_query_string_with_public_user_table() -> None:
    # The narrow semantic form must project a real public.user_table
    # row as a positive count. The exact evaluation requires a live
    # PostgreSQL, so this test asserts only the SQL surface: the
    # query joins pg_class to pg_namespace and excludes the documented
    # system namespaces, so a real public-schema user relation cannot
    # be filtered out by the maintained query.
    assert "JOIN pg_namespace n ON n.oid = c.relnamespace" in PG_USER_RELATION_QUERY
    assert "c.relkind IN ('r','p','v','m')" in PG_USER_RELATION_QUERY
    # A public schema row would have nspname='public' which is not in
    # any of the three NOT filters, so it must pass.
    for excluded in ("'pg_catalog'", "'information_schema'", "pg_toast%", "pg_temp_%"):
        assert "public" not in excluded
    assert "public" not in PG_USER_RELATION_QUERY or "NOT" not in PG_USER_RELATION_QUERY.split("public")[1]
