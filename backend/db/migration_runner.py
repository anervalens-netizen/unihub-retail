from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
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
BASELINE_REPLAY_MIGRATIONS = frozenset(
    {"014_target_calculator_store_exclusions.sql"}
)
TOMBSTONE_ADOPTION_PREREQUISITES = {
    "005_retail_ai_analysis_views.sql": "006_drop_ai_analysis_views.sql",
}
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


@dataclass(frozen=True, slots=True)
class MigrationManifest:
    baseline_hash: str
    incorporated_through: str
    checksums: dict[str, str]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_manifest_path() -> Path:
    return get_migrations_dir() / "manifest.json"


def load_migration_manifest(path: Path | None = None) -> MigrationManifest:
    manifest_path = path or get_manifest_path()
    try:
        payload: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
        baseline = payload["baseline"]
        migrations = payload["migrations"]
        version = payload["version"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MigrationError("Migration manifest is invalid") from exc
    if version != 1 or not isinstance(baseline, dict) or not isinstance(migrations, dict):
        raise MigrationError("Migration manifest is invalid")
    baseline_hash = baseline.get("sha256")
    incorporated = baseline.get("incorporated_through")
    if (
        baseline.get("file") != "schema_v2.sql"
        or not isinstance(baseline_hash, str)
        or len(baseline_hash) != 64
        or not isinstance(incorporated, str)
        or incorporated not in migrations
        or not migrations
        or any(
            not isinstance(name, str)
            or not isinstance(checksum, str)
            or len(checksum) != 64
            for name, checksum in migrations.items()
        )
    ):
        raise MigrationError("Migration manifest is invalid")
    return MigrationManifest(baseline_hash, incorporated, dict(migrations))


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


def _validate_applied(
    applied: dict[str, str | None], manifest: MigrationManifest, *, allow_missing_checksums: bool
) -> None:
    unknown = sorted(set(applied) - set(manifest.checksums))
    if unknown:
        raise MigrationError("Database contains migrations absent from the manifest")
    for filename, stored_checksum in applied.items():
        expected = manifest.checksums[filename]
        if stored_checksum is None and allow_missing_checksums:
            continue
        if stored_checksum != expected:
            raise MigrationError("Applied migration checksum mismatch")


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
    applied_now: list[str] = []
    try:
        await verify_database_connection_authority(connection)
        await connection.execute("SELECT pg_advisory_lock($1)", MIGRATION_ADVISORY_LOCK_ID)
        has_application_schema = bool(
            await connection.fetchval(
                "SELECT to_regclass('public.sales_transactions') IS NOT NULL"
            )
        )
        if configured_database_authority() == "migrate" and not has_application_schema:
            raise MigrationError(
                "Fresh bootstrap requires the administrative extension/schema preflight"
            )
        async with connection.transaction():
            await _activate_migration_owner(connection)
            if not has_application_schema:
                await connection.execute(get_schema_path().read_text(encoding="utf-8"))
            await connection.execute(TRACKING_SQL)
            applied = await _tracking_rows(connection)
            _validate_applied(applied, manifest, allow_missing_checksums=True)
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
            for filename, checksum in applied.items():
                if checksum is None:
                    await connection.execute(
                        "UPDATE schema_migrations SET checksum = $2 WHERE filename = $1",
                        filename,
                        manifest.checksums[filename],
                    )
                    applied[filename] = manifest.checksums[filename]
            if not has_application_schema:
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
        _validate_applied(applied, manifest, allow_missing_checksums=False)
        for filename, checksum in manifest.checksums.items():
            if filename in applied:
                continue
            sql = (get_migrations_dir() / filename).read_text(encoding="utf-8")
            async with connection.transaction():
                await _activate_migration_owner(connection)
                await connection.execute(sql)
                await connection.execute(
                    "INSERT INTO schema_migrations (filename, checksum) VALUES ($1, $2)",
                    filename,
                    checksum,
                )
            applied[filename] = checksum
            applied_now.append(filename)
        return applied_now
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
