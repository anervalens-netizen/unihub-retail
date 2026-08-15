"""Bounded PostgreSQL outbox dispatcher owned by the operations worker."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from typing import Any
from uuid import uuid4

from prometheus_client import Counter, Gauge, Histogram

from repositories.transactional_outbox import TransactionalOutboxRepository


logger = logging.getLogger(__name__)
Consumer = Callable[[Any], Awaitable[dict[str, str]]]


class _ClaimLeaseLost(RuntimeError):
    """The fenced attempt can no longer publish a terminal transition."""


OUTBOX_OLDEST_PENDING = Gauge(
    "retail_outbox_oldest_pending_seconds",
    "Age of the oldest pending Retail outbox event.",
)
OUTBOX_HEAD_BLOCKED = Gauge(
    "retail_outbox_head_blocked",
    "Number of pending Retail outbox events blocked by an earlier sequence.",
)
OUTBOX_COMPLETED = Counter(
    "retail_outbox_completed",
    "Retail outbox events completed by this operations worker.",
)
OUTBOX_FAILED = Counter(
    "retail_outbox_failed",
    "Retail outbox delivery attempts that failed with a sanitized code.",
)
OUTBOX_DELIVERY_DURATION = Histogram(
    "retail_outbox_delivery_duration_seconds",
    "Outbox event creation-to-completion duration.",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 900, 3600),
)

_EVENT_CONSUMERS = {
    "retail.pnl_generation_promoted.v1": "pnl_receipt",
    "retail.salary_import_completed.v1": "salary_receipt",
    "retail.planning_forecast_promoted.v1": "planning_receipt",
    "retail.grile_manifest_approved.v1": "grile_manifest_receipt",
}


def _validated_receipt(value: Any) -> tuple[str, str, str]:
    if not isinstance(value, Mapping):
        raise RuntimeError("outbox consumer returned an invalid receipt")
    if set(value) != {"consumer", "domain_generation_key", "effect_sha256"}:
        raise RuntimeError("outbox consumer receipt shape is invalid")
    consumer = value["consumer"]
    generation_key = value["domain_generation_key"]
    effect_sha256 = value["effect_sha256"]
    if not all(isinstance(item, str) for item in value.values()):
        raise RuntimeError("outbox consumer receipt values are invalid")
    return str(consumer), str(generation_key), str(effect_sha256)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _renew_claim(
    repository: Any,
    event: Any,
    owner: str,
    lease_seconds: int,
) -> None:
    try:
        await repository.renew_lease(
            event_id=event.id,
            owner=owner,
            epoch=event.claim_epoch,
            now=_utc_now(),
            lease_seconds=lease_seconds,
        )
    except Exception as exc:
        raise _ClaimLeaseLost("outbox claim lease was lost") from exc


async def _lease_heartbeat(
    repository: Any,
    event: Any,
    owner: str,
    lease_seconds: int,
    stop: asyncio.Event,
) -> None:
    interval = max(0.1, lease_seconds / 3)
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            await _renew_claim(repository, event, owner, lease_seconds)


async def _consume_with_heartbeat(
    consumer: Consumer,
    event: Any,
    heartbeat: asyncio.Task[None],
) -> dict[str, str]:
    async def invoke() -> dict[str, str]:
        return await consumer(event)

    effect = asyncio.create_task(invoke(), name="outbox-consumer-effect")
    try:
        done, _ = await asyncio.wait(
            {effect, heartbeat},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if heartbeat in done:
            error = heartbeat.exception()
            raise error or _ClaimLeaseLost("outbox heartbeat stopped early")
        return await effect
    finally:
        if not effect.done():
            effect.cancel()
            await asyncio.gather(effect, return_exceptions=True)


async def _confirm_claim_and_stop(
    repository: Any,
    event: Any,
    owner: str,
    lease_seconds: int,
    stop: asyncio.Event,
    heartbeat: asyncio.Task[None],
) -> None:
    if heartbeat.done():
        error = heartbeat.exception()
        if error is not None:
            raise error
    await _renew_claim(repository, event, owner, lease_seconds)
    stop.set()
    result = await asyncio.gather(heartbeat, return_exceptions=True)
    if result and isinstance(result[0], BaseException):
        raise result[0]


async def _deliver_claimed(
    *,
    repository: Any,
    consumers: Mapping[str, Consumer],
    event: Any,
    owner: str,
    lease_seconds: int,
) -> None:
    stop = asyncio.Event()
    heartbeat = asyncio.create_task(
        _lease_heartbeat(repository, event, owner, lease_seconds, stop),
        name="outbox-claim-heartbeat",
    )
    try:
        consumer = consumers.get(event.event_type)
        if consumer is None:
            raise RuntimeError("outbox event type has no consumer")
        receipt = _validated_receipt(
            await _consume_with_heartbeat(consumer, event, heartbeat)
        )
        await _renew_claim(repository, event, owner, lease_seconds)
        await repository.record_receipt(
            event_id=event.id,
            owner=owner,
            epoch=event.claim_epoch,
            consumer=receipt[0],
            domain_generation_key=receipt[1],
            effect_sha256=receipt[2],
            received_at=_utc_now(),
        )
        await _confirm_claim_and_stop(
            repository, event, owner, lease_seconds, stop, heartbeat
        )
        completed_at = _utc_now()
        await repository.mark_completed(
            event_id=event.id,
            owner=owner,
            epoch=event.claim_epoch,
            now=completed_at,
        )
    except asyncio.CancelledError:
        raise
    except _ClaimLeaseLost:
        OUTBOX_FAILED.inc()
        return
    except Exception:
        OUTBOX_FAILED.inc()
        try:
            await _confirm_claim_and_stop(
                repository, event, owner, lease_seconds, stop, heartbeat
            )
        except _ClaimLeaseLost:
            return
        try:
            await repository.mark_failed(
                event_id=event.id,
                owner=owner,
                epoch=event.claim_epoch,
                error_code="handler_failed",
                now=_utc_now(),
            )
        except RuntimeError:
            return
        return
    finally:
        stop.set()
        if not heartbeat.done():
            heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
    OUTBOX_COMPLETED.inc()
    created_at = event.created_at
    if created_at.tzinfo is not None and created_at.utcoffset() is not None:
        OUTBOX_DELIVERY_DURATION.observe(
            max(0.0, (completed_at - created_at).total_seconds())
        )


async def dispatch_outbox_once(
    *,
    repository: Any,
    consumers: Mapping[str, Consumer],
    owner: str,
    now: datetime,
    batch_size: int,
    lease_seconds: int,
) -> int:
    """Claim and finish one bounded batch without any queue dependency."""
    claimed = await repository.claim_batch(
        owner=owner,
        now=now,
        limit=batch_size,
        lease_seconds=lease_seconds,
    )
    if not claimed:
        return 0
    await asyncio.gather(
        *(
            _deliver_claimed(
                repository=repository,
                consumers=consumers,
                event=event,
                owner=owner,
                lease_seconds=lease_seconds,
            )
            for event in claimed
        )
    )
    return len(claimed)


def _receipt_only_consumer(name: str) -> Consumer:
    async def consume(event: Any) -> dict[str, str]:
        generation_key = f"{name}:{event.generation_hash}:{event.revision}"
        effect_sha256 = hashlib.sha256(
            json.dumps(
                {
                    "consumer": name,
                    "domain_generation_key": generation_key,
                    "event_type": event.event_type,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return {
            "consumer": name,
            "domain_generation_key": generation_key,
            "effect_sha256": effect_sha256,
        }

    return consume


def _production_consumers(ctx: dict[str, Any]) -> dict[str, Consumer]:
    from services.grile_outbox_delivery import build_sales_generation_consumer

    consumers = {
        event_type: _receipt_only_consumer(consumer)
        for event_type, consumer in _EVENT_CONSUMERS.items()
    }
    consumers["retail.sales_generation_promoted.v1"] = (
        build_sales_generation_consumer(ctx)
    )
    return consumers


async def _refresh_state_metrics(repository: TransactionalOutboxRepository) -> None:
    state = await repository.observe_state(now=_utc_now())
    OUTBOX_OLDEST_PENDING.set(float(state["oldest_pending_seconds"]))
    OUTBOX_HEAD_BLOCKED.set(int(state["head_blocked"]))


async def _dispatcher_loop(ctx: dict[str, Any]) -> None:
    repository = TransactionalOutboxRepository(ctx["db_pool"])
    consumers = _production_consumers(ctx)
    owner = f"operations-{os.getpid()}-{uuid4().hex[:12]}"
    stop = ctx["outbox_dispatcher_stop"]
    while not stop.is_set():
        try:
            processed = await dispatch_outbox_once(
                repository=repository,
                consumers=consumers,
                owner=owner,
                now=_utc_now(),
                batch_size=50,
                lease_seconds=60,
            )
            await _refresh_state_metrics(repository)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning(
                "Outbox dispatch iteration failed error_class=%s",
                type(exc).__name__,
            )
            processed = 0
        if processed:
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=1.0)
        except TimeoutError:
            pass


def start_outbox_dispatcher(ctx: dict[str, Any]) -> None:
    if ctx.get("outbox_dispatcher_task") is not None:
        raise RuntimeError("outbox dispatcher is already active")
    ctx["outbox_dispatcher_stop"] = asyncio.Event()
    ctx["outbox_dispatcher_task"] = asyncio.create_task(
        _dispatcher_loop(ctx),
        name="retail-transactional-outbox",
    )


async def stop_outbox_dispatcher(ctx: dict[str, Any]) -> None:
    stop = ctx.get("outbox_dispatcher_stop")
    task = ctx.get("outbox_dispatcher_task")
    if stop is not None:
        stop.set()
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
