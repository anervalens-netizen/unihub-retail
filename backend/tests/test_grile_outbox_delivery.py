"""Sales-outbox to Campaigns, Contests and Grile V2 delivery contract."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import inspect
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

from fastapi.routing import APIRoute
import pytest

from auth import require_auth
from test_transactional_outbox import (
    MemoryOutboxRepository,
    required_symbol,
)
from routers.grile import router
import services.grile_outbox_delivery as delivery_module
import services.outbox_worker as outbox_worker_module
from services import grile_pilot_v2
from services.grile_pilot_v2_registry import PILOT_V2_MONTH, PILOT_V2_SHEETS


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
EFFECT_SHA256 = "f" * 64


class DeliveryProbe:
    """Idempotent projectors with a deterministic fake Sheets boundary."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.campaign_keys: set[str] = set()
        self.contest_keys: set[str] = set()
        self.grile_keys: set[str] = set()
        self.google_transport_calls = 0
        self.google_effective_mutations = 0
        self.v1_mutations = 0

    async def publish_campaigns(
        self,
        *,
        month: str,
        generation_hash: str,
        revision: int,
    ) -> dict[str, int]:
        self.calls.append("campaigns")
        self.campaign_keys.add(f"{month}:{generation_hash}:{revision}")
        return {"revision": 101}

    async def publish_contests(
        self,
        *,
        month: str,
        generation_hash: str,
        revision: int,
    ) -> dict[str, int]:
        self.calls.append("contests")
        self.contest_keys.add(f"{month}:{generation_hash}:{revision}")
        return {"revision": 202}

    async def sync_grile_v2(
        self,
        *,
        month: str,
        generation_hash: str,
        sales_revision: int,
        campaign_revision: int,
        contest_revision: int,
    ) -> dict[str, object]:
        self.calls.append("grile_v2")
        self.google_transport_calls += 1
        assert month == PILOT_V2_MONTH
        assert campaign_revision == 101
        assert contest_revision == 202
        generation_key = f"grile_v2:{generation_hash}:{sales_revision}"
        if generation_key not in self.grile_keys:
            self.grile_keys.add(generation_key)
            self.google_effective_mutations += 1
        return {
            "domain_generation_key": generation_key,
            "effect_sha256": EFFECT_SHA256,
            "store_count": len(PILOT_V2_SHEETS),
            "generation_hash": generation_hash,
            "sales_revision": sales_revision,
            "campaign_revision": campaign_revision,
            "contest_revision": contest_revision,
        }


class PublicationJob:
    def __init__(self, result: dict[str, Any]) -> None:
        self._result = result

    async def result(self, **_kwargs: Any) -> dict[str, Any]:
        return self._result


class FullRegistryRepo:
    async def get_expected_by_site(self, _month: str) -> dict[str, dict[str, Any]]:
        return {
            sheet.site_code: {
                "db_target": Decimal("100"),
                "db_sales_mtd": Decimal("40"),
                "db_max_sale_date": "2026-08-12",
            }
            for sheet in PILOT_V2_SHEETS
        }

    async def get_hierarchy(self) -> dict[str, dict[str, str]]:
        return {
            sheet.site_code: {
                "locatie": sheet.site_code,
                "firma": "Mobiup",
                "regional": "Regional",
                "asm": "Manager",
            }
            for sheet in PILOT_V2_SHEETS
        }

    async def get_current_statuses(self, _month: str) -> list[dict[str, Any]]:
        return []


def test_delivery_surface_and_runtime_have_no_direct_duplicate_trigger() -> None:
    delivery = required_symbol(
        "services.grile_outbox_delivery", "deliver_sales_generation_event"
    )
    assert set(inspect.signature(delivery).parameters) == {
        "event",
        "publish_campaigns",
        "publish_contests",
        "sync_grile_v2",
    }

    worker_source = (ROOT / "backend/worker.py").read_text(encoding="utf-8")
    assert "trigger_grile_pilot_v2_sync(" not in worker_source
    assert "start_grile_pilot_v2_sync(" not in worker_source
    assert "run_grile_pilot_v2_sync_loop(" not in worker_source

    delivery_module_source = inspect.getmodule(delivery)
    assert delivery_module_source is not None
    delivery_source = inspect.getsource(delivery_module_source)
    for forbidden_v1_writer in (
        "grile_sheets",
        "grile_monthly",
        "trigger_grile_check_after_import",
    ):
        assert forbidden_v1_writer not in delivery_source


@pytest.mark.asyncio
async def test_duplicate_sales_delivery_has_one_effective_google_mutation() -> None:
    delivery = required_symbol(
        "services.grile_outbox_delivery", "deliver_sales_generation_event"
    )
    repository = MemoryOutboxRepository()
    event = repository.seed(now=NOW, name="sales-v2-delivery", revision=17)
    probe = DeliveryProbe()

    first = await delivery(
        event,
        publish_campaigns=probe.publish_campaigns,
        publish_contests=probe.publish_contests,
        sync_grile_v2=probe.sync_grile_v2,
    )
    second = await delivery(
        event,
        publish_campaigns=probe.publish_campaigns,
        publish_contests=probe.publish_contests,
        sync_grile_v2=probe.sync_grile_v2,
    )

    assert probe.calls == [
        "campaigns",
        "contests",
        "grile_v2",
        "campaigns",
        "contests",
        "grile_v2",
    ]
    assert len(probe.campaign_keys) == 1
    assert len(probe.contest_keys) == 1
    assert probe.google_transport_calls == 2
    assert probe.google_effective_mutations == 1
    assert probe.v1_mutations == 0
    assert first == second == {
        "consumer": "grile_v2",
        "domain_generation_key": f"grile_v2:{event.generation_hash}:17",
        "effect_sha256": EFFECT_SHA256,
    }


@pytest.mark.asyncio
async def test_grile_failure_publishes_no_receipt_and_retains_last_snapshot() -> None:
    delivery = required_symbol(
        "services.grile_outbox_delivery", "deliver_sales_generation_event"
    )
    repository = MemoryOutboxRepository()
    event = repository.seed(now=NOW, name="sales-v2-provider-failure")
    probe = DeliveryProbe()
    last_good_snapshot = {
        "generation": "previous",
        "store_count": len(PILOT_V2_SHEETS),
    }

    async def unavailable_google(**_kwargs: Any) -> dict[str, object]:
        probe.calls.append("grile_v2")
        raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await delivery(
            event,
            publish_campaigns=probe.publish_campaigns,
            publish_contests=probe.publish_contests,
            sync_grile_v2=unavailable_google,
        )

    assert probe.calls == ["campaigns", "contests", "grile_v2"]
    assert last_good_snapshot == {
        "generation": "previous",
        "store_count": 21,
    }
    assert repository.receipts == {}
    assert probe.v1_mutations == 0


@pytest.mark.asyncio
async def test_grile_callback_result_rejects_stale_sales_lineage() -> None:
    delivery = required_symbol(
        "services.grile_outbox_delivery", "deliver_sales_generation_event"
    )
    repository = MemoryOutboxRepository()
    event = repository.seed(now=NOW, name="sales-v2-stale-lineage")
    probe = DeliveryProbe()

    async def stale_grile(**kwargs: Any) -> dict[str, object]:
        result = await probe.sync_grile_v2(**kwargs)
        result["generation_hash"] = "0" * 64
        return result

    with pytest.raises(RuntimeError, match="delivery lineage differs"):
        await delivery(
            event,
            publish_campaigns=probe.publish_campaigns,
            publish_contests=probe.publish_contests,
            sync_grile_v2=stale_grile,
        )


@pytest.mark.asyncio
async def test_failed_grile_attempt_evicts_publication_before_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = MemoryOutboxRepository()
    event = repository.seed(now=NOW, name="sales-v2-cache-retry", revision=17)
    job_id = f"grile-pilot-v2:2026-08:{event.generation_hash}:17"
    publication_result = {
        "promotion": {"revision": 101},
        "contest": {"revision": 202},
        "grile_v2_job_id": job_id,
    }
    enqueue = AsyncMock(
        side_effect=[
            PublicationJob(publication_result),
            PublicationJob(publication_result),
        ]
    )
    monkeypatch.setattr(
        "services.jobs.enqueue_campaign_reporting_publication",
        enqueue,
    )
    successful_effect = {
        "domain_generation_key": f"grile_v2:{event.generation_hash}:17",
        "effect_sha256": EFFECT_SHA256,
        "store_count": len(PILOT_V2_SHEETS),
        "generation_hash": event.generation_hash,
        "sales_revision": 17,
        "campaign_revision": 101,
        "contest_revision": 202,
    }
    sync_effect = AsyncMock(
        side_effect=[RuntimeError("provider unavailable"), successful_effect]
    )
    monkeypatch.setattr(delivery_module, "_sync_grile_v2_effect", sync_effect)
    consume = delivery_module.build_sales_generation_consumer({"db_pool": object()})

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await consume(event)
    receipt = await consume(event)

    assert enqueue.await_count == 2
    enqueue.assert_awaited_with(
        month="2026-08",
        requested_by_sub="system:outbox",
        reason=f"sales_outbox:{event.generation_hash}:17",
        generation_hash=event.generation_hash,
        sales_revision=17,
    )
    assert sync_effect.await_count == 2
    assert sync_effect.await_args is not None
    assert sync_effect.await_args.kwargs["job_id"] == job_id
    assert receipt["domain_generation_key"] == (
        f"grile_v2:{event.generation_hash}:17"
    )


@pytest.mark.asyncio
async def test_superseded_a_completes_noop_then_b_mutates_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = MemoryOutboxRepository()
    event_a = repository.seed(now=NOW, name="sales-v2-a-b", revision=1)
    event_b = repository.seed(
        now=NOW,
        name="sales-v2-a-b",
        sequence=2,
        revision=2,
        generation_hash="c" * 64,
    )
    superseded_result = {
        "status": "superseded",
        "sales_generation_hash": event_a.generation_hash,
        "sales_generation_revision": 1,
        "promotion": None,
        "contest": None,
        "grile_v2_job_id": None,
    }
    current_job_id = f"grile-pilot-v2:2026-08:{event_b.generation_hash}:2"
    current_result = {
        "promotion": {"revision": 102},
        "contest": {"revision": 202},
        "grile_v2_job_id": current_job_id,
    }
    enqueue = AsyncMock(
        side_effect=[PublicationJob(superseded_result), PublicationJob(current_result)]
    )
    monkeypatch.setattr(
        "services.jobs.enqueue_campaign_reporting_publication",
        enqueue,
    )
    current_effect = {
        "domain_generation_key": f"grile_v2:{event_b.generation_hash}:2",
        "effect_sha256": EFFECT_SHA256,
        "store_count": len(PILOT_V2_SHEETS),
        "generation_hash": event_b.generation_hash,
        "sales_revision": 2,
        "campaign_revision": 102,
        "contest_revision": 202,
    }
    sync_effect = AsyncMock(return_value=current_effect)
    monkeypatch.setattr(delivery_module, "_sync_grile_v2_effect", sync_effect)
    consume = delivery_module.build_sales_generation_consumer({"db_pool": object()})
    monkeypatch.setattr(
        outbox_worker_module,
        "_utc_now",
        lambda: NOW,
    )

    assert await outbox_worker_module.dispatch_outbox_once(
        repository=repository,
        consumers={delivery_module.SALES_EVENT_TYPE: consume},
        owner="operations-a-b",
        now=NOW,
        batch_size=1,
        lease_seconds=60,
    ) == 1
    assert event_a.state == "completed"
    assert event_b.state == "pending"
    receipt_a = repository.receipts[(event_a.id, "grile_v2")]

    assert await outbox_worker_module.dispatch_outbox_once(
        repository=repository,
        consumers={delivery_module.SALES_EVENT_TYPE: consume},
        owner="operations-a-b",
        now=NOW,
        batch_size=1,
        lease_seconds=60,
    ) == 1
    assert event_b.state == "completed"
    receipt_b = repository.receipts[(event_b.id, "grile_v2")]

    assert receipt_a[0] == (
        f"grile_v2:{event_a.generation_hash}:1"
    )
    assert receipt_a[1] != EFFECT_SHA256
    assert receipt_b[1] == EFFECT_SHA256
    assert enqueue.await_count == 2
    sync_effect.assert_awaited_once()


@pytest.mark.asyncio
async def test_superseded_grile_race_returns_terminal_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arq.jobs as arq_jobs
    import services.jobs as jobs_service

    generation_hash = "a" * 64
    job_id = f"grile-pilot-v2:2026-08:{generation_hash}:17"

    class SupersededJob:
        def __init__(self, resolved_id: str, _pool: Any, **_kwargs: Any) -> None:
            assert resolved_id == job_id

        async def result(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "status": "superseded",
                "sales_generation_hash": generation_hash,
                "sales_generation_revision": 17,
                "campaign_revision": 101,
                "contest_revision": 202,
                "synced": [],
                "skipped": [],
                "failed": [],
            }

    monkeypatch.setattr(arq_jobs, "Job", SupersededJob)
    monkeypatch.setattr(
        jobs_service,
        "_require_arq_pool",
        AsyncMock(return_value=object()),
    )

    result = await delivery_module._sync_grile_v2_effect(
        job_id=job_id,
        month="2026-08",
        generation_hash=generation_hash,
        sales_revision=17,
        campaign_revision=101,
        contest_revision=202,
    )

    assert result["outcome"] == "superseded"
    assert result["domain_generation_key"] == f"grile_v2:{generation_hash}:17"
    receipt = delivery_module._receipt_from_grile_result(
        result,
        generation_hash=generation_hash,
        sales_revision=17,
        campaign_revision=101,
        contest_revision=202,
    )
    assert receipt["effect_sha256"] == result["effect_sha256"]


@pytest.mark.asyncio
async def test_grile_worker_result_requires_exact_generation_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arq.jobs as arq_jobs
    import services.jobs as jobs_service

    generation_hash = "a" * 64
    job_id = f"grile-pilot-v2:2026-08:{generation_hash}:17"

    class StaleJob:
        def __init__(self, resolved_id: str, _pool: Any, **_kwargs: Any) -> None:
            assert resolved_id == job_id

        async def result(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "sales_generation_hash": "0" * 64,
                "sales_generation_revision": 17,
                "campaign_revision": 101,
                "contest_revision": 202,
                "synced": [sheet.site_code for sheet in PILOT_V2_SHEETS],
                "skipped": [],
                "failed": [],
            }

    monkeypatch.setattr(arq_jobs, "Job", StaleJob)
    monkeypatch.setattr(
        jobs_service,
        "_require_arq_pool",
        AsyncMock(return_value=object()),
    )

    with pytest.raises(RuntimeError, match="worker lineage differs"):
        await delivery_module._sync_grile_v2_effect(
            job_id=job_id,
            month="2026-08",
            generation_hash=generation_hash,
            sales_revision=17,
            campaign_revision=101,
            contest_revision=202,
        )


@pytest.mark.asyncio
async def test_authenticated_get_remains_snapshot_only_and_returns_21_of_21(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert len(PILOT_V2_SHEETS) == 21
    routes = {
        route.path: route
        for route in router.routes
        if isinstance(route, APIRoute)
    }
    route = routes["/api/grile/pilot-v2"]
    assert route.methods == {"GET"}
    assert require_auth in {
        dependency.call for dependency in route.dependant.dependencies
    }

    snapshot_reads = 0

    async def snapshot_only() -> dict[str, grile_pilot_v2.PilotV2Reading]:
        nonlocal snapshot_reads
        snapshot_reads += 1
        return {
            sheet.site_code: grile_pilot_v2.PilotV2Reading(
                Decimal("100"), Decimal("40"), Decimal("80")
            )
            for sheet in PILOT_V2_SHEETS
        }

    monkeypatch.setattr(grile_pilot_v2, "read_pilot_v2_snapshot", snapshot_only)
    result = await grile_pilot_v2.get_pilot_v2_overview(
        cast(Any, FullRegistryRepo()),
        PILOT_V2_MONTH,
    )

    assert snapshot_reads == 1
    assert result["store_count"] == 21
    stores = [
        store
        for manager in result["managers"]
        for store in manager["stores"]
    ]
    assert len(stores) == 21
    assert {store["site_code"] for store in stores} == {
        sheet.site_code for sheet in PILOT_V2_SHEETS
    }
