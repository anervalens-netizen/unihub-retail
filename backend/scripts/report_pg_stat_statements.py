#!/usr/bin/env python3
"""Emit a read-only monthly PostgreSQL workload report for Retail queries."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import asyncpg
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(BACKEND_ROOT.parent / ".env")

STATEMENTS_SQL = """
SELECT
    queryid::text AS query_id,
    calls::bigint AS calls,
    total_exec_time::double precision AS total_exec_time_ms,
    mean_exec_time::double precision AS mean_exec_time_ms,
    rows::bigint AS rows,
    shared_blks_hit::bigint AS shared_blocks_hit,
    shared_blks_read::bigint AS shared_blocks_read,
    temp_blks_read::bigint AS temp_blocks_read,
    temp_blks_written::bigint AS temp_blocks_written,
    query
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND userid = (SELECT usesysid FROM pg_user WHERE usename = current_user)
  AND calls >= $1
  AND query !~* 'pg_stat_statements'
ORDER BY total_exec_time DESC, calls DESC, queryid
LIMIT $2
"""


def normalize_query(value: Any, *, max_length: int = 500) -> str:
    compact = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(compact) <= max_length:
        return compact
    return compact[: max_length - 3] + "..."


def statement_payload(row: Any) -> dict[str, Any]:
    return {
        "query_id": str(row["query_id"]),
        "calls": int(row["calls"]),
        "total_exec_time_ms": round(float(row["total_exec_time_ms"]), 3),
        "mean_exec_time_ms": round(float(row["mean_exec_time_ms"]), 3),
        "rows": int(row["rows"]),
        "shared_blocks_hit": int(row["shared_blocks_hit"]),
        "shared_blocks_read": int(row["shared_blocks_read"]),
        "temp_blocks_read": int(row["temp_blocks_read"]),
        "temp_blocks_written": int(row["temp_blocks_written"]),
        "query": normalize_query(row["query"]),
    }


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
    conn = await asyncpg.connect(database_url)
    try:
        async with conn.transaction():
            await conn.execute("SET TRANSACTION READ ONLY")
            installed = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements')"
            )
            if not installed:
                raise RuntimeError("pg_stat_statements extension is not installed")
            database_name = await conn.fetchval("SELECT current_database()")
            rows = await conn.fetch(STATEMENTS_SQL, min_calls, limit)
    finally:
        await conn.close()
    return {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "database": str(database_name),
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
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
