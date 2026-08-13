#!/usr/bin/env python3
"""Drive the frozen production outbox APIs through the locked 10k SLO load.

Only fixture creation and read-only measurements use SQL directly. Claims,
leases, retries, receipts, terminal transitions and the sales delivery chain
are owned by the Release-B runtime modules imported below.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import inspect
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse


# The authority is launched with ``python -I``. Add only the intended backend
# package root after isolated startup so PYTHONPATH/sitecustomize cannot replace
# the frozen workload before its own checks run.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import asyncpg
from redis.asyncio import Redis


SEED = 20260812
WARMUP = 500
EVENTS = 10_000
RATE = 20
CLAIMERS = 4
BATCH_SIZE = 50
HANDLERS = 8
REPOSITORY_MODULE = "repositories.transactional_outbox"
WORKER_MODULE = "services.outbox_worker"
SALES_DELIVERY_MODULE = "services.grile_outbox_delivery"
EVENT_TYPES = (
    (
        "retail.sales_generation_promoted.v1",
        "sales_generation",
        "emit_retail_sales_generation_promoted",
        "grile_v2",
    ),
    (
        "retail.pnl_generation_promoted.v1",
        "pnl_generation",
        "emit_retail_pnl_generation_promoted",
        "pnl_receipt",
    ),
    (
        "retail.salary_import_completed.v1",
        "salary_import",
        "emit_retail_salary_import_completed",
        "salary_receipt",
    ),
    (
        "retail.planning_forecast_promoted.v1",
        "planning_forecast",
        "emit_retail_planning_forecast_promoted",
        "planning_receipt",
    ),
    (
        "retail.grile_manifest_approved.v1",
        "grile_manifest",
        "emit_retail_grile_manifest_approved",
        "grile_manifest_receipt",
    ),
)
EXPECTED_DISPATCH_PARAMETERS = {
    "repository",
    "consumers",
    "owner",
    "now",
    "batch_size",
    "lease_seconds",
}
EXPECTED_DELIVERY_PARAMETERS = {
    "event",
    "publish_campaigns",
    "publish_contests",
    "sync_grile_v2",
}
EXPECTED_EMITTER_PARAMETERS = {
    "conn",
    "aggregate_id",
    "generation_hash",
    "source_hash",
    "cutoff",
    "month",
    "revision",
    "occurred_at",
}


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_isolated_url(value: str, *, database: bool) -> dict[str, Any]:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("isolated service must bind loopback")
    forbidden = 5432 if database else 6379
    if parsed.port in {None, forbidden}:
        raise ValueError("isolated service must use an ephemeral non-default port")
    if database:
        name = parsed.path.lstrip("/")
        if "test" not in name.lower() or name.lower() == "unihub":
            raise ValueError("database must be explicitly test-named")
        if os.getenv("UNIHUB_TEST_DATABASE") != "1":
            raise ValueError("UNIHUB_TEST_DATABASE=1 is required")
        return {"host": host, "port": parsed.port, "database": name}
    return {"host": host, "port": parsed.port, "database": parsed.path.lstrip("/") or "0"}


def nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("empty latency series")
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


@dataclass(frozen=True)
class EventSpec:
    ordinal: int
    event_type: str
    aggregate_type: str
    fixture_sql_function: str
    consumer: str
    aggregate_id: str
    revision: int
    generation_hash: str
    source_hash: str


@dataclass(frozen=True)
class ProductionApi:
    repository_type: type[Any]
    sales_emitter: Callable[..., Awaitable[Any]]
    dispatch_once: Callable[..., Awaitable[Any]]
    deliver_sales: Callable[..., Awaitable[dict[str, str]]]
    authorities: dict[str, dict[str, Any]]


def event_specs(count: int, *, measured: bool) -> list[EventSpec]:
    per_type = count // len(EVENT_TYPES)
    if count % len(EVENT_TYPES) or per_type % 10:
        raise ValueError("event count must divide into five types and ten sequences")
    aggregate_count = per_type // 10
    specs: list[EventSpec] = []
    ordinal = 0
    prefix = "m" if measured else "w"
    for type_index, (
        event_type,
        aggregate_type,
        fixture_sql_function,
        consumer,
    ) in enumerate(EVENT_TYPES):
        for aggregate in range(aggregate_count):
            aggregate_id = f"{prefix}{type_index}-{aggregate:03d}"
            for revision in range(1, 11):
                ordinal += 1
                material = f"{SEED}:{prefix}:{type_index}:{aggregate}:{revision}"
                specs.append(
                    EventSpec(
                        ordinal=ordinal,
                        event_type=event_type,
                        aggregate_type=aggregate_type,
                        fixture_sql_function=fixture_sql_function,
                        consumer=consumer,
                        aggregate_id=aggregate_id,
                        revision=revision,
                        generation_hash=hashlib.sha256(material.encode()).hexdigest(),
                        source_hash=hashlib.sha256(
                            (material + ":source").encode()
                        ).hexdigest(),
                    )
                )
    return specs


def _required_symbol(module_name: str, symbol_name: str) -> tuple[Any, Any]:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"required production module is missing: {module_name}"
        ) from exc
    symbol = getattr(module, symbol_name, None)
    if symbol is None or not callable(symbol):
        raise RuntimeError(
            f"required production symbol is missing: {module_name}.{symbol_name}"
        )
    return module, symbol


def _source_authority(root: Path, module: Any, symbols: list[str]) -> dict[str, Any]:
    source = Path(inspect.getsourcefile(module) or "").resolve()
    backend = (root / "backend").resolve()
    if source == backend or backend not in source.parents or not source.is_file():
        raise RuntimeError(f"production module resolved outside repository: {source}")
    return {
        "path": str(source.relative_to(root.resolve())),
        "sha256": file_sha256(source),
        "symbols": symbols,
    }


def load_production_api(root: Path) -> ProductionApi:
    repository_module, repository_type = _required_symbol(
        REPOSITORY_MODULE, "TransactionalOutboxRepository"
    )
    _, sales_emitter = _required_symbol(
        REPOSITORY_MODULE, "emit_sales_generation_promoted"
    )
    worker_module, dispatch_once = _required_symbol(
        WORKER_MODULE, "dispatch_outbox_once"
    )
    delivery_module, deliver_sales = _required_symbol(
        SALES_DELIVERY_MODULE, "deliver_sales_generation_event"
    )
    if set(inspect.signature(sales_emitter).parameters) != EXPECTED_EMITTER_PARAMETERS:
        raise RuntimeError("production sales emitter signature drifted")
    if set(inspect.signature(dispatch_once).parameters) != EXPECTED_DISPATCH_PARAMETERS:
        raise RuntimeError("production dispatcher signature drifted")
    if set(inspect.signature(deliver_sales).parameters) != EXPECTED_DELIVERY_PARAMETERS:
        raise RuntimeError("production sales delivery signature drifted")
    for method in (
        "claim_batch",
        "record_receipt",
        "mark_completed",
        "mark_failed",
        "replay_dead",
    ):
        if not callable(getattr(repository_type, method, None)):
            raise RuntimeError(f"production repository method is missing: {method}")
    authorities = {
        REPOSITORY_MODULE: _source_authority(
            root,
            repository_module,
            ["TransactionalOutboxRepository", "emit_sales_generation_promoted"],
        ),
        WORKER_MODULE: _source_authority(
            root, worker_module, ["dispatch_outbox_once"]
        ),
        SALES_DELIVERY_MODULE: _source_authority(
            root, delivery_module, ["deliver_sales_generation_event"]
        ),
    }
    return ProductionApi(
        repository_type=repository_type,
        sales_emitter=sales_emitter,
        dispatch_once=dispatch_once,
        deliver_sales=deliver_sales,
        authorities=authorities,
    )


async def _emit_fixture(
    connection: asyncpg.Connection,
    spec: EventSpec,
    api: ProductionApi,
    *,
    register: Callable[[str], None] | None,
) -> str:
    occurred_at = datetime.now(timezone.utc)
    cutoff = occurred_at - timedelta(hours=1)
    async with connection.transaction():
        if spec.event_type == EVENT_TYPES[0][0]:
            await connection.execute("SET LOCAL ROLE unihub_sales_import")
            event_id = await api.sales_emitter(
                connection,
                aggregate_id=spec.aggregate_id,
                generation_hash=spec.generation_hash,
                source_hash=spec.source_hash,
                cutoff=cutoff,
                month="2026-08",
                revision=spec.revision,
                occurred_at=occurred_at,
            )
        else:
            # Release B intentionally freezes no Python producer for these four
            # paths. Their exact event-specific SQL wrappers from migration 069
            # are used only to seed this disposable test database.
            event_id = await connection.fetchval(
                f"SELECT public.{spec.fixture_sql_function}($1,$2,$3,$4,$5,$6,$7)",
                spec.aggregate_id,
                spec.generation_hash,
                spec.source_hash,
                cutoff,
                "2026-08",
                spec.revision,
                occurred_at,
            )
        value = str(event_id)
        if register is not None:
            register(value)
    return value


class DeterministicEffects:
    """Synthetic, idempotent side-effect boundary for the production dispatcher."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.campaign_keys: set[str] = set()
        self.contest_keys: set[str] = set()
        self.grile_keys: set[str] = set()
        self.sales_transport_calls = 0

    async def publish_campaigns(
        self, *, month: str, generation_hash: str, revision: int
    ) -> dict[str, int]:
        async with self._lock:
            self.campaign_keys.add(f"{month}:{generation_hash}:{revision}")
        return {"revision": 101}

    async def publish_contests(
        self, *, month: str, generation_hash: str, revision: int
    ) -> dict[str, int]:
        async with self._lock:
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
    ) -> dict[str, Any]:
        if campaign_revision != 101 or contest_revision != 202:
            raise RuntimeError("sales projector revision lineage drifted")
        key = f"grile_v2:{generation_hash}:{sales_revision}"
        async with self._lock:
            self.sales_transport_calls += 1
            self.grile_keys.add(key)
        return {
            "domain_generation_key": key,
            "effect_sha256": hashlib.sha256(key.encode()).hexdigest(),
            "store_count": 21,
        }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    db_identity = validate_isolated_url(args.dsn, database=True)
    valkey_identity = validate_isolated_url(args.valkey_url, database=False)
    api = load_production_api(root)
    pool = await asyncpg.create_pool(
        args.dsn, min_size=4, max_size=16, command_timeout=30
    )
    valkey = Redis.from_url(args.valkey_url, decode_responses=True)
    try:
        valkey_info = await valkey.info(section="server")
        if not valkey_info.get("redis_version"):
            raise RuntimeError("isolated Valkey did not identify its server version")
        return await run_workload(
            args,
            pool=pool,
            valkey=valkey,
            valkey_info=valkey_info,
            api=api,
            db_identity=db_identity,
            valkey_identity=valkey_identity,
        )
    finally:
        await valkey.aclose()
        await pool.close()


async def run_workload(
    args: argparse.Namespace,
    *,
    pool: asyncpg.Pool,
    valkey: Redis,
    valkey_info: dict[str, Any],
    api: ProductionApi,
    db_identity: dict[str, Any],
    valkey_identity: dict[str, Any],
) -> dict[str, Any]:

    handler_limit = asyncio.Semaphore(args.handlers)
    stop = asyncio.Event()
    feed_done = asyncio.Event()
    enqueue_monotonic: dict[str, float] = {}
    enqueue_offsets: list[float] = []
    measured_ordinals: dict[str, int] = {}
    latencies_by_event: dict[str, float] = {}
    failed_attempts = 0
    delivery_attempts = 0
    ratio_samples: list[dict[str, float]] = []
    pending_age_samples: list[dict[str, float]] = []
    state_lock = asyncio.Lock()
    effects = DeterministicEffects()
    first_measured = 0.0

    async with pool.acquire() as connection:
        migration = await connection.fetchrow(
            "SELECT filename, checksum FROM schema_migrations ORDER BY filename DESC LIMIT 1"
        )
        if (
            not migration
            or migration["filename"]
            != "069_ai_cohort_and_transactional_outbox.sql"
        ):
            raise RuntimeError("outbox workload requires production schema through exact 069")
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
        migration_checksum = str(migration["checksum"])

    repository = api.repository_type(pool)

    async def measured_attempt(event: Any) -> tuple[str, int | None, bool]:
        nonlocal delivery_attempts, failed_attempts
        event_id = str(event.id)
        ordinal = measured_ordinals.get(event_id)
        if ordinal is None:
            return event_id, None, False
        attempt = int(event.attempt_count)
        should_fail = ordinal % 200 == 0 and attempt == 1
        async with state_lock:
            delivery_attempts += 1
            if should_fail:
                failed_attempts += 1
        return event_id, ordinal, should_fail

    async def finish_success(event_id: str, ordinal: int | None) -> None:
        if ordinal is None:
            return
        async with state_lock:
            if event_id in latencies_by_event:
                raise RuntimeError("production dispatcher delivered one event twice")
            latencies_by_event[event_id] = time.monotonic() - enqueue_monotonic[event_id]

    async def sales_consumer(event: Any) -> dict[str, str]:
        async with handler_limit:
            event_id, ordinal, should_fail = await measured_attempt(event)
            if should_fail:
                raise RuntimeError("slo_transient")
            receipt = await api.deliver_sales(
                event,
                publish_campaigns=effects.publish_campaigns,
                publish_contests=effects.publish_contests,
                sync_grile_v2=effects.sync_grile_v2,
            )
            await finish_success(event_id, ordinal)
            return receipt

    def receipt_consumer(consumer: str) -> Callable[[Any], Awaitable[dict[str, str]]]:
        async def handle(event: Any) -> dict[str, str]:
            async with handler_limit:
                event_id, ordinal, should_fail = await measured_attempt(event)
                if should_fail:
                    raise RuntimeError("slo_transient")
                key = f"{consumer}:{event.generation_hash}:{event.revision}"
                await finish_success(event_id, ordinal)
                return {
                    "consumer": consumer,
                    "domain_generation_key": key,
                    "effect_sha256": hashlib.sha256(key.encode()).hexdigest(),
                }

        return handle

    consumers: dict[str, Callable[[Any], Awaitable[dict[str, str]]]] = {
        EVENT_TYPES[0][0]: sales_consumer
    }
    consumers.update(
        {
            event_type: receipt_consumer(consumer)
            for event_type, _aggregate, _fixture, consumer in EVENT_TYPES[1:]
        }
    )

    async def claimer(index: int) -> None:
        while not stop.is_set():
            processed = await api.dispatch_once(
                repository=repository,
                consumers=consumers,
                owner=f"slo-{index}",
                now=datetime.now(timezone.utc),
                batch_size=args.batch_size,
                lease_seconds=60,
            )
            if not processed:
                await asyncio.sleep(0.02)

    claim_tasks = [
        asyncio.create_task(claimer(index), name=f"outbox-slo-claimer-{index}")
        for index in range(args.claimers)
    ]
    sampler: asyncio.Task[None] | None = None

    def ensure_claimers_healthy() -> None:
        for task in claim_tasks:
            if not task.done():
                continue
            if task.cancelled():
                raise RuntimeError(f"outbox claimer stopped early: {task.get_name()}")
            error = task.exception()
            if error is not None:
                raise RuntimeError(
                    f"outbox claimer failed early: {task.get_name()}"
                ) from error
            if not stop.is_set():
                raise RuntimeError(
                    f"outbox claimer exited before workload completion: {task.get_name()}"
                )
        if sampler is not None and sampler.done() and not feed_done.is_set():
            if sampler.cancelled():
                raise RuntimeError("outbox sampler stopped during the measured feed")
            error = sampler.exception()
            if error is not None:
                raise RuntimeError("outbox sampler failed during the measured feed") from error
            raise RuntimeError("outbox sampler exited before the measured feed completed")

    async def feed(specs: list[EventSpec], *, paced: bool) -> None:
        nonlocal first_measured
        started = time.monotonic()
        if paced:
            first_measured = started
        async with pool.acquire() as connection:
            for index, spec in enumerate(specs):
                ensure_claimers_healthy()
                if paced:
                    due = started + index / args.rate
                    delay = due - time.monotonic()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    ensure_claimers_healthy()

                def register(event_id: str, item: EventSpec = spec) -> None:
                    if paced:
                        registered_at = time.monotonic()
                        enqueue_monotonic[event_id] = registered_at
                        enqueue_offsets.append(registered_at - started)
                        measured_ordinals[event_id] = item.ordinal

                await _emit_fixture(
                    connection, spec, api, register=register if paced else None
                )

    async def wait_for_warmup(timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ensure_claimers_healthy()
            async with pool.acquire() as connection:
                completed = await connection.fetchval(
                    "SELECT count(*) FROM retail_outbox_events WHERE state='completed'"
                )
            if completed == args.warmup:
                return
            await asyncio.sleep(0.1)
        raise RuntimeError("outbox warmup did not drain in 60 seconds")

    async def sample_until_done() -> None:
        last_ratio_sample = -5.0
        drain_deadline: float | None = None
        while True:
            ensure_claimers_healthy()
            async with pool.acquire() as connection:
                row = await connection.fetchrow(
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
            elapsed = time.monotonic() - first_measured
            pending_age_samples.append(
                {
                    "elapsed_seconds": elapsed,
                    "oldest_pending_seconds": float(row["oldest_pending"]),
                    "head_blocked_age_seconds": float(row["head_blocked_age"]),
                }
            )
            async with state_lock:
                attempts, failures = delivery_attempts, failed_attempts
            if attempts >= 200 and elapsed - last_ratio_sample >= 5:
                ratio = failures / attempts
                ratio_samples.append(
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
            if feed_done.is_set():
                if drain_deadline is None:
                    drain_deadline = time.monotonic() + 60.0
                if row["completed"] == args.events:
                    if row["pending"] or row["processing"] or row["dead"]:
                        raise RuntimeError("terminal outbox counts are inconsistent")
                    return
                if time.monotonic() > drain_deadline:
                    raise RuntimeError("measured outbox run exceeded 60-second drain window")
            await asyncio.sleep(1)

    try:
        await feed(event_specs(args.warmup, measured=False), paced=False)
        await wait_for_warmup()
        sampler = asyncio.create_task(sample_until_done(), name="outbox-slo-sampler")
        try:
            await feed(event_specs(args.events, measured=True), paced=True)
            feed_done.set()
            await sampler
        except BaseException:
            feed_done.set()
            if not sampler.done():
                sampler.cancel()
            await asyncio.gather(sampler, return_exceptions=True)
            raise
    finally:
        stop.set()
        # Do not let a secondary cleanup exception mask the primary workload
        # failure; the wrapper still receives a non-zero exit immediately.
        await asyncio.gather(*claim_tasks, return_exceptions=True)

    async with pool.acquire() as connection:
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
        receipt_counts = {
            row["event_type"]: row["count"]
            for row in await connection.fetch(
                """SELECT event_type, count(*) FROM retail_outbox_consumer_receipts r
                   JOIN retail_outbox_events e ON e.id=r.event_id
                   WHERE e.aggregate_id LIKE 'm%'
                   GROUP BY event_type ORDER BY event_type"""
            )
        }
    latencies = list(latencies_by_event.values())
    p95 = nearest_rank(latencies, 0.95)
    oldest = max(sample["oldest_pending_seconds"] for sample in pending_age_samples)
    ratio = failed_attempts / delivery_attempts
    passed = (
        terminal
        == {
            "completed": EVENTS,
            "pending": 0,
            "processing": 0,
            "dead": 0,
            "total": EVENTS,
        }
        and len(latencies) == EVENTS
        and delivery_attempts == EVENTS + 50
        and failed_attempts == 50
        and ratio < 0.01
        and ratio_samples
        and max(float(sample["ratio"]) for sample in ratio_samples) < 0.01
        and p95 < 30.0
        and oldest < 60.0
        and len(effects.grile_keys) == 2_000
        and effects.sales_transport_calls == 2_000
        and set(receipt_counts.values()) == {2_000}
    )
    payload = {
        "schema_version": 2,
        "authority": "backend/scripts/run_outbox_slo_workload.py",
        "seed": args.seed,
        "database_identity": db_identity,
        "valkey_identity": valkey_identity,
        "valkey_version": str(valkey_info["redis_version"]),
        "migration_069_checksum": migration_checksum,
        "production_api": api.authorities,
        "production_dispatch": {
            "repository": "repositories.transactional_outbox.TransactionalOutboxRepository",
            "dispatcher": "services.outbox_worker.dispatch_outbox_once",
            "sales_delivery": "services.grile_outbox_delivery.deliver_sales_generation_event",
            "sales_producer": "repositories.transactional_outbox.emit_sales_generation_promoted",
            "dispatcher_valkey_dependency": False,
        },
        "fixture_adapters": {
            "non_sales_producers": [item[2] for item in EVENT_TYPES[1:]],
            "source": "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql",
            "effects": "deterministic non-network callbacks; sales uses production delivery chain",
        },
        "workload": {
            "warmup": args.warmup,
            "events": args.events,
            "rate_per_second": args.rate,
            "claimers": args.claimers,
            "batch_size": args.batch_size,
            "handlers": args.handlers,
            "event_types": [item[0] for item in EVENT_TYPES],
            "aggregates_per_type": 200,
            "sequences_per_aggregate": 10,
            "transient_failures": 50,
            "retry_seconds": 5,
            "lease_seconds": 60,
        },
        "terminal": terminal,
        "receipt_counts": receipt_counts,
        "effective_sales_mutations": len(effects.grile_keys),
        "sales_transport_calls": effects.sales_transport_calls,
        "duplicate_effects": effects.sales_transport_calls - len(effects.grile_keys),
        "delivery_attempts": delivery_attempts,
        "failed_attempts": failed_attempts,
        "failure_ratio": ratio,
        "failure_ratio_samples": ratio_samples,
        "latency_seconds": latencies,
        "latency_input_sha256": canonical_sha256(latencies),
        "enqueue_offsets_seconds": enqueue_offsets,
        "enqueue_offsets_sha256": canonical_sha256(enqueue_offsets),
        "p95_delivery_seconds": p95,
        "pending_age_samples": pending_age_samples,
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
    return payload


def self_test() -> None:
    before = os.environ.get("UNIHUB_TEST_DATABASE")
    os.environ["UNIHUB_TEST_DATABASE"] = "1"
    refused = 0
    for value, database in (
        ("postgresql://u:p@server:5432/unihub", True),
        ("postgresql://u:p@127.0.0.1:5432/unihub_test", True),
        ("redis://server:6379/0", False),
    ):
        try:
            validate_isolated_url(value, database=database)
        except ValueError:
            refused += 1
    if before is None:
        os.environ.pop("UNIHUB_TEST_DATABASE", None)
    else:
        os.environ["UNIHUB_TEST_DATABASE"] = before
    specs = event_specs(EVENTS, measured=True)
    if (
        refused != 3
        or len(specs) != EVENTS
        or len({spec.generation_hash for spec in specs}) != EVENTS
        or sum(spec.ordinal % 200 == 0 for spec in specs) != 50
    ):
        raise SystemExit("outbox deterministic/isolation contract drifted")
    load_production_api(Path(__file__).resolve().parents[2])
    print("outbox authority self-test PASS: runtime APIs, isolation and 10k contract stable")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn")
    parser.add_argument("--valkey-url")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--warmup", type=int)
    parser.add_argument("--events", type=int)
    parser.add_argument("--rate", type=int)
    parser.add_argument("--claimers", type=int)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--handlers", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return args
    expected = (SEED, WARMUP, EVENTS, RATE, CLAIMERS, BATCH_SIZE, HANDLERS)
    actual = (
        args.seed,
        args.warmup,
        args.events,
        args.rate,
        args.claimers,
        args.batch_size,
        args.handlers,
    )
    if actual != expected:
        parser.error(f"workload arguments differ from locked contract: {actual!r}")
    if not args.dsn or not args.valkey_url or not args.output:
        parser.error("dsn, valkey URL and output are required")
    if args.output.exists() or args.output.is_symlink():
        parser.error("output already exists")
    return args


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        return
    payload = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    if payload["result"] != "PASS":
        raise SystemExit("outbox SLO thresholds failed")


if __name__ == "__main__":
    main()
