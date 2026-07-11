from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

import logging_config
from db.connection import close_db_pool, get_pool


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("UNIHUB_TEST_DATABASE") != "1",
        reason="Requires the explicitly isolated PostgreSQL test database",
    ),
]


@pytest_asyncio.fixture(autouse=True)
async def _detach_handler() -> AsyncIterator[None]:
    await logging_config.detach_db_error_handler()
    yield
    await logging_config.detach_db_error_handler()


class _Acquire:
    def __init__(self, enter: Callable[[], Any]) -> None:
        self._enter = enter

    async def __aenter__(self) -> Any:
        return self._enter()

    async def __aexit__(self, *_args: Any) -> None:
        return None


class _Pool:
    def __init__(self, enter: Callable[[], Any]) -> None:
        self._enter = enter

    def acquire(self) -> _Acquire:
        return _Acquire(self._enter)


def _record(message: str = "db handler test", *, extra: dict[str, Any] | None = None) -> logging.LogRecord:
    record = logging.LogRecord("tests.db_error", logging.ERROR, __file__, 1, message, (), None)
    for key, value in (extra or {}).items():
        setattr(record, key, value)
    return record


async def test_logger_exception_persists_traceback_and_redacts_isolated_postgres() -> None:
    pool = await get_pool()
    marker = "H16-LOGGER-EXCEPTION-UNIQUE"
    logging_config.attach_db_error_handler(pool)
    logger = logging.getLogger("tests.h16.integration")
    try:
        try:
            raise ValueError(marker)
        except ValueError:
            logger.exception(
                "failed token=super-secret %s", marker,
                extra={"Authorization": "Bearer secret-value", "nested": [{"salary_cnp": "1234567890123"}]},
            )
        await logging_config.detach_db_error_handler()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT message, traceback, extra FROM error_logs WHERE message LIKE $1 ORDER BY id DESC LIMIT 1",
                f"%{marker}%",
            )
            await conn.execute("DELETE FROM error_logs WHERE message LIKE $1", f"%{marker}%")
        assert row is not None
        assert "ValueError" in row["traceback"] and marker in row["traceback"]
        assert "super-secret" not in row["message"]
        assert "secret-value" not in str(row["extra"])
        assert "1234567890123" not in str(row["extra"])
    finally:
        await logging_config.detach_db_error_handler()
        await close_db_pool()


async def test_event_redaction_limits_and_unserializable_values() -> None:
    handler = logging_config.DBErrorHandler(queue_size=1, write_timeout=1, drain_timeout=1)
    record = _record(
        "Bearer abc.def.ghi password=hunter2 cnp=1234567890123 " + "m" * 3000,
        extra={
            "Cookie": "session-value",
            "nested": [{"access_token": "access-value", "safe": object()}],
            "payload": "x" * 10000,
        },
    )
    event = handler._event_from_record(record)
    assert len(event.message) == 2000
    assert "hunter2" not in event.message and "1234567890123" not in event.message
    assert event.extra_json is not None and len(event.extra_json) <= 8000
    assert "session-value" not in event.extra_json and "access-value" not in event.extra_json


async def test_queue_is_bounded_and_failure_fallback_does_not_recurse(capsys: pytest.CaptureFixture[str]) -> None:
    entered = asyncio.Event()

    async def block_forever() -> None:
        entered.set()
        await asyncio.Event().wait()

    class _BlockingConn:
        async def execute(self, *_args: Any) -> None:
            await block_forever()

    handler = logging_config.DBErrorHandler(queue_size=1, write_timeout=30, drain_timeout=0.1)
    handler.attach(_Pool(lambda: _BlockingConn()), asyncio.get_running_loop())
    before = logging_config.DB_ERROR_LOG_DROPPED_TOTAL.labels(reason="queue_full")._value.get()
    handler.emit(_record("first"))
    await asyncio.wait_for(entered.wait(), timeout=1)
    handler.emit(_record("second"))
    handler.emit(_record("third"))
    await asyncio.sleep(0)
    assert logging_config.DB_ERROR_LOG_DROPPED_TOTAL.labels(reason="queue_full")._value.get() == before + 1
    assert handler._consumer is not None
    await handler.detach()
    assert "DB_ERROR_LOG_DROP reason=queue_full" in capsys.readouterr().err


async def test_persist_error_and_timeout_are_bounded(capsys: pytest.CaptureFixture[str]) -> None:
    class _BrokenConn:
        async def execute(self, *_args: Any) -> None:
            raise RuntimeError("DATABASE_URL=postgresql://secret")

    handler = logging_config.DBErrorHandler(queue_size=2, write_timeout=0.1, drain_timeout=0.1)
    handler.attach(_Pool(lambda: _BrokenConn()), asyncio.get_running_loop())
    handler.emit(_record("password=hunter2"))
    await handler.detach()
    stderr = capsys.readouterr().err
    assert "persist_error" in stderr
    assert "hunter2" not in stderr and "postgresql://secret" not in stderr


async def test_persist_timeout_is_counted_and_consumer_finishes(capsys: pytest.CaptureFixture[str]) -> None:
    class _SlowConn:
        async def execute(self, *_args: Any) -> None:
            await asyncio.Event().wait()

    handler = logging_config.DBErrorHandler(queue_size=1, write_timeout=0.05, drain_timeout=0.2)
    before = logging_config.DB_ERROR_LOG_DROPPED_TOTAL.labels(reason="persist_timeout")._value.get()
    handler.attach(_Pool(lambda: _SlowConn()), asyncio.get_running_loop())
    handler.emit(_record("timeout event"))
    await handler.detach()
    assert logging_config.DB_ERROR_LOG_DROPPED_TOTAL.labels(reason="persist_timeout")._value.get() == before + 1
    assert "persist_timeout" in capsys.readouterr().err


async def test_attach_detach_is_idempotent_and_emit_outside_lifecycle_is_safe() -> None:
    pool = await get_pool()
    logging_config.attach_db_error_handler(pool)
    first = logging_config._db_handler_instance
    logging_config.attach_db_error_handler(pool)
    assert logging_config._db_handler_instance is first
    assert first is not None and first._consumer is not None
    await logging_config.detach_db_error_handler()
    await logging_config.detach_db_error_handler()
    assert logging_config._db_handler_instance is None
    logging.getLogger("tests.h16.lifecycle").error("ignored after detach")
    await close_db_pool()


async def test_main_unhandled_exception_logs_at_error_without_changing_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from starlette.requests import Request
    import main

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(main.logger, "error", lambda *_args, **kwargs: calls.append(kwargs))
    request = Request({"type": "http", "method": "GET", "path": "/boom", "headers": [], "state": {}})
    response = await main.unhandled_exception_handler(request, RuntimeError("boom"))
    assert response.status_code == 500
    assert calls and calls[0]["exc_info"][1].args == ("boom",)
