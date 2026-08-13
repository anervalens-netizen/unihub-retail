"""Fault-injection contract for the PostgreSQL-owned outbox dispatcher."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import inspect
from pathlib import Path
from typing import Any

import pytest

from test_transactional_outbox import (
    MemoryOutboxRepository,
    RETRY_DELAYS_SECONDS,
    required_symbol,
)


SALES_EVENT_TYPE = "retail.sales_generation_promoted.v1"


NOW = datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)
EFFECT_SHA256 = "e" * 64


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
    worker_source = Path("backend/worker.py").read_text(encoding="utf-8")
    tree_source = " ".join(worker_source.split())

    assert "start_outbox_dispatcher" in tree_source
    assert 'worker_role == "operations"' in tree_source
    assert "OUTBOX_QUEUE_NAME" not in worker_source


@pytest.mark.asyncio
async def test_fixed_retry_schedule_redacts_error_and_attempt_eight_is_dead() -> None:
    dispatch = required_symbol("services.outbox_worker", "dispatch_outbox_once")
    repository = MemoryOutboxRepository()
    event = repository.seed(now=NOW, name="poison-sales")

    async def poison(_event: Any) -> dict[str, str]:
        raise RuntimeError("private customer record must never be persisted")

    attempt_at = NOW
    for attempt, delay in enumerate(RETRY_DELAYS_SECONDS, start=1):
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
            assert event.available_at == attempt_at + timedelta(seconds=delay)
            attempt_at = event.available_at
        else:
            assert event.state == "dead"
            assert event.dead_at == attempt_at


@pytest.mark.asyncio
async def test_crash_before_effect_retries_without_losing_the_event() -> None:
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

    await dispatch(
        repository=repository,
        consumers={SALES_EVENT_TYPE: consumer},
        owner="operations-before",
        now=NOW + timedelta(seconds=5),
        batch_size=50,
        lease_seconds=60,
    )
    assert event.state == "completed"
    assert transports == 2
    assert effective_mutations == 1
    assert len(repository.receipts) == 1


@pytest.mark.asyncio
async def test_crash_after_effect_before_receipt_is_effective_once() -> None:
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

    await dispatch(
        repository=repository,
        consumers={SALES_EVENT_TYPE: idempotent_consumer},
        owner="operations-after",
        now=NOW + timedelta(seconds=5),
        batch_size=50,
        lease_seconds=60,
    )
    assert event.state == "completed"
    assert transports == 2
    assert effective_mutations == 1
    assert len(repository.receipts) == 1


@pytest.mark.asyncio
async def test_expired_lease_is_reclaimed_and_stale_owner_is_fenced() -> None:
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
    assert event.completed_at == recovered_at
    with pytest.raises(RuntimeError, match="stale outbox claim"):
        await repository.mark_completed(
            event_id=event.id,
            owner="operations-lost",
            epoch=stale_epoch,
            now=recovered_at,
        )
