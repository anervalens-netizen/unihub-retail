"""Isolated-database certification for the sandbox read-only authority preflight.

``AI_ASSISTANT_READONLY_DSN`` is handed to arbitrary model-generated code, so
the runtime connects with that exact credential at startup and fails closed
unless the principal is provably read-only. These tests run only against a
disposable isolated PostgreSQL (see ``UNIHUB_TEST_DATABASE``) and never touch
production.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest

from ai_assistant.db_authority import (
    READONLY_AUTHORITY_ROLE,
    AiReadOnlyAuthorityError,
    verify_sandbox_readonly_authority,
)

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="AI read-only authority certification requires an isolated PostgreSQL database",
)

PASSWORD = "isolated-probe-password"  # noqa: S105 - disposable isolated database only
PROBE_TABLE = "ai_readonly_authority_probe"
WRITE_ROLE = "unihub_business_write"
AI_LOGIN = "unihub_ai_readonly"
WEB_LOGIN = "unihub_ai_probe_web"
ELEVATED_LOGIN = "unihub_ai_probe_elevated"
UNBOUNDED_LOGIN = "unihub_ai_probe_unbounded"
OVER_BOUND_LOGIN = "unihub_ai_probe_overbound"
BOUNDED_DEFAULTS = (
    "SET statement_timeout = '120s'",
    "SET lock_timeout = '5s'",
    "SET idle_in_transaction_session_timeout = '60s'",
)


def dsn_for(login: str) -> str:
    parsed = urlsplit(os.environ["DATABASE_URL"])
    authority = f"{login}:{PASSWORD}@{parsed.hostname}:{parsed.port}"
    return urlunsplit(("postgresql", authority, parsed.path, "", ""))


# Only the disposable LOGINs this file creates may be dropped. The NOLOGIN
# authority roles ``unihub_web_read`` and ``unihub_business_write`` belong to
# migration 040 and are shared with the rest of the isolated suite: dropping
# them, or running DROP OWNED BY for them, would revoke every migration-granted
# privilege and break unrelated tests.
PROBE_LOGINS = (
    ELEVATED_LOGIN,
    UNBOUNDED_LOGIN,
    OVER_BOUND_LOGIN,
    AI_LOGIN,
    WEB_LOGIN,
)
_AUTHORITY_ROLE_BOOTSTRAP = """
DO $$
DECLARE authority_name TEXT;
BEGIN
    FOREACH authority_name IN ARRAY ARRAY['unihub_web_read', 'unihub_business_write']
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = authority_name) THEN
            EXECUTE format(
                'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
                'NOINHERIT NOBYPASSRLS NOREPLICATION',
                authority_name
            );
        END IF;
        EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), authority_name);
        EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', authority_name);
    END LOOP;
END
$$;
"""


async def _drop_probe_logins(connection: asyncpg.Connection) -> None:
    for login in PROBE_LOGINS:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_roles WHERE rolname = $1", login
        )
        if not exists:
            continue
        await connection.execute(f'DROP OWNED BY "{login}" CASCADE')
        await connection.execute(f'DROP ROLE "{login}"')


async def _recreate_roles(connection: asyncpg.Connection) -> None:
    await _drop_probe_logins(connection)
    # Idempotent, additive and non-destructive: it never alters or drops the
    # shared authority roles and never revokes their migration ACLs.
    await connection.execute(_AUTHORITY_ROLE_BOOTSTRAP)
    await connection.execute(
        f'CREATE ROLE "{AI_LOGIN}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
        f"NOREPLICATION NOBYPASSRLS INHERIT CONNECTION LIMIT 4 PASSWORD '{PASSWORD}'"
    )
    for statement in BOUNDED_DEFAULTS:
        await connection.execute(f'ALTER ROLE "{AI_LOGIN}" {statement}')
    await connection.execute(f'GRANT "{READONLY_AUTHORITY_ROLE}" TO "{AI_LOGIN}"')

    await connection.execute(
        f'CREATE ROLE "{WEB_LOGIN}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
        f"NOREPLICATION NOBYPASSRLS INHERIT CONNECTION LIMIT 4 PASSWORD '{PASSWORD}'"
    )
    for statement in BOUNDED_DEFAULTS:
        await connection.execute(f'ALTER ROLE "{WEB_LOGIN}" {statement}')
    await connection.execute(f'GRANT "{READONLY_AUTHORITY_ROLE}" TO "{WEB_LOGIN}"')
    await connection.execute(f'GRANT "{WRITE_ROLE}" TO "{WEB_LOGIN}"')

    await connection.execute(
        f'CREATE ROLE "{ELEVATED_LOGIN}" LOGIN SUPERUSER PASSWORD \'{PASSWORD}\''
    )
    await connection.execute(
        f'CREATE ROLE "{UNBOUNDED_LOGIN}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
        f"NOREPLICATION NOBYPASSRLS INHERIT CONNECTION LIMIT 4 PASSWORD '{PASSWORD}'"
    )
    await connection.execute(f'GRANT "{READONLY_AUTHORITY_ROLE}" TO "{UNBOUNDED_LOGIN}"')
    await connection.execute(
        f'CREATE ROLE "{OVER_BOUND_LOGIN}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
        f"NOREPLICATION NOBYPASSRLS INHERIT CONNECTION LIMIT 4 PASSWORD '{PASSWORD}'"
    )
    await connection.execute(
        f'ALTER ROLE "{OVER_BOUND_LOGIN}" SET statement_timeout = \'600s\''
    )
    await connection.execute(
        f'ALTER ROLE "{OVER_BOUND_LOGIN}" SET lock_timeout = \'30s\''
    )
    await connection.execute(
        f'ALTER ROLE "{OVER_BOUND_LOGIN}" SET '
        "idle_in_transaction_session_timeout = '300s'"
    )
    await connection.execute(f'GRANT "{READONLY_AUTHORITY_ROLE}" TO "{OVER_BOUND_LOGIN}"')

    await connection.execute(
        f'CREATE TABLE IF NOT EXISTS "{PROBE_TABLE}" (id integer PRIMARY KEY, value text)'
    )
    await connection.execute(
        f'GRANT SELECT ON TABLE "{PROBE_TABLE}" TO "{READONLY_AUTHORITY_ROLE}"'
    )
    await connection.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLE "{PROBE_TABLE}" '
        f'TO "{WRITE_ROLE}"'
    )


@pytest.fixture
async def authority_database() -> Any:
    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        await _recreate_roles(connection)
        yield connection
    finally:
        # The probe table owns the only privilege this file grants to the shared
        # authority roles, so dropping it restores their exact prior ACL state.
        await connection.execute(f'DROP TABLE IF EXISTS "{PROBE_TABLE}"')
        await _drop_probe_logins(connection)
        await connection.close()


@pytest.mark.anyio
async def test_dedicated_read_only_login_passes(authority_database: Any) -> None:
    del authority_database

    assert await verify_sandbox_readonly_authority(dsn_for(AI_LOGIN)) == AI_LOGIN


@pytest.mark.anyio
async def test_read_only_login_connection_limit_is_enforced(authority_database: Any) -> None:
    del authority_database
    connections = [await asyncpg.connect(dsn_for(AI_LOGIN)) for _ in range(4)]
    try:
        with pytest.raises(asyncpg.TooManyConnectionsError):
            await asyncpg.connect(dsn_for(AI_LOGIN))
    finally:
        await asyncio.gather(*(connection.close() for connection in connections))


@pytest.mark.anyio
async def test_web_business_write_login_is_rejected(authority_database: Any) -> None:
    del authority_database

    with pytest.raises(AiReadOnlyAuthorityError) as failure:
        await verify_sandbox_readonly_authority(dsn_for(WEB_LOGIN))

    assert READONLY_AUTHORITY_ROLE in str(failure.value)
    assert PASSWORD not in str(failure.value)


@pytest.mark.anyio
async def test_elevated_login_is_rejected(authority_database: Any) -> None:
    del authority_database

    with pytest.raises(AiReadOnlyAuthorityError, match="elevated role attributes: superuser"):
        await verify_sandbox_readonly_authority(dsn_for(ELEVATED_LOGIN))


@pytest.mark.anyio
async def test_unlimited_connections_are_rejected(authority_database: Any) -> None:
    await authority_database.execute(f'ALTER ROLE "{AI_LOGIN}" CONNECTION LIMIT -1')

    with pytest.raises(AiReadOnlyAuthorityError, match="CONNECTION LIMIT 4"):
        await verify_sandbox_readonly_authority(dsn_for(AI_LOGIN))


@pytest.mark.anyio
async def test_unbounded_timeout_defaults_are_rejected(authority_database: Any) -> None:
    del authority_database

    with pytest.raises(AiReadOnlyAuthorityError, match="statement_timeout"):
        await verify_sandbox_readonly_authority(dsn_for(UNBOUNDED_LOGIN))


@pytest.mark.anyio
async def test_timeout_defaults_above_the_permitted_maximum_are_rejected(
    authority_database: Any,
) -> None:
    del authority_database

    with pytest.raises(AiReadOnlyAuthorityError, match="bound of"):
        await verify_sandbox_readonly_authority(dsn_for(OVER_BOUND_LOGIN))


@pytest.mark.anyio
async def test_unusable_credential_is_rejected() -> None:
    with pytest.raises(AiReadOnlyAuthorityError, match="cannot open"):
        await verify_sandbox_readonly_authority(dsn_for("unihub_ai_absent_login"))


@pytest.mark.anyio
async def test_verified_login_reads_application_data_and_cannot_write(
    authority_database: Any,
) -> None:
    """The certified identity keeps SELECT and PostgreSQL refuses every write."""
    connection = authority_database
    await connection.execute(f'INSERT INTO "{PROBE_TABLE}" (id, value) VALUES (1, \'a\')')
    assert await verify_sandbox_readonly_authority(dsn_for(AI_LOGIN)) == AI_LOGIN

    probe = await asyncpg.connect(dsn_for(AI_LOGIN))
    try:
        assert await probe.fetchval(f'SELECT count(*) FROM "{PROBE_TABLE}"') == 1
        for private_table in (
            "ai_assistant_conversations",
            "ai_assistant_messages",
            "ai_assistant_artifacts",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await probe.fetchval(f'SELECT count(*) FROM "{private_table}"')
        for statement in (
            f'INSERT INTO "{PROBE_TABLE}" (id, value) VALUES (2, \'b\')',
            f'UPDATE "{PROBE_TABLE}" SET value = \'c\'',
            f'DELETE FROM "{PROBE_TABLE}"',
            f'TRUNCATE "{PROBE_TABLE}"',
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await probe.execute(statement)
    finally:
        await probe.close()


@pytest.mark.anyio
async def test_timeouts_are_verified_from_the_exact_dedicated_session(
    authority_database: Any,
) -> None:
    del authority_database
    await verify_sandbox_readonly_authority(dsn_for(AI_LOGIN))

    probe = await asyncpg.connect(dsn_for(AI_LOGIN))
    try:
        settings = {
            row["name"]: row
            for row in await probe.fetch(
                "SELECT name, setting, reset_val, unit FROM pg_settings "
                "WHERE name IN ('statement_timeout', 'lock_timeout', "
                "'idle_in_transaction_session_timeout')"
            )
        }
        assert {name: row["unit"] for name, row in settings.items()} == {
            "statement_timeout": "ms",
            "lock_timeout": "ms",
            "idle_in_transaction_session_timeout": "ms",
        }
        assert int(settings["statement_timeout"]["setting"]) == 120_000
        assert int(settings["lock_timeout"]["setting"]) == 5_000
        assert int(settings["idle_in_transaction_session_timeout"]["setting"]) == 60_000
        assert int(settings["statement_timeout"]["reset_val"]) == 120_000
        assert int(settings["lock_timeout"]["reset_val"]) == 5_000
        assert int(settings["idle_in_transaction_session_timeout"]["reset_val"]) == 60_000
    finally:
        await probe.close()
