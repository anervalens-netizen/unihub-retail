"""Sales-outbox to Campaigns, Contests and Grile V2 delivery contract."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import inspect
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute
import pytest

from auth import require_auth
from test_transactional_outbox import (
    MemoryOutboxRepository,
    required_symbol,
)
from routers.grile import router
from services import grile_pilot_v2
from services.grile_pilot_v2_registry import PILOT_V2_MONTH, PILOT_V2_SHEETS


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
        }


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

    worker_source = Path("backend/worker.py").read_text(encoding="utf-8")
    assert "trigger_grile_pilot_v2_sync(" not in worker_source
    assert "start_grile_pilot_v2_sync(" not in worker_source
    assert "run_grile_pilot_v2_sync_loop(" not in worker_source

    delivery_source = inspect.getsource(inspect.getmodule(delivery))
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
        FullRegistryRepo(),
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
