#!/usr/bin/env python3
"""Emit a read-only PostgreSQL workload snapshot with stable query fingerprints."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import asyncpg
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(REPO_ROOT / ".env")

STATEMENTS_SQL = """
SELECT
    queryid::text AS query_id,
    calls::bigint AS calls,
    total_exec_time::double precision AS total_exec_time_ms,
    mean_exec_time::double precision AS mean_exec_time_ms,
    min_exec_time::double precision AS min_exec_time_ms,
    max_exec_time::double precision AS max_exec_time_ms,
    stddev_exec_time::double precision AS stddev_exec_time_ms,
    rows::bigint AS rows,
    shared_blks_hit::bigint AS shared_blocks_hit,
    shared_blks_read::bigint AS shared_blocks_read,
    temp_blks_read::bigint AS temp_blocks_read,
    temp_blks_written::bigint AS temp_blocks_written,
    wal_bytes::numeric AS wal_bytes,
    query
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND userid = (SELECT usesysid FROM pg_user WHERE usename = current_user)
  AND calls >= $1
  AND query !~* 'pg_stat_statements'
ORDER BY total_exec_time DESC, calls DESC, queryid
LIMIT $2
"""


def normalize_query(value: Any, *, max_length: int | None = 500) -> str:
    compact = re.sub(r"\s+", " ", str(value or "")).strip()
    if max_length is None or len(compact) <= max_length:
        return compact
    if max_length < 4:
        raise ValueError("max_length must be at least 4 or None")
    return compact[: max_length - 3] + "..."


def query_fingerprint(value: Any) -> str:
    """Hash the full whitespace-normalized pg_stat_statements query text."""
    normalized = normalize_query(value, max_length=None)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def estimated_p95_ms(mean_ms: float, stddev_ms: float, max_ms: float) -> float:
    """Return a clearly labelled normal-approximation bounded by observed max."""
    if min(mean_ms, stddev_ms, max_ms) < 0:
        raise ValueError("statement timings cannot be negative")
    estimate = mean_ms + 1.644854 * stddev_ms
    return round(min(max_ms, max(mean_ms, estimate)), 3)


def statement_payload(row: Any) -> dict[str, Any]:
    calls = int(row["calls"])
    rows = int(row["rows"])
    mean_ms = float(row["mean_exec_time_ms"])
    min_ms = float(row.get("min_exec_time_ms", mean_ms))
    max_ms = float(row.get("max_exec_time_ms", mean_ms))
    stddev_ms = float(row.get("stddev_exec_time_ms", 0.0))
    shared_hit = int(row["shared_blocks_hit"])
    shared_read = int(row["shared_blocks_read"])
    query = row["query"]
    total_shared = shared_hit + shared_read
    return {
        "query_id": str(row["query_id"]),
        "fingerprint_sha256": query_fingerprint(query),
        "calls": calls,
        "total_exec_time_ms": round(float(row["total_exec_time_ms"]), 3),
        "mean_exec_time_ms": round(mean_ms, 3),
        "min_exec_time_ms": round(min_ms, 3),
        "max_exec_time_ms": round(max_ms, 3),
        "stddev_exec_time_ms": round(stddev_ms, 3),
        "estimated_p95_exec_time_ms": estimated_p95_ms(mean_ms, stddev_ms, max_ms),
        "estimated_p95_method": "min(observed_max, mean+1.644854*stddev)",
        "rows": rows,
        "mean_rows_per_call": round(rows / calls, 3) if calls else 0.0,
        "shared_blocks_hit": shared_hit,
        "shared_blocks_read": shared_read,
        "shared_read_ratio": round(shared_read / total_shared, 6) if total_shared else 0.0,
        "temp_blocks_read": int(row["temp_blocks_read"]),
        "temp_blocks_written": int(row["temp_blocks_written"]),
        "wal_bytes": int(row.get("wal_bytes", 0) or 0),
        "query": normalize_query(query),
    }


def runtime_sha() -> str | None:
    configured = os.getenv("UNIHUB_RUNTIME_SHA", "").strip()
    if re.fullmatch(r"[0-9a-f]{40}", configured):
        return configured
    try:
        value = subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


async def collect_report(
    database_url: str,
    *,
    limit: int = 25,
    min_calls: int = 1,
) -> dict[str, Any]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if min_calls < 1:
        raise ValueError("min_calls must be at least 1")
    conn = await asyncpg.connect(database_url, command_timeout=15)
    try:
        async with conn.transaction():
            await conn.execute("SET TRANSACTION READ ONLY")
            await conn.execute("SET LOCAL statement_timeout = '15s'")
            installed = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements')"
            )
            if not installed:
                raise RuntimeError("pg_stat_statements extension is not installed")
            database_name = await conn.fetchval("SELECT current_database()")
            server_version = await conn.fetchval("SHOW server_version")
            stats_reset = await conn.fetchval(
                "SELECT stats_reset FROM pg_stat_statements_info LIMIT 1"
            )
            rows = await conn.fetch(STATEMENTS_SQL, min_calls, limit)
    finally:
        await conn.close()
    return {
        "schema_version": 2,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "runtime_sha": runtime_sha(),
        "database": str(database_name),
        "server_version": str(server_version),
        "statistics_reset_at": stats_reset.isoformat() if stats_reset else None,
        "scope": "current_database_current_user",
        "order": "total_exec_time_desc",
        "limit": limit,
        "min_calls": min_calls,
        "statements": [statement_payload(row) for row in rows],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--min-calls", type=int, default=1)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    report = asyncio.run(
        collect_report(
            args.database_url,
            limit=args.limit,
            min_calls=args.min_calls,
        )
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
