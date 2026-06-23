from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest

import db.connection as connection


@pytest.mark.asyncio
async def test_pool_configures_server_side_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_pool = object()
    create_pool = AsyncMock(return_value=created_pool)
    monkeypatch.setattr(connection.asyncpg, "create_pool", create_pool)
    monkeypatch.setattr(connection, "pool", None)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://unihub_test:test@127.0.0.1:55432/unihub_test",
    )
    monkeypatch.setenv("UNIHUB_TEST_DATABASE", "1")
    monkeypatch.setenv("DB_STATEMENT_TIMEOUT_MS", "90000")
    monkeypatch.setenv("DB_LOCK_TIMEOUT_MS", "7000")
    monkeypatch.setenv("DB_IDLE_TRANSACTION_TIMEOUT_MS", "45000")

    result = await connection.init_db_pool()

    assert result is created_pool
    call = create_pool.await_args
    assert call is not None
    kwargs = call.kwargs
    assert kwargs["command_timeout"] == 90
    assert kwargs["server_settings"] == {
        "application_name": "unihub-retail",
        "statement_timeout": "90000",
        "lock_timeout": "7000",
        "idle_in_transaction_session_timeout": "45000",
    }


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_live_pool_connections_have_server_timeouts() -> None:
    pool = await connection.get_pool()
    async with pool.acquire() as conn:
        values = await conn.fetchrow(
            """
            SELECT
                EXTRACT(
                    EPOCH FROM current_setting('statement_timeout')::interval
                )::INT AS statement_seconds,
                EXTRACT(
                    EPOCH FROM current_setting('lock_timeout')::interval
                )::INT AS lock_seconds,
                EXTRACT(
                    EPOCH FROM
                        current_setting(
                            'idle_in_transaction_session_timeout'
                        )::interval
                )::INT AS idle_transaction_seconds
            """
        )
    assert values["statement_seconds"] == 120
    assert values["lock_seconds"] == 10
    assert values["idle_transaction_seconds"] == 60
