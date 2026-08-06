#!/usr/bin/env python3
"""Fresh-process XLSX writer benchmark; evidence tool, not a CI test."""
from __future__ import annotations

import json
import multiprocessing as mp
import resource
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _worker(rows_count: int, long_text: bool, output: mp.Queue) -> None:
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from services.exports import ExportsService

    columns = [
        {"key": f"metric_{index}", "label": f"Metric {index}", "type": "currency" if index % 3 == 0 else "text", "group": "Benchmark"}
        for index in range(20)
    ]
    text = "x" * 512 if long_text else "store"
    rows = [
        {column["key"]: (text if column["type"] == "text" else index * 1.25) for column in columns}
        for index in range(rows_count)
    ]
    service = ExportsService(None)  # type: ignore[arg-type]
    request: dict[str, Any] = {"dataset": "stores", "months": ["2026-07"]}
    started = time.perf_counter()
    artifact = service._render_simple_table_xlsx(request, {"columns": columns, "rows": rows}, None, None)
    try:
        peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        output.put({
            "rows": rows_count,
            "columns": len(columns),
            "long_text": long_text,
            "seconds": round(time.perf_counter() - started, 3),
            "output_bytes": artifact.size,
            "peak_rss_bytes": peak_rss,
        })
    finally:
        artifact.close()


def run_case(rows_count: int, long_text: bool) -> dict[str, Any]:
    context = mp.get_context("spawn")
    queue: mp.Queue = context.Queue()
    process = context.Process(target=_worker, args=(rows_count, long_text, queue))
    process.start()
    process.join()
    if process.exitcode != 0 or queue.empty():
        raise RuntimeError(f"benchmark child failed for rows={rows_count}, long_text={long_text}")
    return queue.get()


def main() -> None:
    cases = [
        run_case(10_000, False),
        run_case(50_000, False),
        run_case(10_000, True),
    ]
    print(json.dumps({"writer": "write_only", "cases": cases}, indent=2))


if __name__ == "__main__":
    main()
