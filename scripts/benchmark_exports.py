#!/usr/bin/env python3
"""Fresh-process export benchmark; evidence tool, never a CI gate."""
from __future__ import annotations

import json
import multiprocessing as mp
import resource
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _columns() -> list[dict[str, str]]:
    return [
        {"key": f"metric_{index}", "label": f"Metric {index}", "type": "currency" if index % 3 == 0 else "text", "group": "Benchmark"}
        for index in range(20)
    ]


def _worker(kind: str, rows_count: int, long_text: bool, output: Any) -> None:
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from services.exports import ExportsService

    columns = _columns()
    text = "x" * 512 if long_text else "store"
    rows = [{column["key"]: (text if column["type"] == "text" else index * 1.25) for column in columns} for index in range(rows_count)]
    request: dict[str, Any] = {"dataset": "stores", "months": ["2026-07"], "daily_metrics": ["total_sales"]}
    service = ExportsService(None)  # type: ignore[arg-type]
    started = time.perf_counter()
    artifact = None
    try:
        if kind == "simple":
            artifact = service._render_simple_table_xlsx(request, {"columns": columns, "rows": rows}, None, None)
        elif kind == "daily_chart":
            # This is the in-process part of the chart variant; the enclosing
            # spawned benchmark process measures its real RSS independently.
            daily_rows = [
                {"import_month": "2026-07", "day_of_month": day, "total_sales": day * 100, "total_quantity": day, "total_receipts": day, "receipt_2plus_count": 0, "focus_quantity": 0, "target": 0, "working_days": day, "store_count": 1, "agent_count": 1, "incentive_sales": 0, "incentive_quantity": 0, "incentive_bonus": 0, "promo_sales": 0, "promo_quantity": 0}
                for day in range(1, 32)
            ]
            artifact = service._render_table_xlsx(request, {"columns": columns, "rows": rows}, None, daily_rows)
        else:
            from services.export_complex_worker import render_daily_comparison_xlsx

            comparison_rows = [
                {"day": day, "total_sales:2026-06": day * 100, "total_sales:2026-07": day * 120}
                for day in range(1, 32)
            ]
            result = render_daily_comparison_xlsx({
                "request": request,
                "months": ["2026-06", "2026-07"],
                "metrics": ["total_sales"],
                "levels": ["general"],
                "include_closed_stores": False,
                "selected_days": None,
                "tables": [("general", {"columns": [{"key": "day", "label": "Zi", "type": "integer"}, {"key": "total_sales:2026-06", "label": "2026-06 Vanzari", "type": "currency"}, {"key": "total_sales:2026-07", "label": "2026-07 Vanzari", "type": "currency"}], "rows": comparison_rows})],
                "level_config": {"general": {"label": "General", "sheet": "General", "dimensions": []}},
                "metric_labels": {"total_sales": "Vanzari"},
                "max_output_bytes": 64 * 1024 * 1024,
                "max_peak_rss_bytes": 512 * 1024 * 1024,
            })
            from services.exports import XlsxArtifact
            from pathlib import Path as WorkerPath
            path = WorkerPath(result["path"])
            stream = path.open("r+b")
            path.unlink(missing_ok=True)
            artifact = XlsxArtifact(stream=stream, filename=result["filename"], size=result["size"])
        # XLSX is complete before the first byte is safe to stream; report that
        # true TTFB rather than a misleading pre-save timestamp.
        ttfb = time.perf_counter() - started
        first_chunk = next(artifact.iter_chunks(), b"")
        output.put({"kind": kind, "rows": rows_count, "columns": len(columns), "long_text": long_text, "wall_seconds": round(time.perf_counter() - started, 3), "ttfb_seconds": round(ttfb, 3), "output_bytes": artifact.size, "first_chunk_bytes": len(first_chunk), "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024})
    finally:
        if artifact is not None:
            artifact.close()


def run_case(kind: str, rows_count: int, long_text: bool) -> dict[str, Any]:
    context = mp.get_context("spawn")
    # SimpleQueue writes directly to the pipe. A regular Queue starts its
    # feeder thread lazily on ``put()``, after the complex renderer has applied
    # RLIMIT_AS, which can make the benchmark fail for harness-only reasons.
    queue = context.SimpleQueue()
    process = context.Process(target=_worker, args=(kind, rows_count, long_text, queue))
    process.start()
    process.join()
    if process.exitcode != 0 or queue.empty():
        raise RuntimeError(f"benchmark child failed for {kind}, rows={rows_count}")
    return queue.get()


def run_concurrent() -> dict[str, Any]:
    context = mp.get_context("spawn")
    queues = [context.SimpleQueue(), context.SimpleQueue()]
    processes = [context.Process(target=_worker, args=("daily_chart", 10_000, False, queue)) for queue in queues]
    started = time.perf_counter()
    for process in processes:
        process.start()
    for process in processes:
        process.join()
    if any(process.exitcode != 0 for process in processes) or any(queue.empty() for queue in queues):
        raise RuntimeError("concurrent chart benchmark failed")
    return {"concurrency": 2, "wall_seconds": round(time.perf_counter() - started, 3), "cases": [queue.get() for queue in queues]}


def main() -> None:
    cases = [
        run_case("simple", 10_000, False),
        run_case("simple", 50_000, False),
        run_case("simple", 10_000, True),
        run_case("daily_chart", 10_000, False),
        run_case("daily_comparison", 31, False),
    ]
    print(json.dumps({"writer": "fresh_process", "cases": cases, "concurrent_daily_chart": run_concurrent()}, indent=2))


if __name__ == "__main__":
    main()
