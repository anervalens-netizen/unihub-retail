"""Host-side ceilings for direct sandbox SQL, independent of USERSET defaults.

Only the explicit sandbox login's sessions are signaled. The host-only guard
inherits that login, never the reverse; sandbox code cannot signal the guard.
A sandbox-controlled application_name must never exempt a target from policing.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
import logging
import time

import asyncpg

from .guard_authority import verify_guard_connection

logger = logging.getLogger(__name__)
GUARD_APPLICATION_NAME = "unihub-ai-db-guard"

# Server timestamps avoid host/server clock skew. query_start is a conservative
# upper bound for lock-wait duration (PostgreSQL exposes no wait-start timestamp).
# Include aborted idle transactions: they can retain resources too.
_SCAN_SQL = """
SELECT pid,
       CASE
         WHEN state IN ('idle in transaction', 'idle in transaction (aborted)')
              AND clock_timestamp() - state_change > $3 * interval '1 second'
           THEN pg_terminate_backend(pid)
         WHEN state = 'active' AND (
              clock_timestamp() - query_start > $1 * interval '1 second'
              OR (wait_event_type = 'Lock'
                  AND clock_timestamp() - query_start > $2 * interval '1 second'))
           THEN pg_cancel_backend(pid)
       END AS signaled
FROM pg_stat_activity
WHERE usesysid = (SELECT oid FROM pg_roles WHERE rolname = 'unihub_ai_readonly')
  AND pid <> pg_backend_pid()
"""


@dataclass(frozen=True)
class GuardLimits:
    statement_seconds: float = 300
    lock_seconds: float = 5
    idle_transaction_seconds: float = 60
    poll_seconds: float = 1


class DatabaseSessionGuard:
    def __init__(self, dsn: str, *, limits: GuardLimits | None = None):
        self._dsn = dsn
        self.limits = limits or GuardLimits()
        self._connection: asyncpg.Connection | None = None
        self._task: asyncio.Task[None] | None = None
        self._first_attempt = asyncio.Event()
        self._last_scan: float | None = None
        self.error: str | None = "AI database guard has not completed its first scan"

    @property
    def ready(self) -> bool:
        return (
            self._last_scan is not None
            and time.monotonic() - self._last_scan < self.limits.poll_seconds + 4
            and self._connection is not None
            and not self._connection.is_closed()
            and self._task is not None
            and not self._task.done()
        )

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=GUARD_APPLICATION_NAME)
        await self._first_attempt.wait()
        if not self.ready:
            raise RuntimeError("AI database guard initial scan failed")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        self._last_scan = None

    async def _connect(self) -> None:
        self._connection = await asyncpg.connect(
            self._dsn,
            timeout=3,
            command_timeout=3,
            server_settings={"application_name": GUARD_APPLICATION_NAME},
        )
        # Check inherited defaults before overriding them, including every reconnect.
        await verify_guard_connection(self._connection)
        await self._connection.execute(
            "SET statement_timeout = '3000ms'; SET lock_timeout = '1000ms'; "
            "SET idle_in_transaction_session_timeout = '3000ms'"
        )

    async def _scan(self) -> None:
        assert self._connection is not None
        await self._connection.fetch(
            _SCAN_SQL,
            self.limits.statement_seconds,
            self.limits.lock_seconds,
            self.limits.idle_transaction_seconds,
        )
        self._last_scan = time.monotonic()
        self.error = None

    async def _disconnect(self) -> None:
        connection, self._connection = self._connection, None
        self._last_scan = None
        if connection is not None:
            try:
                await connection.close(timeout=1)
            except Exception:
                connection.terminate()

    async def _run(self) -> None:
        backoff = 1.0
        try:
            while True:
                delay = self.limits.poll_seconds
                try:
                    if self._connection is None:
                        await self._connect()
                    await self._scan()
                    backoff = 1.0
                except Exception:
                    # Never render driver exceptions: they may contain credentials.
                    self.error = "AI database guard disconnected or scan failed"
                    await self._disconnect()
                    logger.warning(self.error)
                    delay = backoff
                    backoff = min(backoff * 2, 5)
                finally:
                    self._first_attempt.set()
                await asyncio.sleep(delay)
        finally:
            await self._disconnect()
