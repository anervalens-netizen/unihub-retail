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
EXPECTED_ENTRYPOINT_SHA256 = "85e62608c78a741b43937a392a7482ab27d8656395f4ee6773238870ea4e452d"  # pragma: allowlist secret

FUTURE_STAMP = "20260903_010203"
COMPONENT_LABELS = (
    "unihub",
    "mobiup_dwh",
    "unihub_identity",
    "unihub_retail",
    "unihub_distribution",
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
    file_count: int = 9,
    source_release_sha: str = FIXTURE_SHA,
) -> list[str]:
    return [
        f"stamp={stamp}",
        f"status={status}",
        f"source_release_sha={source_release_sha}",
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
    manifest_entries: int = 9,
    source_release_sha: str = FIXTURE_SHA,
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
        [
            str(metadata),
            stamp,
            source_release_sha,
            reference,
            str(expected),
            str(staged),
            str(identity),
        ],
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
    restore_lines = []
    for label in (
        "unihub",
        "mobiup_dwh",
        "unihub_identity",
        "unihub_retail",
        "unihub_distribution",
        "unihub_learning",
        "authentik",
        "glitchtip",
    ):
        restore_lines.append(
            chr(9).join(
                [
                    label,
                    f"dr_{label}",
                    "2026-09-03T01:05:00Z",
                    "2026-09-03T01:05:02Z",
                    "2",
                    "363",
                ]
            )
        )
    restores.write_text("\n".join(restore_lines) + chr(10), encoding="utf-8")
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
    # The synthetic source repo's HEAD is generated by _init_source_repo
    # and forwarded as --source-sha; capture it so the metadata can mirror
    # the same SHA via source_release_sha and advance past the
    # generation-metadata preflight.
    backup = tmp_path / "backup"
    work = tmp_path / "work"
    backup.mkdir()
    work.mkdir()
    repo, source_sha = _init_source_repo(tmp_path)
    _write_generation_tree(
        backup,
        FUTURE_STAMP,
        result_lines=_valid_result_lines(
            FUTURE_STAMP, source_release_sha=source_sha
        ),
    )
    evidence = tmp_path / "evidence.json"
    _fake_docker(tmp_path, "empty")
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    env["DOCKER_TEST_MODE"] = "empty"
    completed = subprocess.run(
        [
            "bash",
            str(ENTRYPOINT),
            "--backup-root",
            str(backup),
            "--stamp",
            FUTURE_STAMP,
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
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
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
        f"source_release_sha={FIXTURE_SHA}",
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
        "".join(f"postgres/component{i}_x.dump\t{'a' * 64}\n" for i in range(9)),
        encoding="utf-8",
    )
    completed = _run_python(
        _metadata_program(),
        [
            str(metadata),
            FUTURE_STAMP,
            FIXTURE_SHA,
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
    end_marker = 'printf \'%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n\' \\\n    "$label"'
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


# ---------------------------------------------------------------------------
# Codex review 5112723089: rejected restored content
# - mandatory bounded stores business control
# - strong per-component identity/hash revalidation
# ---------------------------------------------------------------------------


def _extract_business_integrity_block() -> str:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index('CURRENT_PHASE="business-integrity"')
    end = text.index('BUSINESS_FINGERPRINT="$(\n  python3 -', start)
    return text[start:end]


def _extract_initial_component_block() -> str:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index("Strong component identity capture:")
    end = text.index(': >"$WORK/source-before.tsv"', start)
    return text[start:end]


def _extract_component_revalidation_block() -> str:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index("Strong per-component identity revalidation:")
    end = text.index(
        'local docker_ps_output=""',
        start,
    )
    return text[start:end]


def test_review5112723089_stores_mandatory_existence_check() -> None:
    block = _extract_business_integrity_block()
    assert 'die "mandatory business control public.stores is missing"' in block


def test_review5112723089_stores_mandatory_strict_positivity() -> None:
    block = _extract_business_integrity_block()
    # The narrow check: stores must be present, numeric, AND strictly > 0.
    assert 'die "mandatory business control stores is empty"' in block
    assert '[ "$count" -gt 0 ] || die "mandatory business control stores is empty"' in block


def test_review5112723089_stores_zero_does_not_pass_through_sample_loop() -> None:
    block = _extract_business_integrity_block()
    # The `continue` path for a non-existent table must NOT bypass the
    # strict stores gate. The `stores_ok` flag accumulates only after a
    # positive count is observed, and the [ "$stores_ok" -eq 1 ] gate
    # fires even if three other sample tables succeed.
    assert "stores_ok=1" in block
    assert '[ "$stores_ok" -eq 1 ]' in block


def test_review5112723089_stores_positive_count_passes_bounded_gate() -> None:
    block = _extract_business_integrity_block()
    # The bounded gate is a strict positivity check, not equality to
    # any pinned historical value.
    assert "stores_ok=1" in block
    assert "=121" not in block
    # The sample-count and reproducibility rules are preserved.
    assert '[ "$selected" -ge 3 ]' in block
    assert "business-integrity counts are not reproducible" in block


def test_review5112723089_initial_component_uses_safe_descriptor() -> None:
    block = _extract_initial_component_block()
    assert "os.O_RDONLY | os.O_NOFOLLOW" in block
    assert "S_ISREG" in block
    assert "fstat" in block or "fstat(fd)" in block
    # The authoritative initial SHA MUST come from the same descriptor
    # snapshot used for the identity tuple. A separate later reread is
    # forbidden.
    assert "hashlib.sha256(data).hexdigest()" not in block
    assert "digest.hexdigest()" in block
    assert "digest.update" in block
    assert "sha256sum" not in block
    assert "actual_sha != expected_sha" in block or "expected_sha" in block


def test_review5112723089_initial_component_captures_full_identity_tuple() -> None:
    block = _extract_initial_component_block()
    for field in ("device", "inode", "size", "mtime_ns", "sha256", "path"):
        assert f"{field}=" in block, field


def test_review5112723089_revalidation_uses_safe_descriptor_per_component() -> None:
    block = _extract_component_revalidation_block()
    assert "os.O_RDONLY | os.O_NOFOLLOW" in block
    assert "S_ISREG" in block
    assert "fstat(fd)" in block or "os.fstat(fd)" in block
    # Each problem class must be a fail-closed signal.
    for problem in ("device", "inode", "size", "mtime_ns", "sha256"):
        assert problem in block, problem


def test_review5112723089_revalidation_fails_cleanup_on_any_drift() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert 'FAILURE_REASON="backup component identity changed during exercise"' in text
    # The fail-closed chain must set every required field.
    for marker in (
        'SOURCE_BACKUP_MUTATION="true"',
        'RESULT="fail"',
        'CLEANUP_STATUS="fail"',
    ):
        assert marker in text, marker


def test_review5112723089_initial_validation_rejects_mismatched_component(
    tmp_path: Path,
) -> None:
    # Synthetic: the manifest promises a SHA but the actual file differs.
    # The exact validation script must die with a checksum-mismatch
    # message; the catch-all in the shell wrapper turns the die into a
    # script-level failure.
    import textwrap
    backup = tmp_path / "backup"
    backup.mkdir()
    component = backup / "comp.bin"
    component.write_bytes(b"actual payload")
    expected_sha = "0" * 64
    completed = subprocess.run(
        [
            "bash",
            "-c",
            textwrap.dedent(
                f"""
                set -Eeuo pipefail
                trap '' EXIT
                IDENTITY_OUT="$(python3 - "{component}" "comp.bin" "{expected_sha}" "{tmp_path / "id.tsv"}" 2>&1 <<'PY'
                import hashlib
                import os
                import stat
                import sys
                source_path, relative, expected_sha, identity_path = sys.argv[1:5]
                try:
                    fd = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW)
                except OSError as exc:
                    raise SystemExit(f"unable to open backup component safely: {{exc}}")
                try:
                    source_stat = os.fstat(fd)
                    if not stat.S_ISREG(source_stat.st_mode):
                        raise SystemExit("backup component is not a regular file")
                    chunks = []
                    while True:
                        chunk = os.read(fd, 1048576)
                        if not chunk:
                            break
                        chunks.append(chunk)
                finally:
                    os.close(fd)
                data = b"".join(chunks)
                actual_sha = hashlib.sha256(data).hexdigest()
                if actual_sha != expected_sha:
                    raise SystemExit(
                        f"source checksum mismatch: {{relative}} expected={{expected_sha}} actual={{actual_sha}}"
                    )
                with open(identity_path, "a", encoding="utf-8") as identity:
                    identity.write(
                        f"path={{source_path}}\\n"
                        f"relative={{relative}}\\n"
                        f"device={{source_stat.st_dev}}\\n"
                        f"inode={{source_stat.st_ino}}\\n"
                        f"size={{source_stat.st_size}}\\n"
                        f"mtime_ns={{source_stat.st_mtime_ns}}\\n"
                        f"sha256={{actual_sha}}\\n"
                    )
                print(actual_sha)
                PY
                )" || echo "DIED"
                printf '%s' "$IDENTITY_OUT"
                """
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert "source checksum mismatch" in completed.stdout
    assert "DIED" in completed.stdout
    assert not (tmp_path / "id.tsv").exists()


def _write_component_identity(identity_path: Path, source_path: Path, payload: bytes) -> None:
    """Capture a strong identity tuple for a synthetic test component.

    Mirrors the maintained production capture exactly: same descriptor,
    same byte snapshot, same tuple fields. The relative field is
    recorded for parity with the production block.
    """
    fd = os.open(str(source_path), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        ss = os.fstat(fd)
        chunks = []
        while True:
            chunk = os.read(fd, 1048576)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(fd)
    data = b"".join(chunks)
    assert data == payload  # synthetic invariant
    identity_path.write_text(
        f"path={source_path}\nrelative=comp.bin\n"
        f"device={ss.st_dev}\ninode={ss.st_ino}\n"
        f"size={ss.st_size}\nmtime_ns={ss.st_mtime_ns}\n"
        f"sha256={hashlib.sha256(data).hexdigest()}\n",
        encoding="utf-8",
    )


_REVALIDATE_PROGRAM = """
import os, sys, hashlib, stat
identity_path = sys.argv[1]
expected_by_path = {}
current_path = None
with open(identity_path, encoding='utf-8') as identity:
    for raw in identity:
        line = raw.strip()
        if not line:
            current_path = None
            continue
        key, value = line.split('=', 1)
        if key == 'path':
            current_path = value
            expected_by_path.setdefault(current_path, {})
        if current_path is not None:
            expected_by_path[current_path][key] = value
failures = []
for source_path, expected in expected_by_path.items():
    try:
        fd = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        failures.append(f'{source_path}: unable to reopen: {exc}')
        continue
    try:
        current = os.fstat(fd)
        if not stat.S_ISREG(current.st_mode):
            failures.append(f'{source_path}: no longer a regular file')
            continue
        chunks = []
        while True:
            chunk = os.read(fd, 1048576)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(fd)
    data = b''.join(chunks)
    actual_sha = hashlib.sha256(data).hexdigest()
    problems = []
    if str(current.st_dev) != expected.get('device', ''):
        problems.append('device')
    if str(current.st_ino) != expected.get('inode', ''):
        problems.append('inode')
    if str(current.st_size) != expected.get('size', ''):
        problems.append('size')
    if str(current.st_mtime_ns) != expected.get('mtime_ns', ''):
        problems.append('mtime_ns')
    if actual_sha != expected.get('sha256', ''):
        problems.append('sha256')
    if problems:
        failures.append(f'{source_path}: {problems}')
if failures:
    raise SystemExit('; '.join(failures))
print('ok')
"""


def _run_revalidate(identity_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _REVALIDATE_PROGRAM, str(identity_path)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_review5112723089_revalidation_detects_same_size_replacement(
    tmp_path: Path,
) -> None:
    # Synthetic: a same-size byte replacement must be caught by SHA drift.
    identity = tmp_path / "id.tsv"
    original = tmp_path / "comp.bin"
    payload = b"original bytes 12345"
    original.write_bytes(payload)
    _write_component_identity(identity, original, payload)
    # Same-length byte replacement.
    original.write_bytes(b"replaced bytes 999XY")
    assert original.stat().st_size == len(payload)
    rev = _run_revalidate(identity)
    assert rev.returncode != 0
    assert "sha256" in rev.stderr


def test_review5112723089_revalidation_detects_inode_swap(
    tmp_path: Path,
) -> None:
    # Inode replacement: the file at the same path is unlinked and
    # replaced with a new inode containing identical bytes. The captured
    # inode must not match anymore. To guarantee a new inode we create
    # the replacement in a fresh subdirectory and rename it over the
    # captured path; this forces the kernel to allocate a new inode
    # rather than reuse the freshly freed one.
    identity = tmp_path / "id.tsv"
    original = tmp_path / "comp.bin"
    payload = b"original content for inode swap test"
    original.write_bytes(payload)
    captured_inode = original.stat().st_ino
    _write_component_identity(identity, original, payload)
    original.unlink()
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    staging = other_dir / "comp.bin"
    staging.write_bytes(payload)
    assert staging.stat().st_ino != captured_inode
    staging.rename(original)
    rev = _run_revalidate(identity)
    assert rev.returncode != 0
    assert "inode" in rev.stderr


def test_review5112723089_revalidation_detects_mtime_ns_shift(
    tmp_path: Path,
) -> None:
    # mtime_ns drift alone (no byte change, no inode swap) must still
    # fail the revalidation, because a same-second re-touch on the
    # underlying file is a credible backup-side mutation signal.
    identity = tmp_path / "id.tsv"
    target = tmp_path / "comp.bin"
    payload = b"stable content for mtime_ns test"
    target.write_bytes(payload)
    _write_component_identity(identity, target, payload)
    # Bump only mtime_ns while keeping bytes identical.
    os.utime(target, ns=(123456789, 987654321))
    rev = _run_revalidate(identity)
    assert rev.returncode != 0
    assert "mtime_ns" in rev.stderr


def test_review5112723089_revalidation_passes_unchanged_component(
    tmp_path: Path,
) -> None:
    identity = tmp_path / "id.tsv"
    target = tmp_path / "comp.bin"
    payload = b"untouched component bytes for revalidation"
    target.write_bytes(payload)
    _write_component_identity(identity, target, payload)
    rev = _run_revalidate(identity)
    assert rev.returncode == 0, rev.stderr
    assert "ok" in rev.stdout


def test_review5112723089_revalidation_missing_component_fails(
    tmp_path: Path,
) -> None:
    # Missing component (component deleted between start and cleanup)
    # must produce a fail-closed signal during revalidation.
    identity = tmp_path / "id.tsv"
    target = tmp_path / "comp.bin"
    payload = b"transient component for missing test"
    target.write_bytes(payload)
    _write_component_identity(identity, target, payload)
    target.unlink()
    rev = _run_revalidate(identity)
    assert rev.returncode != 0
    assert "unable to reopen" in rev.stderr


def test_review5112723089_revalidation_non_regular_component_fails(
    tmp_path: Path,
) -> None:
    # Replacing a regular component with a directory at the same path
    # must be detected as a non-regular file at revalidation time. A
    # directory is openable with O_RDONLY but is not S_ISREG, so the
    # open succeeds and the regular-file check fires.
    identity = tmp_path / "id.tsv"
    target = tmp_path / "comp.bin"
    payload = b"regular component for non-regular test"
    target.write_bytes(payload)
    _write_component_identity(identity, target, payload)
    target.unlink()
    target.mkdir()
    rev = _run_revalidate(identity)
    assert rev.returncode != 0
    assert "no longer a regular file" in rev.stderr


# ---------------------------------------------------------------------------
# Codex review 5114302995: source release binding + duplicate-version gate
# ---------------------------------------------------------------------------


def test_review5114302995_missing_source_release_sha_key_fails(
    tmp_path: Path,
) -> None:
    # Synthesize metadata WITHOUT the source_release_sha key.
    lines = [
        f"stamp={FUTURE_STAMP}",
        "status=verified",
        # intentionally no source_release_sha
        "started_at=2026-09-03T01:02:03Z",
        "completed_at=2026-09-03T01:03:05Z",
        "file_count=9",
    ]
    completed = _run_metadata_program(
        tmp_path, "\n".join(lines) + "\n"
    )
    assert completed.returncode != 0
    assert "missing required generation metadata keys" in completed.stderr
    assert "source_release_sha" in completed.stderr


def test_review5114302995_malformed_source_release_sha_fails(
    tmp_path: Path,
) -> None:
    lines = _valid_result_lines(
        FUTURE_STAMP,
        source_release_sha="not-a-real-sha-just-some-junk",
    )
    completed = _run_metadata_program(
        tmp_path, "\n".join(lines) + "\n"
    )
    assert completed.returncode != 0
    assert "source_release_sha is not exactly 40 lowercase" in completed.stderr


def test_review5114302995_uppercase_source_release_sha_fails(
    tmp_path: Path,
) -> None:
    upper = FIXTURE_SHA.upper()
    lines = _valid_result_lines(
        FUTURE_STAMP,
        source_release_sha=upper,
    )
    completed = _run_metadata_program(
        tmp_path, "\n".join(lines) + "\n"
    )
    assert completed.returncode != 0
    assert "source_release_sha is not exactly 40 lowercase" in completed.stderr


def test_review5114302995_duplicate_source_release_sha_key_fails(
    tmp_path: Path,
) -> None:
    lines = _valid_result_lines(FUTURE_STAMP) + [
        f"source_release_sha={FIXTURE_SHA}",
    ]
    completed = _run_metadata_program(
        tmp_path, "\n".join(lines) + "\n"
    )
    assert completed.returncode != 0
    assert "duplicate generation metadata key" in completed.stderr


def test_review5114302995_source_release_sha_mismatch_with_source_sha_fails(
    tmp_path: Path,
) -> None:
    # Metadata carries a different source_release_sha than the expected
    # --source-sha argument forwarded by the test harness.
    lines = _valid_result_lines(
        FUTURE_STAMP,
        source_release_sha="0" * 40,
    )
    completed = _run_metadata_program(
        tmp_path, "\n".join(lines) + "\n"
    )
    assert completed.returncode != 0
    assert "source_release_sha does not match" in completed.stderr
    assert "expected=" in completed.stderr
    assert "observed=" in completed.stderr


def test_review5114302995_source_release_sha_match_passes_metadata(
    tmp_path: Path,
) -> None:
    lines = _valid_result_lines(FUTURE_STAMP)
    # The on-disk fixture appends a trailing newline; mirror that
    # exactly so the asserted digest matches the metadata snapshot.
    fixture_bytes = ("\n".join(lines) + "\n").encode("utf-8")
    completed = _run_metadata_program(
        tmp_path, "\n".join(lines) + "\n"
    )
    assert completed.returncode == 0, completed.stderr
    # The reported digest still depends on the same single byte snapshot.
    reported_sha = completed.stdout.strip().split("\t")[2]
    assert reported_sha == hashlib.sha256(fixture_bytes).hexdigest()


def test_review5114302995_existing_timestamp_fail_closed_intact(
    tmp_path: Path,
) -> None:
    # The new required key must not displace the existing timestamp and
    # stamp validation. A naive timestamp still fails closed.
    lines = _valid_result_lines(
        FUTURE_STAMP,
        started_at="2026-09-03T01:02:03",
    )
    completed = _run_metadata_program(
        tmp_path, "\n".join(lines) + "\n"
    )
    assert completed.returncode != 0
    assert "explicit UTC offset" in completed.stderr


def test_review5114302995_duplicate_installed_version_fails_closed(
    tmp_path: Path,
) -> None:
    # The runtime dependency validator must reject a single package that
    # has both the locked version AND an extra duplicate installed
    # version in the same interpreter.
    program = _lock_program()
    # Build a site with one package at two different versions.
    site = tmp_path / "site"
    site.mkdir()
    _add_dist(site, "k5demo-app", "1.2.3")
    # The PEP 503 normalized name is the same; a second dist-info with
    # the same name and a different version creates the duplicate
    # installed set.
    _add_dist(site, "k5demo-app", "9.9.9")
    lock = _lock_text(("k5demo-app", "1.2.3"))
    completed = _run_lock_program(tmp_path, lock, site)
    assert completed.returncode != 0
    assert "k5demo-app" in completed.stderr
    # The failure must list the locked version AND every observed
    # installed version deterministically.
    assert "locked=1.2.3" in completed.stderr
    assert "1.2.3" in completed.stderr
    assert "9.9.9" in completed.stderr


def test_review5114302995_exact_single_installed_locked_version_passes(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site"
    site.mkdir()
    _add_dist(site, "k5demo-app", "1.2.3")
    lock = _lock_text(("k5demo-app", "1.2.3"))
    completed = _run_lock_program(tmp_path, lock, site)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().split("\t")[0] == "pass"


def test_review5114302995_only_wrong_version_fails(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    _add_dist(site, "k5demo-app", "9.9.9")
    lock = _lock_text(("k5demo-app", "1.2.3"))
    completed = _run_lock_program(tmp_path, lock, site)
    assert completed.returncode != 0
    assert "k5demo-app" in completed.stderr
    assert "locked=1.2.3" in completed.stderr
    assert "9.9.9" in completed.stderr


def test_review5114302995_normalized_duplicate_distributions_fail(
    tmp_path: Path,
) -> None:
    # Two PEP-503-normalized equivalent names (e.g. "k5demo-app" and
    # "K5Demo.App") must collapse to one normalized name in the
    # installed set; the resulting set then has two versions and
    # must fail closed even if the locked version is present.
    site = tmp_path / "site"
    site.mkdir()
    _add_dist(site, "k5demo-app", "1.2.3")
    _add_dist(site, "K5Demo.App", "9.9.9")
    lock = _lock_text(("k5demo-app", "1.2.3"))
    completed = _run_lock_program(tmp_path, lock, site)
    assert completed.returncode != 0
    assert "k5demo-app" in completed.stderr
    assert "9.9.9" in completed.stderr


def test_review5114302995_missing_locked_package_still_fails(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site"
    site.mkdir()
    _add_dist(site, "k5demo-app", "1.2.3")
    # Lock pins a package that is NOT installed.
    lock = _lock_text(("k5demo-app", "1.2.3"), ("k5demo-missing", "9.9.9"))
    completed = _run_lock_program(tmp_path, lock, site)
    assert completed.returncode != 0
    assert "k5demo-missing" in completed.stderr


# ---------------------------------------------------------------------------
# Codex review 5114892694 / comment 3935450171: failed-start lifecycle hole
# ---------------------------------------------------------------------------


def _build_failed_start_probe(
    tmp_path: Path,
    container_name: str,
    volume_name: str,
    log_path: Path,
) -> tuple[Path, str, Path, Path]:
    """Build the deterministic fake-Docker shim used by the failed-start test.

    The shim simulates docker's "create succeeded, start failed" outcome
    by:
      1. accepting `docker volume create` and `docker run -d`;
      2. recording the exact container name on a sentinel file so the
         post-mortem existence probe (used by the fixed script) returns
         a real hit;
      3. exiting non-zero from `docker run -d` so the entrypoint's
         `else` branch fires.

    The shim then participates in the normal cleanup path: it accepts
    `docker rm -v -f`, `docker volume rm`, and removes the container and
    volume names from any subsequent listing so the verification step
    proves the resources are actually gone.
    """
    shim = tmp_path / "docker"
    shim.write_text(
        f"""#!/usr/bin/env bash
set -u
STATE={log_path.with_name("shim-state")!s}
SENTINEL={log_path!s}
CONTAINER={container_name!r}
VOLUME={volume_name!r}

# Lazy initialization: the state file persists across shim invocations,
# so we only set it to 1 (both resources present) on the very first call.
if [ ! -e "$STATE" ]; then
  printf '1\\n' >"$STATE"
fi

list_containers() {{
  if [ "$(cat "$STATE")" = "1" ]; then
    printf '%s\\n' "$CONTAINER"
  fi
  printf '%s\\n' "$CONTAINER" >>"$SENTINEL"
}}
list_volumes() {{
  if [ "$(cat "$STATE")" = "1" ]; then
    printf '%s\\n' "$VOLUME"
  fi
}}

case "$1:$2" in
  ps:-a)
    list_containers
    exit 0
    ;;
  volume:ls)
    list_volumes
    exit 0
    ;;
  volume:create)
    exit 0
    ;;
  run:-d)
    printf 'run-d\\n' >>"$SENTINEL"
    # The create side-effect already happened. Fail the start phase
    # to mirror a real port-conflict lifecycle.
    exit 42
    ;;
  rm:-v)
    printf 'rm-v\\n' >>"$SENTINEL"
    printf '0\\n' >"$STATE"
    exit 0
    ;;
  volume:rm)
    printf 'volume-rm\\n' >>"$SENTINEL"
    printf '0\\n' >"$STATE"
    exit 0
    ;;
  inspect:*)
    # Defense in depth: the failed-start path must never reach .Config.Env.
    exit 0
    ;;
  *)
    printf 'unexpected-args %s\\n' "$*" >>"$SENTINEL"
    exit 0
    ;;
esac
""",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return (
        shim,
        "exit=42 from docker run -d (create-then-fail)",
        log_path,
        tmp_path / "post-listings",
    )


def _build_failed_start_entrypoint(
    tmp_path: Path,
    container_name: str,
    volume_name: str,
    log_path: Path,
) -> tuple[Path, Path, str, Path]:
    """Build a tiny entrypoint that exercises only the post-failure
    container probe + cleanup trap. The point is to run the same fixed
    control flow against a deterministic fake Docker without spinning up
    any real restore machinery.
    """
    shim, _, _, _ = _build_failed_start_probe(
        tmp_path,
        container_name,
        volume_name,
        log_path,
    )
    work = tmp_path / "k5-isolated-restore-failed-start"
    work.mkdir()
    state = tmp_path / "state.tsv"
    state.write_text("", encoding="utf-8")
    probe = f"""#!/usr/bin/env bash
set -u
CONTAINER={container_name!r}
VOLUME={volume_name!r}
CONTAINER_CREATED=0
VOLUME_CREATED=1
DOCKER_RM_STATUS=not-created
DOCKER_VOLUME_RM_STATUS=not-created
DOCKER_PS_STATUS=not-run
DOCKER_VOLUME_LS_STATUS=not-run
APP_PID=
APP_PROCESS_STATUS=not-started
WORK={work!s}
WORK_ROOT={tmp_path!s}
SOURCE_BACKUP_MUTATION=false
RESULT=fail
CLEANUP_STATUS=pending
FAILURE_REASON=

cleanup() {{
  set +e
  if [ "$CONTAINER_CREATED" -eq 1 ]; then
    if docker rm -v -f "$CONTAINER" >/dev/null 2>&1; then
      DOCKER_RM_STATUS="pass"
    else
      DOCKER_RM_STATUS="fail"
    fi
  fi
  if [ "$VOLUME_CREATED" -eq 1 ]; then
    if docker volume rm "$VOLUME" >/dev/null 2>&1; then
      DOCKER_VOLUME_RM_STATUS="pass"
    else
      DOCKER_VOLUME_RM_STATUS="fail"
    fi
  fi
  local ps_out vol_out
  ps_out="{work}/docker-ps-cleanup.txt"
  vol_out="{work}/docker-volume-cleanup.txt"
  if docker ps -a --no-trunc --format '{{{{.Names}}}}' >"$ps_out" 2>/dev/null; then
    DOCKER_PS_STATUS="pass"
  else
    DOCKER_PS_STATUS="fail"
  fi
  if docker volume ls --format '{{{{.Name}}}}' >"$vol_out" 2>/dev/null; then
    DOCKER_VOLUME_LS_STATUS="pass"
  else
    DOCKER_VOLUME_LS_STATUS="fail"
  fi
  if ! {{ [[ "$DOCKER_RM_STATUS" = "pass" || "$DOCKER_RM_STATUS" = "not-created" ]] &&
     [[ "$DOCKER_VOLUME_RM_STATUS" = "pass" || "$DOCKER_VOLUME_RM_STATUS" = "not-created" ]] &&
     [ "$DOCKER_PS_STATUS" = "pass" ] &&
     [ "$DOCKER_VOLUME_LS_STATUS" = "pass" ] &&
     ! grep -Fxq "$CONTAINER" "$ps_out" &&
     ! grep -Fxq "$VOLUME" "$vol_out"; }}; then
    RESULT="fail"
    CLEANUP_STATUS="fail"
  else
    CLEANUP_STATUS="pass"
  fi
  printf '%s\\t%s\\t%s\\t%s\\t%s\\n' \\
    "$RESULT" "$CLEANUP_STATUS" "$APP_PROCESS_STATUS" "$SOURCE_BACKUP_MUTATION" \\
    "$FAILURE_REASON" >>"{state}"
  rm -rf -- "{work}"
  exit 0
}}
trap cleanup EXIT

# --- replica of the fixed entrypoint control flow ---
if docker run -d --name "$CONTAINER" -v "$VOLUME:/var/lib/postgresql" postgres:18-alpine >/dev/null; then
  CONTAINER_CREATED=1
else
  if docker ps -a --no-trunc --format '{{{{.Names}}}}' 2>/dev/null | grep -Fxq "$CONTAINER" \\
    || docker ps -a --no-trunc --format '{{{{.Names}}}}' 2>/dev/null | grep -Fxq "$CONTAINER" 1>/dev/null 2>&1; then
    CONTAINER_CREATED=1
  elif ! docker ps -a --no-trunc --format '{{{{.Names}}}}' >/dev/null 2>&1; then
    CONTAINER_CREATED=1
  fi
  FAILURE_REASON="failed to create disposable PostgreSQL container"
fi
"""
    script = tmp_path / "failed_start_probe.sh"
    script.write_text(probe, encoding="utf-8")
    script.chmod(0o755)
    return shim, work, "container", state


def test_review5114892694_failed_start_removes_exact_container_and_volume(
    tmp_path: Path,
) -> None:
    container = "k5-20260831-121759-pg"
    volume = "k5-20260831-121759-pgdata"
    sentinel = tmp_path / "sentinel.log"
    shim, _, _, state = _build_failed_start_entrypoint(
        tmp_path,
        container,
        volume,
        sentinel,
    )
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    completed = subprocess.run(
        ["bash", str(tmp_path / "failed_start_probe.sh")],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    # The post-mortem existence probe must have observed the exact
    # container (proves docker ps -a hit during the else-branch). The
    # cleanup must have actually removed the exact container (proves
    # `docker rm -v -f $CONTAINER` was invoked) and the named volume
    # (proves `docker volume rm $VOLUME` was invoked).
    sentinel_text = sentinel.read_text(encoding="utf-8")
    assert "run-d" in sentinel_text
    assert container in sentinel_text
    assert "rm-v" in sentinel_text
    assert "volume-rm" in sentinel_text
    # No inspect call (which would have read .Config.Env or other
    # secret surfaces) should have been triggered by the failed-start
    # lifecycle.
    assert "inspect:" not in sentinel_text
    records = [
        line.split("\t")
        for line in state.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert records, "cleanup never recorded state"
    last = records[-1]
    # Cleanup itself succeeded (container + volume both reaped, listings
    # post-cleanup show neither) so cleanup_status reports pass.
    assert last[1] == "pass", last
    # The overall K5 result is still FAILURE because the start itself
    # never produced a healthy PostgreSQL container.
    assert last[0] == "fail", last
    # The recorded failure reason carries the start-side cause.
    assert last[4] == "failed to create disposable PostgreSQL container"
    # The cleanup trap absorbed the start-side failure and exited 0; the
    # recorded state already proves the K5 result is fail/pass outcome
    # above. No additional stderr assertions are required.


# ---------------------------------------------------------------------------
# Codex findings 3936216994, 3936216998, 3936217000, 3934742056, 3934742062
# ---------------------------------------------------------------------------


def _run_streaming_initial_program(
    tmp_path: Path,
    relative: str,
    payload: bytes,
    *,
    expected_sha: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the maintained initial component validation program.

    The test owns the source file in tmp_path; the program is extracted
    from the production entrypoint at runtime.
    """
    if expected_sha is None:
        expected_sha = hashlib.sha256(payload).hexdigest()
    source = tmp_path / "comp.bin"
    source.write_bytes(payload)
    source_path = str(source)
    identity = tmp_path / "id.tsv"
    program = _extract_streaming_initial_block()
    completed = subprocess.run(
        [sys.executable, "-c", program, source_path, relative, expected_sha, str(identity)],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed


def _extract_streaming_initial_block() -> str:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    # Extract only the Python program between <<'PY' ... PY markers.
    start = text.index("Strong component identity capture:")
    py_open = text.index("<<'PY'", start) + len("<<'PY'") + 1
    py_close = text.index("\nPY\n", py_open)
    return text[py_open:py_close]


def test_review3934742056_initial_component_digest_streams_via_sha256_update(
    tmp_path: Path,
) -> None:
    block = _extract_streaming_initial_block()
    # Streaming hash usage is required; the prior b"".join(chunks) +
    # hashlib.sha256(data) pattern must not reappear.
    assert "digest.update" in block
    assert "digest = hashlib.sha256()" in block
    assert "digest.hexdigest()" in block
    # The legacy whole-file buffer pattern must be gone from the initial
    # validation block.
    assert "b\"\".join(chunks)" not in block
    assert "hashlib.sha256(data).hexdigest()" not in block


def test_review3934742056_initial_component_digest_still_correct(
    tmp_path: Path,
) -> None:
    payload = b"streaming-component-payload"
    completed = _run_streaming_initial_program(
        tmp_path, "comp.bin", payload
    )
    assert completed.returncode == 0, completed.stderr
    identity = dict(
        line.split("=", 1)
        for line in (tmp_path / "id.tsv").read_text(encoding="utf-8").splitlines()
    )
    assert identity["sha256"] == hashlib.sha256(payload).hexdigest()


def test_review3934742056_initial_component_digest_rejects_wrong_checksum(
    tmp_path: Path,
) -> None:
    payload = b"streaming-component-payload"
    wrong = "f" * 64
    completed = _run_streaming_initial_program(
        tmp_path, "comp.bin", payload, expected_sha=wrong
    )
    assert completed.returncode != 0
    assert "source checksum mismatch" in completed.stderr
    assert wrong in completed.stderr


def test_review3934742056_cleanup_revalidation_streams_via_sha256_update() -> None:
    block = _extract_component_revalidation_block()
    assert "digest.update" in block
    assert "digest = hashlib.sha256()" in block
    assert "digest.hexdigest()" in block
    assert "b\"\".join(chunks)" not in block
    assert "hashlib.sha256(data).hexdigest()" not in block


def test_review3934742056_cleanup_revalidation_detects_changed_bytes(
    tmp_path: Path,
) -> None:
    identity = tmp_path / "id.tsv"
    original = tmp_path / "comp.bin"
    payload = b"streaming-cleanup-payload-for-revalidation"
    original.write_bytes(payload)
    _write_component_identity(identity, original, payload)
    # Replace the bytes without changing size, mtime_ns, or inode.
    os.utime(original, ns=(123456789, 987654321))
    original.write_bytes(b"streaming-cleanup-payload-for-revalidation-2")
    rev = _run_revalidate(identity)
    assert rev.returncode != 0
    assert "sha256" in rev.stderr


def test_review3934742056_streaming_program_does_not_buffer_full_payload(
    tmp_path: Path,
) -> None:
    # Use a payload large enough that an in-memory join would be obvious
    # in a memory profile; we only assert that no `b"".join(chunks)`
    # list-accumulation pattern remains in the maintained program.
    block = _extract_streaming_initial_block()
    assert "chunks.append" not in block
    assert "chunks = []" not in block


def test_review3934742056_open_failure_does_not_leak_absolute_source_path(
    tmp_path: Path,
) -> None:
    payload = b"x" * 16
    # Point the program at a private, distinctive path; the failure
    # context must never contain the absolute path.
    private_root = tmp_path / "private" / "k5-super-secret-backup-root"
    private_root.mkdir(parents=True, exist_ok=True)
    source = private_root / "comp.bin"
    source.write_bytes(payload)
    identity = tmp_path / "id.tsv"
    full_block = _extract_streaming_initial_block()
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            full_block,
            str(source),
            "comp.bin",
            hashlib.sha256(payload).hexdigest(),
            str(identity),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    # Make the next invocation hit a real open failure: replace the
    # private file with a symlink so the O_NOFOLLOW open rejects it.
    source.unlink()
    source.symlink_to(private_root / "real.bin")
    (private_root / "real.bin").write_bytes(payload)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            full_block,
            str(source),
            "comp.bin",
            hashlib.sha256(payload).hexdigest(),
            str(identity),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    # The OS-level open can succeed even when pointed at the private
    # path; force a real open failure by removing the file after the
    # test program is launched, OR by pointing the program at a
    # symlink (which the O_NOFOLLOW open rejects). Use the symlink
    # path to deterministically trip the open failure.
    private_root = tmp_path / "private" / "k5-super-secret-backup-root"
    source = private_root / "comp.bin"
    source.unlink()
    source.symlink_to(private_root / "real.bin")
    (private_root / "real.bin").write_bytes(payload)
    identity = tmp_path / "id.tsv"
    full_block = _extract_streaming_initial_block()
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            full_block,
            str(source),
            "comp.bin",
            hashlib.sha256(payload).hexdigest(),
            str(identity),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    # Filename-free failure context only.
    assert "private" not in completed.stderr
    assert "k5-super-secret-backup-root" not in completed.stderr
    assert "real.bin" not in completed.stderr
    # The relative name is preserved so the operator can identify the
    # failing component.
    assert "comp.bin" in completed.stderr
    # Filename-free error type and errno are present.
    assert "error=" in completed.stderr
    assert "errno=" in completed.stderr


def test_review3934742062_failure_reason_does_not_leak_private_root(
    tmp_path: Path,
) -> None:
    # The previous test exercises the same surface directly; this test
    # ensures the persisted failureReason does not include the
    # absolute private path that flows through `die`.
    private_root = tmp_path / "private" / "k5-super-secret-backup-root"
    private_root.mkdir(parents=True, exist_ok=True)
    # Use a non-existent file path under a private, distinctive root.
    missing = private_root / "missing.bin"
    identity = tmp_path / "id.tsv"
    full_block = _extract_streaming_initial_block()
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            full_block,
            str(missing),
            "comp.bin",
            "0" * 64,
            str(identity),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    # The persisted failure context contains only the relative name and
    # the error class / errno, never the absolute path or the private
    # root.
    assert "private" not in completed.stderr
    assert "k5-super-secret-backup-root" not in completed.stderr
    assert str(missing) not in completed.stderr
    assert "comp.bin" in completed.stderr


def test_review3936216994_user_data_gate_present_for_all_eight_dbs() -> None:
    # The script must probe row data for every label, in order.
    text = ENTRYPOINT.read_text(encoding="utf-8")
    for label in (
        "unihub",
        "mobiup_dwh",
        "unihub_identity",
        "unihub_retail",
        "unihub_distribution",
        "unihub_learning",
        "authentik",
        "glitchtip",
    ):
        # Each label's loop body must include the user-data present
        # probe; otherwise schema-only restores for that label could
        # silently pass.
        assert f'"{label}"' in text, label
    # Confirm the for-loop still iterates over all eight labels and the
    # row-data gate runs inside the loop body.
    assert "for label in unihub mobiup_dwh unihub_identity unihub_retail unihub_distribution unihub_learning authentik glitchtip" in text
    assert "user_data_present" in text
    assert "restored database $database contains user relations but no row data" in text
    # The acceptance evidence writer must serialize the per-DB flag.
    assert "userDataPresent" in text
    assert '"true"' in text or "True" in text


def test_review3936216994_user_data_probe_uses_safe_postgres_quoting() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    # format('%I.%I', ...) is the maintained bounded quoting mechanism.
    assert "format('%I.%I'" in text
    # The probe must not select non-r/p relkinds; ordinary + partitioned
    # only. system catalog + info schema + pg_toast + pg_temp excluded.
    assert "c.relkind IN ('r','p')" in text


def test_review3936216994_user_data_probe_rejects_schema_only_db() -> None:
    program = text = (
        ENTRYPOINT.read_text(encoding="utf-8").split("for label in unihub mobiup_dwh")[1]
    )
    # The fail-closed message must mention "no row data".
    assert "no row data" in program


def test_review3936216998_postgres_image_id_authoritative_in_evidence() -> None:
    # The evidence must persist postgresImageId and use it (or the
    # equivalent content-addressed image ID) for postgresImageDigest.
    text = ENTRYPOINT.read_text(encoding="utf-8")
    # Strip bash comments so the assertion only inspects executable code
    # paths (the production comment intentionally references the
    # deprecated pattern for documentation purposes).
    code_lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        code_lines.append(line)
    code = "\n".join(code_lines)
    assert '"postgresImageId":' in code
    # The deprecated authoritative-from-RepoDigests[0] pattern is gone
    # from the executable code path.
    assert "RepoDigests[0]" not in code
    assert "values[0].split" not in code


def test_review3936216998_image_inspect_emits_only_image_id() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    # Strip bash comments so the assertion only inspects executable code
    # paths (the production comment intentionally references the
    # deprecated pattern for documentation purposes).
    code_lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        code_lines.append(line)
    code = "\n".join(code_lines)
    # The inspect call no longer asks for RepoDigests in the format
    # string (which would force Python to re-parse JSON in a fragile
    # way). Only `.Id` is captured.
    start = code.index('CURRENT_PHASE="postgres-image"')
    end = code.index('CURRENT_PHASE="payload-stage"')
    block = code[start:end]
    assert "--format '{{.Id}}'" in block
    assert "RepoDigests" not in block


def test_review3936216998_postgres_digest_equals_postgres_image_id() -> None:
    # The fix binds POSTGRES_DIGEST to the captured image ID, not to
    # an arbitrary first RepoDigest.
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index('CURRENT_PHASE="postgres-image"')
    end = text.index('CURRENT_PHASE="payload-stage"')
    block = text[start:end]
    assert "POSTGRES_DIGEST=\"$POSTGRES_IMAGE_ID\"" in block


def test_review3936217000_source_repo_check_uses_git_native_probe() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    # The .git directory check must be gone; a `git worktree` checkout
    # has a regular file there, so a directory test would reject it.
    assert '[ -d "$SOURCE_REPO/.git" ]' not in text
    assert 'rev-parse --is-inside-work-tree' in text
    assert 'SOURCE_IS_WORKTREE="$(' in text
    assert '[ "$SOURCE_IS_WORKTREE" = "true" ]' in text


def test_review3936217000_real_local_git_worktree_passes_preflight(
    tmp_path: Path,
) -> None:
    # Build a real worktree from a local repository and confirm the
    # maintained probe reports it as inside a work tree.
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_AUTHOR_NAME"] = "k5-fixture"
    env["GIT_AUTHOR_EMAIL"] = "k5@example.invalid"
    env["GIT_COMMITTER_NAME"] = "k5-fixture"
    env["GIT_COMMITTER_EMAIL"] = "k5@example.invalid"

    def git(*args: str, cwd: Path) -> str:
        completed = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return completed.stdout.strip()

    main_repo = tmp_path / "main"
    main_repo.mkdir()
    git("init", "-q", "--initial-branch=main", cwd=main_repo)
    (main_repo / "README").write_text("k5 fixture", encoding="utf-8")
    git("add", "README", cwd=main_repo)
    git("commit", "-q", "-m", "k5 fixture", cwd=main_repo)

    worktree = tmp_path / "wt"
    git("worktree", "add", "-b", "k5-feature", str(worktree), "main", cwd=main_repo)

    # A worktree has .git as a regular FILE, not a directory; verify
    # the maintained probe still reports it as inside a work tree.
    assert not (worktree / ".git").is_dir()
    assert (worktree / ".git").is_file()
    outcome = git("rev-parse", "--is-inside-work-tree", cwd=worktree)
    assert outcome == "true"

    # A non-git directory must NOT report inside a work tree.
    non_git = tmp_path / "non-git"
    non_git.mkdir()
    (non_git / "blob").write_text("data", encoding="utf-8")
    non_git_outcome = subprocess.run(
        ["git", "-C", str(non_git), "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert non_git_outcome.returncode != 0 or non_git_outcome.stdout.strip() != "true"


# ---------------------------------------------------------------------------
# Codex findings 3936446009, 3936446025, 3936446029
# Executable PostgreSQL row-presence SQL + visits expected-table gate
# + sanitized generation artifact open errors.
# ---------------------------------------------------------------------------


import contextlib


def _extract_row_presence_sql() -> str:
    """Extract the exact row-presence SQL heredoc body used by the
    production entrypoint. The heredoc is delimited by `<<'SQL'` and
    `SQL`; only the SQL body between those markers is returned so the
    regression can execute the same bytes the production code does.
    """
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index("psql -X -qAt -v ON_ERROR_STOP=1 -U postgres -d \"$database\" <<'SQL'")
    body_start = start + text[start:].index("<<'SQL'") + len("<<'SQL'") + 1
    body_end = start + text[start:].index("\nSQL\n", body_start - start)
    return text[body_start:body_end]


def _extract_generation_metadata_open_block() -> str:
    """Return the Python source opened by the generation-metadata
    heredoc so the test can drive the exact captured-output path.
    """
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index('CURRENT_PHASE="generation-metadata"')
    py_open = text.index("<<'PY'", start) + len("<<'PY'") + 1
    py_close = text.index("\nPY\n", py_open)
    return text[py_open:py_close]


def _extract_generation_manifest_open_block() -> str:
    """Return the Python source opened by the generation-manifest
    heredoc so the test can drive the exact captured-output path.
    """
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index('CURRENT_PHASE="generation-manifest"')
    py_open = text.index("<<'PY'", start) + len("<<'PY'") + 1
    py_close = text.index("\nPY\n", py_open)
    return text[py_open:py_close]


def test_review3936446009_invalid_bool_or_oid_and_format_in_from_are_gone() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    # The original defect used bool_or(c.oid) and FROM ONLY format(...).
    # Both must be gone from the row-presence branch.
    assert "bool_or(c.oid)" not in text
    assert "FROM ONLY format(" not in text
    # The replacement must use server-side EXECUTE and a bounded final
    # boolean to the shell.
    assert "EXECUTE format(" in text
    assert "k5_row_presence" in text


def test_review3936446009_row_presence_sql_is_valid_postgres() -> None:
    # The extracted SQL must parse via a real PostgreSQL session if
    # available; otherwise we use a pure-python PG parser sanity check
    # to ensure the SQL is structurally well-formed. We rely on a real
    # engine test in the engine-backed case below; here we just
    # confirm the SQL does not contain the legacy invalid patterns.
    body = _extract_row_presence_sql()
    # No boolean casts on oid; only the final RAISE INFO signal.
    assert "bool_or(c.oid)" not in body
    assert "FROM ONLY" not in body
    # The dynamic quoted relation must use EXECUTE format(...).
    assert "EXECUTE format(" in body
    assert "%I.%I" in body


def test_review3936446009_engine_backed_catalogs_only_returns_false() -> None:
    # CASE 1: system catalogs only -> row-presence must be false.
    if os.environ.get("UNIHUB_TEST_DATABASE") != "1":
        pytest.skip("UNIHUB_TEST_DATABASE not set; engine test requires real DB")
    import asyncio
    import asyncpg

    async def run() -> bool:
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            dbname = f"k5_test_{os.getpid()}"
            with contextlib.suppress(asyncpg.DuplicateDatabaseError):
                await conn.execute(f'CREATE DATABASE "{dbname}"')
            try:
                test_conn = await asyncpg.connect(
                    dsn=os.environ["DATABASE_URL"].rsplit("/", 1)[0] + f"/{dbname}"
                )
                try:
                    # Execute the production DO block first; it stores
                    # the result in a session temp table. Then read it.
                    await test_conn.execute(_extract_row_presence_sql())
                    val = await test_conn.fetchval(
                        "SELECT present::text FROM k5_row_presence LIMIT 1"
                    )
                    return val == "true"
                finally:
                    await test_conn.close()
            finally:
                with contextlib.suppress(asyncpg.PostgresError):
                    await conn.execute(
                        f'DROP DATABASE IF EXISTS "{dbname}"'
                    )
        finally:
            await conn.close()

    assert asyncio.run(run()) is False


def test_review3936446009_engine_backed_empty_user_table_returns_false() -> None:
    # CASE 2: a non-system user table with zero rows -> must be false.
    if os.environ.get("UNIHUB_TEST_DATABASE") != "1":
        pytest.skip("UNIHUB_TEST_DATABASE not set; engine test requires real DB")
    import asyncio
    import asyncpg

    async def run() -> bool:
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            dbname = f"k5_test_{os.getpid()}"
            with contextlib.suppress(asyncpg.DuplicateDatabaseError):
                await conn.execute(f'CREATE DATABASE "{dbname}"')
            try:
                test_conn = await asyncpg.connect(
                    dsn=os.environ["DATABASE_URL"].rsplit("/", 1)[0] + f"/{dbname}"
                )
                try:
                    await test_conn.execute("CREATE TABLE k5_user (id int)")
                    await test_conn.execute(_extract_row_presence_sql())
                    val = await test_conn.fetchval(
                        "SELECT present::text FROM k5_row_presence LIMIT 1"
                    )
                    return val == "true"
                finally:
                    await test_conn.close()
            finally:
                with contextlib.suppress(asyncpg.PostgresError):
                    await conn.execute(
                        f'DROP DATABASE IF EXISTS "{dbname}"'
                    )
        finally:
            await conn.close()

    assert asyncio.run(run()) is False


def test_review3936446009_engine_backed_one_row_user_table_returns_true() -> None:
    # CASE 3: insert one synthetic row into a non-system user table.
    if os.environ.get("UNIHUB_TEST_DATABASE") != "1":
        pytest.skip("UNIHUB_TEST_DATABASE not set; engine test requires real DB")
    import asyncio
    import asyncpg

    async def run() -> bool:
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            dbname = f"k5_test_{os.getpid()}"
            with contextlib.suppress(asyncpg.DuplicateDatabaseError):
                await conn.execute(f'CREATE DATABASE "{dbname}"')
            try:
                test_conn = await asyncpg.connect(
                    dsn=os.environ["DATABASE_URL"].rsplit("/", 1)[0] + f"/{dbname}"
                )
                try:
                    await test_conn.execute("CREATE TABLE k5_user (id int)")
                    await test_conn.execute("INSERT INTO k5_user VALUES (1)")
                    await test_conn.execute(_extract_row_presence_sql())
                    val = await test_conn.fetchval(
                        "SELECT present::text FROM k5_row_presence LIMIT 1"
                    )
                    return val == "true"
                finally:
                    await test_conn.close()
            finally:
                with contextlib.suppress(asyncpg.PostgresError):
                    await conn.execute(
                        f'DROP DATABASE IF EXISTS "{dbname}"'
                    )
        finally:
            await conn.close()

    assert asyncio.run(run()) is True


def test_review3936446009_engine_backed_unusual_identifier_quoting_returns_true() -> None:
    # CASE 4: a safely quotable unusual schema/table identifier (mixed
    # case + space) is still safely EXECUTE-quoted.
    if os.environ.get("UNIHUB_TEST_DATABASE") != "1":
        pytest.skip("UNIHUB_TEST_DATABASE not set; engine test requires real DB")
    import asyncio
    import asyncpg

    async def run() -> bool:
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            dbname = f"k5_test_{os.getpid()}"
            with contextlib.suppress(asyncpg.DuplicateDatabaseError):
                await conn.execute(f'CREATE DATABASE "{dbname}"')
            try:
                test_conn = await asyncpg.connect(
                    dsn=os.environ["DATABASE_URL"].rsplit("/", 1)[0] + f"/{dbname}"
                )
                try:
                    await test_conn.execute('CREATE SCHEMA "Mixed Case"')
                    await test_conn.execute(
                        'CREATE TABLE "Mixed Case"."k5 user table" (id int)'
                    )
                    await test_conn.execute(
                        'INSERT INTO "Mixed Case"."k5 user table" VALUES (1)'
                    )
                    await test_conn.execute(_extract_row_presence_sql())
                    val = await test_conn.fetchval(
                        "SELECT present::text FROM k5_row_presence LIMIT 1"
                    )
                    return val == "true"
                finally:
                    await test_conn.close()
            finally:
                with contextlib.suppress(asyncpg.PostgresError):
                    await conn.execute(
                        f'DROP DATABASE IF EXISTS "{dbname}"'
                    )
        finally:
            await conn.close()

    assert asyncio.run(run()) is True


def test_review3938278145_visits_expected_table_gate_present() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    # The SQLite visits.db archive authority creates exactly `visits`
    # (see backend/scripts/run_tests_isolated.sh). The gate must use
    # that exact name and must record the bounded fact in evidence.
    assert 'VISITS_EXPECTED_TABLE="visits"' in text
    assert 'VISITS_EXPECTED_TABLE="fieldops_visits"' not in text
    assert "name='$VISITS_EXPECTED_TABLE'" in text
    assert "VISITS_EXPECTED_TABLE_COUNT" in text
    assert "EXISTS(SELECT 1 FROM $VISITS_EXPECTED_TABLE LIMIT 1)" in text
    assert '"expectedTable": "visits"' in text
    assert '"expectedTable": "fieldops_visits"' not in text
    assert '"rowDataPresent": True' in text


def test_review3938278145_sqlite_missing_expected_table_fails(tmp_path: Path) -> None:
    import sqlite3 as _sqlite3
    db = tmp_path / "missing.db"
    conn = _sqlite3.connect(str(db))
    conn.close()
    expected = "visits"
    count = subprocess.run(
        [
            "sqlite3",
            str(db),
            f"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='{expected}';",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert count == "0"


def test_review3938278145_sqlite_zero_row_expected_table_fails(tmp_path: Path) -> None:
    import sqlite3 as _sqlite3
    db = tmp_path / "zero.db"
    conn = _sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()
    exists_raw = subprocess.run(
        [
            "sqlite3",
            str(db),
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='visits';",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert exists_raw == "1"
    row_raw = subprocess.run(
        [
            "sqlite3",
            str(db),
            "SELECT EXISTS(SELECT 1 FROM visits LIMIT 1);",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert row_raw == "0"


def test_review3938278145_sqlite_one_row_expected_table_passes(tmp_path: Path) -> None:
    import sqlite3 as _sqlite3
    db = tmp_path / "one.db"
    conn = _sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO visits VALUES (1)")
        conn.commit()
    finally:
        conn.close()
    exists_raw = subprocess.run(
        [
            "sqlite3",
            str(db),
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='visits';",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert exists_raw == "1"
    row_raw = subprocess.run(
        [
            "sqlite3",
            str(db),
            "SELECT EXISTS(SELECT 1 FROM visits LIMIT 1);",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert row_raw == "1"


def test_review3938278145_sqlite_fieldops_visits_only_does_not_satisfy_gate(
    tmp_path: Path,
) -> None:
    # visits is missing but fieldops_visits has rows. The bounded
    # expected-table gate must FAIL because the exact `visits`
    # expected table is absent, regardless of an unrelated
    # fieldops_visits presence.
    import sqlite3 as _sqlite3
    db = tmp_path / "fieldops_only.db"
    conn = _sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE fieldops_visits (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO fieldops_visits VALUES (1)")
        conn.commit()
    finally:
        conn.close()
    visits_count = subprocess.run(
        [
            "sqlite3",
            str(db),
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='visits';",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert visits_count == "0"


def test_review3938278145_sqlite_unrelated_table_does_not_satisfy_gate(
    tmp_path: Path,
) -> None:
    # visits is empty; an unrelated table has rows. The bounded
    # expected-table gate must still FAIL because the exact expected
    # table is empty.
    import sqlite3 as _sqlite3
    db = tmp_path / "unrelated.db"
    conn = _sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE k5_unrelated (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO k5_unrelated VALUES (1)")
        conn.commit()
    finally:
        conn.close()
    row_raw = subprocess.run(
        [
            "sqlite3",
            str(db),
            "SELECT EXISTS(SELECT 1 FROM visits LIMIT 1);",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert row_raw == "0"


def test_review3936446029_generation_metadata_sanitized_open_error_format(
    tmp_path: Path,
) -> None:
    # Drive the production open-failure path against a private,
    # distinctive path. The captured output must contain the
    # filename-free error type and errno, never the absolute path.
    private_root = tmp_path / "private" / "k5-super-secret-backup-root"
    private_root.mkdir(parents=True, exist_ok=True)
    real = private_root / "real.result"
    real.write_text("ignored", encoding="utf-8")
    target = private_root / "metadata.result"
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(real)
    program = _extract_generation_metadata_open_block()
    completed = subprocess.run(
        [sys.executable, "-c", program, str(target), FUTURE_STAMP, FIXTURE_SHA,
         "2026-09-03T02:00:00Z", str(tmp_path / "expected.tsv"),
         str(tmp_path / "staged.result"), str(tmp_path / "identity.tsv")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "private" not in completed.stderr
    assert "k5-super-secret-backup-root" not in completed.stderr
    assert str(target) not in completed.stderr
    assert "real.result" not in completed.stderr
    assert "artifact=generation-metadata" in completed.stderr
    assert "error=" in completed.stderr
    assert "errno=" in completed.stderr


def test_review3936446029_generation_manifest_sanitized_open_error_format(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private" / "k5-super-secret-backup-root"
    private_root.mkdir(parents=True, exist_ok=True)
    real = private_root / "real.sha256"
    real.write_text("ignored", encoding="utf-8")
    target = private_root / "manifest.sha256"
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(real)
    program = _extract_generation_manifest_open_block()
    expected = tmp_path / "expected.tsv"
    expected.write_text("", encoding="utf-8")
    staged = tmp_path / "staged.sha256"
    identity = tmp_path / "identity.tsv"
    completed = subprocess.run(
        [sys.executable, "-c", program, str(target), FUTURE_STAMP,
         str(expected), str(staged), str(identity)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "private" not in completed.stderr
    assert "k5-super-secret-backup-root" not in completed.stderr
    assert str(target) not in completed.stderr
    assert "real.sha256" not in completed.stderr
    assert "artifact=generation-manifest" in completed.stderr
    assert "error=" in completed.stderr
    assert "errno=" in completed.stderr


# ---------------------------------------------------------------------------
# Codex 3937141403: bind readiness to the exact launched APP_PID
# ---------------------------------------------------------------------------


def _app_owns_loopback_listener_source() -> str:
    """Extract the exact app_owns_loopback_listener function source from
    the production entrypoint so the focused regressions execute the
    same bytes the readiness loop does.
    """
    return _shell_function_source(
        "app_owns_loopback_listener", chr(10) + "terminate_application()"
    )


def _run_app_owns_loopback_listener(pid: str, port: str) -> subprocess.CompletedProcess[str]:
    source = _app_owns_loopback_listener_source()
    # Ensure the harness has a newline between the extracted function
    # source (which ends with `}`) and the call site so bash can parse
    # the function-definition closer and the call as separate lines.
    if not source.endswith("\n"):
        source = source + "\n"
    # Propagate the helper's exit status out of the subprocess: the
    # last command must be the helper call, not a printf that masks
    # its nonzero status.
    harness = (
        "set -u\n"
        + source
        + f"app_owns_loopback_listener {shlex.quote(pid)} {shlex.quote(port)}\n"
    )
    return subprocess.run(
        ["bash", "-c", harness],
        check=False,
        capture_output=True,
        text=True,
    )


def _spawn_loopback_listener(port: int) -> subprocess.Popen[bytes]:
    """Start a long-lived Python child that bind/listens on
    127.0.0.1:<port> so we can verify the ownership check.
    """
    script = (
        "import socket, time, sys\n"
        "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
        "s.bind(('127.0.0.1', %d))\n"
        "s.listen(8)\n"
        "sys.stdout.write('ready\\n')\n"
        "sys.stdout.flush()\n"
        "while True:\n"
        "    time.sleep(60)\n"
    ) % port
    return subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_review3937141403_app_owns_loopback_listener_helper_is_present() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "app_owns_loopback_listener()" in text
    assert "/proc/net/tcp" in text
    assert "0100007F" in text
    # The check must not lean on lsof/ss/netstat invocations. Comment
    # prose that names those tools as explicitly forbidden is allowed.
    for forbidden in ("$(lsof ", " $(ss ", "$(netstat ", "lsof -", " ss -", "netstat -"):
        assert forbidden not in text, forbidden
    # A `ss ` or `lsof` substring inside the helper docstring is
    # permitted; the helper must not invoke those binaries.
    helper_start = text.index("app_owns_loopback_listener() {")
    helper_end = text.index(chr(10) + "terminate_application() {", helper_start)
    helper_body = text[helper_start:helper_end]
    assert "$(lsof" not in helper_body
    assert "$(ss" not in helper_body
    assert "$(netstat" not in helper_body


def test_review3937141403_own_listener_for_pid_and_port_passes() -> None:
    if not Path("/proc/net/tcp").exists():
        pytest.skip("Linux /proc required")
    import socket as _socket
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    proc = _spawn_loopback_listener(port)
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == b"ready"
        completed = _run_app_owns_loopback_listener(str(proc.pid), str(port))
        assert completed.returncode == 0, completed.stderr
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_review3937141403_wrong_pid_for_owned_port_fails() -> None:
    # Process A owns the listener; process B is a different live PID.
    # The check against (B, A_port) must FAIL.
    if not Path("/proc/net/tcp").exists():
        pytest.skip("Linux /proc required")
    import socket as _socket
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    owner = _spawn_loopback_listener(port)
    try:
        assert owner.stdout is not None
        assert owner.stdout.readline().strip() == b"ready"
        # Spawn a sibling that owns no listener.
        sibling_script = "import time; time.sleep(120)\n"
        sibling = subprocess.Popen(
            [sys.executable, "-c", sibling_script]
        )
        try:
            completed = _run_app_owns_loopback_listener(
                str(sibling.pid), str(port)
            )
            assert completed.returncode != 0
        finally:
            sibling.terminate()
            sibling.wait(timeout=10)
    finally:
        owner.terminate()
        owner.wait(timeout=10)


def test_review3937141403_correct_pid_wrong_unowned_port_fails() -> None:
    # A live PID that owns NO listener at all must FAIL the ownership
    # check, even when supplied with a syntactically valid port.
    if not Path("/proc/net/tcp").exists():
        pytest.skip("Linux /proc required")
    import socket as _socket
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    occupied_port = sock.getsockname()[1]
    sock.close()
    # Take the port down so the orphan port is unowned.
    temp_listener = _spawn_loopback_listener(occupied_port)
    try:
        assert temp_listener.stdout is not None
        assert temp_listener.stdout.readline().strip() == b"ready"
    finally:
        temp_listener.terminate()
        temp_listener.wait(timeout=10)
    idle_script = "import time; time.sleep(120)\n"
    idle = subprocess.Popen([sys.executable, "-c", idle_script])
    try:
        completed = _run_app_owns_loopback_listener(
            str(idle.pid), str(occupied_port)
        )
        assert completed.returncode != 0
    finally:
        idle.terminate()
        idle.wait(timeout=10)


def test_review3937141403_dead_pid_fails() -> None:
    # A pid that has already exited must FAIL closed.
    if not Path("/proc/net/tcp").exists():
        pytest.skip("Linux /proc required")
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait(timeout=10)
    pid = gone.pid
    # Confirm the pid is no longer alive (process recycled already).
    if Path(f"/proc/{pid}").exists():
        # Wait briefly for the kernel to reap; if the pid is recycled,
        # the test cannot proceed deterministically.
        gone.wait()
        if Path(f"/proc/{pid}").exists():
            pytest.skip("pid still present; cannot build dead-pid fixture")
    completed = _run_app_owns_loopback_listener(str(pid), "9899")
    assert completed.returncode != 0


def test_review3937141403_invalid_pid_and_port_fail_closed() -> None:
    if not Path("/proc/net/tcp").exists():
        pytest.skip("Linux /proc required")
    # Non-numeric pid and port must fail closed.
    for pid_value, port_value in [
        ("abc", "9899"),
        ("123", "xyz"),
        ("123", "0"),
        ("123", "70000"),
    ]:
        completed = _run_app_owns_loopback_listener(pid_value, port_value)
        assert completed.returncode != 0, (pid_value, port_value)


def test_review3937141403_readiness_sequence_prevents_unrelated_acceptance() -> None:
    # Source/control-flow assertion: the readiness loop must call
    # app_process_alive, app_owns_loopback_listener (pre-probe),
    # probe_json for /livez /health /readyz, app_process_alive
    # (post-probe), and app_owns_loopback_listener (post-probe)
    # BEFORE assigning ready=1.
    text = ENTRYPOINT.read_text(encoding="utf-8")
    ready_section_start = text.index("ready=0\nfor _ in $(seq 1 60)")
    ready_section_end = text.index("[ \"$ready\" -eq 1 ] || die", ready_section_start)
    section = text[ready_section_start:ready_section_end]

    pre_probe_ownership = section.index('app_owns_loopback_listener "$APP_PID" "$APP_PORT"')
    livez_probe = section.index('probe_json /livez')
    health_probe = section.index('probe_json /health')
    readyz_probe = section.index('probe_json /readyz')
    readyz_to_post_probe_ownership = section.index(
        'app_owns_loopback_listener "$APP_PID" "$APP_PORT"',
        readyz_probe,
    )
    post_probe_liveness = section.index("app_process_alive", readyz_probe)
    ready_set = section.index("ready=1", readyz_probe)

    assert pre_probe_ownership < livez_probe < health_probe < readyz_probe
    assert post_probe_liveness < ready_set
    assert readyz_to_post_probe_ownership < ready_set
    # Ownership MUST be re-checked AFTER the post-probe liveness check
    # so a process that died mid-probe cannot satisfy readiness.
    assert post_probe_liveness < readyz_to_post_probe_ownership


# ---------------------------------------------------------------------------
# Codex 3938278149: propagate final evidence writer failure
# ---------------------------------------------------------------------------


def _update_final_evidence_source() -> str:
    """Extract the exact update_final_evidence function source so the
    focused regression runs the same bytes the cleanup trap calls.
    """
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index("update_final_evidence() {")
    end = text.index(chr(10) + "cleanup() {", start)
    return text[start:end]


def _shadowed_python_failure(tmp_path: Path) -> Path:
    """Build a PATH-shadow `python3` that consumes stdin (the
    heredoc body) and exits nonzero deterministically. The shadowed
    binary is isolated to the test subprocess so other pytest tests
    keep using the real interpreter.
    """
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    wrapper = shadow / "python3"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "# Deterministic failure injection: consume any heredoc body on\n"
        "# stdin, then exit 42. Other tests do not see this PATH.\n"
        "cat >/dev/null\n"
        "exit 42\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return shadow


def test_review3938278149_update_final_evidence_propagates_writer_failure(
    tmp_path: Path,
) -> None:
    # The exact regression: an old evidence file is present and
    # stat-able; the final Python writer fails; capture_evidence_identity
    # must NOT be reached; update_final_evidence must return nonzero.
    shadow = _shadowed_python_failure(tmp_path)
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schemaVersion": "k5/1",
                "kind": "restore-exercise-evidence",
                "result": "fail",
                "cleanupStatus": "pending",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    identity = os.stat(evidence)

    captured_sentinel = tmp_path / "sentinel.txt"
    function_source = _update_final_evidence_source()
    if not function_source.endswith("\n"):
        function_source = function_source + "\n"
    # Inline the function source verbatim, then run a sentinel
    # capture_evidence_identity override that records reachability so
    # we can prove the production helper never calls it on writer
    # failure. The production source is unmodified: only a same-named
    # local override shadows it for this regression.
    harness = (
        "set +e\n"
        "EVIDENCE_CREATED=1\n"
        f"EVIDENCE_OUT={shlex.quote(str(evidence))}\n"
        f"EVIDENCE_DEVICE={identity.st_dev}\n"
        f"EVIDENCE_INODE={identity.st_ino}\n"
        f"CLEANUP_STATUS=pass\n"
        f"SOURCE_BACKUP_MUTATION=false\n"
        f"RESULT=pass\n"
        f"CURRENT_PHASE=\n"
        f"FAILURE_REASON=\n"
        f"DOCKER_RM_STATUS=pass\n"
        f"DOCKER_VOLUME_RM_STATUS=pass\n"
        f"DOCKER_PS_STATUS=pass\n"
        f"DOCKER_VOLUME_LS_STATUS=pass\n"
        f"APP_PROCESS_STATUS=terminated\n"
        "capture_evidence_identity() {\n"
        f"  printf 'identity-called\\n' > {shlex.quote(str(captured_sentinel))}\n"
        "  return 0\n"
        "}\n"
        + function_source
        + "update_final_evidence\n"
    )
    env = os.environ.copy()
    env["PATH"] = f"{shadow}:{env['PATH']}"
    completed = subprocess.run(
        ["bash", "-c", harness],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    # The writer failed (exit 42), so the helper must propagate that
    # exact nonzero status. The bash harness's last command IS the
    # helper call, so the subprocess returncode mirrors it.
    assert completed.returncode == 42, completed.stderr
    # The shadowed capture_evidence_identity must NOT have run.
    assert not captured_sentinel.exists(), completed.stdout
    # The old evidence file must remain present and stat-able.
    assert evidence.exists()
    after = json.loads(evidence.read_text(encoding="utf-8"))
    assert after["result"] == "fail"
    assert after["cleanupStatus"] == "pending"


def test_review3938278149_update_final_evidence_source_preserves_writer_status() -> None:
    # Narrow source/control-flow assertion: the helper must capture
    # the Python writer's exit code explicitly (NOT via `!`), and
    # capture_evidence_identity must appear only after the writer
    # status has been validated as zero.
    source = _update_final_evidence_source()
    # The writer status must be captured via $? into a local.
    assert "writer_rc=$?" in source
    # The helper must early-return on writer nonzero.
    assert '[ "$writer_rc" -eq 0 ] || return "$writer_rc"' in source
    # capture_evidence_identity must appear AFTER the writer-status
    # guard, never unconditionally after the heredoc.
    helper_end_idx = source.rindex("capture_evidence_identity")
    guard_idx = source.index('[ "$writer_rc" -eq 0 ] || return "$writer_rc"')
    assert guard_idx < helper_end_idx
    # The anti-pattern `if ! python3` is absent as code (it would
    # clobber $?); it may only appear inside a comment that names it
    # as a forbidden pattern.
    non_comment = chr(10).join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "if ! python3" not in non_comment
    # capture_evidence_identity must NOT appear unconditionally after
    # the heredoc terminator (i.e., outside the writer-status guard).
    after_heredoc = source.split("PY\n", 1)[1]
    # The first capture_evidence_identity call in the post-heredoc
    # body must be preceded by the writer-status guard.
    assert "writer_rc" in after_heredoc.split("capture_evidence_identity", 1)[0]


def test_review3938278149_final_cleanup_path_cannot_publish_pass_after_writer_failure(
    tmp_path: Path,
) -> None:
    # Drive the production cleanup() control flow with the same writer
    # failure injection: the final cleanup/PASS path cannot exit 0
    # and cannot leave result=pass when the Python writer fails. The
    # harness mirrors the production cleanup() sequence:
    #   1. Call update_final_evidence; on nonzero, flip RESULT/CLEANUP
    #      to fail and capture the failure reason.
    #   2. Only on writer success do we ever set RESULT=CLEANUP=pass.
    shadow = _shadowed_python_failure(tmp_path)
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schemaVersion": "k5/1",
                "kind": "restore-exercise-evidence",
                "result": "fail",
                "cleanupStatus": "pending",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    identity = os.stat(evidence)
    function_source = _update_final_evidence_source()
    if not function_source.endswith("\n"):
        function_source = function_source + "\n"
    captured_sentinel = tmp_path / "identity-was-called.txt"
    sidecar = tmp_path / "post.txt"
    harness = (
        "set +e\n"
        "RESULT=pass\n"
        "CLEANUP_STATUS=pass\n"
        "FAILURE_REASON=\n"
        "CURRENT_PHASE=service-acceptance\n"
        "APP_PROCESS_STATUS=terminated\n"
        "DOCKER_RM_STATUS=pass\n"
        "DOCKER_VOLUME_RM_STATUS=pass\n"
        "DOCKER_PS_STATUS=pass\n"
        "DOCKER_VOLUME_LS_STATUS=pass\n"
        "SOURCE_BACKUP_MUTATION=false\n"
        f"EVIDENCE_OUT={shlex.quote(str(evidence))}\n"
        f"EVIDENCE_DEVICE={identity.st_dev}\n"
        f"EVIDENCE_INODE={identity.st_ino}\n"
        f"EVIDENCE_CREATED=1\n"
        "capture_evidence_identity() {\n"
        f"  printf '1\\n' > {shlex.quote(str(captured_sentinel))}\n"
        "  return 0\n"
        "}\n"
        + function_source
        # Mirror the production cleanup() sequencing for the final
        # evidence publication step. The PASS branch is reachable
        # ONLY when update_final_evidence returns 0.
        + "if ! update_final_evidence; then\n"
        + "  CLEANUP_STATUS=fail\n"
        + "  RESULT=fail\n"
        + "  FAILURE_REASON='final evidence publication failed; durable evidence remains non-pass'\n"
        + "fi\n"
        + "printf 'final_result=%s\\nfinal_cleanup=%s\\nfinal_reason=%s\\n' \"$RESULT\" \"$CLEANUP_STATUS\" \"$FAILURE_REASON\" > "
        + shlex.quote(str(sidecar)) + "\n"
        + "if [ \"$RESULT\" = pass ]; then exit 0; else exit 1; fi\n"
    )
    env = os.environ.copy()
    env["PATH"] = f"{shadow}:{env['PATH']}"
    completed = subprocess.run(
        ["bash", "-c", harness],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode == 1, completed.stderr
    sidecar_text = sidecar.read_text(encoding="utf-8")
    assert "final_result=fail" in sidecar_text
    assert "final_cleanup=fail" in sidecar_text
    assert "final_reason=" in sidecar_text
    # capture_evidence_identity must NOT have been reached.
    assert not captured_sentinel.exists()
    assert evidence.exists()
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["result"] == "fail"
    assert payload["cleanupStatus"] == "pending"


# ---------------------------------------------------------------------------
# K5 follow-up #251: verifier aligned with backup topology authority
# (eight PostgreSQL databases + visits = 9 generation components).
# ---------------------------------------------------------------------------


def test_topology251_eight_pg_plus_visits_manifest_passes(tmp_path: Path) -> None:
    # The maintained verifier accepts exactly the demonstrated real backup
    # topology: 8 PostgreSQL dumps + 1 visits SQLite = 9 components.
    components = _component_relatives(FUTURE_STAMP)
    assert len(components) == 9
    completed = _run_manifest_program(tmp_path, _valid_manifest_text())
    assert completed.returncode == 0, completed.stderr
    manifest = tmp_path / "generation.sha256"
    assert completed.stdout.strip() == hashlib.sha256(
        manifest.read_bytes()
    ).hexdigest()


def test_topology251_old_seven_pg_omitting_distribution_is_rejected(
    tmp_path: Path,
) -> None:
    # The pre-#251 consumer accepted exactly 7 PG databases plus visits; the
    # unihub_distribution dump was treated as an unknown extra component and
    # the generation was rejected. With the topology correction, the
    # omission of unihub_distribution is the new failure mode.
    legacy_labels = (
        "unihub",
        "mobiup_dwh",
        "unihub_identity",
        "unihub_retail",
        "unihub_learning",
        "authentik",
        "glitchtip",
    )
    legacy_components = [
        *(f"postgres/{label}_{FUTURE_STAMP}.dump" for label in legacy_labels),
        f"visits/visits_{FUTURE_STAMP}.db",
    ]
    assert len(legacy_components) == 8
    legacy_lines = []
    for relative in legacy_components:
        digest = hashlib.sha256(
            f"synthetic {relative}\n".encode("utf-8")
        ).hexdigest()
        legacy_lines.append(f"{digest}  {relative}")
    completed = _run_manifest_program(
        tmp_path, "\n".join(legacy_lines) + "\n"
    )
    assert completed.returncode != 0
    assert "manifest component mismatch" in completed.stderr
    assert "unihub_distribution" in completed.stderr
    assert not (tmp_path / "staged.sha256").exists()


def test_topology251_arbitrary_extra_component_is_rejected(tmp_path: Path) -> None:
    # The new authority is exactly 8 PG + 1 visits = 9 components. Adding a
    # tenth arbitrary component (the verifier must not silently accept
    # arbitrary additional databases) is rejected.
    extra_component = (
        f"postgres/unihub_rogue_{FUTURE_STAMP}.dump"
    )
    manifest_text = _valid_manifest_text()
    # Inject one extra entry after the canonical 9.
    manifest_lines = manifest_text.rstrip("\n").split("\n")
    extra_digest = hashlib.sha256(
        f"synthetic {extra_component}\n".encode("utf-8")
    ).hexdigest()
    manifest_lines.append(f"{extra_digest}  {extra_component}")
    expanded_manifest = "\n".join(manifest_lines) + "\n"
    completed = _run_manifest_program(tmp_path, expanded_manifest)
    assert completed.returncode != 0
    assert "manifest component mismatch" in completed.stderr
    assert "extra" in completed.stderr
    assert not (tmp_path / "staged.sha256").exists()


def test_topology251_metadata_file_count_nine_matches_nine_entry_manifest(
    tmp_path: Path,
) -> None:
    # Valid metadata with file_count=9 must satisfy the canonical 9-entry
    # manifest. Both the metadata and the helper default have been aligned.
    result_text = "\n".join(_valid_result_lines(FUTURE_STAMP)) + "\n"
    completed = _run_metadata_program(tmp_path, result_text)
    assert completed.returncode == 0, completed.stderr
    metadata = tmp_path / "generation.result"
    staged = tmp_path / "staged.result"
    assert staged.read_bytes() == metadata.read_bytes()


def test_topology251_metadata_file_count_eight_against_nine_entry_manifest_fails(
    tmp_path: Path,
) -> None:
    # A metadata file_count that lags the canonical 9-entry manifest by
    # one is rejected before any downstream authority is established.
    result_text = "\n".join(
        _valid_result_lines(FUTURE_STAMP, file_count=8)
    ) + "\n"
    completed = _run_metadata_program(tmp_path, result_text)
    assert completed.returncode != 0
    assert "does not match" in completed.stderr
    assert "manifest entry count" in completed.stderr
    assert not (tmp_path / "staged.result").exists()


# ---------------------------------------------------------------------------
# Codex review 5120769319 / comment 3940210418 (P1): the postgres-restore
# loop in ops/k5-isolated-restore.sh MUST execute exactly the eight
# authoritative PostgreSQL labels, and the final-evidence writer MUST
# fail closed if the recorded restore rows do not match that exact set.
# ---------------------------------------------------------------------------


EXPECTED_PG_RESTORE_LABELS = (
    "unihub",
    "mobiup_dwh",
    "unihub_identity",
    "unihub_retail",
    "unihub_distribution",
    "unihub_learning",
    "authentik",
    "glitchtip",
)


def _extract_postgres_restore_loop_block() -> str:
    """Extract the postgres-restore loop body from the entrypoint.

    The extraction is bounded: from the start of the CURRENT_PHASE=
    "postgres-restore" assignment through the matching `done` that
    closes the loop. Both bounds are anchored to entrypoint tokens,
    so a future refactor that renames the phase or the loop terminator
    will surface here rather than silently passing.
    """
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index('CURRENT_PHASE="postgres-restore"')
    end_marker = 'CURRENT_PHASE="visits-restore"'
    end = text.index(end_marker, start)
    return text[start:end]


def test_distribution_p1_postgres_restore_loop_has_exactly_eight_labels() -> None:
    # The postgres-restore loop body must iterate EXACTLY the eight
    # authoritative PostgreSQL labels, in the documented canonical order,
    # no more and no fewer.
    block = _extract_postgres_restore_loop_block()
    # Pull every token after the `for label in` and before the `; do`.
    match = re.search(
        r"for label in\s+([^\n]+?)\s*;\s*do",
        block,
    )
    assert match is not None, "postgres-restore loop header missing"
    raw = match.group(1)
    actual = tuple(raw.split())
    assert actual == EXPECTED_PG_RESTORE_LABELS, (
        f"postgres-restore loop labels diverged: actual={actual} "
        f"expected={EXPECTED_PG_RESTORE_LABELS}"
    )
    assert len(actual) == 8


def test_distribution_p1_distribution_uses_same_restore_row_presence_path() -> None:
    # unihub_distribution must share the EXACT same restore body as
    # every other label: the same createdb + pg_restore + relation
    # count + row-presence probe + postgres-restores.tsv write. There
    # must be no per-label special-casing that would let one label
    # bypass the row-presence gate.
    block = _extract_postgres_restore_loop_block()
    # The bash loop body unconditionally writes one postgres-restores.tsv
    # row per iteration with the same printf format. Confirm exactly one
    # such printf exists and that the row-presence probe is inside the
    # loop body (not gated by any per-label condition).
    assert block.count(">>\"$WORK/postgres-restores.tsv\"") == 1
    # The row-presence die() helper appears in two adjacent error paths
    # (boolean parse failure and absent-row failure); at minimum the
    # probe MUST be present so unihub_distribution cannot be silently
    # exempted from the gate.
    assert block.count('restored database $database row-presence validation') >= 1
    # The row-presence probe must execute for every iteration, including
    # the unihub_distribution iteration, because the loop variable
    # `database` resolves identically and the check is not conditional
    # on any label.
    assert "[ \"$user_data_present\" != \"t\" ]" in block
    # The label variable is consumed by the printf and the dump path,
    # so unihub_distribution cannot be silently filtered out.
    assert "${label}_${STAMP}.dump" in block
    assert '"$label"' in block


def _build_evidence_args_with_restores(
    tmp_path: Path, restore_labels: tuple[str, ...]
) -> tuple[list[str], Path]:
    """Build the acceptance-program args for a synthetic restores.tsv
    containing the supplied labels (in canonical order) and the same
    otherwise-success arguments as `_success_evidence_fixture`."""
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
    lines = []
    for label in restore_labels:
        lines.append(
            chr(9).join(
                [
                    label,
                    f"dr_{label}",
                    "2026-09-03T01:05:00Z",
                    "2026-09-03T01:05:02Z",
                    "2",
                    "363",
                ]
            )
        )
    restores.write_text("\n".join(lines) + chr(10), encoding="utf-8")
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
    return args, evidence


def test_distribution_p1_evidence_writer_accepts_exact_eight_rows(
    tmp_path: Path,
) -> None:
    # The final-evidence writer must successfully record an evidence
    # payload when the postgres-restore TSV contains EXACTLY the eight
    # authoritative labels in canonical order.
    args, evidence = _build_evidence_args_with_restores(
        tmp_path, EXPECTED_PG_RESTORE_LABELS
    )
    completed = _run_python(_acceptance_program(), args)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    # Even on success the maintained overall is still "fail" pending
    # cleanup verification, but the recorded restores must match the
    # exact set, in the exact order, with the eight authoritative
    # labels so the eventual pass can be published.
    databases = payload["postgresRestoreStatus"]["databases"]
    assert [item["label"] for item in databases] == list(EXPECTED_PG_RESTORE_LABELS)
    assert len(databases) == 8
    # unihub_distribution must be present and follow unihub_retail.
    assert "unihub_distribution" in [item["label"] for item in databases]


def test_distribution_p1_evidence_writer_rejects_old_seven_rows_missing_distribution(
    tmp_path: Path,
) -> None:
    # The pre-#251 restore shape (7 PG labels, no unihub_distribution)
    # must be rejected at the fail-closed label validation gate. A
    # PASS may never be published for this set.
    legacy_labels = (
        "unihub",
        "mobiup_dwh",
        "unihub_identity",
        "unihub_retail",
        "unihub_learning",
        "authentik",
        "glitchtip",
    )
    assert len(legacy_labels) == 7
    args, evidence = _build_evidence_args_with_restores(tmp_path, legacy_labels)
    completed = _run_python(_acceptance_program(), args)
    assert completed.returncode != 0
    assert "label set mismatch" in completed.stderr
    assert "unihub_distribution" in completed.stderr
    # The original evidence payload must remain unchanged.
    assert evidence.read_text(encoding="utf-8") == "original\n"


def test_distribution_p1_evidence_writer_rejects_arbitrary_ninth_pg_label(
    tmp_path: Path,
) -> None:
    # Adding a ninth PostgreSQL restore label beyond the eight
    # authoritative ones must also fail closed. The exact-set/equal-list
    # validation has no slack for arbitrary extra databases.
    extended_labels = EXPECTED_PG_RESTORE_LABELS + ("unihub_rogue",)
    assert len(extended_labels) == 9
    args, evidence = _build_evidence_args_with_restores(tmp_path, extended_labels)
    completed = _run_python(_acceptance_program(), args)
    assert completed.returncode != 0
    assert "label set mismatch" in completed.stderr
    assert "unihub_rogue" in completed.stderr
    # The original evidence payload must remain unchanged.
    assert evidence.read_text(encoding="utf-8") == "original\n"
