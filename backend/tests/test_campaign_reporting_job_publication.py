from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import services.jobs as jobs_service
from services.job_publication import enqueue_campaign_reporting_publication


GENERATION_HASH = "a" * 64


@pytest.mark.asyncio
async def test_campaign_publication_job_is_generation_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = object()
    job = SimpleNamespace(
        job_id=f"campaign-reporting:2026-08:{GENERATION_HASH}:17"
    )
    require_pool = AsyncMock(return_value=pool)
    publish = AsyncMock(return_value=job)
    monkeypatch.setattr(
        "services.job_publication.get_request_id",
        lambda: "request-17",
    )

    result = await enqueue_campaign_reporting_publication(
        month="2026-08",
        requested_by_sub="system:outbox",
        reason=f"sales_outbox:{GENERATION_HASH}:17",
        generation_hash=GENERATION_HASH,
        sales_revision=17,
        require_pool=require_pool,
        publish=publish,
    )

    assert result is job
    require_pool.assert_awaited_once_with()
    publish.assert_awaited_once_with(
        pool,
        "publish_campaign_reporting_background",
        "2026-08",
        "system:outbox",
        f"sales_outbox:{GENERATION_HASH}:17",
        GENERATION_HASH,
        17,
        "request-17",
        _job_id=f"campaign-reporting:2026-08:{GENERATION_HASH}:17",
        _queue_name=jobs_service.SALES_IMPORT_QUEUE_NAME,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("generation_hash", "sales_revision", "message"),
    [
        ("A" * 64, 17, "generation hash"),
        ("a" * 63, 17, "generation hash"),
        (GENERATION_HASH, True, "sales revision"),
        (GENERATION_HASH, 0, "sales revision"),
    ],
)
async def test_campaign_publication_rejects_invalid_generation_identity(
    generation_hash: str,
    sales_revision: int,
    message: str,
) -> None:
    require_pool = AsyncMock()

    with pytest.raises(ValueError, match=message):
        await enqueue_campaign_reporting_publication(
            month="2026-08",
            requested_by_sub="system:outbox",
            reason="sales_outbox",
            generation_hash=generation_hash,
            sales_revision=sales_revision,
            require_pool=require_pool,
            publish=AsyncMock(),
        )

    require_pool.assert_not_awaited()


@pytest.mark.asyncio
async def test_jobs_facade_preserves_generation_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = SimpleNamespace(job_id="campaign-reporting:bound")
    enqueue = AsyncMock(return_value=job)
    monkeypatch.setattr(
        "services.job_publication.enqueue_campaign_reporting_publication",
        enqueue,
    )

    result = await jobs_service.enqueue_campaign_reporting_publication(
        month="2026-08",
        requested_by_sub="system:outbox",
        reason="sales_outbox",
        generation_hash=GENERATION_HASH,
        sales_revision=17,
    )

    assert result is job
    enqueue.assert_awaited_once_with(
        month="2026-08",
        requested_by_sub="system:outbox",
        reason="sales_outbox",
        generation_hash=GENERATION_HASH,
        sales_revision=17,
        require_pool=jobs_service._require_arq_pool,
        publish=jobs_service._publish_arq_job,
    )
