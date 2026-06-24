from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any
from unittest.mock import AsyncMock

import pytest

import scripts.import_historical as historical


class TransactionContext(AbstractAsyncContextManager[None]):
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> None:
        self.entered = True

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        self.exited = True


class FakeConnection:
    def __init__(self) -> None:
        self.tx = TransactionContext()

    def transaction(self) -> TransactionContext:
        return self.tx


@pytest.mark.asyncio
async def test_historical_lifecycle_reconciliation_is_atomic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConnection()
    rebuild = AsyncMock()
    monkeypatch.setattr(
        historical,
        "rebuild_agent_lifecycle_reporting",
        rebuild,
    )

    await historical.reconcile_lifecycle(conn)  # type: ignore[arg-type]

    assert conn.tx.entered is True
    assert conn.tx.exited is True
    rebuild.assert_awaited_once_with(conn)
