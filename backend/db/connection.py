from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import asyncpg

from config import DATABASE_AUTHORITY_CONTRACTS, DatabaseAuthority, configured_database_authority

logger = logging.getLogger(__name__)

pool: asyncpg.Pool | None = None
# Migrations must match NNN_name.sql (3-digit numeric prefix)
_MIGRATION_FILENAME_RE = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")


async def database_principal_has_direct_authority(
    connection: asyncpg.Connection,
    principal: str,
) -> bool:
    """Detect authority attached directly to a process LOGIN.

    Process LOGINs must derive every database capability from their one exact
    NOLOGIN authority contract. Direct ACLs, owned objects, or default ACLs
    would bypass that contract and could also grant uncontrolled future access.
    """
    return bool(
        await connection.fetchval(
            """
            WITH target AS (
                SELECT oid FROM pg_roles WHERE rolname = $1
            )
            SELECT EXISTS (
                SELECT 1
                FROM pg_shdepend AS dependency
                CROSS JOIN target
                WHERE dependency.refclassid = 'pg_authid'::regclass
                  AND dependency.refobjid = target.oid
                  AND dependency.deptype IN ('a', 'o')
            )
            """,
            principal,
        )
    )


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


async def verify_database_connection_authority(
    connection: asyncpg.Connection,
    authority: DatabaseAuthority | None = None,
) -> None:
    """Verify the authenticated process principal and exclusive authority groups.

    The check is intentionally enabled only by ``UNIHUB_DB_PROCESS_AUTHORITY``.
    This keeps isolated tests and offline tools compatible until their explicit
    authority contract is provisioned, while production units fail closed once
    they declare the process authority.
    """
    configured = authority if authority is not None else configured_database_authority()
    if configured is None:
        if os.getenv("UNIHUB_ENV", "development").strip().lower() == "production":
            raise RuntimeError("Production database connections require an explicit process authority")
        return
    contract = DATABASE_AUTHORITY_CONTRACTS[configured]
    identity = await connection.fetchrow(
        """
        SELECT current_user::text AS current_user,
               session_user::text AS session_user,
               rolcanlogin,
               rolsuper,
               rolinherit,
               rolcreatedb,
               rolcreaterole,
               rolbypassrls,
               rolreplication
        FROM pg_roles
        WHERE rolname = current_user
        """
    )
    if identity is None:
        raise RuntimeError("Database authority check could not resolve the authenticated principal")
    current_user = str(identity["current_user"])
    session_user = str(identity["session_user"])
    if current_user != contract.principal or session_user != current_user:
        raise RuntimeError("Database authority principal does not match this process")
    if (
        not bool(identity["rolcanlogin"])
        or bool(identity["rolsuper"])
        or bool(identity["rolinherit"]) != contract.requires_inherit
        or bool(identity["rolcreatedb"])
        or bool(identity["rolcreaterole"])
        or bool(identity["rolbypassrls"])
        or bool(identity["rolreplication"])
    ):
        raise RuntimeError(
            "Database authority principal flags do not match its process contract"
        )

    direct_memberships = await connection.fetch(
        """
        SELECT parent.rolname, membership.inherit_option, membership.set_option
        FROM pg_auth_members AS membership
        JOIN pg_roles AS parent ON parent.oid = membership.roleid
        JOIN pg_roles AS member ON member.oid = membership.member
        WHERE member.rolname = current_user
        ORDER BY parent.rolname
        """
    )
    expected_direct = {
        role_name: (
            False if configured == "migrate" else True,
            role_name == "unihub_schema_owner",
        )
        for role_name in contract.required_memberships
    }
    actual_direct = {
        str(item["rolname"]): (
            bool(item["inherit_option"]), bool(item["set_option"])
        )
        for item in direct_memberships
    }
    if actual_direct != expected_direct:
        raise RuntimeError(
            "Database authority principal direct memberships or options do not match its exact contract"
        )

    effective_memberships = {
        str(item["rolname"])
        for item in await connection.fetch(
            """
            SELECT candidate.rolname
            FROM pg_roles AS candidate
            WHERE candidate.rolname <> current_user
              AND pg_has_role(current_user, candidate.oid, 'member')
            ORDER BY candidate.rolname
            """
        )
    }
    if effective_memberships != set(contract.required_memberships):
        raise RuntimeError(
            "Database authority principal has unexpected direct or transitive memberships"
        )
    if await database_principal_has_direct_authority(connection, current_user):
        raise RuntimeError(
            "Database authority principal has direct grants, default privileges, or ownership"
        )


def database_connection_options(application_name: str) -> dict[str, object]:
    """Return the bounded asyncpg settings shared by pools and one-shot tools."""
    statement_timeout_ms = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "120000"))
    lock_timeout_ms = int(os.getenv("DB_LOCK_TIMEOUT_MS", "10000"))
    idle_transaction_timeout_ms = int(
        os.getenv("DB_IDLE_TRANSACTION_TIMEOUT_MS", "60000")
    )
    return {
        "command_timeout": statement_timeout_ms / 1000,
        "server_settings": {
            "application_name": application_name,
            "statement_timeout": str(statement_timeout_ms),
            "lock_timeout": str(lock_timeout_ms),
            "idle_in_transaction_session_timeout": str(idle_transaction_timeout_ms),
        },
    }


async def connect_database_url(
    database_url: str, *, application_name: str
) -> asyncpg.Connection:
    """Open a bounded one-shot application connection."""
    return await asyncpg.connect(
        database_url, **database_connection_options(application_name)
    )


async def verify_database_pool_authority(
    db_pool: asyncpg.Pool,
    authority: DatabaseAuthority | None = None,
) -> None:
    """Acquire a real connection before checking its authenticated DB identity."""
    configured = authority if authority is not None else configured_database_authority()
    if configured is None:
        return
    async with db_pool.acquire() as connection:
        await verify_database_connection_authority(connection, configured)


def get_schema_path() -> Path:
    return Path(__file__).with_name("schema_v2.sql")


async def init_db_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        connection_options = database_connection_options("unihub-retail")
        created_pool = await asyncpg.create_pool(
            dsn=get_database_url(),
            min_size=int(os.getenv("DB_POOL_MIN_SIZE", "3")),
            max_size=int(os.getenv("DB_POOL_MAX_SIZE", "10")),
            **connection_options,
        )
        try:
            await verify_database_pool_authority(created_pool)
        except BaseException:
            await created_pool.close()
            raise
        pool = created_pool
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
