"""External timeout enforcement proofs: disposable PostgreSQL only."""
from __future__ import annotations

import asyncio
import os
from typing import Any

import asyncpg
import pytest

from tests.test_ai_assistant_db_authority import (
    AI_LOGIN, authority_database, dsn_for,
)

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1", reason="requires isolated PostgreSQL"
)


@pytest.mark.anyio
async def test_same_readonly_role_can_cancel_and_terminate_other_session(authority_database: Any) -> None:
    from ai_assistant.db_authority import verify_sandbox_readonly_authority

    assert await verify_sandbox_readonly_authority(dsn_for(AI_LOGIN)) == AI_LOGIN
    guard = await asyncpg.connect(dsn_for(AI_LOGIN))
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


async def wait_until(predicate: Any) -> None:
    async with asyncio.timeout(8):
        while not predicate():
            await asyncio.sleep(0.02)


@pytest.mark.anyio
async def test_host_guard_cancels_statement_with_timeout_disabled(authority_database: Any) -> None:
    from ai_assistant.db_guard import DatabaseSessionGuard, GuardLimits

    guard = DatabaseSessionGuard(dsn_for(AI_LOGIN), limits=GuardLimits(0.25, 0.15, 0.3, 0.03))
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

    guard = DatabaseSessionGuard(dsn_for(AI_LOGIN), limits=GuardLimits(20, 0.2, 20, 0.03))
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

    guard = DatabaseSessionGuard(dsn_for(AI_LOGIN), limits=GuardLimits(20, 5, 0.2, 0.03))
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

    guard = DatabaseSessionGuard(dsn_for(AI_LOGIN), limits=GuardLimits(0.1, 0.1, 0.1, 0.03))
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

    guard = DatabaseSessionGuard(dsn_for(AI_LOGIN), limits=GuardLimits(poll_seconds=0.03))
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
    guard = db_guard.DatabaseSessionGuard(dsn_for(AI_LOGIN))
    try:
        await guard.start()
        assert not guard.ready
        assert guard.error == "AI database guard disconnected or scan failed"
        await wait_until(lambda: guard.ready)
        assert guard.error is None
    finally:
        await guard.close()
