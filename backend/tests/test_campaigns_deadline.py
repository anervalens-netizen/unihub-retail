from __future__ import annotations

import asyncio
import time
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from config import ConfigError, load_runtime_config
from models import PromoIncentiveSummary
from routers.campaigns import get_promotions_incentives
from services.campaigns import CampaignDateRangeError, CampaignsService
from services.campaigns.metrics import (
    CAMPAIGN_DEADLINE_EXCEEDED_TOTAL,
    CAMPAIGN_REQUEST_REJECTED_TOTAL,
)
from services.request_deadline import RequestDeadline, RequestDeadlineExceeded


def _repo() -> MagicMock:
    repo = MagicMock()
    repo.fetch_promo_total = AsyncMock(return_value=None)
    repo.fetch_promo_store_rows = AsyncMock(return_value=[])
    repo.fetch_incentive_store_rows = AsyncMock(return_value=[])
    repo.fetch_incentive_agent_rows = AsyncMock(return_value=[])
    return repo


def _conn() -> AsyncMock:
    conn = AsyncMock()
    conn.transaction = MagicMock()
    conn.transaction.return_value.__aenter__ = AsyncMock(return_value=conn)
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
    return conn


def _patch_empty_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.campaigns.load_special_cards_config", lambda: ({}, None))
    monkeypatch.setattr(
        "services.campaigns.parse_promotion_definitions",
        lambda _config, _month: ([], None),
    )
    monkeypatch.setattr(
        "services.campaigns.parse_promotion_definition",
        lambda _config, _month, promotion_key=None: (None, None),
    )
    monkeypatch.setattr(
        "services.campaigns.fetch_promo_incentive_summary",
        AsyncMock(return_value=PromoIncentiveSummary()),
    )


async def _run(service: CampaignsService, deadline: RequestDeadline) -> dict:
    return await service.get_promotions_incentives(
        date(2026, 8, 1),
        date(2026, 8, 31),
        None,
        None,
        None,
        None,
        None,
        deadline=deadline,
    )


@pytest.mark.asyncio
async def test_campaign_pool_wait_timeout_cancels_without_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_empty_inputs(monkeypatch)
    cancelled = asyncio.Event()

    async def acquire() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    pool = SimpleNamespace(acquire=acquire, release=AsyncMock())
    service = CampaignsService(_repo(), pool)  # type: ignore[arg-type]
    metric = CAMPAIGN_DEADLINE_EXCEEDED_TOTAL.labels(phase="pool_wait")
    before = metric._value.get()

    with pytest.raises(RequestDeadlineExceeded):
        await _run(service, RequestDeadline(0.03))

    assert cancelled.is_set()
    pool.release.assert_not_awaited()
    assert metric._value.get() == before + 1


@pytest.mark.asyncio
async def test_campaign_query_timeout_cancels_and_releases_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_empty_inputs(monkeypatch)
    conn = _conn()
    query_cancelled = asyncio.Event()

    async def blocked_campaign(_conn: object, _month: str) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            query_cancelled.set()

    monkeypatch.setattr("services.campaigns.get_incentive_campaign", blocked_campaign)
    pool = SimpleNamespace(
        acquire=AsyncMock(return_value=conn),
        release=AsyncMock(return_value=None),
    )
    service = CampaignsService(_repo(), pool)  # type: ignore[arg-type]
    metric = CAMPAIGN_DEADLINE_EXCEEDED_TOTAL.labels(phase="db_load")
    before = metric._value.get()

    with pytest.raises(RequestDeadlineExceeded):
        await _run(service, RequestDeadline(0.03))

    assert query_cancelled.is_set()
    pool.release.assert_awaited_once_with(conn)
    assert metric._value.get() == before + 1


@pytest.mark.asyncio
async def test_campaign_compute_timeout_happens_after_pool_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_empty_inputs(monkeypatch)
    monkeypatch.setattr(
        "services.campaigns.get_incentive_campaign",
        AsyncMock(return_value=None),
    )

    def slow_compute(_snapshot: object) -> dict:
        time.sleep(0.15)
        return {}

    monkeypatch.setattr(
        "services.campaigns.build_promotions_incentives_response",
        slow_compute,
    )
    conn = _conn()
    pool = SimpleNamespace(
        acquire=AsyncMock(return_value=conn),
        release=AsyncMock(return_value=None),
    )
    service = CampaignsService(_repo(), pool)  # type: ignore[arg-type]
    metric = CAMPAIGN_DEADLINE_EXCEEDED_TOTAL.labels(phase="compute")
    before = metric._value.get()

    with pytest.raises(RequestDeadlineExceeded):
        await _run(service, RequestDeadline(0.03))

    pool.release.assert_awaited_once_with(conn)
    assert metric._value.get() == before + 1


@pytest.mark.asyncio
async def test_campaign_router_maps_deadline_to_504() -> None:
    service = AsyncMock()
    service.get_promotions_incentives.side_effect = RequestDeadlineExceeded()

    with pytest.raises(HTTPException) as exc_info:
        await get_promotions_incentives(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            deadline=RequestDeadline(1),
            svc=service,
        )

    assert exc_info.value.status_code == 504


@pytest.mark.asyncio
async def test_invalid_iso_date_records_finite_reason_without_pool_acquire() -> None:
    pool = SimpleNamespace(acquire=AsyncMock(), release=AsyncMock())
    service = CampaignsService(_repo(), pool)  # type: ignore[arg-type]
    metric = CAMPAIGN_REQUEST_REJECTED_TOTAL.labels(reason="invalid_iso_date")
    before = metric._value.get()

    with pytest.raises(CampaignDateRangeError):
        await service.get_promotions_incentives(  # type: ignore[arg-type]
            "bad-date",
            "2026-08-31",
            None,
            None,
            None,
            None,
            None,
        )

    pool.acquire.assert_not_awaited()
    assert metric._value.get() == before + 1


def test_campaign_deadline_runtime_config_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RETAIL_WORKER_ROLE", raising=False)
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "4")
    monkeypatch.setenv("DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY", "2")
    monkeypatch.setenv("CAMPAIGNS_REQUEST_DEADLINE_MS", "6500")

    config = load_runtime_config("web")
    assert config.campaigns_request_deadline_ms == 6500

    monkeypatch.setenv("CAMPAIGNS_REQUEST_DEADLINE_MS", "10001")
    with pytest.raises(ConfigError, match="CAMPAIGNS_REQUEST_DEADLINE_MS"):
        load_runtime_config("web")
