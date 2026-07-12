"""Atomic bounded Valkey store for distributed rate-limit decisions."""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Any, Awaitable, Protocol, cast

from redis.asyncio import Redis


_FIXED_WINDOW_SCRIPT = """
local clock = redis.call('TIME')
local now_ms = (tonumber(clock[1]) * 1000) + math.floor(tonumber(clock[2]) / 1000)
local window_ms = tonumber(ARGV[2])
local window_start = tonumber(redis.call('HGET', KEYS[1], 'window_start') or tostring(now_ms))
local current = tonumber(redis.call('HGET', KEYS[1], 'count') or '0')
if now_ms - window_start >= window_ms then
  window_start = now_ms
  current = 0
end
local ttl = math.max(1, window_ms - (now_ms - window_start))
if current >= tonumber(ARGV[1]) then
  return {0, 0, ttl, ttl}
end
current = current + 1
redis.call('HSET', KEYS[1], 'window_start', window_start, 'count', current)
redis.call('PEXPIRE', KEYS[1], ttl)
return {1, tonumber(ARGV[1]) - current, 0, ttl}
""".strip()


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int
    reset_after_seconds: int


class RateLimitStore(Protocol):
    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision: ...
    async def close(self) -> None: ...


class ValkeyRateLimitStore:
    def __init__(self, client: Redis, timeout_seconds: float = 1.0) -> None:
        self.client = client
        self.timeout_seconds = timeout_seconds

    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        operation = cast(
            Awaitable[Any],
            self.client.eval(_FIXED_WINDOW_SCRIPT, 1, key, str(limit), str(window_seconds * 1000)),
        )
        result = await asyncio.wait_for(
            operation,
            timeout=self.timeout_seconds,
        )
        allowed, remaining, retry_ms, reset_ms = (int(value) for value in result)
        return RateLimitDecision(
            allowed=bool(allowed),
            remaining=max(0, remaining),
            retry_after_seconds=max(0, math.ceil(retry_ms / 1000)),
            reset_after_seconds=max(1, math.ceil(reset_ms / 1000)),
        )

    async def close(self) -> None:
        await self.client.aclose()
