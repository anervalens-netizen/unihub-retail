from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from redis.asyncio import Redis

from rate_limit_store import ValkeyRateLimitStore


class SlowClient:
    async def eval(self, *_args):
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_store_timeout_is_bounded() -> None:
    store = ValkeyRateLimitStore(SlowClient(), timeout_seconds=0.001)  # type: ignore[arg-type]
    with pytest.raises(TimeoutError):
        await store.check("synthetic", 1, 1)


@pytest.mark.asyncio
async def test_real_valkey_two_instances_share_one_atomic_quota() -> None:
    url = os.environ["RATE_LIMIT_TEST_VALKEY_URL"]
    client_a = Redis.from_url(url, decode_responses=True)
    client_b = Redis.from_url(url, decode_responses=True)
    store_a, store_b = ValkeyRateLimitStore(client_a), ValkeyRateLimitStore(client_b)
    key = f"test:ratelimit:{uuid.uuid4().hex}"
    try:
        decisions = await asyncio.gather(*[(store_a if index % 2 else store_b).check(key, 10, 2) for index in range(100)])
        assert sum(decision.allowed for decision in decisions) == 10
        assert sum(not decision.allowed for decision in decisions) == 90
        assert all(0 <= decision.remaining <= 9 for decision in decisions)
        assert all(decision.reset_after_seconds in {1, 2} for decision in decisions)
        assert await client_a.pttl(key) > 0
        assert await client_a.hlen(key) == 2
    finally:
        await client_a.delete(key)
        await store_a.close(); await store_b.close()


@pytest.mark.asyncio
async def test_real_valkey_window_expires_without_request_history_growth() -> None:
    url = os.environ["RATE_LIMIT_TEST_VALKEY_URL"]
    client = Redis.from_url(url, decode_responses=True); store = ValkeyRateLimitStore(client)
    key = f"test:ratelimit:{uuid.uuid4().hex}"
    try:
        assert (await store.check(key, 1, 1)).allowed
        rejected = await store.check(key, 1, 1)
        assert not rejected.allowed and rejected.retry_after_seconds == 1
        await asyncio.sleep(1.05)
        assert (await store.check(key, 1, 1)).allowed
        assert await client.hlen(key) == 2
    finally:
        await client.delete(key); await store.close()
