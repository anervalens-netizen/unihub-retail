"""Fail-closed preflight for the sandbox read-only PostgreSQL identity.

``AI_ASSISTANT_READONLY_DSN`` is handed to arbitrary model-generated code
inside the Docker sandbox, so a syntactically valid DSN is not a technical
boundary. Before the runtime reports healthy it must connect with that exact
credential and prove, on the real server, that the login derives its entire
authority from the repository read-only role, cannot write application data
and cannot leave unbounded or idle transactions behind.

The check deliberately reads effective capabilities (``has_table_privilege``,
``has_schema_privilege``, ``pg_has_role``) instead of stored grants: indirect
membership, ownership and default privileges are all authority in practice.
"""

from __future__ import annotations

import asyncpg

READONLY_AUTHORITY_ROLE = "unihub_web_read"

MAX_STATEMENT_TIMEOUT_MS = 300_000
MAX_LOCK_TIMEOUT_MS = 5_000
MAX_IDLE_TRANSACTION_TIMEOUT_MS = 60_000

_CONNECT_TIMEOUT_SECONDS = 10.0
_COMMAND_TIMEOUT_SECONDS = 30.0
_EXCLUDED_SCHEMAS = ("pg_catalog", "information_schema")
_WRITE_TABLE_PRIVILEGES = ("INSERT", "UPDATE", "DELETE", "TRUNCATE")
_TABLE_RELKINDS = ("r", "p", "f", "v", "m")
_TIMEOUT_BOUNDS_MS = {
    "statement_timeout": MAX_STATEMENT_TIMEOUT_MS,
    "lock_timeout": MAX_LOCK_TIMEOUT_MS,
    "idle_in_transaction_session_timeout": MAX_IDLE_TRANSACTION_TIMEOUT_MS,
}
_ELEVATED_ROLE_ATTRIBUTES = (
    ("rolsuper", "superuser"),
    ("rolcreatedb", "createdb"),
    ("rolcreaterole", "createrole"),
    ("rolreplication", "replication"),
    ("rolbypassrls", "bypassrls"),
)
_IDENTITY_SQL = """
SELECT current_user::text AS current_user,
       session_user::text AS session_user,
       rolcanlogin, rolinherit, rolsuper, rolcreatedb, rolcreaterole,
       rolreplication, rolbypassrls
FROM pg_roles
WHERE rolname = current_user
"""
_DIRECT_MEMBERSHIP_SQL = """
SELECT parent.rolname::text AS rolname, membership.inherit_option
FROM pg_auth_members AS membership
JOIN pg_roles AS parent ON parent.oid = membership.roleid
JOIN pg_roles AS member ON member.oid = membership.member
WHERE member.rolname = current_user
ORDER BY parent.rolname
"""
_EFFECTIVE_MEMBERSHIP_SQL = """
SELECT candidate.rolname::text AS rolname
FROM pg_roles AS candidate
WHERE candidate.rolname <> current_user
  AND pg_has_role(current_user, candidate.oid, 'member')
ORDER BY candidate.rolname
"""
_TABLE_WRITE_SQL = """
SELECT n.nspname::text AS schema_name, c.relname::text AS object_name,
       array_agg(candidate.privilege ORDER BY candidate.privilege) AS privileges
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
CROSS JOIN unnest($2::text[]) AS candidate(privilege)
WHERE c.relkind = ANY($3::text[])
  AND NOT (n.nspname = ANY($1::text[]))
  AND n.nspname NOT LIKE 'pg\\_toast%'
  AND n.nspname NOT LIKE 'pg\\_temp%'
  AND has_table_privilege(current_user, c.oid, candidate.privilege)
GROUP BY n.nspname, c.relname
ORDER BY n.nspname, c.relname
LIMIT 5
"""
_SCHEMA_CREATE_SQL = """
SELECT n.nspname::text AS schema_name
FROM pg_namespace AS n
WHERE NOT (n.nspname = ANY($1::text[]))
  AND n.nspname NOT LIKE 'pg\\_toast%'
  AND n.nspname NOT LIKE 'pg\\_temp%'
  AND has_schema_privilege(current_user, n.oid, 'CREATE')
ORDER BY n.nspname
LIMIT 5
"""
_DATABASE_CREATE_SQL = """
SELECT current_database()::text AS database_name
WHERE has_database_privilege(current_user, current_database(), 'CREATE')
"""
_TIMEOUT_SQL = """
SELECT name::text AS name, setting, reset_val, unit, source::text AS source
FROM pg_settings
WHERE name = ANY($1::text[])
"""


class AiReadOnlyAuthorityError(RuntimeError):
    """The sandbox database credential does not satisfy the read-only contract."""


async def verify_sandbox_readonly_authority(dsn: str) -> str:
    """Connect with ``dsn`` and return the verified read-only principal.

    Raises :class:`AiReadOnlyAuthorityError` whenever any part of the contract
    cannot be proven. The error text names roles and settings only; it never
    contains the DSN or its password.
    """
    credential = dsn.strip()
    if not credential:
        raise AiReadOnlyAuthorityError("AI sandbox read-only DSN is not configured")
    try:
        connection = await asyncpg.connect(
            credential,
            timeout=_CONNECT_TIMEOUT_SECONDS,
            command_timeout=_COMMAND_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # pragma: no cover - exercised by negative controls
        raise AiReadOnlyAuthorityError(
            f"AI sandbox read-only DSN cannot open a PostgreSQL session ({type(exc).__name__})"
        ) from exc
    try:
        principal = await _verify_identity(connection)
        await _verify_write_authority(connection, principal)
        await _verify_session_timeouts(connection, principal)
        return principal
    finally:
        await connection.close()


async def _verify_identity(connection: asyncpg.Connection) -> str:
    row = await connection.fetchrow(_IDENTITY_SQL)
    if row is None:
        raise AiReadOnlyAuthorityError(
            "AI sandbox read-only DSN does not resolve an authenticated PostgreSQL role"
        )
    current_user = str(row["current_user"])
    if current_user != str(row["session_user"]):
        raise AiReadOnlyAuthorityError(
            "AI sandbox read-only login must authenticate directly, not through SET ROLE"
        )
    if not bool(row["rolcanlogin"]):
        raise AiReadOnlyAuthorityError(
            f"AI sandbox read-only role {current_user} is not a LOGIN principal"
        )
    elevated = [
        label for column, label in _ELEVATED_ROLE_ATTRIBUTES if bool(row[column])
    ]
    if elevated:
        raise AiReadOnlyAuthorityError(
            f"AI sandbox read-only login {current_user} has elevated role attributes: "
            + ", ".join(elevated)
        )
    if not bool(row["rolinherit"]):
        raise AiReadOnlyAuthorityError(
            f"AI sandbox read-only login {current_user} must INHERIT its read-only authority"
        )
    direct = await connection.fetch(_DIRECT_MEMBERSHIP_SQL)
    direct_roles = {str(item["rolname"]) for item in direct}
    if direct_roles != {READONLY_AUTHORITY_ROLE}:
        raise AiReadOnlyAuthorityError(
            f"AI sandbox read-only login {current_user} must be a direct member of exactly "
            f"{READONLY_AUTHORITY_ROLE}; found {_render_roles(direct_roles)}"
        )
    if not all(bool(item["inherit_option"]) for item in direct):
        raise AiReadOnlyAuthorityError(
            f"AI sandbox read-only login {current_user} must inherit {READONLY_AUTHORITY_ROLE}"
        )
    effective = {
        str(item["rolname"])
        for item in await connection.fetch(_EFFECTIVE_MEMBERSHIP_SQL)
    }
    if effective != {READONLY_AUTHORITY_ROLE}:
        raise AiReadOnlyAuthorityError(
            f"AI sandbox read-only login {current_user} has unexpected effective "
            f"memberships: {_render_roles(effective)}"
        )
    return current_user


async def _verify_write_authority(
    connection: asyncpg.Connection, principal: str
) -> None:
    writable = await connection.fetch(
        _TABLE_WRITE_SQL,
        list(_EXCLUDED_SCHEMAS),
        list(_WRITE_TABLE_PRIVILEGES),
        list(_TABLE_RELKINDS),
    )
    if writable:
        rendered = ", ".join(
            f"{row['schema_name']}.{row['object_name']}[{','.join(row['privileges'])}]"
            for row in writable
        )
        raise AiReadOnlyAuthorityError(
            f"AI sandbox read-only login {principal} holds effective write authority on "
            f"application tables: {rendered}"
        )
    creatable = [
        str(row["schema_name"]) for row in await connection.fetch(_SCHEMA_CREATE_SQL, list(_EXCLUDED_SCHEMAS))
    ]
    if creatable:
        raise AiReadOnlyAuthorityError(
            f"AI sandbox read-only login {principal} holds CREATE on application schemas: "
            + ", ".join(creatable)
        )
    database = await connection.fetchval(_DATABASE_CREATE_SQL)
    if database is not None:
        raise AiReadOnlyAuthorityError(
            f"AI sandbox read-only login {principal} holds CREATE on database {database}"
        )


async def _verify_session_timeouts(
    connection: asyncpg.Connection, principal: str
) -> None:
    rows = await connection.fetch(_TIMEOUT_SQL, list(_TIMEOUT_BOUNDS_MS))
    settings = {str(row["name"]): row for row in rows}
    missing = sorted(set(_TIMEOUT_BOUNDS_MS) - set(settings))
    if missing:
        raise AiReadOnlyAuthorityError(
            "AI sandbox read-only login cannot read bounded session defaults: "
            + ", ".join(missing)
        )
    for name, maximum in _TIMEOUT_BOUNDS_MS.items():
        row = settings[name]
        if str(row["unit"]) != "ms":
            raise AiReadOnlyAuthorityError(
                f"AI sandbox read-only login reports {name} in unexpected units"
            )
        effective = _milliseconds(row["setting"], name)
        inherited = _milliseconds(row["reset_val"], name)
        if effective <= 0 or inherited <= 0:
            raise AiReadOnlyAuthorityError(
                f"AI sandbox read-only login {principal} must set a non-zero {name} "
                "default on the role, database or cluster"
            )
        if effective > maximum or inherited > maximum:
            raise AiReadOnlyAuthorityError(
                f"AI sandbox read-only login {principal} exceeds the permitted {name} "
                f"bound of {maximum} ms"
            )
    statement = _milliseconds(settings["statement_timeout"]["setting"], "statement_timeout")
    lock = _milliseconds(settings["lock_timeout"]["setting"], "lock_timeout")
    inherited_lock = _milliseconds(settings["lock_timeout"]["reset_val"], "lock_timeout")
    inherited_statement = _milliseconds(
        settings["statement_timeout"]["reset_val"], "statement_timeout"
    )
    if lock >= statement or inherited_lock >= inherited_statement:
        raise AiReadOnlyAuthorityError(
            f"AI sandbox read-only login {principal} must keep lock_timeout below "
            "statement_timeout"
        )


def _milliseconds(raw: object, name: str) -> int:
    try:
        return int(str(raw))
    except (TypeError, ValueError) as exc:
        raise AiReadOnlyAuthorityError(
            f"AI sandbox read-only login reports a non-numeric {name}"
        ) from exc


def _render_roles(roles: set[str]) -> str:
    return ", ".join(sorted(roles)) if roles else "none"
