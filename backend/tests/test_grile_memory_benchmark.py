from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace

from scripts.benchmark_grile_worker_memory import MemorySample, benchmark, evaluate_samples


def sample(run: int, *, rss: float, uss: float, sha: str = "same") -> MemorySample:
    return MemorySample(
        run=run,
        rss_mb=rss,
        uss_mb=uss,
        traced_current_mb=1.0,
        traced_peak_mb=2.0,
        objects=100,
        threads=2,
        open_transports=0,
        business_sha256=sha,
    )


def test_memory_gate_rejects_monotonic_growth_even_below_slope_limit() -> None:
    samples = [sample(index, rss=50 + index, uss=30 + index) for index in range(1, 11)]

    report = evaluate_samples(samples)

    assert report["passed"] is False
    assert "monotonic_post_gc_growth" in report["reasons"]


def test_memory_gate_rejects_transport_or_semantic_leak() -> None:
    samples = [sample(index, rss=50, uss=30) for index in range(1, 11)]
    samples[5] = replace(samples[5], open_transports=1, business_sha256="changed")

    report = evaluate_samples(samples)

    assert report["passed"] is False
    assert "open_google_transports" in report["reasons"]
    assert "business_semantics_changed" in report["reasons"]


def test_ten_run_fixture_passes_with_closed_clients_and_stable_semantics() -> None:
    args = argparse.Namespace(
        runs=10,
        stores=12,
        concurrency=3,
        client_allocation_kib=128,
        month="2026-08",
    )

    report = asyncio.run(benchmark(args))

    # The dedicated CLI is the strict process-memory gate.  Under the complete
    # pytest process unrelated allocator activity can make the monotonic-noise
    # check fluctuate, so this integration test asserts the deterministic
    # lifecycle and threshold invariants.
    assert not {
        "rss_limit",
        "rss_slope",
        "uss_slope",
        "thread_growth_after_warmup",
        "open_google_transports",
        "business_semantics_changed",
    }.intersection(report["evaluation"]["reasons"])
    assert report["evaluation"]["max_rss_mb"] < 300
    assert all(sample["open_transports"] == 0 for sample in report["samples"])
    assert len({sample["business_sha256"] for sample in report["samples"]}) == 1
