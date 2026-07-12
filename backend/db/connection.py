from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import asyncpg

logger = logging.getLogger(__name__)

pool: asyncpg.Pool | None = None
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


def validate_test_database_url(database_url: str) -> None:
    """Refuse test execution against production or a shared PostgreSQL cluster.

    Integration tests are destructive by design. They are allowed only when
    the caller explicitly opts in and the URL points to a loopback database
    whose name is clearly marked as a test database, on a port other than the
    production Retail port.
    """
    if os.getenv("UNIHUB_TEST_DATABASE") != "1":
        raise RuntimeError(
            "Database tests require UNIHUB_TEST_DATABASE=1 and an isolated "
            "PostgreSQL instance"
        )

    parsed = urlparse(database_url)
    database_name = unquote(parsed.path.lstrip("/"))
    hostname = (parsed.hostname or "").lower()

    if parsed.scheme not in {"postgresql", "postgres"}:
        raise RuntimeError("Test DATABASE_URL must use PostgreSQL")
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Test DATABASE_URL must point to a loopback host")
    if parsed.port == 5432:
        raise RuntimeError(
            "Test DATABASE_URL cannot use the production Retail port 5432"
        )
    if not (
        database_name.endswith("_test")
        or database_name.startswith("test_")
    ):
        raise RuntimeError(
            "Test database name must start with test_ or end with _test"
        )


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    if os.getenv("UNIHUB_RUNNING_TESTS") == "1":
        validate_test_database_url(database_url)
    return database_url


def get_schema_path() -> Path:
    return Path(__file__).with_name("schema_v2.sql")


async def init_db_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        statement_timeout_ms = int(
            os.getenv("DB_STATEMENT_TIMEOUT_MS", "120000")
        )
        lock_timeout_ms = int(os.getenv("DB_LOCK_TIMEOUT_MS", "10000"))
        idle_transaction_timeout_ms = int(
            os.getenv("DB_IDLE_TRANSACTION_TIMEOUT_MS", "60000")
        )
        pool = await asyncpg.create_pool(
            dsn=get_database_url(),
            min_size=int(os.getenv("DB_POOL_MIN_SIZE", "3")),
            max_size=int(os.getenv("DB_POOL_MAX_SIZE", "10")),
            command_timeout=statement_timeout_ms / 1000,
            server_settings={
                "application_name": "unihub-retail",
                "statement_timeout": str(statement_timeout_ms),
                "lock_timeout": str(lock_timeout_ms),
                "idle_in_transaction_session_timeout": str(
                    idle_transaction_timeout_ms
                ),
            },
        )
    return pool


async def prewarm_pool() -> None:
    """Force pool to open min_size connections and verify each round-trips.

    asyncpg normally opens min_size connections eagerly, but the verification
    round-trip catches auth/network issues at boot instead of on first request.
    """
    current_pool = await get_pool()
    min_size = current_pool.get_min_size()
    if min_size <= 0:
        return

    async def _ping() -> None:
        async with current_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

    await asyncio.gather(*(_ping() for _ in range(min_size)))
    logger.info("DB pool prewarmed (%d connections)", min_size)


async def close_db_pool() -> None:
    global pool
    if pool is not None:
        await pool.close()
        pool = None


async def get_pool() -> asyncpg.Pool:
    if pool is None:
        return await init_db_pool()
    return pool


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
