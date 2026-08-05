from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from services.grile_monthly_google import GoogleSyncAdapter, call_with_backoff
from repositories.grile_monthly_operations import prepare_reset_clear


class _Request:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class _Values:
    def __init__(self, calls):
        self.calls = calls

    def batchGet(self, **kwargs):
        self.calls.append(("read", threading.get_ident(), kwargs))
        return _Request({"valueRanges": []})

    def batchClear(self, **kwargs):
        self.calls.append(("clear", threading.get_ident(), kwargs))
        return _Request({"cleared": True})


class _Sheets:
    def __init__(self, calls):
        self._values = _Values(calls)

    def spreadsheets(self):
        return self

    def values(self):
        return self._values


class _Drive:
    pass


@pytest.mark.asyncio
async def test_google_adapter_constructs_and_uses_clients_on_one_dedicated_thread():
    calls = []
    factory_threads = []

    def factory():
        factory_threads.append(threading.get_ident())
        return _Sheets(calls), _Drive()

    adapter = GoogleSyncAdapter(service_factory=factory)
    try:
        await adapter.start()
        await adapter.request("read_values", {"spreadsheet_id": "sheet", "ranges": []})
        await adapter.request(
            "clear",
            {"spreadsheet_id": "sheet", "ranges": ["Grila!A1"]},
            destructive=True,
        )
    finally:
        assert await adapter.close()

    assert len(set(factory_threads + [item[1] for item in calls])) == 1
    assert factory_threads[0] != threading.get_ident()


@pytest.mark.asyncio
async def test_async_backoff_cancellation_does_not_schedule_next_attempt():
    calls = []

    class Retryable(Exception):
        resp = SimpleNamespace(status=503)

    class FakeAdapter:
        async def request(self, operation, request, **kwargs):
            calls.append(operation)
            raise Retryable()

    task = asyncio.create_task(
        call_with_backoff(
            FakeAdapter(),
            "read_values",
            {},
            label="read",
            attempts=4,
            base_delay=1,
        )
    )
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == ["read_values"]


@pytest.mark.asyncio
async def test_destructive_adapter_call_is_never_retried():
    calls = []

    class Retryable(Exception):
        resp = SimpleNamespace(status=503)

    class FakeAdapter:
        async def request(self, operation, request, **kwargs):
            calls.append(operation)
            raise Retryable()

    with pytest.raises(Retryable):
        await call_with_backoff(
            FakeAdapter(),
            "clear",
            {},
            label="clear",
            attempts=4,
            destructive=True,
        )
    assert calls == ["clear"]


@pytest.mark.asyncio
async def test_stale_owner_cannot_prepare_destructive_clear():
    class Acquire:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def fetchrow(self, query, *args):
            self.args = args
            return None

    class Pool:
        def __init__(self):
            self.conn = Acquire()

        def acquire(self):
            return self.conn

    pool = Pool()
    assert await prepare_reset_clear(
        pool,
        operation_id=7,
        site_code="SITE01",
        execution_owner="old-owner",
        execution_epoch=3,
    ) is None
    assert pool.conn.args[-2:] == ("old-owner", 3)
