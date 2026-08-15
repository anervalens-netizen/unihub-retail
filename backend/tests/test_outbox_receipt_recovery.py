"""Regression coverage for receipt-backed outbox terminal recovery."""

from __future__ import annotations

from datetime import datetime, timedelta
import os
from typing import Any
from uuid import UUID

import asyncpg
import pytest

from db.connection import validate_test_database_url
from repositories import transactional_outbox as outbox_repository_module
from test_transactional_outbox import (
    RETRY_DELAYS_SECONDS,
    SingleConnectionPool,
    required_symbol,
    requires_isolated_db,
)


CONSUMER = "grile_v2"
EFFECT_SHA256 = "e" * 64


def test_terminal_sql_reconciles_durable_receipts_before_dead_lettering() -> None:
    reclaim = " ".join(outbox_repository_module._RECLAIM_EXPIRED_SQL.split())
    failed = " ".join(outbox_repository_module._MARK_FAILED_SQL.split())

    for statement in (reclaim, failed):
        assert "retail_outbox_consumer_receipts" in statement
        assert "receipt_at IS NOT NULL THEN 'completed'" in statement
        assert "WHEN event.attempt_count = 8 THEN 'dead'" in statement


async def _emit_pair_and_reach_attempt_eight(
    connection: asyncpg.Connection,
    *,
    prefix: str,
) -> tuple[Any, UUID, UUID, Any, datetime]:
    repository_type = required_symbol(
        "repositories.transactional_outbox", "TransactionalOutboxRepository"
    )
    emit = required_symbol(
        "repositories.transactional_outbox", "emit_sales_generation_promoted"
    )
    occurred_at = await connection.fetchval("SELECT now()")
    assert isinstance(occurred_at, datetime)

    await connection.execute("SET LOCAL ROLE unihub_sales_import")
    first_id = await emit(
        connection,
        aggregate_id=prefix,
        generation_hash="a" * 64,
        source_hash="b" * 64,
        cutoff=occurred_at - timedelta(hours=1),
        month="2026-08",
        revision=1,
        occurred_at=occurred_at,
    )
    second_id = await emit(
        connection,
        aggregate_id=prefix,
        generation_hash="c" * 64,
        source_hash="d" * 64,
        cutoff=occurred_at - timedelta(hours=1),
        month="2026-08",
        revision=2,
        occurred_at=occurred_at + timedelta(seconds=1),
    )
    await connection.execute("RESET ROLE")
    await connection.execute("SET LOCAL ROLE unihub_operations")

    repository = repository_type(SingleConnectionPool(connection))
    attempt_at = occurred_at + timedelta(seconds=2)
    for attempt in range(1, 8):
        claimed = await repository.claim_batch(
            owner="operations-receipt-test",
            now=attempt_at,
            limit=10,
            lease_seconds=60,
        )
        assert len(claimed) == 1
        event = claimed[0]
        assert event.id == first_id
        assert event.attempt_count == attempt
        failed_at = attempt_at + timedelta(seconds=1)
        assert await repository.mark_failed(
            event_id=event.id,
            owner="operations-receipt-test",
            epoch=event.claim_epoch,
            error_code="handler_failed",
            now=failed_at,
        ) == "pending"
        attempt_at = failed_at + timedelta(
            seconds=RETRY_DELAYS_SECONDS[attempt - 1]
        )

    final_claim = await repository.claim_batch(
        owner="operations-receipt-test",
        now=attempt_at,
        limit=10,
        lease_seconds=60,
    )
    assert len(final_claim) == 1
    event = final_claim[0]
    assert event.id == first_id
    assert event.attempt_count == 8
    assert event.lease_until is not None
    return repository, first_id, second_id, event, attempt_at


async def _record_receipt(
    repository: Any,
    event: Any,
    *,
    received_at: datetime,
) -> None:
    assert await repository.record_receipt(
        event_id=event.id,
        owner="operations-receipt-test",
        epoch=event.claim_epoch,
        consumer=CONSUMER,
        domain_generation_key=(
            f"{CONSUMER}:{event.generation_hash}:{event.revision}"
        ),
        effect_sha256=EFFECT_SHA256,
        received_at=received_at,
    )


@pytest.mark.asyncio
@requires_isolated_db
async def test_attempt_eight_receipt_survives_crash_and_unblocks_successor() -> None:
    database_url = os.environ["DATABASE_URL"]
    validate_test_database_url(database_url)
    connection = await asyncpg.connect(database_url)
    transaction = connection.transaction()
    await transaction.start()
    try:
        repository, first_id, second_id, event, final_claim_at = (
            await _emit_pair_and_reach_attempt_eight(
                connection,
                prefix="contract-receipt-crash",
            )
        )
        received_at = final_claim_at + timedelta(seconds=1)
        await _record_receipt(repository, event, received_at=received_at)

        recovery_at = event.lease_until + timedelta(seconds=1)
        recovered = await repository.claim_batch(
            owner="operations-receipt-recovery",
            now=recovery_at,
            limit=10,
            lease_seconds=60,
        )

        assert [item.id for item in recovered] == [second_id]
        first = await connection.fetchrow(
            """SELECT state, attempt_count, completed_at, dead_at
               FROM retail_outbox_events WHERE id = $1""",
            first_id,
        )
        assert first is not None
        assert first["state"] == "completed"
        assert int(first["attempt_count"]) == 8
        assert first["completed_at"] == received_at
        assert first["dead_at"] is None
    finally:
        await transaction.rollback()
        await connection.close()


@pytest.mark.asyncio
@requires_isolated_db
async def test_attempt_eight_failure_after_receipt_completes_instead_of_dead() -> None:
    database_url = os.environ["DATABASE_URL"]
    validate_test_database_url(database_url)
    connection = await asyncpg.connect(database_url)
    transaction = connection.transaction()
    await transaction.start()
    try:
        repository, first_id, second_id, event, final_claim_at = (
            await _emit_pair_and_reach_attempt_eight(
                connection,
                prefix="contract-receipt-failure",
            )
        )
        received_at = final_claim_at + timedelta(seconds=1)
        await _record_receipt(repository, event, received_at=received_at)

        state = await repository.mark_failed(
            event_id=event.id,
            owner="operations-receipt-test",
            epoch=event.claim_epoch,
            error_code="handler_failed",
            now=received_at + timedelta(seconds=1),
        )
        assert state == "completed"

        successor = await repository.claim_batch(
            owner="operations-after-receipt",
            now=received_at + timedelta(seconds=2),
            limit=10,
            lease_seconds=60,
        )
        assert [item.id for item in successor] == [second_id]
        first = await connection.fetchrow(
            """SELECT state, attempt_count, completed_at, dead_at
               FROM retail_outbox_events WHERE id = $1""",
            first_id,
        )
        assert first is not None
        assert first["state"] == "completed"
        assert int(first["attempt_count"]) == 8
        assert first["completed_at"] == received_at
        assert first["dead_at"] is None
    finally:
        await transaction.rollback()
        await connection.close()
