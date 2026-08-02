"""Request-scoped deadlines that propagate remaining budget to asyncpg calls."""
from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar


_T = TypeVar("_T")
_MIN_TIMEOUT_SECONDS = 0.001
_CLEANUP_RESERVE_SECONDS = 0.010


class RequestDeadlineExceeded(TimeoutError):
    """The request cannot safely start another database operation."""


class RequestDeadline:
    """A monotonic, request-wide budget shared by concurrent components."""

    def __init__(self, timeout_seconds: float) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Request deadline must be positive")
        self._expires_at = time.monotonic() + timeout_seconds

    @classmethod
    def from_runtime_config(cls, runtime_config: Any) -> "RequestDeadline":
        """Build once from the already validated web-process configuration."""
        deadline_ms = runtime_config.dashboard_request_deadline_ms
        if deadline_ms is None:
            raise RuntimeError("Dashboard deadline is unavailable outside the web RuntimeConfig")
        return cls(float(deadline_ms) / 1_000)

    def remaining_seconds(self) -> float:
        remaining = self._expires_at - time.monotonic()
        if remaining <= _MIN_TIMEOUT_SECONDS:
            raise RequestDeadlineExceeded("Dashboard request deadline exceeded")
        return remaining

    def remaining_operation_seconds(self) -> float:
        """Leave a small bounded interval for cancellation and pool release."""
        remaining = self.remaining_seconds() - _CLEANUP_RESERVE_SECONDS
        if remaining <= _MIN_TIMEOUT_SECONDS:
            raise RequestDeadlineExceeded("Dashboard request deadline exceeded")
        return remaining

    async def run(self, operation: Awaitable[_T]) -> _T:
        try:
            timeout = self.remaining_seconds()
        except RequestDeadlineExceeded:
            # A fresh coroutine handed to an already-expired deadline must not
            # survive unawaited long enough to emit a RuntimeWarning.
            if inspect.iscoroutine(operation):
                operation.close()
            raise
        try:
            async with asyncio.timeout(timeout):
                return await operation
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise RequestDeadlineExceeded("Dashboard request deadline exceeded") from exc

    def bind_pool(self, pool: Any) -> "DeadlinePool":
        return DeadlinePool(pool, self)


class DeadlineConnection:
    """asyncpg connection facade that supplies the positive remaining timeout."""

    def __init__(self, connection: Any, deadline: RequestDeadline) -> None:
        self._connection = connection
        self._deadline = deadline

    async def _call(self, method: Callable[..., Awaitable[_T]], *args: Any, **kwargs: Any) -> _T:
        remaining = self._deadline.remaining_operation_seconds()
        requested_timeout = kwargs.pop("timeout", None)
        if requested_timeout is not None:
            remaining = min(remaining, float(requested_timeout))
        if remaining <= _MIN_TIMEOUT_SECONDS:
            raise RequestDeadlineExceeded("Dashboard request deadline exceeded")
        try:
            return await method(*args, timeout=remaining, **kwargs)
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise RequestDeadlineExceeded("Dashboard request deadline exceeded") from exc

    async def fetch(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call(self._connection.fetch, *args, **kwargs)

    async def fetchrow(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call(self._connection.fetchrow, *args, **kwargs)

    async def fetchval(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call(self._connection.fetchval, *args, **kwargs)

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call(self._connection.execute, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


class _DeadlineAcquire:
    def __init__(self, acquire_context: Any, deadline: RequestDeadline) -> None:
        self._acquire_context = acquire_context
        self._deadline = deadline

    async def __aenter__(self) -> DeadlineConnection:
        try:
            async with asyncio.timeout(self._deadline.remaining_operation_seconds()):
                connection = await self._acquire_context.__aenter__()
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise RequestDeadlineExceeded("Dashboard request deadline exceeded") from exc
        return DeadlineConnection(connection, self._deadline)

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any:
        return await self._acquire_context.__aexit__(exc_type, exc, traceback)


class DeadlinePool:
    """Pool facade that binds each acquired connection to one request deadline."""

    def __init__(self, pool: Any, deadline: RequestDeadline) -> None:
        self._pool = pool
        self._deadline = deadline

    def acquire(self) -> _DeadlineAcquire:
        self._deadline.remaining_seconds()
        return _DeadlineAcquire(self._pool.acquire(), self._deadline)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._pool, name)
