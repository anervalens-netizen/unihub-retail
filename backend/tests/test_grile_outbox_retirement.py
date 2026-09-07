from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from routers.grile import grile_pilot_v2
from services.grile_outbox_delivery import (
    SALES_EVENT_TYPE,
    build_sales_generation_consumer,
    deliver_sales_generation_event,
)
import services.outbox_worker as outbox_worker_module
from services.grile_pilot_v2_runtime import grile_pilot_v2_sync_background
from test_transactional_outbox import MemoryOutboxRepository


GENERATION_HASH = "a" * 64
NOW = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)


class _PublicationJob:
    def __init__(self, result: dict[str, Any] | BaseException) -> None:
        self._result = result

    async def result(self, **_kwargs: Any) -> dict[str, Any]:
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result


def _event() -> SimpleNamespace:
    return SimpleNamespace(
        event_type=SALES_EVENT_TYPE,
        generation_hash=GENERATION_HASH,
        revision=17,
        payload={
            "month": "2026-08",
            "generation_hash": GENERATION_HASH,
            "revision": 17,
        },
    )


@pytest.mark.asyncio
async def test_sales_delivery_keeps_campaigns_and_returns_retired_receipt() -> None:
    campaigns = AsyncMock(return_value={"revision": 3})
    contests = AsyncMock(return_value={"revision": 4})
    retired = AsyncMock(
        return_value={
            "outcome": "retired",
            "domain_generation_key": f"grile_v2:{GENERATION_HASH}:17",
            "effect_sha256": "b" * 64,
            "generation_hash": GENERATION_HASH,
            "sales_revision": 17,
            "campaign_revision": 3,
            "contest_revision": 4,
        }
    )

    receipt = await deliver_sales_generation_event(
        _event(),
        publish_campaigns=campaigns,
        publish_contests=contests,
        sync_grile_v2=retired,
    )

    campaigns.assert_awaited_once()
    contests.assert_awaited_once()
    retired.assert_awaited_once()
    assert receipt == {
        "consumer": "grile_v2",
        "domain_generation_key": f"grile_v2:{GENERATION_HASH}:17",
        "effect_sha256": "b" * 64,
    }


@pytest.mark.asyncio
async def test_delivery_rejects_stale_effect_lineage() -> None:
    stale = AsyncMock(
        return_value={
            "outcome": "retired",
            "domain_generation_key": f"grile_v2:{GENERATION_HASH}:17",
            "effect_sha256": "b" * 64,
            "generation_hash": "0" * 64,
            "sales_revision": 17,
            "campaign_revision": 3,
            "contest_revision": 4,
        }
    )

    with pytest.raises(RuntimeError, match="delivery lineage differs"):
        await deliver_sales_generation_event(
            _event(),
            publish_campaigns=AsyncMock(return_value={"revision": 3}),
            publish_contests=AsyncMock(return_value={"revision": 4}),
            sync_grile_v2=stale,
        )


@pytest.mark.asyncio
async def test_bound_consumer_never_opens_grile_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    publication_result = {
            "promotion": {"revision": 3},
            "contest": {"revision": 4},
            "sales_generation_hash": GENERATION_HASH,
            "sales_generation_revision": 17,
            "grile_v2_job_id": None,
        }
    job = MagicMock()
    job.result = AsyncMock(return_value=publication_result)
    publication = AsyncMock(return_value=job)
    monkeypatch.setattr("services.jobs.enqueue_campaign_reporting_publication", publication)
    forbidden_pool = AsyncMock(side_effect=AssertionError("Grile queue accessed"))
    monkeypatch.setattr("services.jobs._require_arq_pool", forbidden_pool)

    receipt = await build_sales_generation_consumer({"db_pool": MagicMock()})(_event())

    assert receipt["consumer"] == "grile_v2"
    assert len(receipt["effect_sha256"]) == 64
    forbidden_pool.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_publication_is_evicted_before_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication_result = {
        "promotion": {"revision": 3},
        "contest": {"revision": 4},
        "sales_generation_hash": GENERATION_HASH,
        "sales_generation_revision": 17,
        "grile_v2_job_id": None,
    }
    enqueue = AsyncMock(
        side_effect=[
            _PublicationJob(RuntimeError("publication unavailable")),
            _PublicationJob(publication_result),
        ]
    )
    monkeypatch.setattr("services.jobs.enqueue_campaign_reporting_publication", enqueue)
    consume = build_sales_generation_consumer({"db_pool": object()})

    with pytest.raises(RuntimeError, match="publication unavailable"):
        await consume(_event())
    receipt = await consume(_event())

    assert enqueue.await_count == 2
    assert receipt["consumer"] == "grile_v2"


@pytest.mark.asyncio
async def test_superseded_generation_completes_before_current_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = MemoryOutboxRepository()
    event_a = repository.seed(now=NOW, name="sales-retired-a-b", revision=1)
    event_b = repository.seed(
        now=NOW,
        name="sales-retired-a-b",
        sequence=2,
        revision=2,
        generation_hash="c" * 64,
    )
    enqueue = AsyncMock(
        side_effect=[
            _PublicationJob(
                {
                    "status": "superseded",
                    "sales_generation_hash": event_a.generation_hash,
                    "sales_generation_revision": 1,
                    "promotion": None,
                    "contest": None,
                    "grile_v2_job_id": None,
                }
            ),
            _PublicationJob(
                {
                    "promotion": {"revision": 3},
                    "contest": {"revision": 4},
                    "sales_generation_hash": event_b.generation_hash,
                    "sales_generation_revision": 2,
                    "grile_v2_job_id": None,
                }
            ),
        ]
    )
    monkeypatch.setattr("services.jobs.enqueue_campaign_reporting_publication", enqueue)
    monkeypatch.setattr(outbox_worker_module, "_utc_now", lambda: NOW)
    consume = build_sales_generation_consumer({"db_pool": object()})

    for _event_number in range(2):
        assert await outbox_worker_module.dispatch_outbox_once(
            repository=repository,
            consumers={SALES_EVENT_TYPE: consume},
            owner="operations-retired-a-b",
            now=NOW,
            batch_size=1,
            lease_seconds=60,
        ) == 1

    assert event_a.state == event_b.state == "completed"
    receipt_a = repository.receipts[(event_a.id, "grile_v2")]
    receipt_b = repository.receipts[(event_b.id, "grile_v2")]
    assert receipt_a[0] == f"grile_v2:{event_a.generation_hash}:1"
    assert receipt_b[0] == f"grile_v2:{event_b.generation_hash}:2"
    assert receipt_a[1] != receipt_b[1]
    assert enqueue.await_count == 2


@pytest.mark.asyncio
async def test_queued_legacy_job_drains_as_retired_without_context_access() -> None:
    result = await grile_pilot_v2_sync_background(
        {}, "2026-08", "legacy", GENERATION_HASH, 17, 3, 4
    )
    assert result["status"] == "retired"
    assert result["contract"] == "grile-v2-queued-job-retired-v1"
    assert result["synced"] == result["skipped"] == result["failed"] == []


@pytest.mark.asyncio
async def test_pilot_read_endpoint_is_retired() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await grile_pilot_v2(month="2026-08", _claims=MagicMock())
    assert exc_info.value.status_code == 410
