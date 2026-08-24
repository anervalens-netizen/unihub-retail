from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

import db.migration_runner as runner
import db.recover_online_index as recovery
from db.migration_runner import MigrationError, MigrationManifest


class _Tx:
    def __init__(self, connection: "_FakeConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> None:
        assert not self.connection.in_transaction
        self.connection.in_transaction = True

    async def __aexit__(self, exc_type: object, *_args: object) -> None:
        self.connection.in_transaction = False
        self.connection.events.append("rollback" if exc_type else "commit")


class _FakeConnection:
    def __init__(self) -> None:
        self.in_transaction = False
        self.events: list[str] = []
        self.rows: dict[str, str] = {}
        self.index_rows: list[dict[str, object]] = []
        self.existing_object = False
        self.timeout = "0"
        self.fail_statement: Exception | None = None
        self.fail_restore = False
        self.fail_reset = False
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    def transaction(self) -> _Tx:
        return _Tx(self)

    def is_in_transaction(self) -> bool:
        return self.in_transaction

    async def fetchval(self, sql: str, *args: object) -> Any:
        compact = " ".join(sql.split())
        if compact == "SHOW lock_timeout":
            return self.timeout
        if "set_config('lock_timeout'" in sql:
            value = str(args[0])
            if value == "0" and self.fail_restore:
                raise RuntimeError("lock timeout restore failed")
            self.timeout = value
            self.events.append(f"timeout:{value}")
            return value
        if "current_user = 'unihub_schema_owner'" in sql:
            return False
        if "current_user = session_user" in sql:
            if self.fail_reset:
                return False
            return True
        if "SELECT checksum FROM schema_migrations" in sql:
            return self.rows.get(str(args[0]))
        if "index_class.relname = $1" in sql and "EXISTS" in sql:
            return self.existing_object
        raise AssertionError(sql)

    async def fetch(self, sql: str, *args: object) -> list[dict[str, object]]:
        assert not self.in_transaction
        if "FROM pg_class AS index_class" in sql:
            return self.index_rows
        self.events.append(f"sql:{sql.strip()}")
        if self.fail_statement is not None:
            raise self.fail_statement
        return []

    async def execute(self, sql: str, *args: object) -> str:
        compact = " ".join(sql.split())
        if "pg_advisory_lock" in compact or "pg_advisory_unlock" in compact:
            self.events.append(compact)
            return "SELECT 1"
        if compact.startswith("INSERT INTO schema_migrations"):
            self.rows[str(args[0])] = str(args[1])
            return "INSERT 0 1"
        if compact.startswith("UPDATE schema_migrations SET checksum"):
            if self.rows.get(str(args[0])) != str(args[2]):
                return "UPDATE 0"
            self.rows[str(args[0])] = str(args[1])
            return "UPDATE 1"
        if compact == "RESET ROLE":
            self.events.append("role:reset")
            return "RESET"
        raise AssertionError(sql)


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("-- header\n/* note */\nCREATE INDEX CONCURRENTLY idx_sales ON sales_transactions (site_code);", ("idx_sales", "sales_transactions")),
        ("CREATE INDEX CONCURRENTLY idx_a ON t USING btree (id) WHERE id > 0", ("idx_a", "t")),
    ],
)
def test_controlled_cic_parser_accepts_only_safe_shape(sql: str, expected: tuple[str, str]) -> None:
    assert recovery.parse_controlled_cic(sql) == expected


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE UNIQUE INDEX CONCURRENTLY idx ON t (id)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx ON t (id)",
        "CREATE INDEX idx ON t (id)",
        'CREATE INDEX CONCURRENTLY "idx" ON t (id)',
        "CREATE INDEX CONCURRENTLY idx ON public.t (id)",
        "CREATE INDEX CONCURRENTLY idx ON t (id); DROP TABLE t",
        "CREATE INDEX CONCURRENTLY IDX ON t (id)",
    ],
)
def test_controlled_cic_parser_fails_closed(sql: str) -> None:
    with pytest.raises(MigrationError):
        recovery.parse_controlled_cic(sql)


@pytest.mark.asyncio
async def test_initial_preflight_happens_before_sentinel_and_rejects_any_object() -> None:
    connection = _FakeConnection()
    connection.existing_object = True
    with pytest.raises(MigrationError, match="already exists"):
        await recovery._apply_cic_online_migration(  # type: ignore[arg-type]
            connection,
            filename="070_idx.sql",
            checksum="a" * 64,
            sql="CREATE INDEX CONCURRENTLY idx ON t (id)",
            index_name="idx",
            table_name="t",
        )
    assert connection.rows == {}


@pytest.mark.asyncio
async def test_cic_timeout_is_restored_after_success_and_failure() -> None:
    connection = _FakeConnection()
    await recovery._execute_cic_statement(  # type: ignore[arg-type]
        connection, "CREATE INDEX CONCURRENTLY idx ON t (id)"
    )
    assert connection.timeout == "0"
    assert "timeout:5000ms" in connection.events
    assert connection.events[-1] == "timeout:0"

    connection = _FakeConnection()
    connection.fail_statement = RuntimeError("create failed")
    with pytest.raises(RuntimeError):
        await recovery._execute_cic_statement(  # type: ignore[arg-type]
            connection, "CREATE INDEX CONCURRENTLY idx ON t (id)"
        )
    assert connection.timeout == "0"

    connection = _FakeConnection()
    connection.fail_restore = True
    with pytest.raises(RuntimeError, match="lock timeout restore"):
        await recovery._execute_cic_statement(  # type: ignore[arg-type]
            connection, "CREATE INDEX CONCURRENTLY idx ON t (id)"
        )


@pytest.mark.asyncio
async def test_post_validation_requires_exact_catalog_flags() -> None:
    connection = _FakeConnection()
    connection.index_rows = [
        {
            "index_name": "idx",
            "table_name": "t",
            "indisvalid": True,
            "indisready": True,
            "indislive": True,
        }
    ]
    await recovery._cic_post_validate_index(  # type: ignore[arg-type]
        connection, "idx", "t"
    )
    connection.index_rows[0]["indisready"] = False
    with pytest.raises(MigrationError, match="catalog validation"):
        await recovery._cic_post_validate_index(  # type: ignore[arg-type]
            connection, "idx", "t"
        )


@pytest.mark.asyncio
async def test_role_reset_failure_is_fail_closed() -> None:
    connection = _FakeConnection()
    connection.fail_reset = True
    with pytest.raises(MigrationError, match="schema-owner reset"):
        await runner._reset_online_migration_owner(  # type: ignore[arg-type]
            connection, activated=True
        )
    assert "role:reset" in connection.events


@pytest.mark.asyncio
async def test_cic_success_finalizes_only_after_validation() -> None:
    connection = _FakeConnection()
    connection.index_rows = [
        {
            "index_name": "idx",
            "table_name": "t",
            "indisvalid": True,
            "indisready": True,
            "indislive": True,
        }
    ]
    checksum = "b" * 64
    await recovery._apply_cic_online_migration(  # type: ignore[arg-type]
        connection,
        filename="070_idx.sql",
        checksum=checksum,
        sql="CREATE INDEX CONCURRENTLY idx ON t (id)",
        index_name="idx",
        table_name="t",
    )
    assert connection.rows["070_idx.sql"] == checksum


@pytest.mark.asyncio
async def test_recovery_requires_exact_sentinel_and_manifest_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = MigrationManifest("a" * 64, "001.sql", {"070.sql": "b" * 64}, {"070.sql": "online"})
    monkeypatch.setattr(recovery, "load_migration_manifest", lambda: manifest)
    monkeypatch.setattr(recovery, "verify_migration_files", lambda _manifest: None)
    monkeypatch.setattr(recovery, "get_migrations_dir", lambda: Path("/tmp"))
    monkeypatch.setattr(recovery.asyncpg, "connect", AsyncMock())
    with pytest.raises(MigrationError, match="sentinel"):
        await recovery.recover_online_migration("070.sql", "postgresql://test")


@pytest.mark.asyncio
async def test_recovery_absent_creates_and_expected_existing_rebuilds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    connection.rows["070.sql"] = runner._online_recovery_checksum("b" * 64)
    monkeypatch.setattr(recovery, "load_migration_manifest", lambda: MigrationManifest("a" * 64, "001.sql", {"070.sql": "b" * 64}, {"070.sql": "online"}))
    monkeypatch.setattr(recovery, "verify_migration_files", lambda _manifest: None)
    sql_path = tmp_path / "070.sql"
    sql_path.write_text("CREATE INDEX CONCURRENTLY idx ON t (id)", encoding="utf-8")
    monkeypatch.setattr(recovery, "get_migrations_dir", lambda: tmp_path)
    monkeypatch.setattr(recovery.asyncpg, "connect", AsyncMock(return_value=connection))
    monkeypatch.setattr(recovery, "verify_database_connection_authority", AsyncMock())
    monkeypatch.setattr(recovery, "_cic_post_validate_index", AsyncMock())
    monkeypatch.setattr(recovery, "_finalize_online_migration", AsyncMock())
    monkeypatch.setattr(recovery, "_inspect_index", AsyncMock(return_value=None))
    await recovery.recover_online_migration("070.sql", "postgresql://test")
    recovery._inspect_index.assert_awaited_once()  # type: ignore[attr-defined]

    recovery._inspect_index.reset_mock()  # type: ignore[attr-defined]
    monkeypatch.setattr(recovery, "_inspect_index", AsyncMock(return_value=("i", "t")))
    drop_create = AsyncMock()
    monkeypatch.setattr(recovery, "_execute_cic_statement", drop_create)
    await recovery.recover_online_migration("070.sql", "postgresql://test")
    assert drop_create.await_count == 2
    assert drop_create.await_args_list[0].args[1].startswith("DROP INDEX CONCURRENTLY")


@pytest.mark.asyncio
async def test_recovery_refuses_unexpected_object_without_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    execute = AsyncMock()
    monkeypatch.setattr(recovery, "_execute_cic_statement", execute)
    monkeypatch.setattr(recovery, "_inspect_index", AsyncMock(return_value=("i", "other")))
    with pytest.raises(MigrationError, match="unexpected"):
        await recovery._recover_cic_index(  # type: ignore[arg-type]
            connection,
            index_name="idx",
            table_name="expected",
            sql="CREATE INDEX CONCURRENTLY idx ON expected (id)",
        )
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_normal_online_path_still_refuses_recovery_sentinel() -> None:
    manifest = MigrationManifest("a" * 64, "001.sql", {"070.sql": "b" * 64}, {"070.sql": "online"})
    with pytest.raises(MigrationError, match="recovery required"):
        runner._validate_applied(
            {"070.sql": runner._online_recovery_checksum("b" * 64)},
            manifest,
            allow_missing_checksums=False,
        )


@pytest.mark.skipif(os.getenv("UNIHUB_TEST_DATABASE") != "1", reason="requires isolated PostgreSQL")
@pytest.mark.asyncio
async def test_real_cic_runs_outside_transaction_and_validates_catalog() -> None:
    import asyncpg

    from db.connection import get_database_url

    connection = await asyncpg.connect(get_database_url())
    try:
        await connection.execute("DROP TABLE IF EXISTS f2_cic_table CASCADE")
        await connection.execute("CREATE TABLE f2_cic_table (id integer NOT NULL)")
        await recovery._execute_cic_statement(  # type: ignore[arg-type]
            connection, "CREATE INDEX CONCURRENTLY f2_cic_index ON f2_cic_table (id)"
        )
        assert not connection.is_in_transaction()
        await recovery._cic_post_validate_index(  # type: ignore[arg-type]
            connection, "f2_cic_index", "f2_cic_table"
        )
    finally:
        await connection.execute("DROP TABLE IF EXISTS f2_cic_table CASCADE")
        await connection.close()


@pytest.mark.parametrize("sql", ["", "/* unterminated", "CREATE INDEX CONCURRENTLY idx ON t."])
def test_parser_rejects_empty_unterminated_and_ambiguous_sql(sql: str) -> None:
    with pytest.raises(MigrationError):
        recovery.parse_controlled_cic(sql)


def test_cic_detector_routes_only_cic_attempts() -> None:
    assert recovery._CIC_ATTEMPT_RE.match(
        recovery._strip_leading_comments("-- c\nCREATE INDEX CONCURRENTLY idx ON t (id)")
    )
    assert recovery._CIC_ATTEMPT_RE.match(
        recovery._strip_leading_comments("CREATE UNIQUE INDEX CONCURRENTLY idx ON t (id)")
    )
    assert not recovery._CIC_ATTEMPT_RE.match(
        recovery._strip_leading_comments("CREATE INDEX idx ON t (id)")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        {"index_name": "idx", "table_name": "other", "indisvalid": True, "indisready": True, "indislive": True},
        {"index_name": "idx", "table_name": "t", "indisvalid": False, "indisready": True, "indislive": True},
        {"index_name": "idx", "table_name": "t", "indisvalid": True, "indisready": False, "indislive": True},
        {"index_name": "idx", "table_name": "t", "indisvalid": True, "indisready": True, "indislive": False},
    ],
)
async def test_post_validation_rejects_every_catalog_mismatch(row: dict[str, object]) -> None:
    connection = _FakeConnection()
    connection.index_rows = [row]
    with pytest.raises(MigrationError, match="catalog validation"):
        await recovery._cic_post_validate_index(  # type: ignore[arg-type]
            connection, "idx", "t"
        )


@pytest.mark.asyncio
async def test_post_validation_rejects_missing_or_duplicate_index() -> None:
    connection = _FakeConnection()
    row_sets: tuple[list[dict[str, object]], ...] = (
        [],
        [
            {"index_name": "idx"},
            {"index_name": "idx"},
        ],
    )
    for rows in row_sets:
        connection.index_rows = rows
        with pytest.raises(MigrationError, match="created exactly once"):
            await recovery._cic_post_validate_index(  # type: ignore[arg-type]
                connection, "idx", "t"
            )


@pytest.mark.asyncio
async def test_cic_attempt_failures_preserve_sentinel() -> None:
    connection = _FakeConnection()
    connection.fail_statement = RuntimeError("create failed")
    with pytest.raises(MigrationError, match="recovery required"):
        await recovery._apply_cic_online_migration(  # type: ignore[arg-type]
            connection,
            filename="070_idx.sql",
            checksum="c" * 64,
            sql="CREATE INDEX CONCURRENTLY idx ON t (id)",
            index_name="idx",
            table_name="t",
        )
    assert connection.rows["070_idx.sql"].startswith(runner.ONLINE_RECOVERY_PREFIX)

    connection = _FakeConnection()
    connection.index_rows = [{
        "index_name": "idx", "table_name": "t", "indisvalid": False,
        "indisready": True, "indislive": True,
    }]
    with pytest.raises(MigrationError, match="catalog validation"):
        await recovery._apply_cic_online_migration(  # type: ignore[arg-type]
            connection,
            filename="071_idx.sql",
            checksum="d" * 64,
            sql="CREATE INDEX CONCURRENTLY idx ON t (id)",
            index_name="idx",
            table_name="t",
        )
    assert connection.rows["071_idx.sql"].startswith(runner.ONLINE_RECOVERY_PREFIX)


@pytest.mark.asyncio
async def test_recovery_refuses_non_index_object_without_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    drop = AsyncMock()
    monkeypatch.setattr(recovery, "_execute_cic_statement", drop)
    monkeypatch.setattr(recovery, "_inspect_index", AsyncMock(return_value=("r", "t")))
    with pytest.raises(MigrationError, match="non-index"):
        await recovery._recover_cic_index(  # type: ignore[arg-type]
            connection,
            index_name="idx",
            table_name="t",
            sql="CREATE INDEX CONCURRENTLY idx ON t (id)",
        )
    drop.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_online_cic_uses_controlled_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = tmp_path / "070_idx.sql"
    migration.write_text("CREATE INDEX CONCURRENTLY idx ON t (id)", encoding="utf-8")
    manifest = MigrationManifest("a" * 64, "001.sql", {migration.name: "b" * 64}, {migration.name: "online"})
    connection = _FakeConnection()
    apply = AsyncMock()
    monkeypatch.setattr(runner, "get_migrations_dir", lambda: tmp_path)
    monkeypatch.setattr(recovery, "_apply_cic_online_migration", apply)
    applied = await runner._apply_pending_migrations(  # type: ignore[arg-type]
        connection, manifest, {}, cutover_bootstrap=False
    )
    assert applied == [migration.name]
    apply.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["missing.sql", "070.sql"])
async def test_recovery_rejects_unknown_or_non_online_filename(
    filename: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = MigrationManifest("a" * 64, "001.sql", {"070.sql": "b" * 64}, {})
    monkeypatch.setattr(recovery, "load_migration_manifest", lambda: manifest)
    monkeypatch.setattr(recovery, "verify_migration_files", lambda _manifest: None)
    with pytest.raises(MigrationError, match="manifest|online"):
        await recovery.recover_online_migration(filename, "postgresql://test")


def test_manifest_loader_and_file_verifier_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(MigrationError, match="manifest is invalid"):
        runner.load_migration_manifest(invalid)
    bad_baseline = tmp_path / "bad-baseline.json"
    bad_baseline.write_text(
        '{"baseline":{"file":"schema_v2.sql","sha256":"'
        + "a" * 64
        + '","incorporated_through":"missing.sql"},'
        '"migrations":{"001.sql":"'
        + "b" * 64
        + '"},"version":1}',
        encoding="utf-8",
    )
    with pytest.raises(MigrationError, match="manifest is invalid"):
        runner.load_migration_manifest(bad_baseline)

    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    migration = migration_dir / "001.sql"
    migration.write_text("SELECT 1", encoding="utf-8")
    schema = tmp_path / "schema_v2.sql"
    schema.write_text("schema", encoding="utf-8")
    monkeypatch.setattr(runner, "get_migrations_dir", lambda: migration_dir)
    monkeypatch.setattr(runner, "get_schema_path", lambda: schema)
    manifest = MigrationManifest("0" * 64, "001.sql", {"001.sql": "1" * 64})
    with pytest.raises(MigrationError, match="files do not match"):
        runner.verify_migration_files(manifest)
    matching = MigrationManifest(
        runner._sha256(schema), "001.sql", {"001.sql": runner._sha256(migration)}
    )
    runner.verify_migration_files(matching)
    with pytest.raises(MigrationError, match="Frozen schema"):
        runner.verify_migration_files(
            MigrationManifest("2" * 64, "001.sql", {"001.sql": runner._sha256(migration)})
        )


def test_manifest_validation_rejects_unknown_and_wrong_checksum() -> None:
    manifest = MigrationManifest("a" * 64, "001.sql", {"001.sql": "b" * 64})
    with pytest.raises(MigrationError, match="absent from the manifest"):
        runner._validate_applied(
            {"unknown.sql": "c" * 64}, manifest, allow_missing_checksums=False
        )
    with pytest.raises(MigrationError, match="checksum mismatch"):
        runner._validate_applied(
            {"001.sql": "c" * 64}, manifest, allow_missing_checksums=False
        )


@pytest.mark.skipif(os.getenv("UNIHUB_TEST_DATABASE") != "1", reason="requires isolated PostgreSQL")
@pytest.mark.asyncio
async def test_real_recovery_rebuilds_existing_index_and_preserves_failed_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncpg

    from db.connection import get_database_url

    database_url = get_database_url()
    success_file = "f2_recovery_real.sql"
    failure_file = "f2_recovery_failure.sql"
    success_checksum = "e" * 64
    failure_checksum = "f" * 64
    success_sql = "CREATE INDEX CONCURRENTLY f2_recovery_index ON f2_recovery_table (id)"
    failure_sql = "CREATE INDEX CONCURRENTLY f2_recovery_conflict_index ON f2_recovery_table (id)"
    manifest = MigrationManifest(
        "a" * 64,
        "001.sql",
        {success_file: success_checksum, failure_file: failure_checksum},
        {success_file: "online", failure_file: "online"},
    )
    (tmp_path / success_file).write_text(success_sql, encoding="utf-8")
    (tmp_path / failure_file).write_text(failure_sql, encoding="utf-8")
    monkeypatch.setattr(recovery, "load_migration_manifest", lambda: manifest)
    monkeypatch.setattr(recovery, "verify_migration_files", lambda _manifest: None)
    monkeypatch.setattr(recovery, "get_migrations_dir", lambda: tmp_path)

    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute("DROP TABLE IF EXISTS f2_recovery_table CASCADE")
        await connection.execute("DROP TABLE IF EXISTS f2_recovery_other CASCADE")
        await connection.execute("CREATE TABLE f2_recovery_table (id integer NOT NULL)")
        await connection.execute("CREATE TABLE f2_recovery_other (id integer NOT NULL)")
        await connection.execute(
            "CREATE INDEX CONCURRENTLY f2_recovery_index ON f2_recovery_table (id)"
        )
        await connection.execute(
            "CREATE INDEX CONCURRENTLY f2_recovery_conflict_index ON f2_recovery_other (id)"
        )
        await connection.execute(
            "INSERT INTO schema_migrations (filename, checksum) VALUES ($1, $2), ($3, $4)",
            success_file,
            runner._online_recovery_checksum(success_checksum),
            failure_file,
            runner._online_recovery_checksum(failure_checksum),
        )
        await connection.execute(
            "INSERT INTO schema_migrations (filename, checksum) VALUES ($1, $2)",
            "f2_recovery_control.sql",
            "control-checksum",
        )

        await recovery.recover_online_migration(success_file, database_url)
        success_row = await connection.fetchrow(
            "SELECT checksum FROM schema_migrations WHERE filename = $1", success_file
        )
        success_catalog = await connection.fetchrow(
            """
            SELECT table_class.relname AS table_name,
                   pg_index.indisvalid, pg_index.indisready, pg_index.indislive
            FROM pg_class AS index_class
            JOIN pg_index ON pg_index.indexrelid = index_class.oid
            JOIN pg_class AS table_class ON table_class.oid = pg_index.indrelid
            WHERE index_class.relname = 'f2_recovery_index'
            """
        )
        assert success_row["checksum"] == success_checksum
        assert success_catalog["table_name"] == "f2_recovery_table"
        assert all(success_catalog[key] for key in ("indisvalid", "indisready", "indislive"))
        assert not connection.is_in_transaction()

        with pytest.raises(MigrationError, match="recovery failed"):
            await recovery.recover_online_migration(failure_file, database_url)
        failure_row = await connection.fetchrow(
            "SELECT checksum FROM schema_migrations WHERE filename = $1", failure_file
        )
        control_row = await connection.fetchrow(
            "SELECT checksum FROM schema_migrations WHERE filename = $1",
            "f2_recovery_control.sql",
        )
        assert failure_row["checksum"] == runner._online_recovery_checksum(failure_checksum)
        assert control_row["checksum"] == "control-checksum"
    finally:
        await connection.execute(
            "DELETE FROM schema_migrations WHERE filename IN ($1, $2, $3)",
            success_file,
            failure_file,
            "f2_recovery_control.sql",
        )
        await connection.execute("DROP TABLE IF EXISTS f2_recovery_table CASCADE")
        await connection.execute("DROP TABLE IF EXISTS f2_recovery_other CASCADE")
        await connection.close()
