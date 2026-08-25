from __future__ import annotations

from typing import Any

import pytest

from db.migration_runner import MigrationManifest


class _AtomicTransaction:
    def __init__(self, connection: "_AtomicConnection") -> None:
        self.connection = connection
        self.schema_snapshot = False
        self.rows_snapshot: dict[str, str] = {}

    async def __aenter__(self) -> None:
        self.schema_snapshot = self.connection.schema_changed
        self.rows_snapshot = dict(self.connection.rows)
        self.connection.events.append("transaction:start")
        return None

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is not None:
            self.connection.schema_changed = self.schema_snapshot
            self.connection.rows = self.rows_snapshot
            self.connection.events.append("transaction:rollback")
        else:
            self.connection.events.append("transaction:commit")


class _AtomicConnection:
    def __init__(self) -> None:
        self.schema_changed = False
        self.rows: dict[str, str] = {}
        self.events: list[str] = []

    def transaction(self) -> _AtomicTransaction:
        return _AtomicTransaction(self)

    async def execute(self, sql: str, *args: object) -> str:
        compact = " ".join(sql.split())
        if compact == "CREATE TABLE f3_atomic(id int)":
            self.schema_changed = True
            return "CREATE TABLE"
        if compact.startswith("INSERT INTO schema_migrations"):
            raise RuntimeError("simulated ledger failure")
        raise AssertionError(sql)


class _BackfillConnection:
    def __init__(self, filename: str, checksum: str | None) -> None:
        self.rows: dict[str, str | None] = {filename: checksum}
        self.executed_sql: list[str] = []
        self.read_sql: list[str] = []

    async def execute(self, sql: str, *args: object) -> str:
        self.executed_sql.append(sql)
        filename, checksum = str(args[0]), str(args[1])
        if "checksum IS NULL" in sql:
            if self.rows.get(filename) is None:
                self.rows[filename] = checksum
                return "UPDATE 1"
            return "UPDATE 0"
        self.rows[filename] = checksum
        return "UPDATE 1"

    async def fetchrow(self, sql: str, *args: object) -> dict[str, str | None] | None:
        self.read_sql.append(sql)
        filename = str(args[0])
        if filename not in self.rows:
            return None
        return {"checksum": self.rows[filename]}


async def _noop_activate(_connection: Any) -> None:
    return None


@pytest.mark.asyncio
async def test_transactional_migration_rolls_back_schema_when_ledger_insert_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.migration_runner as runner

    connection = _AtomicConnection()
    monkeypatch.setattr(runner, "_activate_migration_owner", _noop_activate)

    with pytest.raises(RuntimeError, match="simulated ledger failure"):
        await runner._apply_transactional_migration(  # type: ignore[arg-type]
            connection,
            filename="070_f3_atomic.sql",
            checksum="a" * 64,
            sql="CREATE TABLE f3_atomic(id int)",
        )

    assert connection.schema_changed is False
    assert connection.rows == {}
    assert connection.events == ["transaction:start", "transaction:rollback"]


@pytest.mark.asyncio
async def test_checksum_backfill_fails_closed_when_concurrent_value_conflicts() -> None:
    import db.migration_runner as runner

    filename = "001_first.sql"
    immutable_checksum = "c" * 64
    manifest_checksum = "b" * 64
    connection = _BackfillConnection(filename, immutable_checksum)
    manifest = MigrationManifest(
        "a" * 64,
        filename,
        {filename: manifest_checksum},
    )

    # Simulate a legacy NULL value observed in the earlier tracking snapshot,
    # followed by a conflicting non-NULL database value before backfill writes.
    applied: dict[str, str | None] = {filename: None}
    with pytest.raises(runner.MigrationError, match="Applied migration checksum mismatch"):
        await runner._backfill_missing_checksums(  # type: ignore[arg-type]
            connection,
            manifest,
            applied,
        )

    assert len(connection.executed_sql) == 1
    assert "AND checksum IS NULL" in connection.executed_sql[0]
    assert len(connection.read_sql) == 1
    assert connection.rows[filename] == immutable_checksum
    assert applied[filename] is None


@pytest.mark.asyncio
async def test_checksum_backfill_accepts_concurrent_expected_value() -> None:
    import db.migration_runner as runner

    filename = "001_first.sql"
    manifest_checksum = "b" * 64
    connection = _BackfillConnection(filename, manifest_checksum)
    manifest = MigrationManifest(
        "a" * 64,
        filename,
        {filename: manifest_checksum},
    )
    applied: dict[str, str | None] = {filename: None}

    await runner._backfill_missing_checksums(  # type: ignore[arg-type]
        connection,
        manifest,
        applied,
    )

    assert len(connection.executed_sql) == 1
    assert len(connection.read_sql) == 1
    assert applied[filename] == manifest_checksum
