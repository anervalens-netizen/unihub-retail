"""Low-level online migration runtime primitives.

This module is the leaf of the F1/F2 migration dependency graph. It owns the
strictly-low-level primitives that talk to a single ``asyncpg`` connection for
online-schema and CREATE INDEX CONCURRENTLY (CIC) execution: schema-owner
elevation, the ``schema_migrations`` recovery sentinel, single-statement
dispatch outside a transaction, the controlled-CIC parser, and the catalog
validation that gates the controlled path.

Nothing in this module depends on the runner's manifest, advisory lock id, or
authority-cutover orchestration; everything required to run is below the
``asyncpg.Connection`` boundary and the configured database authority.
"""
from __future__ import annotations

import re

import asyncpg

from config import configured_database_authority


ONLINE_RECOVERY_PREFIX = "online-recovery:"

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


class MigrationError(RuntimeError):
    pass


async def _activate_migration_owner(connection: asyncpg.Connection) -> None:
    if configured_database_authority() == "migrate":
        await connection.execute("SET LOCAL ROLE unihub_schema_owner")
        if await connection.fetchval("SELECT current_user = 'unihub_schema_owner'") is not True:
            raise MigrationError("Migration schema-owner elevation failed")


async def _activate_online_migration_owner(connection: asyncpg.Connection) -> bool:
    if configured_database_authority() != "migrate":
        return False
    await connection.execute("SET ROLE unihub_schema_owner")
    if await connection.fetchval("SELECT current_user = 'unihub_schema_owner'") is True:
        return True
    await connection.execute("RESET ROLE")
    raise MigrationError("Online migration schema-owner elevation failed")


async def _reset_online_migration_owner(
    connection: asyncpg.Connection, *, activated: bool
) -> None:
    if not activated:
        return
    await connection.execute("RESET ROLE")
    if await connection.fetchval("SELECT current_user = session_user") is not True:
        raise MigrationError("Online migration schema-owner reset failed")


def _online_recovery_checksum(checksum: str) -> str:
    return f"{ONLINE_RECOVERY_PREFIX}{checksum}"


async def _mark_online_recovery(
    connection: asyncpg.Connection, filename: str, checksum: str
) -> None:
    async with connection.transaction():
        await _activate_migration_owner(connection)
        await connection.execute(
            "INSERT INTO schema_migrations (filename, checksum) VALUES ($1, $2)",
            filename,
            _online_recovery_checksum(checksum),
        )


async def _execute_online_statement(
    connection: asyncpg.Connection, sql: str
) -> None:
    if connection.is_in_transaction():
        raise MigrationError("Online migration requires no active transaction")
    # fetch() uses asyncpg's extended-query/prepared path even without bind
    # parameters. PostgreSQL therefore accepts exactly one top-level statement
    # and rejects accidental multi-command migration files.
    await connection.fetch(sql)
    if connection.is_in_transaction():
        raise MigrationError("Online migration left an active transaction")


async def _finalize_online_migration(
    connection: asyncpg.Connection, filename: str, checksum: str
) -> None:
    async with connection.transaction():
        await _activate_migration_owner(connection)
        updated = await connection.execute(
            """
            UPDATE schema_migrations
            SET checksum = $2, applied_at = now()
            WHERE filename = $1 AND checksum = $3
            """,
            filename,
            checksum,
            _online_recovery_checksum(checksum),
        )
        if updated != "UPDATE 1":
            raise MigrationError("Online migration recovery marker was not finalized")


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


async def _execute_cic_statement(connection: asyncpg.Connection, sql: str) -> None:
    """Run one controlled CIC statement outside a transaction and restore timeout."""
    if connection.is_in_transaction():
        raise MigrationError("Controlled online migration requires no active transaction")
    prior_timeout = str(await connection.fetchval("SHOW lock_timeout"))
    try:
        await connection.fetchval(
            "SELECT set_config('lock_timeout', $1, false)",
            f"{CIC_LOCK_TIMEOUT_MS}ms",
        )
        await connection.fetch(sql)
    finally:
        await connection.fetchval(
            "SELECT set_config('lock_timeout', $1, false)", prior_timeout
        )
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
