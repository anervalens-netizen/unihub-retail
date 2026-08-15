"""Fault-injection contract for the PostgreSQL-owned outbox dispatcher."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import inspect
from pathlib import Path
from typing import Any

import pytest

import services.outbox_worker as outbox_worker_module
from test_transactional_outbox import (
    MemoryOutboxRepository,
    RETRY_DELAYS_SECONDS,
    required_symbol,
)


ROOT = Path(__file__).resolve().parents[2]
SALES_EVENT_TYPE = "retail.sales_generation_promoted.v1"


NOW = datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)
EFFECT_SHA256 = "e" * 64


class RecordingOutboxRepository(MemoryOutboxRepository):
    def __init__(self) -> None:
        super().__init__()
        self.renewal_times: list[datetime] = []

    async def renew_lease(self, **kwargs: Any) -> bool:
        self.renewal_times.append(kwargs["now"])
        return await super().renew_lease(**kwargs)


class LeaseLossRepository(MemoryOutboxRepository):
    async def renew_lease(self, **_kwargs: Any) -> bool:
        raise RuntimeError("stale outbox claim")


class ReceiptWriteLeaseLossRepository(MemoryOutboxRepository):
    async def record_receipt(self, **kwargs: Any) -> bool:
        event = self.events[kwargs["event_id"]]
        event.claim_owner = "operations-new-owner"
        event.claim_epoch += 1
        raise RuntimeError("receipt write interrupted after lease loss")


def _set_runtime_clock(
    monkeypatch: pytest.MonkeyPatch,
    value: datetime,
) -> None:
    monkeypatch.setattr(outbox_worker_module, "_utc_now", lambda: value)


def _receipt(event: Any) -> dict[str, str]:
    return {
        "consumer": "grile_v2",
        "domain_generation_key": (
            f"grile_v2:{event.generation_hash}:{event.revision}"
        ),
        "effect_sha256": EFFECT_SHA256,
    }


def test_dispatcher_surface_is_small_and_has_no_valkey_dependency() -> None:
    dispatch = required_symbol("services.outbox_worker", "dispatch_outbox_once")
    parameters = set(inspect.signature(dispatch).parameters)

    assert parameters == {
        "repository",
        "consumers",
        "owner",
        "now",
        "batch_size",
        "lease_seconds",
    }
    assert not ({"redis", "valkey", "queue"} & parameters)


def test_existing_operations_worker_owns_dispatch_without_a_new_queue() -> None:
    required_symbol("services.outbox_worker", "dispatch_outbox_once")
    worker_source = (ROOT / "backend/worker.py").read_text(encoding="utf-8")
    tree_source = " ".join(worker_source.split())

    assert "start_outbox_dispatcher" in tree_source
    assert 'worker_role == "operations"' in tree_source
    assert "OUTBOX_QUEUE_NAME" not in worker_source


@pytest.mark.asyncio
async def test_fixed_retry_schedule_redacts_error_and_attempt_eight_is_dead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch = required_symbol("services.outbox_worker", "dispatch_outbox_once")
    repository = MemoryOutboxRepository()
    event = repository.seed(now=NOW, name="poison-sales")

    async def poison(_event: Any) -> dict[str, str]:
        raise RuntimeError("private customer record must never be persisted")

    attempt_at = NOW
    for attempt, delay in enumerate(RETRY_DELAYS_SECONDS, start=1):
        terminal_at = attempt_at + timedelta(seconds=1)
        _set_runtime_clock(monkeypatch, terminal_at)
        await dispatch(
            repository=repository,
            consumers={SALES_EVENT_TYPE: poison},
            owner="operations-poison",
            now=attempt_at,
            batch_size=50,
            lease_seconds=60,
        )
        assert event.attempt_count == attempt
        assert event.last_error_code == "handler_failed"
        assert "alice" not in event.last_error_code.casefold()
        if attempt < 8:
            assert event.state == "pending"
            assert event.available_at == terminal_at + timedelta(seconds=delay)
            attempt_at = event.available_at
        else:
            assert event.state == "dead"
            assert event.dead_at == terminal_at


@pytest.mark.asyncio
async def test_crash_before_effect_retries_without_losing_the_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch = required_symbol("services.outbox_worker", "dispatch_outbox_once")
    repository = MemoryOutboxRepository()
    event = repository.seed(now=NOW, name="crash-before-effect")
    transports = 0
    effective_mutations = 0

    async def consumer(claimed: Any) -> dict[str, str]:
        nonlocal transports, effective_mutations
        transports += 1
        if transports == 1:
            raise RuntimeError("worker stopped before provider effect")
        effective_mutations += 1
        return _receipt(claimed)

    _set_runtime_clock(monkeypatch, NOW + timedelta(seconds=1))
    await dispatch(
        repository=repository,
        consumers={SALES_EVENT_TYPE: consumer},
        owner="operations-before",
        now=NOW,
        batch_size=50,
        lease_seconds=60,
    )
    assert event.state == "pending"
    assert effective_mutations == 0

    retry_at = event.available_at
    _set_runtime_clock(monkeypatch, retry_at + timedelta(seconds=1))
    await dispatch(
        repository=repository,
        consumers={SALES_EVENT_TYPE: consumer},
        owner="operations-before",
        now=retry_at,
        batch_size=50,
        lease_seconds=60,
    )
    assert event.state == "completed"
    assert transports == 2
    assert effective_mutations == 1
    assert len(repository.receipts) == 1


@pytest.mark.asyncio
async def test_crash_after_effect_before_receipt_is_effective_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch = required_symbol("services.outbox_worker", "dispatch_outbox_once")
    repository = MemoryOutboxRepository(fail_next_receipt_write=True)
    event = repository.seed(now=NOW, name="crash-after-effect")
    provider_keys: set[str] = set()
    transports = 0
    effective_mutations = 0

    async def idempotent_consumer(claimed: Any) -> dict[str, str]:
        nonlocal transports, effective_mutations
        transports += 1
        receipt = _receipt(claimed)
        key = receipt["domain_generation_key"]
        if key not in provider_keys:
            provider_keys.add(key)
            effective_mutations += 1
        return receipt

    _set_runtime_clock(monkeypatch, NOW + timedelta(seconds=1))
    await dispatch(
        repository=repository,
        consumers={SALES_EVENT_TYPE: idempotent_consumer},
        owner="operations-after",
        now=NOW,
        batch_size=50,
        lease_seconds=60,
    )
    assert event.state == "pending"
    assert effective_mutations == 1
    assert repository.receipts == {}

    retry_at = event.available_at
    _set_runtime_clock(monkeypatch, retry_at + timedelta(seconds=1))
    await dispatch(
        repository=repository,
        consumers={SALES_EVENT_TYPE: idempotent_consumer},
        owner="operations-after",
        now=retry_at,
        batch_size=50,
        lease_seconds=60,
    )
    assert event.state == "completed"
    assert transports == 2
    assert effective_mutations == 1
    assert len(repository.receipts) == 1


@pytest.mark.asyncio
async def test_expired_lease_is_reclaimed_and_stale_owner_is_fenced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch = required_symbol("services.outbox_worker", "dispatch_outbox_once")
    repository = MemoryOutboxRepository()
    event = repository.seed(now=NOW, name="lost-worker")
    first_claim = await repository.claim_batch(
        owner="operations-lost",
        now=NOW,
        limit=1,
        lease_seconds=60,
    )
    assert first_claim == [event]
    stale_epoch = event.claim_epoch

    async def consumer(claimed: Any) -> dict[str, str]:
        return _receipt(claimed)

    recovered_at = NOW + timedelta(seconds=61)
    completed_at = recovered_at + timedelta(seconds=1)
    _set_runtime_clock(monkeypatch, completed_at)
    await dispatch(
        repository=repository,
        consumers={SALES_EVENT_TYPE: consumer},
        owner="operations-recovery",
        now=recovered_at,
        batch_size=50,
        lease_seconds=60,
    )

    assert event.state == "completed"
    assert event.attempt_count == 2
    assert event.claim_epoch == stale_epoch + 1
    assert event.completed_at == completed_at
    with pytest.raises(RuntimeError, match="stale outbox claim"):
        await repository.mark_completed(
            event_id=event.id,
            owner="operations-lost",
            epoch=stale_epoch,
            now=recovered_at,
        )


@pytest.mark.asyncio
async def test_long_effect_renews_lease_and_uses_fresh_completion_time() -> None:
    dispatch = required_symbol("services.outbox_worker", "dispatch_outbox_once")
    repository = RecordingOutboxRepository()
    started_at = datetime.now(timezone.utc)
    event = repository.seed(now=started_at, name="heartbeat")

    async def slow_consumer(claimed: Any) -> dict[str, str]:
        await asyncio.sleep(0.45)
        return _receipt(claimed)

    await dispatch(
        repository=repository,
        consumers={SALES_EVENT_TYPE: slow_consumer},
        owner="operations-heartbeat",
        now=started_at,
        batch_size=1,
        lease_seconds=1,
    )

    assert event.state == "completed"
    assert event.completed_at is not None and event.completed_at > started_at
    assert len(repository.renewal_times) >= 3


@pytest.mark.asyncio
async def test_heartbeat_lease_loss_cancels_effect_and_cannot_ack() -> None:
    dispatch = required_symbol("services.outbox_worker", "dispatch_outbox_once")
    repository = LeaseLossRepository()
    started_at = datetime.now(timezone.utc)
    event = repository.seed(now=started_at, name="lease-loss")
    cancelled = asyncio.Event()

    async def blocked_consumer(_claimed: Any) -> dict[str, str]:
        try:
            await asyncio.sleep(2)
        finally:
            cancelled.set()
        return _receipt(_claimed)

    await dispatch(
        repository=repository,
        consumers={SALES_EVENT_TYPE: blocked_consumer},
        owner="operations-lease-loss",
        now=started_at,
        batch_size=1,
        lease_seconds=1,
    )

    assert cancelled.is_set()
    assert event.state == "processing"
    assert event.completed_at is None
    assert repository.receipts == {}


@pytest.mark.asyncio
async def test_failure_path_cannot_transition_after_claim_is_stolen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch = required_symbol("services.outbox_worker", "dispatch_outbox_once")
    repository = ReceiptWriteLeaseLossRepository()
    event = repository.seed(now=NOW, name="claim-stolen")
    _set_runtime_clock(monkeypatch, NOW + timedelta(seconds=1))

    await dispatch(
        repository=repository,
        consumers={SALES_EVENT_TYPE: lambda claimed: _async_receipt(claimed)},
        owner="operations-old-owner",
        now=NOW,
        batch_size=1,
        lease_seconds=60,
    )

    assert event.state == "processing"
    assert event.claim_owner == "operations-new-owner"
    assert event.last_error_code is None
    assert event.completed_at is None


async def _async_receipt(event: Any) -> dict[str, str]:
    return _receipt(event)
