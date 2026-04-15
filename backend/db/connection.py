from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

pool: asyncpg.Pool | None = None
SCHEMA_NAME = "schema_v2"
SCHEMA_META_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    schema_name TEXT PRIMARY KEY,
    schema_hash TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""".strip()

SCHEMA_MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""".strip()

# Migrations must match NNN_name.sql (3-digit numeric prefix)
_MIGRATION_FILENAME_RE = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")


def _load_repo_env_file() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_repo_env_file()


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return database_url


def get_schema_path() -> Path:
    return Path(__file__).with_name("schema_v2.sql")


def read_schema_sql() -> str:
    return get_schema_path().read_text(encoding="utf-8")


def compute_schema_hash(schema_sql: str) -> str:
    return hashlib.sha256(schema_sql.encode("utf-8")).hexdigest()


async def init_db_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(
            dsn=get_database_url(),
            min_size=1,
            max_size=int(os.getenv("DB_POOL_MAX_SIZE", "10")),
            command_timeout=120,
        )
    return pool


async def close_db_pool() -> None:
    global pool
    if pool is not None:
        await pool.close()
        pool = None


async def get_pool() -> asyncpg.Pool:
    if pool is None:
        return await init_db_pool()
    return pool


async def ensure_schema_current(*, force: bool = False) -> bool:
    current_pool = await get_pool()
    schema_sql = read_schema_sql()
    schema_hash = compute_schema_hash(schema_sql)

    async with current_pool.acquire() as connection:
        await connection.execute(SCHEMA_META_TABLE_SQL)
        stored_hash = await connection.fetchval(
            """
            SELECT schema_hash
            FROM schema_meta
            WHERE schema_name = $1
            """,
            SCHEMA_NAME,
        )
        if not force and stored_hash == schema_hash:
            return False

        async with connection.transaction():
            await connection.execute(schema_sql)
            await connection.execute(
                """
                INSERT INTO schema_meta (schema_name, schema_hash, applied_at)
                VALUES ($1, $2, now())
                ON CONFLICT (schema_name) DO UPDATE
                SET schema_hash = EXCLUDED.schema_hash,
                    applied_at = EXCLUDED.applied_at
                """,
                SCHEMA_NAME,
                schema_hash,
            )
    return True


async def apply_schema() -> None:
    await ensure_schema_current(force=True)


def get_migrations_dir() -> Path:
    return Path(__file__).with_name("migrations")


def list_migration_files(migrations_dir: Path | None = None) -> list[Path]:
    """Return NNN_*.sql migrations în ordine numerică.

    Ignoră fișiere fără prefix numeric (README.md, backup-uri etc.) și
    validează strict formatul ca să nu apară surprize de ordonare
    (e.g. 2_foo.sql înainte de 10_bar.sql ar sorta lexicografic greșit —
    de-aia impun 3 cifre).
    """
    d = migrations_dir or get_migrations_dir()
    if not d.exists():
        return []
    candidates = [p for p in d.iterdir() if p.is_file() and p.suffix == ".sql"]
    valid = [p for p in candidates if _MIGRATION_FILENAME_RE.match(p.name)]
    invalid = [p.name for p in candidates if not _MIGRATION_FILENAME_RE.match(p.name)]
    if invalid:
        raise RuntimeError(
            "Migrations invalide (format cerut: NNN_nume.sql cu 3 cifre): "
            + ", ".join(sorted(invalid))
        )
    return sorted(valid, key=lambda p: p.name)


async def apply_pending_migrations(*, migrations_dir: Path | None = None) -> list[str]:
    """Aplică migrations NNN_*.sql nebifate în `schema_migrations`.

    Fiecare fișier rulează într-o tranzacție separată — dacă pica una,
    restul nu se aplică. Returnează lista fișierelor aplicate (pentru log).

    Flow:
    1. `ensure_schema_current()` rulează schema_v2.sql (baseline idempotent)
    2. `apply_pending_migrations()` rulează delta peste baseline

    Migrations ar trebui să fie idempotente când e posibil (IF NOT EXISTS),
    dar tracking-ul ne acoperă pentru operațiuni care nu sunt (e.g. INSERT
    pentru data seeding, UPDATE cu efect unic).
    """
    current_pool = await get_pool()
    files = list_migration_files(migrations_dir)
    applied: list[str] = []

    async with current_pool.acquire() as connection:
        await connection.execute(SCHEMA_MIGRATIONS_TABLE_SQL)
        already = {
            row["filename"]
            for row in await connection.fetch("SELECT filename FROM schema_migrations")
        }

        for path in files:
            if path.name in already:
                continue
            sql = path.read_text(encoding="utf-8")
            async with connection.transaction():
                await connection.execute(sql)
                await connection.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1)",
                    path.name,
                )
            applied.append(path.name)
            logger.info("Applied migration %s", path.name)

    return applied
