from __future__ import annotations

import hashlib
import os
from pathlib import Path

import asyncpg

pool: asyncpg.Pool | None = None
SCHEMA_NAME = "schema_v2"
SCHEMA_META_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    schema_name TEXT PRIMARY KEY,
    schema_hash TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""".strip()


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
