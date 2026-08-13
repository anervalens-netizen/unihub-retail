"""Stateful orchestration engine for the locked outbox SLO workload."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import time
from typing import Any, Awaitable, Callable

import asyncpg


Consumer = Callable[[Any], Awaitable[dict[str, str]]]


class OutboxWorkload:
    """Run one deterministic workload while keeping mutable state explicit."""

    def __init__(
        self,
        args: Any,
        *,
        pool: asyncpg.Pool,
        valkey_info: dict[str, Any],
        api: Any,
        db_identity: dict[str, Any],
        valkey_identity: dict[str, Any],
        event_types: tuple[tuple[str, str, str, str], ...],
        event_specs: Callable[..., list[Any]],
        emit_fixture: Callable[..., Awaitable[str]],
        effects: Any,
        canonical_sha256: Callable[[Any], str],
        nearest_rank: Callable[[list[float], float], float],
        locked_events: int,
    ) -> None:
        self.args = args
        self.pool = pool
        self.valkey_info = valkey_info
        self.api = api
        self.db_identity = db_identity
        self.valkey_identity = valkey_identity
        self.event_types = event_types
        self.make_event_specs = event_specs
        self.emit_fixture = emit_fixture
        self.effects = effects
        self.canonical_sha256 = canonical_sha256
        self.nearest_rank = nearest_rank
        self.locked_events = locked_events
        self.handler_limit = asyncio.Semaphore(args.handlers)
        self.stop = asyncio.Event()
        self.feed_done = asyncio.Event()
        self.enqueue_monotonic: dict[str, float] = {}
        self.enqueue_offsets: list[float] = []
        self.measured_ordinals: dict[str, int] = {}
        self.latencies_by_event: dict[str, float] = {}
        self.failed_attempts = 0
        self.delivery_attempts = 0
        self.ratio_samples: list[dict[str, float]] = []
        self.pending_age_samples: list[dict[str, float]] = []
        self.state_lock = asyncio.Lock()
        self.first_measured = 0.0
        self.migration_checksum = ""
        self.repository: Any = None
        self.claim_tasks: list[asyncio.Task[None]] = []
        self.sampler: asyncio.Task[None] | None = None

    async def validate_database(self) -> None:
        async with self.pool.acquire() as connection:
            migration = await connection.fetchrow(
                "SELECT filename, checksum FROM schema_migrations ORDER BY filename DESC LIMIT 1"
            )
            if (
                not migration
                or migration["filename"]
                != "069_ai_cohort_and_transactional_outbox.sql"
            ):
                raise RuntimeError(
                    "outbox workload requires production schema through exact 069"
                )
            initial_counts = dict(
                await connection.fetchrow(
                    """SELECT
                     (SELECT count(*) FROM retail_outbox_events) AS events,
                     (SELECT count(*) FROM retail_outbox_consumer_receipts) AS receipts,
                     (SELECT count(*) FROM retail_outbox_replay_audit) AS replays"""
                )
            )
            if initial_counts != {"events": 0, "receipts": 0, "replays": 0}:
                raise RuntimeError(f"outbox database is not empty: {initial_counts}")
            self.migration_checksum = str(migration["checksum"])
        self.repository = self.api.repository_type(self.pool)

    async def measured_attempt(self, event: Any) -> tuple[str, int | None, bool]:
        event_id = str(event.id)
        ordinal = self.measured_ordinals.get(event_id)
        if ordinal is None:
            return event_id, None, False
        should_fail = ordinal % 200 == 0 and int(event.attempt_count) == 1
        async with self.state_lock:
            self.delivery_attempts += 1
            if should_fail:
                self.failed_attempts += 1
        return event_id, ordinal, should_fail

    async def finish_success(self, event_id: str, ordinal: int | None) -> None:
        if ordinal is None:
            return
        async with self.state_lock:
            if event_id in self.latencies_by_event:
                raise RuntimeError("production dispatcher delivered one event twice")
            self.latencies_by_event[event_id] = (
                time.monotonic() - self.enqueue_monotonic[event_id]
            )

    async def sales_consumer(self, event: Any) -> dict[str, str]:
        async with self.handler_limit:
            event_id, ordinal, should_fail = await self.measured_attempt(event)
            if should_fail:
                raise RuntimeError("slo_transient")
            receipt = await self.api.deliver_sales(
                event,
                publish_campaigns=self.effects.publish_campaigns,
                publish_contests=self.effects.publish_contests,
                sync_grile_v2=self.effects.sync_grile_v2,
            )
            await self.finish_success(event_id, ordinal)
            return receipt

    def receipt_consumer(self, consumer: str) -> Consumer:
        async def handle(event: Any) -> dict[str, str]:
            async with self.handler_limit:
                event_id, ordinal, should_fail = await self.measured_attempt(event)
                if should_fail:
                    raise RuntimeError("slo_transient")
                key = f"{consumer}:{event.generation_hash}:{event.revision}"
                await self.finish_success(event_id, ordinal)
                return {
                    "consumer": consumer,
                    "domain_generation_key": key,
                    "effect_sha256": hashlib.sha256(key.encode()).hexdigest(),
                }

        return handle

    def consumers(self) -> dict[str, Consumer]:
        result: dict[str, Consumer] = {
            self.event_types[0][0]: self.sales_consumer
        }
        result.update(
            {
                event_type: self.receipt_consumer(consumer)
                for event_type, _aggregate, _fixture, consumer in self.event_types[1:]
            }
        )
        return result

    async def claimer(self, index: int, consumers: dict[str, Consumer]) -> None:
        while not self.stop.is_set():
            processed = await self.api.dispatch_once(
                repository=self.repository,
                consumers=consumers,
                owner=f"slo-{index}",
                now=datetime.now(timezone.utc),
                batch_size=self.args.batch_size,
                lease_seconds=60,
            )
            if not processed:
                await asyncio.sleep(0.02)

    def start_claimers(self) -> None:
        consumers = self.consumers()
        self.claim_tasks = [
            asyncio.create_task(
                self.claimer(index, consumers), name=f"outbox-slo-claimer-{index}"
            )
            for index in range(self.args.claimers)
        ]

    def ensure_claimers_healthy(self) -> None:
        for task in self.claim_tasks:
            if not task.done():
                continue
            if task.cancelled():
                raise RuntimeError(f"outbox claimer stopped early: {task.get_name()}")
            error = task.exception()
            if error is not None:
                raise RuntimeError(
                    f"outbox claimer failed early: {task.get_name()}"
                ) from error
            if not self.stop.is_set():
                raise RuntimeError(
                    f"outbox claimer exited before workload completion: {task.get_name()}"
                )
        if self.sampler is not None and self.sampler.done() and not self.feed_done.is_set():
            if self.sampler.cancelled():
                raise RuntimeError("outbox sampler stopped during the measured feed")
            error = self.sampler.exception()
            if error is not None:
                raise RuntimeError(
                    "outbox sampler failed during the measured feed"
                ) from error
            raise RuntimeError("outbox sampler exited before the measured feed completed")

    async def feed(self, specs: list[Any], *, paced: bool) -> None:
        started = time.monotonic()
        if paced:
            self.first_measured = started
        async with self.pool.acquire() as connection:
            for index, spec in enumerate(specs):
                self.ensure_claimers_healthy()
                if paced:
                    delay = started + index / self.args.rate - time.monotonic()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    self.ensure_claimers_healthy()

                def register(event_id: str, item: Any = spec) -> None:
                    if paced:
                        registered_at = time.monotonic()
                        self.enqueue_monotonic[event_id] = registered_at
                        self.enqueue_offsets.append(registered_at - started)
                        self.measured_ordinals[event_id] = item.ordinal

                await self.emit_fixture(
                    connection,
                    spec,
                    self.api,
                    register=register if paced else None,
                )

    async def wait_for_warmup(self, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.ensure_claimers_healthy()
            async with self.pool.acquire() as connection:
                completed = await connection.fetchval(
                    "SELECT count(*) FROM retail_outbox_events WHERE state='completed'"
                )
            if completed == self.args.warmup:
                return
            await asyncio.sleep(0.1)
        raise RuntimeError("outbox warmup did not drain in 60 seconds")

    async def sample_row(self) -> Any:
        async with self.pool.acquire() as connection:
            return await connection.fetchrow(
                """SELECT
                  count(*) FILTER (WHERE state='completed' AND aggregate_id LIKE 'm%') AS completed,
                  count(*) FILTER (WHERE state='pending' AND aggregate_id LIKE 'm%') AS pending,
                  count(*) FILTER (WHERE state='processing' AND aggregate_id LIKE 'm%') AS processing,
                  count(*) FILTER (WHERE state='dead' AND aggregate_id LIKE 'm%') AS dead,
                  COALESCE(max(extract(epoch FROM clock_timestamp()-created_at))
                    FILTER (WHERE state='pending' AND aggregate_id LIKE 'm%'), 0) AS oldest_pending,
                  COALESCE(max(extract(epoch FROM clock_timestamp()-created_at)) FILTER (
                    WHERE state IN ('pending','processing','dead') AND aggregate_id LIKE 'm%'
                    AND EXISTS (
                      SELECT 1 FROM retail_outbox_events later
                      WHERE later.aggregate_type=retail_outbox_events.aggregate_type
                        AND later.aggregate_id=retail_outbox_events.aggregate_id
                        AND later.aggregate_sequence>retail_outbox_events.aggregate_sequence
                        AND later.state='pending'
                    )), 0) AS head_blocked_age
                FROM retail_outbox_events"""
            )

    async def sample_until_done(self) -> None:
        last_ratio_sample = -5.0
        drain_deadline: float | None = None
        while True:
            self.ensure_claimers_healthy()
            row = await self.sample_row()
            elapsed = time.monotonic() - self.first_measured
            self.pending_age_samples.append(
                {
                    "elapsed_seconds": elapsed,
                    "oldest_pending_seconds": float(row["oldest_pending"]),
                    "head_blocked_age_seconds": float(row["head_blocked_age"]),
                }
            )
            async with self.state_lock:
                attempts, failures = self.delivery_attempts, self.failed_attempts
            if attempts >= 200 and elapsed - last_ratio_sample >= 5:
                ratio = failures / attempts
                self.ratio_samples.append(
                    {
                        "elapsed_seconds": elapsed,
                        "attempts": attempts,
                        "failures": failures,
                        "ratio": ratio,
                    }
                )
                if ratio >= 0.01:
                    raise RuntimeError(f"failure ratio reached {ratio:.6f}")
                last_ratio_sample = elapsed
            if self.feed_done.is_set():
                if drain_deadline is None:
                    drain_deadline = time.monotonic() + 60.0
                if row["completed"] == self.args.events:
                    if row["pending"] or row["processing"] or row["dead"]:
                        raise RuntimeError("terminal outbox counts are inconsistent")
                    return
                if time.monotonic() > drain_deadline:
                    raise RuntimeError(
                        "measured outbox run exceeded 60-second drain window"
                    )
            await asyncio.sleep(1)

    async def drive(self) -> None:
        self.start_claimers()
        try:
            await self.feed(
                self.make_event_specs(self.args.warmup, measured=False), paced=False
            )
            await self.wait_for_warmup()
            self.sampler = asyncio.create_task(
                self.sample_until_done(), name="outbox-slo-sampler"
            )
            try:
                await self.feed(
                    self.make_event_specs(self.args.events, measured=True), paced=True
                )
                self.feed_done.set()
                await self.sampler
            except BaseException:
                self.feed_done.set()
                if not self.sampler.done():
                    self.sampler.cancel()
                await asyncio.gather(self.sampler, return_exceptions=True)
                raise
        finally:
            self.stop.set()
            # Cleanup errors cannot mask the primary fail-fast workload error.
            await asyncio.gather(*self.claim_tasks, return_exceptions=True)

    async def terminal_counts(self) -> tuple[dict[str, int], dict[str, int]]:
        async with self.pool.acquire() as connection:
            terminal = dict(
                await connection.fetchrow(
                    """SELECT
                      count(*) FILTER (WHERE state='completed' AND aggregate_id LIKE 'm%') AS completed,
                      count(*) FILTER (WHERE state='pending' AND aggregate_id LIKE 'm%') AS pending,
                      count(*) FILTER (WHERE state='processing' AND aggregate_id LIKE 'm%') AS processing,
                      count(*) FILTER (WHERE state='dead' AND aggregate_id LIKE 'm%') AS dead,
                      count(*) FILTER (WHERE aggregate_id LIKE 'm%') AS total
                    FROM retail_outbox_events"""
                )
            )
            receipts = {
                row["event_type"]: row["count"]
                for row in await connection.fetch(
                    """SELECT event_type, count(*) FROM retail_outbox_consumer_receipts r
                       JOIN retail_outbox_events e ON e.id=r.event_id
                       WHERE e.aggregate_id LIKE 'm%'
                       GROUP BY event_type ORDER BY event_type"""
                )
            }
        return terminal, receipts

    def passed(
        self,
        terminal: dict[str, int],
        receipt_counts: dict[str, int],
        latencies: list[float],
        p95: float,
        oldest: float,
        ratio: float,
    ) -> bool:
        return bool(
            terminal
            == {
                "completed": self.locked_events,
                "pending": 0,
                "processing": 0,
                "dead": 0,
                "total": self.locked_events,
            }
            and len(latencies) == self.locked_events
            and self.delivery_attempts == self.locked_events + 50
            and self.failed_attempts == 50
            and ratio < 0.01
            and self.ratio_samples
            and max(float(sample["ratio"]) for sample in self.ratio_samples) < 0.01
            and p95 < 30.0
            and oldest < 60.0
            and len(self.effects.grile_keys) == 2_000
            and self.effects.sales_transport_calls == 2_000
            and set(receipt_counts.values()) == {2_000}
        )

    def build_payload(
        self,
        terminal: dict[str, int],
        receipt_counts: dict[str, int],
    ) -> dict[str, Any]:
        latencies = list(self.latencies_by_event.values())
        p95 = self.nearest_rank(latencies, 0.95)
        oldest = max(
            sample["oldest_pending_seconds"] for sample in self.pending_age_samples
        )
        ratio = self.failed_attempts / self.delivery_attempts
        passed = self.passed(
            terminal, receipt_counts, latencies, p95, oldest, ratio
        )
        return {
            "schema_version": 2,
            "authority": "backend/scripts/run_outbox_slo_workload.py",
            "seed": self.args.seed,
            "database_identity": self.db_identity,
            "valkey_identity": self.valkey_identity,
            "valkey_version": str(self.valkey_info["redis_version"]),
            "migration_069_checksum": self.migration_checksum,
            "production_api": self.api.authorities,
            "production_dispatch": {
                "repository": "repositories.transactional_outbox.TransactionalOutboxRepository",
                "dispatcher": "services.outbox_worker.dispatch_outbox_once",
                "sales_delivery": "services.grile_outbox_delivery.deliver_sales_generation_event",
                "sales_producer": "repositories.transactional_outbox.emit_sales_generation_promoted",
                "dispatcher_valkey_dependency": False,
            },
            "fixture_adapters": {
                "protected_sql_fixture_emitters": [
                    item[2] for item in self.event_types[1:]
                ],
                "source": "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql",
                "effects": "receipt-only deterministic non-network fixture callbacks; sales uses production delivery chain",
            },
            "workload": {
                "warmup": self.args.warmup,
                "events": self.args.events,
                "rate_per_second": self.args.rate,
                "claimers": self.args.claimers,
                "batch_size": self.args.batch_size,
                "handlers": self.args.handlers,
                "event_types": [item[0] for item in self.event_types],
                "aggregates_per_type": 200,
                "sequences_per_aggregate": 10,
                "transient_failures": 50,
                "retry_seconds": 5,
                "lease_seconds": 60,
            },
            "terminal": terminal,
            "receipt_counts": receipt_counts,
            "effective_sales_mutations": len(self.effects.grile_keys),
            "sales_transport_calls": self.effects.sales_transport_calls,
            "duplicate_effects": (
                self.effects.sales_transport_calls - len(self.effects.grile_keys)
            ),
            "delivery_attempts": self.delivery_attempts,
            "failed_attempts": self.failed_attempts,
            "failure_ratio": ratio,
            "failure_ratio_samples": self.ratio_samples,
            "latency_seconds": latencies,
            "latency_input_sha256": self.canonical_sha256(latencies),
            "enqueue_offsets_seconds": self.enqueue_offsets,
            "enqueue_offsets_sha256": self.canonical_sha256(self.enqueue_offsets),
            "p95_delivery_seconds": p95,
            "pending_age_samples": self.pending_age_samples,
            "oldest_pending_seconds": oldest,
            "thresholds": {
                "p95_delivery_seconds_lt": 30,
                "oldest_pending_seconds_lt": 60,
                "failure_ratio_lt": 0.01,
                "dead_count": 0,
            },
            "protected_live_promotion_executed": False,
            "salary_export_executed": False,
            "result": "PASS" if passed else "FAIL",
        }

    async def run(self) -> dict[str, Any]:
        await self.validate_database()
        await self.drive()
        terminal, receipts = await self.terminal_counts()
        return self.build_payload(terminal, receipts)
