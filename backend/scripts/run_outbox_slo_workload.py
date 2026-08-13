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

from scripts.outbox_slo_workload_engine import OutboxWorkload


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
            # These four event types are reserved in Release B. Their exact
            # migration-069 SQL wrappers are isolated transport fixtures, not
            # application producers or protected business lineage.
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
    workload = OutboxWorkload(
        args,
        pool=pool,
        valkey_info=valkey_info,
        api=api,
        db_identity=db_identity,
        valkey_identity=valkey_identity,
        event_types=EVENT_TYPES,
        event_specs=event_specs,
        emit_fixture=_emit_fixture,
        effects=DeterministicEffects(),
        canonical_sha256=canonical_sha256,
        nearest_rank=nearest_rank,
        locked_events=EVENTS,
    )
    return await workload.run()


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
