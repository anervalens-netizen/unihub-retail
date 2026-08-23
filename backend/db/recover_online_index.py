"""Explicit operator recovery for a controlled online migration.

F2 keeps recovery out of ``run_migrations``. A normal migration run never
auto-recovers an online-recovery sentinel; the operator invokes
:func:`recover_online_migration` with the exact manifest filename.
"""
from __future__ import annotations

import os
import re

import asyncpg

from db.connection import (
    database_connection_options,
    verify_database_connection_authority,
)
from db.migration_runner import (
    MIGRATION_ADVISORY_LOCK_ID,
    ONLINE_EXECUTION_MODE,
    MigrationError,
    _activate_online_migration_owner,
    _finalize_online_migration,
    _mark_online_recovery,
    _online_recovery_checksum,
    _reset_online_migration_owner,
    get_migrations_dir,
    load_migration_manifest,
    verify_migration_files,
)

CIC_LOCK_TIMEOUT_MS = 5000
_SAFE_IDENTIFIER_RE = re.compile(r"[a-z_][a-z0-9_]*")
_CIC_ATTEMPT_RE = re.compile(
    r"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+CONCURRENTLY\b", re.IGNORECASE
)
_CIC_STATEMENT_RE = re.compile(
    r"^\s*CREATE\s+INDEX\s+CONCURRENTLY\s+"
    r"(?P<index>[a-z_][a-z0-9_]*)\s+ON\s+"
    r"(?P<table>[a-z_][a-z0-9_]*)(?P<tail>.*)$",
    re.DOTALL | re.IGNORECASE,
)


def _strip_leading_comments(sql: str) -> str:
    """Remove PostgreSQL comments and whitespace from the front of SQL."""
    s = sql
    while True:
        s = s.lstrip()
        if not s:
            return s
        if s.startswith("--"):
            newline = s.find("\n")
            if newline == -1:
                return ""
            s = s[newline + 1 :]
            continue
        if s.startswith("/*"):
            end = s.find("*/")
            if end == -1:
                raise MigrationError("Migration SQL contains an unterminated block comment")
            s = s[end + 2 :]
            continue
        return s


def _looks_like_cic_statement(sql: str) -> bool:
    """Detect CIC syntax so the strict parser can route it fail-closed."""
    return bool(_CIC_ATTEMPT_RE.match(_strip_leading_comments(sql)))


def parse_controlled_cic(sql: str) -> tuple[str, str]:
    """Parse one standalone non-unique CIC with safe unquoted identifiers."""
    stmt = _strip_leading_comments(sql).strip()
    if not stmt:
        raise MigrationError("Migration SQL is empty")
    if stmt.endswith(";"):
        stmt = stmt[:-1].rstrip()
    if ";" in stmt:
        raise MigrationError("Multiple top-level SQL statements are not allowed")
    match = _CIC_STATEMENT_RE.match(stmt)
    if not match:
        raise MigrationError(
            "Migration SQL is not a standalone non-unique "
            "CREATE INDEX CONCURRENTLY statement"
        )
    index_name = match.group("index")
    table_name = match.group("table")
    if not _SAFE_IDENTIFIER_RE.fullmatch(index_name) or not _SAFE_IDENTIFIER_RE.fullmatch(
        table_name
    ):
        raise MigrationError(
            "Quoted or ambiguous index/table identifiers are not allowed"
        )
    if match.group("tail").lstrip().startswith("."):
        raise MigrationError(
            "Quoted or ambiguous index/table identifiers are not allowed"
        )
    return index_name, table_name


async def _cic_session_lock_timeout(connection: asyncpg.Connection) -> str:
    value = await connection.fetchval("SHOW lock_timeout")
    return str(value)


async def _cic_set_lock_timeout(connection: asyncpg.Connection, value: str) -> None:
    """Set a session-level lock timeout using a bound value."""
    await connection.fetchval("SELECT set_config('lock_timeout', $1, false)", value)


async def _execute_cic_statement(connection: asyncpg.Connection, sql: str) -> None:
    """Run one controlled CIC statement outside a transaction and restore timeout."""
    if connection.is_in_transaction():
        raise MigrationError("Controlled online migration requires no active transaction")
    prior_timeout = await _cic_session_lock_timeout(connection)
    try:
        await _cic_set_lock_timeout(connection, f"{CIC_LOCK_TIMEOUT_MS}ms")
        await connection.fetch(sql)
    finally:
        await _cic_set_lock_timeout(connection, prior_timeout)
    if connection.is_in_transaction():
        raise MigrationError("Controlled online migration left an active transaction")


async def _cic_preflight_index_absent(
    connection: asyncpg.Connection, index_name: str
) -> None:
    """Fail closed before writing a sentinel if the public name already exists."""
    exists = await connection.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_class AS index_class
            JOIN pg_namespace AS namespace ON namespace.oid = index_class.relnamespace
            WHERE index_class.relname = $1
              AND namespace.nspname = 'public'
        )
        """,
        index_name,
    )
    if exists:
        raise MigrationError(
            "Online migration candidate index already exists before it can be created"
        )


async def _cic_post_validate_index(
    connection: asyncpg.Connection,
    index_name: str,
    table_name: str,
) -> None:
    """Require the exact valid/ready/live index on the exact expected table."""
    rows = await connection.fetch(
        """
        SELECT index_class.relname AS index_name,
               table_class.relname AS table_name,
               pg_index.indisvalid AS indisvalid,
               pg_index.indisready AS indisready,
               pg_index.indislive AS indislive
        FROM pg_class AS index_class
        JOIN pg_index ON pg_index.indexrelid = index_class.oid
        JOIN pg_class AS table_class ON table_class.oid = pg_index.indrelid
        JOIN pg_namespace AS namespace ON namespace.oid = index_class.relnamespace
        WHERE index_class.relname = $1
          AND index_class.relkind = 'i'
          AND namespace.nspname = 'public'
        """,
        index_name,
    )
    if len(rows) != 1:
        raise MigrationError("Online migration index was not created exactly once")
    row = rows[0]
    if (
        str(row["index_name"]) != index_name
        or str(row["table_name"]) != table_name
        or not bool(row["indisvalid"])
        or not bool(row["indisready"])
        or not bool(row["indislive"])
    ):
        raise MigrationError("Online migration index catalog validation failed")


async def _apply_cic_online_migration(
    connection: asyncpg.Connection,
    *,
    filename: str,
    checksum: str,
    sql: str,
    index_name: str,
    table_name: str,
) -> None:
    await _cic_preflight_index_absent(connection, index_name)
    await _mark_online_recovery(connection, filename, checksum)
    role_activated = False
    try:
        role_activated = await _activate_online_migration_owner(connection)
        await _execute_cic_statement(connection, sql)
    except Exception as exc:
        raise MigrationError(
            f"Online migration failed; recovery required for {filename}"
        ) from exc
    finally:
        await _reset_online_migration_owner(connection, activated=role_activated)
    await _cic_post_validate_index(connection, index_name, table_name)
    await _finalize_online_migration(connection, filename, checksum)


async def _inspect_index(
    connection: asyncpg.Connection, index_name: str
) -> tuple[str, str] | None:
    """Return ``(relkind, table_name)`` for an exact public relation, or ``None``."""
    rows = await connection.fetch(
        """
        SELECT index_class.relkind AS relkind,
               table_class.relname AS table_name
        FROM pg_class AS index_class
        LEFT JOIN pg_index ON pg_index.indexrelid = index_class.oid
        LEFT JOIN pg_class AS table_class ON table_class.oid = pg_index.indrelid
        JOIN pg_namespace AS namespace ON namespace.oid = index_class.relnamespace
        WHERE index_class.relname = $1
          AND namespace.nspname = 'public'
        """,
        index_name,
    )
    if not rows:
        return None
    if len(rows) != 1:
        raise MigrationError("Recovery candidate index is ambiguous")
    row = rows[0]
    raw_relkind = row["relkind"]
    relkind = raw_relkind.decode("ascii") if isinstance(raw_relkind, bytes) else str(raw_relkind)
    return relkind, str(row["table_name"])


async def _recover_cic_index(
    connection: asyncpg.Connection,
    *,
    index_name: str,
    table_name: str,
    sql: str,
) -> None:
    indexed = await _inspect_index(connection, index_name)
    if indexed is None:
        await _execute_cic_statement(connection, sql)
        return
    relkind, existing_table = indexed
    if relkind != "i":
        raise MigrationError("Unexpected non-index object; refusing to drop")
    if existing_table != table_name:
        raise MigrationError("Existing index targets an unexpected table; refusing to drop")
    await _execute_cic_statement(connection, f"DROP INDEX CONCURRENTLY {index_name}")
    await _execute_cic_statement(connection, sql)


async def recover_online_migration(
    filename: str,
    database_url: str | None = None,
) -> None:
    """Recover one controlled online migration that left its recovery sentinel."""
    manifest = load_migration_manifest()
    verify_migration_files(manifest)
    if filename not in manifest.checksums:
        raise MigrationError("Recovery filename is not present in the immutable manifest")
    if manifest.execution_mode(filename) != ONLINE_EXECUTION_MODE:
        raise MigrationError("Recovery filename is not an online migration")
    migration_database_url = database_url or os.getenv("MIGRATION_DATABASE_URL")
    if not migration_database_url:
        raise MigrationError("MIGRATION_DATABASE_URL is required for migration recovery")
    connection = await asyncpg.connect(
        migration_database_url,
        **database_connection_options("unihub-retail-migrations"),
    )
    try:
        await connection.execute("SELECT pg_advisory_lock($1)", MIGRATION_ADVISORY_LOCK_ID)
        await verify_database_connection_authority(connection)
        checksum = manifest.checksums[filename]
        stored = await connection.fetchval(
            "SELECT checksum FROM schema_migrations WHERE filename = $1", filename
        )
        if stored != _online_recovery_checksum(checksum):
            raise MigrationError(
                "Recovery filename does not hold the exact online recovery sentinel"
            )
        sql = (get_migrations_dir() / filename).read_text(encoding="utf-8")
        index_name, table_name = parse_controlled_cic(sql)
        role_activated = False
        try:
            role_activated = await _activate_online_migration_owner(connection)
            await _recover_cic_index(
                connection,
                index_name=index_name,
                table_name=table_name,
                sql=sql,
            )
        except Exception as exc:
            raise MigrationError(f"Online migration recovery failed: {filename}") from exc
        finally:
            await _reset_online_migration_owner(connection, activated=role_activated)
        await _cic_post_validate_index(connection, index_name, table_name)
        await _finalize_online_migration(connection, filename, checksum)
    finally:
        try:
            await connection.execute("SELECT pg_advisory_unlock($1)", MIGRATION_ADVISORY_LOCK_ID)
        finally:
            await connection.close()
