"""External timeout enforcement proofs: disposable PostgreSQL only."""
from __future__ import annotations

import asyncio
import os
from typing import Any

import asyncpg
import pytest

from tests.test_ai_assistant_db_authority import (
    AI_LOGIN, PASSWORD, BOUNDED_DEFAULTS, authority_database, dsn_for,
)

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1", reason="requires isolated PostgreSQL"
)


GUARD_LOGIN = "unihub_ai_guard"


@pytest.fixture(autouse=True)
async def guard_database(authority_database: Any):
    await authority_database.execute(
        f"CREATE ROLE {GUARD_LOGIN} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
        f"NOREPLICATION NOBYPASSRLS INHERIT PASSWORD '{PASSWORD}'"
    )
    try:
        await authority_database.execute(f"GRANT {AI_LOGIN}, pg_read_all_stats TO {GUARD_LOGIN}")
        for statement in BOUNDED_DEFAULTS:
            await authority_database.execute(f"ALTER ROLE {GUARD_LOGIN} {statement}")
        yield authority_database
    finally:
        await authority_database.execute(f"DROP OWNED BY {GUARD_LOGIN}")
        await authority_database.execute(f"DROP ROLE {GUARD_LOGIN}")


@pytest.mark.anyio
async def test_directional_guard_cancel_terminate_and_reverse_denied(authority_database: Any) -> None:
    from ai_assistant.db_authority import verify_sandbox_readonly_authority

    assert await verify_sandbox_readonly_authority(dsn_for(AI_LOGIN)) == AI_LOGIN
    guard = await asyncpg.connect(dsn_for(GUARD_LOGIN))
    target = await asyncpg.connect(dsn_for(AI_LOGIN))
    query = None
    try:
        assert not await guard.fetchval(
            "SELECT pg_has_role(current_user, 'pg_signal_backend', 'MEMBER')"
        )
        pid = target.get_server_pid()
        query = asyncio.create_task(target.execute("SELECT pg_sleep(20)"))
        async with asyncio.timeout(5):
            while not await guard.fetchval(
                "SELECT state = 'active' AND wait_event = 'PgSleep' "
                "FROM pg_stat_activity WHERE pid = $1", pid
            ):
                await asyncio.sleep(0.02)
        assert await guard.fetchval("SELECT pg_cancel_backend($1)", pid)
        with pytest.raises(asyncpg.QueryCanceledError):
            await query
        assert await target.fetchval("SELECT 1") == 1
        for function in ("pg_cancel_backend", "pg_terminate_backend"):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await target.fetchval(f"SELECT {function}($1)", guard.get_server_pid())
        assert not await target.fetchval(
            "SELECT pg_has_role(current_user, 'unihub_ai_guard', 'MEMBER')"
        )
        for sql in ("SET ROLE unihub_ai_guard", "GRANT unihub_ai_guard TO unihub_ai_readonly"):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await target.execute(sql)
        assert await guard.fetchval("SELECT 1") == 1
        assert await guard.fetchval("SELECT pg_terminate_backend($1, 1000)", pid)
        async with asyncio.timeout(5):
            while not target.is_closed():
                await asyncio.sleep(0.02)
    finally:
        if query is not None and not query.done():
            query.cancel()
            await asyncio.gather(query, return_exceptions=True)
        await target.close()
        await guard.close()


@pytest.mark.anyio
async def test_guard_authority_accepts_only_dedicated_login(authority_database: Any) -> None:
    from ai_assistant.guard_authority import verify_guard_authority, AiGuardAuthorityError
    assert await verify_guard_authority(dsn_for(GUARD_LOGIN)) == GUARD_LOGIN
    with pytest.raises(AiGuardAuthorityError, match="directly"):
        await verify_guard_authority(dsn_for(AI_LOGIN))
    with pytest.raises(AiGuardAuthorityError, match="not configured"):
        await verify_guard_authority("")
    from ai_assistant.guard_authority import verify_guard_connection
    connection = await asyncpg.connect(dsn_for(GUARD_LOGIN))
    try:
        await connection.execute("SET ROLE unihub_ai_readonly")
        with pytest.raises(AiGuardAuthorityError, match="directly"):
            await verify_guard_connection(connection)
    finally:
        await connection.close()


@pytest.mark.anyio
@pytest.mark.parametrize("mutation", [
    "ALTER ROLE unihub_ai_guard SUPERUSER",
    "ALTER ROLE unihub_ai_guard NOINHERIT",
    "GRANT pg_signal_backend TO unihub_ai_guard",
    "REVOKE pg_read_all_stats FROM unihub_ai_guard",
    "GRANT unihub_ai_readonly TO unihub_ai_guard WITH ADMIN OPTION",
    "GRANT UPDATE ON ai_readonly_authority_probe TO unihub_ai_guard",
    "GRANT CREATE ON SCHEMA public TO unihub_ai_guard",
    "GRANT CREATE ON DATABASE unihub_test TO unihub_ai_guard",
    "ALTER ROLE unihub_ai_guard SET statement_timeout = 0",
    "ALTER ROLE unihub_ai_guard SET lock_timeout = '6s'",
    "ALTER ROLE unihub_ai_guard SET idle_in_transaction_session_timeout = 0",
])
async def test_guard_authority_rejects_unsafe_capabilities(authority_database: Any, mutation: str) -> None:
    from ai_assistant.guard_authority import verify_guard_authority, AiGuardAuthorityError
    await authority_database.execute(mutation)
    with pytest.raises(AiGuardAuthorityError):
        await verify_guard_authority(dsn_for(GUARD_LOGIN))


@pytest.mark.anyio
async def test_guard_reconnect_rechecks_authority(authority_database: Any) -> None:
    from ai_assistant.db_guard import DatabaseSessionGuard, GuardLimits
    guard = DatabaseSessionGuard(dsn_for(GUARD_LOGIN), limits=GuardLimits(poll_seconds=0.03))
    try:
        await guard.start()
        assert guard.ready and guard._connection is not None
        await authority_database.execute("ALTER ROLE unihub_ai_guard SET statement_timeout = 0")
        await authority_database.fetchval("SELECT pg_terminate_backend($1, 1000)", guard._connection.get_server_pid())
        await wait_until(lambda: guard.error is not None)
        await asyncio.sleep(1.2)
        assert not guard.ready
        await authority_database.execute("ALTER ROLE unihub_ai_guard SET statement_timeout = '120s'")
        await wait_until(lambda: guard.ready)
    finally:
        await guard.close()


async def wait_until(predicate: Any) -> None:
    async with asyncio.timeout(8):
        while not predicate():
            await asyncio.sleep(0.02)


@pytest.mark.anyio
async def test_host_guard_cancels_statement_with_timeout_disabled(authority_database: Any) -> None:
    from ai_assistant.db_guard import DatabaseSessionGuard, GuardLimits

    guard = DatabaseSessionGuard(dsn_for(GUARD_LOGIN), limits=GuardLimits(0.25, 0.15, 0.3, 0.03))
    target = await asyncpg.connect(dsn_for(AI_LOGIN))
    try:
        await guard.start()
        assert guard.ready
        await target.execute("SET statement_timeout = 0")
        # A sandbox can spoof application_name, so it must not create an exemption.
        await target.execute("SET application_name = 'unihub-ai-db-guard'")
        assert await target.fetchval("SELECT 42") == 42
        async with asyncio.timeout(5):
            with pytest.raises(asyncpg.QueryCanceledError, match="user request"):
                await target.execute("SELECT pg_sleep(20)")
        assert await target.fetchval("SELECT 1") == 1
    finally:
        await target.close()
        await guard.close()
    assert not guard.ready


@pytest.mark.anyio
async def test_host_guard_cancels_real_lock_with_timeout_disabled(authority_database: Any) -> None:
    from ai_assistant.db_guard import DatabaseSessionGuard, GuardLimits
    from tests.test_ai_assistant_db_authority import PROBE_TABLE

    guard = DatabaseSessionGuard(dsn_for(GUARD_LOGIN), limits=GuardLimits(20, 0.2, 20, 0.03))
    target = await asyncpg.connect(dsn_for(AI_LOGIN))
    try:
        await authority_database.execute("BEGIN")
        await authority_database.execute(f'LOCK TABLE "{PROBE_TABLE}" IN ACCESS EXCLUSIVE MODE')
        await guard.start()
        await target.execute("SET lock_timeout = 0; SET statement_timeout = 0")
        async with asyncio.timeout(5):
            with pytest.raises(asyncpg.QueryCanceledError, match="user request"):
                await target.fetch(f'SELECT * FROM "{PROBE_TABLE}"')
    finally:
        await authority_database.execute("ROLLBACK")
        await target.close()
        await guard.close()


@pytest.mark.anyio
@pytest.mark.parametrize("aborted", [False, True])
async def test_host_guard_terminates_idle_transaction_with_timeout_disabled(
    authority_database: Any, aborted: bool,
) -> None:
    from ai_assistant.db_guard import DatabaseSessionGuard, GuardLimits

    guard = DatabaseSessionGuard(dsn_for(GUARD_LOGIN), limits=GuardLimits(20, 5, 0.2, 0.03))
    target = await asyncpg.connect(dsn_for(AI_LOGIN))
    try:
        await guard.start()
        await target.execute("SET idle_in_transaction_session_timeout = 0; BEGIN; SELECT 1")
        if aborted:
            with pytest.raises(asyncpg.DivisionByZeroError):
                await target.execute("SELECT 1 / 0")
        await wait_until(target.is_closed)
        assert guard.ready
    finally:
        await target.close()
        await guard.close()


@pytest.mark.anyio
async def test_host_guard_never_signals_another_role(authority_database: Any) -> None:
    from ai_assistant.db_guard import DatabaseSessionGuard, GuardLimits
    from tests.test_ai_assistant_db_authority import WEB_LOGIN

    guard = DatabaseSessionGuard(dsn_for(GUARD_LOGIN), limits=GuardLimits(0.1, 0.1, 0.1, 0.03))
    other = await asyncpg.connect(dsn_for(WEB_LOGIN))
    try:
        await guard.start()
        await other.execute("SET statement_timeout = 0; SELECT pg_sleep(0.5)")
        await other.execute("SET idle_in_transaction_session_timeout = 0; BEGIN; SELECT 1")
        await asyncio.sleep(0.3)
        assert await other.fetchval("SELECT 1") == 1
        await other.execute("ROLLBACK")
        assert guard.ready
    finally:
        await other.close()
        await guard.close()


@pytest.mark.anyio
async def test_guard_disconnect_is_unready_and_reconnect_recovers(authority_database: Any) -> None:
    from ai_assistant.db_guard import DatabaseSessionGuard, GuardLimits

    guard = DatabaseSessionGuard(dsn_for(GUARD_LOGIN), limits=GuardLimits(poll_seconds=0.03))
    try:
        await guard.start()
        connection = guard._connection
        assert connection is not None
        assert await connection.fetchval("SHOW application_name") == "unihub-ai-db-guard"
        pid = connection.get_server_pid()
        await authority_database.fetchval("SELECT pg_terminate_backend($1, 1000)", pid)
        await wait_until(lambda: not guard.ready)
        await wait_until(lambda: guard.ready)
        assert guard._connection is not None
        assert guard._connection.get_server_pid() != pid
    finally:
        await guard.close()


@pytest.mark.anyio
async def test_first_connect_failure_is_unready_then_recovers(
    authority_database: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_assistant import db_guard

    original = db_guard.asyncpg.connect
    calls = 0

    async def flaky(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("private driver detail must not appear in health")
        return await original(*args, **kwargs)

    monkeypatch.setattr(db_guard.asyncpg, "connect", flaky)
    guard = db_guard.DatabaseSessionGuard(dsn_for(GUARD_LOGIN))
    try:
        with pytest.raises(RuntimeError, match="initial scan failed"):
            await guard.start()
        assert not guard.ready
        assert guard.error == "AI database guard disconnected or scan failed"
        # The background loop itself remains recoverable; FastAPI startup closes
        # it when propagating this initial failure so systemd can retry cleanly.
        await wait_until(lambda: guard.ready)
        assert guard.error is None
    finally:
        await guard.close()


@pytest.mark.anyio
async def test_guard_database_aliases_match(authority_database: Any) -> None:
    from ai_assistant.guard_authority import verify_guard_database
    await verify_guard_database(
        dsn_for(AI_LOGIN), dsn_for(GUARD_LOGIN).replace("127.0.0.1", "localhost")
    )


@pytest.mark.anyio
async def test_guard_database_other_database_rejected(authority_database: Any) -> None:
    from ai_assistant.guard_authority import verify_guard_database, AiGuardAuthorityError
    from urllib.parse import urlsplit, urlunsplit
    # Created only in the canonical runner's disposable PostgreSQL container.
    await authority_database.execute("CREATE DATABASE ai_guard_other_database")
    parsed = urlsplit(dsn_for(GUARD_LOGIN))
    other = urlunsplit(parsed._replace(path="/ai_guard_other_database"))
    try:
        with pytest.raises(AiGuardAuthorityError, match="same PostgreSQL server and database"):
            await verify_guard_database(dsn_for(AI_LOGIN), other)
    finally:
        await authority_database.execute("DROP DATABASE ai_guard_other_database")


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["postmaster_start", "database_oid", "server_port", "current_user", "session_user"])
async def test_guard_database_identity_mismatch_rejected(authority_database: Any, monkeypatch, field) -> None:
    from ai_assistant import guard_authority
    original = guard_authority.asyncpg.connect

    class AlteredIdentity:
        def __init__(self, connection):
            self.connection = connection

        async def fetchrow(self, sql):
            identity = dict(await self.connection.fetchrow(sql))
            identity[field] = "different-identity"
            return identity

        async def close(self, **kwargs):
            await self.connection.close(**kwargs)

        def terminate(self):
            self.connection.terminate()

    async def connect(dsn, **kwargs):
        connection = await original(dsn, **kwargs)
        return AlteredIdentity(connection) if GUARD_LOGIN in dsn else connection

    monkeypatch.setattr(guard_authority.asyncpg, "connect", connect)
    with pytest.raises(guard_authority.AiGuardAuthorityError):
        await guard_authority.verify_guard_database(dsn_for(AI_LOGIN), dsn_for(GUARD_LOGIN))
