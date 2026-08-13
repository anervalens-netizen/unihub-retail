"""Immutable Release-B contract for production-side outbox creation and claims."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256
import importlib
import inspect
import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import asyncpg
import pytest

from db.connection import validate_test_database_url


LOCKED_MIGRATION_SHA256 = "e2f3f1ff09c14cbba577ac40ba476250a7b746ebbe0bdf373c6ebf4e552fc8a0"
SALES_EVENT_TYPE = "retail.sales_generation_promoted.v1"
ALLOWED_PAYLOAD_KEYS = {
    "event_schema",
    "aggregate_type",
    "aggregate_id",
    "generation_hash",
    "source_hash",
    "cutoff",
    "month",
    "revision",
    "occurred_at",
}
FORBIDDEN_PAYLOAD_TOKENS = {
    "cnp",
    "person",
    "name",
    "salary",
    "amount",
    "credential",
    "requested_by_sub",
    "raw_row",
}
RETRY_DELAYS_SECONDS = (5, 30, 120, 300, 900, 1800, 3600, 3600)
CONTRACT_NAMESPACE = UUID("7c79a465-e5be-4ebd-a440-a81143276cbe")
requires_isolated_db = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires the explicitly isolated PostgreSQL contract database",
)


def required_symbol(module_name: str, symbol_name: str) -> Any:
    """Load a frozen Release-B surface while keeping collection useful."""
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"Release-B implementation is missing required module {module_name}: {exc}",
            pytrace=False,
        )
    if not hasattr(module, symbol_name):
        pytest.fail(
            f"Release-B module {module_name} is missing public symbol {symbol_name}",
            pytrace=False,
        )
    return getattr(module, symbol_name)


@dataclass(slots=True)
class ContractEvent:
    id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: str
    generation_hash: str
    revision: int
    aggregate_sequence: int
    event_key: str
    payload: dict[str, Any]
    created_at: datetime
    available_at: datetime
    state: str = "pending"
    attempt_count: int = 0
    claim_owner: str | None = None
    claim_epoch: int = 0
    lease_until: datetime | None = None
    completed_at: datetime | None = None
    dead_at: datetime | None = None
    last_error_code: str | None = None
    replay_count: int = 0


@dataclass(frozen=True, slots=True)
class ReplayAudit:
    event_id: UUID
    replay_number: int
    previous_attempt_count: int
    previous_dead_at: datetime
    reason: str
    requested_by_sub_sha256: str
    requested_at: datetime


@dataclass(slots=True)
class MemoryOutboxRepository:
    """Side-effect-free fault-injection double; production stays PostgreSQL."""

    events: dict[UUID, ContractEvent] = field(default_factory=dict)
    receipts: dict[tuple[UUID, str], tuple[str, str]] = field(default_factory=dict)
    generation_receipts: dict[tuple[str, str], tuple[UUID, str]] = field(
        default_factory=dict
    )
    replay_audit: list[ReplayAudit] = field(default_factory=list)
    fail_next_receipt_write: bool = False

    def seed(
        self,
        *,
        now: datetime,
        name: str = "sales-2026-08",
        sequence: int = 1,
        revision: int = 1,
        event_type: str = SALES_EVENT_TYPE,
        state: str = "pending",
        attempt_count: int = 0,
    ) -> ContractEvent:
        generation_hash = "a" * 64
        event_key = f"{event_type}:{name}:{generation_hash}:{revision}"
        event = ContractEvent(
            id=uuid5(CONTRACT_NAMESPACE, f"{event_key}:{sequence}"),
            event_type=event_type,
            aggregate_type="sales_generation",
            aggregate_id=name,
            generation_hash=generation_hash,
            revision=revision,
            aggregate_sequence=sequence,
            event_key=event_key,
            payload={
                "event_schema": event_type,
                "aggregate_type": "sales_generation",
                "aggregate_id": name,
                "generation_hash": generation_hash,
                "source_hash": "b" * 64,
                "cutoff": "2026-08-12T00:00:00Z",
                "month": "2026-08",
                "revision": revision,
                "occurred_at": "2026-08-13T08:00:00Z",
            },
            created_at=now,
            available_at=now,
            state=state,
            attempt_count=attempt_count,
            dead_at=now if state == "dead" else None,
        )
        self.events[event.id] = event
        return event

    async def claim_batch(
        self,
        *,
        owner: str,
        now: datetime,
        limit: int,
        lease_seconds: int = 60,
    ) -> list[ContractEvent]:
        for event in self.events.values():
            if (
                event.state == "processing"
                and event.lease_until is not None
                and event.lease_until <= now
            ):
                event.state = "pending"
                event.claim_owner = None
                event.lease_until = None
                event.available_at = now
                event.last_error_code = "lease_expired"

        claimed: list[ContractEvent] = []
        candidates = sorted(
            self.events.values(),
            key=lambda item: (item.available_at, item.created_at, str(item.id)),
        )
        for event in candidates:
            if len(claimed) >= limit:
                break
            if event.state != "pending" or event.available_at > now:
                continue
            blocked = any(
                other.aggregate_type == event.aggregate_type
                and other.aggregate_id == event.aggregate_id
                and other.aggregate_sequence < event.aggregate_sequence
                and other.state != "completed"
                for other in self.events.values()
            )
            if blocked:
                continue
            event.state = "processing"
            event.attempt_count += 1
            event.claim_owner = owner
            event.claim_epoch += 1
            event.lease_until = now + timedelta(seconds=lease_seconds)
            claimed.append(event)
        return claimed

    def _claimed(self, event_id: UUID, owner: str, epoch: int) -> ContractEvent:
        event = self.events[event_id]
        if (
            event.state != "processing"
            or event.claim_owner != owner
            or event.claim_epoch != epoch
        ):
            raise RuntimeError("stale outbox claim")
        return event

    async def record_receipt(
        self,
        *,
        event_id: UUID,
        consumer: str,
        domain_generation_key: str,
        effect_sha256: str,
        received_at: datetime,
    ) -> bool:
        del received_at
        if self.fail_next_receipt_write:
            self.fail_next_receipt_write = False
            raise RuntimeError("receipt write interrupted")
        event_key = (event_id, consumer)
        generation_key = (consumer, domain_generation_key)
        expected = (domain_generation_key, effect_sha256)
        existing = self.receipts.get(event_key)
        if existing is not None:
            if existing != expected:
                raise RuntimeError("consumer receipt conflict")
            return False
        generation_existing = self.generation_receipts.get(generation_key)
        if generation_existing is not None:
            if generation_existing != (event_id, effect_sha256):
                raise RuntimeError("domain generation receipt conflict")
            return False
        self.receipts[event_key] = expected
        self.generation_receipts[generation_key] = (event_id, effect_sha256)
        return True

    async def mark_completed(
        self,
        *,
        event_id: UUID,
        owner: str,
        epoch: int,
        now: datetime,
    ) -> bool:
        event = self._claimed(event_id, owner, epoch)
        event.state = "completed"
        event.claim_owner = None
        event.lease_until = None
        event.completed_at = now
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
        event = self._claimed(event_id, owner, epoch)
        event.claim_owner = None
        event.lease_until = None
        event.last_error_code = error_code
        if event.attempt_count == len(RETRY_DELAYS_SECONDS):
            event.state = "dead"
            event.dead_at = now
            return "dead"
        event.state = "pending"
        event.available_at = now + timedelta(
            seconds=RETRY_DELAYS_SECONDS[event.attempt_count - 1]
        )
        return "pending"

    async def replay_dead(
        self,
        *,
        event_id: UUID,
        reason: str,
        requested_by_sub_sha256: str,
        now: datetime,
    ) -> int:
        event = self.events.get(event_id)
        if (
            event is None
            or event.state != "dead"
            or event.attempt_count != 8
            or event.dead_at is None
        ):
            raise RuntimeError("only an exact dead outbox event can be replayed")
        replay_number = event.replay_count + 1
        self.replay_audit.append(
            ReplayAudit(
                event_id=event.id,
                replay_number=replay_number,
                previous_attempt_count=event.attempt_count,
                previous_dead_at=event.dead_at,
                reason=reason,
                requested_by_sub_sha256=requested_by_sub_sha256,
                requested_at=now,
            )
        )
        event.state = "pending"
        event.attempt_count = 0
        event.available_at = now
        event.last_error_code = None
        event.dead_at = None
        event.replay_count = replay_number
        return replay_number


class SingleConnectionPool:
    """Pool-shaped adapter preserving the caller's isolated transaction."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def acquire(self) -> "SingleConnectionPool":
        return self

    async def __aenter__(self) -> Any:
        return self.connection

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> bool:
        return False


def _call_name(call: ast.Call) -> str:
    target = call.func
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def test_release_b_outbox_public_surface_and_locked_schema() -> None:
    repository_type = required_symbol(
        "repositories.transactional_outbox", "TransactionalOutboxRepository"
    )
    emitter = required_symbol(
        "repositories.transactional_outbox", "emit_sales_generation_promoted"
    )

    assert set(inspect.signature(emitter).parameters) == {
        "conn",
        "aggregate_id",
        "generation_hash",
        "source_hash",
        "cutoff",
        "month",
        "revision",
        "occurred_at",
    }
    for method in (
        "claim_batch",
        "record_receipt",
        "mark_completed",
        "mark_failed",
        "replay_dead",
    ):
        assert callable(getattr(repository_type, method, None)), method

    migration = Path("backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql")
    assert sha256(migration.read_bytes()).hexdigest() == LOCKED_MIGRATION_SHA256
    manifest = json.loads(Path("backend/db/migrations/manifest.json").read_text())
    assert manifest["migrations"]["069_ai_cohort_and_transactional_outbox.sql"] == (
        LOCKED_MIGRATION_SHA256
    )


def test_claim_implementation_uses_skip_locked_and_finite_lease() -> None:
    repository_type = required_symbol(
        "repositories.transactional_outbox", "TransactionalOutboxRepository"
    )
    module_source = inspect.getsource(inspect.getmodule(repository_type))
    normalized = " ".join(module_source.upper().split())

    assert "FOR UPDATE SKIP LOCKED" in normalized
    assert "60" in inspect.getsource(repository_type.claim_batch)
    assert "PG_ADVISORY" in normalized


@pytest.mark.asyncio
@requires_isolated_db
async def test_two_claimers_skip_a_locked_head_without_double_claiming() -> None:
    database_url = os.environ["DATABASE_URL"]
    validate_test_database_url(database_url)
    repository_type = required_symbol(
        "repositories.transactional_outbox", "TransactionalOutboxRepository"
    )
    emit = required_symbol(
        "repositories.transactional_outbox", "emit_sales_generation_promoted"
    )
    prefix = "contract-skip-locked"

    setup = await asyncpg.connect(database_url)
    try:
        await setup.execute(
            "ALTER TABLE retail_outbox_events DISABLE TRIGGER "
            "trg_retail_outbox_events_guard"
        )
        await setup.execute(
            "DELETE FROM retail_outbox_events WHERE aggregate_id LIKE $1",
            f"{prefix}%",
        )
        await setup.execute(
            "ALTER TABLE retail_outbox_events ENABLE TRIGGER "
            "trg_retail_outbox_events_guard"
        )
        occurred_at = await setup.fetchval("SELECT now()")
        async with setup.transaction():
            await setup.execute("SET LOCAL ROLE unihub_sales_import")
            for suffix in ("a", "b"):
                await emit(
                    setup,
                    aggregate_id=f"{prefix}-{suffix}",
                    generation_hash="c" * 64,
                    source_hash="d" * 64,
                    cutoff=occurred_at - timedelta(hours=1),
                    month="2026-08",
                    revision=1,
                    occurred_at=occurred_at,
                )

        first_connection = await asyncpg.connect(database_url)
        second_connection = await asyncpg.connect(database_url)
        first_transaction = first_connection.transaction()
        await first_transaction.start()
        try:
            await first_connection.execute("SET LOCAL ROLE unihub_operations")
            first_repository = repository_type(
                SingleConnectionPool(first_connection)
            )
            first = await first_repository.claim_batch(
                owner="operations-lock-holder",
                now=occurred_at + timedelta(seconds=1),
                limit=1,
                lease_seconds=60,
            )
            assert len(first) == 1

            await second_connection.execute("SET ROLE unihub_operations")
            second_repository = repository_type(
                SingleConnectionPool(second_connection)
            )
            second = await second_repository.claim_batch(
                owner="operations-skip-locked",
                now=occurred_at + timedelta(seconds=1),
                limit=10,
                lease_seconds=60,
            )
            assert len(second) == 1
            assert first[0].id != second[0].id
            assert {
                first[0].aggregate_id,
                second[0].aggregate_id,
            } == {f"{prefix}-a", f"{prefix}-b"}
        finally:
            await first_transaction.rollback()
            await first_connection.close()
            await second_connection.close()
    finally:
        await setup.execute("RESET ROLE")
        await setup.execute(
            "ALTER TABLE retail_outbox_events DISABLE TRIGGER "
            "trg_retail_outbox_events_guard"
        )
        await setup.execute(
            "DELETE FROM retail_outbox_events WHERE aggregate_id LIKE $1",
            f"{prefix}%",
        )
        await setup.execute(
            "ALTER TABLE retail_outbox_events ENABLE TRIGGER "
            "trg_retail_outbox_events_guard"
        )
        await setup.close()


def test_sales_promotion_emits_inside_its_existing_transaction() -> None:
    source = Path("backend/services/sales_generation_flow.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "promote_sales_generation"
    )
    emitter_calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and _call_name(node) == "emit_sales_generation_promoted"
    ]

    assert len(emitter_calls) == 1, (
        "sales promotion must emit exactly one canonical event before commit"
    )
    call = emitter_calls[0]
    transaction_blocks = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.AsyncWith)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Attribute)
            and item.context_expr.func.attr == "transaction"
            for item in node.items
        )
    ]
    assert any(
        block.lineno <= call.lineno <= (block.end_lineno or block.lineno)
        for block in transaction_blocks
    ), "outbox emission must share the sales promotion PostgreSQL transaction"


@pytest.mark.asyncio
@requires_isolated_db
async def test_emit_rollback_key_order_privacy_roles_and_head_of_line_claim() -> None:
    database_url = os.environ["DATABASE_URL"]
    validate_test_database_url(database_url)
    repository_type = required_symbol(
        "repositories.transactional_outbox", "TransactionalOutboxRepository"
    )
    emit = required_symbol(
        "repositories.transactional_outbox", "emit_sales_generation_promoted"
    )

    connection = await asyncpg.connect(database_url)
    transaction = connection.transaction()
    await transaction.start()
    try:
        occurred_at = await connection.fetchval("SELECT now()")
        cutoff = occurred_at - timedelta(hours=1)
        generation_hash = "a" * 64
        source_hash = "b" * 64

        await connection.execute("SET LOCAL ROLE unihub_sales_import")
        rolled_back = connection.transaction()
        await rolled_back.start()
        await emit(
            connection,
            aggregate_id="contract-rollback",
            generation_hash=generation_hash,
            source_hash=source_hash,
            cutoff=cutoff,
            month="2026-08",
            revision=1,
            occurred_at=occurred_at,
        )
        await rolled_back.rollback()
        assert await connection.fetchval(
            "SELECT count(*) FROM retail_outbox_events WHERE aggregate_id = $1",
            "contract-rollback",
        ) == 0

        first_id = await emit(
            connection,
            aggregate_id="contract-sales-a",
            generation_hash=generation_hash,
            source_hash=source_hash,
            cutoff=cutoff,
            month="2026-08",
            revision=1,
            occurred_at=occurred_at,
        )
        assert await emit(
            connection,
            aggregate_id="contract-sales-a",
            generation_hash=generation_hash,
            source_hash=source_hash,
            cutoff=cutoff,
            month="2026-08",
            revision=1,
            occurred_at=occurred_at,
        ) == first_id
        second_id = await emit(
            connection,
            aggregate_id="contract-sales-a",
            generation_hash=generation_hash,
            source_hash=source_hash,
            cutoff=cutoff,
            month="2026-08",
            revision=2,
            occurred_at=occurred_at,
        )
        other_id = await emit(
            connection,
            aggregate_id="contract-sales-b",
            generation_hash=generation_hash,
            source_hash=source_hash,
            cutoff=cutoff,
            month="2026-08",
            revision=1,
            occurred_at=occurred_at,
        )
        assert len({first_id, second_id, other_id}) == 3

        rows = await connection.fetch(
            """
            SELECT id, aggregate_id, aggregate_sequence, event_key, payload
            FROM retail_outbox_events
            WHERE aggregate_id IN ('contract-sales-a', 'contract-sales-b')
            ORDER BY aggregate_id, aggregate_sequence
            """
        )
        assert [row["aggregate_sequence"] for row in rows] == [1, 2, 1]
        assert rows[0]["event_key"] == (
            f"{SALES_EVENT_TYPE}:contract-sales-a:{generation_hash}:1"
        )
        payload = rows[0]["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        assert set(payload) == ALLOWED_PAYLOAD_KEYS
        assert not (set(payload) & FORBIDDEN_PAYLOAD_TOKENS)
        serialized = json.dumps(payload, sort_keys=True).casefold()
        assert all(token not in serialized for token in FORBIDDEN_PAYLOAD_TOKENS)

        await connection.execute("RESET ROLE")
        await connection.execute("SET LOCAL ROLE unihub_web_read")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with connection.transaction():
                await emit(
                    connection,
                    aggregate_id="contract-web-denied",
                    generation_hash=generation_hash,
                    source_hash=source_hash,
                    cutoff=cutoff,
                    month="2026-08",
                    revision=1,
                    occurred_at=occurred_at,
                )

        repository = repository_type(SingleConnectionPool(connection))
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with connection.transaction():
                await repository.claim_batch(
                    owner="web-must-not-claim",
                    now=occurred_at + timedelta(seconds=1),
                    limit=10,
                    lease_seconds=60,
                )

        await connection.execute("RESET ROLE")
        await connection.execute("SET LOCAL ROLE unihub_operations")
        claim_at = occurred_at + timedelta(seconds=1)
        first_claim = await repository.claim_batch(
            owner="operations-a",
            now=claim_at,
            limit=10,
            lease_seconds=60,
        )
        claimed_ids = {str(event.id) for event in first_claim}
        assert claimed_ids == {str(first_id), str(other_id)}
        assert all(event.aggregate_sequence == 1 for event in first_claim)
        for event in first_claim:
            assert event.claim_owner == "operations-a"
            assert event.attempt_count == 1
            assert event.claim_epoch == 1
            assert event.lease_until == claim_at + timedelta(seconds=60)
            await repository.mark_completed(
                event_id=event.id,
                owner="operations-a",
                epoch=event.claim_epoch,
                now=claim_at + timedelta(seconds=1),
            )

        second_claim = await repository.claim_batch(
            owner="operations-b",
            now=claim_at + timedelta(seconds=2),
            limit=10,
            lease_seconds=60,
        )
        assert [str(event.id) for event in second_claim] == [str(second_id)]
        assert second_claim[0].aggregate_sequence == 2
    finally:
        await transaction.rollback()
        await connection.close()
