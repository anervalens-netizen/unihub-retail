from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import asyncpg
import pytest

from db.migration_runner import (
    ONLINE_EXECUTION_MODE,
    ONLINE_RECOVERY_PREFIX,
    MigrationError,
    MigrationManifest,
    _apply_online_migration,
    _execute_online_statement,
    _online_recovery_checksum,
    _validate_applied,
    load_migration_manifest,
)


class _Transaction:
    def __init__(self, connection: "_OnlineConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> None:
        assert not self.connection.in_transaction
        self.connection.in_transaction = True
        self.connection.events.append("transaction:start")
        return None

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.connection.events.append(
            "transaction:rollback" if exc_type is not None else "transaction:commit"
        )
        self.connection.in_transaction = False
        self.connection.local_role_active = False


class _OnlineConnection:
    def __init__(self, *, online_failure: Exception | None = None) -> None:
        self.in_transaction = False
        self.online_failure = online_failure
        self.rows: dict[str, str] = {}
        self.events: list[str] = []
        self.role_active = False
        self.local_role_active = False

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    def is_in_transaction(self) -> bool:
        return self.in_transaction

    async def fetchval(self, sql: str, *_args: object) -> bool:
        if "current_user = 'unihub_schema_owner'" in sql:
            return self.role_active or self.local_role_active
        if "current_user = session_user" in sql:
            return not self.role_active
        raise AssertionError(sql)

    async def execute(self, sql: str, *args: object) -> str:
        compact = " ".join(sql.split())
        if compact == "SET LOCAL ROLE unihub_schema_owner":
            assert self.in_transaction
            self.local_role_active = True
            self.events.append("role:set-local")
            return "SET"
        if compact == "SET ROLE unihub_schema_owner":
            assert not self.in_transaction
            self.role_active = True
            self.events.append("role:set-session")
            return "SET"
        if compact == "RESET ROLE":
            self.role_active = False
            self.events.append("role:reset")
            return "RESET"
        if compact.startswith("INSERT INTO schema_migrations"):
            assert self.in_transaction
            filename, checksum = str(args[0]), str(args[1])
            assert filename not in self.rows
            self.rows[filename] = checksum
            self.events.append(
                "recovery:mark"
                if checksum.startswith(ONLINE_RECOVERY_PREFIX)
                else "ledger:insert"
            )
            return "INSERT 0 1"
        if compact.startswith("UPDATE schema_migrations SET checksum = $2"):
            assert self.in_transaction
            filename, checksum, marker = map(str, args[:3])
            if self.rows.get(filename) != marker:
                return "UPDATE 0"
            self.rows[filename] = checksum
            self.events.append("ledger:finalize")
            return "UPDATE 1"
        raise AssertionError(sql)

    async def fetch(self, sql: str, *_args: object) -> list[dict[str, Any]]:
        assert not self.in_transaction
        self.events.append("online:execute")
        if self.online_failure is not None:
            raise self.online_failure
        return []


def _manifest_payload(*, execution_modes: dict[str, str]) -> dict[str, object]:
    return {
        "version": 2,
        "baseline": {
            "file": "schema_v2.sql",
            "sha256": "a" * 64,
            "incorporated_through": "001_first.sql",
        },
        "migrations": {
            "001_first.sql": "b" * 64,
            "002_online.sql": "c" * 64,
        },
        "execution_modes": execution_modes,
    }


def _online_manifest(*, checksum: str = "c" * 64) -> MigrationManifest:
    return MigrationManifest(
        "a" * 64,
        "001_first.sql",
        {
            "001_first.sql": "b" * 64,
            "070_online.sql": checksum,
        },
        {"070_online.sql": ONLINE_EXECUTION_MODE},
    )


def test_manifest_v2_keeps_transactional_default_and_explicit_online(
    tmp_path: Path,
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            _manifest_payload(
                execution_modes={"002_online.sql": ONLINE_EXECUTION_MODE}
            )
        ),
        encoding="utf-8",
    )

    manifest = load_migration_manifest(path)

    assert manifest.execution_mode("001_first.sql") == "transactional"
    assert manifest.execution_mode("002_online.sql") == ONLINE_EXECUTION_MODE


@pytest.mark.parametrize(
    "execution_modes",
    [
        {"999_unknown.sql": ONLINE_EXECUTION_MODE},
        {"002_online.sql": "maintenance-window"},
        {"002_online.sql": "transactional"},
    ],
)
def test_manifest_rejects_unknown_or_implicit_execution_overrides(
    tmp_path: Path,
    execution_modes: dict[str, str],
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(_manifest_payload(execution_modes=execution_modes)),
        encoding="utf-8",
    )

    with pytest.raises(MigrationError, match="manifest is invalid"):
        load_migration_manifest(path)


def test_manifest_v1_is_rejected_after_execution_contract_upgrade(tmp_path: Path) -> None:
    payload = _manifest_payload(execution_modes={})
    payload["version"] = 1
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MigrationError, match="manifest is invalid"):
        load_migration_manifest(path)


@pytest.mark.asyncio
async def test_online_migration_marks_before_execution_and_finalizes_same_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNIHUB_DB_PROCESS_AUTHORITY", "migrate")
    connection = _OnlineConnection()
    checksum = "d" * 64

    await _apply_online_migration(  # type: ignore[arg-type]
        connection,
        filename="070_online.sql",
        checksum=checksum,
        sql="VACUUM schema_migrations",
    )

    assert connection.rows == {"070_online.sql": checksum}
    assert connection.role_active is False
    assert connection.events.index("recovery:mark") < connection.events.index(
        "online:execute"
    )
    assert connection.events.index("online:execute") < connection.events.index(
        "ledger:finalize"
    )
    assert connection.events[-2:] == ["ledger:finalize", "transaction:commit"]


@pytest.mark.asyncio
async def test_online_failure_leaves_sentinel_in_canonical_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNIHUB_DB_PROCESS_AUTHORITY", "migrate")
    connection = _OnlineConnection(online_failure=RuntimeError("simulated"))
    checksum = "e" * 64

    with pytest.raises(MigrationError, match="recovery required for 070_online.sql"):
        await _apply_online_migration(  # type: ignore[arg-type]
            connection,
            filename="070_online.sql",
            checksum=checksum,
            sql="VACUUM schema_migrations",
        )

    assert connection.rows == {
        "070_online.sql": _online_recovery_checksum(checksum),
    }
    assert connection.role_active is False
    assert "role:reset" in connection.events
    assert "ledger:finalize" not in connection.events


def test_existing_online_recovery_sentinel_blocks_automatic_retry() -> None:
    checksum = "c" * 64
    manifest = _online_manifest(checksum=checksum)

    with pytest.raises(MigrationError, match="recovery required.*070_online.sql"):
        _validate_applied(
            {"070_online.sql": _online_recovery_checksum(checksum)},
            manifest,
            allow_missing_checksums=False,
        )


def test_recovery_sentinel_is_bound_to_manifest_checksum() -> None:
    manifest = _online_manifest(checksum="c" * 64)

    with pytest.raises(MigrationError, match="does not match the immutable manifest"):
        _validate_applied(
            {"070_online.sql": _online_recovery_checksum("d" * 64)},
            manifest,
            allow_missing_checksums=False,
        )


def test_recovery_sentinel_cannot_be_bypassed_by_removing_online_mode() -> None:
    checksum = "c" * 64
    manifest = MigrationManifest(
        "a" * 64,
        "001_first.sql",
        {
            "001_first.sql": "b" * 64,
            "070_online.sql": checksum,
        },
    )

    with pytest.raises(MigrationError, match="does not match the immutable manifest"):
        _validate_applied(
            {"070_online.sql": _online_recovery_checksum(checksum)},
            manifest,
            allow_missing_checksums=False,
        )


@pytest.mark.asyncio
async def test_online_executor_refuses_active_transaction() -> None:
    connection = _OnlineConnection()
    connection.in_transaction = True

    with pytest.raises(MigrationError, match="requires no active transaction"):
        await _execute_online_statement(  # type: ignore[arg-type]
            connection,
            "VACUUM schema_migrations",
        )

    assert "online:execute" not in connection.events


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL",
)
async def test_real_online_executor_accepts_command_forbidden_in_transaction() -> None:
    from db.connection import get_database_url

    connection = await asyncpg.connect(get_database_url())
    try:
        assert not connection.is_in_transaction()
        await _execute_online_statement(connection, "VACUUM schema_migrations")
        assert not connection.is_in_transaction()
    finally:
        await connection.close()
