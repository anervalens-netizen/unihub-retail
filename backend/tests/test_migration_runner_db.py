from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import asyncpg
import pytest

from db.connection import get_database_url, get_pool
from db.migration_runner import run_migrations, verify_migrations_current
from db.migration_runner import (
    AUTHORITY_CUTOVER_BOOTSTRAP_ENV,
    AUTHORITY_CUTOVER_MIGRATIONS,
    MigrationError,
    MigrationManifest,
)


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
        owner_elevation_succeeds: bool = True,
        superuser: bool = True,
    ) -> None:
        self.has_schema = has_schema
        self.tracking_exists = tracking_exists
        self.checksum_exists = checksum_exists
        self.rows = rows or {}
        self.owner_elevation_succeeds = owner_elevation_succeeds
        self.superuser = superuser
        self.executed: list[str] = []
        self.closed = False

    async def fetchval(self, sql: str, *_args: object) -> bool:
        if "current_user = 'unihub_schema_owner'" in sql:
            return self.owner_elevation_succeeds
        if "sales_transactions" in sql:
            return self.has_schema and (
                self.tracking_exists if "schema_migrations" in sql else True
            )
        if "to_regclass('public.schema_migrations')" in sql:
            return self.tracking_exists
        if "information_schema.columns" in sql:
            return self.checksum_exists
        raise AssertionError(sql)

    async def fetchrow(self, _sql: str) -> dict[str, object]:
        return {
            "current_user": "unihub",
            "session_user": "unihub",
            "rolsuper": self.superuser,
        }

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
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL",
)
async def test_real_admin_authority_cutover_replays_exact_040_041(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.migration_runner as runner

    manifest = runner.load_migration_manifest()
    connection = await asyncpg.connect(get_database_url())
    try:
        assert await connection.fetchval(
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
        )
        await connection.execute(
            "DELETE FROM schema_migrations WHERE filename = ANY($1::text[])",
            sorted(AUTHORITY_CUTOVER_MIGRATIONS),
        )
    finally:
        await connection.close()

    monkeypatch.setenv(AUTHORITY_CUTOVER_BOOTSTRAP_ENV, "1")
    monkeypatch.delenv("UNIHUB_DB_PROCESS_AUTHORITY", raising=False)
    assert await run_migrations(get_database_url()) == [
        "040_db_authority_append_only.sql",
        "041_schema_owner_handoff.sql",
    ]

    connection = await asyncpg.connect(get_database_url())
    try:
        rows = await connection.fetch(
            "SELECT filename, checksum FROM schema_migrations "
            "WHERE filename = ANY($1::text[]) ORDER BY filename",
            sorted(AUTHORITY_CUTOVER_MIGRATIONS),
        )
        assert {row["filename"]: row["checksum"] for row in rows} == {
            name: manifest.checksums[name]
            for name in sorted(AUTHORITY_CUTOVER_MIGRATIONS)
        }
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_runner_prefers_explicit_migration_owner_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.migration_runner as runner

    manifest = runner.load_migration_manifest()
    connection = _Connection(rows=dict(manifest.checksums))
    connect = AsyncMock(return_value=connection)
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql://owner@localhost/db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://runtime@localhost/db")
    monkeypatch.setenv("DB_STATEMENT_TIMEOUT_MS", "91000")
    monkeypatch.setenv("DB_LOCK_TIMEOUT_MS", "9000")
    monkeypatch.setenv("DB_IDLE_TRANSACTION_TIMEOUT_MS", "45000")
    monkeypatch.setattr(runner.asyncpg, "connect", connect)

    assert await run_migrations() == []
    assert connect.await_args is not None
    assert connect.await_args.args[0] == "postgresql://owner@localhost/db"
    assert connect.await_args.kwargs["command_timeout"] == 91
    assert connect.await_args.kwargs["server_settings"] == {
        "application_name": "unihub-retail-migrations",
        "statement_timeout": "91000",
        "lock_timeout": "9000",
        "idle_in_transaction_session_timeout": "45000",
    }


@pytest.mark.asyncio
async def test_migration_authority_sets_local_stable_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.migration_runner as runner

    manifest = runner.load_migration_manifest()
    connection = _Connection(rows=dict(manifest.checksums))
    monkeypatch.setenv("UNIHUB_DB_PROCESS_AUTHORITY", "migrate")
    monkeypatch.setattr(runner, "verify_database_connection_authority", AsyncMock())
    monkeypatch.setattr(runner.asyncpg, "connect", _async_return(connection))

    assert await run_migrations("postgresql://unused") == []
    assert "SET LOCAL ROLE unihub_schema_owner" in connection.executed


@pytest.mark.asyncio
async def test_migration_authority_fails_if_local_owner_is_not_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.migration_runner as runner

    manifest = runner.load_migration_manifest()
    connection = _Connection(
        rows=dict(manifest.checksums), owner_elevation_succeeds=False
    )
    monkeypatch.setenv("UNIHUB_DB_PROCESS_AUTHORITY", "migrate")
    monkeypatch.setattr(runner, "verify_database_connection_authority", AsyncMock())
    monkeypatch.setattr(runner.asyncpg, "connect", _async_return(connection))

    with pytest.raises(MigrationError, match="schema-owner elevation"):
        await run_migrations("postgresql://unused")


@pytest.mark.asyncio
async def test_restricted_migration_authority_refuses_empty_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.migration_runner as runner

    connection = _Connection(has_schema=False)
    monkeypatch.setenv("UNIHUB_DB_PROCESS_AUTHORITY", "migrate")
    monkeypatch.setattr(runner, "verify_database_connection_authority", AsyncMock())
    monkeypatch.setattr(runner.asyncpg, "connect", _async_return(connection))

    with pytest.raises(MigrationError, match="administrative extension/schema preflight"):
        await run_migrations("postgresql://unused")


@pytest.mark.asyncio
async def test_admin_authority_cutover_bootstrap_accepts_only_pending_040_041(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.migration_runner as runner

    manifest = runner.load_migration_manifest()
    connection = _Connection(
        rows={
            name: checksum
            for name, checksum in manifest.checksums.items()
            if name not in AUTHORITY_CUTOVER_MIGRATIONS
        }
    )
    authority_verify = AsyncMock()
    monkeypatch.setenv(AUTHORITY_CUTOVER_BOOTSTRAP_ENV, "1")
    monkeypatch.setenv("UNIHUB_ENV", "production")
    monkeypatch.delenv("UNIHUB_DB_PROCESS_AUTHORITY", raising=False)
    monkeypatch.setattr(runner, "verify_database_connection_authority", authority_verify)
    monkeypatch.setattr(runner.asyncpg, "connect", _async_return(connection))

    assert await run_migrations("postgresql://unused") == [
        "040_db_authority_append_only.sql",
        "041_schema_owner_handoff.sql",
    ]
    assert connection.rows == manifest.checksums
    authority_verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_authority_cutover_bootstrap_flag_is_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.migration_runner as runner

    connection = _Connection()
    monkeypatch.setenv(AUTHORITY_CUTOVER_BOOTSTRAP_ENV, "true")
    monkeypatch.setattr(runner.asyncpg, "connect", _async_return(connection))

    with pytest.raises(MigrationError, match="must be exactly 1"):
        await run_migrations("postgresql://unused")


@pytest.mark.asyncio
async def test_admin_authority_cutover_rejects_process_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.migration_runner as runner

    connection = _Connection()
    monkeypatch.setenv(AUTHORITY_CUTOVER_BOOTSTRAP_ENV, "1")
    monkeypatch.setenv("UNIHUB_DB_PROCESS_AUTHORITY", "web")
    monkeypatch.setattr(runner.asyncpg, "connect", _async_return(connection))

    with pytest.raises(MigrationError, match="cannot be combined"):
        await run_migrations("postgresql://unused")


@pytest.mark.asyncio
async def test_admin_authority_cutover_rejects_untracked_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.migration_runner as runner

    connection = _Connection(has_schema=False, tracking_exists=False)
    monkeypatch.setenv(AUTHORITY_CUTOVER_BOOTSTRAP_ENV, "1")
    monkeypatch.delenv("UNIHUB_DB_PROCESS_AUTHORITY", raising=False)
    monkeypatch.setattr(runner.asyncpg, "connect", _async_return(connection))

    with pytest.raises(MigrationError, match="existing tracked application database"):
        await run_migrations("postgresql://unused")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("connection", "message"),
    [
        (_Connection(rows={}), "exactly migrations 040 and 041"),
        (_Connection(rows={}, superuser=False), "administrative superuser"),
    ],
)
async def test_admin_authority_cutover_bootstrap_fails_closed(
    connection: _Connection,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.migration_runner as runner

    manifest = runner.load_migration_manifest()
    if connection.superuser:
        connection.rows = dict(manifest.checksums)
    else:
        connection.rows = {
            name: checksum
            for name, checksum in manifest.checksums.items()
            if name not in AUTHORITY_CUTOVER_MIGRATIONS
        }
    monkeypatch.setenv(AUTHORITY_CUTOVER_BOOTSTRAP_ENV, "1")
    monkeypatch.delenv("UNIHUB_DB_PROCESS_AUTHORITY", raising=False)
    monkeypatch.setattr(runner.asyncpg, "connect", _async_return(connection))

    with pytest.raises(MigrationError, match=message):
        await run_migrations("postgresql://unused")


@pytest.mark.asyncio
async def test_runner_requires_migration_url_and_never_falls_back_to_runtime_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://runtime@localhost/db")

    with pytest.raises(MigrationError, match="MIGRATION_DATABASE_URL"):
        await run_migrations()


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


@pytest.mark.asyncio
async def test_fresh_database_replays_seed_migration_omitted_from_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import db.migration_runner as runner

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    names = [
        "001_schema.sql",
        "014_target_calculator_store_exclusions.sql",
        "022_baseline_end.sql",
        "023_later.sql",
    ]
    files = []
    for index, name in enumerate(names, start=1):
        path = migrations / name
        path.write_text(f"SELECT {index};", encoding="utf-8")
        files.append(path)
    baseline = tmp_path / "schema_v2.sql"
    baseline.write_text("CREATE TABLE example(id int);", encoding="utf-8")
    manifest = MigrationManifest(
        runner._sha256(baseline),
        "022_baseline_end.sql",
        {path.name: runner._sha256(path) for path in files},
    )
    connection = _Connection(has_schema=False)
    monkeypatch.setattr(runner, "load_migration_manifest", lambda: manifest)
    monkeypatch.setattr(runner, "get_migrations_dir", lambda: migrations)
    monkeypatch.setattr(runner, "get_schema_path", lambda: baseline)
    monkeypatch.setattr(runner.asyncpg, "connect", _async_return(connection))

    assert await run_migrations("postgresql://unused") == [
        "014_target_calculator_store_exclusions.sql",
        "023_later.sql",
    ]
    assert "SELECT 2;" in connection.executed
    assert connection.rows == manifest.checksums


@pytest.mark.asyncio
async def test_post_006_database_adopts_missing_unreplayable_tombstone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import db.migration_runner as runner

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    tombstone = migrations / "005_retail_ai_analysis_views.sql"
    prerequisite = migrations / "006_drop_ai_analysis_views.sql"
    tombstone.write_text("RAISE unreplayable;", encoding="utf-8")
    prerequisite.write_text("SELECT 6;", encoding="utf-8")
    baseline = tmp_path / "schema_v2.sql"
    baseline.write_text("SELECT 0;", encoding="utf-8")
    manifest = MigrationManifest(
        runner._sha256(baseline),
        prerequisite.name,
        {
            tombstone.name: runner._sha256(tombstone),
            prerequisite.name: runner._sha256(prerequisite),
        },
    )
    connection = _Connection(
        rows={prerequisite.name: manifest.checksums[prerequisite.name]}
    )
    monkeypatch.setattr(runner, "load_migration_manifest", lambda: manifest)
    monkeypatch.setattr(runner, "get_migrations_dir", lambda: migrations)
    monkeypatch.setattr(runner, "get_schema_path", lambda: baseline)
    monkeypatch.setattr(runner.asyncpg, "connect", _async_return(connection))

    assert await run_migrations("postgresql://unused") == []
    assert connection.rows == manifest.checksums
    assert "RAISE unreplayable;" not in connection.executed


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
