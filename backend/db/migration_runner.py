from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import asyncpg

from config import configured_database_authority
from db.connection import (
    database_connection_options,
    get_migrations_dir,
    get_schema_path,
    verify_database_connection_authority,
)


MIGRATION_ADVISORY_LOCK_ID = 7_221_904_202_607_12
AUTHORITY_CUTOVER_BOOTSTRAP_ENV = "UNIHUB_DB_AUTHORITY_CUTOVER_BOOTSTRAP"
AUTHORITY_CUTOVER_MIGRATIONS = frozenset(
    {
        "040_db_authority_append_only.sql",
        "041_schema_owner_handoff.sql",
    }
)
BASELINE_REPLAY_MIGRATIONS = frozenset(
    {"014_target_calculator_store_exclusions.sql"}
)
TOMBSTONE_ADOPTION_PREREQUISITES = {
    "005_retail_ai_analysis_views.sql": "006_drop_ai_analysis_views.sql",
}
TRANSACTIONAL_EXECUTION_MODE = "transactional"
ONLINE_EXECUTION_MODE = "online"
ONLINE_RECOVERY_PREFIX = "online-recovery:"
# F2: controlled non-unique CREATE INDEX CONCURRENTLY recovery uses a bounded
# lock_timeout (5s) so a competing long-holder cannot stall an online recovery
# indefinitely; the prior per-session setting is restored in a finally.
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
TRACKING_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    schema_name TEXT PRIMARY KEY,
    schema_hash TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    checksum TEXT,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT;
""".strip()


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


def _authority_cutover_bootstrap_enabled() -> bool:
    value = os.getenv(AUTHORITY_CUTOVER_BOOTSTRAP_ENV, "").strip()
    if not value:
        return False
    if value != "1":
        raise MigrationError(
            f"{AUTHORITY_CUTOVER_BOOTSTRAP_ENV} must be exactly 1 for the one-time cutover"
        )
    return True


@dataclass(frozen=True, slots=True)
class MigrationManifest:
    baseline_hash: str
    incorporated_through: str
    checksums: dict[str, str]
    execution_modes: dict[str, str] = field(default_factory=dict)

    def execution_mode(self, filename: str) -> str:
        return self.execution_modes.get(filename, TRANSACTIONAL_EXECUTION_MODE)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_manifest_path() -> Path:
    return get_migrations_dir() / "manifest.json"


def _valid_manifest_migrations(migrations: object) -> bool:
    if not isinstance(migrations, dict) or not migrations:
        return False
    return all(
        isinstance(name, str)
        and isinstance(checksum, str)
        and len(checksum) == 64
        for name, checksum in migrations.items()
    )


def _valid_execution_modes(
    execution_modes: object, migrations: dict[str, str]
) -> bool:
    if not isinstance(execution_modes, dict):
        return False
    return all(
        isinstance(name, str)
        and name in migrations
        and mode == ONLINE_EXECUTION_MODE
        for name, mode in execution_modes.items()
    )


def load_migration_manifest(path: Path | None = None) -> MigrationManifest:
    manifest_path = path or get_manifest_path()
    try:
        payload: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
        baseline = payload["baseline"]
        migrations = payload["migrations"]
        version = payload["version"]
        execution_modes = payload.get("execution_modes", {})
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MigrationError("Migration manifest is invalid") from exc
    if (
        version != 1
        or not isinstance(baseline, dict)
        or not _valid_manifest_migrations(migrations)
    ):
        raise MigrationError("Migration manifest is invalid")
    assert isinstance(migrations, dict)
    if not _valid_execution_modes(execution_modes, migrations):
        raise MigrationError("Migration manifest is invalid")
    assert isinstance(execution_modes, dict)
    baseline_hash = baseline.get("sha256")
    incorporated = baseline.get("incorporated_through")
    if (
        baseline.get("file") != "schema_v2.sql"
        or not isinstance(baseline_hash, str)
        or len(baseline_hash) != 64
        or not isinstance(incorporated, str)
        or incorporated not in migrations
    ):
        raise MigrationError("Migration manifest is invalid")
    return MigrationManifest(
        baseline_hash,
        incorporated,
        dict(migrations),
        dict(execution_modes),
    )


def verify_migration_files(manifest: MigrationManifest) -> None:
    migrations_dir = get_migrations_dir()
    actual = {
        path.name: _sha256(path)
        for path in migrations_dir.iterdir()
        if path.is_file() and path.suffix == ".sql"
    }
    if actual != manifest.checksums:
        raise MigrationError("Migration files do not match the immutable manifest")
    if _sha256(get_schema_path()) != manifest.baseline_hash:
        raise MigrationError("Frozen schema baseline does not match the manifest")


async def _tracking_rows(connection: asyncpg.Connection) -> dict[str, str | None]:
    rows = await connection.fetch(
        "SELECT filename, checksum FROM schema_migrations ORDER BY filename"
    )
    return {row["filename"]: row["checksum"] for row in rows}


def _online_recovery_checksum(checksum: str) -> str:
    return f"{ONLINE_RECOVERY_PREFIX}{checksum}"


def _validate_applied(
    applied: dict[str, str | None],
    manifest: MigrationManifest,
    *,
    allow_missing_checksums: bool,
) -> None:
    unknown = sorted(set(applied) - set(manifest.checksums))
    if unknown:
        raise MigrationError("Database contains migrations absent from the manifest")
    for filename, stored_checksum in applied.items():
        expected = manifest.checksums[filename]
        if isinstance(stored_checksum, str) and stored_checksum.startswith(
            ONLINE_RECOVERY_PREFIX
        ):
            if (
                stored_checksum != _online_recovery_checksum(expected)
                or manifest.execution_mode(filename) != ONLINE_EXECUTION_MODE
            ):
                raise MigrationError(
                    "Online migration recovery state does not match the immutable manifest"
                )
            raise MigrationError(
                f"Online migration recovery required before migrations can continue: {filename}"
            )
        if stored_checksum is None and allow_missing_checksums:
            continue
        if stored_checksum != expected:
            raise MigrationError("Applied migration checksum mismatch")


async def _verify_authority_cutover_bootstrap(
    connection: asyncpg.Connection,
    manifest: MigrationManifest,
) -> None:
    """Authorize only the one-time 039 -> 041 admin transition.

    The new migration LOGIN cannot exist before 040 creates its authority
    groups and 041 creates the stable schema owner. This explicit bridge is
    deliberately unusable for fresh installs, an incomplete pre-040 history,
    any post-039 migration already applied, a configured process authority, or
    a non-superuser/session-role switch. Later manifest migrations may exist,
    but the bootstrap invocation applies only 040 and 041.
    """
    if configured_database_authority() is not None:
        raise MigrationError(
            "Authority cutover bootstrap cannot be combined with a process authority"
        )
    identity = await connection.fetchrow(
        """
        SELECT current_user::text AS current_user,
               session_user::text AS session_user,
               rolsuper
        FROM pg_roles
        WHERE rolname = current_user
        """
    )
    if (
        identity is None
        or str(identity["current_user"]) != str(identity["session_user"])
        or not bool(identity["rolsuper"])
    ):
        raise MigrationError(
            "Authority cutover bootstrap requires the authenticated administrative superuser"
        )
    if not bool(
        await connection.fetchval(
            "SELECT to_regclass('public.sales_transactions') IS NOT NULL "
            "AND to_regclass('public.schema_migrations') IS NOT NULL"
        )
    ):
        raise MigrationError(
            "Authority cutover bootstrap requires an existing tracked application database"
        )
    applied = await _tracking_rows(connection)
    _validate_applied(applied, manifest, allow_missing_checksums=False)
    ordered_names = list(manifest.checksums)
    first_cutover_index = min(
        ordered_names.index(filename) for filename in AUTHORITY_CUTOVER_MIGRATIONS
    )
    expected_applied = set(ordered_names[:first_cutover_index])
    if set(applied) != expected_applied:
        raise MigrationError(
            "Authority cutover bootstrap requires every migration through 039 "
            "applied and every migration from 040 onward pending"
        )


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


async def _apply_online_migration(
    connection: asyncpg.Connection,
    *,
    filename: str,
    checksum: str,
    sql: str,
) -> None:
    await _mark_online_recovery(connection, filename, checksum)
    role_activated = False
    try:
        role_activated = await _activate_online_migration_owner(connection)
        await _execute_online_statement(connection, sql)
    except Exception as exc:
        raise MigrationError(
            f"Online migration failed; recovery required for {filename}"
        ) from exc
    finally:
        await _reset_online_migration_owner(
            connection,
            activated=role_activated,
        )
    await _finalize_online_migration(connection, filename, checksum)


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
    """True when the SQL is intended as a CREATE INDEX CONCURRENTLY attempt.

    This is intentionally permissive: it only detects the CIC pattern so the
    runner can route it through the controlled F2 path. The strict parser
    (:func:`parse_controlled_cic`) is the authority that then fails closed on
    UNIQUE, IF NOT EXISTS, quoted/ambiguous identifiers and multi-statement
    bodies.
    """
    return bool(_CIC_ATTEMPT_RE.match(_strip_leading_comments(sql)))


def parse_controlled_cic(sql: str) -> tuple[str, str]:
    """Parse a standalone non-unique CREATE INDEX CONCURRENTLY statement.

    Returns ``(index_name, table_name)`` for the exact unquoted-safe lowercase
    identifiers, or raises :class:`MigrationError` fail-closed for UNIQUE,
    ``IF NOT EXISTS``, ordinary CREATE INDEX, quoted/ambiguous identifiers,
    multiple top-level statements, or any other (generic online) SQL.
    """
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
    # set_config sets the per-session setting (is_local=false) and accepts the
    # prior value as a bound parameter, so the restore is quoting-safe.
    await connection.fetchval("SELECT set_config('lock_timeout', $1, false)", value)


async def _execute_cic_statement(connection: asyncpg.Connection, sql: str) -> None:
    """Run one controlled CREATE/DROP INDEX CONCURRENTLY outside a transaction.

    A bounded 5s ``lock_timeout`` is applied for the statement and the prior
    session setting is restored in a ``finally`` on success and on failure.
    """
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
    """Fail closed before the F2 sentinel when the exact index already exists."""
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
        await _reset_online_migration_owner(
            connection,
            activated=role_activated,
        )
    await _cic_post_validate_index(connection, index_name, table_name)
    await _finalize_online_migration(connection, filename, checksum)


async def _apply_transactional_migration(
    connection: asyncpg.Connection,
    *,
    filename: str,
    checksum: str,
    sql: str,
) -> None:
    async with connection.transaction():
        await _activate_migration_owner(connection)
        await connection.execute(sql)
        await connection.execute(
            "INSERT INTO schema_migrations (filename, checksum) VALUES ($1, $2)",
            filename,
            checksum,
        )


async def _adopt_tombstones(
    connection: asyncpg.Connection,
    manifest: MigrationManifest,
    applied: dict[str, str | None],
) -> None:
    for tombstone, prerequisite in TOMBSTONE_ADOPTION_PREREQUISITES.items():
        if tombstone not in applied and prerequisite in applied:
            adopted_checksum = manifest.checksums[tombstone]
            await connection.execute(
                """
                INSERT INTO schema_migrations (filename, checksum)
                VALUES ($1, $2)
                ON CONFLICT (filename) DO NOTHING
                """,
                tombstone,
                adopted_checksum,
            )
            applied[tombstone] = adopted_checksum


async def _backfill_missing_checksums(
    connection: asyncpg.Connection,
    manifest: MigrationManifest,
    applied: dict[str, str | None],
) -> None:
    for filename, checksum in applied.items():
        if checksum is not None:
            continue
        await connection.execute(
            "UPDATE schema_migrations SET checksum = $2 WHERE filename = $1",
            filename,
            manifest.checksums[filename],
        )
        applied[filename] = manifest.checksums[filename]


async def _record_fresh_baseline(
    connection: asyncpg.Connection,
    manifest: MigrationManifest,
    applied: dict[str, str | None],
) -> None:
    incorporated_names = [
        name
        for name in manifest.checksums
        if name <= manifest.incorporated_through
        and name not in BASELINE_REPLAY_MIGRATIONS
    ]
    for filename in incorporated_names:
        await connection.execute(
            """
            INSERT INTO schema_migrations (filename, checksum)
            VALUES ($1, $2)
            ON CONFLICT (filename) DO NOTHING
            """,
            filename,
            manifest.checksums[filename],
        )
        applied[filename] = manifest.checksums[filename]
    await connection.execute(
        """
        INSERT INTO schema_meta (schema_name, schema_hash, applied_at)
        VALUES ('schema_v2', $1, now())
        ON CONFLICT (schema_name) DO NOTHING
        """,
        manifest.baseline_hash,
    )


async def _prepare_migration_history(
    connection: asyncpg.Connection,
    manifest: MigrationManifest,
    *,
    has_application_schema: bool,
) -> dict[str, str | None]:
    async with connection.transaction():
        await _activate_migration_owner(connection)
        if not has_application_schema:
            await connection.execute(get_schema_path().read_text(encoding="utf-8"))
        await connection.execute(TRACKING_SQL)
        applied = await _tracking_rows(connection)
        _validate_applied(applied, manifest, allow_missing_checksums=True)
        await _adopt_tombstones(connection, manifest, applied)
        await _backfill_missing_checksums(connection, manifest, applied)
        if not has_application_schema:
            await _record_fresh_baseline(connection, manifest, applied)
    _validate_applied(applied, manifest, allow_missing_checksums=False)
    return applied


async def _apply_pending_migrations(
    connection: asyncpg.Connection,
    manifest: MigrationManifest,
    applied: dict[str, str | None],
    *,
    cutover_bootstrap: bool,
) -> list[str]:
    applied_now: list[str] = []
    for filename, checksum in manifest.checksums.items():
        if filename in applied:
            continue
        if cutover_bootstrap and filename not in AUTHORITY_CUTOVER_MIGRATIONS:
            continue
        sql = (get_migrations_dir() / filename).read_text(encoding="utf-8")
        if manifest.execution_mode(filename) == ONLINE_EXECUTION_MODE:
            if _looks_like_cic_statement(sql):
                index_name, table_name = parse_controlled_cic(sql)
                await _apply_cic_online_migration(
                    connection,
                    filename=filename,
                    checksum=checksum,
                    sql=sql,
                    index_name=index_name,
                    table_name=table_name,
                )
            else:
                await _apply_online_migration(
                    connection,
                    filename=filename,
                    checksum=checksum,
                    sql=sql,
                )
        else:
            await _apply_transactional_migration(
                connection,
                filename=filename,
                checksum=checksum,
                sql=sql,
            )
        applied[filename] = checksum
        applied_now.append(filename)
    return applied_now


async def run_migrations(database_url: str | None = None) -> list[str]:
    manifest = load_migration_manifest()
    verify_migration_files(manifest)
    migration_database_url = database_url or os.getenv("MIGRATION_DATABASE_URL")
    if not migration_database_url:
        raise MigrationError("MIGRATION_DATABASE_URL is required for migrations")
    connection = await asyncpg.connect(
        migration_database_url,
        **database_connection_options("unihub-retail-migrations"),
    )
    try:
        await connection.execute("SELECT pg_advisory_lock($1)", MIGRATION_ADVISORY_LOCK_ID)
        cutover_bootstrap = _authority_cutover_bootstrap_enabled()
        if cutover_bootstrap:
            await _verify_authority_cutover_bootstrap(connection, manifest)
        else:
            await verify_database_connection_authority(connection)
        has_application_schema = bool(
            await connection.fetchval(
                "SELECT to_regclass('public.sales_transactions') IS NOT NULL"
            )
        )
        if configured_database_authority() == "migrate" and not has_application_schema:
            raise MigrationError(
                "Fresh bootstrap requires the administrative extension/schema preflight"
            )
        applied = await _prepare_migration_history(
            connection,
            manifest,
            has_application_schema=has_application_schema,
        )
        return await _apply_pending_migrations(
            connection,
            manifest,
            applied,
            cutover_bootstrap=cutover_bootstrap,
        )
    finally:
        try:
            await connection.execute(
                "SELECT pg_advisory_unlock($1)", MIGRATION_ADVISORY_LOCK_ID
            )
        finally:
            await connection.close()


async def verify_migrations_current(pool: asyncpg.Pool) -> None:
    manifest = load_migration_manifest()
    verify_migration_files(manifest)
    async with pool.acquire() as connection:
        tracking_exists = bool(
            await connection.fetchval(
                "SELECT to_regclass('public.schema_migrations') IS NOT NULL"
            )
        )
        if not tracking_exists:
            raise MigrationError("Migration tracking is not initialized")
        checksum_exists = bool(
            await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'schema_migrations'
                      AND column_name = 'checksum'
                )
                """
            )
        )
        if not checksum_exists:
            raise MigrationError("Migration checksum tracking is not initialized")
        applied = await _tracking_rows(connection)
    _validate_applied(applied, manifest, allow_missing_checksums=False)
    if set(applied) != set(manifest.checksums):
        raise MigrationError("Database has pending migrations")
