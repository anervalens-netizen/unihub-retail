"""Regression tests for campaign publication with a one-connection DB pool."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from services.campaign_reporting import CampaignReportingPublication
from services.contest_reporting import ContestReportingPublication
import services.campaign_reporting as campaign_reporting_module
import services.campaign_reporting_worker as worker_module
import services.contest_reporting as contest_reporting_module


GENERATION_HASH = "a" * 64


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> bool:
        return False


class _Connection:
    def transaction(self) -> _Transaction:
        return _Transaction()

    async def fetchrow(self, _query: str, month: str) -> dict[str, Any]:
        assert month == "2026-08"
        return {"generation_hash": GENERATION_HASH, "revision": 17}


class _Acquire:
    def __init__(self, pool: "_SingleConnectionPool") -> None:
        self.pool = pool

    async def __aenter__(self) -> _Connection:
        if self.pool.active:
            raise AssertionError("a second real pool connection was requested")
        self.pool.active = True
        self.pool.acquire_count += 1
        return self.pool.connection

    async def __aexit__(self, *_args: object) -> bool:
        self.pool.active = False
        return False


class _SingleConnectionPool:
    def __init__(self) -> None:
        self.connection = _Connection()
        self.active = False
        self.acquire_count = 0

    def acquire(self) -> _Acquire:
        return _Acquire(self)


class _CampaignPublisher:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def publish_month(
        self,
        period: str,
        *,
        requested_by_sub: str,
        reason: str,
    ) -> CampaignReportingPublication:
        assert period == "2026-08"
        assert requested_by_sub == "system:outbox"
        assert reason == "sales_outbox"
        async with self.pool.acquire() as conn:
            assert isinstance(conn, _Connection)
        return CampaignReportingPublication(
            period=period,
            generation_id=1,
            revision=3,
            row_count=1,
            status="official",
            input_sha256="b" * 64,
        )


class _ContestPublisher:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def publish_month(
        self,
        period: str,
        *,
        requested_by_sub: str,
        reason: str,
    ) -> ContestReportingPublication:
        assert period == "2026-08"
        assert requested_by_sub == "system:outbox"
        assert reason == "sales_outbox"
        async with self.pool.acquire() as conn:
            assert isinstance(conn, _Connection)
        return ContestReportingPublication(
            period=period,
            generation_id=2,
            revision=4,
            row_count=1,
            status="official",
            input_sha256="c" * 64,
        )


@pytest.mark.asyncio
async def test_campaign_publication_reuses_lineage_connection_at_pool_size_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _SingleConnectionPool()
    enqueue = AsyncMock(return_value=SimpleNamespace(job_id="grile-bound"))
    monkeypatch.setattr(
        campaign_reporting_module,
        "CampaignReportingPublisher",
        _CampaignPublisher,
    )
    monkeypatch.setattr(
        contest_reporting_module,
        "ContestReportingPublisher",
        _ContestPublisher,
    )
    monkeypatch.setattr(
        worker_module.grile_pilot_v2_runtime,
        "enqueue_grile_pilot_v2_sync",
        enqueue,
    )

    result = await worker_module.publish_campaign_reporting_background(
        {"db_pool": pool},
        "2026-08",
        "system:outbox",
        "sales_outbox",
        GENERATION_HASH,
        17,
    )

    assert pool.acquire_count == 1
    assert result["sales_generation_hash"] == GENERATION_HASH
    assert result["sales_generation_revision"] == 17
    assert result["promotion"]["revision"] == 3
    assert result["contest"]["revision"] == 4
    assert result["grile_v2_job_id"] == "grile-bound"
    enqueue.assert_awaited_once_with(
        month="2026-08",
        trigger=f"sales_outbox:{GENERATION_HASH}:17",
        generation_hash=GENERATION_HASH,
        sales_revision=17,
        campaign_revision=3,
        contest_revision=4,
    )
