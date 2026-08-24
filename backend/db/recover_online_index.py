"""Explicit operator recovery for a controlled online migration.

F2 keeps recovery out of ``run_migrations``. A normal migration run never
auto-recovers an online-recovery sentinel; the operator invokes
:func:`recover_online_migration` with the exact manifest filename.

The controlled-CIC primitives (parser, executor, preflight, post-validation,
catalog inspection) live in :mod:`db.migration_runtime` together with the
shared online-migration runtime primitives. This module re-uses them and adds
the operator-facing dispatch: load the manifest, re-derive ``pg_advisory_lock``
ownership, replay the exact CIC, drop an existing partial index, then
finalize the recovery sentinel.
"""
from __future__ import annotations

import os

import asyncpg

from db.connection import (
    database_connection_options,
    verify_database_connection_authority,
)
from db.migration_runtime import (
    MigrationError,
    _activate_online_migration_owner,
    _cic_post_validate_index,
    _execute_cic_statement,
    _finalize_online_migration,
    _online_recovery_checksum,
    _reset_online_migration_owner,
    parse_controlled_cic,
)
from db.migration_runner import (
    MIGRATION_ADVISORY_LOCK_ID,
    ONLINE_EXECUTION_MODE,
    get_migrations_dir,
    load_migration_manifest,
    verify_migration_files,
)


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
