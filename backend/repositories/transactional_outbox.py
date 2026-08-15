"""PostgreSQL-owned transactional outbox persistence.

The migration owns event identity and producer authorization.  This module is
the Release-B operations boundary for fenced claims, effective-once receipts,
terminal transitions, and audited replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any
from uuid import UUID

import asyncpg


RETRY_DELAYS_SECONDS = (5, 30, 120, 300, 900, 1800, 3600, 3600)
_OWNER_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_ERROR_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_CONSUMER_RE = _ERROR_RE
_GENERATION_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,239}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: str
    generation_hash: str
    revision: int
    aggregate_sequence: int
    event_key: str
    payload: dict[str, Any]
    payload_sha256: str
    state: str
    attempt_count: int
    available_at: datetime
    claim_owner: str | None
    claim_epoch: int
    lease_until: datetime | None
    claimed_at: datetime | None
    last_error_code: str | None
    last_error_at: datetime | None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    dead_at: datetime | None
    replay_count: int


_EVENT_COLUMNS = """
    id, event_type, aggregate_type, aggregate_id, generation_hash, revision,
    aggregate_sequence, event_key, payload, payload_sha256, state,
    attempt_count, available_at, claim_owner, claim_epoch, lease_until,
    claimed_at, last_error_code, last_error_at, occurred_at, created_at,
    updated_at, completed_at, dead_at, replay_count
"""

_RECLAIM_EXPIRED_SQL = """
    WITH expired AS MATERIALIZED (
        SELECT event.id,
               (
                   SELECT max(receipt.received_at)
                   FROM retail_outbox_consumer_receipts AS receipt
                   WHERE receipt.event_id = event.id
               ) AS receipt_at
        FROM retail_outbox_events AS event
        WHERE event.state = 'processing' AND event.lease_until <= $1
        FOR UPDATE OF event
    )
    UPDATE retail_outbox_events AS event
    SET state = CASE
            WHEN expired.receipt_at IS NOT NULL THEN 'completed'
            WHEN event.attempt_count = 8 THEN 'dead'
            ELSE 'pending'
        END,
        available_at = CASE
            WHEN expired.receipt_at IS NOT NULL OR event.attempt_count = 8
                THEN event.available_at
            ELSE $1
        END,
        claim_owner = NULL,
        lease_until = NULL,
        last_error_code = CASE
            WHEN expired.receipt_at IS NOT NULL THEN event.last_error_code
            ELSE 'lease_expired'
        END,
        last_error_at = CASE
            WHEN expired.receipt_at IS NOT NULL THEN event.last_error_at
            ELSE $1
        END,
        updated_at = $1,
        completed_at = CASE
            WHEN expired.receipt_at IS NOT NULL
                THEN COALESCE(event.completed_at, expired.receipt_at)
            ELSE event.completed_at
        END,
        dead_at = CASE
            WHEN expired.receipt_at IS NOT NULL THEN NULL
            WHEN event.attempt_count = 8 THEN $1
            ELSE NULL
        END
    FROM expired
    WHERE event.id = expired.id
"""

_CLAIM_SQL = f"""
    WITH candidates AS MATERIALIZED (
        SELECT candidate.id, candidate.aggregate_type, candidate.aggregate_id
        FROM retail_outbox_events AS candidate
        WHERE candidate.state = 'pending'
          AND candidate.available_at <= $2
          AND NOT EXISTS (
              SELECT 1
              FROM retail_outbox_events AS predecessor
              WHERE predecessor.aggregate_type = candidate.aggregate_type
                AND predecessor.aggregate_id = candidate.aggregate_id
                AND predecessor.aggregate_sequence < candidate.aggregate_sequence
                AND predecessor.state <> 'completed'
          )
        ORDER BY candidate.available_at, candidate.created_at, candidate.id
        FOR UPDATE SKIP LOCKED
        LIMIT $3
    ), aggregate_locks AS MATERIALIZED (
        SELECT id, pg_advisory_xact_lock(
            hashtextextended(aggregate_type || chr(31) || aggregate_id, 0)
        ) AS fence
        FROM candidates
    ), updated AS (
        UPDATE retail_outbox_events AS event
        SET state = 'processing',
            attempt_count = event.attempt_count + 1,
            claim_owner = $1,
            claim_epoch = event.claim_epoch + 1,
            lease_until = $2 + ($4 * interval '1 second'),
            claimed_at = $2,
            updated_at = $2
        FROM aggregate_locks
        WHERE event.id = aggregate_locks.id
        RETURNING event.*
    )
    SELECT {_EVENT_COLUMNS} FROM updated ORDER BY available_at, created_at, id
"""

_RECORD_RECEIPT_SQL = """
    INSERT INTO retail_outbox_consumer_receipts (
        event_id, consumer, domain_generation_key, effect_sha256, received_at
    ) VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT DO NOTHING
    RETURNING event_id
"""

_MARK_COMPLETED_SQL = """
    UPDATE retail_outbox_events
    SET state = 'completed', claim_owner = NULL, lease_until = NULL,
        completed_at = $4, updated_at = $4
    WHERE id = $1 AND state = 'processing'
      AND claim_owner = $2 AND claim_epoch = $3
      AND lease_until > $4
    RETURNING id
"""

_RENEW_LEASE_SQL = """
    UPDATE retail_outbox_events
    SET lease_until = $4 + ($5 * interval '1 second'), updated_at = $4
    WHERE id = $1 AND state = 'processing'
      AND claim_owner = $2 AND claim_epoch = $3
      AND lease_until > $4
    RETURNING id
"""

_RECEIPT_CLAIM_SQL = """
    SELECT 1
    FROM retail_outbox_events
    WHERE id = $1 AND state = 'processing'
      AND claim_owner = $2 AND claim_epoch = $3
      AND lease_until > $4
    FOR UPDATE
"""

_MARK_FAILED_SQL = """
    WITH claimed AS MATERIALIZED (
        SELECT event.id,
               (
                   SELECT max(receipt.received_at)
                   FROM retail_outbox_consumer_receipts AS receipt
                   WHERE receipt.event_id = event.id
               ) AS receipt_at
        FROM retail_outbox_events AS event
        WHERE event.id = $1 AND event.state = 'processing'
          AND event.claim_owner = $2 AND event.claim_epoch = $3
          AND event.lease_until > $5
        FOR UPDATE OF event
    )
    UPDATE retail_outbox_events AS event
    SET state = CASE
            WHEN claimed.receipt_at IS NOT NULL THEN 'completed'
            WHEN event.attempt_count = 8 THEN 'dead'
            ELSE 'pending'
        END,
        available_at = CASE
            WHEN claimed.receipt_at IS NOT NULL OR event.attempt_count = 8
                THEN event.available_at
            ELSE $5 + (CASE event.attempt_count
                WHEN 1 THEN 5 WHEN 2 THEN 30 WHEN 3 THEN 120 WHEN 4 THEN 300
                WHEN 5 THEN 900 WHEN 6 THEN 1800 ELSE 3600
            END * interval '1 second')
        END,
        claim_owner = NULL,
        lease_until = NULL,
        last_error_code = CASE
            WHEN claimed.receipt_at IS NOT NULL THEN event.last_error_code
            ELSE $4
        END,
        last_error_at = CASE
            WHEN claimed.receipt_at IS NOT NULL THEN event.last_error_at
            ELSE $5
        END,
        updated_at = $5,
        completed_at = CASE
            WHEN claimed.receipt_at IS NOT NULL
                THEN COALESCE(event.completed_at, claimed.receipt_at)
            ELSE event.completed_at
        END,
        dead_at = CASE
            WHEN claimed.receipt_at IS NOT NULL THEN NULL
            WHEN event.attempt_count = 8 THEN $5
            ELSE NULL
        END
    FROM claimed
    WHERE event.id = claimed.id
    RETURNING event.state
"""

_OBSERVE_STATE_SQL = """
    SELECT
      COALESCE(max(extract(epoch FROM $1 - created_at))
        FILTER (WHERE state = 'pending'), 0) AS oldest_pending_seconds,
      count(*) FILTER (
        WHERE state = 'pending' AND EXISTS (
          SELECT 1 FROM retail_outbox_events AS predecessor
          WHERE predecessor.aggregate_type = retail_outbox_events.aggregate_type
            AND predecessor.aggregate_id = retail_outbox_events.aggregate_id
            AND predecessor.aggregate_sequence < retail_outbox_events.aggregate_sequence
            AND predecessor.state <> 'completed'
        )
      ) AS head_blocked
    FROM retail_outbox_events
"""


def _event_from_row(row: Any) -> OutboxEvent:
    values = dict(row)
    payload = values["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    values["payload"] = dict(payload)
    return OutboxEvent(**values)


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


async def emit_sales_generation_promoted(
    conn: asyncpg.Connection,
    *,
    aggregate_id: str,
    generation_hash: str,
    source_hash: str,
    cutoff: datetime,
    month: str,
    revision: int,
    occurred_at: datetime,
) -> UUID:
    """Emit through the migration-owned producer in the caller transaction."""
    _require_aware(cutoff, "cutoff")
    _require_aware(occurred_at, "occurred_at")
    event_id = await conn.fetchval(
        """SELECT public.emit_retail_sales_generation_promoted(
               $1, $2, $3, $4, $5, $6, $7
           )""",
        aggregate_id,
        generation_hash,
        source_hash,
        cutoff,
        month,
        revision,
        occurred_at,
    )
    if not isinstance(event_id, UUID):
        raise RuntimeError("sales outbox producer returned no event identity")
    return event_id


class TransactionalOutboxRepository:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def claim_batch(
        self,
        *,
        owner: str,
        now: datetime,
        limit: int,
        lease_seconds: int = 60,
    ) -> list[OutboxEvent]:
        if not _OWNER_RE.fullmatch(owner):
            raise ValueError("outbox claim owner is invalid")
        _require_aware(now, "now")
        if not 1 <= limit <= 100:
            raise ValueError("outbox claim batch must be between 1 and 100")
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("outbox lease must be between 1 and 3600 seconds")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(_RECLAIM_EXPIRED_SQL, now)
                rows = await conn.fetch(
                    _CLAIM_SQL, owner, now, limit, lease_seconds
                )
        return [_event_from_row(row) for row in rows]

    async def renew_lease(
        self,
        *,
        event_id: UUID,
        owner: str,
        epoch: int,
        now: datetime,
        lease_seconds: int = 60,
    ) -> bool:
        if not _OWNER_RE.fullmatch(owner):
            raise ValueError("outbox claim owner is invalid")
        _require_aware(now, "now")
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("outbox lease must be between 1 and 3600 seconds")
        async with self.pool.acquire() as conn:
            updated = await conn.fetchval(
                _RENEW_LEASE_SQL,
                event_id,
                owner,
                epoch,
                now,
                lease_seconds,
            )
        if updated is None:
            raise RuntimeError("stale outbox claim")
        return True

    async def record_receipt(
        self,
        *,
        event_id: UUID,
        owner: str,
        epoch: int,
        consumer: str,
        domain_generation_key: str,
        effect_sha256: str,
        received_at: datetime,
    ) -> bool:
        if not _CONSUMER_RE.fullmatch(consumer):
            raise ValueError("outbox consumer is invalid")
        if not _GENERATION_KEY_RE.fullmatch(domain_generation_key):
            raise ValueError("outbox domain generation key is invalid")
        if not _SHA256_RE.fullmatch(effect_sha256):
            raise ValueError("outbox effect digest is invalid")
        _require_aware(received_at, "received_at")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                active_claim = await conn.fetchval(
                    _RECEIPT_CLAIM_SQL,
                    event_id,
                    owner,
                    epoch,
                    received_at,
                )
                if active_claim is None:
                    raise RuntimeError("stale outbox claim")
                inserted = await conn.fetchval(
                    _RECORD_RECEIPT_SQL,
                    event_id,
                    consumer,
                    domain_generation_key,
                    effect_sha256,
                    received_at,
                )
                if inserted is not None:
                    return True
                event_receipt = await conn.fetchrow(
                    """SELECT domain_generation_key, effect_sha256
                       FROM retail_outbox_consumer_receipts
                       WHERE event_id = $1 AND consumer = $2""",
                    event_id,
                    consumer,
                )
                generation_receipt = await conn.fetchrow(
                    """SELECT event_id, effect_sha256
                       FROM retail_outbox_consumer_receipts
                       WHERE consumer = $1 AND domain_generation_key = $2""",
                    consumer,
                    domain_generation_key,
                )
        if event_receipt is not None:
            if (
                str(event_receipt["domain_generation_key"]) == domain_generation_key
                and str(event_receipt["effect_sha256"]) == effect_sha256
            ):
                return False
            raise RuntimeError("consumer receipt conflict")
        if generation_receipt is not None:
            if (
                generation_receipt["event_id"] == event_id
                and str(generation_receipt["effect_sha256"]) == effect_sha256
            ):
                return False
            raise RuntimeError("domain generation receipt conflict")
        raise RuntimeError("consumer receipt insert was not observable")

    async def mark_completed(
        self,
        *,
        event_id: UUID,
        owner: str,
        epoch: int,
        now: datetime,
    ) -> bool:
        _require_aware(now, "now")
        async with self.pool.acquire() as conn:
            updated = await conn.fetchval(
                _MARK_COMPLETED_SQL, event_id, owner, epoch, now
            )
        if updated is None:
            raise RuntimeError("stale outbox claim")
        return True

    async def mark_failed(
        self,
        *,
        event_id: UUID,
        owner: str,
        epoch: int,
        error_code: str,
        now: datetime,
    ) -> str:
        if not _ERROR_RE.fullmatch(error_code):
            raise ValueError("outbox error code is invalid")
        _require_aware(now, "now")
        async with self.pool.acquire() as conn:
            state = await conn.fetchval(
                _MARK_FAILED_SQL, event_id, owner, epoch, error_code, now
            )
        if state is None:
            raise RuntimeError("stale outbox claim")
        return str(state)

    async def replay_dead(
        self,
        *,
        event_id: UUID,
        reason: str,
        requested_by_sub_sha256: str,
        now: datetime,
    ) -> int:
        _require_aware(now, "now")
        if not _ERROR_RE.fullmatch(reason):
            raise ValueError("outbox replay reason is invalid")
        if not _SHA256_RE.fullmatch(requested_by_sub_sha256):
            raise ValueError("outbox replay actor digest is invalid")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                event = await conn.fetchrow(
                    """SELECT state, attempt_count, dead_at, replay_count
                       FROM retail_outbox_events WHERE id = $1 FOR UPDATE""",
                    event_id,
                )
                if event is None:
                    raise LookupError("outbox event was not found")
                if (
                    event["state"] != "dead"
                    or int(event["attempt_count"]) != 8
                    or event["dead_at"] is None
                ):
                    raise RuntimeError("only an exact dead outbox event can be replayed")
                replay_number = int(event["replay_count"]) + 1
                await conn.execute(
                    """INSERT INTO retail_outbox_replay_audit (
                           event_id, replay_number, previous_attempt_count,
                           previous_dead_at, reason, requested_by_sub_sha256,
                           requested_at
                       ) VALUES ($1, $2, 8, $3, $4, $5, $6)""",
                    event_id,
                    replay_number,
                    event["dead_at"],
                    reason,
                    requested_by_sub_sha256,
                    now,
                )
                updated = await conn.fetchval(
                    """UPDATE retail_outbox_events
                       SET state = 'pending', attempt_count = 0,
                           available_at = $3, last_error_code = NULL,
                           last_error_at = NULL, dead_at = NULL,
                           replay_count = $2, updated_at = $3
                       WHERE id = $1 AND state = 'dead'
                       RETURNING replay_count""",
                    event_id,
                    replay_number,
                    now,
                )
        if updated is None:
            raise RuntimeError("dead outbox event changed during replay")
        return int(updated)

    async def observe_state(self, *, now: datetime) -> dict[str, float | int]:
        _require_aware(now, "now")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(_OBSERVE_STATE_SQL, now)
        if row is None:
            return {"oldest_pending_seconds": 0.0, "head_blocked": 0}
        return {
            "oldest_pending_seconds": max(
                0.0, float(row["oldest_pending_seconds"] or 0)
            ),
            "head_blocked": int(row["head_blocked"] or 0),
        }
