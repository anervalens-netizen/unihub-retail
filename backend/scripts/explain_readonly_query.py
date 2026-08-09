#!/usr/bin/env python3
"""Run bounded EXPLAIN ANALYZE for one reviewed read-only SQL statement."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
from typing import Any

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|copy|create|alter|drop|truncate|grant|revoke|vacuum|analyze|refresh|call|do|set|reset|listen|notify|lock)\b",
    re.IGNORECASE,
)


def validate_readonly_sql(sql: str) -> str:
    compact = sql.strip()
    if not compact:
        raise ValueError("query is empty")
    if len(compact.encode("utf-8")) > 256_000:
        raise ValueError("query exceeds 256 KiB")
    without_final = compact[:-1].rstrip() if compact.endswith(";") else compact
    if ";" in without_final or "--" in without_final or "/*" in without_final:
        raise ValueError("multiple statements and SQL comments are forbidden")
    if not re.match(r"^(select|with)\b", without_final, re.IGNORECASE):
        raise ValueError("only SELECT/WITH statements are allowed")
    if _FORBIDDEN.search(without_final):
        raise ValueError("query contains a forbidden statement keyword")
    if "$" in without_final:
        raise ValueError("parameterized statements require a reviewed fixture and are not accepted here")
    return without_final


async def explain(
    database_url: str,
    sql: str,
    *,
    timeout_ms: int,
    expected_database: str,
) -> Any:
    if not 100 <= timeout_ms <= 120_000:
        raise ValueError("timeout_ms must be between 100 and 120000")
    safe_sql = validate_readonly_sql(sql)
    if os.getenv("UNIHUB_PERF_COPY_DATABASE", "").strip() != "1":
        raise RuntimeError("set UNIHUB_PERF_COPY_DATABASE=1 to confirm a non-production copy")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$-]{0,62}", expected_database):
        raise ValueError("expected_database is invalid")
    conn = await asyncpg.connect(database_url, command_timeout=(timeout_ms / 1000) + 5)
    try:
        actual_database = str(await conn.fetchval("SELECT current_database()"))
        if actual_database != expected_database:
            raise RuntimeError(
                f"refusing EXPLAIN: connected to {actual_database!r}, expected {expected_database!r}"
            )
        async with conn.transaction():
            await conn.execute("SET TRANSACTION READ ONLY")
            await conn.execute(f"SET LOCAL statement_timeout = '{timeout_ms}ms'")
            row = await conn.fetchval(
                "EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, SUMMARY, FORMAT JSON) " + safe_sql
            )
    finally:
        await conn.close()
    return row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query_file", type=Path)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--timeout-ms", type=int, default=10_000)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    result = asyncio.run(
        explain(
            args.database_url,
            args.query_file.read_text(encoding="utf-8"),
            timeout_ms=args.timeout_ms,
            expected_database=args.expected_database,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
