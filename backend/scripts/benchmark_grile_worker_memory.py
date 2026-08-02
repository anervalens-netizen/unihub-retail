#!/usr/bin/env python3
"""Repeatable memory gate for the full Grile check lifecycle.

The default fixture executes the production orchestration, executor and client
lifecycle without DB or Google mutations.  It records post-GC RSS/USS,
tracemalloc, Python object count, threads and open fake transports for ten runs.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date
import gc
from hashlib import sha256
import json
from pathlib import Path
import sys
import threading
import tracemalloc
from typing import Any, Iterator, cast

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import grile


DEFAULT_RUNS = 10
DEFAULT_STORES = 24
WARMUP_RUNS = 2
MAX_RSS_MB = 300.0
MAX_SLOPE_MB_PER_RUN = 5.0
MONOTONIC_GROWTH_TOLERANCE_MB = 0.5


@dataclass(frozen=True)
class MemorySample:
    run: int
    rss_mb: float
    uss_mb: float
    traced_current_mb: float
    traced_peak_mb: float
    objects: int
    threads: int
    open_transports: int
    business_sha256: str


class FixtureTransport:
    open_count = 0

    def __init__(self, allocation_kib: int) -> None:
        self.payload = bytearray(allocation_kib * 1024)
        self.closed = False
        FixtureTransport.open_count += 1

    def close(self) -> None:
        if self.closed:
            return
        self.payload.clear()
        self.closed = True
        FixtureTransport.open_count -= 1


class FixtureResource:
    def __init__(self, allocation_kib: int) -> None:
        self._http = FixtureTransport(allocation_kib)


class FixtureRepository:
    def __init__(
        self,
        stores: list[dict[str, Any]],
        expected: dict[str, dict[str, Any]],
        captured: dict[int, list[dict[str, Any]]],
    ) -> None:
        self.stores = stores
        self.expected = expected
        self.captured = captured

    async def get_active_sheets(self, _month: str) -> list[Any]:
        return self.stores

    async def get_expected_by_site(self, _month: str) -> dict[str, dict[str, Any]]:
        return self.expected

    async def claim_run(
        self,
        run_id: int,
        *,
        progress_total: int,
        site_codes: list[str],
    ) -> dict[str, int]:
        del progress_total
        self.captured[run_id] = []
        return {site_code: index + 1 for index, site_code in enumerate(site_codes)}

    async def record_full_observation(
        self,
        run_id: int,
        row: dict[str, Any],
        *,
        generation: int,
        checked_by_sub: str | None = None,
    ) -> bool:
        del generation, checked_by_sub
        self.captured[run_id].append(dict(row))
        return True

    async def set_run_progress(self, _run_id: int, _current: int) -> None:
        return None

    async def finalize_run(self, _run_id: int, **_kwargs: Any) -> None:
        return None


def _proc_memory_mb() -> tuple[float, float]:
    values: dict[str, int] = {}
    with Path("/proc/self/smaps_rollup").open(encoding="utf-8") as stream:
        for line in stream:
            key, separator, remainder = line.partition(":")
            if not separator:
                continue
            raw = remainder.strip().split()
            if raw and raw[0].isdigit():
                values[key] = int(raw[0])
    rss_kib = values.get("Rss", 0)
    uss_kib = (
        values.get("Private_Clean", 0)
        + values.get("Private_Dirty", 0)
        + values.get("Private_Hugetlb", 0)
    )
    return rss_kib / 1024.0, uss_kib / 1024.0


def _linear_slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_mean = (len(values) - 1) / 2
    y_mean = sum(values) / len(values)
    numerator = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values))
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    return numerator / denominator


def _monotonic_growth(values: list[float]) -> bool:
    return (
        len(values) > 1
        and all(current >= previous for previous, current in zip(values, values[1:]))
        and values[-1] - values[0] >= MONOTONIC_GROWTH_TOLERANCE_MB
        and any(current > previous for previous, current in zip(values, values[1:]))
    )


def evaluate_samples(samples: list[MemorySample]) -> dict[str, Any]:
    if len(samples) <= WARMUP_RUNS:
        raise ValueError(f"At least {WARMUP_RUNS + 1} samples are required")
    stable = samples[WARMUP_RUNS:]
    rss = [sample.rss_mb for sample in stable]
    uss = [sample.uss_mb for sample in stable]
    threads = [sample.threads for sample in stable]
    hashes = {sample.business_sha256 for sample in samples}
    reasons: list[str] = []
    rss_slope = _linear_slope(rss)
    uss_slope = _linear_slope(uss)
    if max(sample.rss_mb for sample in samples) >= MAX_RSS_MB:
        reasons.append("rss_limit")
    if rss_slope >= MAX_SLOPE_MB_PER_RUN:
        reasons.append("rss_slope")
    if uss_slope >= MAX_SLOPE_MB_PER_RUN:
        reasons.append("uss_slope")
    if _monotonic_growth(rss) or _monotonic_growth(uss):
        reasons.append("monotonic_post_gc_growth")
    if max(threads) != min(threads):
        reasons.append("thread_growth_after_warmup")
    if any(sample.open_transports for sample in samples):
        reasons.append("open_google_transports")
    if len(hashes) != 1:
        reasons.append("business_semantics_changed")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "warmup_runs": WARMUP_RUNS,
        "rss_slope_mb_per_run": round(rss_slope, 4),
        "uss_slope_mb_per_run": round(uss_slope, 4),
        "max_rss_mb": round(max(sample.rss_mb for sample in samples), 4),
        "max_uss_mb": round(max(sample.uss_mb for sample in samples), 4),
        "thread_range_after_warmup": [min(threads), max(threads)],
        "business_sha256": next(iter(hashes)) if len(hashes) == 1 else None,
    }


def _business_hash(rows: list[dict[str, Any]]) -> str:
    projected = [
        {
            key: row.get(key)
            for key in (
                "site_code",
                "completion_pct",
                "grila_target",
                "grila_sales",
                "db_target",
                "db_sales_mtd",
                "fill_status",
                "target_status",
                "sales_status",
                "error_code",
            )
        }
        for row in sorted(rows, key=lambda item: str(item["site_code"]))
    ]
    payload = json.dumps(projected, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


@contextmanager
def fixture_runtime(
    *,
    store_count: int,
    client_allocation_kib: int,
) -> Iterator[dict[int, list[dict[str, Any]]]]:
    stores = [
        {
            "site_code": f"SITE{index:03d}",
            "sheet_id": f"sheet-{index:03d}",
            "template_version": "v2",
        }
        for index in range(store_count)
    ]
    expected = {
        store["site_code"]: {
            "db_target": 100.0,
            "db_sales_mtd": 50.0,
            "db_max_sale_date": date(2026, 8, 1),
        }
        for store in stores
    }
    captured: dict[int, list[dict[str, Any]]] = {}
    values = [
        {"values": [[100.0]]},
        {"values": [[50.0]]},
        {"values": [[1.0]]},
        {"values": []},
        {"values": []},
    ]
    originals = {
        "GrileRepository": grile.GrileRepository,
        "get_credentials": grile.get_credentials,
        "build_services": grile.build_services,
        "fetch_grila": grile.fetch_grila,
        "fetch_mod_time": grile.fetch_mod_time,
    }

    def repository_factory(_pool: object) -> FixtureRepository:
        return FixtureRepository(stores, expected, captured)

    def build_fixture_services() -> tuple[FixtureResource, FixtureResource]:
        return (
            FixtureResource(client_allocation_kib),
            FixtureResource(client_allocation_kib),
        )

    setattr(grile, "GrileRepository", repository_factory)
    setattr(grile, "get_credentials", lambda: object())
    setattr(grile, "build_services", build_fixture_services)
    setattr(grile, "fetch_grila", lambda *_args: values)
    setattr(grile, "fetch_mod_time", lambda *_args: "2026-08-01T12:00:00Z")
    try:
        yield captured
    finally:
        for name, value in originals.items():
            setattr(grile, name, value)


async def benchmark(args: argparse.Namespace) -> dict[str, Any]:
    samples: list[MemorySample] = []
    FixtureTransport.open_count = 0
    tracemalloc.start()
    try:
        with fixture_runtime(
            store_count=args.stores,
            client_allocation_kib=args.client_allocation_kib,
        ) as captured:
            for run_number in range(1, args.runs + 1):
                await grile.run_grile_check(
                    cast(asyncpg.Pool, object()),
                    month=args.month,
                    source="memory-benchmark",
                    run_id=run_number,
                    concurrency=args.concurrency,
                )
                business_sha256 = _business_hash(captured.pop(run_number))
                gc.collect()
                traced_current, traced_peak = tracemalloc.get_traced_memory()
                rss_mb, uss_mb = _proc_memory_mb()
                samples.append(
                    MemorySample(
                        run=run_number,
                        rss_mb=round(rss_mb, 4),
                        uss_mb=round(uss_mb, 4),
                        traced_current_mb=round(traced_current / 1024 / 1024, 4),
                        traced_peak_mb=round(traced_peak / 1024 / 1024, 4),
                        objects=len(gc.get_objects()),
                        threads=threading.active_count(),
                        open_transports=FixtureTransport.open_count,
                        business_sha256=business_sha256,
                    )
                )
    finally:
        tracemalloc.stop()
    return {
        "fixture": {
            "month": args.month,
            "runs": args.runs,
            "stores": args.stores,
            "concurrency": args.concurrency,
            "client_allocation_kib": args.client_allocation_kib,
            "google_and_db_mutations": False,
        },
        "samples": [asdict(sample) for sample in samples],
        "evaluation": evaluate_samples(samples),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--stores", type=int, default=DEFAULT_STORES)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--client-allocation-kib", type=int, default=512)
    parser.add_argument("--month", default="2026-08")
    args = parser.parse_args()
    if args.runs < WARMUP_RUNS + 1:
        parser.error(f"--runs must be at least {WARMUP_RUNS + 1}")
    if min(args.stores, args.concurrency, args.client_allocation_kib) < 1:
        parser.error("stores, concurrency and allocation must be positive")
    report = asyncio.run(benchmark(args))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["evaluation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
