from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "ops" / "k5-isolated-restore.sh"
EXPECTED_ENTRYPOINT_SHA256 = (
    "eca6b387773cadca3a6da3e9fd7a097d0133e2c8ef89597e5ecf63eb5f52b8d2"
)


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
        "wall-clock-from-payload-transfer-start-to-restored-service-acceptance",
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
