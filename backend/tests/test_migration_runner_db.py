from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from db.connection import get_database_url, get_pool
from db.migration_runner import run_migrations, verify_migrations_current
from db.migration_runner import MigrationError, MigrationManifest


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Connection:
    def __init__(
        self,
        *,
        has_schema: bool = True,
        tracking_exists: bool = True,
        checksum_exists: bool = True,
        rows: dict[str, str | None] | None = None,
    ) -> None:
        self.has_schema = has_schema
        self.tracking_exists = tracking_exists
        self.checksum_exists = checksum_exists
        self.rows = rows or {}
        self.executed: list[str] = []
        self.closed = False

    async def fetchval(self, sql: str) -> bool:
        if "sales_transactions" in sql:
            return self.has_schema
        if "to_regclass('public.schema_migrations')" in sql:
            return self.tracking_exists
        if "information_schema.columns" in sql:
            return self.checksum_exists
        raise AssertionError(sql)

    async def fetch(self, _sql: str) -> list[dict[str, str | None]]:
        return [
            {"filename": filename, "checksum": checksum}
            for filename, checksum in sorted(self.rows.items())
        ]

    async def execute(self, sql: str, *args: object) -> str:
        self.executed.append(sql)
        if "UPDATE schema_migrations SET checksum" in sql:
            self.rows[str(args[0])] = str(args[1])
        elif "INSERT INTO schema_migrations" in sql and args:
            self.rows[str(args[0])] = str(args[1])
        return "OK"

    def transaction(self) -> _Transaction:
        return _Transaction()

    async def close(self) -> None:
        self.closed = True


class _Acquire:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Pool:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)


@pytest.mark.asyncio
async def test_current_database_is_read_only_verified() -> None:
    await verify_migrations_current(await get_pool())


@pytest.mark.asyncio
async def test_runner_is_idempotent_and_advisory_locked() -> None:
    results = await asyncio.gather(
        run_migrations(get_database_url()),
        run_migrations(get_database_url()),
    )
    assert results == [[], []]


@pytest.mark.asyncio
async def test_existing_database_backfills_checksums_and_applies_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import db.migration_runner as runner

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    first = migrations / "001_first.sql"
    second = migrations / "002_second.sql"
    first.write_text("SELECT 1;", encoding="utf-8")
    second.write_text("SELECT 2;", encoding="utf-8")
    baseline = tmp_path / "schema_v2.sql"
    baseline.write_text("SELECT 0;", encoding="utf-8")
    manifest = MigrationManifest(
        runner._sha256(baseline),
        first.name,
        {first.name: runner._sha256(first), second.name: runner._sha256(second)},
    )
    connection = _Connection(rows={first.name: None})
    monkeypatch.setattr(runner, "load_migration_manifest", lambda: manifest)
    monkeypatch.setattr(runner, "get_migrations_dir", lambda: migrations)
    monkeypatch.setattr(runner, "get_schema_path", lambda: baseline)
    monkeypatch.setattr(runner.asyncpg, "connect", _async_return(connection))

    assert await run_migrations("postgresql://unused") == [second.name]
    assert connection.rows == manifest.checksums
    assert connection.closed


@pytest.mark.asyncio
async def test_fresh_database_uses_frozen_baseline_then_later_migrations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import db.migration_runner as runner

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    first = migrations / "001_first.sql"
    second = migrations / "002_second.sql"
    first.write_text("SELECT 1;", encoding="utf-8")
    second.write_text("SELECT 2;", encoding="utf-8")
    baseline = tmp_path / "schema_v2.sql"
    baseline.write_text("CREATE TABLE example(id int);", encoding="utf-8")
    manifest = MigrationManifest(
        runner._sha256(baseline),
        first.name,
        {first.name: runner._sha256(first), second.name: runner._sha256(second)},
    )
    connection = _Connection(has_schema=False)
    monkeypatch.setattr(runner, "load_migration_manifest", lambda: manifest)
    monkeypatch.setattr(runner, "get_migrations_dir", lambda: migrations)
    monkeypatch.setattr(runner, "get_schema_path", lambda: baseline)
    monkeypatch.setattr(runner.asyncpg, "connect", _async_return(connection))

    assert await run_migrations("postgresql://unused") == [second.name]
    assert connection.rows == manifest.checksums
    assert baseline.read_text(encoding="utf-8") in connection.executed


def _async_return(value: Any):
    async def return_value(*_args: object, **_kwargs: object) -> Any:
        return value

    return return_value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "connection,message",
    [
        (_Connection(tracking_exists=False), "tracking is not initialized"),
        (_Connection(checksum_exists=False), "checksum tracking is not initialized"),
        (_Connection(rows={}), "pending migrations"),
    ],
)
async def test_read_only_verification_rejects_incomplete_tracking(
    monkeypatch: pytest.MonkeyPatch,
    connection: _Connection,
    message: str,
) -> None:
    import db.migration_runner as runner

    manifest = MigrationManifest("a" * 64, "001_first.sql", {"001_first.sql": "b" * 64})
    monkeypatch.setattr(runner, "load_migration_manifest", lambda: manifest)
    monkeypatch.setattr(runner, "verify_migration_files", lambda _manifest: None)
    with pytest.raises(MigrationError, match=message):
        await verify_migrations_current(_Pool(connection))  # type: ignore[arg-type]
