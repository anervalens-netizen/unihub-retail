"""Host-only, directional PostgreSQL watchdog authority; never sandbox credentials."""
from __future__ import annotations

import asyncio

import asyncpg

from . import db_authority as readonly

GUARD_LOGIN = "unihub_ai_guard"
SANDBOX_LOGIN = "unihub_ai_readonly"
_DIRECT_ROLES = {SANDBOX_LOGIN, "pg_read_all_stats"}
_EFFECTIVE_ROLES = _DIRECT_ROLES | {readonly.READONLY_AUTHORITY_ROLE}
_MEMBERSHIP_SQL = """
SELECT parent.rolname::text AS rolname, m.inherit_option, m.admin_option
FROM pg_auth_members m
JOIN pg_roles parent ON parent.oid = m.roleid
JOIN pg_roles member ON member.oid = m.member
WHERE member.rolname = current_user
"""


_DATABASE_IDENTITY_SQL = """
SELECT current_database()::text AS database_name,
       (SELECT oid FROM pg_database WHERE datname = current_database()) AS database_oid,
       pg_postmaster_start_time() AS postmaster_start,
       inet_server_port() AS server_port,
       current_user::text AS current_user, session_user::text AS session_user
"""
_DATABASE_IDENTITY_FIELDS = ("database_name", "database_oid", "postmaster_start", "server_port")


class AiGuardAuthorityError(RuntimeError):
    """Host guard authority could not be proven; safe to expose without a DSN."""


async def verify_guard_connection(connection: asyncpg.Connection) -> str:
    """Verify the actual session before applying any client timeout overrides."""
    row = await connection.fetchrow(readonly._IDENTITY_SQL)
    if (row is None or row["current_user"] != GUARD_LOGIN
            or row["session_user"] != GUARD_LOGIN):
        raise AiGuardAuthorityError(f"AI guard must authenticate directly as {GUARD_LOGIN}")
    if not row["rolcanlogin"] or not row["rolinherit"] or any(
        row[column] for column, _ in readonly._ELEVATED_ROLE_ATTRIBUTES
    ):
        raise AiGuardAuthorityError("AI guard must be a non-elevated INHERIT LOGIN")
    direct = await connection.fetch(_MEMBERSHIP_SQL)
    if {r["rolname"] for r in direct} != _DIRECT_ROLES or any(
        not r["inherit_option"] or r["admin_option"] for r in direct
    ):
        raise AiGuardAuthorityError("AI guard requires exactly readonly + pg_read_all_stats, inherited without ADMIN")
    effective = await connection.fetch(readonly._EFFECTIVE_MEMBERSHIP_SQL)
    if {r["rolname"] for r in effective} != _EFFECTIVE_ROLES:
        raise AiGuardAuthorityError("AI guard has unexpected effective memberships (pg_signal_backend forbidden)")
    try:
        await readonly._verify_write_authority(connection, GUARD_LOGIN)
        await readonly._verify_session_timeouts(connection, GUARD_LOGIN)
    except readonly.AiReadOnlyAuthorityError as exc:
        raise AiGuardAuthorityError(str(exc).replace("sandbox read-only", "guard")) from None
    return GUARD_LOGIN


async def verify_guard_database(readonly_dsn: str, guard_dsn: str) -> None:
    """Prove both host endpoints reach the same database/postmaster, not URI alias.

    No privileged grants are needed. Keep both sessions open during comparison;
    fail closed on restart, missing identity, wrong login or any transport failure.
    """
    connections: list[asyncpg.Connection] = []
    try:
        async with asyncio.timeout(10):
            identities = []
            for dsn, principal in ((readonly_dsn, SANDBOX_LOGIN), (guard_dsn, GUARD_LOGIN)):
                if not dsn.strip():
                    raise AiGuardAuthorityError("AI guard database DSNs must be configured")
                connection = await asyncpg.connect(dsn, timeout=3, command_timeout=3)
                connections.append(connection)
                identity = await connection.fetchrow(_DATABASE_IDENTITY_SQL)
                if (identity is None or identity["current_user"] != principal
                        or identity["session_user"] != principal
                        or any(identity[field] is None for field in _DATABASE_IDENTITY_FIELDS)):
                    raise AiGuardAuthorityError("AI guard database identity cannot be proven")
                identities.append(tuple(identity[field] for field in _DATABASE_IDENTITY_FIELDS))
            if identities[0] != identities[1]:
                raise AiGuardAuthorityError("AI guard and sandbox must use the same PostgreSQL server and database")
    except AiGuardAuthorityError:
        raise
    except Exception:
        raise AiGuardAuthorityError("AI guard database identity check failed") from None
    finally:
        for connection in connections:
            try:
                await connection.close(timeout=1)
            except Exception:
                connection.terminate()


async def verify_guard_authority(dsn: str) -> str:
    """Startup API: verify dedicated host DSN, return login, fail closed safely."""
    if not dsn.strip():
        raise AiGuardAuthorityError("AI guard DSN is not configured")
    connection = None
    try:
        connection = await asyncpg.connect(dsn, timeout=3, command_timeout=3)
        return await verify_guard_connection(connection)
    except AiGuardAuthorityError:
        raise
    except Exception:
        raise AiGuardAuthorityError("AI guard connection or authority check failed") from None
    finally:
        if connection is not None:
            try:
                await connection.close(timeout=1)
            except Exception:
                connection.terminate()
